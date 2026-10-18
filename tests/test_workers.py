"""The job queue shared by the API and workers (server/jobs.py, server/worker.py)."""
import io
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest
from conftest import FakeOCR, FakeTranslator
from PIL import Image

from netra_translate import NetraTranslate
from netra_translate.server.jobs import INTERRUPTED, INTERRUPTED_RETRY, JobOptions, JobStore
from netra_translate.server.settings import Settings
from netra_translate.server.worker import Worker


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=str(tmp_path / "jobs"), warmup=False, api_key=None, demo=False)


@pytest.fixture
def store(settings):
    return JobStore(settings)


def new_job(store, name="scan"):
    return store.create(png(), name, "png", 1, JobOptions())


def make_worker(settings, store, sample_blocks, ocr=None, calls=None):
    def factory(layout):
        if calls is not None:
            calls.append(layout)
        return NetraTranslate(ocr=ocr or FakeOCR(sample_blocks), translator=FakeTranslator())
    return Worker(settings, store, factory)


def wait_until(predicate, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


# ── the queue ──────────────────────────────────────────────────────────
def test_steps_run_in_the_order_they_were_queued(settings, store, sample_blocks):
    ids = [new_job(store, f"f{i}").id for i in range(5)]
    ocr = FakeOCR(sample_blocks)
    worker = make_worker(settings, store, sample_blocks, ocr=ocr)
    while worker.run_once():
        pass
    order = [os.path.basename(os.path.dirname(source)) for source, _ in ocr.calls]
    assert order == ids
    assert all(store.get(i).status == "done" for i in ids)


def test_a_step_is_claimed_once(settings, store):
    job = new_job(store)
    first, second = store.claim("w1"), store.claim("w2")
    assert first is not None and first.job_id == job.id and first.step == "ocr"
    assert second is None


def test_two_workers_never_run_the_same_job(settings, store, sample_blocks):
    import threading

    lock, runs = threading.Lock(), []

    class Slow(FakeOCR):
        def process_document(self, source, **kw):
            with lock:
                runs.append(source)
            time.sleep(0.05)
            return super().process_document(source, **kw)

    workers = [make_worker(settings, store, sample_blocks, ocr=Slow(sample_blocks)) for _ in range(2)]
    ids = [new_job(store, f"f{i}").id for i in range(8)]
    for w in workers:
        w.start()
    try:
        assert wait_until(lambda: all(store.get(i).status == "done" for i in ids))
    finally:
        for w in workers:
            w.stop(timeout=5)
    assert len(runs) == len(set(runs)) == 8


def test_two_worker_processes_share_the_queue(settings, store, tmp_path):
    """The real deployment: separate processes, one data directory."""
    script = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {os.path.dirname(__file__)!r})
        from conftest import FakeOCR, FakeTranslator
        from netra_translate import NetraTranslate
        from netra_translate.server.jobs import JobStore
        from netra_translate.server.settings import Settings
        from netra_translate.server.worker import Worker

        class Marking(FakeOCR):
            def process_document(self, source, **kw):
                open(os.path.join(os.path.dirname(source), f"ran-{{os.getpid()}}"), "w").close()
                time.sleep(0.3)
                return super().process_document(source, **kw)

        settings = Settings(data_dir={settings.data_dir!r}, warmup=False)
        blocks = [{{"id": "p0-b0", "type": "paragraph", "page": 0, "bbox": [0, 0, 9, 9], "text": "Hi"}}]
        Worker(settings, JobStore(settings),
               lambda layout: NetraTranslate(ocr=Marking(blocks), translator=FakeTranslator())).run()
    """)
    procs = [subprocess.Popen([sys.executable, "-c", script]) for _ in range(2)]
    try:
        assert wait_until(lambda: len(store.workers()) == 2, timeout=120), "workers didn't start"
        ids = [new_job(store, f"f{i}").id for i in range(8)]
        assert wait_until(lambda: all(store.get(i).status == "done" for i in ids), timeout=60)
    finally:
        for p in procs:
            p.kill()
            p.wait()
    markers = [[n for n in os.listdir(store.dir(i)) if n.startswith("ran-")] for i in ids]
    assert all(len(m) == 1 for m in markers), markers       # each job ran exactly once
    assert len({m[0] for m in markers}) == 2                # and both processes took jobs


# ── recovery ───────────────────────────────────────────────────────────
def test_a_dead_workers_claim_becomes_an_error(settings, store):
    job = new_job(store)
    store.beat("deadbeef", {"started": 0, "models_ready": True})
    task = store.claim("deadbeef")
    j = store.get(job.id)
    j.status, j.phase = "running", "ocr"
    store.save(j)

    store.recover()                 # the worker is alive: nothing happens
    assert store.get(job.id).status == "running"

    path = os.path.join(store.workers_dir, "deadbeef.json")
    with open(path, encoding="utf-8") as f:
        beat = json.load(f)
    beat["beat"] -= 3600            # no heartbeat for an hour
    with open(path, "w", encoding="utf-8") as f:
        json.dump(beat, f)
    store.recover()
    job = store.get(job.id)
    assert job.status == "error" and job.error == INTERRUPTED
    assert not os.path.exists(task.path)
    assert not os.path.exists(os.path.join(store.dir(job.id), "upload.bin"))


def test_interrupted_retranslation_keeps_the_ocr(settings, store, sample_blocks):
    job = new_job(store)
    make_worker(settings, store, sample_blocks).run_once()
    os.remove(os.path.join(store.dir(job.id), "translation.json"))   # as if it never finished
    store.retranslate(job.id, "km2en")
    store.claim("gone")             # claimed by a worker with no heartbeat
    store.recover()
    job = store.get(job.id)
    assert job.status == "error" and job.error == INTERRUPTED_RETRY and job.ocr_done


def test_queued_jobs_survive_a_restart(settings, sample_blocks):
    store = JobStore(settings)
    job = new_job(store)
    del store

    store = JobStore(settings)      # the API restarts with no worker running yet
    store.recover()
    assert store.get(job.id).status == "queued"
    make_worker(settings, store, sample_blocks).run_once()
    assert store.get(job.id).status == "done"


def test_deleting_a_running_job_stops_its_worker(settings, store, sample_blocks):
    class DeletesItself(FakeOCR):
        def process_document(self, source, **kw):
            store.delete(os.path.basename(os.path.dirname(source)))
            return super().process_document(source, **kw)

    job = new_job(store)
    worker = make_worker(settings, store, sample_blocks, ocr=DeletesItself(sample_blocks))
    assert worker.run_once() is True
    assert os.listdir(store.claims_dir) == []
    with pytest.raises(KeyError):
        store.get(job.id)


def test_stopped_worker_retires(settings, store, sample_blocks):
    worker = make_worker(settings, store, sample_blocks)
    worker.start()
    assert [w["id"] for w in store.workers()] == [worker.id]
    worker.stop(timeout=5)
    assert store.workers() == []


# ── the API without an embedded worker ─────────────────────────────────
@pytest.fixture
def api(settings):
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    from netra_translate.server.app import create_app

    loaded = []

    def factory(layout):
        loaded.append(layout)
        raise AssertionError("the API process must not load models")

    settings.embedded_worker = False
    with TestClient(create_app(settings, pipeline_factory=factory)) as c:
        yield c, loaded


def test_api_only_process_loads_no_models(api, settings, sample_blocks):
    c, loaded = api
    r = c.post("/v1/translate", files={"file": ("scan.png", png(), "image/png")})
    assert r.status_code == 202
    jid = r.json()["job"]["id"]
    time.sleep(0.5)
    assert c.get(f"/v1/jobs/{jid}").json()["job"]["status"] == "queued"
    assert loaded == [] and c.app.state.worker is None

    # A worker elsewhere picks it up.
    make_worker(settings, c.app.state.jobs, sample_blocks).run_once()
    assert c.get(f"/v1/jobs/{jid}").json()["job"]["status"] == "done"
    assert c.get(f"/v1/jobs/{jid}/result").status_code == 200


def test_ready_waits_for_a_worker(api, settings, sample_blocks):
    c, _ = api
    r = c.get("/ready")
    assert r.status_code == 503 and r.json() == {"ready": False, "workers": 0}
    assert c.get("/health").json() == {"ok": True, "models_ready": False}
    assert c.get("/v1/info").json()["workers"] == []

    worker = make_worker(settings, c.app.state.jobs, sample_blocks)
    worker.start()
    try:
        r = c.get("/ready")
        assert r.status_code == 200 and r.json() == {"ready": True, "workers": 1}
        info = c.get("/v1/info").json()
        assert info["models_ready"] is True and len(info["workers"]) == 1
        assert info["workers"][0]["busy"] is False
    finally:
        worker.stop(timeout=5)


def test_wait_sees_a_job_finished_by_another_worker(api, settings, sample_blocks):
    c, _ = api
    worker = make_worker(settings, JobStore(settings), sample_blocks)    # its own store, as in another process
    worker.start()
    try:
        r = c.post("/v1/translate", data={"wait": "true"}, files={"file": ("scan.png", png(), "image/png")})
        assert r.status_code == 200 and r.json()["job"]["status"] == "done"
    finally:
        worker.stop(timeout=5)

import io
import json
import os
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from conftest import FakeOCR, FakeTranslator
from fastapi.testclient import TestClient
from PIL import Image

from netra_translate import FORMATS, NetraTranslate
from netra_translate.server.app import create_app
from netra_translate.server.jobs import INTERRUPTED
from netra_translate.server.settings import Settings


def png(size=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def make_client(tmp_path, sample_blocks):
    """make_client(**settings) -> (TestClient, pipelines-by-layout). Closed after the test."""
    clients = []

    def make(ocr=None, **kw):
        pipes = {}

        def factory(layout):
            pipes[layout] = NetraTranslate(ocr=ocr or FakeOCR(sample_blocks), translator=FakeTranslator())
            return pipes[layout]

        settings = Settings(**{"data_dir": str(tmp_path / "jobs"), "warmup": False, "api_key": None,
                               "demo": False, **kw})
        c = TestClient(create_app(settings, pipeline_factory=factory))
        c.__enter__()
        clients.append(c)
        return c, pipes

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()[0]


def upload(c, data=None, name="scan.png", **form):
    return c.post("/v1/translate", data=form, files={"file": (name, data or png(), "image/png")})


def run(c, **form) -> dict:
    """Upload and wait for the job to finish."""
    r = upload(c, **form)
    assert r.status_code == 202, r.text
    job = c.app.state.jobs.wait(r.json()["job"]["id"], 10)
    return job.public()


# ── meta ───────────────────────────────────────────────────────────────
def test_health(client):
    assert client.get("/health").json() == {"ok": True, "models_ready": True}
    assert client.get("/healthz").status_code == 200


def test_info(make_client):
    c, _ = make_client(max_pages=7, demo=True)
    data = c.get("/v1/info").json()
    assert data["name"] == "Netra Translate"
    assert data["directions"] == ["auto", "en2km", "km2en"]
    assert data["formats"] == list(FORMATS)
    assert data["limits"]["max_pages"] == 7
    assert data["demo"] is True and data["auth"] is False


def test_static_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and "Netra Translate" in r.text
    for path in ("/static/app.css", "/static/tokens.css", "/static/brand/symbol.svg",
                 "/static/brand/wordmark-latin.svg", "/static/favicon.svg", "/static/js/main.js", "/static/js/job.js"):
        assert client.get(path).status_code == 200, path
    r = client.get("/static/fonts/KantumruyPro-Regular.woff2")
    assert r.status_code == 200 and len(r.content) > 10_000


# ── jobs ───────────────────────────────────────────────────────────────
def test_translate_job_end_to_end(client):
    job = run(client)
    assert job["status"] == "done" and job["pages"] == 1 and job["filename"] == "scan"
    assert job["direction"] == "auto" and job["ocr_done"] is True

    data = client.get(f"/v1/jobs/{job['id']}/result").json()
    assert data["translate_version"] == 1
    assert data["blocks"][1]["text"] == "[en2km] The weather is nice today."
    assert data["blocks"][1]["source_text"] == "The weather is nice today."
    assert data["blocks"][3]["source_rows"] == [["Name", "2024"], ["ឈ្មោះ", ""]]
    assert [j["id"] for j in client.get("/v1/jobs").json()["jobs"]] == [job["id"]]


def test_upload_is_removed_after_ocr(client, tmp_path):
    job = run(client)
    files = set(os.listdir(tmp_path / "jobs" / job["id"]))
    assert {"job.json", "source.json", "translation.json"} <= files
    assert "upload.bin" not in files


def test_direction_and_options_are_applied(make_client, sample_blocks):
    c, pipes = make_client()
    job = run(c, direction="km2en", layout="false")
    assert job["options"] == {"direction": "km2en", "layout": False}
    assert {d for _, d in pipes[False].translator.seen} == {"km2en"}


def test_wait_returns_result_for_single_image(client):
    r = upload(client, wait="true")
    assert r.status_code == 200
    assert r.json()["job"]["status"] == "done"
    assert r.json()["result"]["blocks"][0]["text"] == "[en2km] Annual Report"


def test_progress_reports_both_phases(client):
    job = run(client)
    assert job["progress"]["phase"] is None
    # translate phase: one step per text/table block (heading, 2 paragraphs, table)
    assert job["progress"]["done"] == job["progress"]["total"] == 4


def test_export_every_format(client):
    jid = run(client)["id"]
    for fmt in FORMATS:
        r = client.get(f"/v1/jobs/{jid}/export", params={"format": fmt})
        assert r.status_code == 200, fmt
        assert "scan_translated" in r.headers["content-disposition"]
    assert client.get(f"/v1/jobs/{jid}/export", params={"format": "docx"}).content[:2] == b"PK"
    txt = client.get(f"/v1/jobs/{jid}/export", params={"format": "txt", "bilingual": "true"}).text
    assert "The weather is nice today." in txt and "[en2km] The weather is nice today." in txt
    assert client.get(f"/v1/jobs/{jid}/export", params={"format": "pdf"}).status_code == 422


def test_retranslate_skips_ocr(make_client, sample_blocks):
    ocr = FakeOCR(sample_blocks)
    c, _ = make_client(ocr=ocr)
    jid = run(c)["id"]
    r = c.post(f"/v1/jobs/{jid}/translate", params={"direction": "km2en"})
    assert r.status_code == 202
    job = c.app.state.jobs.wait(jid, 10)
    assert job.status == "done" and job.direction == "km2en"
    assert len(ocr.calls) == 1
    blocks = c.get(f"/v1/jobs/{jid}/result").json()["blocks"]
    assert blocks[1]["text"] == "[km2en] The weather is nice today."
    assert c.post(f"/v1/jobs/{jid}/translate", params={"direction": "xx"}).status_code == 422


def test_failed_translation_can_be_retried(make_client, sample_blocks):
    c, pipes = make_client()
    pipes_seen = []

    class Flaky(FakeTranslator):
        def translate(self, text, direction="auto"):
            if not pipes_seen:
                pipes_seen.append(1)
                raise RuntimeError("model crashed")
            return super().translate(text, direction)

    c.app.state.worker._pipelines[False] = NetraTranslate(ocr=FakeOCR(sample_blocks), translator=Flaky())
    job = run(c)
    assert job["status"] == "error" and job["ocr_done"] is True
    assert "RuntimeError" in job["error"]
    assert c.get(f"/v1/jobs/{job['id']}/result").status_code == 409
    assert c.post(f"/v1/jobs/{job['id']}/translate", params={"direction": "auto"}).status_code == 202
    assert c.app.state.jobs.wait(job["id"], 10).status == "done"


def test_ocr_failure_is_reported(make_client):
    class Broken(FakeOCR):
        def process_document(self, source, **kw):
            raise ValueError("bad image")

    c, _ = make_client(ocr=Broken([]))
    job = run(c)
    assert job["status"] == "error" and job["ocr_done"] is False
    assert "bad image" in job["error"]
    assert c.post(f"/v1/jobs/{job['id']}/translate", params={"direction": "auto"}).status_code == 409


def test_unknown_job_is_404(client):
    missing = "0" * 32
    assert client.get(f"/v1/jobs/{missing}").status_code == 404
    assert client.get(f"/v1/jobs/{missing}/result").status_code == 404
    assert client.get(f"/v1/jobs/{missing}/export").status_code == 404
    assert client.get("/v1/jobs/../../etc/result").status_code == 404
    assert client.get("/v1/jobs/not-a-hex-id").status_code == 404


def test_delete(client, tmp_path):
    jid = run(client)["id"]
    assert client.delete(f"/v1/jobs/{jid}").status_code == 204
    assert client.get(f"/v1/jobs/{jid}").status_code == 404
    assert not (tmp_path / "jobs" / jid).exists()


def test_page_images_are_served_as_assets(make_client, sample_blocks):
    from netra_ocr.document import AssetStore, Document

    class OCRWithPage(FakeOCR):
        def process_document(self, source, **kw):
            assets = AssetStore()
            assets.put("page-0", Image.new("RGB", (300, 200), "white"))
            return Document(pages=[{"index": 0, "width": 300, "height": 200, "image": "page-0"}],
                            blocks=[dict(b) for b in self.blocks], assets=assets)

    c, _ = make_client(ocr=OCRWithPage(sample_blocks))
    jid = run(c)["id"]
    assert c.get(f"/v1/jobs/{jid}/result").json()["pages"][0]["image"] == "page-0"
    r = c.get(f"/v1/jobs/{jid}/assets/page-0")
    assert r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff"
    assert c.get(f"/v1/jobs/{jid}/assets/page-9").status_code == 404


# ── validation ─────────────────────────────────────────────────────────
def test_upload_validation(make_client):
    c, _ = make_client(max_upload_mb=1)
    r = c.post("/v1/translate", files={"file": ("a.png", b"", "image/png")})
    assert r.status_code == 422 and r.json()["detail"] == "The file is empty."
    assert upload(c, data=b"not an image at all").status_code == 415
    assert upload(c, data=b"\x89PNG" + b"0" * (1024 * 1024 + 10)).status_code == 413
    assert upload(c, direction="fr2en").status_code == 422


def test_layout_rejected_when_not_installed(client, monkeypatch):
    import netra_translate.server.app as app_module
    monkeypatch.setattr(app_module, "_layout_available", lambda: False)
    r = upload(client, layout="true")
    assert r.status_code == 422 and "layout" in r.json()["detail"].lower()


# ── demo + auth ────────────────────────────────────────────────────────
def test_demo_mode_never_lists_jobs(make_client):
    c, _ = make_client(demo=True)
    jid = run(c)["id"]
    assert c.get("/v1/jobs").json() == {"jobs": []}
    assert c.get(f"/v1/jobs/{jid}").status_code == 200


def test_api_key(make_client):
    c, _ = make_client(api_key="s3cret")
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200
    assert c.get("/v1/info").status_code == 401
    assert c.get("/v1/info", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/v1/info", headers={"X-API-Key": "s3cret"}).json()["auth"] is True
    assert c.get("/v1/info", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/v1/info", params={"key": "s3cret"}).status_code == 200


# ── persistence ────────────────────────────────────────────────────────
def test_jobs_survive_a_restart(make_client, tmp_path):
    c1, _ = make_client()
    jid = run(c1)["id"]
    c1.__exit__(None, None, None)

    c2, _ = make_client()
    assert c2.get(f"/v1/jobs/{jid}").json()["job"]["status"] == "done"
    assert c2.get(f"/v1/jobs/{jid}/result").json()["blocks"][0]["text"] == "[en2km] Annual Report"


def test_interrupted_job_is_marked_failed(make_client, tmp_path):
    c1, _ = make_client()
    jid = run(c1)["id"]
    c1.__exit__(None, None, None)
    d = tmp_path / "jobs" / jid
    meta = json.loads((d / "job.json").read_text(encoding="utf-8"))
    # Running, with no worker claim, and untouched for longer than ORPHAN_SECONDS.
    meta.update(status="running", phase="ocr", ocr_done=False, updated=time.time() - 60)
    (d / "job.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "translation.json").unlink()

    c2, _ = make_client()
    job = c2.get(f"/v1/jobs/{jid}").json()["job"]
    assert job["status"] == "error" and job["error"] == INTERRUPTED


def test_expired_jobs_are_cleaned_up(make_client):
    c, _ = make_client(job_ttl_hours=0)
    jid = run(c)["id"]
    c.app.state.jobs.cleanup()
    assert c.get(f"/v1/jobs/{jid}").status_code == 404


# ── deprecated preview API ─────────────────────────────────────────────
def test_deprecated_ocr_translate_endpoint(client):
    files = {"file": ("scan.png", png(), "image/png")}
    r = client.post("/v1/ocr-translate", params={"direction": "km2en"}, files=files)
    assert r.status_code == 200
    data = r.json()
    assert len(data["id"]) == 32 and data["blocks"][1]["text"] == "[km2en] The weather is nice today."
    r = client.post("/v1/ocr-translate", params={"format": "docx"}, files=files)
    assert r.status_code == 200 and r.content[:2] == b"PK"

"""Translation jobs: an on-disk store and queue, shared by the API and the workers.

The disk is the source of truth, so the API and any number of worker processes
(``netra-translate worker``) can share one data directory, and jobs survive
restarts::

    <data_dir>/<job_id>/
        job.json            status, progress, options, original filename
        upload.bin          the uploaded file (deleted once OCR is done)
        source.json         the OCR document, as produced
        translation.json    merged source + translated blocks for the current direction
        assets/             page renders + figure/table crops
    <data_dir>/_queue/<ns>-<job_id>.json            a step waiting for a worker
    <data_dir>/_claims/<worker_id>.<job_id>.json    the step a worker is running
    <data_dir>/_workers/<worker_id>.json            each worker's heartbeat

A worker takes a step by renaming its queue entry into ``_claims/``: the rename is
atomic, so exactly one worker wins. A claim whose worker stops sending heartbeats
is recovered: the job is marked as interrupted, the same as after a restart.
The models live in the workers (server/worker.py); nothing here loads them.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from netra_ocr.document import AssetStore, Document

from ..result import TranslationResult
from .settings import Settings

logger = logging.getLogger(__name__)

_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
INTERRUPTED = "Interrupted: the server restarted or a worker stopped. Please upload the file again."
INTERRUPTED_RETRY = "Translation was interrupted: the server restarted or a worker stopped. Try again."

HEARTBEAT_SECONDS = 5
# A worker that hasn't written a heartbeat for this long is gone.
STALE_SECONDS = 30
# A queued/running job with no queue entry or claim this long after its last
# change was cut off between steps.
ORPHAN_SECONDS = 10


@dataclass
class JobOptions:
    direction: str = "auto"
    layout: bool = False


@dataclass
class Job:
    id: str
    filename: str
    kind: str                       # "pdf" or an image kind
    options: JobOptions
    pages: int = 0
    status: str = "queued"          # queued | running | done | error
    phase: Optional[str] = None     # ocr | translate while running
    done: int = 0
    total: int = 0
    direction: Optional[str] = None  # direction of the stored translation
    ocr_done: bool = False           # source.json exists, so translation can be retried
    error: Optional[str] = None
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def public(self) -> dict:
        d = asdict(self)
        d["progress"] = {"phase": self.phase, "done": self.done, "total": self.total}
        for k in ("phase", "done", "total"):
            del d[k]
        return d


@dataclass
class Task:
    """A claimed step: ``ocr`` (OCR then translate) or ``translate`` (translate only)."""
    job_id: str
    step: str
    direction: Optional[str]
    worker_id: str
    path: str                       # the claim file


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir
        self.queue_dir = os.path.join(self.root, "_queue")
        self.claims_dir = os.path.join(self.root, "_claims")
        self.workers_dir = os.path.join(self.root, "_workers")
        for d in (self.root, self.queue_dir, self.claims_dir, self.workers_dir):
            os.makedirs(d, exist_ok=True)
        # Wakes workers in this process when a job is queued, and wait() when one
        # finishes; workers in other processes poll instead.
        self.queued = threading.Event()
        self._changed = threading.Condition()
        self._seq_lock = threading.Lock()
        self._seq = 0

    # ── persistence ────────────────────────────────────────────────────
    def dir(self, job_id: str) -> str:
        if not isinstance(job_id, str) or not _JOB_ID.match(job_id):
            raise KeyError(job_id)
        return os.path.join(self.root, job_id)

    def save(self, job: Job) -> None:
        job.updated = time.time()
        _write_json(os.path.join(self.dir(job.id), "job.json"), asdict(job))

    def _load(self, job_id: str) -> Optional[Job]:
        raw = _read_json(os.path.join(self.dir(job_id), "job.json"))
        if raw is None:
            return None
        raw["options"] = JobOptions(**raw.get("options", {}))
        return Job(**raw)

    def _enqueue(self, job_id: str, step: str, direction: Optional[str] = None) -> None:
        # Queue entries sort by name. The clock can tick as rarely as every 15 ms
        # (Windows), so steps queued by this process within one tick keep their order.
        with self._seq_lock:
            self._seq = max(time.time_ns(), self._seq + 1)
            name = f"{self._seq:020d}-{job_id}.json"
        _write_json(os.path.join(self.queue_dir, name), {"step": step, "direction": direction})
        self.queued.set()

    def notify(self) -> None:
        with self._changed:
            self._changed.notify_all()

    # ── public API ─────────────────────────────────────────────────────
    def create(self, data: bytes, filename: str, kind: str, pages: int, options: JobOptions) -> Job:
        job = Job(id=uuid.uuid4().hex, filename=filename, kind=kind, options=options,
                  pages=pages, total=pages)
        d = self.dir(job.id)
        os.makedirs(d)
        with open(os.path.join(d, "upload.bin"), "wb") as f:
            f.write(data)
        self.save(job)
        self._enqueue(job.id, "ocr")
        return job

    def retranslate(self, job_id: str, direction: str) -> Job:
        """Translate an OCR'd job again (another direction, or a retry after a
        failed translation). OCR is not repeated."""
        job = self.get(job_id)
        if job.status not in ("done", "error") or not job.ocr_done:
            raise LookupError(job.status)
        job.status, job.phase, job.done, job.total, job.error = "queued", "translate", 0, 0, None
        job.options.direction = direction
        self.save(job)
        self._enqueue(job_id, "translate", direction)
        return job

    def get(self, job_id: str) -> Job:
        job = self._load(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list(self, limit: int = 50) -> list[Job]:
        jobs = []
        for name in os.listdir(self.root):
            if not _JOB_ID.match(name):
                continue
            try:
                job = self._load(name)
            except Exception:
                logger.warning("Skipping unreadable job directory %s", name)
                continue
            if job is not None:
                jobs.append(job)
        jobs.sort(key=lambda j: j.created, reverse=True)
        return jobs[:limit]

    def delete(self, job_id: str) -> None:
        d = self.dir(job_id)
        if not os.path.exists(os.path.join(d, "job.json")):
            raise KeyError(job_id)
        for name in _listdir(self.queue_dir):
            if name.endswith(f"-{job_id}.json"):
                _remove(os.path.join(self.queue_dir, name))
        # A worker running this job notices that its directory is gone and stops.
        shutil.rmtree(d, ignore_errors=True)
        self.notify()

    def wait(self, job_id: str, timeout: float) -> Optional[Job]:
        deadline = time.time() + timeout
        while True:
            try:
                job = self.get(job_id)
            except KeyError:
                return None
            remaining = deadline - time.time()
            if job.status in ("done", "error") or remaining <= 0:
                return job
            with self._changed:
                self._changed.wait(min(0.25, remaining))

    def result(self, job_id: str) -> TranslationResult:
        """The stored translation. Raises KeyError (no job) or LookupError (not ready)."""
        job = self.get(job_id)
        d = self.dir(job_id)
        raw = _read_json(os.path.join(d, "translation.json"))
        if raw is None:
            raise LookupError(job.status)
        # Translated blocks carry extra fields (source_text, direction, source_rows)
        # that Document.from_dict would strip, so the documents are rebuilt directly.
        assets = AssetStore(os.path.join(d, "assets"))
        return TranslationResult(
            source=Document(pages=raw["source"]["pages"], blocks=raw["source"]["blocks"], assets=assets),
            translated=Document(pages=raw["translated"]["pages"], blocks=raw["translated"]["blocks"],
                                assets=assets),
            direction=raw.get("direction", "auto"))

    def asset_path(self, job_id: str, asset_id: str) -> Optional[str]:
        self.get(job_id)
        return AssetStore(os.path.join(self.dir(job_id), "assets")).path(asset_id)

    # ── the queue, as seen by workers ──────────────────────────────────
    def claim(self, worker_id: str) -> Optional[Task]:
        """Take the oldest queued step, or None. Safe across processes."""
        for name in sorted(_listdir(self.queue_dir)):
            if not name.endswith(".json") or "-" not in name:
                continue
            job_id = name[:-5].split("-", 1)[1]
            if not _JOB_ID.match(job_id):
                continue
            path = os.path.join(self.claims_dir, f"{worker_id}.{job_id}.json")
            try:
                os.rename(os.path.join(self.queue_dir, name), path)
            except (FileNotFoundError, FileExistsError, PermissionError):
                continue                    # another worker took it
            raw = _read_json(path) or {}
            return Task(job_id, raw.get("step", "ocr"), raw.get("direction"), worker_id, path)
        return None

    def owns(self, task: Task) -> bool:
        """False once the job was deleted or the claim recovered from this worker."""
        return os.path.exists(task.path) and os.path.isdir(os.path.join(self.root, task.job_id))

    def release(self, task: Task) -> None:
        _remove(task.path)
        self.notify()

    # ── workers ────────────────────────────────────────────────────────
    def beat(self, worker_id: str, info: dict) -> None:
        _write_json(os.path.join(self.workers_dir, f"{worker_id}.json"),
                    {**info, "id": worker_id, "beat": time.time()})

    def retire(self, worker_id: str) -> None:
        _remove(os.path.join(self.workers_dir, f"{worker_id}.json"))

    def workers(self) -> list[dict]:
        """Live workers (a recent heartbeat), oldest first."""
        now, out = time.time(), []
        for name in _listdir(self.workers_dir):
            if not name.endswith(".json"):
                continue
            beat = _read_json(os.path.join(self.workers_dir, name))
            if beat and now - beat.get("beat", 0) < STALE_SECONDS:
                out.append(beat)
        out.sort(key=lambda b: b.get("started", 0))
        return out

    def models_ready(self) -> bool:
        return any(w.get("models_ready") for w in self.workers())

    # ── recovery and retention ─────────────────────────────────────────
    def recover(self) -> None:
        """Fail the jobs whose worker died (claims without a live heartbeat), and
        jobs left queued or running with nothing to run them."""
        live = {w["id"] for w in self.workers()}
        for name in _listdir(self.claims_dir):
            parts = name.split(".")
            if len(parts) != 3 or parts[0] in live:
                continue
            try:
                os.remove(os.path.join(self.claims_dir, name))
            except OSError:
                continue                    # released or recovered meanwhile
            self._interrupt(parts[1])
        now = time.time()
        for job in self.list(limit=1_000_000):
            if (job.status in ("queued", "running") and now - job.updated > ORPHAN_SECONDS
                    and not self._pending(job.id)):
                self._interrupt(job.id)

    def _pending(self, job_id: str) -> bool:
        # The queue is read before the claims: a rename between the two reads is
        # then seen in one of them.
        if any(n.endswith(f"-{job_id}.json") for n in _listdir(self.queue_dir)):
            return True
        return any(n.endswith(f".{job_id}.json") for n in _listdir(self.claims_dir))

    def _interrupt(self, job_id: str) -> None:
        try:
            job = self.get(job_id)
        except KeyError:
            return
        if job.status not in ("queued", "running"):
            return
        d = self.dir(job_id)
        if os.path.exists(os.path.join(d, "translation.json")):
            # A re-translation was cut short; the previous one is still there.
            job.status, job.phase, job.error = "done", None, None
            job.options.direction = job.direction or job.options.direction
        elif job.ocr_done:
            job.status, job.phase, job.error = "error", None, INTERRUPTED_RETRY
        else:
            job.status, job.phase, job.error = "error", None, INTERRUPTED
            _remove(os.path.join(d, "upload.bin"))
        logger.warning("Job %s was interrupted (%s)", job_id, job.status)
        self.save(job)
        self.notify()

    def cleanup(self) -> None:
        cutoff = time.time() - self.settings.job_ttl_hours * 3600
        for job in self.list(limit=1_000_000):
            if job.status in ("done", "error") and job.updated < cutoff:
                try:
                    self.delete(job.id)
                except KeyError:
                    pass
        # Queue entries whose job is gone, and long-dead workers' heartbeats.
        for name in _listdir(self.queue_dir):
            job_id = name[:-5].split("-", 1)[-1]
            if not os.path.isdir(os.path.join(self.root, job_id)):
                _remove(os.path.join(self.queue_dir, name))
        for name in _listdir(self.workers_dir):
            path = os.path.join(self.workers_dir, name)
            beat = _read_json(path) or {}
            if time.time() - beat.get("beat", 0) > 86400:
                _remove(path)


# The name used before the API and the workers were split.
JobManager = JobStore


def describe_device() -> str:
    try:
        from netra_ocr.recognition.config import describe_device as _describe
        return _describe()
    except Exception:
        return "CPU"


def _listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _retry(fn, *args):
    # On Windows a file can't be replaced (or briefly opened) while another
    # process has it open; that lasts milliseconds, so try again.
    for attempt in range(20):
        try:
            return fn(*args)
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01 * (attempt + 1))


def _write_json(path: str, data: dict) -> None:
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    _retry(os.replace, tmp, path)


def _read_json(path: str) -> Optional[dict]:
    def read():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        return _retry(read)
    except FileNotFoundError:
        return None

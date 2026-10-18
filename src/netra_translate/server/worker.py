"""Inference workers: each owns a set of models and runs queued steps from the job store.

A worker runs one step at a time, so its CPU threads (or GPU) serve one job and
torch models are never shared across threads. ``netra-translate serve`` runs one
worker in a thread next to the API. ``netra-translate worker`` runs one in its own
process; any number of those can share a data directory with an API started
with ``--no-worker``::

    netra-translate serve --no-worker &
    netra-translate worker &
    netra-translate worker &
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from typing import Callable, Optional

from netra_ocr.document import Document

from ..pipeline import NetraTranslate
from .jobs import HEARTBEAT_SECONDS, Job, JobStore, Task, _write_json, describe_device
from .settings import Settings

logger = logging.getLogger(__name__)

# How often a worker in another process looks for queued steps.
POLL_SECONDS = 0.5


class _Abandoned(Exception):
    """The job was deleted, or its claim recovered, while this worker ran it."""


class Worker:
    def __init__(self, settings: Settings, store: JobStore,
                 pipeline_factory: Optional[Callable[[bool], NetraTranslate]] = None):
        self.settings = settings
        self.store = store
        self.id = uuid.uuid4().hex[:12]
        self.started = time.time()
        self._factory = pipeline_factory or self._default_factory
        self._pipelines: dict[bool, NetraTranslate] = {}
        self._translator = None
        self.models_ready = threading.Event()
        self._stop = threading.Event()
        self._beats_stop = threading.Event()
        self._busy: Optional[str] = None
        self._device: Optional[tuple[str, str]] = None
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ──────────────────────────────────────────────────────
    def start(self) -> None:
        """Run in a background thread (the worker inside ``netra-translate serve``)."""
        # Announce the worker before returning, so /ready and /v1/info see it at once.
        if not self.settings.warmup:
            self.models_ready.set()
        self._beat()
        self._thread = threading.Thread(target=self.run, name=f"netra-translate-worker-{self.id}",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: Optional[float] = None) -> None:
        """Finish the current step, then exit."""
        self._stop.set()
        self.store.queued.set()
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run(self) -> None:
        if self.settings.threads:
            import torch
            torch.set_num_threads(self.settings.threads)
        self._beat()
        beats = threading.Thread(target=self._beat_loop, name=f"netra-translate-heartbeat-{self.id}",
                                 daemon=True)
        beats.start()
        try:
            if self.settings.warmup:
                self._warmup()
            else:
                self.models_ready.set()     # models load on the first job
            self._beat()
            while not self._stop.is_set():
                if self.run_once():
                    continue
                self.store.queued.wait(POLL_SECONDS)
                self.store.queued.clear()
        finally:
            self._beats_stop.set()
            beats.join(HEARTBEAT_SECONDS + 1)
            self.store.retire(self.id)

    def run_once(self) -> bool:
        """Run the oldest queued step, if there is one. Returns whether there was."""
        task = self.store.claim(self.id)
        if task is None:
            return False
        self._busy = task.job_id
        self._beat()
        try:
            if task.step == "ocr":
                self._process(task)
            else:
                self._retranslate(task)
        except _Abandoned:
            logger.warning("Job %s was deleted or reassigned; stopped working on it", task.job_id)
        except Exception:
            logger.exception("Job %s crashed", task.job_id)
        finally:
            self._busy = None
            self.store.release(task)
            self._beat()
        return True

    # ── heartbeat ──────────────────────────────────────────────────────
    def _beat(self) -> None:
        if self._device is None:
            self._device = (_device(self.settings), describe_device())
        try:
            self.store.beat(self.id, {
                "pid": os.getpid(), "host": socket.gethostname(), "started": self.started,
                "device": self._device[0], "device_name": self._device[1],
                "models_ready": self.models_ready.is_set(), "job": self._busy})
        except OSError:
            logger.exception("Could not write the worker heartbeat")

    def _beat_loop(self) -> None:
        while not self._beats_stop.wait(HEARTBEAT_SECONDS):
            self._beat()

    # ── models ─────────────────────────────────────────────────────────
    def _default_factory(self, layout: bool) -> NetraTranslate:
        from ..translator import Translator
        if self._translator is None:
            self._translator = Translator(device=self.settings.device)
        return NetraTranslate(detector=self.settings.detector, layout=layout,
                              translator=self._translator)

    def _pipeline(self, layout: bool) -> NetraTranslate:
        if layout not in self._pipelines:
            self._pipelines[layout] = self._factory(layout)
        return self._pipelines[layout]

    def _warmup(self) -> None:
        """Load the default models before taking any job."""
        try:
            pipe = self._pipeline(self.settings.layout)
            pipe.ocr  # detector (+ layout model)
            try:
                from netra_ocr.recognition.recognize_text import _get_predictor
                _get_predictor(decoder="ar")
            except ImportError:
                pass
            pipe.translator.model
            logger.info("Worker %s: models loaded on %s", self.id, describe_device())
        except Exception:
            logger.exception("Model warmup failed; models will load on the first job")
        finally:
            self.models_ready.set()

    # ── steps ──────────────────────────────────────────────────────────
    def _save(self, task: Task, job: Job) -> None:
        if not self.store.owns(task):
            raise _Abandoned(task.job_id)
        self.store.save(job)

    def _start(self, task: Task, phase: str) -> Optional[Job]:
        try:
            job = self.store.get(task.job_id)
        except KeyError:
            return None
        job.status, job.phase, job.error = "running", phase, None
        self._save(task, job)
        return job

    def _progress(self, task: Task, job: Job, phase: str):
        def progress(done: int, total: int) -> None:
            job.phase, job.done, job.total = phase, done, total
            self._save(task, job)
        return progress

    def _finish(self, task: Task, job: Job, error: Optional[str]) -> None:
        job.status = "error" if error else "done"
        job.phase, job.error = None, error
        self._save(task, job)

    def _process(self, task: Task) -> None:
        job = self._start(task, "ocr")
        if job is None:
            return
        d = self.store.dir(job.id)
        upload = os.path.join(d, "upload.bin")
        error = None
        try:
            pipe = self._pipeline(job.options.layout)
            doc = pipe.ocr.process_document(upload, beam_width=pipe.ocr_beam,
                                            max_pages=self.settings.max_pages,
                                            progress=self._progress(task, job, "ocr"))
            if not self.store.owns(task):
                raise _Abandoned(job.id)
            doc.save(d, "source.json")
            job.ocr_done = True
            self._translate(task, job, pipe, doc, job.options.direction)
        except _Abandoned:
            raise
        except Exception as e:
            logger.exception("Job %s failed", job.id)
            error = _friendly(e)
        finally:
            try:
                os.remove(upload)
            except OSError:
                pass
        self._finish(task, job, error)

    def _retranslate(self, task: Task) -> None:
        job = self._start(task, "translate")
        if job is None:
            return
        error = None
        try:
            doc = Document.load(self.store.dir(job.id), "source.json")
            direction = task.direction or job.options.direction
            self._translate(task, job, self._pipeline(job.options.layout), doc, direction)
        except _Abandoned:
            raise
        except Exception as e:
            logger.exception("Re-translation of job %s failed", job.id)
            error = _friendly(e)
        self._finish(task, job, error)

    def _translate(self, task: Task, job: Job, pipe: NetraTranslate, doc: Document,
                   direction: str) -> None:
        job.phase, job.done, job.total = "translate", 0, 0
        self._save(task, job)
        result = pipe.translate_document(doc, direction=direction,
                                         progress=self._progress(task, job, "translate"))
        if not self.store.owns(task):
            raise _Abandoned(job.id)
        _write_json(os.path.join(self.store.dir(job.id), "translation.json"), {
            "direction": direction,
            "source": {"pages": result.source.pages, "blocks": result.source.blocks},
            "translated": {"pages": result.translated.pages, "blocks": result.translated.blocks},
        })
        job.direction = direction


def _device(settings: Settings) -> str:
    if settings.device:
        return settings.device
    try:
        from netra_ocr.recognition.config import _default_device
        return _default_device()
    except Exception:
        return "cpu"


def _friendly(e: Exception) -> str:
    """A message for the person who uploaded the file (details go to the log)."""
    if isinstance(e, MemoryError):
        return "The server ran out of memory. Try a smaller file or fewer pages."
    if isinstance(e, (ValueError, OSError)) and str(e):
        return f"The file could not be processed: {e}"
    return f"Something went wrong while processing the file ({type(e).__name__}). Please try again."


def main(settings: Optional[Settings] = None) -> int:
    """Run one worker in this process until SIGTERM/SIGINT (``netra-translate worker``)."""
    import signal

    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = JobStore(settings)
    store.recover()
    worker = Worker(settings, store)

    def on_signal(signum, frame):
        if worker.stopping:
            raise KeyboardInterrupt     # a second signal: stop now
        logger.info("Worker %s: finishing the current job, then exiting", worker.id)
        worker.stop()

    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_signal)
    logger.info("Worker %s: jobs from %s", worker.id, settings.data_dir)
    try:
        worker.run()
    except KeyboardInterrupt:
        return 130
    return 0

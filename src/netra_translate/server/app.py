"""Netra Translate web app and REST API.

Run with ``netra-translate serve`` (or ``uvicorn netra_translate.server.app:app``),
then open http://localhost:8000 for the app or http://localhost:8000/docs for the
interactive API reference.
"""
from __future__ import annotations

import hmac
import importlib.util
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Callable, Literal, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from netra_ocr.io import count_pages, sniff_kind
from starlette.concurrency import run_in_threadpool

from .. import __version__
from ..pipeline import DIRECTIONS, NetraTranslate
from ..result import FORMATS
from .jobs import JobOptions, JobStore, describe_device
from .settings import Settings
from .worker import Worker

logger = logging.getLogger(__name__)

PRODUCT = "Netra Translate"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
Direction = Literal["auto", "km2en", "en2km"]
Format = Literal["docx", "html", "md", "txt", "json"]
RECOVER_SECONDS = 15
CLEANUP_SECONDS = 600


def _safe_basename(filename: Optional[str]) -> str:
    stem = os.path.splitext(os.path.basename(filename or "document"))[0]
    stem = re.sub(r"[^\w\-. ]+", "_", stem, flags=re.UNICODE).strip(" ._") or "document"
    return stem[:80]


def _layout_available() -> bool:
    return importlib.util.find_spec("doclayout_yolo") is not None


def _device() -> str:
    try:
        from netra_ocr.recognition.config import _default_device
        return _default_device()
    except Exception:
        return os.environ.get("NETRA_DEVICE") or "cpu"


def _attachment(data: bytes, filename: str, mime: str) -> Response:
    ext = os.path.splitext(filename)[1]
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename=\"translation{ext}\"; "
                               f"filename*=UTF-8''{quote(filename)}"})


def _janitor(store: JobStore, stop: threading.Event) -> None:
    """Recover jobs whose worker died, and delete expired jobs."""
    last_cleanup = 0.0
    while not stop.wait(RECOVER_SECONDS):
        try:
            store.recover()
            if time.time() - last_cleanup > CLEANUP_SECONDS:
                store.cleanup()
                last_cleanup = time.time()
        except Exception:
            logger.exception("Job maintenance failed")


def create_app(settings: Optional[Settings] = None,
               pipeline_factory: Optional[Callable[[bool], NetraTranslate]] = None) -> FastAPI:
    """Build the app. ``pipeline_factory(layout)`` replaces the real models (tests).

    With ``settings.embedded_worker`` (the default) a worker thread runs the jobs
    in this process; otherwise ``netra-translate worker`` processes sharing
    ``settings.data_dir`` do.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = JobStore(settings)
        store.recover()
        stop = threading.Event()
        janitor = threading.Thread(target=_janitor, args=(store, stop), name="netra-translate-janitor",
                                   daemon=True)
        janitor.start()
        app.state.jobs = store
        app.state.worker = None
        if settings.embedded_worker:
            app.state.worker = Worker(settings, store, pipeline_factory)
            app.state.worker.start()
        try:
            yield
        finally:
            stop.set()
            if app.state.worker is not None:
                app.state.worker.stop(timeout=5)

    app = FastAPI(
        title=PRODUCT,
        version=__version__,
        description="Khmer <-> English document translation: OCR an image or PDF with Netra OCR, "
                    "translate it with Netra MT, and export DOCX, HTML, Markdown, JSON or text.",
        lifespan=lifespan,
    )

    def jobs() -> JobStore:
        return app.state.jobs

    # ── auth (only when NETRA_API_KEY is set) ──────────────────────────
    @app.middleware("http")
    async def require_key(request: Request, call_next):
        if settings.api_key and request.url.path.startswith("/v1/"):
            supplied = request.headers.get("x-api-key") or ""
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                supplied = auth[7:]
            if not supplied and request.method == "GET":
                # <img src> and download links can't send headers.
                supplied = request.query_params.get("key", "")
            if not hmac.compare_digest(supplied.encode(), settings.api_key.encode()):
                return JSONResponse({"detail": "Missing or invalid API key."}, status_code=401)
        return await call_next(request)

    def job_or_404(job_id: str):
        try:
            return jobs().get(job_id)
        except KeyError:
            raise HTTPException(404, "Document not found. It may have expired; upload it again.")

    def result_or_error(job_id: str):
        job_or_404(job_id)
        try:
            return jobs().result(job_id)
        except LookupError as e:
            raise HTTPException(409, f"The translation is not ready yet (job is {e}).")

    async def read_upload(file: UploadFile) -> tuple[bytes, str, int]:
        data = await file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, f"File too large. The limit is {settings.max_upload_mb} MB.")
        if not data:
            raise HTTPException(422, "The file is empty.")
        kind = sniff_kind(data[:16])
        if kind is None:
            raise HTTPException(415, "Unsupported file. Upload a PDF, JPG, PNG, TIFF, BMP or WebP.")
        try:
            pages = count_pages(data)
        except Exception:
            raise HTTPException(422, "The file could not be read. It may be damaged or password-protected.")
        if pages < 1:
            raise HTTPException(422, "The document has no pages.")
        if pages > settings.max_pages:
            raise HTTPException(413, f"The document has {pages} pages; the limit is {settings.max_pages}.")
        return data, kind, pages

    def check_layout(layout: bool) -> None:
        if layout and not _layout_available():
            raise HTTPException(422, "Layout analysis isn't installed on this server "
                                     "(pip install \"netra-translate[layout]\").")

    def payload(job) -> dict:
        return {"job": job.public(), "result": jobs().result(job.id).to_dict()}

    # ── meta ───────────────────────────────────────────────────────────
    @app.get("/health", summary="Liveness: the API is up")
    @app.get("/healthz", include_in_schema=False)
    def health():
        return {"ok": True, "models_ready": jobs().models_ready()}

    @app.get("/ready", summary="Readiness: a worker has its models loaded",
             responses={503: {"description": "No worker is ready yet"}})
    def ready():
        workers = [w for w in jobs().workers() if w.get("models_ready")]
        return JSONResponse({"ready": bool(workers), "workers": len(workers)},
                            status_code=200 if workers else 503)

    @app.get("/v1/info", summary="Server, model and limit information")
    def info():
        workers = jobs().workers()
        first = workers[0] if workers else {}
        return {
            "name": PRODUCT,
            "version": __version__,
            "device": first.get("device") or _device(),
            "device_name": first.get("device_name") or describe_device(),
            "models_ready": any(w.get("models_ready") for w in workers),
            "workers": [{"device": w.get("device"), "device_name": w.get("device_name"),
                         "models_ready": bool(w.get("models_ready")), "busy": bool(w.get("job"))}
                        for w in workers],
            "directions": list(DIRECTIONS),
            "formats": list(FORMATS),
            "layout_available": _layout_available(),
            "defaults": {"direction": "auto", "layout": settings.layout},
            "limits": {"max_upload_mb": settings.max_upload_mb, "max_pages": settings.max_pages,
                       "job_ttl_hours": settings.job_ttl_hours},
            "auth": bool(settings.api_key),
            "demo": settings.demo,
        }

    # ── translate ──────────────────────────────────────────────────────
    @app.post("/v1/translate", summary="Upload an image or PDF to translate",
              responses={200: {"description": "Finished (single image with wait=true)"},
                         202: {"description": "Accepted; poll GET /v1/jobs/{id}"}})
    async def translate(
        file: UploadFile = File(..., description="PDF, JPG, PNG, TIFF, BMP or WebP"),
        direction: Direction = Form("auto", description="auto detects Khmer vs English per block"),
        layout: Optional[bool] = Form(None, description="Layout analysis (headings, paragraphs, tables)"),
        wait: bool = Form(False, description="For a single image, wait for the result instead of returning 202"),
    ):
        layout = settings.layout if layout is None else layout
        check_layout(layout)
        data, kind, pages = await read_upload(file)
        job = jobs().create(data, _safe_basename(file.filename), kind, pages,
                            JobOptions(direction=direction, layout=layout))
        if wait and pages == 1:
            job = await run_in_threadpool(jobs().wait, job.id, settings.sync_timeout)
            if job is None:
                raise HTTPException(404, "The document was deleted while it was being translated.")
            if job.status == "done":
                return payload(job)
            if job.status == "error":
                return JSONResponse({"job": job.public()}, status_code=500)
        return JSONResponse({"job": job.public()}, status_code=202)

    @app.get("/v1/jobs", summary="Recent jobs, newest first",
             description="Always empty on a shared demo server (NETRA_DEMO=1).")
    def list_jobs(limit: int = Query(50, ge=1, le=500)):
        if settings.demo:
            return {"jobs": []}
        return {"jobs": [j.public() for j in jobs().list(limit)]}

    @app.get("/v1/jobs/{job_id}", summary="Job status and progress")
    def get_job(job_id: str):
        return {"job": job_or_404(job_id).public()}

    @app.delete("/v1/jobs/{job_id}", status_code=204, summary="Delete a job and all its files")
    def delete_job(job_id: str):
        job_or_404(job_id)
        jobs().delete(job_id)
        return Response(status_code=204)

    @app.get("/v1/jobs/{job_id}/result", summary="The translated document",
             description="Netra OCR's document schema. Translated text blocks add `source_text` "
                         "and `direction`; tables add `source_rows`.")
    def get_result(job_id: str):
        return result_or_error(job_id).to_dict()

    @app.post("/v1/jobs/{job_id}/translate", status_code=202,
              summary="Translate again in another direction (OCR is not repeated)")
    def retranslate(job_id: str, direction: Direction = Query(...)):
        job_or_404(job_id)
        try:
            job = jobs().retranslate(job_id, direction)
        except LookupError as e:
            raise HTTPException(409, f"The document is busy or failed (job is {e}).")
        return {"job": job.public()}

    @app.get("/v1/jobs/{job_id}/export", summary="Download the translation",
             description="`md` becomes a .zip when the document has figures. "
                         "`bilingual` puts each source block next to its translation.")
    def export_result(job_id: str, format: Format = "docx", bilingual: bool = False):
        result = result_or_error(job_id)
        job = jobs().get(job_id)
        return _attachment(*result.export(format, bilingual=bilingual,
                                          basename=f"{job.filename}_translated"))

    @app.get("/v1/jobs/{job_id}/assets/{asset_id}", summary="A page render or figure/table crop")
    def get_asset(job_id: str, asset_id: str):
        job_or_404(job_id)
        path = jobs().asset_path(job_id, asset_id)
        if path is None:
            raise HTTPException(404, "Image not found.")
        return FileResponse(path, headers={"Cache-Control": "private, max-age=86400, immutable"})

    # ── deprecated: the netra-ocr-mt preview API ───────────────────────
    @app.post("/v1/ocr-translate", deprecated=True,
              summary="Deprecated: use POST /v1/translate and GET /v1/jobs/{id}/export")
    async def ocr_translate(
        file: UploadFile = File(...),
        direction: Direction = Query("auto"),
        format: Format = Query("json"),
        bilingual: bool = Query(False),
    ):
        check_layout(settings.layout)
        data, kind, pages = await read_upload(file)
        job = jobs().create(data, _safe_basename(file.filename), kind, pages,
                            JobOptions(direction=direction, layout=settings.layout))
        job = await run_in_threadpool(jobs().wait, job.id, max(settings.sync_timeout, 3600))
        if job is None:
            raise HTTPException(404, "The document was deleted while it was being translated.")
        if job.status != "done":
            raise HTTPException(500 if job.status == "error" else 504,
                                job.error or "Timed out; poll GET /v1/jobs/{id}.")
        result = jobs().result(job.id)
        if format == "json":
            return {"id": job.id, **result.to_dict()}
        return _attachment(*result.export(format, bilingual=bilingual,
                                          basename=f"{job.filename}_translated"))

    # ── web app ────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"),
                            headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()

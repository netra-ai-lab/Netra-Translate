"""Python client for a Netra Translate server (``netra-translate serve``).

    >>> from netra_translate import Client
    >>> client = Client("http://localhost:8000")
    >>> out = client.translate("letter.pdf", direction="km2en")      # waits for the result
    >>> open("letter.docx", "wb").write(client.export(out["job"]["id"], "docx"))

Needs the ``client`` extra: ``pip install "netra-translate[client]"``.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional, Union

try:
    import httpx
except ImportError as e:  # pragma: no cover
    raise ImportError('The client needs httpx: pip install "netra-translate[client]"') from e

FileLike = Union[str, "os.PathLike[str]", bytes]


class NetraAPIError(Exception):
    """The server answered with an error (``status`` is the HTTP status code)."""

    def __init__(self, status: int, detail: str, job: Optional[dict] = None):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail
        self.job = job


class Client:
    """Talks to the REST API documented at ``/docs`` on the server.

    ``api_key`` is needed when the server sets ``NETRA_API_KEY``. Pass ``http``
    to reuse an ``httpx.Client`` (or FastAPI's ``TestClient``); ``base_url`` is
    then taken from it.
    """

    def __init__(self, base_url: Optional[str] = "http://localhost:8000", api_key: Optional[str] = None,
                 timeout: float = 120.0, http: Optional[httpx.Client] = None):
        self._own = http is None
        self.http = http if http is not None else httpx.Client(base_url=base_url or "", timeout=timeout)
        self.headers = {"X-API-Key": api_key} if api_key else {}

    # ── plumbing ───────────────────────────────────────────────────────
    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self.http.request(method, path, headers=self.headers, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if "job" in body:
                job = body["job"]
                raise NetraAPIError(response.status_code, job.get("error") or "The job failed.", job)
            raise NetraAPIError(response.status_code, body.get("detail") or response.text or response.reason_phrase)
        return response

    def close(self) -> None:
        if self._own:
            self.http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── API ────────────────────────────────────────────────────────────
    def info(self) -> dict:
        """Server version, device, workers, limits (``GET /v1/info``)."""
        return self._request("GET", "/v1/info").json()

    def ready(self) -> bool:
        """Whether a worker has its models loaded (``GET /ready``)."""
        return self.http.get("/ready").status_code == 200

    def submit(self, file: FileLike, direction: str = "auto", layout: Optional[bool] = None,
               filename: Optional[str] = None) -> dict:
        """Upload a file; returns the queued job (``POST /v1/translate``)."""
        if isinstance(file, (bytes, bytearray)):
            data, name = bytes(file), filename or "upload"
        else:
            path = os.fspath(file)
            with open(path, "rb") as f:
                data = f.read()
            name = filename or os.path.basename(path)
        form = {"direction": direction}
        if layout is not None:
            form["layout"] = "true" if layout else "false"
        return self._request("POST", "/v1/translate", files={"file": (name, data)}, data=form).json()["job"]

    def translate(self, file: FileLike, direction: str = "auto", layout: Optional[bool] = None,
                  wait: bool = True, timeout: Optional[float] = None, filename: Optional[str] = None) -> dict:
        """Upload a file and, with ``wait`` (default), wait for the translation.

        Returns ``{"job": ..., "result": ...}`` (``result`` is the translated
        document, as ``GET /v1/jobs/{id}/result``), or ``{"job": ...}`` with
        ``wait=False``. Raises :class:`NetraAPIError` if the job fails.
        """
        job = self.submit(file, direction=direction, layout=layout, filename=filename)
        if not wait:
            return {"job": job}
        job = self.wait(job["id"], timeout=timeout)
        return {"job": job, "result": self.result(job["id"])}

    def job(self, job_id: str) -> dict:
        """Status and progress (``GET /v1/jobs/{id}``)."""
        return self._request("GET", f"/v1/jobs/{job_id}").json()["job"]

    def jobs(self, limit: int = 50) -> list[dict]:
        """Recent jobs, newest first."""
        return self._request("GET", "/v1/jobs", params={"limit": limit}).json()["jobs"]

    def wait(self, job_id: str, timeout: Optional[float] = None, poll: float = 1.0) -> dict:
        """Poll until the job is done; raises :class:`NetraAPIError` if it fails,
        ``TimeoutError`` after ``timeout`` seconds."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            job = self.job(job_id)
            if job["status"] == "done":
                return job
            if job["status"] == "error":
                raise NetraAPIError(500, job.get("error") or "The job failed.", job)
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Job {job_id} is still {job['status']} after {timeout} s")
            time.sleep(poll)

    def result(self, job_id: str) -> dict:
        """The translated document (``GET /v1/jobs/{id}/result``)."""
        return self._request("GET", f"/v1/jobs/{job_id}/result").json()

    def export(self, job_id: str, format: str = "docx", bilingual: bool = False) -> bytes:
        """The translation as a file: docx, html, md (a .zip with figures), txt or json."""
        params: dict[str, Any] = {"format": format, "bilingual": "true" if bilingual else "false"}
        return self._request("GET", f"/v1/jobs/{job_id}/export", params=params).content

    def retranslate(self, job_id: str, direction: str, wait: bool = True,
                    timeout: Optional[float] = None) -> dict:
        """Translate again in another direction, reusing the OCR."""
        job = self._request("POST", f"/v1/jobs/{job_id}/translate", params={"direction": direction}).json()["job"]
        return self.wait(job_id, timeout=timeout) if wait else job

    def delete(self, job_id: str) -> None:
        """Delete a job and its files."""
        self._request("DELETE", f"/v1/jobs/{job_id}")

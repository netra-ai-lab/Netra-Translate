"""Server configuration, read from NETRA_* environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Optional


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Where jobs (uploads, page renders, documents) live.
    data_dir: str = field(default_factory=lambda: os.environ.get(
        "NETRA_DATA_DIR", os.path.join(os.path.expanduser("~"), ".cache", "netra-translate", "jobs")))
    max_upload_mb: int = field(default_factory=lambda: _env_int("NETRA_MAX_UPLOAD_MB", 50))
    max_pages: int = field(default_factory=lambda: _env_int("NETRA_MAX_PAGES", 100))
    # Jobs are deleted this long after their last change.
    job_ttl_hours: int = field(default_factory=lambda: _env_int("NETRA_JOB_TTL_HOURS", 24))
    # Optional. Unset (the default) means no key: anyone who can reach the
    # port can use it. Set it before exposing an instance beyond your machine.
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get("NETRA_API_KEY") or None)
    detector: str = field(default_factory=lambda: os.environ.get("NETRA_DETECTOR", "yolo"))
    # Default for the "Layout analysis" option when a request doesn't say.
    layout: bool = field(default_factory=lambda: _env_bool("NETRA_LAYOUT", False))
    device: Optional[str] = field(default_factory=lambda: os.environ.get("NETRA_DEVICE") or None)
    # Load models at startup so the first request isn't slow.
    warmup: bool = field(default_factory=lambda: _env_bool("NETRA_WARMUP", True))
    # Seconds POST /v1/translate?wait=true waits for a single image before answering 202.
    sync_timeout: int = field(default_factory=lambda: _env_int("NETRA_SYNC_TIMEOUT", 120))
    # Shared public server (the Hugging Face Space): jobs are never listed, so
    # visitors only see the ones their own browser created.
    demo: bool = field(default_factory=lambda: _env_bool("NETRA_DEMO", False))
    # Run a worker inside `netra-translate serve`. Turn off when separate
    # `netra-translate worker` processes share the data directory.
    embedded_worker: bool = field(default_factory=lambda: _env_bool("NETRA_EMBEDDED_WORKER", True))
    # torch CPU threads per worker (0 = torch's default, all cores). Set it when
    # several workers share a machine, so they don't fight over the cores.
    threads: int = field(default_factory=lambda: _env_int("NETRA_THREADS", 0))

    @classmethod
    def from_config(cls, path: str, **overrides) -> "Settings":
        """Settings from a YAML/JSON file (its ``server:`` options); the
        environment fills in whatever the file doesn't set."""
        from ..config import load_config
        names = [f.name for f in fields(cls)]
        return cls(**{**load_config(path, "server", names), **overrides})

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

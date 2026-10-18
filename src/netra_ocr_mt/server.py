"""Deprecated: use ``netra_translate.server`` (``uvicorn netra_translate.server.app:app``)."""
from netra_translate.server.app import app, create_app  # noqa: F401

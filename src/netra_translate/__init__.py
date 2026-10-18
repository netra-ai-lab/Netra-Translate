"""Netra Translate: image or PDF in, translated document out (Khmer <-> English).

    from netra_translate import NetraTranslate

    pipe = NetraTranslate()
    for res in pipe.predict("scan.jpg"):
        res.print()
        res.save_to_docx("output/")
"""
from importlib.metadata import PackageNotFoundError, version as _dist_version

from .pipeline import DIRECTIONS, NetraTranslate, OCRTranslator
from .result import FORMATS, TranslationResult
from .translator import Translator

try:
    __version__ = _dist_version("netra-translate")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"

__all__ = ["DIRECTIONS", "FORMATS", "Client", "NetraTranslate", "OCRTranslator", "TranslationResult",
           "Translator", "__version__"]


def __getattr__(name):
    # Imported on first use, so the core package doesn't need httpx.
    if name in ("Client", "NetraAPIError"):
        from . import client
        return getattr(client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

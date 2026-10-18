"""Deprecated: the package is now ``netra_translate``. This alias goes away in the next release."""
import sys
import warnings

warnings.warn("netra_ocr_mt has been renamed to netra_translate; "
              "update your imports (from netra_translate import NetraTranslate).",
              DeprecationWarning, stacklevel=2)

import netra_translate as _nt  # noqa: E402
from netra_translate import (  # noqa: E402,F401
    DIRECTIONS, FORMATS, NetraTranslate, OCRTranslator, TranslationResult, Translator, __version__)
from netra_translate import cli, merge, pipeline, result, text, translator  # noqa: E402,F401

# `import netra_ocr_mt.text` etc. resolve to the new modules.
for _name in ("cli", "merge", "pipeline", "result", "text", "translator"):
    sys.modules[f"{__name__}.{_name}"] = getattr(_nt, _name)

__all__ = _nt.__all__

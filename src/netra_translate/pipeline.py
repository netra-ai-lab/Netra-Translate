"""OCR -> translate pipeline."""
from __future__ import annotations

import copy
from typing import Callable, Iterable, Iterator, Optional, Union

from netra_ocr.document import TEXT_TYPES, Document

from . import text as T
from .merge import merge_lines
from .result import TranslationResult
from .translator import Translator

DIRECTIONS = ("auto", T.EN2KM, T.KM2EN)

Source = Union[str, bytes]
Progress = Optional[Callable[[int, int], None]]


def _check_direction(direction: str) -> None:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")


class NetraTranslate:
    """Image/PDF in, translated structured document out.

    >>> from netra_translate import NetraTranslate
    >>> pipe = NetraTranslate()
    >>> for res in pipe.predict("scan.jpg"):
    ...     res.print()
    ...     res.save_to_docx("output/")

    Both models load lazily on first use and are reused across calls.
    """

    def __init__(self, detector: str = "yolo", layout: bool = False, direction: str = "auto",
                 device: Optional[str] = None, mode: str = "greedy", beam_size: int = 5,
                 ocr_decoder: str = "ar", ocr_beam: int = 1, conf: Optional[float] = None,
                 merge_lines: bool = True, translator: Optional[Translator] = None, ocr=None):
        _check_direction(direction)
        self.direction = direction
        self.merge_lines = merge_lines
        self.ocr_beam = ocr_beam
        self._ocr_args = dict(detector=detector, conf=conf, decoder=ocr_decoder, layout=layout)
        self._ocr = ocr  # injectable for tests
        self.translator = translator or Translator(device=device, mode=mode, beam_size=beam_size)

    # Options a config file may set (everything but the injectable models).
    CONFIG_KEYS = ("detector", "layout", "direction", "device", "mode", "beam_size", "ocr_decoder",
                   "ocr_beam", "conf", "merge_lines")

    @classmethod
    def from_config(cls, path: str, **overrides) -> "NetraTranslate":
        """Build a pipeline from a YAML/JSON config file (see :mod:`netra_translate.config`).

        >>> pipe = NetraTranslate.from_config("netra.yaml", device="cpu")
        """
        from .config import load_config
        return cls(**{**load_config(path, "pipeline", cls.CONFIG_KEYS), **overrides})

    @property
    def ocr(self):
        if self._ocr is None:
            from netra_ocr.ocr_engine import KhmerOCRPipeline
            self._ocr = KhmerOCRPipeline(**self._ocr_args)
        return self._ocr

    # ── PaddleOCR-style entry points ───────────────────────────────────
    def predict(self, input: Union[Source, Iterable[Source]], **kwargs) -> list[TranslationResult]:
        """Translate one file (path or bytes) or a list of them; returns one result per file.

        Keyword arguments are passed to :meth:`run` (``direction``, ``max_pages``, …).
        """
        return list(self.predict_iter(input, **kwargs))

    def predict_iter(self, input: Union[Source, Iterable[Source]], **kwargs) -> Iterator[TranslationResult]:
        """Like :meth:`predict`, but yields each result as soon as it's ready."""
        sources = [input] if isinstance(input, (str, bytes)) or hasattr(input, "__fspath__") else input
        for source in sources:
            if hasattr(source, "__fspath__"):
                source = str(source)
            result = self.run(source, **kwargs)
            if isinstance(source, str):
                result.input_path = source
            yield result

    # ── steps ──────────────────────────────────────────────────────────
    def run(self, source: Source, max_pages: Optional[int] = None,
            include_headers_footers: bool = True, progress: Progress = None,
            direction: Optional[str] = None) -> TranslationResult:
        """OCR ``source`` (image/TIFF/PDF path or bytes) and translate every text block.

        ``progress(done, total)`` is called after each OCR page.
        """
        doc = self.ocr.process_document(
            source, beam_width=self.ocr_beam, include_headers_footers=include_headers_footers,
            max_pages=max_pages, progress=progress)
        return self.translate_document(doc, direction=direction)

    def translate_document(self, doc: Document, direction: Optional[str] = None,
                           progress: Progress = None) -> TranslationResult:
        """Translate an OCR document. ``progress(done, total)`` is called after each block."""
        direction = direction or self.direction
        _check_direction(direction)
        if self.merge_lines:
            doc = merge_lines(doc)
        cache: dict[tuple[str, str], tuple[str, str]] = {}

        def tr(text: str) -> tuple[str, str]:
            key = (text, direction)
            if key not in cache:
                cache[key] = self.translator.translate(text, direction)
            return cache[key]

        total = sum(1 for b in doc.blocks if b["type"] in TEXT_TYPES or b["type"] == "table")
        done = 0
        blocks = []
        for b in doc.blocks:
            nb = copy.deepcopy(b)
            if b["type"] in TEXT_TYPES:
                paragraph = T.reflow_lines(b.get("text", "").split("\n"))
                nb["source_text"] = b.get("text", "")
                nb["text"], nb["direction"] = tr(paragraph) if paragraph else ("", None)
            elif b["type"] == "table":
                nb["source_rows"] = b["rows"]
                nb["rows"] = [[tr(c)[0] if c.strip() else c for c in row] for row in b["rows"]]
                if b.get("caption"):
                    nb["caption"] = tr(b["caption"])[0]
            else:
                blocks.append(nb)
                continue
            blocks.append(nb)
            done += 1
            if progress:
                progress(done, total)
        translated = Document(pages=copy.deepcopy(doc.pages), blocks=blocks, assets=doc.assets)
        return TranslationResult(source=doc, translated=translated, direction=direction)


# Old name (netra-ocr-mt 1.0 previews). Kept as an alias.
OCRTranslator = NetraTranslate

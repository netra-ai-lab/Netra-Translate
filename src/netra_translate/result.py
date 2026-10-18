"""Translated document + export helpers."""
from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

from netra_ocr.document import TEXT_TYPES, Document

JSON_VERSION = 1
FORMATS = ("json", "txt", "md", "html", "docx")


@dataclass
class TranslationResult:
    """``source`` is the OCR output; ``translated`` has the same blocks with text replaced.

    Translated text blocks carry ``source_text`` and ``direction``; translated
    tables carry ``source_rows``.
    """
    source: Document
    translated: Document
    direction: str = "auto"           # what was asked for; each block records what was used
    input_path: Optional[str] = None  # set by predict() for file inputs; names saved files

    @property
    def text(self) -> str:
        return self.translated.text

    @property
    def json(self) -> dict:
        """The translated document as a JSON-ready dict (same as :meth:`to_dict`)."""
        return self.to_dict()

    def to_dict(self) -> dict:
        data = self.translated.to_dict()
        data["translate_version"] = JSON_VERSION
        return data

    def bilingual_document(self) -> Document:
        """Each block followed by its translation (headings keep the source heading)."""
        blocks = []
        for src, tr in zip(self.source.blocks, self.translated.blocks):
            blocks.append(copy.deepcopy(src))
            if src["type"] in TEXT_TYPES or src["type"] == "table":
                extra = copy.deepcopy(tr)
                extra["id"] = tr["id"] + "-tr"
                if extra["type"] == "heading":
                    extra["type"] = "paragraph"
                blocks.append(extra)
        return Document(pages=copy.deepcopy(self.translated.pages), blocks=blocks,
                        assets=self.translated.assets)

    def export(self, fmt: str, bilingual: bool = False, basename: Optional[str] = None
               ) -> tuple[bytes, str, str]:
        """Render as ``(data, filename, mimetype)``; fmt is json|txt|md|html|docx."""
        fmt = fmt.lower().lstrip(".")
        if fmt not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}, got {fmt!r}")
        basename = basename or self._stem()
        if fmt == "json":
            data = json.dumps(self.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
            return data, basename + ".json", "application/json"
        from netra_ocr.exporters import export
        doc = self.bilingual_document() if bilingual else self.translated
        return export(doc, fmt, basename=basename)

    def save(self, output_path: str, bilingual: bool = False) -> str:
        """Write to ``output_path``; extension picks the format. Returns the path written
        (Markdown with figures becomes a .zip)."""
        root, ext = os.path.splitext(output_path)
        data, filename, _ = self.export(ext or ".txt", bilingual=bilingual)
        path = root + os.path.splitext(filename)[1]
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    # ── PaddleOCR-style helpers ────────────────────────────────────────
    def print(self, bilingual: bool = False) -> None:
        """Print the translated text (UTF-8, whatever the console encoding)."""
        text = self.bilingual_document().text if bilingual else self.text
        out = sys.stdout
        if hasattr(out, "reconfigure"):
            try:
                out.reconfigure(encoding="utf-8")
            except Exception:
                pass
        print(text, file=out)

    def save_to_json(self, save_path: str) -> str:
        return self._save_to(save_path, "json")

    def save_to_docx(self, save_path: str, bilingual: bool = False) -> str:
        return self._save_to(save_path, "docx", bilingual)

    def save_to_markdown(self, save_path: str, bilingual: bool = False) -> str:
        return self._save_to(save_path, "md", bilingual)

    def _stem(self) -> str:
        if self.input_path:
            return os.path.splitext(os.path.basename(self.input_path))[0] + "_translated"
        return "translation"

    def _save_to(self, save_path: str, fmt: str, bilingual: bool = False) -> str:
        """``save_path`` is a directory (file named after the input) or a full file path."""
        if os.path.splitext(save_path)[1].lower().lstrip(".") in (*FORMATS, "zip"):
            return self.save(os.path.splitext(save_path)[0] + "." + fmt, bilingual=bilingual)
        return self.save(os.path.join(save_path, self._stem() + "." + fmt), bilingual=bilingual)

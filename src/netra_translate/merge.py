"""Merge per-line OCR blocks into paragraphs before translation.

Without layout analysis Netra-OCR emits one block per text line (``label == "line"``),
so a sentence wrapped over two lines would be translated as two fragments. Consecutive
line blocks are joined when the previous line is unfinished and the next line sits
directly below it.
"""
from __future__ import annotations

import copy

from netra_ocr.document import Document

SENTENCE_END = ("។", "៕", ".", "!", "?", ":", "៖")


def _joinable(prev: dict, nxt: dict, max_gap: float) -> bool:
    if prev["page"] != nxt["page"] or not prev.get("bbox") or not nxt.get("bbox"):
        return False
    if prev["text"].rstrip().endswith(SENTENCE_END):
        return False
    px1, py1, px2, py2 = prev["lines"][-1]["bbox"]
    nx1, ny1, nx2, ny2 = nxt["bbox"]
    height = max(py2 - py1, 1)
    gap = ny1 - py2
    return -height * 0.5 <= gap <= max_gap * height and nx1 < px2 and nx2 > px1


def merge_lines(doc: Document, max_gap: float = 0.6) -> Document:
    """Return a copy of ``doc`` with consecutive ``line`` blocks merged into paragraphs."""
    out = []
    for b in doc.blocks:
        b = copy.deepcopy(b)
        prev = out[-1] if out else None
        is_line = b["type"] == "paragraph" and b.get("label") == "line" and b.get("lines")
        if (is_line and prev is not None and prev["type"] == "paragraph"
                and prev.get("label") in ("line", "paragraph-merged") and prev.get("lines")
                and _joinable(prev, b, max_gap)):
            prev["text"] += "\n" + b["text"]
            prev["lines"].extend(b["lines"])
            x1, y1, x2, y2 = prev["bbox"]
            bx1, by1, bx2, by2 = b["bbox"]
            prev["bbox"] = [min(x1, bx1), min(y1, by1), max(x2, bx2), max(y2, by2)]
            prev["label"] = "paragraph-merged"
        else:
            out.append(b)
    return Document(pages=copy.deepcopy(doc.pages), blocks=out, assets=doc.assets,
                    revision=doc.revision)

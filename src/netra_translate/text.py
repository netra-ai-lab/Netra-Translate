"""Text utilities that sit between OCR output and the NMT model.

Netra-NMT does no sentence splitting and silently truncates long input, so the
OCR text is reflowed into paragraphs and split into sentences here.
"""
from __future__ import annotations

import re
from typing import Iterable, List

EN2KM = "en2km"
KM2EN = "km2en"

_KHMER_RE = re.compile(r"[ក-៿᧠-᧿]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ZERO_WIDTH = re.compile(r"[​‌‍﻿]")

# Sentence terminators: Khmer khan/bariyosan split anywhere; Latin . ! ? only
# when followed by whitespace (keeps "3.14" and "a?b=1" intact).
_SENT_END = re.compile(r"(?<=[។៕])\s*|(?<=[.!?])\s+(?=\S)")
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:៖])\s+")


def khmer_ratio(text: str) -> float:
    """Fraction of letters in ``text`` that are Khmer (0.0 when no letters)."""
    km = len(_KHMER_RE.findall(text))
    en = len(_LATIN_RE.findall(text))
    total = km + en
    return km / total if total else 0.0


def detect_direction(text: str) -> str:
    """Pick the translation direction from the dominant script.

    Mostly Khmer -> ``km2en``; otherwise ``en2km``.
    """
    return KM2EN if khmer_ratio(text) >= 0.5 else EN2KM


def clean(text: str) -> str:
    text = _ZERO_WIDTH.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def reflow_lines(lines: Iterable[str]) -> str:
    """Merge OCR text lines of one block into a single paragraph.

    Khmer is written without inter-word spaces, so a line break between two Khmer
    characters is joined with nothing; everything else is joined with a space.
    A trailing hyphen on a Latin word is treated as a soft wrap.
    """
    out = ""
    for raw in lines:
        line = clean(raw)
        if not line:
            continue
        if not out:
            out = line
            continue
        prev, nxt = out[-1], line[0]
        if _KHMER_RE.match(prev) and _KHMER_RE.match(nxt):
            out += line
        elif prev == "-" and len(out) > 1 and out[-2].isalpha() and nxt.islower():
            out = out[:-1] + line
        else:
            out += " " + line
    return out


def split_sentences(text: str) -> List[str]:
    """Split a paragraph into sentences on Khmer and Latin terminators."""
    text = clean(text)
    if not text:
        return []
    parts = [p.strip() for p in _SENT_END.split(text)]
    return [p for p in parts if p]


def chunk_sentence(sentence: str, max_chars: int = 300) -> List[str]:
    """Break an over-long sentence so it stays under the model's length limit.

    Prefers clause punctuation, then Latin spaces; Khmer with no separators is
    hard-cut at ``max_chars`` as a last resort.
    """
    if len(sentence) <= max_chars:
        return [sentence]
    chunks: List[str] = []
    buf = ""
    for clause in _CLAUSE_SPLIT.split(sentence):
        if buf and len(buf) + len(clause) + 1 > max_chars:
            chunks.append(buf)
            buf = clause
        else:
            buf = f"{buf} {clause}".strip()
    if buf:
        chunks.append(buf)

    final: List[str] = []
    for chunk in chunks:
        while len(chunk) > max_chars:
            cut = chunk.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            final.append(chunk[:cut].strip())
            chunk = chunk[cut:].strip()
        if chunk:
            final.append(chunk)
    return final


def has_letters(text: str) -> bool:
    """True if ``text`` contains any Khmer or Latin letter (else not worth translating)."""
    return bool(_KHMER_RE.search(text) or _LATIN_RE.search(text))


def join_translations(parts: Iterable[str]) -> str:
    """Join translated sentences with single spaces, dropping empties."""
    return " ".join(p.strip() for p in parts if p and p.strip())

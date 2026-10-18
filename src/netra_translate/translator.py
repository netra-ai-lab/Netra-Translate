"""Sentence-safe wrapper around ``netra_nmt.NetraTranslator``.

Netra-NMT translates one string at a time with no sentence splitting and
truncates long input, so paragraphs are split here and translated per sentence.
"""
from __future__ import annotations

from typing import Optional

from . import text as T


class Translator:
    def __init__(self, device: Optional[str] = None, mode: str = "greedy",
                 beam_size: int = 5, max_chars: int = 200, max_new_tokens: int = 200,
                 model=None):
        self.device = device
        self.mode = mode
        self.beam_size = beam_size
        self.max_chars = max_chars
        self.max_new_tokens = max_new_tokens
        self._model = model  # injectable for tests

    @property
    def model(self):
        if self._model is None:
            from netra_nmt import NetraTranslator
            self._model = NetraTranslator(device=self.device)
        return self._model

    def translate(self, text: str, direction: str = "auto") -> tuple[str, str]:
        """Translate a paragraph. Returns ``(translation, direction_used)``.

        Text without any Khmer/Latin letters (page numbers, dates) is returned as is.
        """
        text = T.clean(text)
        if direction == "auto":
            direction = T.detect_direction(text)
        if not T.has_letters(text):
            return text, direction

        out = []
        for sentence in T.split_sentences(text):
            for chunk in T.chunk_sentence(sentence, self.max_chars):
                if not T.has_letters(chunk):
                    out.append(chunk)
                    continue
                out.append(self.model.translate(
                    chunk, direction=direction, mode=self.mode,
                    beam_size=self.beam_size, max_new_tokens=self.max_new_tokens))
        return T.join_translations(out), direction

"""Model weights: download everything the pipeline needs ahead of time.

    netra-translate download            # OCR recognizer + translator
    netra-translate download --layout   # + the layout model

Weights go to the Hugging Face cache (``HF_HOME``, default ``~/.cache/huggingface``).
After a download, ``HF_HUB_OFFLINE=1`` runs without network access. The YOLO
text-line detector and the translator's tokenizer ship inside their wheels.
"""
from __future__ import annotations

from typing import Callable, Optional


def download(layout: bool = False, log: Optional[Callable[[str], None]] = print) -> list[str]:
    """Fetch every model file into the Hugging Face cache; returns their paths."""
    from huggingface_hub import hf_hub_download
    from netra_nmt.config import CONFIG_FILENAME, HF_REPO_ID, WEIGHTS_FILENAME
    from netra_ocr.recognition.recognize_text import DECODER_FILENAMES, DEFAULT_MODEL_REPO

    wanted = [("recognizer", DEFAULT_MODEL_REPO, f) for f in DECODER_FILENAMES.values()]
    wanted += [("translator", HF_REPO_ID, f) for f in (WEIGHTS_FILENAME, CONFIG_FILENAME)]
    if layout:
        from netra_ocr.layout.doclayout import DEFAULT_FILENAME, DEFAULT_REPO
        wanted.append(("layout", DEFAULT_REPO, DEFAULT_FILENAME))
    paths = []
    for what, repo, filename in wanted:
        path = hf_hub_download(repo, filename)
        paths.append(path)
        if log:
            log(f"{what}: {path}")
    return paths

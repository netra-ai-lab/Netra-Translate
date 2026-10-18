"""Config files for the pipeline and the server (YAML or JSON).

A config file is a mapping of options. Options can be grouped by who reads them::

    pipeline:            # netra-translate translate, NetraTranslate.from_config()
      layout: true
      direction: km2en
    server:              # netra-translate serve / worker
      max_pages: 20
      job_ttl_hours: 6

A file without those two keys is read whole by whichever command loads it.
Options given on the command line override the file.
"""
from __future__ import annotations

import json
import os
from typing import Iterable

SECTIONS = ("pipeline", "server")


def load_config(path: str, section: str, allowed: Iterable[str]) -> dict:
    """The options for ``section`` from ``path``; unknown keys raise ValueError."""
    if section not in SECTIONS:
        raise ValueError(f"section must be one of {SECTIONS}")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if os.path.splitext(path)[1].lower() == ".json":
        data = json.loads(text)
    else:
        import yaml
        data = yaml.safe_load(text)
    data = {} if data is None else data
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a config file must be a mapping of options")
    if any(k in data for k in SECTIONS):
        unknown = set(data) - set(SECTIONS)
        if unknown:
            raise ValueError(f"{path}: unknown section(s) {', '.join(sorted(unknown))}; "
                             f"use {' and '.join(SECTIONS)}")
        data = data.get(section) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path}: '{section}' must be a mapping of options")
    allowed = sorted(allowed)
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValueError(f"{path}: unknown option(s) {', '.join(unknown)}. "
                         f"Allowed: {', '.join(allowed)}")
    return data

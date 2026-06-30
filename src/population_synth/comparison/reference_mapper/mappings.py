"""Category-mapping loader for reference populations.

A reference mapper consumes per-attribute category mappings curated under
``config/mapping/{scb,ssb,istat}/``. :func:`load_mappings` assembles those
per-attribute JSON files (or a single monolithic file) into one dict.
"""

from __future__ import annotations

import json
from pathlib import Path

from population_synth._paths import PROJECT_ROOT

_SCB_MAPPINGS_DIR = PROJECT_ROOT / "config" / "mapping" / "scb"


def load_mappings(path: Path | None = None) -> dict:
    """Load category mappings from *path* (defaults to the SCB reference directory).

    *path* may be either a directory of per-attribute JSON files (each filename
    stem becomes a top-level key) or a single monolithic ``category_mappings.json``
    file. The returned dict is identical for both layouts.
    """
    p = path or _SCB_MAPPINGS_DIR
    if p.is_dir():
        merged: dict = {}
        for f in sorted(p.glob("*.json")):
            with open(f, "r", encoding="utf-8") as fh:
                merged[f.stem] = json.load(fh)
        return merged
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

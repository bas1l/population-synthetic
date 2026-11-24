"""Category-mapping loader for real populations.

A real mapper consumes per-attribute category mappings curated under
``config/mapping/{scb,ssb,istat}/``. :func:`load_mappings` assembles those
per-attribute JSON files (or a single monolithic file) into one dict.
:func:`load_index` reads the per-country ``_index.json`` master that lists the
comparison attributes (attribute → filename). The cross-attribute statistics
(joint pairs, coherence attributes/threshold) live in a separate comparison-analysis
config (``config/analysis/fidelity/{country}.json``), not the mapping index.
"""

from __future__ import annotations

import json
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT

_SCB_MAPPINGS_DIR = PROJECT_ROOT / "config" / "mapping" / "scb"

#: Master-index filename inside a country mapping directory.
INDEX_FILENAME = "_index.json"

#: Keys every ``_index.json`` master must declare.
_REQUIRED_INDEX_KEYS = ("attributes",)


def load_mappings(path: Path | None = None) -> dict:
    """Load category mappings from *path* (defaults to the SCB real directory).

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


def index_path(path: Path) -> Path:
    """Resolve the ``_index.json`` file path for *path* (a directory or the file itself)."""
    return path / INDEX_FILENAME if path.is_dir() else path


def load_index(path: Path) -> dict:
    """Load and validate the ``_index.json`` master for a country mapping directory.

    *path* may be either the country mapping directory (the ``_index.json`` inside
    it is read) or the master file directly. The returned dict is the parsed
    master; it is validated to declare ``attributes``, an ordered
    ``attribute -> filename`` mapping (key order = comparison axis order). Fails
    loudly on a missing file, a missing ``attributes`` key, or a malformed
    ``attributes`` block.
    """
    ip = index_path(path)
    if not ip.is_file():
        raise FileNotFoundError(f"No mapping index found: {ip} not found")

    with open(ip, "r", encoding="utf-8") as fh:
        index = json.load(fh)

    for key in _REQUIRED_INDEX_KEYS:
        if key not in index:
            raise KeyError(f"Mapping index {ip} is missing required key {key!r}")

    attributes = index["attributes"]
    if not isinstance(attributes, dict) or not attributes:
        raise ValueError(f"Mapping index {ip} 'attributes' must be a non-empty object")

    # ``deprecated_attributes`` is optional (absence is fine); when present it must be a
    # list of attribute-name strings. Membership against ``attributes`` is validated later,
    # at the analysis chokepoint that consumes it (``_scheme_from_index``).
    if "deprecated_attributes" in index:
        deprecated = index["deprecated_attributes"]
        if not isinstance(deprecated, list) or not all(isinstance(name, str) for name in deprecated):
            raise ValueError(
                f"Mapping index {ip} 'deprecated_attributes' must be a list of attribute-name strings"
            )

    return index

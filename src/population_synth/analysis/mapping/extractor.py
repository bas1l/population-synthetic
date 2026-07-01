"""extractor.py -- Extract demographic profiles from pipeline identity.json files.

Only the flat / configurable identity format (top-level attribute keys) is
supported.  A legacy narrative dict (``{"narrative": ...}``) is treated as an
unrecognised format and returns ``None`` (warn-and-skip).

The public entry point is ``extract_individual(identity_path)`` which returns a
flat attribute dict (or None on failure).

This module is a thin facade over the ``population_synth.analysis.mapping.synthetic_mapper``
subpackage: the country mapper classes own the per-attribute mapping, and
``load_raw_population`` / ``map_population`` provide the load-then-map flow. The
public import path (``extract_individual`` / ``extract_population``) is preserved
unchanged for backward compatibility.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from population_synth.analysis.mapping.synthetic_mapper import (
    get_synthetic_mapper,
    load_raw_population,
    map_population,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_individual(identity_path: Path, country: str = "swedish") -> dict[str, Any] | None:
    """Read an identity.json file, auto-detect format, and return a flat attribute dict.

    Returns None if the file cannot be read or the persona is critically incomplete.
    """
    persona_id = identity_path.parent.name
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s: could not read identity.json: %s", persona_id, exc)
        return None

    attrs = get_synthetic_mapper(country).map_individual(identity, persona_id)
    if attrs is None:
        return None
    return {"id": persona_id, **attrs}


def extract_population(seed_root: Path, country: str = "swedish") -> dict[str, Any]:
    """Load pipeline identities from disk and map them to the canonical schema.

    Convenience wrapper over ``load_raw_population`` + ``map_population``; the
    compare scripts call those two steps explicitly to keep load and map visible.
    """
    return map_population(load_raw_population(seed_root), country)

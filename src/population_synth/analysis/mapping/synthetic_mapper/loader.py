"""Two-step synthetic-population pipeline: load raw from disk, then map to schema.

``load_raw_population`` reads the ``persona_*/identity.json`` files verbatim (the
population *as it is on the harddrive*); ``map_population`` applies the
country-specific synthetic mapper to produce the canonical schema population.
Keeping the two steps separate mirrors the reference side
(``load_reference_population`` -> ``normalize_population``).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from population_synth.analysis.mapping.synthetic_mapper.factory import get_synthetic_mapper
from population_synth.analysis.mapping.synthetic_mapper.base import  BaseSyntheticMapper

logger = logging.getLogger(__name__)


def load_raw_population(seed_root: Path) -> dict[str, Any]:
    """Load ``persona_*/identity.json`` files verbatim from disk (no mapping).

    Each individual is the raw identity dict with its ``id`` (the persona
    directory name) injected.  Raises ``ValueError`` if no identity files exist.
    """
    identity_files = sorted(seed_root.glob("persona_*/identity.json"))
    if not identity_files:
        raise ValueError(f"No persona_*/identity.json files found under {seed_root}")

    print(f"Found {len(identity_files)} identity files under {seed_root}")

    individuals: list[dict[str, Any]] = []
    unreadable = 0
    for path in identity_files:
        persona_id = path.parent.name
        try:
            identity = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("%s: could not read identity.json: %s", persona_id, exc)
            unreadable += 1
            continue
        individuals.append({"id": persona_id, **identity})

    return {
        "metadata": {
            "source": "pipeline-raw",
            "seed_root": str(seed_root.resolve()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_files": len(identity_files),
            "unreadable": unreadable,
        },
        "individuals": individuals,
    }


def map_population(raw_pop: dict[str, Any], country: str = "swedish") -> dict[str, Any]:
    """Map a raw pipeline population to the canonical schema for *country*.

    Skips critically-incomplete personas (``map_individual`` returns ``None``)
    and folds disk-unreadable files (from :func:`load_raw_population`) into the
    skip count, so the returned ``metadata`` matches the legacy one-shot path.
    """
    mapper: BaseSyntheticMapper = get_synthetic_mapper(country)
    individuals: list[dict[str, Any]] = []
    skipped = int(raw_pop["metadata"].get("unreadable", 0))

    for indiv in raw_pop["individuals"]:
        persona_id = indiv.get("id", "?")
        mapped = mapper.map_individual(indiv, persona_id)
        if mapped is None:
            skipped += 1
        else:
            individuals.append({"id": persona_id, **mapped})

    if skipped:
        print(f"WARNING: Skipped {skipped} persona(s) due to errors or missing data", file=sys.stderr)

    return {
        "metadata": {
            "source": "pipeline",
            "seed_root": raw_pop["metadata"].get("seed_root"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": len(individuals),
            "skipped": skipped,
        },
        "individuals": individuals,
    }

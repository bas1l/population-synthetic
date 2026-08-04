"""Identity of the generation regime a persona was produced under.

A checkpoint is only safe to resume against the *same* configuration that wrote
it. Splicing a persona's first eight categories from one strategy onto its last
six from another would produce a record that no experimental arm actually
generated, and nothing downstream could detect it. The fingerprint is the value
that makes that detectable: :func:`build_run_fingerprint` reduces the run's
inputs to a small comparable dict, and the writer refuses any checkpoint whose
stored copy differs.

Kept apart from ``persona_writer`` on purpose -- the writer owns one persona's
files and must stay ignorant of strategies, schemas and providers; it only ever
compares two opaque dicts for equality.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence


def _file_sha256(path: Path | str) -> str:
    """Hash a config file's bytes, so any edit at all changes the fingerprint."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_run_fingerprint(
    *,
    strategy_path: Path | str | None,
    schema_path: Path | str,
    provider: str,
    model: str,
    category_order: Sequence[str] | None,
) -> dict[str, Any]:
    """Reduce a run's generation regime to a comparable dict.

    The two hashes are over the raw file bytes rather than the parsed content:
    a semantically inert reformat then invalidates checkpoints, which is the safe
    direction to err in (a discarded checkpoint costs LLM calls; a wrongly
    accepted one silently corrupts an experimental arm).

    ``category_order`` is the resolved DAG order, not the strategy's edge list --
    it is what the prompts actually saw, and it is what the resume prefix walk is
    replayed against. ``None`` for modes that have no category DAG.
    """
    return {
        "strategy_sha256": _file_sha256(strategy_path) if strategy_path is not None else None,
        "schema_sha256": _file_sha256(schema_path),
        "model_key": f"{provider}:{model}",
        "category_order": list(category_order) if category_order is not None else None,
    }

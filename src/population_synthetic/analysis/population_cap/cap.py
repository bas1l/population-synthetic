"""cap.py -- Seeded per-combo cap of generated personas into a capped mirror.

The population-cap task runs first in the analysis pipeline. For a single
combination (country x strategy x model), :func:`cap_combo` seeded-selects exactly
``n`` of the ``persona_*`` directories under one ``01_Raw/{slug}/`` combo dir and
copies them -- together with the combo-level ancillary files (``logs/``,
``run_metadata.json``, ``manifest_snapshot.yaml``) -- into a layout-identical mirror
at ``dest_dir``. Downstream raw-persona consumers (mapping, generation_metadata) read
the mirror instead of the full raw dir, so no task can analyze more than ``n``
personas.

Selection reuses the project's shared without-replacement index draw
(:func:`population_synthetic.analysis.utils.sampling.select_indices`) over the
lexicographically sorted ``persona_*`` list, so a fixed ``seed`` is reproducible and
stays consistent with the fidelity subsample.

This module is deliberately schema-agnostic: it never inspects persona attributes,
canonical mapping axes, country label maps, or fidelity math. It only knows about the
on-disk combo layout.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TypedDict

from population_synthetic.analysis.utils.sampling import select_indices

logger = logging.getLogger(__name__)

# Combo-level ancillary entries copied verbatim (not per-persona). A missing entry is
# skipped silently -- not every run emits every ancillary file.
_ANCILLARY_ENTRIES = ("logs", "run_metadata.json", "manifest_snapshot.yaml")

# Glob for the per-persona directories inside a combo dir.
_PERSONA_GLOB = "persona_*"


class CapSummary(TypedDict):
    """Per-combo result of a :func:`cap_combo` call."""

    slug: str
    requested_n: int
    available: int
    selected: int
    seed: int
    selected_ids: list[str]
    truncated: bool


def _sorted_persona_dirs(raw_slug_dir: Path) -> list[Path]:
    """Return the combo's ``persona_*`` subdirectories, lexicographically sorted by name."""
    return sorted(
        (p for p in raw_slug_dir.glob(_PERSONA_GLOB) if p.is_dir()),
        key=lambda p: p.name,
    )


def cap_combo(
    raw_slug_dir: Path,
    n: int,
    seed: int,
    dest_dir: Path,
    *,
    force: bool = False,
) -> CapSummary:
    """Seeded-select ``n`` persona dirs from one raw combo dir and copy them to ``dest_dir``.

    The selected ``persona_*`` directories are copied wholesale (identity + telemetry +
    nested logs) via :func:`shutil.copytree`, and the combo-level ancillary entries
    (``logs/``, ``run_metadata.json``, ``manifest_snapshot.yaml``) are copied verbatim,
    reproducing the ``raw_slug_dir`` layout under ``dest_dir``. The source
    ``raw_slug_dir`` is never mutated.

    When fewer than ``n`` persona dirs are available, all of them are copied and a loud
    warning is logged (the batch is not failed); the returned summary records
    ``selected < requested_n`` with ``truncated`` False. ``truncated`` is True only when
    the selection genuinely dropped personas (``available > n``).

    Args:
        raw_slug_dir: The source ``01_Raw/{slug}/`` combo directory.
        n: Target number of persona dirs to retain (the cap). Must be positive.
        seed: Seed for the reproducible without-replacement draw.
        dest_dir: Destination combo dir (the capped mirror ``population_cap/{slug}/``).
        force: When True, an existing ``dest_dir`` is removed and fully rewritten. When
            False and ``dest_dir`` already exists, raises (caller decides skip vs force).

    Returns:
        A :class:`CapSummary` dict:
        ``{slug, requested_n, available, selected, seed, selected_ids, truncated}``.

    Raises:
        ValueError: If ``n`` is not a positive integer.
        FileNotFoundError: If ``raw_slug_dir`` does not exist or is not a directory.
        FileExistsError: If ``dest_dir`` exists and ``force`` is False.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"cap_combo requires a positive integer n; got {n!r}.")

    raw_slug_dir = Path(raw_slug_dir)
    dest_dir = Path(dest_dir)

    if not raw_slug_dir.is_dir():
        raise FileNotFoundError(f"Raw combo directory not found: {raw_slug_dir}")

    slug = raw_slug_dir.name

    if dest_dir.exists():
        if not force:
            raise FileExistsError(
                f"Capped mirror already exists for combo {slug!r}: {dest_dir} "
                f"(pass force=True to overwrite)."
            )
        shutil.rmtree(dest_dir)

    persona_dirs = _sorted_persona_dirs(raw_slug_dir)
    available = len(persona_dirs)

    if available == 0:
        logger.warning(
            "population_cap: combo %r has 0 %s directories under %s; "
            "writing an empty capped mirror.",
            slug,
            _PERSONA_GLOB,
            raw_slug_dir,
        )

    truncated = available > n
    if available < n:
        logger.warning(
            "population_cap: combo %r has only %d persona dirs, fewer than the "
            "requested n=%d; copying all %d (no truncation).",
            slug,
            available,
            n,
            available,
        )

    selected_idx = select_indices(available, n, seed)
    selected_dirs = [persona_dirs[i] for i in selected_idx]

    dest_dir.mkdir(parents=True, exist_ok=True)

    for persona_dir in selected_dirs:
        shutil.copytree(persona_dir, dest_dir / persona_dir.name)

    for entry_name in _ANCILLARY_ENTRIES:
        source = raw_slug_dir / entry_name
        if not source.exists():
            continue
        target = dest_dir / entry_name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    return CapSummary(
        slug=slug,
        requested_n=n,
        available=available,
        selected=len(selected_dirs),
        seed=seed,
        selected_ids=[d.name for d in selected_dirs],
        truncated=truncated,
    )

"""cap.py -- Seeded per-combo cap of VALIDATED personas into the capped outputs.

The population-cap task runs LAST of the validation gate (``validate_raw`` -> ``mapping``
-> ``validate_mapped`` -> ``population_cap``). For a single combination
(country x strategy x model), :func:`cap_combo`:

1. reads the two per-combo validity CSVs and intersects them to the **clean** persona ids
   (those that pass BOTH the raw-completeness and the mapped-value gates);
2. seeded-selects ``n`` of those clean personas;
3. copies the selected raw ``persona_*`` directories -- together with the combo-level
   ancillary files (``logs/``, ``run_metadata.json``, ``manifest_snapshot.yaml``) -- into
   the capped persona-dir mirror at ``dest_dir`` (consumed by ``generation_metadata`` for
   telemetry); and
4. writes the **capped mapped file** for the same ``n`` -- a subset of ``mapping/{slug}.json``
   filtered to the selected ids -- into ``_mapped/{slug}.json``, alongside a copy of the
   real reference ``real_{country}.json`` (consumed by fidelity, multivariate, consistency,
   pairwise, real_population_stats and persona_realism).

Selection reuses the project's shared without-replacement index draw
(:func:`population_synthetic.analysis.utils.sampling.select_indices`) over the
lexicographically sorted clean-persona list, so a fixed ``seed`` is reproducible.

When fewer than ``n`` clean personas exist, all of them are used and a loud warning is
logged (the batch is not failed): the capped outputs then hold a visible, *clean*
shortfall rather than the previous silent, *dirty* one. The source directories and the
``mapping/`` output are never mutated.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, TypedDict

from population_synthetic.analysis.utils.fs import clear_readonly_tree, rmtree_resilient
from population_synthetic.analysis.utils.sampling import select_indices
from population_synthetic.analysis.utils.validity_csv import read_passed_ids

logger = logging.getLogger(__name__)

# Combo-level ancillary entries copied verbatim (not per-persona). A missing entry is
# skipped silently -- not every run emits every ancillary file.
_ANCILLARY_ENTRIES = ("logs", "run_metadata.json", "manifest_snapshot.yaml")

# Glob for the per-persona directories inside a combo dir.
_PERSONA_GLOB = "persona_*"


class CapSummary(TypedDict):
    """Per-combo result of a :func:`cap_combo` call."""

    slug: str
    country: str
    requested_n: int
    raw_passed: int
    mapped_passed: int
    clean_available: int
    selected: int
    seed: int
    selected_ids: list[str]
    truncated: bool
    synthetic_file: str | None
    real_file: str | None
    mapped_n: int


def _sorted_persona_dirs(raw_slug_dir: Path) -> list[Path]:
    """Return the combo's ``persona_*`` subdirectories, lexicographically sorted by name."""
    return sorted(
        (p for p in raw_slug_dir.glob(_PERSONA_GLOB) if p.is_dir()),
        key=lambda p: p.name,
    )


def _clean_persona_dirs(raw_slug_dir: Path, clean_ids: set[str]) -> list[Path]:
    """Return this combo's persona dirs whose name is in ``clean_ids``, sorted by name."""
    return [p for p in _sorted_persona_dirs(raw_slug_dir) if p.name in clean_ids]


def _write_capped_mapped(
    mapped_src_file: Path,
    selected_ids: set[str],
    seed: int,
    dest_file: Path,
) -> int:
    """Filter ``mapped_src_file`` individuals to ``selected_ids`` and write ``dest_file``.

    Returns the number of individuals written. When the source mapped file is absent
    (mapping produced none for this combo), writes an empty mapped population and returns 0.
    """
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    if not mapped_src_file.is_file():
        payload: dict[str, Any] = {
            "metadata": {"source": "population_cap", "n": 0, "cap_seed": seed},
            "individuals": [],
        }
        with open(dest_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return 0

    with open(mapped_src_file, "r", encoding="utf-8") as f:
        mapped = json.load(f)

    individuals = [ind for ind in mapped.get("individuals", []) if ind.get("id") in selected_ids]
    metadata = dict(mapped.get("metadata", {}))
    metadata["capped_from"] = metadata.get("n")
    metadata["n"] = len(individuals)
    metadata["cap_seed"] = seed

    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "individuals": individuals}, f, indent=2, ensure_ascii=False)
    return len(individuals)


def cap_combo(
    *,
    slug: str,
    country: str,
    raw_slug_dir: Path,
    mapping_dir: Path,
    validate_raw_csv: Path,
    validate_mapped_csv: Path,
    n: int,
    seed: int,
    dest_dir: Path,
    mapped_dest_dir: Path,
    force: bool = False,
) -> CapSummary:
    """Seeded-cap one combo's CLEAN personas into the capped persona mirror + mapped file.

    Args:
        slug: Combo slug (``{country}_{strategy}_{model}``).
        country: Country id (selects the ``real_{country}.json`` reference to copy).
        raw_slug_dir: The source ``01_Raw/{slug}/`` combo directory.
        mapping_dir: The full mapping output dir (``03_Analysis/mapping``); read-only.
        validate_raw_csv: This combo's ``validate_raw/{slug}.csv`` verdict.
        validate_mapped_csv: This combo's ``validate_mapped/{slug}.csv`` verdict.
        n: Target number of clean personas to retain (the cap). Must be positive.
        seed: Seed for the reproducible without-replacement draw.
        dest_dir: Destination capped persona-dir mirror (``population_cap/{slug}/``).
        mapped_dest_dir: Destination capped mapped dir (``population_cap/_mapped/``).
        force: When True, an existing ``dest_dir`` is removed and rewritten; else raises.

    Returns:
        A :class:`CapSummary`.

    Raises:
        ValueError: If ``n`` is not a positive integer.
        FileNotFoundError: If ``raw_slug_dir`` is missing, or a validity CSV is absent.
        FileExistsError: If ``dest_dir`` exists and ``force`` is False.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"cap_combo requires a positive integer n; got {n!r}.")

    raw_slug_dir = Path(raw_slug_dir)
    dest_dir = Path(dest_dir)
    mapped_dest_dir = Path(mapped_dest_dir)

    if not raw_slug_dir.is_dir():
        raise FileNotFoundError(f"Raw combo directory not found: {raw_slug_dir}")

    if dest_dir.exists():
        if not force:
            raise FileExistsError(
                f"Capped mirror already exists for combo {slug!r}: {dest_dir} "
                f"(pass force=True to overwrite)."
            )
        rmtree_resilient(dest_dir)

    # --- Intersect the two validity gates to the clean persona ids.
    raw_passed = read_passed_ids(validate_raw_csv)
    mapped_passed = read_passed_ids(validate_mapped_csv)
    clean_ids = raw_passed & mapped_passed

    clean_dirs = _clean_persona_dirs(raw_slug_dir, clean_ids)
    clean_available = len(clean_dirs)

    if clean_available == 0:
        logger.warning(
            "population_cap: combo %r has 0 personas passing BOTH validity gates "
            "(raw_passed=%d, mapped_passed=%d); writing empty capped outputs.",
            slug,
            len(raw_passed),
            len(mapped_passed),
        )

    truncated = clean_available > n
    if clean_available < n:
        logger.warning(
            "population_cap: combo %r has only %d clean persona(s) (pass BOTH gates), "
            "fewer than the requested n=%d; capping to %d -- a VISIBLE clean shortfall.",
            slug,
            clean_available,
            n,
            clean_available,
        )

    selected_idx = select_indices(clean_available, n, seed)
    selected_dirs = [clean_dirs[i] for i in selected_idx]
    selected_ids = {d.name for d in selected_dirs}

    # --- 1) Capped persona-dir mirror (telemetry for generation_metadata).
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

    # The synced source pool marks dehydrated (OneDrive placeholder) entries read-only and
    # ``copytree``/``copy2`` carry that mode over, which would leave THIS mirror undeletable
    # on the next --force run. Clear it on what we just wrote.
    clear_readonly_tree(dest_dir)

    # --- 2) Capped mapped file + copied real reference (for the mapped-file consumers).
    synthetic_name = f"{slug}.json"
    mapped_n = _write_capped_mapped(
        mapping_dir / synthetic_name, selected_ids, seed, mapped_dest_dir / synthetic_name
    )

    real_name: str | None = f"real_{country}.json"
    real_src = mapping_dir / real_name
    if real_src.is_file():
        mapped_dest_dir.mkdir(parents=True, exist_ok=True)
        real_dest = mapped_dest_dir / real_name
        shutil.copy2(real_src, real_dest)
        # Same reason as the mirror above -- a read-only copy would make the NEXT run's
        # ``copy2`` onto it fail with WinError 5 before it ever reached the rmtree.
        clear_readonly_tree(real_dest)
    else:
        logger.warning(
            "population_cap: real reference %s not found under %s; the capped mapped dir "
            "will lack it until mapping emits the real population.",
            real_name,
            mapping_dir,
        )
        real_name = None

    return CapSummary(
        slug=slug,
        country=country,
        requested_n=n,
        raw_passed=len(raw_passed),
        mapped_passed=len(mapped_passed),
        clean_available=clean_available,
        selected=len(selected_dirs),
        seed=seed,
        selected_ids=[d.name for d in selected_dirs],
        truncated=truncated,
        synthetic_file=synthetic_name if mapped_n > 0 else None,
        real_file=real_name,
        mapped_n=mapped_n,
    )

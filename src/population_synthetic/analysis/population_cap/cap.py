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

Reaching ``n`` is a **precondition**, not an aspiration. A combination holding fewer than
``n`` clean personas is *excluded*: :func:`withdraw_combo` removes its capped mirror and
its capped mapped file if an earlier run left them behind, and :func:`cap_combo` returns a
summary carrying ``excluded=True`` and no output paths. The absent ``_mapped/{slug}.json``
is what makes every mapped-file consumer skip it, through the skip predicate they already
honour -- so a thin combination can never enter a fidelity score, a ranking or a
significance test as an equal competitor. The rule is evaluated before the mirror/``force``
check, so neither a library caller nor a pre-existing mirror can bypass it, and it is
re-evaluated on every invocation, so an output base populated under the old
cap-to-whatever-exists behaviour is cleaned without ``force``.

The threshold is strict and has no escape hatch: no tolerance band, no config knob, no
override parameter -- ``clean_available >= n`` or nothing, the boundary inclusive. The
exclusion is a *verdict*, not an error: it is logged at WARNING with both gate counts, it
travels on the returned summary for the caller to record in its indexes, and it does not
fail the batch. The source directories and the ``mapping/`` output are never mutated, so a
withdrawal destroys nothing that a later ``force`` re-run cannot rematerialize identically.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

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
    excluded: bool
    exclusion_reason: str | None


class CleanSelection(NamedTuple):
    """The full-N rule's input: this combo's two gate counts and its clean persona dirs.

    Typed rather than a loose tuple because two independent callers decide on it -- the
    per-combo cap itself and the CLI's re-run path -- and they must not be able to disagree
    about how many clean personas a combination has. ``dirs`` is already the intersection
    that matters: an id passing both validity CSVs *and* present as a directory under
    ``01_Raw/{slug}/``. The two raw counts are carried alongside for the exclusion message
    and the stage index, never for the threshold.

    Attributes:
        raw_passed: Number of ids passing the raw-completeness gate.
        mapped_passed: Number of ids passing the mapped-value gate.
        dirs: The persona directories passing both gates, lexicographically sorted.
    """

    raw_passed: int
    mapped_passed: int
    dirs: list[Path]

    @property
    def clean_available(self) -> int:
        """Number of countable clean personas -- the quantity the full-N rule tests."""
        return len(self.dirs)


def _sorted_persona_dirs(raw_slug_dir: Path) -> list[Path]:
    """Return the combo's ``persona_*`` subdirectories, lexicographically sorted by name."""
    return sorted(
        (p for p in raw_slug_dir.glob(_PERSONA_GLOB) if p.is_dir()),
        key=lambda p: p.name,
    )


def _clean_persona_dirs(raw_slug_dir: Path, clean_ids: set[str]) -> list[Path]:
    """Return this combo's persona dirs whose name is in ``clean_ids``, sorted by name."""
    return [p for p in _sorted_persona_dirs(raw_slug_dir) if p.name in clean_ids]


def clean_selection(
    raw_slug_dir: Path, validate_raw_csv: Path, validate_mapped_csv: Path
) -> CleanSelection:
    """Intersect the two validity gates with what is on disk into a :class:`CleanSelection`.

    A persona is countable only when its id passes BOTH gates *and* it exists as a
    directory under ``raw_slug_dir``: a passing id with no directory is not a persona this
    stage can copy, so it must not count towards the full-N threshold.

    Args:
        raw_slug_dir: The source ``01_Raw/{slug}/`` combo directory.
        validate_raw_csv: This combo's ``validate_raw/{slug}.csv`` verdict.
        validate_mapped_csv: This combo's ``validate_mapped/{slug}.csv`` verdict.

    Returns:
        A :class:`CleanSelection`.

    Raises:
        FileNotFoundError: If either validity CSV is absent. A missing gate verdict means
            the gate has not run for this combo -- it is never read as "short".
    """
    raw_passed = read_passed_ids(validate_raw_csv)
    mapped_passed = read_passed_ids(validate_mapped_csv)
    clean_ids = raw_passed & mapped_passed
    return CleanSelection(
        raw_passed=len(raw_passed),
        mapped_passed=len(mapped_passed),
        dirs=_clean_persona_dirs(Path(raw_slug_dir), clean_ids),
    )


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


def withdraw_combo(
    *,
    slug: str,
    country: str,
    clean: CleanSelection,
    n: int,
    seed: int,
    dest_dir: Path,
    mapped_dest_dir: Path,
) -> CapSummary:
    """Ensure an excluded combo has no capped outputs, and return its excluded summary.

    Withdrawal is the physical half of the exclusion verdict: the capped persona mirror and
    the capped mapped file are removed if present, so the combination reads as absent to
    every downstream consumer instead of as a thin competitor. It is deliberately
    idempotent -- absent artifacts are a no-op, never a raise -- because the rule is
    re-evaluated on every invocation, including runs where nothing was ever written and
    runs cleaning up an output base capped under the old behaviour.

    The copied real reference ``real_{country}.json`` is *not* touched: it is shared by
    every combo of that country, so withdrawing one must not disturb its siblings.

    Args:
        slug: Combo slug (``{country}_{strategy}_{model}``).
        country: Country id, carried through onto the summary.
        clean: The selection the full-N rule was evaluated on.
        n: The requested cap this combination failed to reach.
        seed: The seed of the draw that will not be made, carried for the record.
        dest_dir: The capped persona-dir mirror to withdraw (``population_cap/{slug}/``).
        mapped_dest_dir: The capped mapped dir holding a possibly stale ``{slug}.json``.

    Returns:
        A :class:`CapSummary` with ``excluded=True`` and no output files.
    """
    dest_dir = Path(dest_dir)
    mapped_dest_dir = Path(mapped_dest_dir)

    reason = (
        f"only {clean.clean_available} clean persona(s) pass both validity gates "
        f"(raw_passed={clean.raw_passed}, mapped_passed={clean.mapped_passed}), "
        f"fewer than the requested n={n}"
    )
    logger.warning(
        "population_cap: combo %r EXCLUDED -- %s. Withdrawing its capped outputs; every "
        "downstream analysis will skip this combination.",
        slug,
        reason,
    )

    if dest_dir.exists():
        rmtree_resilient(dest_dir)

    stale_mapped = mapped_dest_dir / f"{slug}.json"
    if stale_mapped.exists():
        # A file copied out of the synced pool can carry the read-only bit, which makes
        # ``unlink`` fail with WinError 5; clear it first (same reason as the mirror).
        clear_readonly_tree(stale_mapped)
        stale_mapped.unlink()

    return CapSummary(
        slug=slug,
        country=country,
        requested_n=n,
        raw_passed=clean.raw_passed,
        mapped_passed=clean.mapped_passed,
        clean_available=clean.clean_available,
        selected=0,
        seed=seed,
        selected_ids=[],
        truncated=False,
        synthetic_file=None,
        real_file=None,
        mapped_n=0,
        excluded=True,
        exclusion_reason=reason,
    )


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

    Enforces the full-N rule first: a combination with fewer than ``n`` clean personas is
    excluded via :func:`withdraw_combo` and returns immediately, before the mirror/``force``
    check, so no caller can bypass the rule and no pre-existing mirror can shield a stale
    short population. ``force`` gates only the expensive re-copy of a combination that has
    already passed the rule -- ``dest_dir.exists()`` means a cap ran, not that a valid one
    did.

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
        A :class:`CapSummary`, either the excluded one from :func:`withdraw_combo` or the
        full-N one describing the outputs just written.

    Raises:
        ValueError: If ``n`` is not a positive integer.
        FileNotFoundError: If ``raw_slug_dir`` is missing, or a validity CSV is absent.
        FileExistsError: If the combination is full-N, ``dest_dir`` exists and ``force`` is
            False. An excluded combination returns before this check.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"cap_combo requires a positive integer n; got {n!r}.")

    raw_slug_dir = Path(raw_slug_dir)
    dest_dir = Path(dest_dir)
    mapped_dest_dir = Path(mapped_dest_dir)

    if not raw_slug_dir.is_dir():
        raise FileNotFoundError(f"Raw combo directory not found: {raw_slug_dir}")

    # --- The full-N rule, evaluated before anything is read or written. Zero clean
    # personas is not a special case: it is the same rule at its extreme.
    clean = clean_selection(raw_slug_dir, validate_raw_csv, validate_mapped_csv)
    clean_available = clean.clean_available
    if clean_available < n:
        return withdraw_combo(
            slug=slug,
            country=country,
            clean=clean,
            n=n,
            seed=seed,
            dest_dir=dest_dir,
            mapped_dest_dir=mapped_dest_dir,
        )

    if dest_dir.exists():
        if not force:
            raise FileExistsError(
                f"Capped mirror already exists for combo {slug!r}: {dest_dir} "
                f"(pass force=True to overwrite)."
            )
        rmtree_resilient(dest_dir)

    truncated = clean_available > n

    selected_idx = select_indices(clean_available, n, seed)
    selected_dirs = [clean.dirs[i] for i in selected_idx]
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
        raw_passed=clean.raw_passed,
        mapped_passed=clean.mapped_passed,
        clean_available=clean_available,
        selected=len(selected_dirs),
        seed=seed,
        selected_ids=[d.name for d in selected_dirs],
        truncated=truncated,
        synthetic_file=synthetic_name if mapped_n > 0 else None,
        real_file=real_name,
        mapped_n=mapped_n,
        excluded=False,
        exclusion_reason=None,
    )

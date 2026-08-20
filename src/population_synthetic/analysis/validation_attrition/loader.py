"""loader.py -- read the validation gate's three persisted records into one typed set.

The gate writes its counts in three places, none of which references the others:

* ``population_cap/_index.json`` -- one ``CapSummary`` per combination, carrying the
  generated pool (``raw_total``), both gate counts, the clean pool and the draw;
* ``validate_raw/_summary.csv`` -- one row per combination, ``n_personas`` / ``passed``;
* ``validate_mapped/_summary.csv`` -- the same two counts for the mapped gate.

This module welds them. It reads only that published contract and never reaches into
either validator's per-persona CSVs or into the cap's selection logic, so the gate's
three halves can change freely as long as those three files keep their shape.

**The completeness gate.** A combination is *consumable* only when it appears in all
three files **and** their counts agree. The two failure modes are treated differently
on purpose, following ``realism_ranking/loader.py``:

* **Absent** from one of the two validator roll-ups is a pipeline-progress state --
  the roll-ups are upserted one combination per invocation, so a partially-run gate
  legitimately has rows missing. Skipped with a machine-readable reason, or raised
  under ``strict``.
* **Disagreeing** counts always raise, naming both files and the command that
  regenerates them. A disagreement means the gate's two halves observed different data,
  which is exactly what ``raw_total`` was added to make visible: ``raw_passed`` is read
  *out of* ``validate_raw``'s own output, so ``raw_passed == passed`` is a tautology
  and can never detect a raw pool that grew or shrank after validation ran.
  ``raw_total`` is the only independent observation, and ``raw_total != n_personas`` is
  the drift signal. Note the comparison is against ``n_personas``, **not** against
  ``raw_passed``: a combination whose pool legitimately fails the raw gate has
  ``raw_total > raw_passed`` and is perfectly healthy.

``raw_total`` is **required**, never defaulted from ``validate_raw``'s count: an index
predating it raises and names the re-run, matching the house read-boundary style
(``capped_source.py``, ``cap_index.py`` -- every raise names the offending path *and*
the task that fixes it). Silently substituting the validator's count would reinstate
the tautology this whole field exists to break.

The module knows nothing about matplotlib, figure layout, dpi, or how any rate is
derived. It resolves paths through the registry, reads three files, and types integers.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.cap_index import INDEX_FILENAME
from population_synthetic.analysis.utils.capped_source import resolve_stage_source
from population_synthetic.analysis.utils.registry import analysis_output_dir, get_process
from population_synthetic.analysis.utils.tidy_csv import missing_columns
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

__all__ = [
    "MAPPED_SUMMARY_PROCESS_ID",
    "RAW_SUMMARY_PROCESS_ID",
    "SUMMARY_FILENAME",
    "AttritionRecord",
    "AttritionSources",
    "load_attrition_records",
    "resolve_sources",
]

#: The registered process ids whose folders hold the two validator roll-ups. Named
#: rather than inlined so the folder names stay the registry's business, not this
#: module's (project invariant: no path literals for analysis output folders).
RAW_SUMMARY_PROCESS_ID = "validate_raw"
MAPPED_SUMMARY_PROCESS_ID = "validate_mapped"

#: Filename of the folder-level roll-up both validators upsert into. Written by
#: ``scripts/analyze/validate_{raw,mapped}_personas.py``; the header it carries is
#: declared as ``SUMMARY_HEADER`` in each validator's ``validate.py``.
SUMMARY_FILENAME = "_summary.csv"

#: The three roll-up columns this module reads. A subset check, not an equality check:
#: ``validate_raw`` carries two more columns than ``validate_mapped`` and both are fine.
SLUG_COLUMN = "slug"
N_PERSONAS_COLUMN = "n_personas"
PASSED_COLUMN = "passed"
_REQUIRED_SUMMARY_COLUMNS = (SLUG_COLUMN, N_PERSONAS_COLUMN, PASSED_COLUMN)

#: ``CapSummary`` keys read here, and their required Python types. ``raw_total`` is
#: listed with the rest rather than treated as optional -- see the module docstring.
_REQUIRED_INT_KEYS = (
    "requested_n", "raw_total", "raw_passed", "mapped_passed", "clean_available", "selected",
)
_REQUIRED_BOOL_KEYS = ("truncated", "excluded")

#: The key whose absence means the index predates Phase 1 of this feature, reported
#: with its own message because the fix is a gate re-run rather than a schema bump.
_RAW_TOTAL_KEY = "raw_total"


@dataclass(frozen=True)
class AttritionSources:
    """The three files one country's attrition is read from, for provenance and errors.

    Carried as a value rather than recomputed by each caller so the paths named in an
    error message, the paths recorded in the JSON document, and the paths actually read
    are provably the same three.
    """

    cap_index: Path
    validate_raw_summary: Path
    validate_mapped_summary: Path


@dataclass(frozen=True)
class AttritionRecord:
    """One combination's gate counts, as the three files jointly report them.

    Counts only: every quantity here was read, none was derived. The two rates are the
    builder's job, so a reader of this record can never confuse a measurement with a
    quotient.

    ``generated`` is ``CapSummary.raw_total`` -- the pool as the cap observed it on
    disk. ``raw_valid`` and ``mapped_valid`` are the two gates' pass counts, ``clean``
    the personas passing both, ``selected`` what the cap drew (zero whenever
    ``excluded``).

    ``had_surplus`` is ``CapSummary.truncated`` renamed at the boundary, once, so the
    false friend cannot travel further: it means ``clean > requested_n``, a surplus cut
    down -- never a shortfall.
    """

    slug: str
    country: str
    model: str
    strategy: str
    requested_n: int
    generated: int
    raw_valid: int
    mapped_valid: int
    clean: int
    selected: int
    excluded: bool
    exclusion_reason: str
    had_surplus: bool


def resolve_sources(output_base: str | Path) -> AttritionSources:
    """Resolve the three input paths under *output_base* (no reading, no existence check).

    Raises ``FileNotFoundError`` only for the ``population_cap`` stage directory, whose
    resolver checks it -- an absent gate stage means nothing here can be read at all.
    """
    output_base = Path(output_base)
    return AttritionSources(
        cap_index=resolve_stage_source(output_base) / INDEX_FILENAME,
        validate_raw_summary=(
            analysis_output_dir(RAW_SUMMARY_PROCESS_ID, output_base, for_read=True) / SUMMARY_FILENAME
        ),
        validate_mapped_summary=(
            analysis_output_dir(MAPPED_SUMMARY_PROCESS_ID, output_base, for_read=True) / SUMMARY_FILENAME
        ),
    )


def _script(process_id: str) -> str:
    """The registered script that regenerates *process_id*'s output (never a literal)."""
    return get_process(process_id).script


def _read_summary(path: Path, *, process_id: str) -> dict[str, tuple[int, int]]:
    """Read one validator roll-up into ``{slug: (n_personas, passed)}`` (fail-fast).

    Raises when the file is absent, lacks one of the three columns it is read for, a
    count will not parse as an integer, or a slug appears twice -- the roll-up is
    upserted by slug, so a duplicate makes that combination's counts ambiguous.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Validator summary not found: {path}. It is the folder-level roll-up "
            f"{process_id} upserts one row per combination into; run {_script(process_id)} "
            "for this output base before analysing attrition."
        )
    counts: dict[str, tuple[int, int]] = {}
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, _REQUIRED_SUMMARY_COLUMNS)
        if missing:
            raise ValueError(
                f"{path}: {process_id} summary is missing required column(s) {missing}; "
                f"header is {list(header)}. Re-run {_script(process_id)} to rewrite it."
            )
        for position, record in enumerate(reader):
            slug = (record.get(SLUG_COLUMN) or "").strip()
            if not slug:
                raise ValueError(
                    f"{path}: row {position} carries no {SLUG_COLUMN!r}. Re-run "
                    f"{_script(process_id)} to rewrite the summary."
                )
            if slug in counts:
                raise ValueError(
                    f"{path}: slug {slug!r} appears twice. The summary is upserted by slug, "
                    f"so a duplicate makes that combination's counts ambiguous; delete the "
                    f"file and re-run {_script(process_id)} for every combination."
                )
            parsed = []
            for column in (N_PERSONAS_COLUMN, PASSED_COLUMN):
                raw = record[column]
                try:
                    parsed.append(int(raw))
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path}: combination {slug!r} column {column!r} is {raw!r}, which is "
                        f"not an integer count. Re-run {_script(process_id)} to rewrite it."
                    ) from exc
            counts[slug] = (parsed[0], parsed[1])
    return counts


def _read_cap_index(path: Path) -> list[dict[str, Any]]:
    """Read ``population_cap/_index.json`` as a list of records (fail-fast)."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Population-cap index not found: {path}. It is the gate's own per-combination "
            f"record and the row grain of the attrition artifact; run "
            f"{_script('population_cap')} for this output base first."
        )
    with open(path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        raise ValueError(
            f"Population-cap index must be a JSON list of per-combination records, got "
            f"{type(entries).__name__}: {path}"
        )
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Population-cap index record {position} must be a JSON object, got "
                f"{type(entry).__name__}: {path}"
            )
    return entries


def _require_int(entry: Mapping[str, Any], key: str, *, slug: str, path: Path) -> int:
    value = entry.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"{path}: combination {slug!r} must carry a non-negative integer {key!r}, got "
            f"{value!r}. Re-run {_script('population_cap')} for this combination."
        )
    return value


def _require_bool(entry: Mapping[str, Any], key: str, *, slug: str, path: Path) -> bool:
    value = entry.get(key)
    if not isinstance(value, bool):
        raise ValueError(
            f"{path}: combination {slug!r} must carry a boolean {key!r}, got {value!r}. "
            f"Re-run {_script('population_cap')} for this combination."
        )
    return value


def _require_raw_total(entry: Mapping[str, Any], *, slug: str, path: Path) -> None:
    """Raise the dedicated "this index predates ``raw_total``" error, naming the re-run.

    Separated from :func:`_require_int` because the remedy differs in kind: a malformed
    value is corruption, whereas an absent key means the index was written before the
    field existed and is fixed by re-running the gate -- which is safe, seeded, and
    changes nothing else.
    """
    if _RAW_TOTAL_KEY in entry:
        return
    raise ValueError(
        f"{path}: combination {slug!r} carries no {_RAW_TOTAL_KEY!r}. It is the generated "
        f"pool as the cap observed it on disk, and the only independent observation of that "
        f"pool -- 'raw_passed' is read out of validate_raw's own output, so it agrees with "
        f"that validator by construction. It is never defaulted from the validator's count. "
        f"The index predates the field: re-run the gate to backfill it with "
        f"`{_script('population_cap')} --force` (the draw is seeded, so the selected personas "
        f"do not change)."
    )


def _assert_counts_agree(
    entry: Mapping[str, Any],
    *,
    slug: str,
    raw_counts: tuple[int, int],
    mapped_counts: tuple[int, int],
    sources: AttritionSources,
) -> None:
    """Raise unless the cap's record and both validator roll-ups report the same counts.

    Three comparisons, each against the file that independently measured the quantity:

    * ``raw_total`` vs ``validate_raw``'s ``n_personas`` -- the **drift** check. These
      are two independent observations of the same pool (one globbed at cap time, one
      counted at validation time), so a disagreement means the gate's halves read
      different data. It is deliberately *not* compared against ``raw_passed``, which
      is legitimately smaller whenever personas fail the raw gate.
    * ``raw_passed`` vs ``validate_raw``'s ``passed`` and ``mapped_passed`` vs
      ``validate_mapped``'s ``passed`` -- consistency checks on the transcription. They
      are tautological while the index is fresh, and stop being so the moment either
      validator is re-run without re-running the cap.
    """
    raw_n, raw_passed = raw_counts
    _, mapped_passed = mapped_counts
    disagreements = [
        (_RAW_TOTAL_KEY, entry[_RAW_TOTAL_KEY], N_PERSONAS_COLUMN, raw_n, sources.validate_raw_summary),
        ("raw_passed", entry["raw_passed"], PASSED_COLUMN, raw_passed, sources.validate_raw_summary),
        ("mapped_passed", entry["mapped_passed"], PASSED_COLUMN, mapped_passed, sources.validate_mapped_summary),
    ]
    mismatched = [item for item in disagreements if item[1] != item[3]]
    if not mismatched:
        return
    detail = "; ".join(
        f"{cap_key}={cap_value} in {sources.cap_index} but {csv_key}={csv_value} in {csv_path}"
        for cap_key, cap_value, csv_key, csv_value, csv_path in mismatched
    )
    raise ValueError(
        f"Combination {slug!r} is reported inconsistently by the validation gate: {detail}. "
        f"The gate's halves observed different data -- one of them ran against a pool the "
        f"other did not see -- so every attrition count for this combination would be a "
        f"numerator and a denominator from different states of the disk. Re-run the gate in "
        f"order for this combination: {_script(RAW_SUMMARY_PROCESS_ID)}, "
        f"{_script('mapping')}, {_script(MAPPED_SUMMARY_PROCESS_ID)}, then "
        f"`{_script('population_cap')} --force`."
    )


def _axis_registries(
    axis_ids: tuple[list[str], list[str], list[str]] | None,
) -> tuple[list[str], list[str], list[str]]:
    """The (country, strategy, model) id registries the slug is decomposed against.

    Injectable so tests need not depend on the repository's live axis config; ``None``
    reads the config, which is the single source of truth for what an axis id is.
    """
    if axis_ids is not None:
        return axis_ids
    return (
        sorted(d["id"] for d in discover_axis_values("countries")),
        sorted(d["id"] for d in discover_axis_values("strategies")),
        sorted(d["id"] for d in discover_axis_values("models")),
    )


def load_attrition_records(
    output_base: str | Path,
    *,
    countries: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    strategies: Sequence[str] | None = None,
    slugs: Sequence[str] | None = None,
    strict: bool = False,
    axis_ids: tuple[list[str], list[str], list[str]] | None = None,
) -> tuple[list[AttritionRecord], list[tuple[str, str]]]:
    """Load every consumable combination's gate counts under *output_base*.

    The walk is driven by ``population_cap/_index.json``, so the row grain is every
    combination the gate recorded -- **including the ones it withdrew**. A withdrawn
    combination is a record like any other, carrying ``excluded=True``, its reason, and
    ``selected=0``; it is never skipped, because reporting it is the whole point.

    Args:
        output_base: The run's output base (the parent of ``03_Analysis/``).
        countries / models / strategies / slugs: Optional selection filters, applied
            after the slug is decomposed. Filtering is selection, not a verdict: a
            filtered-out combination is neither a record nor a skip.
        strict: Raise on a combination that is missing from one of the two validator
            roll-ups instead of skipping it.
        axis_ids: Optional ``(country_ids, strategy_ids, model_ids)`` override for the
            slug decomposition; ``None`` reads the axis config.

    Returns:
        ``(records, skipped)`` -- the consumable records in ``_index.json`` order, and
        ``(slug, reason)`` pairs for the combinations that could not be consumed.

    Raises:
        FileNotFoundError: If the cap stage, the cap index, or either validator roll-up
            is absent.
        ValueError: If the index is malformed, a record lacks ``raw_total`` or a typed
            count, a roll-up is malformed, the counts disagree across the three files,
            or -- under *strict* -- a combination is missing from a roll-up.
    """
    sources = resolve_sources(output_base)
    entries = _read_cap_index(sources.cap_index)
    raw_summary = _read_summary(sources.validate_raw_summary, process_id=RAW_SUMMARY_PROCESS_ID)
    mapped_summary = _read_summary(sources.validate_mapped_summary, process_id=MAPPED_SUMMARY_PROCESS_ID)
    country_ids, strategy_ids, model_ids = _axis_registries(axis_ids)

    records: list[AttritionRecord] = []
    skipped: list[tuple[str, str]] = []

    for position, entry in enumerate(entries):
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError(
                f"{sources.cap_index}: record {position} must carry a non-empty string "
                f"'slug', got {slug!r}."
            )
        if slugs is not None and slug not in slugs:
            continue

        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            skipped.append((slug, diagnose_slug(slug, country_ids, strategy_ids, model_ids)))
            continue
        country, strategy, model = decomposed
        if countries is not None and country not in countries:
            continue
        if models is not None and model not in models:
            continue
        if strategies is not None and strategy not in strategies:
            continue

        _require_raw_total(entry, slug=slug, path=sources.cap_index)
        counts = {
            key: _require_int(entry, key, slug=slug, path=sources.cap_index)
            for key in _REQUIRED_INT_KEYS
        }
        flags = {
            key: _require_bool(entry, key, slug=slug, path=sources.cap_index)
            for key in _REQUIRED_BOOL_KEYS
        }

        missing_from = [
            str(path)
            for present, path in (
                (slug in raw_summary, sources.validate_raw_summary),
                (slug in mapped_summary, sources.validate_mapped_summary),
            )
            if not present
        ]
        if missing_from:
            reason = (
                f"no row in {', '.join(missing_from)} -- the validator roll-up is upserted "
                f"one combination per invocation, so this combination has not been validated "
                f"at that stage for this output base"
            )
            if strict:
                raise ValueError(f"Combination {slug!r}: {reason}.")
            skipped.append((slug, reason))
            continue

        _assert_counts_agree(
            entry,
            slug=slug,
            raw_counts=raw_summary[slug],
            mapped_counts=mapped_summary[slug],
            sources=sources,
        )

        reason = entry.get("exclusion_reason")
        records.append(
            AttritionRecord(
                slug=slug,
                country=country,
                model=model,
                strategy=strategy,
                requested_n=counts["requested_n"],
                generated=counts[_RAW_TOTAL_KEY],
                raw_valid=counts["raw_passed"],
                mapped_valid=counts["mapped_passed"],
                clean=counts["clean_available"],
                selected=counts["selected"],
                excluded=flags["excluded"],
                # Empty rather than None: the CSV column is text, and ``excluded`` is
                # the authoritative flag -- an empty reason never means "not excluded".
                exclusion_reason=str(reason) if reason else "",
                had_surplus=flags["truncated"],
            )
        )

    return records, skipped

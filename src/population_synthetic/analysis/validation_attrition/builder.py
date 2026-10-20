"""builder.py -- derive the attrition rates and assemble the artifacts. Pure.

Everything this module produces is arithmetic over the counts
:mod:`~population_synthetic.analysis.validation_attrition.loader` read: no file is
opened, no path is resolved, no figure is drawn. It is the single place either rate is
computed, so the charts *read* both rather than recomputing them (guide 02 sect. 9 --
visualization is a pure sink) and the CSV and the figure can never disagree.

**The two rates, and why they are denominated the way they are.**

``retention_rate = clean / raw_valid``
    The share of the **finished** pool that survives *both* validity gates. Undefined --
    ``None``, an empty cell -- when no persona finished.

``generation_multiplier = raw_valid / clean``
    Finished personas per *usable* persona. Deliberately **not**
    ``raw_valid / selected``: ``selected`` is zero for every combination the full-N
    rule withdrew, so that denominator is undefined precisely on the seven
    ``swedish_02`` combinations whose waste the artifact exists to show. Denominating
    on ``clean`` keeps the number computable exactly where it matters most, and it
    answers the question an operator actually asks -- how many personas must I generate
    to obtain one I can use -- rather than a question about the cap's ceiling.

**Why ``raw_valid`` and not ``generated``.** A persona that fails the raw-completeness
gate is, on this pipeline, a generation stopped midway (only ``identity.partial.json`` on
disk): an artefact of interrupting the run, not an outcome of the model or the method.
Counting it would charge a combination for when its run happened to be stopped. So no
rate divides by ``generated``; the count is still published, beside ``raw_valid``, so the
unfinished personas stay visible.

Both are reciprocals on the same pair of counts, and both are published, because they
are read in opposite directions: the rate is what a survival figure plots, the
multiplier is what a cost figure multiplies by. Neither is ever ``0.0`` or infinite
when undefined; ``0.0`` retention is a real measurement (personas finished and none
survived) and must stay distinguishable from an absent one.

The pooled totals in the document are sums of persona counts, which are additive, so
the pooled rate is a legitimate count-weighted mean over the selected combinations --
not an average of per-combination rates, which would weight a 110-persona combination
equally with a 549-persona one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from population_synthetic.analysis.utils.attrition_csv import SCHEMA_VERSION, AttritionRow
from population_synthetic.analysis.validation_attrition.loader import (
    AttritionRecord,
    AttritionSources,
)

__all__ = [
    "PROCESS_ID",
    "build_document",
    "build_rows",
    "generation_multiplier",
    "retention_rate",
]

#: The canonical analysis-process id this builder's artifacts are stamped with.
PROCESS_ID = "validation_attrition"


def retention_rate(raw_valid: int, clean: int) -> float | None:
    """``clean / raw_valid``, or ``None`` when no persona finished.

    ``None`` and not ``0.0``: a zero retention rate says a finished pool was entirely
    discarded, which is a measurement. An empty pool supports no such claim.
    """
    if raw_valid == 0:
        return None
    return clean / raw_valid


def generation_multiplier(raw_valid: int, clean: int) -> float | None:
    """``raw_valid / clean`` -- finished personas per usable persona; ``None`` at ``clean == 0``.

    ``None`` and not infinity: a combination with no usable personas has *no* finite
    cost per usable persona, and writing ``inf`` would let it be plotted, sorted and
    averaged as though it did.
    """
    if clean == 0:
        return None
    return raw_valid / clean


def build_rows(records: Sequence[AttritionRecord]) -> list[AttritionRow]:
    """Build the tidy CSV rows for *records*, sorted by slug.

    Sorted rather than left in index order so two runs over the same gate records
    produce byte-identical files whatever order the index happens to hold.
    """
    rows = [
        AttritionRow(
            slug=record.slug,
            country=record.country,
            model=record.model,
            strategy=record.strategy,
            requested_n=record.requested_n,
            generated=record.generated,
            raw_valid=record.raw_valid,
            mapped_valid=record.mapped_valid,
            clean=record.clean,
            selected=record.selected,
            retention_rate=retention_rate(record.raw_valid, record.clean),
            generation_multiplier=generation_multiplier(record.raw_valid, record.clean),
            excluded=record.excluded,
            exclusion_reason=record.exclusion_reason,
            had_surplus=record.had_surplus,
        )
        for record in records
    ]
    return sorted(rows, key=lambda row: row.slug)


def _combination_entry(row: AttritionRow) -> dict[str, Any]:
    """One combination's JSON entry -- the same quantities the CSV row carries."""
    return {
        "slug": row.slug,
        "country": row.country,
        "model": row.model,
        "strategy": row.strategy,
        "requested_n": row.requested_n,
        "funnel": {
            "generated": row.generated,
            "raw_valid": row.raw_valid,
            "mapped_valid": row.mapped_valid,
            "clean": row.clean,
            "selected": row.selected,
        },
        "retention_rate": row.retention_rate,
        "generation_multiplier": row.generation_multiplier,
        "excluded": row.excluded,
        "exclusion_reason": row.exclusion_reason,
        "had_surplus": row.had_surplus,
    }


def _totals(rows: Sequence[AttritionRow]) -> dict[str, Any]:
    """Pooled funnel counts and the two rates over them (see the module docstring)."""
    raw_valid = sum(row.raw_valid for row in rows)
    clean = sum(row.clean for row in rows)
    return {
        "generated": sum(row.generated for row in rows),
        "raw_valid": raw_valid,
        "mapped_valid": sum(row.mapped_valid for row in rows),
        "clean": clean,
        "selected": sum(row.selected for row in rows),
        "retention_rate": retention_rate(raw_valid, clean),
        "generation_multiplier": generation_multiplier(raw_valid, clean),
    }


def build_document(
    records: Sequence[AttritionRecord],
    *,
    country: str,
    skipped: Sequence[tuple[str, str]],
    sources: AttritionSources,
) -> dict[str, Any]:
    """Assemble the JSON report for one country.

    Args:
        records: The consumable combinations, as the loader returned them.
        country: The country id the artifacts are written for.
        skipped: ``(slug, reason)`` pairs the loader could not consume, reported rather
            than dropped -- a combination absent from the document must be
            distinguishable from one that was never there (guide 03 sect. 6).
        sources: The three files the counts were read from, recorded verbatim so a
            reader of the JSON alone can retrace every number.

    Returns:
        A plain dict, carrying no timestamp: the caller stamps ``generated_at`` if it
        wants one, which keeps the builder's output byte-reproducible for a fixed input.
    """
    rows = build_rows(records)
    excluded = [row for row in rows if row.excluded]
    return {
        "process": PROCESS_ID,
        "country": country,
        "schema_version": SCHEMA_VERSION,
        "n_combinations": len(rows),
        "n_excluded": len(excluded),
        "definitions": {
            "generated": (
                "persona_* directories the cap observed under 01_Raw for this combination "
                "(CapSummary.raw_total) -- the only observation of the pool independent of "
                "either validator. Published for transparency only: it includes generations "
                "stopped midway, so no rate divides by it"
            ),
            "raw_valid": (
                "personas passing the raw-completeness gate -- the finished pool; a persona "
                "failing it is a generation stopped midway and is ignored by both rates"
            ),
            "mapped_valid": "personas passing the mapped-value gate",
            "clean": "personas passing BOTH gates -- the pool the seeded cap draws from",
            "selected": "personas the cap drew; zero for every excluded combination, by design",
            "retention_rate": "clean / raw_valid; null when raw_valid == 0, never 0.0",
            "generation_multiplier": (
                "raw_valid / clean -- finished personas per usable persona. Not "
                "raw_valid / selected, which is undefined for every withdrawn combination. "
                "Null when clean == 0, never infinite"
            ),
            "had_surplus": (
                "the cap's 'truncated' flag: clean > requested_n, i.e. a surplus was cut "
                "down. It is NOT a shortfall marker -- that is 'excluded'"
            ),
        },
        "totals": _totals(rows),
        "combinations": [_combination_entry(row) for row in rows],
        # Listed separately as well as flagged inline: this is the only artifact in the
        # analysis layer where a withdrawn combination appears at all, so it is worth
        # being readable without filtering the full table.
        "excluded_combinations": [
            {
                "slug": row.slug,
                "requested_n": row.requested_n,
                "generated": row.generated,
                "raw_valid": row.raw_valid,
                "clean": row.clean,
                "reason": row.exclusion_reason,
            }
            for row in excluded
        ],
        "skipped_combinations": [
            {"slug": slug, "reason": reason} for slug, reason in skipped
        ],
        "provenance": {
            "consumed_artifacts": [
                str(Path(sources.cap_index)),
                str(Path(sources.validate_raw_summary)),
                str(Path(sources.validate_mapped_summary)),
            ],
        },
    }

"""builder.py -- every cross-combination realism claim, as pure computation.

Takes the loader's :class:`~population_synthetic.analysis.realism_ranking.loader.CompetitorRecord`
list and produces the ranking document plus its flat CSV rows. It touches no path, no
figure, and no config file: paths belong to the CLI edge, rendering to ``charts.py``,
and config values arrive as arguments (config is the single source of truth, read
fail-fast by the caller).

The two axes are kept explicitly apart because their directions are opposite and
conflating them inverts the interpretation:

============  ==========================  =========================  ==================
Axis          Quantity                    Real population's role     Direction
============  ==========================  =========================  ==================
A: validity   impossibility rate          ordinary ranked competitor lower is better
B: coverage   typicality dispersion       the target to match        near zero is better
============  ==========================  =========================  ==================

On Axis A the real population is ranked like everything else, so the question "are
conditionally-chain-sampled personas themselves internally incoherent?" is *asked*
rather than assumed away. On Axis B it is the target: the observed LLM failure mode is
mode collapse, so matching the real spread is the goal and maximising it is not --
``distance_to_scb`` near zero is good, and a large distance is bad in either direction.

Statistical-honesty rules enforced throughout (guide 03):

* every rate carries its denominator, and the denominator is never used as a divisor
  when it is zero;
* every p-value is accompanied by an effect size and the name of the multiple-comparison
  correction applied to its family;
* a test that cannot be computed (a group below two samples, zero variance, a missing
  optional dependency, a non-convergent fit) is recorded in ``skipped_tests`` with a
  reason -- silence downstream reads as "this was tested and found null";
* the bootstrap uses one seeded local generator, and the seed is stamped in provenance;
* the pseudo-replication and one-run-per-combination confounds are emitted as
  machine-readable caveats, not left to prose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.realism_csv import (
    SEVERITY_COUNT_FIELDS,
    SEVERITY_LEVELS,
    SEVERITY_RANK,
)
from population_synthetic.analysis.utils.stats_tests import (
    bootstrap_ci,
    bootstrap_difference_ci,
    dunn_posthoc,
    holm_adjust,
    kruskal_test,
    summarize,
    two_proportion_test,
    variance_equality_test,
)

__all__ = [
    "CAVEATS",
    "CORRECTION",
    "DISPERSION_MEASURES",
    "DRIVER_COUNTING_UNIT",
    "DRIVER_NON_ADDITIVE",
    "PAIR_SUMMARY_COUNTING_UNIT",
    "SEVERITY_DIRECTIONS",
    "build_ranking",
    "summary_rows",
    "scb_contrast_rows",
    "severity_driver_rows",
    "severity_driver_value_rows",
    "severity_pair_summary",
]

#: The multiple-comparison correction applied to every family of tests here. Stated
#: explicitly in the output so a reader never has to infer it from the numbers.
CORRECTION = "holm"

#: The dispersion measures contrasted against the real population on Axis B, in a
#: fixed order (single source for the distance keys).
DISPERSION_MEASURES: tuple[str, ...] = ("variance", "entropy", "tail_coverage")

#: Confounds that survive this analysis and must travel with its numbers.
CAVEATS: tuple[dict[str, str], ...] = (
    {
        "id": "pseudo_replication",
        "text": (
            "Personas within one combination come from a single generation run and share "
            "its prompt, model state and sampling seed, so they are not independent draws "
            "from that combination's population. Treating them as independent narrows every "
            "interval and inflates every test statistic reported here; the p-values are "
            "therefore optimistic, and small differences between combinations should not be "
            "read as established."
        ),
    },
    {
        "id": "single_run_per_combination",
        "text": (
            "Each combination was generated exactly once, so run-level variance is "
            "completely confounded with the model x method cell. A difference attributed "
            "here to a model or a method could equally be one unusually good or bad run of "
            "that cell; separating them needs replicate generation runs, which this design "
            "does not have."
        ),
    },
)


@dataclass(frozen=True)
class _Skip:
    test: str
    reason: str


def _library_versions() -> dict[str, str | None]:
    """Resolved versions of every library whose output lands in this document."""
    versions: dict[str, str | None] = {}
    for name in ("numpy", "scipy", "statsmodels", "scikit_posthocs"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", None)
        except ImportError:
            versions[name] = None
    return versions


# --------------------------------------------------------------------------- #
# Axis A -- impossibility ranking (all competitors, the real one included)     #
# --------------------------------------------------------------------------- #


def _axis_a_ranking(
    records: Sequence[CompetitorRecord], *, bootstrap: dict[str, Any]
) -> list[dict[str, Any]]:
    """Rank every competitor by impossibility rate, with a seeded bootstrap CI.

    Ordering is by point rate ascending (lower is better) with the slug as a stable
    tie-break; ties are made explicit through equal ``rank`` values rather than being
    broken arbitrarily. A competitor with no successful persona has no rate and is
    ranked last with ``rate: None`` -- never with an imputed 0, which would read as
    perfect coherence.

    CI overlap is *displayed* by the charts, never asserted as a test: non-overlapping
    intervals imply a difference, but overlapping ones do not imply its absence.
    """
    entries: list[dict[str, Any]] = []
    for record in records:
        indicators = record.impossible_indicators
        ci = bootstrap_ci(
            list(indicators),
            iterations=bootstrap["iterations"],
            ci_level=bootstrap["ci_level"],
            seed=bootstrap["seed"],
        )
        entries.append({
            "slug": record.slug,
            "country": record.country,
            "model": record.model,
            "strategy": record.strategy,
            "is_real_reference": record.is_real_reference,
            "rate": ci["point"],
            "ci_lo": ci["lo"],
            "ci_hi": ci["hi"],
            "ci_level": ci["ci_level"],
            "impossible_count": int(sum(indicators)),
            # The denominator travels with the rate, always.
            "denominator": record.n_personas,
            "n_failed": record.n_failed,
        })

    entries.sort(key=lambda e: (e["rate"] is None, e["rate"] if e["rate"] is not None else 0.0,
                                e["slug"]))
    rank = 0
    previous: float | None = math.nan
    for position, entry in enumerate(entries, start=1):
        if entry["rate"] != previous:
            rank = position
            previous = entry["rate"]
        entry["rank"] = rank
    return entries


def _grid(
    entries: Sequence[dict[str, Any]],
    *,
    value_of: Callable[[dict[str, Any]], dict[str, Any] | None],
    note: str,
) -> dict[str, Any]:
    """Shape any per-competitor scalar into a model x method grid plus the real population.

    *entries* are per-competitor dicts carrying at least ``slug``, ``model``,
    ``strategy`` and ``is_real_reference``; *value_of* extracts the cell payload from
    one entry (``None`` when that competitor has no defined value). One reshape serves
    every heatmap the task emits, so the layout and the guards below cannot diverge
    between them.

    Three properties the shape is chosen to guarantee:

    * **An unjudged pair is ``None``, not ``0.0``.** Zero is a real measurement -- the
      best possible one for a defect rate -- so an absent cell rendered as zero would
      report a combination that was never judged as the cleanest in the sweep. The cell
      stays ``None`` here and the chart draws it as an explicit ``n/a``.
    * **The real population is not a grid cell.** It has no model and no method, so it
      has no coordinate; forcing it into a row would invent a factor level. It is carried
      separately under ``real`` and drawn as its own band -- the same reason the factor
      tests hold it out.
    * **Every value keeps its denominator**, so a cell is never read without the base it
      was computed over.
    * **The method axis is the complexity axis.** ``methods`` comes back ordered by
      :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`, not
      sorted, so every grid this task emits reads simplest-method-first like the rest of
      the analysis layer. The charts take their axis from this list verbatim, which is
      what keeps the JSON block and the figures from ordering the same grid differently.

    Raises ``ValueError`` if two combinations claim the same ``(model, method)`` cell, or
    if a synthetic competitor is missing either coordinate. Slugs are
    ``{country}_{strategy}_{model}`` and unique by construction, so either case means the
    consumption set is corrupt -- silently overwriting one with the other would publish a
    grid that omits a judged combination without saying so.
    """
    models: list[str] = []
    methods: list[str] = []
    cells: dict[str, dict[str, dict[str, Any] | None]] = {}
    placed: dict[tuple[str, str], str] = {}
    real: dict[str, Any] | None = None

    for entry in entries:
        if entry["is_real_reference"]:
            real = value_of(entry)
            continue
        model, method = entry["model"], entry["strategy"]
        if not model or not method:
            raise ValueError(
                f"Competitor {entry['slug']!r} is not the real population but is missing its "
                f"model/method coordinate (model={model!r}, strategy={method!r}); it cannot be "
                "placed on the model x method grid. The consumption set is corrupt -- re-run "
                "scripts/analyze/analyze_persona_realism.py for this combination."
            )
        if (model, method) in placed:
            raise ValueError(
                f"Two combinations claim the same grid cell (model={model!r}, method={method!r}): "
                f"{placed[(model, method)]!r} and {entry['slug']!r}. Slugs are unique by "
                "construction, so this means the consumption set holds a duplicate."
            )
        placed[(model, method)] = entry["slug"]
        if model not in models:
            models.append(model)
        if method not in methods:
            methods.append(method)
        cells.setdefault(model, {})[method] = value_of(entry)

    models.sort()
    # The method axis is ordered by pipeline complexity, simplest first -- the order
    # `_families.yaml` declares and every other analysis process publishes, so a heatmap
    # here can be read beside a fidelity or method-significance figure. Alphabetical is
    # not merely a different convention on this axis: every `all_generate_*` family sorts
    # ahead of `all_pick*`, so it very nearly *inverts* complexity and puts the most
    # elaborate method leftmost. An id the strategy-axis config does not know raises here
    # rather than sorting last, for the reason the resolver states: an axis that quietly
    # lost its order is indistinguishable from one that kept it.
    methods = strategy_complexity_order(methods)
    # Materialise the full rectangle so an unjudged pair is an explicit None rather than a
    # missing key a reader has to notice the absence of.
    full = {model: {method: cells.get(model, {}).get(method) for method in methods}
            for model in models}

    return {"models": models, "methods": methods, "cells": full, "real": real, "note": note}


_GRID_NOTE_SUFFIX = (
    " The real population is carried under 'real' rather than as a grid row: it has no "
    "model and no method, so it has no cell on this grid."
)


def _axis_a_grid(ranking: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Reshape the Axis A ranking into a model x method grid plus the real population.

    Built **from the ranking entries**, never recomputed, so the heatmap and the forest
    plot cannot drift apart: both render the same numbers from the same objects.
    """
    def _cell(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "slug": entry["slug"],
            "rate": entry["rate"],
            "ci_lo": entry["ci_lo"],
            "ci_hi": entry["ci_hi"],
            "denominator": entry["denominator"],
        }

    return _grid(
        ranking,
        value_of=_cell,
        note=(
            "A null cell means that model x method combination was not judged (or was not "
            "consumable) -- it is NOT an impossibility rate of zero, which would be the best "
            "possible result." + _GRID_NOTE_SUFFIX
        ),
    )


# --------------------------------------------------------------------------- #
# Severity dimension -- reporting only, one grid per level                     #
# --------------------------------------------------------------------------- #


#: What each severity level *means* and which way it reads. Defined once and consumed
#: by both severity blocks (the prevalence grids and the driver attribution), because
#: the two describe the same three levels: a direction stated in one place and not the
#: other is how S1 ends up read as a defect on one table and not on its sibling.
SEVERITY_DIRECTIONS: dict[str, dict[str, Any]] = {
    "S3": {
        "meaning": "hard biological / legal / temporal contradiction",
        "direction": "lower is better -- an S3 clash is a defect",
        "penalised": True,
    },
    "S2": {
        "meaning": "near-impossible attribute pairing",
        "direction": "lower is better -- an S2 clash is a defect",
        "penalised": True,
    },
    "S1": {
        "meaning": "unusual but possible",
        "direction": (
            "neither better nor worse -- S1 is reported and never penalised. A higher "
            "S1 rate plausibly indicates reach into the unusual-but-possible tail "
            "rather than a defect, so this level must not be read as a score."
        ),
        "penalised": False,
    },
}


def _grid_entries(records: Sequence[CompetitorRecord]) -> list[dict[str, Any]]:
    """The per-competitor adapter dicts :func:`_grid` places, with a record back-pointer.

    ``_grid`` reshapes *entries*, not records, so a block whose cell payload needs the
    whole record hands it through under ``_record``. Built once here so every
    record-backed grid places its competitors by exactly the same coordinates -- and so
    the real competitor is recognised by the same ``is_real_reference`` flag in each.
    """
    return [
        {
            "slug": r.slug, "model": r.model, "strategy": r.strategy,
            "is_real_reference": r.is_real_reference, "_record": r,
        }
        for r in records
    ]


def _affected_at(record: CompetitorRecord, level: str) -> int:
    """How many of *record*'s personas carry at least one clash at *level*.

    The numerator of the severity heatmap cell **and** the ``affected`` a driver
    attribution reports, computed once here so the two can never disagree: the drivers
    exist to explain this number, and explaining a different number would be worse than
    not explaining it at all.
    """
    field = SEVERITY_COUNT_FIELDS[level]
    return sum(1 for row in record.personas if getattr(row, field) > 0)


def _severity_grids(records: Sequence[CompetitorRecord]) -> dict[str, Any]:
    """Per-severity clash prevalence, one model x method grid per level.

    **Descriptive only.** Nothing here feeds the ranking, the contrasts or the factor
    tests: this is a separate dimension from the binary ``can_exist``, reported so the
    three severity levels can be inspected on their own, and it deliberately does not
    change any existing number. ``severity_weights`` / ``impossibility_severities`` in
    ``judge.yaml`` remain declared-but-unwired -- wiring them would move every
    impossibility rate already published.

    The metric per cell is **the share of that combination's personas exhibiting at
    least one clash at that level**, with its denominator. Prevalence, not a count of
    clashes: a persona with four S2 clashes is one persona with an S2 problem, and
    counting clashes instead would let a single richly-annotated persona dominate a
    combination's score.

    The levels are counted **independently**, not as a partition. A persona carrying
    both an S3 and an S2 appears in the S3 grid *and* the S2 grid, which is what makes
    the three readable on their own -- ``max_severity`` alone would file that persona
    under S3 and silently understate the S2 prevalence.

    Direction is **not** uniform across the three, and the block says so per level.
    S3 and S2 are defects, so lower is better. S1 is *unusual-but-possible*, which the
    judge's own contract reports and never penalises: a high S1 rate plausibly means
    healthy reach into the tails rather than a problem. Presenting it on a
    lower-is-better ramp would assert that unusual people are defects.
    """
    levels: dict[str, Any] = {}
    for level in SEVERITY_LEVELS:

        def _cell(entry: dict[str, Any], _level: str = level) -> dict[str, Any]:
            record: CompetitorRecord = entry["_record"]
            n = len(record.personas)
            affected = _affected_at(record, _level)
            return {
                "slug": record.slug,
                # Denominator 0 is never used as a divisor: no persona, no rate.
                "rate": (affected / n) if n else None,
                "affected": affected,
                "denominator": n,
            }

        levels[level] = {
            **SEVERITY_DIRECTIONS[level],
            "grid": _grid(
                _grid_entries(records),
                value_of=_cell,
                note=(
                    f"A null cell means that model x method combination was not judged -- it is "
                    f"NOT an {level} prevalence of zero." + _GRID_NOTE_SUFFIX
                ),
            ),
        }

    return {
        "levels": levels,
        "metric": "share of a combination's personas exhibiting >=1 clash at this severity",
        "independent_levels": (
            "The three levels are counted independently, not as a partition: a persona "
            "carrying both an S3 and an S2 clash is counted in both."
        ),
        "reporting_only": (
            "Descriptive. This dimension feeds no ranking, no contrast and no significance "
            "test, and does not affect the binary can_exist impossibility rate."
        ),
    }


# --------------------------------------------------------------------------- #
# Severity drivers -- WHAT clashed in each cell (reporting only)                #
# --------------------------------------------------------------------------- #


#: The unit every driver count is in. Carried as a data field on the block and on every
#: emitted row rather than only in a docstring: the tables travel without the code, and
#: a count whose unit has to be guessed is a count that gets misread as "clashes".
DRIVER_COUNTING_UNIT = (
    "personas, not clashes: a clash the judge raised in several rounds of one persona "
    "counts that persona once, and the denominator is the cell's persona count"
)

#: Why these numbers do not add up to the cell they explain. A data field for the same
#: reason: the failure mode is a reader summing them or drawing them as a whole.
DRIVER_NON_ADDITIVE = (
    "driver prevalences are not shares of a whole and do not sum to the cell's "
    "severity rate: one persona may carry several distinct clashes, each clash names "
    "two attributes, and the three severity levels are not a partition. Never render "
    "these as a pie or a 100%-stacked bar."
)

#: Appended to a per-cell driver note. Ranks are positional, so equal counts are
#: ordered by the declared tie-break rather than sharing a rank -- the equality is
#: visible in ``n_personas``, which is the number to read, not the rank.
_DRIVER_TIE_BREAK = (
    "ties on n_personas are broken by attribute name (then category value) so the rank "
    "order is deterministic; equal counts share no rank, so read n_personas, not rank"
)


def _clash_index(
    record: CompetitorRecord, level: str
) -> tuple[
    dict[tuple[str, str], set[str]],
    dict[tuple[str, str], dict[tuple[str, str], set[str]]],
    dict[tuple[str, str], set[str]],
]:
    """Index one competitor's clashes at *level* by attribute pair and category pair.

    Returns ``(personas_by_pair, personas_by_pair_and_values, unresolved_by_pair)``,
    each mapping to a **set of persona ids** because the counting unit is the persona:
    the per-clash rows are one per round, and a clash raised in three rounds of one
    persona is one affected persona, not three.

    An ``unresolved`` clash -- the judge named an attribute the persona does not carry,
    or carries with no value -- is counted at the *pair* grain (the pair is known and
    the clash is real) and excluded from the *value* grain, where it has nothing to
    contribute. It is counted separately so a value list that under-covers its pair is
    explained rather than merely short.
    """
    by_pair: dict[tuple[str, str], set[str]] = {}
    by_values: dict[tuple[str, str], dict[tuple[str, str], set[str]]] = {}
    unresolved: dict[tuple[str, str], set[str]] = {}
    for row in record.clashes:
        if row.severity != level:
            continue
        pair = (row.attr_a, row.attr_b)
        by_pair.setdefault(pair, set()).add(row.persona_id)
        if row.unresolved:
            unresolved.setdefault(pair, set()).add(row.persona_id)
            continue
        values = (row.value_a, row.value_b)
        by_values.setdefault(pair, {}).setdefault(values, set()).add(row.persona_id)
    return by_pair, by_values, unresolved


def _rank_by_personas(
    counts: dict[tuple[str, str], set[str]],
    *,
    denominator: int,
    top_n: int,
    min_count: int,
) -> tuple[list[tuple[int, tuple[str, str], int, float | None]], int, int]:
    """Rank ``{pair: {persona ids}}`` into ``(entries, n_suppressed, n_truncated)``.

    *entries* are ``(rank, pair, n_personas, prevalence)``, ordered by ``n_personas``
    descending with the pair itself as a **total** tie-break, so the ranks are a
    function of the counts alone and the emitted bytes do not depend on dict insertion
    order anywhere upstream.

    A pair below *min_count* is dropped and counted in *n_suppressed* rather than
    published: a rank-1 driver seen in two personas is an anecdote, and printing it at
    the top of a table asserts otherwise. What *top_n* leaves out is counted separately
    in *n_truncated* -- those are real drivers, merely below the cut, and the two
    exclusions must not be confusable.

    ``prevalence`` is ``None`` when the denominator is zero; a cell with no personas
    has no rate, and 0.0 would be a measurement.
    """
    ordered = sorted(
        ((pair, len(personas)) for pair, personas in counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    kept = [(pair, n) for pair, n in ordered if n >= min_count]
    entries = [
        (rank, pair, n, (n / denominator) if denominator else None)
        for rank, (pair, n) in enumerate(kept[:top_n], start=1)
    ]
    return entries, len(ordered) - len(kept), max(0, len(kept) - top_n)


def _driver_cell(
    record: CompetitorRecord,
    level: str,
    *,
    top_n: int,
    min_count: int,
    skips: list[_Skip],
) -> dict[str, Any]:
    """One competitor's ranked drivers at one severity level.

    ``denominator`` and ``affected`` are the *same* numbers the severity heatmap cell
    carries (both via :func:`_affected_at`), so a driver prevalence is always readable
    against the cell it explains.

    A competitor whose personas declare clashes at this level but whose per-clash rows
    hold none cannot be explained; that records a :class:`_Skip` and yields an empty
    driver list, never a silent zero -- an empty list would read as "nothing drove this
    cell", which is a claim, and a false one.
    """
    denominator = len(record.personas)
    affected = _affected_at(record, level)
    by_pair, by_values, unresolved = _clash_index(record, level)

    if affected and not by_pair:
        skips.append(_Skip(
            test=f"severity_drivers[{level}][{record.slug}]",
            reason=(
                f"{affected} persona(s) carry a {level} clash per {record.personas_csv_path}, "
                "but the per-clash CSV holds no row for them, so the cell cannot be "
                "attributed. Re-run scripts/analyze/analyze_persona_realism.py "
                "--rewrite-artifacts for this combination."
            ),
        ))

    ranked, n_suppressed, n_truncated = _rank_by_personas(
        by_pair, denominator=denominator, top_n=top_n, min_count=min_count,
    )
    drivers: list[dict[str, Any]] = []
    for rank, pair, n_personas, prevalence in ranked:
        value_ranked, n_values_suppressed, n_values_truncated = _rank_by_personas(
            by_values.get(pair, {}), denominator=denominator,
            top_n=top_n, min_count=min_count,
        )
        drivers.append({
            "rank": rank,
            "attr_a": pair[0],
            "attr_b": pair[1],
            "n_personas": n_personas,
            "prevalence": prevalence,
            # Personas whose value join failed: counted at the pair grain, absent from
            # the value grain, so a short value list is explained rather than puzzling.
            "n_personas_unresolved": len(unresolved.get(pair, ())),
            "values": [
                {
                    "rank": value_rank,
                    "value_a": values[0],
                    "value_b": values[1],
                    "n_personas": value_n,
                    "prevalence": value_prevalence,
                }
                for value_rank, values, value_n, value_prevalence in value_ranked
            ],
            "n_values_suppressed": n_values_suppressed,
            "n_values_truncated": n_values_truncated,
        })

    return {
        "slug": record.slug,
        "model": record.model,
        "strategy": record.strategy,
        "is_real_reference": record.is_real_reference,
        # Identical to the severity grid's cell, by construction (_affected_at).
        "denominator": denominator,
        "affected": affected,
        "drivers": drivers,
        "n_distinct_pairs": len(by_pair),
        "n_suppressed": n_suppressed,
        "n_truncated": n_truncated,
        "n_unresolved": sum(len(personas) for personas in unresolved.values()),
    }


def _severity_drivers(
    records: Sequence[CompetitorRecord],
    skips: list[_Skip],
    *,
    top_n: int,
    min_count: int,
    skipped_combinations: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Which attribute pairs -- and which category pairs -- drove each severity cell.

    **Descriptive only, exactly as the severity grids are.** It feeds no ranking, no
    contrast and no significance test, and it changes no number already published: it
    answers the question the heatmaps provoke and cannot answer, which is *what*
    clashed in a cell that the heatmap only sizes.

    One grid per level with the same layout as the prevalence grids, so a cell here
    lines up with the cell there: same coordinates, same denominator, same ``affected``.
    The real population is placed by :func:`_grid` exactly as it is everywhere else --
    an ordinary competitor carried under ``real`` because it has no model x method
    coordinate, never a grid row and never a reference.

    Comparative claims are deliberately absent. Ranking driver prevalences *across*
    cells would need a correction battery this block does not run, so it ranks only
    *within* a cell and the tables stay descriptive.

    *top_n* and *min_count* arrive as arguments (this module reads no config): the
    first bounds how much of each cell's tail is published, the second is the count
    below which a driver is suppressed-and-counted rather than ranked.
    """
    if top_n < 1:
        raise ValueError(f"driver top_n must be >= 1, got {top_n!r}: a table of zero rows explains nothing.")
    if min_count < 1:
        raise ValueError(
            f"driver min_count must be >= 1, got {min_count!r}: a driver exhibited by no "
            "persona is not a driver."
        )

    # Computed per (competitor, level) up front so the grid closures below are pure
    # lookups and the block-level aggregates are a second pass over finished cells --
    # never an accumulator mutated from inside a closure, whose totals would depend on
    # how many times _grid happened to call it.
    cells = {
        (record.slug, level): _driver_cell(
            record, level, top_n=top_n, min_count=min_count, skips=skips,
        )
        for record in records
        for level in SEVERITY_LEVELS
    }

    levels: dict[str, Any] = {}
    for level in SEVERITY_LEVELS:

        def _cell(entry: dict[str, Any], _level: str = level) -> dict[str, Any]:
            return cells[(entry["_record"].slug, _level)]

        levels[level] = {
            **SEVERITY_DIRECTIONS[level],
            "grid": _grid(
                _grid_entries(records),
                value_of=_cell,
                note=(
                    f"A null cell means that model x method combination was not judged -- it "
                    f"is NOT an absence of {level} drivers. " + _DRIVER_TIE_BREAK
                    + "." + _GRID_NOTE_SUFFIX
                ),
            ),
        }

    n_unresolved = sum(cell["n_unresolved"] for cell in cells.values())
    return {
        "levels": levels,
        "metric": (
            "share of a cell's personas exhibiting a given attribute-pair clash at this "
            "severity, ranked within the cell"
        ),
        "counting_unit": DRIVER_COUNTING_UNIT,
        "non_additive": DRIVER_NON_ADDITIVE,
        "reporting_only": (
            "Descriptive. This block feeds no ranking, no contrast and no significance "
            "test, and changes no number already published -- it explains the severity "
            "grids, it does not score them."
        ),
        "top_n": top_n,
        "min_count": min_count,
        "n_unresolved": n_unresolved,
        "excluded": {
            # Every exclusion this block is subject to, counted rather than left to be
            # inferred from a short table (guide 03 sect. 6: report what was dropped).
            "combinations_skipped": len(skipped_combinations),
            "personas_without_a_successful_round": sum(record.n_failed for record in records),
            "clashes_unresolved": n_unresolved,
            "drivers_below_min_count": sum(cell["n_suppressed"] for cell in cells.values()),
            "drivers_below_top_n": sum(cell["n_truncated"] for cell in cells.values()),
            "note": (
                "combinations_skipped are the units the loader could not consume (listed "
                "with reasons under skipped_combinations); "
                "personas_without_a_successful_round left no verdict and are outside every "
                "denominator here; clashes_unresolved are (persona, pair) clashes whose "
                "category values could not be joined -- counted at the attribute-pair grain "
                "and absent from the category-pair grain; the two driver counts are pairs "
                "ranked out of the published tables, below min_count and below top_n "
                "respectively."
            ),
        },
    }


# --------------------------------------------------------------------------- #
# Severity pair summary -- WHAT clashed country-wide (reporting only)          #
# --------------------------------------------------------------------------- #


#: The counting unit of the country-wide pair summary. A sibling of
#: :data:`DRIVER_COUNTING_UNIT` and deliberately not the same string: the per-cell driver
#: tables divide by *the cell's* persona count, this block divides by the **pooled** count
#: over the competitors it pools, and a caveat that named the wrong denominator would be
#: worse than none. The persona-not-clash half is identical in both, by construction.
PAIR_SUMMARY_COUNTING_UNIT = (
    "personas, not clashes: a pair the judge raised in several rounds of one persona "
    "counts that persona once, and each series is divided by its own pooled persona count"
)

#: Why this block reads the raw clash rows rather than the published driver tables.
#: Carried as a data field, and printed on the figure, because the two blocks answer
#: neighbouring questions from the same rows and the difference is invisible downstream.
PAIR_SUMMARY_PROVENANCE = (
    "computed from every per-clash row, not from the per-cell severity_drivers tables: "
    "those are already cut by --driver-top-n and floored by --driver-min-count, so summing "
    "them would over-weight pairs that merely clear many cells' cut and erase pairs that "
    "are broad but never locally top-ranked"
)


def _pair_personas(
    records: Sequence[CompetitorRecord], level: str
) -> dict[tuple[str, str], set[tuple[str, str]]]:
    """``{attribute pair: {(slug, persona_id)}}`` over *records* at *level*.

    The value is a set of ``(slug, persona_id)`` because the counting unit is the persona
    and ``persona_id`` is only unique *within* a combination: keyed on the id alone,
    ``persona_00007`` of one combination and of another would collapse into one. The set
    also absorbs the rounds -- a pair raised in three rounds of one persona is three clash
    rows and one affected persona -- which is the same dedupe :func:`_clash_index` and
    :func:`_affected_at` apply, one grain coarser.
    """
    by_pair: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for record in records:
        for row in record.clashes:
            if row.severity != level:
                continue
            by_pair.setdefault((row.attr_a, row.attr_b), set()).add((record.slug, row.persona_id))
    return by_pair


def severity_pair_summary(
    records: Sequence[CompetitorRecord], level: str, *, top_n: int
) -> dict[str, Any]:
    """Country-wide ranking of the attribute pairs that clashed at one severity *level*.

    The complement of the severity heatmaps: those answer "which model x method cells have
    a high rate at this level", this answers "at this level, what actually clashed,
    ranked". Attribute-pair grain, pooled **across** competitors -- deliberately not the
    model x method grain and not the category-value grain.

    Two properties make the numbers readable against the heatmap they complement:

    * **The counting unit is the persona.** A pair is counted once per persona that raised
      it, however many rounds or clash rows carried it -- the dedupe key is
      ``(slug, persona_id, attr_a, attr_b)`` at a fixed severity, matching
      :func:`_affected_at` and the driver prevalences.
    * **The denominator is the pooled persona count** over the competitors pooled, i.e.
      the summed ``len(record.personas)`` -- the same population the corresponding
      heatmap divides each of its cells by, so a bar is readable against that grid.

    **The real population is never pooled into the synthetic bars.** It is an ordinary
    competitor with no reference role, but it is also a single 100-persona unit against
    ~50 synthetic ones, so pooling it would both bury it and let its contribution be read
    as the synthetic population's. It is carried as its own series, with its own
    denominator, exactly as :func:`_grid` carries it as its own band.

    Ranking is by pooled **synthetic** persona count descending, with the pair itself as a
    total tie-break (``n_personas`` desc -> ``attr_a`` -> ``attr_b``), so the order is a
    function of the counts alone and no residual tie survives. A pair only the real
    population raised therefore ranks at zero and is almost always below the cut; it stays
    in the universe and is counted under ``n_pairs_real_only`` rather than dropped, since
    excluding it would privilege-by-omission the competitor this analysis refuses to
    privilege.

    *top_n* bounds how many pairs are published; what it leaves out is **counted**, never
    silently truncated. It arrives as an argument because this module reads no config.

    Returns a payload with an empty ``pairs`` list when no competitor clashed at *level* --
    a real and reportable outcome, which the renderer states rather than drawing as an
    empty axis. The denominators travel on it regardless, because "nobody clashed" is a
    rate over a real base and is worth nothing without one.

    Raises ``KeyError`` on an unknown severity level, and ``ValueError`` on *top_n* below
    one, on an empty *records*, on records spanning more than one country, or on more than
    one competitor flagged as the real population -- each of those makes the pooled
    denominator mean something other than what the figure would claim.
    """
    if level not in SEVERITY_DIRECTIONS:
        raise KeyError(
            f"Unknown severity level {level!r}: the judge emits {list(SEVERITY_LEVELS)}."
        )
    if top_n < 1:
        raise ValueError(
            f"pair-summary top_n must be >= 1, got {top_n!r}: a figure of zero bars ranks nothing."
        )
    if not records:
        raise ValueError(
            "severity_pair_summary needs at least one competitor: with none there is no "
            "denominator, and a pooled share over an empty population is undefined."
        )
    countries = sorted({record.country for record in records})
    if len(countries) > 1:
        raise ValueError(
            f"severity_pair_summary pools one country's competitors, got {countries}. "
            "Pooling across countries would divide clashes from several populations by one "
            "denominator that describes none of them."
        )

    real_records = [record for record in records if record.is_real_reference]
    if len(real_records) > 1:
        raise ValueError(
            "More than one competitor is flagged as the real population "
            f"({[r.slug for r in real_records]}); the consumption set is corrupt."
        )
    real = real_records[0] if real_records else None
    synthetic = [record for record in records if not record.is_real_reference]

    synthetic_pairs = _pair_personas(synthetic, level)
    real_pairs = _pair_personas(real_records, level)

    denominator = sum(len(record.personas) for record in synthetic)
    real_denominator = len(real.personas) if real is not None else None

    def _share(count: int, base: int | None) -> float | None:
        # A zero base is never used as a divisor: no persona, no rate (and 0.0 would be a
        # measurement -- the best possible one for a defect share).
        return (count / base) if base else None

    ordered = sorted(
        set(synthetic_pairs) | set(real_pairs),
        key=lambda pair: (-len(synthetic_pairs.get(pair, ())), pair[0], pair[1]),
    )
    pairs = [
        {
            "rank": rank,
            "attr_a": pair[0],
            "attr_b": pair[1],
            "n_personas": len(synthetic_pairs.get(pair, ())),
            "prevalence": _share(len(synthetic_pairs.get(pair, ())), denominator),
            "real_n_personas": None if real is None else len(real_pairs.get(pair, ())),
            "real_prevalence": (
                None if real is None
                else _share(len(real_pairs.get(pair, ())), real_denominator)
            ),
        }
        for rank, pair in enumerate(ordered[:top_n], start=1)
    ]

    return {
        "severity": level,
        **SEVERITY_DIRECTIONS[level],
        "country": countries[0],
        "pairs": pairs,
        "denominator": denominator,
        "n_synthetic_competitors": len(synthetic),
        "real_slug": None if real is None else real.slug,
        "real_denominator": real_denominator,
        "n_pairs_total": len(ordered),
        "n_pairs_shown": len(pairs),
        "n_pairs_hidden": max(0, len(ordered) - len(pairs)),
        # Pairs no synthetic competitor raised. They rank at zero and are therefore almost
        # always below the cut, so their absence from the bars is explained rather than
        # looking like the real population was held out of the universe.
        "n_pairs_real_only": sum(
            1 for pair in ordered if not synthetic_pairs.get(pair) and real_pairs.get(pair)
        ),
        "top_n": top_n,
        "metric": (
            "share of personas exhibiting a given attribute-pair clash at this severity, "
            "each series over its own pooled denominator"
        ),
        "counting_unit": PAIR_SUMMARY_COUNTING_UNIT,
        "non_additive": DRIVER_NON_ADDITIVE,
        "provenance": PAIR_SUMMARY_PROVENANCE,
        "reporting_only": (
            "Descriptive. This block feeds no ranking, no contrast and no significance "
            "test, and changes no number already published."
        ),
    }


# --------------------------------------------------------------------------- #
# Axis A -- pairwise contrasts against the real competitor                     #
# --------------------------------------------------------------------------- #


def _axis_a_contrasts(
    synthetic: Sequence[CompetitorRecord],
    real: CompetitorRecord,
    *,
    bootstrap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Each synthetic competitor vs the real one: rate difference, CI, test, effect.

    Holm-corrected across the whole family of contrasts, because asking the same
    question once per competitor is exactly the situation an uncorrected p-value
    mis-reports. ``diff > 0`` means the synthetic competitor is **less** coherent than
    the real population (a higher impossibility rate).
    """
    real_indicators = list(real.impossible_indicators)
    rows: list[dict[str, Any]] = []
    for record in synthetic:
        indicators = list(record.impossible_indicators)
        test = two_proportion_test(
            int(sum(indicators)), len(indicators),
            int(sum(real_indicators)), len(real_indicators),
        )
        diff_ci = bootstrap_difference_ci(
            indicators, real_indicators,
            iterations=bootstrap["iterations"],
            ci_level=bootstrap["ci_level"],
            seed=bootstrap["seed"],
        )
        rows.append({
            "slug": record.slug,
            "model": record.model,
            "strategy": record.strategy,
            "reference": real.slug,
            "rate": test["p_a"],
            "reference_rate": test["p_b"],
            "diff": test["diff"],
            "diff_ci_lo": diff_ci["lo"],
            "diff_ci_hi": diff_ci["hi"],
            "effect_h": test["h"],
            "effect_magnitude": test["h_magnitude"],
            "p_raw": test["p"],
            "n": len(indicators),
            "reference_n": len(real_indicators),
            "note": test.get("note"),
        })

    testable = [row for row in rows if row["p_raw"] is not None]
    if testable:
        adjusted = holm_adjust([row["p_raw"] for row in testable])
        for row, p_holm in zip(testable, adjusted):
            row["p_holm"] = p_holm
    for row in rows:
        row.setdefault("p_holm", None)
        row["correction"] = CORRECTION
    return rows


# --------------------------------------------------------------------------- #
# Axis B -- typicality dispersion vs the real target                           #
# --------------------------------------------------------------------------- #


def _dispersion_measures(record: CompetitorRecord) -> dict[str, float | None]:
    """This competitor's own dispersion block, keyed by measure.

    Lifted from the per-combination report rather than recomputed: the judging task
    already published these numbers under its own configured ``tail_threshold``, and
    recomputing them here with a possibly-different threshold would silently produce
    two versions of the same statistic.
    """
    return {measure: record.dispersion.get(measure) for measure in DISPERSION_MEASURES}


def _axis_b_contrast(
    synthetic: Sequence[CompetitorRecord],
    real: CompetitorRecord,
    *,
    variance_center: str,
) -> list[dict[str, Any]]:
    """Distance to the real population's dispersion, per measure, plus a Levene test.

    Direction: **near zero is better**. The real population is the target here, not a
    floor to beat -- a combination whose typicality variance is far *below* the real
    one has mode-collapsed, which is the failure this axis exists to catch, so the
    absolute distance is the quantity of interest in both directions.
    """
    real_measures = _dispersion_measures(real)
    real_typicality = list(real.typicality_means)
    rows: list[dict[str, Any]] = []
    for record in synthetic:
        measures = _dispersion_measures(record)
        distance = {
            measure: (
                abs(measures[measure] - real_measures[measure])
                if measures[measure] is not None and real_measures[measure] is not None
                else None
            )
            for measure in DISPERSION_MEASURES
        }
        rows.append({
            "slug": record.slug,
            "model": record.model,
            "strategy": record.strategy,
            "target": real.slug,
            "dispersion": measures,
            "target_dispersion": real_measures,
            "distance_to_scb": distance,
            "variance_equality": variance_equality_test(
                {record.slug: list(record.typicality_means), "real_reference": real_typicality},
                center=variance_center,
            ),
            "n": len(record.typicality_means),
            "target_n": len(real_typicality),
        })
    return rows


# --------------------------------------------------------------------------- #
# Factor significance -- model vs method                                       #
# --------------------------------------------------------------------------- #


def _factor_groups(
    records: Sequence[CompetitorRecord], factor: str
) -> dict[str, list[float]]:
    """Pool per-persona typicality means by *factor* (``model`` or ``strategy``)."""
    groups: dict[str, list[float]] = {}
    for record in records:
        key = getattr(record, factor)
        groups.setdefault(key, []).extend(record.typicality_means)
    return {key: values for key, values in groups.items() if values}


def _factor_level_order(levels: Sequence[str], factor: str) -> list[str]:
    """The published order of one factor's levels.

    The method factor is ordered by pipeline complexity, exactly as the grids are; the
    model factor has no declared order and stays alphabetical. Applied to the group
    mapping *before* the tests run, so the group listing, the Kruskal input and the Dunn
    pair list all present the levels in one order rather than three.
    """
    if factor == "strategy":
        return strategy_complexity_order(sorted(levels))
    return sorted(levels)


def _factor_significance(
    records: Sequence[CompetitorRecord], factor: str, skips: list[_Skip]
) -> dict[str, Any]:
    """Kruskal-Wallis + Dunn/Holm over per-persona typicality means, grouped by *factor*.

    The real competitor is **held out** by the caller: it is not a model x method cell,
    so including it would compare a factor level against a non-level and unbalance the
    design. It enters the analysis only through the pairwise contrasts above.
    """
    groups = _factor_groups(records, factor)
    usable = {key: values for key, values in groups.items() if len(values) >= 2}
    if len(usable) < 2:
        skips.append(_Skip(
            test=f"kruskal_by_{factor}",
            reason=f"need >=2 {factor} levels with >=2 typicality observations, got {len(usable)}",
        ))
        return {"kruskal": None, "dunn": [], "groups": {}, "correction": CORRECTION}

    usable = {key: usable[key] for key in _factor_level_order(list(usable), factor)}
    return {
        "kruskal": kruskal_test(usable),
        "dunn": dunn_posthoc(usable),
        "groups": {key: summarize(values) for key, values in usable.items()},
        "correction": CORRECTION,
        "unit": "per-persona mean typicality over the can_exist subset",
    }


def _mixed_logit_can_exist(
    records: Sequence[CompetitorRecord], skips: list[_Skip]
) -> dict[str, Any] | None:
    """Logit-linked mixed model of ``can_exist`` on model + method, clustered by combination.

    One binary observation per persona, fixed effects for the model and the method, and
    a **random intercept by combination** -- the level at which pseudo-replication
    actually happens (every persona of a combination shares one generation run). Fitted
    with ``statsmodels``' variational-Bayes binomial mixed GLM, which is the mixed-model
    form available for a binary outcome.

    Returns ``None`` and records a reason when the optional ``[analysis]`` extra is
    absent, when the design is degenerate (fewer than two levels on either factor, or a
    single combination), or when the fit does not converge. It is never silently
    omitted: a missing test that leaves no trace reads downstream as a test that was run
    and found nothing.
    """
    try:
        import numpy as np
        import pandas as pd
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except ImportError as exc:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason=f"optional analysis dependency missing ({exc}); install with: pip install -e .[analysis]",
        ))
        return None

    rows = [
        {
            "can_exist": 0 if row.can_exist_majority is False else 1,
            "model": record.model,
            "method": record.strategy,
            "combination": record.slug,
        }
        for record in records
        for row in record.personas
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        skips.append(_Skip(test="mixed_logit_can_exist", reason="no personas to fit"))
        return None
    if frame["model"].nunique() < 2 or frame["method"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason=(
                f"degenerate design: {frame['model'].nunique()} model level(s) x "
                f"{frame['method'].nunique()} method level(s); need >=2 of each"
            ),
        ))
        return None
    if frame["combination"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason="a random intercept by combination needs >=2 combinations",
        ))
        return None
    if frame["can_exist"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason="the outcome is constant (every persona judged the same way); the logit is undefined",
        ))
        return None

    try:
        fit = BinomialBayesMixedGLM.from_formula(
            "can_exist ~ C(model) + C(method)", {"combination": "0 + C(combination)"}, frame,
        ).fit_vb(verbose=False)
    except Exception as exc:  # noqa: BLE001 - any fit failure is a recorded skip
        skips.append(_Skip(test="mixed_logit_can_exist", reason=f"fit did not converge: {exc}"))
        return None

    params = {
        str(name): float(value)
        for name, value in zip(fit.model.exog_names, np.asarray(fit.fe_mean).ravel())
    }
    sds = {
        str(name): float(value)
        for name, value in zip(fit.model.exog_names, np.asarray(fit.fe_sd).ravel())
    }
    return {
        "method": "BinomialBayesMixedGLM (variational Bayes), logit link",
        "formula": "can_exist ~ C(model) + C(method), random intercept by combination",
        "n_observations": int(frame.shape[0]),
        "n_combinations": int(frame["combination"].nunique()),
        "fixed_effects_mean": params,
        "fixed_effects_sd": sds,
        "interpretation": (
            "Posterior means on the log-odds scale with their posterior SDs. A coefficient "
            "whose interval excludes zero by more than ~2 SD is the mixed-model analogue of "
            "a significant factor level; the random intercept absorbs the run-level "
            "clustering that makes the unclustered tests optimistic."
        ),
    }


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #


def build_ranking(
    records: Sequence[CompetitorRecord],
    country: str,
    *,
    bootstrap: dict[str, Any],
    variance_center: str,
    driver_top_n: int,
    driver_min_count: int,
    skipped_combinations: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Assemble one country's complete ranking document.

    *records* must all belong to *country* and must already have passed the loader's
    completeness and homogeneity gates. *bootstrap* is the judge config's block
    (``iterations``/``seed``/``ci_level``), reused verbatim so the intervals here are
    seeded identically to the per-combination ones.

    *driver_top_n* / *driver_min_count* bound the severity-driver tables. They are
    required rather than defaulted because a default here would be a second source of
    truth for a number the CLI already declares, and the two could silently disagree.
    """
    skips: list[_Skip] = []
    real = next((r for r in records if r.is_real_reference), None)
    synthetic = [r for r in records if not r.is_real_reference]

    ranking = _axis_a_ranking(records, bootstrap=bootstrap)

    if real is None:
        reason = (
            f"real_{country} was not among the consumable combinations, so there is nothing "
            "to contrast against. Judge it with "
            f"scripts/analyze/analyze_persona_realism.py --slug real_{country}."
        )
        skips.append(_Skip(test="axis_a_scb_contrast", reason=reason))
        skips.append(_Skip(test="axis_b_dispersion_contrast", reason=reason))
        contrasts: list[dict[str, Any]] = []
        dispersion_contrast: list[dict[str, Any]] = []
    else:
        contrasts = _axis_a_contrasts(synthetic, real, bootstrap=bootstrap)
        dispersion_contrast = _axis_b_contrast(synthetic, real, variance_center=variance_center)

    # Factor tests run over the synthetic competitors only: the real population is not
    # a model x method cell and would unbalance the design.
    by_model = _factor_significance(synthetic, "model", skips)
    by_method = _factor_significance(synthetic, "strategy", skips)
    mixed = _mixed_logit_can_exist(synthetic, skips)

    # Built before the document literal, not inside it: it appends to *skips*, which the
    # literal also reads, and a block whose completeness depended on key order would be
    # a trap for the next person to reorder the document.
    drivers = _severity_drivers(
        records, skips,
        top_n=driver_top_n, min_count=driver_min_count,
        skipped_combinations=skipped_combinations,
    )

    provenance = dict(records[0].provenance) if records else {}
    return {
        "process": "realism_ranking",
        "country": country,
        "n_competitors": len(records),
        "n_synthetic": len(synthetic),
        "real_competitor": real.slug if real is not None else None,
        "axis_definitions": {
            "A": {
                "quantity": "impossibility rate (share of internally-contradictory personas)",
                "real_population_role": "ordinary ranked competitor -- no privileged position",
                "direction": "lower is better, for every competitor including the real one",
            },
            "B": {
                "quantity": "typicality dispersion (variance / entropy / tail coverage)",
                "real_population_role": "the target to match",
                "direction": (
                    "distance to the real population near zero is better -- the failure mode "
                    "being guarded against is mode collapse, so a spread far below the real "
                    "one is as bad as one far above it"
                ),
            },
        },
        "axis_a": {
            "ranking": ranking,
            "grid": _axis_a_grid(ranking),
            "scb_contrast": contrasts,
            "correction": CORRECTION,
        },
        "axis_b": {
            "dispersion_contrast": dispersion_contrast,
            "measures": list(DISPERSION_MEASURES),
            "variance_center": variance_center,
        },
        # A separate dimension from the binary can_exist, deliberately outside axis_a:
        # reporting only, and it changes no existing number.
        "severity": _severity_grids(records),
        # The attribution half of that same dimension, and equally outside axis_a:
        # reporting only, and it changes no existing number.
        "severity_drivers": drivers,
        "factor_significance": {
            "by_model": by_model,
            "by_method": by_method,
            "mixed_logit_can_exist": mixed,
            "correction": CORRECTION,
            "real_competitor_held_out": True,
        },
        "caveats": [dict(caveat) for caveat in CAVEATS],
        "skipped_combinations": [
            {"slug": slug, "reason": reason} for slug, reason in skipped_combinations
        ],
        "skipped_tests": [{"test": skip.test, "reason": skip.reason} for skip in skips],
        "provenance": {
            "bootstrap_seed": bootstrap["seed"],
            "bootstrap_iterations": bootstrap["iterations"],
            "ci_level": bootstrap["ci_level"],
            "library_versions": _library_versions(),
            "judge_model": provenance.get("judge_model"),
            "prompt_template_sha256": provenance.get("prompt_template_sha256"),
            "n_rounds": provenance.get("n_rounds"),
            "consumed_artifacts": [str(record.report_path) for record in records],
        },
    }


def summary_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the Axis A ranking into ``realism_summary.csv`` rows (rank order)."""
    by_slug = {row["slug"]: row for row in ranking["axis_b"]["dispersion_contrast"]}
    rows: list[dict[str, Any]] = []
    for entry in ranking["axis_a"]["ranking"]:
        distance = (by_slug.get(entry["slug"], {}).get("distance_to_scb") or {})
        rows.append({
            "rank": entry["rank"],
            "slug": entry["slug"],
            "country": entry["country"],
            "model": entry["model"],
            "strategy": entry["strategy"],
            "is_real_reference": entry["is_real_reference"],
            "impossibility_rate": entry["rate"],
            "ci_lo": entry["ci_lo"],
            "ci_hi": entry["ci_hi"],
            "impossible_count": entry["impossible_count"],
            "denominator": entry["denominator"],
            "n_failed": entry["n_failed"],
            "dist_variance": distance.get("variance"),
            "dist_entropy": distance.get("entropy"),
            "dist_tail_coverage": distance.get("tail_coverage"),
        })
    return rows


def _driver_cells(
    ranking: dict[str, Any], level: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One level's block and every competitor's cell in it, in slug order.

    Flattens the grid back to a list: the model x method shape exists for the heatmaps,
    and a table wants one row per competitor. The real population is carried under
    ``real`` rather than as a grid row (it has no coordinate), so it is picked up here
    explicitly -- it is an ordinary competitor in these tables, as it is everywhere else
    on this axis, and omitting it would quietly answer "what does the real population
    clash on?" with silence.
    """
    levels = ranking["severity_drivers"]["levels"]
    if level not in levels:
        raise KeyError(
            f"Unknown severity level {level!r}: the judge emits {list(SEVERITY_LEVELS)}."
        )
    grid = levels[level]["grid"]
    rows = [
        cell
        for model in grid["models"]
        for cell in (grid["cells"][model][method] for method in grid["methods"])
        if cell is not None            # an unjudged (model, method) pair is None, not empty
    ]
    if grid["real"] is not None:
        rows.append(grid["real"])
    return levels[level], sorted(rows, key=lambda cell: cell["slug"])


def _competitor_position(
    rows: Sequence[dict[str, Any]]
) -> Callable[[dict[str, Any]], tuple[int, int, str]]:
    """Build the leading sort key of the flat driver tables: method, then model.

    A slug is ``{country}_{strategy}_{model}``, so ordering the tables on it walked the
    methods **alphabetically** -- which on this axis is close to reverse complexity order,
    and left a table disagreeing with its own heatmap about which method comes first.
    Ordering on the decomposed coordinates fixes that while keeping the two properties the
    slug key was chosen for: a competitor's rows stay contiguous (within one country a
    ``(strategy, model)`` pair identifies the slug), and the order stays total.

    The real population sorts after every synthetic competitor rather than among them. It
    has no coordinate on either axis, so the grids carry it beside the cells instead of in
    them; giving it a position on the method axis here would be the fabricated rank they
    refuse.
    """
    method_rank = {
        method: rank
        for rank, method in enumerate(strategy_complexity_order(sorted(
            {row["strategy"] for row in rows if not row["is_real_reference"]}
        )))
    }

    def position(row: dict[str, Any]) -> tuple[int, int, str]:
        if row["is_real_reference"]:
            return (1, 0, row["slug"])
        return (0, method_rank[row["strategy"]], row["model"])

    return position


def _driver_identity(cell: dict[str, Any], level: str, *, penalised: bool) -> dict[str, Any]:
    """The columns every driver row carries whatever its grain.

    ``severity`` sits with the identity columns rather than beside the numbers: the
    three levels are interleaved in one table, so which level a row belongs to is part
    of naming the row, not part of describing it. ``penalised`` follows it immediately
    and travels on every row because these tables are read one row at a time -- an S1
    row that arrives without it is an unusual-but-possible pairing presented in the same
    shape as a defect, which is exactly the misreading the level exists to prevent, and
    the merge makes it the *only* thing on the row that tells the two apart.
    ``counting_unit`` and ``non_additive`` travel for the same reason -- the file
    outlives the docstring.
    """
    return {
        "slug": cell["slug"],
        "model": cell["model"],
        "strategy": cell["strategy"],
        "is_real_reference": cell["is_real_reference"],
        "severity": level,
        "penalised": penalised,
    }


def severity_driver_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every level's drivers into ``severity_drivers.csv`` rows.

    Attribute-pair grain: one row per ranked ``(competitor, severity, attribute pair)``,
    all three levels in one table with ``severity`` as a column. Every row carries the
    cell's ``denominator`` and ``affected`` beside its own count, so a prevalence is
    never read without the base it was computed over, and the level's ``penalised`` flag
    so the row cannot be mistaken for a defect when it is not one.

    ``rank`` stays **within** ``(slug, severity)`` -- a rank-1 S2 driver and a rank-1 S3
    driver are both rank 1, because ranking across levels would compare a hard
    contradiction against an unusual-but-possible pairing on one scale, which the
    severity dimension exists to refuse. The sort key below makes that readable by
    keeping a competitor's levels contiguous and ordered.
    """
    rows: list[dict[str, Any]] = []
    for level in SEVERITY_LEVELS:
        block, cells = _driver_cells(ranking, level)
        penalised = bool(block["penalised"])
        for cell in cells:
            for driver in cell["drivers"]:
                rows.append({
                    **_driver_identity(cell, level, penalised=penalised),
                    "rank": driver["rank"],
                    "attr_a": driver["attr_a"],
                    "attr_b": driver["attr_b"],
                    "n_personas": driver["n_personas"],
                    "prevalence": driver["prevalence"],
                    "denominator": cell["denominator"],
                    "cell_affected": cell["affected"],
                    "n_personas_unresolved": driver["n_personas_unresolved"],
                    "counting_unit": DRIVER_COUNTING_UNIT,
                    "non_additive": DRIVER_NON_ADDITIVE,
                })
    # Total order, no residual tie: the competitor identifies the block of rows and is
    # placed on the method-then-model axes rather than by slug (see _competitor_position),
    # severity orders the levels by SEVERITY_RANK (S3, S2, S1 -- worst first, and never
    # alphabetically, which would put the mildest level at the top), and `rank` is already
    # total within a (slug, severity) cell via the declared tie-break. Sorted after the
    # build rather than during it so the emitted bytes never depend on record order.
    position = _competitor_position(rows)
    rows.sort(key=lambda row: (*position(row), SEVERITY_RANK[row["severity"]], row["rank"]))
    return rows


def severity_driver_value_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every level's drivers into ``severity_driver_values.csv`` rows.

    Category-pair grain: one row per ranked ``(competitor, severity, attribute pair,
    category pair)`` -- the finest published grain, and the one that names the actual
    finding ("Student x Permanent Full-time") rather than only the axes it lives on. The
    parent pair's rank and count travel on the row so the nesting survives the
    flattening, and ``rank`` is within its parent pair exactly as ``pair_rank`` is within
    ``(slug, severity)``.
    """
    rows: list[dict[str, Any]] = []
    for level in SEVERITY_LEVELS:
        block, cells = _driver_cells(ranking, level)
        penalised = bool(block["penalised"])
        for cell in cells:
            for driver in cell["drivers"]:
                for value in driver["values"]:
                    rows.append({
                        **_driver_identity(cell, level, penalised=penalised),
                        "attr_a": driver["attr_a"],
                        "attr_b": driver["attr_b"],
                        "pair_rank": driver["rank"],
                        "pair_n_personas": driver["n_personas"],
                        "rank": value["rank"],
                        "value_a": value["value_a"],
                        "value_b": value["value_b"],
                        "n_personas": value["n_personas"],
                        "prevalence": value["prevalence"],
                        "denominator": cell["denominator"],
                        "counting_unit": DRIVER_COUNTING_UNIT,
                        "non_additive": DRIVER_NON_ADDITIVE,
                    })
    # Same key as the coarser grain, extended through the nesting: (competitor by method
    # then model, severity by SEVERITY_RANK, parent pair by its rank, category pair by its
    # own rank). Both ranks are total within their scope, so no residual tie survives.
    position = _competitor_position(rows)
    rows.sort(key=lambda row: (
        *position(row), SEVERITY_RANK[row["severity"]], row["pair_rank"], row["rank"],
    ))
    return rows


def scb_contrast_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten both axes' contrasts against the real population into CSV rows."""
    dispersion = {row["slug"]: row for row in ranking["axis_b"]["dispersion_contrast"]}
    rows: list[dict[str, Any]] = []
    for contrast in ranking["axis_a"]["scb_contrast"]:
        axis_b = dispersion.get(contrast["slug"], {})
        distance = axis_b.get("distance_to_scb") or {}
        variance_equality = axis_b.get("variance_equality") or {}
        rows.append({
            "slug": contrast["slug"],
            "model": contrast["model"],
            "strategy": contrast["strategy"],
            "reference": contrast["reference"],
            "rate": contrast["rate"],
            "reference_rate": contrast["reference_rate"],
            "rate_diff": contrast["diff"],
            "rate_diff_ci_lo": contrast["diff_ci_lo"],
            "rate_diff_ci_hi": contrast["diff_ci_hi"],
            "effect_h": contrast["effect_h"],
            "effect_magnitude": contrast["effect_magnitude"],
            "p_raw": contrast["p_raw"],
            "p_holm": contrast["p_holm"],
            "correction": contrast["correction"],
            "n": contrast["n"],
            "reference_n": contrast["reference_n"],
            "dist_variance": distance.get("variance"),
            "dist_entropy": distance.get("entropy"),
            "dist_tail_coverage": distance.get("tail_coverage"),
            "variance_equality_stat": variance_equality.get("statistic"),
            "variance_equality_p": variance_equality.get("p"),
        })
    return rows

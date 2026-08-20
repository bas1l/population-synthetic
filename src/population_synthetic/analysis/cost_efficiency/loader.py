"""loader.py -- join accuracy, gate counts and generation cost into one typed set.

Three files, written by three processes that do not reference one another, describe the
same grid of ``country x strategy x model`` combinations:

* ``model_ranking/{country}_performance.csv`` -- the accuracy side. One row per scored
  combination, carrying ``overall_tv_similarity`` and the population ``n`` it was
  scored over. It **does** carry a ``slug`` column.
* ``validation_attrition/{country}_attrition.csv`` -- the gate side. One row per
  combination the gate recorded, **including the withdrawn ones**, carrying the funnel
  counts this module denominates cost on.
* ``generation_metadata/{country}_summary.csv`` -- the telemetry side. One row per
  combination that produced a capped mirror, keyed on ``model`` + ``method``, with **no
  slug column**.

The cost itself is *not* read from the third file. ``generation_metadata`` totals its
cost over the capped mirror -- the ~100 personas each combination was subsampled down to
-- and that denominator understates the wasteful models most and is entirely absent for
a withdrawn combination. Cost comes from
:mod:`~population_synthetic.analysis.cost_efficiency.raw_cost`, which totals the same
telemetry over the full ``01_Raw`` generated pool. The summary CSV is still read,
because it is a declared input and its ``has_token_data`` flag is an independent
observation of whether the run produced token counts at all.

The join key
------------

**The key is the run slug, ``{country}_{strategy}_{model}``, and it is built by
``manifest_loader.axis_slug`` -- the single source of truth for that format.** It is
never re-implemented here, never assembled by an f-string, and never recovered by
splitting a slug on ``_`` (neither strategy nor model ids are ``_``-free, so a naive
split is wrong).

Reconstructing a key is the risky part of this module, so the reconstruction is
*checked* rather than trusted (guide 03 sect. 6 -- be cautious joining on a
reconstructed key; state the rule and assert it is one-to-one):

* The performance CSV publishes both the ``(model, strategy)`` pair and the slug it
  belongs to. Every row's reconstructed key is compared against that published slug and
  a disagreement raises. This is a live test of the reconstruction rule against a
  producer that wrote the slug itself, executed on every read.
* Within each file, the reconstructed keys must be unique. A repeat would make the join
  many-to-one and silently average two combinations together.
* Across files, membership is reconciled explicitly -- see below.

Membership: three files that legitimately disagree
--------------------------------------------------

The three inputs do **not** describe the same row set, and that is correct rather than a
defect:

* the attrition CSV holds **every** combination the gate recorded, withdrawals included;
* the performance CSV holds only combinations that were scored, so no withdrawal
  appears -- a withdrawn combination has no capped mapped file to score;
* the summary CSV holds only combinations with a capped mirror, so again no withdrawal.

The rule this module applies, stated once and asserted on every read:

**The output row set is the attrition row set minus the withdrawals**, and that set must
match the performance and telemetry row sets *exactly*.

* A combination in attrition, not withdrawn, and absent from either of the other two
  files is an **error** -- the gate says it survived and produced a capped mirror, so a
  missing score or missing telemetry means the analysis chain is half-run. It raises,
  naming the key and both files.
* A combination in the performance or telemetry CSV that the attrition CSV does not
  record at all, or records as withdrawn, is an **error** -- an accuracy score for a
  combination the gate withdrew is a contradiction, not a bonus row. It raises.
* A combination in attrition and marked withdrawn is **not** an error. It is reported,
  never inner-joined away (guide 03 sect. 6 -- report what was dropped): its cost over
  the generated pool is still measured and returned separately, because a combination
  that spent money and yielded nothing is the single most relevant fact a cost figure
  can carry, and this is the only place it can be read.
* An **empty** join raises. Zero matched rows is never a valid result here; it means the
  three files describe disjoint pipeline states.

Filtering is selection, not a verdict. ``models``/``strategies``/``slugs`` narrow the
universe on all three sides symmetrically *before* the reconciliation, so a filter
changes what is checked but can never turn a mismatch into a match.

Boundary: this module knows nothing about matplotlib, about how total-variation
similarity was computed, about the capped mirror, or about where any output goes. It
resolves three paths through the registry, reads them, prices the raw pools, and returns
typed records.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from population_synthetic.analysis.cost_efficiency.raw_cost import (
    RawCostTotals,
    RawPricing,
    load_raw_pricing,
    raw_cost_for_slug,
)
from population_synthetic.analysis.utils.attrition_csv import AttritionRow, read_attrition_csv
from population_synthetic.analysis.utils.registry import analysis_output_dir, get_process
from population_synthetic.analysis.utils.tidy_csv import missing_columns
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

__all__ = [
    "ACCURACY_COLUMN",
    "ATTRITION_PROCESS_ID",
    "ATTRITION_SUFFIX",
    "PERFORMANCE_PROCESS_ID",
    "PERFORMANCE_SUFFIX",
    "TELEMETRY_PROCESS_ID",
    "TELEMETRY_SUFFIX",
    "AccuracyRecord",
    "CostRecord",
    "CostSources",
    "JoinResult",
    "WithdrawnCombination",
    "available_countries",
    "load_cost_records",
    "resolve_sources",
]

#: The registered process ids whose folders hold the three inputs. Named rather than
#: inlined so the folder names stay the registry's business (project invariant: no path
#: literals for analysis output folders).
PERFORMANCE_PROCESS_ID = "model_ranking"
ATTRITION_PROCESS_ID = "validation_attrition"
TELEMETRY_PROCESS_ID = "generation_metadata"

#: Per-country filename suffixes each of those processes writes.
PERFORMANCE_SUFFIX = "_performance.csv"
ATTRITION_SUFFIX = "_attrition.csv"
TELEMETRY_SUFFIX = "_summary.csv"

#: The accuracy field this process plots. ``model_ranking``'s headline per-combination
#: score: the mean total-variation similarity across the analysed attribute axis.
ACCURACY_COLUMN = "overall_tv_similarity"

#: Performance-CSV columns read here. A subset check, not an equality check -- that file
#: carries one ``tv_similarity__*`` column per analysed attribute and they are none of
#: this module's business.
_PERFORMANCE_COLUMNS = ("slug", "model", "strategy", "n", ACCURACY_COLUMN)

#: Summary-CSV columns read here. ``method`` holds **strategy ids**, not labels -- the
#: producer writes ``summary.strategy`` into it -- which is what makes the slug
#: reconstruction possible at all.
_TELEMETRY_MODEL_COLUMN = "model"
_TELEMETRY_METHOD_COLUMN = "method"
_TELEMETRY_TOKEN_FLAG_COLUMN = "has_token_data"
_TELEMETRY_COLUMNS = (
    _TELEMETRY_MODEL_COLUMN,
    _TELEMETRY_METHOD_COLUMN,
    _TELEMETRY_TOKEN_FLAG_COLUMN,
)

#: ``has_token_data`` serialises through Python's ``str(bool)``, so the cell reads
#: ``True``/``False`` -- capitalised, and deliberately not the ``true``/``false`` the
#: tidy-CSV contracts in this package emit. Parsed against the producer's own spelling
#: rather than coerced, so a change of spelling upstream raises here instead of silently
#: reading every row as false.
_TELEMETRY_TRUE = "True"
_TELEMETRY_FALSE = "False"


@dataclass(frozen=True)
class CostSources:
    """The three files one country's cost efficiency is joined from, plus the raw pool.

    Carried as a value rather than recomputed per caller, so the paths named in an error
    message, the paths recorded in the JSON document, and the paths actually read are
    provably the same ones.
    """

    performance: Path
    attrition: Path
    telemetry: Path
    #: The generation output root. Cost is totalled under ``{output_base}/01_Raw/``.
    output_base: Path


@dataclass(frozen=True)
class AccuracyRecord:
    """One combination's fidelity score, as ``model_ranking`` published it."""

    slug: str
    model: str
    strategy: str
    #: The headline score. Higher is better; the range is [0, 1].
    overall_tv_similarity: float
    #: The capped population the score was computed over -- the score's denominator.
    n_scored: int


@dataclass(frozen=True)
class CostRecord:
    """One combination's accuracy beside the cost of the run that produced it.

    Measurements only: nothing here is a quotient. ``cost_per_usable_persona`` is the
    builder's job, so a reader of this record can never confuse what was read with what
    was derived.

    ``attrition`` carries the gate counts verbatim (including the two rates the
    attrition contract itself published, which this process consumes rather than
    recomputes), and ``cost`` the raw-pool totals with their own ``cost_basis``.
    """

    slug: str
    country: str
    model: str
    strategy: str
    accuracy: AccuracyRecord
    attrition: AttritionRow
    cost: RawCostTotals
    #: ``has_token_data`` as ``generation_metadata`` observed it on the capped mirror.
    #: An independent observation of the same run over a strict subset of the same
    #: personas; kept beside ``cost.has_token_data`` rather than merged with it.
    capped_has_token_data: bool


@dataclass(frozen=True)
class WithdrawnCombination:
    """A combination the full-N rule withdrew: measured, reported, never plotted.

    It has no accuracy score and no capped mirror, so it cannot appear on a
    cost-vs-accuracy figure -- but it was generated and paid for, and the money is
    measurable over the raw pool. Reporting it is the difference between "these were the
    combinations" and "these were the combinations that worked out".
    """

    slug: str
    model: str
    strategy: str
    reason: str
    generated: int
    clean: int
    cost: RawCostTotals


@dataclass(frozen=True)
class JoinResult:
    """Everything one country's join produced, including what it deliberately excluded."""

    country: str
    records: list[CostRecord]
    withdrawn: list[WithdrawnCombination]
    sources: CostSources
    pricing: RawPricing
    #: Row counts on each side of the join, for the report's membership block. The
    #: three inputs legitimately disagree, so publishing the disagreement is what makes
    #: the output row count auditable instead of merely asserted.
    membership: dict[str, int]


def _script(process_id: str) -> str:
    """The registered script that regenerates *process_id*'s output (never a literal)."""
    return get_process(process_id).script


def resolve_sources(output_base: str | Path, country: str) -> CostSources:
    """Resolve the three input paths for *country* (no reading, no existence check)."""
    output_base = Path(output_base)
    return CostSources(
        performance=(
            analysis_output_dir(PERFORMANCE_PROCESS_ID, output_base, for_read=True)
            / f"{country}{PERFORMANCE_SUFFIX}"
        ),
        attrition=(
            analysis_output_dir(ATTRITION_PROCESS_ID, output_base, for_read=True)
            / f"{country}{ATTRITION_SUFFIX}"
        ),
        telemetry=(
            analysis_output_dir(TELEMETRY_PROCESS_ID, output_base, for_read=True)
            / f"{country}{TELEMETRY_SUFFIX}"
        ),
        output_base=output_base,
    )


def available_countries(output_base: str | Path) -> list[str]:
    """Country ids that have a validation-attrition CSV under *output_base*, sorted.

    The attrition CSV is the row grain of this process, so its presence is what makes a
    country analysable at all. Derived from the filenames rather than from the axis
    registry: the registry lists every country that *could* be generated, which is a
    different question from which one this output base holds artifacts for.
    """
    directory = analysis_output_dir(ATTRITION_PROCESS_ID, Path(output_base), for_read=True)
    if not directory.is_dir():
        return []
    return sorted(
        path.name[: -len(ATTRITION_SUFFIX)]
        for path in directory.glob(f"*{ATTRITION_SUFFIX}")
        if path.is_file() and len(path.name) > len(ATTRITION_SUFFIX)
    )


def _read_performance(path: Path, country: str) -> dict[str, AccuracyRecord]:
    """Read the ranking CSV into ``{slug: AccuracyRecord}`` (fail-fast).

    Every row's slug is **reconstructed** from its ``(model, strategy)`` pair through
    :func:`axis_slug` and compared against the ``slug`` the producer wrote. That check is
    the reason this module can join the slug-less telemetry CSV at all: it proves, on
    this very data, that the reconstruction rule reproduces the producer's own slug.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Model-ranking performance CSV not found: {path}. It is the accuracy side of "
            f"the cost join; run {_script(PERFORMANCE_PROCESS_ID)} for this country first."
        )
    records: dict[str, AccuracyRecord] = {}
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, _PERFORMANCE_COLUMNS)
        if missing:
            raise ValueError(
                f"{path}: performance CSV is missing required column(s) {missing}; header is "
                f"{list(header)}. Re-run {_script(PERFORMANCE_PROCESS_ID)} to rewrite it."
            )
        for position, row in enumerate(reader):
            published_slug = (row["slug"] or "").strip()
            model = (row["model"] or "").strip()
            strategy = (row["strategy"] or "").strip()
            if not published_slug or not model or not strategy:
                raise ValueError(
                    f"{path}: row {position} is missing one of slug/model/strategy "
                    f"({published_slug!r}, {model!r}, {strategy!r}). Re-run "
                    f"{_script(PERFORMANCE_PROCESS_ID)} to rewrite it."
                )
            rebuilt = axis_slug(model, strategy, country)
            if rebuilt != published_slug:
                raise ValueError(
                    f"{path}: row {position} publishes slug {published_slug!r} but its "
                    f"(model={model!r}, strategy={strategy!r}) rebuild through "
                    f"manifest_loader.axis_slug for country {country!r} is {rebuilt!r}. The "
                    "join key for the slug-less generation-metadata summary is reconstructed "
                    "by exactly that rule, so a disagreement here means every reconstructed "
                    "key is suspect. Either the row belongs to another country or an axis id "
                    f"was renamed without re-running {_script(PERFORMANCE_PROCESS_ID)}."
                )
            if published_slug in records:
                raise ValueError(
                    f"{path}: combination {published_slug!r} appears twice. The cost join is "
                    "one-to-one on the slug, so a duplicate would average two scores into one "
                    f"point without saying so. Re-run {_script(PERFORMANCE_PROCESS_ID)}."
                )
            records[published_slug] = AccuracyRecord(
                slug=published_slug,
                model=model,
                strategy=strategy,
                overall_tv_similarity=_require_float(
                    row[ACCURACY_COLUMN], column=ACCURACY_COLUMN, path=path, slug=published_slug,
                    process_id=PERFORMANCE_PROCESS_ID,
                ),
                n_scored=_require_int(
                    row["n"], column="n", path=path, slug=published_slug,
                    process_id=PERFORMANCE_PROCESS_ID,
                ),
            )
    return records


def _require_float(raw: Any, *, column: str, path: Path, slug: str, process_id: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path}: combination {slug!r} column {column!r} is {raw!r}, which is not a "
            f"number. Re-run {_script(process_id)} to rewrite it."
        ) from exc


def _require_int(raw: Any, *, column: str, path: Path, slug: str, process_id: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path}: combination {slug!r} column {column!r} is {raw!r}, which is not an "
            f"integer count. Re-run {_script(process_id)} to rewrite it."
        ) from exc


def _read_telemetry(path: Path, country: str) -> dict[str, bool]:
    """Read the generation-metadata summary into ``{slug: has_token_data}`` (fail-fast).

    This file has **no slug column**: its key is ``model`` + ``method``, where ``method``
    holds strategy ids. The slug is therefore reconstructed through :func:`axis_slug` --
    the same rule ``_read_performance`` has just verified against a producer-written slug
    -- and the reconstructed keys are asserted unique.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Generation-metadata summary CSV not found: {path}. It is the telemetry side of "
            f"the cost join; run {_script(TELEMETRY_PROCESS_ID)} for this country first."
        )
    flags: dict[str, bool] = {}
    seen_keys: dict[str, tuple[str, str]] = {}
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, _TELEMETRY_COLUMNS)
        if missing:
            raise ValueError(
                f"{path}: generation-metadata summary is missing required column(s) {missing}; "
                f"header is {list(header)}. Re-run {_script(TELEMETRY_PROCESS_ID)} to rewrite it."
            )
        for position, row in enumerate(reader):
            model = (row[_TELEMETRY_MODEL_COLUMN] or "").strip()
            method = (row[_TELEMETRY_METHOD_COLUMN] or "").strip()
            if not model or not method:
                raise ValueError(
                    f"{path}: row {position} is missing model/method ({model!r}, {method!r}); "
                    "they are the only join key this file carries. Re-run "
                    f"{_script(TELEMETRY_PROCESS_ID)} to rewrite it."
                )
            slug = axis_slug(model, method, country)
            if slug in seen_keys:
                first_model, first_method = seen_keys[slug]
                raise ValueError(
                    f"{path}: rows (model={first_model!r}, method={first_method!r}) and "
                    f"(model={model!r}, method={method!r}) both reconstruct the join key "
                    f"{slug!r} for country {country!r}. The key is built by "
                    "manifest_loader.axis_slug and the join is one-to-one, so a collision "
                    "would attribute one run's telemetry to two combinations. Re-run "
                    f"{_script(TELEMETRY_PROCESS_ID)} to rewrite the summary."
                )
            seen_keys[slug] = (model, method)
            raw_flag = (row[_TELEMETRY_TOKEN_FLAG_COLUMN] or "").strip()
            if raw_flag not in (_TELEMETRY_TRUE, _TELEMETRY_FALSE):
                raise ValueError(
                    f"{path}: combination {slug!r} column "
                    f"{_TELEMETRY_TOKEN_FLAG_COLUMN!r} is {raw_flag!r}, which is neither "
                    f"{_TELEMETRY_TRUE!r} nor {_TELEMETRY_FALSE!r}. The producer writes a "
                    "Python bool repr; a third spelling means the file was not written by "
                    f"{_script(TELEMETRY_PROCESS_ID)}, and guessing at its meaning would "
                    "silently mark a metered run as having produced no tokens."
                )
            flags[slug] = raw_flag == _TELEMETRY_TRUE
    return flags


def _selected(
    row_slug: str,
    model: str,
    strategy: str,
    *,
    models: Sequence[str] | None,
    strategies: Sequence[str] | None,
    slugs: Sequence[str] | None,
) -> bool:
    """Does this combination survive the caller's selection filters?"""
    if slugs is not None and row_slug not in slugs:
        return False
    if models is not None and model not in models:
        return False
    if strategies is not None and strategy not in strategies:
        return False
    return True


def _reconcile_membership(
    *,
    expected: set[str],
    withdrawn: set[str],
    accuracy: Mapping[str, AccuracyRecord],
    telemetry: Mapping[str, bool],
    sources: CostSources,
) -> None:
    """Raise unless the three selected row sets agree under the stated membership rule.

    *expected* is the attrition row set minus the withdrawals -- the combinations that
    must have both an accuracy score and a capped mirror. Each of the four failure modes
    names the offending key and both files it disagrees between.
    """
    problems: list[str] = []

    for label, present, path, process_id in (
        ("accuracy", set(accuracy), sources.performance, PERFORMANCE_PROCESS_ID),
        ("telemetry", set(telemetry), sources.telemetry, TELEMETRY_PROCESS_ID),
    ):
        missing = sorted(expected - present)
        if missing:
            problems.append(
                f"{len(missing)} combination(s) are recorded as surviving the gate in "
                f"{sources.attrition} but have no {label} row in {path}: {missing[:5]}"
                + (" ..." if len(missing) > 5 else "")
                + f". Re-run {_script(process_id)} for this country."
            )
        contradicted = sorted(present & withdrawn)
        if contradicted:
            problems.append(
                f"{len(contradicted)} combination(s) have a {label} row in {path} but are "
                f"recorded as WITHDRAWN by the full-N rule in {sources.attrition}: "
                f"{contradicted[:5]}"
                + (" ..." if len(contradicted) > 5 else "")
                + ". A withdrawn combination has no capped mirror and no capped mapped file, "
                f"so it cannot have been scored -- one of the two artifacts is stale. Re-run "
                f"{_script('population_cap')}, then {_script(ATTRITION_PROCESS_ID)} --force "
                f"and {_script(process_id)} --force."
            )
        unknown = sorted(present - expected - withdrawn)
        if unknown:
            problems.append(
                f"{len(unknown)} combination(s) have a {label} row in {path} but no row at "
                f"all in {sources.attrition}: {unknown[:5]}"
                + (" ..." if len(unknown) > 5 else "")
                + ". The attrition CSV is the row grain of this process and is written from "
                f"the gate's own index, so a combination absent from it was never capped. "
                f"Re-run {_script(ATTRITION_PROCESS_ID)} --force for this country."
            )

    if problems:
        raise ValueError(
            "The cost join is not one-to-one; the inputs describe different states of the "
            "pipeline. " + " ".join(problems)
        )


def load_cost_records(
    output_base: str | Path,
    country: str,
    *,
    pricing: RawPricing | None = None,
    models: Sequence[str] | None = None,
    strategies: Sequence[str] | None = None,
    slugs: Sequence[str] | None = None,
) -> JoinResult:
    """Join accuracy, gate counts and raw-pool cost for one country.

    Args:
        output_base: The run's output base (the parent of ``01_Raw/`` and ``03_Analysis/``).
        country: The country axis id whose three per-country files are joined.
        pricing: A pricing table from
            :func:`~population_synthetic.analysis.cost_efficiency.raw_cost.load_raw_pricing`.
            ``None`` loads the repository config. Injected rather than read inside the
            loop so every combination in one report is priced from one table (guide 02
            sect. 7 -- config is loaded once, at the edge, and passed down).
        models / strategies / slugs: Optional selection filters, applied symmetrically to
            all three sides *before* the membership reconciliation.

    Returns:
        A :class:`JoinResult`: the joined records sorted by slug, the withdrawn
        combinations sorted by slug, the source paths, the pricing table, and the row
        counts on each side.

    Raises:
        FileNotFoundError: If any of the three inputs, or a combination's ``01_Raw``
            pool, is absent.
        ValueError: If a file is malformed, a reconstructed key collides or disagrees
            with a published slug, the membership rule is violated, or the join is empty.
        KeyError: If a model in the selection has no pricing entry (raised by
            :mod:`raw_cost` before any telemetry is read).
    """
    sources = resolve_sources(output_base, country)
    pricing = load_raw_pricing() if pricing is None else pricing

    attrition_rows = read_attrition_csv(sources.attrition)
    foreign = sorted({row.country for row in attrition_rows} - {country})
    if foreign:
        raise ValueError(
            f"{sources.attrition}: expected every row to carry country {country!r} but found "
            f"{foreign}. The file is named per country, so a foreign row means it was written "
            f"for a different country or hand-edited. Re-run "
            f"{_script(ATTRITION_PROCESS_ID)} --force."
        )

    all_by_slug = {row.slug: row for row in attrition_rows}
    selected_rows = [
        row for row in attrition_rows
        if _selected(row.slug, row.model, row.strategy,
                     models=models, strategies=strategies, slugs=slugs)
    ]
    by_slug = {row.slug: row for row in selected_rows}
    withdrawn_slugs = {row.slug for row in selected_rows if row.excluded}
    expected_slugs = set(by_slug) - withdrawn_slugs

    accuracy = {
        slug: record
        for slug, record in _read_performance(sources.performance, country).items()
        if _selected(slug, record.model, record.strategy,
                     models=models, strategies=strategies, slugs=slugs)
    }
    telemetry_all = _read_telemetry(sources.telemetry, country)
    telemetry = {
        slug: flag for slug, flag in telemetry_all.items()
        # A telemetry row carries no axis ids beyond the pair its key was built from, so
        # the filter is applied through the attrition row that shares its slug -- matched
        # against ALL attrition rows, not the selected ones, so a row the filter excluded
        # is dropped here too rather than surfacing as an unexplained key. A telemetry
        # slug with no attrition row at all is deliberately kept: that is a real
        # membership failure and belongs to the reconciliation below, not to the filter.
        if slug not in all_by_slug
        or _selected(slug, all_by_slug[slug].model, all_by_slug[slug].strategy,
                     models=models, strategies=strategies, slugs=slugs)
    }

    _reconcile_membership(
        expected=expected_slugs,
        withdrawn=withdrawn_slugs,
        accuracy=accuracy,
        telemetry=telemetry,
        sources=sources,
    )

    if not expected_slugs:
        raise ValueError(
            f"The cost join for country {country!r} matched no combination at all "
            f"({len(selected_rows)} attrition row(s) selected, {len(withdrawn_slugs)} of them "
            f"withdrawn). An empty join is never a valid result -- it would publish an empty "
            f"cost figure that looks like a measured absence of cost. Check the selection "
            f"filters, or run {_script(PERFORMANCE_PROCESS_ID)} and "
            f"{_script(TELEMETRY_PROCESS_ID)} for this country."
        )

    records = [
        CostRecord(
            slug=slug,
            country=country,
            model=by_slug[slug].model,
            strategy=by_slug[slug].strategy,
            accuracy=accuracy[slug],
            attrition=by_slug[slug],
            cost=raw_cost_for_slug(sources.output_base, slug, by_slug[slug].model, pricing),
            capped_has_token_data=telemetry[slug],
        )
        for slug in sorted(expected_slugs)
    ]

    for record in records:
        # The capped mirror is a strict subset of the generated pool, so "the survivors
        # reported tokens" cannot be true while "the pool reported tokens" is false. The
        # reverse is legitimate and interesting (the discarded personas carried the only
        # telemetry), and is reported by the builder rather than raised.
        if record.capped_has_token_data and not record.cost.has_token_data:
            raise ValueError(
                f"Combination {record.slug!r}: {sources.telemetry} reports "
                f"{_TELEMETRY_TOKEN_FLAG_COLUMN}=True over the capped mirror, but no LLM call "
                f"in the full generated pool under {sources.output_base} reported any token "
                "count. The capped mirror is copied out of that pool, so it cannot hold "
                "telemetry the pool does not. One of the two is stale: re-run "
                f"{_script('population_cap')} and {_script(TELEMETRY_PROCESS_ID)} --force."
            )

    withdrawn = [
        WithdrawnCombination(
            slug=slug,
            model=by_slug[slug].model,
            strategy=by_slug[slug].strategy,
            reason=by_slug[slug].exclusion_reason,
            generated=by_slug[slug].generated,
            clean=by_slug[slug].clean,
            cost=raw_cost_for_slug(sources.output_base, slug, by_slug[slug].model, pricing),
        )
        for slug in sorted(withdrawn_slugs)
    ]

    return JoinResult(
        country=country,
        records=records,
        withdrawn=withdrawn,
        sources=sources,
        pricing=pricing,
        membership={
            "attrition_rows": len(selected_rows),
            "attrition_withdrawn": len(withdrawn_slugs),
            "accuracy_rows": len(accuracy),
            "telemetry_rows": len(telemetry),
            "joined_rows": len(records),
        },
    )

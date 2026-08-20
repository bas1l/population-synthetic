"""builder.py -- derive the cost efficiency quantities and assemble the artifacts. Pure.

Everything here is arithmetic over the records
:mod:`~population_synthetic.analysis.cost_efficiency.loader` joined: no file is opened,
no path is resolved, no figure is drawn. It is the single place ``cost_per_usable_persona``
is computed, so the chart *reads* it rather than recomputing it and the CSV, the JSON and
the figure cannot disagree about a point (guide 02 sect. 9 -- visualization is a pure
sink).

**The one derived quantity, and its denominator.**

``cost_per_usable_persona = total_cost_usd / clean``
    Dollars spent per persona the pipeline could actually **use** -- a persona that
    passed both validity gates. The numerator is the whole run's spend over the full
    generated pool, so a model that generated 549 personas to keep 100 is charged for
    all 549. That is the entire point: measured over the capped mirror instead, the same
    combination reports 5.7 USD rather than 27.3, and the understatement is largest
    exactly where the waste is largest, which would flatter the wasteful models.

    Denominated on ``clean`` rather than on ``selected`` for the reason the attrition
    contract states: ``selected`` is zero for every withdrawn combination and is
    otherwise a cap ceiling (100) rather than a measurement, so it answers a question
    about the cap instead of about the run.

    ``None`` when there is no telemetry to price, or no usable persona to divide by --
    never ``0.0``, which is a real and different claim, and never infinite. A measured
    ``0.0`` occurs and means the model is unmetered.

**There is deliberately no composite score.** No accuracy-per-dollar, no value index, no
combined rank. Two reasons, and the first alone is decisive: every unmetered model is
priced ``{in: 0, out: 0}``, so the division is undefined for each of them -- about a
third of the current grid. The second is that a composite would bury a directional claim
-- how many dollars a point of fidelity is worth -- inside arithmetic no reader can see
or disagree with. The document declares
``non_composite`` as a field so the omission is a stated property rather than an
oversight.

The pooled totals are sums of dollars and of persona counts, both additive, so the pooled
cost per usable persona is a legitimate spend-weighted figure rather than a mean of
per-combination ratios -- which would weight a 110-persona combination equally with a
549-persona one.
"""

from __future__ import annotations

from typing import Any, Sequence

from population_synthetic.analysis.cost_efficiency.loader import JoinResult
from population_synthetic.analysis.cost_efficiency.raw_cost import (
    COST_BASIS,
    RAW_STAGE_DIR,
    pricing_document,
)
from population_synthetic.analysis.utils.cost_csv import (
    SCHEMA_VERSION,
    CostRow,
    decode_pricing_flags,
    encode_pricing_flags,
)

__all__ = [
    "PROCESS_ID",
    "build_document",
    "build_rows",
    "cost_per_usable_persona",
]

#: The canonical analysis-process id this builder's artifacts are stamped with.
PROCESS_ID = "cost_efficiency"

#: The reason ``non_composite`` is declared, carried into the document so it travels
#: with the table rather than living only in this docstring.
_NON_COMPOSITE_REASON = (
    "No accuracy-per-dollar or combined value score is computed. Every unmetered model "
    "is priced {in: 0, out: 0}, so the division is undefined for each of them -- on the "
    "current axis that is about a third of the grid. And a composite would encode a "
    "directional claim -- how many dollars a point of fidelity is worth -- into "
    "arithmetic the reader cannot see or dispute. Accuracy and cost are published side "
    "by side and the trade-off is the reader's."
)

#: What ``unmetered`` does and does not mean, carried as data for the same reason.
_UNMETERED_NOTE = (
    "An unmetered model is priced {in: 0, out: 0} in config/analysis/model_pricing.yaml "
    "-- the local ollama_* models, which this pipeline does not bill for. Its cost is a "
    "MEASURED zero, not an absent one, and unmetered is not free: local inference has a "
    "real hardware, power and operator cost that the pricing config does not model."
)


def cost_per_usable_persona(total_cost_usd: float | None, clean: int) -> float | None:
    """``total_cost_usd / clean``; ``None`` when either side is undefined.

    ``None`` and not ``0.0`` when the cost is absent: an unpriced-because-untelemetered
    run makes no claim about its spend. ``None`` and not infinity when ``clean == 0``: a
    combination with no usable persona has no finite cost per usable persona, and
    writing ``inf`` would let it be plotted, sorted and averaged as though it did.
    """
    if total_cost_usd is None or clean == 0:
        return None
    return total_cost_usd / clean


def build_rows(result: JoinResult) -> list[CostRow]:
    """Build the tidy CSV rows for *result*'s joined records, sorted by slug.

    Sorted rather than left in join order so two runs over the same inputs produce
    byte-identical files.
    """
    rows = [
        CostRow(
            slug=record.slug,
            country=record.country,
            model=record.model,
            strategy=record.strategy,
            overall_tv_similarity=record.accuracy.overall_tv_similarity,
            n_scored=record.accuracy.n_scored,
            generated=record.attrition.generated,
            clean=record.attrition.clean,
            selected=record.attrition.selected,
            # Read from the attrition contract, not recomputed: it is the same quotient
            # over the same two counts, and deriving it twice is how two artifacts come
            # to disagree about one combination.
            generation_multiplier=record.attrition.generation_multiplier,
            n_calls=record.cost.n_calls,
            input_tokens=record.cost.input_tokens,
            output_tokens=record.cost.output_tokens,
            total_tokens=record.cost.total_tokens,
            total_cost_usd=record.cost.total_cost_usd,
            cost_per_usable_persona=cost_per_usable_persona(
                record.cost.total_cost_usd, record.attrition.clean
            ),
            cost_basis=record.cost.cost_basis,
            unmetered=record.cost.unmetered,
            has_token_data=record.cost.has_token_data,
            price_in=record.cost.price_in,
            price_out=record.cost.price_out,
            pricing_flags=encode_pricing_flags(record.cost.pricing_flags),
        )
        for record in result.records
    ]
    return sorted(rows, key=lambda row: row.slug)


def _combination_entry(row: CostRow) -> dict[str, Any]:
    """One combination's JSON entry -- the same quantities the CSV row carries."""
    return {
        "slug": row.slug,
        "model": row.model,
        "strategy": row.strategy,
        "accuracy": {
            "overall_tv_similarity": row.overall_tv_similarity,
            "n_scored": row.n_scored,
        },
        "pool": {
            "generated": row.generated,
            "clean": row.clean,
            "selected": row.selected,
            "generation_multiplier": row.generation_multiplier,
        },
        "telemetry": {
            "n_calls": row.n_calls,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
            "has_token_data": row.has_token_data,
        },
        "cost": {
            "total_cost_usd": row.total_cost_usd,
            "cost_per_usable_persona": row.cost_per_usable_persona,
            "cost_basis": row.cost_basis,
            "unmetered": row.unmetered,
            "price_in": row.price_in,
            "price_out": row.price_out,
            "pricing_flags": list(decode_pricing_flags(row.pricing_flags)),
        },
    }


def _totals(rows: Sequence[CostRow]) -> dict[str, Any]:
    """Pooled spend and pool counts over the metered rows and over all rows.

    The metered subset is reported separately because pooling a measured zero from an
    unmetered model into a dollar total silently claims those runs were free. Both
    denominators travel with their sums.
    """
    metered = [row for row in rows if not row.unmetered and row.total_cost_usd is not None]
    metered_cost = sum(row.total_cost_usd or 0.0 for row in metered)
    metered_clean = sum(row.clean for row in metered)
    return {
        "n_combinations": len(rows),
        "n_unmetered_combinations": sum(1 for row in rows if row.unmetered),
        "n_without_token_data": sum(1 for row in rows if not row.has_token_data),
        "generated": sum(row.generated for row in rows),
        "clean": sum(row.clean for row in rows),
        "selected": sum(row.selected for row in rows),
        "metered": {
            "n_combinations": len(metered),
            "total_cost_usd": metered_cost,
            "clean": metered_clean,
            "cost_per_usable_persona": cost_per_usable_persona(metered_cost, metered_clean),
        },
    }


def _withdrawn_entry(item: Any) -> dict[str, Any]:
    """One withdrawn combination's JSON entry: what it cost and what it yielded."""
    return {
        "slug": item.slug,
        "model": item.model,
        "strategy": item.strategy,
        "reason": item.reason,
        "generated": item.generated,
        "clean": item.clean,
        "total_cost_usd": item.cost.total_cost_usd,
        "cost_basis": item.cost.cost_basis,
        "unmetered": item.cost.unmetered,
        "has_token_data": item.cost.has_token_data,
    }


def _withdrawn_totals(items: Sequence[Any]) -> dict[str, Any]:
    """Pooled spend on the combinations the full-N rule withdrew.

    Metered rows only, for the reason :func:`_totals` gives; the unmetered count travels
    beside it so the total is never read as covering the whole withdrawn set.
    """
    metered = [i for i in items if not i.cost.unmetered and i.cost.total_cost_usd is not None]
    return {
        "n_combinations": len(items),
        "n_metered_combinations": len(metered),
        "generated": sum(i.generated for i in items),
        "clean": sum(i.clean for i in items),
        "metered_total_cost_usd": sum(i.cost.total_cost_usd or 0.0 for i in metered),
    }


def build_document(result: JoinResult) -> dict[str, Any]:
    """Assemble the JSON report for one country.

    Args:
        result: The join, as the loader returned it -- records, withdrawn combinations,
            source paths, pricing table and the per-side row counts.

    Returns:
        A plain dict carrying no timestamp: the caller stamps ``generated_at`` if it
        wants one, which keeps the builder's output byte-reproducible for a fixed input.
    """
    rows = build_rows(result)
    model_ids = [row.model for row in rows] + [item.model for item in result.withdrawn]
    return {
        "process": PROCESS_ID,
        "country": result.country,
        "schema_version": SCHEMA_VERSION,
        "n_combinations": len(rows),
        "cost_basis": COST_BASIS,
        "non_composite": True,
        "non_composite_reason": _NON_COMPOSITE_REASON,
        "unmetered_note": _UNMETERED_NOTE,
        "definitions": {
            "overall_tv_similarity": (
                "model_ranking's headline per-combination fidelity score: mean "
                "total-variation similarity across the analysed attribute axis, over the "
                "capped population of n_scored personas. Higher is better"
            ),
            "generated": (
                "persona_* directories the cap observed under 01_Raw for this combination "
                "-- the pool every token in total_cost_usd was spent on"
            ),
            "clean": "personas passing BOTH validity gates: the pool the seeded cap draws from",
            "generation_multiplier": (
                "generated / clean, read from the validation_attrition contract rather than "
                "recomputed. Not used to correct the cost: the cost here is measured over "
                "the generated pool directly"
            ),
            "total_cost_usd": (
                "the combination's whole LLM spend over the population named by cost_basis, "
                "priced through config/analysis/model_pricing.yaml. Null when the run "
                "reported no token counts -- absent, never zero"
            ),
            "cost_per_usable_persona": (
                "total_cost_usd / clean -- dollars per persona the pipeline could use. Null "
                "when the cost is absent or clean == 0, never 0.0 and never infinite"
            ),
            "cost_basis": (
                "which persona population the cost was totalled over. "
                f"'{COST_BASIS}' is the full generated pool; the alternative basis (the "
                "~100-persona capped mirror that generation_metadata measures) differs from "
                "it by up to 5.5x on the live grid"
            ),
            "unmetered": _UNMETERED_NOTE,
        },
        # The three inputs legitimately hold different row sets; publishing the counts is
        # what makes the output row count auditable rather than merely asserted.
        "membership": {
            **result.membership,
            "rule": (
                "The output row set is the attrition row set minus the withdrawals. It must "
                "equal the model_ranking and generation_metadata row sets exactly; any other "
                "difference raises. A withdrawn combination has neither an accuracy score "
                "nor a capped mirror, so it is reported under 'withdrawn_combinations' "
                "instead of being plotted -- and never silently inner-joined away."
            ),
            "join_key": (
                "The run slug {country}_{strategy}_{model}, built by "
                "generators/synthetic/manifest_loader.py::axis_slug. The "
                "generation_metadata summary carries no slug column, so its key is "
                "reconstructed from its model + method columns by that same function; the "
                "reconstruction is verified on every read against the slug the "
                "model_ranking CSV publishes for the same (model, strategy) pair."
            ),
        },
        "totals": _totals(rows),
        "combinations": [_combination_entry(row) for row in rows],
        "withdrawn_combinations": [_withdrawn_entry(i) for i in result.withdrawn],
        "withdrawn_totals": _withdrawn_totals(result.withdrawn),
        "pricing": pricing_document(result.pricing, model_ids),
        "provenance": {
            "consumed_artifacts": [
                str(result.sources.performance),
                str(result.sources.attrition),
                str(result.sources.telemetry),
            ],
            "cost_source": str(result.sources.output_base / RAW_STAGE_DIR),
        },
    }

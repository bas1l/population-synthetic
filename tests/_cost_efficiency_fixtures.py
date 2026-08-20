"""Shared fixtures for the ``cost_efficiency`` tests: a minimal joinable output base.

``cost_efficiency`` joins three on-disk artifacts written by three other processes and
totals cost over a fourth (the ``01_Raw`` pool), so almost every test needs the same
four-part workspace. It is materialised here, on ``tmp_path``, with every analysis path
resolved through ``analysis_output_dir`` -- no test carries a ``03_Analysis`` literal or
a folder name.

Axis ids are real ones (``all_pick_v2`` / ``all_generate_pick_v2``) because the chart
orders methods through ``strategy_complexity_order``, which reads the repository's axis
config and raises on an unknown id. Model ids are real too, so the hosting classifier can
be exercised where a test wants it. Nothing else here depends on live config: the pricing
table is constructed in memory rather than read from ``model_pricing.yaml``, so a change
to the repository's real prices cannot move a test's expected cost.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from population_synthetic.analysis.cost_efficiency.raw_cost import (
    RAW_STAGE_DIR,
    PricingProvenance,
    RawPricing,
)
from population_synthetic.analysis.utils.attrition_csv import AttritionRow, write_attrition_csv
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.generators.synthetic.manifest_loader import axis_slug
from tests._generation_metadata_fixtures import build_summary_csv, make_row

COUNTRY = "swedish_02"

#: A hosted (metered) model and a local (unmetered) one, so every test set covers both
#: sides of the distinction the figure is built around.
METERED_MODEL = "claude_haiku"
UNMETERED_MODEL = "ollama_llama31_8b"

SIMPLE_STRATEGY = "all_pick_v2"
COMPLEX_STRATEGY = "all_generate_pick_v2"

#: USD per 1,000,000 tokens. Round numbers so an expected cost is checkable by hand.
_RATES: dict[str, tuple[float, float]] = {
    METERED_MODEL: (1.0, 10.0),
    UNMETERED_MODEL: (0.0, 0.0),
}

#: Performance-CSV header. A superset of what the loader reads, matching the producer,
#: which also writes one ``tv_similarity__*`` column per analysed attribute.
_PERFORMANCE_HEADER = (
    "rank", "model", "strategy", "slug", "n", "overall_tv_similarity", "coherence_score",
)


def make_pricing(
    rates: Mapping[str, tuple[float, float]] | None = None,
    *,
    flags: Mapping[str, tuple[str, ...]] | None = None,
) -> RawPricing:
    """An in-memory pricing table, so tests never depend on the repository's real prices."""
    table = dict(_RATES if rates is None else rates)
    flag_map = {model: () for model in table}
    flag_map.update(flags or {})
    return RawPricing(
        rates=table,
        provenance=PricingProvenance(
            observed_date="2026-01-01",
            source="fixture",
            currency="USD",
            config_path="<fixture>",
            flags=flag_map,
        ),
    )


def slug_for(model: str, strategy: str, country: str = COUNTRY) -> str:
    """The run slug, built by the same single source of truth the loader uses."""
    return axis_slug(model, strategy, country)


def write_raw_pool(
    base: Path,
    slug: str,
    *,
    n_personas: int,
    prompt_tokens: int = 1_000,
    completion_tokens: int = 2_000,
    with_tokens: bool = True,
) -> Path:
    """Write ``01_Raw/{slug}/persona_XXX/llm_interactions.jsonl`` for *n_personas*.

    One call per persona, with a unique ``(persona_id, call_index)`` so the reader's
    double-counting guard passes. ``with_tokens=False`` writes calls that report no token
    counts at all, which is the *absent* state -- distinct from a zero cost.
    """
    pool = base / RAW_STAGE_DIR / slug
    for index in range(n_personas):
        persona_id = f"persona_{index:03d}"
        persona_dir = pool / persona_id
        persona_dir.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {"persona_id": persona_id, "call_index": 0}
        if with_tokens:
            record["prompt_tokens"] = prompt_tokens
            record["completion_tokens"] = completion_tokens
            record["total_tokens"] = prompt_tokens + completion_tokens
        with open(persona_dir / "llm_interactions.jsonl", "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    return pool


def make_attrition_row(
    model: str,
    strategy: str,
    *,
    country: str = COUNTRY,
    generated: int = 10,
    clean: int = 8,
    selected: int = 8,
    requested_n: int = 8,
    excluded: bool = False,
    exclusion_reason: str = "",
) -> AttritionRow:
    """One attrition row with the two rates derived exactly as the producer derives them."""
    return AttritionRow(
        slug=axis_slug(model, strategy, country),
        country=country,
        model=model,
        strategy=strategy,
        requested_n=requested_n,
        generated=generated,
        raw_valid=generated,
        mapped_valid=clean,
        clean=clean,
        selected=selected,
        retention_rate=None if generated == 0 else clean / generated,
        generation_multiplier=None if clean == 0 else generated / clean,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        had_surplus=clean > requested_n,
    )


def write_attrition(base: Path, rows: Sequence[AttritionRow], *, country: str = COUNTRY) -> Path:
    """Materialise ``validation_attrition/{country}_attrition.csv`` under *base*."""
    directory = analysis_output_dir("validation_attrition", base)
    directory.mkdir(parents=True, exist_ok=True)
    return write_attrition_csv(rows, directory / f"{country}_attrition.csv")


def write_performance(
    base: Path,
    entries: Iterable[tuple[str, str, float, int]],
    *,
    country: str = COUNTRY,
    slug_override: Mapping[tuple[str, str], str] | None = None,
) -> Path:
    """Materialise ``model_ranking/{country}_performance.csv`` under *base*.

    *entries* are ``(model, strategy, overall_tv_similarity, n)``. *slug_override* lets a
    test publish a slug that disagrees with the ``axis_slug`` rebuild, which is the
    reconstruction check's own regression case.
    """
    directory = analysis_output_dir("model_ranking", base)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{country}_performance.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_PERFORMANCE_HEADER)
        for rank, (model, strategy, tv, n) in enumerate(entries, start=1):
            slug = (slug_override or {}).get((model, strategy), axis_slug(model, strategy, country))
            writer.writerow([rank, model, strategy, slug, n, tv, 0.9])
    return path


def write_telemetry(
    base: Path,
    pairs: Iterable[tuple[str, str]],
    *,
    country: str = COUNTRY,
    has_token_data: Mapping[tuple[str, str], bool] | None = None,
) -> Path:
    """Materialise ``generation_metadata/{country}_summary.csv`` over the pinned header."""
    flags = has_token_data or {}
    rows = [
        make_row(model, method, has_token_data=flags.get((model, method), True))
        for model, method in pairs
    ]
    return build_summary_csv(base, rows, country=country)


def build_base(
    tmp_path: Path,
    *,
    joined: Sequence[tuple[str, str]] = ((METERED_MODEL, SIMPLE_STRATEGY),),
    withdrawn: Sequence[tuple[str, str]] = (),
    country: str = COUNTRY,
    generated: int = 10,
    clean: int = 8,
    accuracy: float = 0.8,
    with_tokens: bool = True,
) -> Path:
    """A complete, consistent output base: three artifacts plus a raw pool per combination.

    *joined* are combinations that survived the gate (present in all three files);
    *withdrawn* are combinations the full-N rule excluded, which appear only in the
    attrition CSV and whose raw pool still exists and still cost money.
    """
    rows = [
        make_attrition_row(model, strategy, country=country, generated=generated,
                           clean=clean, selected=clean, requested_n=clean)
        for model, strategy in joined
    ]
    rows += [
        make_attrition_row(model, strategy, country=country, generated=generated,
                           clean=1, selected=0, requested_n=clean, excluded=True,
                           exclusion_reason="only 1 clean persona(s) pass both validity gates")
        for model, strategy in withdrawn
    ]
    write_attrition(tmp_path, rows, country=country)
    write_performance(
        tmp_path,
        [(model, strategy, accuracy, clean) for model, strategy in joined],
        country=country,
    )
    write_telemetry(tmp_path, joined, country=country)
    for model, strategy in list(joined) + list(withdrawn):
        write_raw_pool(
            tmp_path, axis_slug(model, strategy, country),
            n_personas=generated, with_tokens=with_tokens,
        )
    return tmp_path

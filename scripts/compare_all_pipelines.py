"""
compare_all_pipelines.py -- Batch comparison of all LLM synthetic populations against a reference.

Discovers all model × strategy × country axis combinations, runs the statistical comparison
for each one that has pipeline output, and aggregates results into a summary table and JSON file.

Usage:
    python scripts/compare_all_pipelines.py
    python scripts/compare_all_pipelines.py --country swedish
    python scripts/compare_all_pipelines.py --country swedish --country italian
    python scripts/compare_all_pipelines.py --model claude_haiku --model gemini_flash
    python scripts/compare_all_pipelines.py --strategy all_pick --no-charts
    python scripts/compare_all_pipelines.py --model claude_haiku --strategy all_pick --radar-tv-only

--country        Country axis ID to include (default: swedish). May be repeated.
--model          Model axis ID filter (e.g. claude_haiku). May be repeated. Default: all models.
--strategy       Strategy axis ID filter (e.g. all_pick). May be repeated. Default: all strategies.
--no-charts      Skip chart generation.
--radar-tv-only  On radar chart, show only TV-similarity polygon (omit chi-squared overlay).
"""

import argparse
import json
import sys
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.charts import (
    plot_comparison_charts,
    plot_radar_comparison,
    plot_radar_grid,
)
from population_synth.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synth.comparison.extractor import extract_population
from population_synth.comparison.normalizer import load_mappings, normalize_if_raw
from population_synth.identity.manifest_loader import compose_manifest, discover_axis_values

_COUNTRY_REFERENCES = {
    "swedish": PROJECT_ROOT / "data" / "scb_api" / "scb_population_pop-10000_02.json",
    "italian": PROJECT_ROOT / "data" / "istat_api" / "istat_population.json",
}

_COUNTRY_MAPPINGS = {
    "swedish": PROJECT_ROOT / "config" / "assets" / "scb_reference" / "category_mappings.json",
    "italian": PROJECT_ROOT / "config" / "assets" / "istat_reference" / "category_mappings.json",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch comparison of all LLM synthetic populations against a reference"
    )
    parser.add_argument(
        "--country",
        dest="countries",
        action="append",
        default=None,
        metavar="COUNTRY_ID",
        help="Country axis ID to include (default: swedish). May be repeated.",
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        default=None,
        metavar="MODEL_ID",
        help="Model axis ID filter. May be repeated. Default: all models.",
    )
    parser.add_argument(
        "--strategy",
        dest="strategies",
        action="append",
        default=None,
        metavar="STRATEGY_ID",
        help="Strategy axis ID filter. May be repeated. Default: all strategies.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation.",
    )
    parser.add_argument(
        "--radar-tv-only",
        action="store_true",
        help="On the radar chart, show only the TV-similarity polygon (omit chi-squared p-value overlay).",
    )
    return parser.parse_args()


def _validate_filter_ids(filter_ids: list[str], axis_ids: set[str], axis_name: str) -> None:
    unknown = [fid for fid in filter_ids if fid not in axis_ids]
    if unknown:
        raise ValueError(
            f"Unknown {axis_name} ID(s): {unknown}. "
            f"Valid IDs are: {sorted(axis_ids)}"
        )


def _mean_tv_distance(report: dict) -> float:
    tv_values = [
        m["tv_distance"]
        for m in report["marginals"].values()
        if isinstance(m.get("tv_distance"), float) and m["tv_distance"] == m["tv_distance"]
    ]
    if not tv_values:
        return float("nan")
    return sum(tv_values) / len(tv_values)


def _split_csv(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [v.strip() for item in values for v in item.split(",") if v.strip()] or None


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries) or ["swedish"]
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)

    all_models = discover_axis_values("models")
    all_strategies = discover_axis_values("strategies")
    all_countries = discover_axis_values("countries")

    all_model_ids = {m["id"] for m in all_models}
    all_strategy_ids = {s["id"] for s in all_strategies}
    all_country_ids = {c["id"] for c in all_countries}

    if model_filter:
        _validate_filter_ids(model_filter, all_model_ids, "model")
    if strategy_filter:
        _validate_filter_ids(strategy_filter, all_strategy_ids, "strategy")
    for cid in country_filter:
        if cid not in all_country_ids:
            raise ValueError(
                f"Unknown country ID: {cid!r}. Valid IDs are: {sorted(all_country_ids)}"
            )

    selected_models = [m for m in all_models if model_filter is None or m["id"] in model_filter]
    selected_strategies = [s for s in all_strategies if strategy_filter is None or s["id"] in strategy_filter]
    selected_countries = [c for c in all_countries if c["id"] in country_filter]

    model_strategy_combos = [
        (model["id"], strategy["id"])
        for strategy in selected_strategies
        for model in selected_models
    ]

    total = len(model_strategy_combos) * len(selected_countries)
    print(f"Discovered {total} combination(s) across {len(selected_countries)} country/countries to process.")
    print()

    summary_rows: list[dict] = []
    output_base: Path | None = None

    for country in selected_countries:
        country_id = country["id"]

        reference_path = _COUNTRY_REFERENCES.get(country_id)
        if reference_path is None:
            print(f"ERROR: No reference population configured for country {country_id!r}", file=sys.stderr)
            sys.exit(1)
        if not reference_path.exists():
            print(f"ERROR: Reference file not found: {reference_path}", file=sys.stderr)
            sys.exit(1)

        mappings_path = _COUNTRY_MAPPINGS.get(country_id)
        if mappings_path is None:
            print(f"ERROR: No category mappings configured for country {country_id!r}", file=sys.stderr)
            sys.exit(1)

        with open(reference_path, "r", encoding="utf-8") as f:
            reference_pop_raw = json.load(f)

        mappings = load_mappings(path=mappings_path)
        reference_pop = normalize_if_raw(reference_pop_raw, mappings, country=country_id)

        print(f"=== {country_id.upper()} (reference: {reference_path.name}) ===")
        print()

        radar_grid_data: dict[tuple[str, str], dict] = {}

        for model_id, strategy_id in model_strategy_combos:
            slug = f"{country_id}_{strategy_id}_{model_id}"
            print(f"[{slug}] Processing...")

            try:
                manifest = compose_manifest(model_id, strategy_id, country_id)
            except FileNotFoundError as exc:
                print(f"  SKIP: axis file missing -- {exc}")
                continue

            if output_base is None and manifest.comparison_output_dir is not None:
                output_base = manifest.comparison_output_dir.parent.parent

            seed_root = manifest.parallel_output_dir
            if seed_root is None or not seed_root.exists():
                print(f"  SKIP: parallel_output_dir does not exist: {seed_root}")
                continue

            persona_files = list(seed_root.glob("persona_*/identity.json"))
            if not persona_files:
                print(f"  SKIP: no persona_*/identity.json files found under {seed_root}")
                continue

            try:
                pipeline_pop = extract_population(seed_root, country=country_id)
            except ValueError as exc:
                print(f"  SKIP: {exc}")
                continue

            n_pipeline = pipeline_pop["metadata"]["n"]
            if n_pipeline < 5:
                print(f"  WARNING: only {n_pipeline} extracted individuals -- statistical tests unreliable")

            evaluator = StatisticalEvaluator(reference_pop, pipeline_pop)
            report = evaluator.generate_report()

            comparison_output_dir = manifest.comparison_output_dir
            if comparison_output_dir is None:
                if output_base is not None:
                    comparison_output_dir = output_base / "03_Analysis" / slug
                else:
                    comparison_output_dir = PROJECT_ROOT / "data" / "analysis" / slug

            comparison_output_dir.mkdir(parents=True, exist_ok=True)
            output_path = comparison_output_dir / f"{slug}.json"

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"  Report written to {output_path}")

            csv_path = output_path.with_suffix(".csv")
            write_csv_summary(report, csv_path)
            print(f"  CSV written to {csv_path}")

            if not args.no_charts:
                charts_dir = comparison_output_dir / slug
                plot_comparison_charts(
                    reference_pop,
                    pipeline_pop,
                    charts_dir,
                    pop_a_label=reference_path.stem,
                    pop_b_label=slug,
                    prefix=slug,
                )
                print(f"  Charts written to {charts_dir}")
                radar_path = plot_radar_comparison(
                    report["marginals"],
                    charts_dir,
                    pop_a_label=reference_path.stem,
                    pop_b_label=slug,
                    show_chi_sq=not args.radar_tv_only,
                    prefix=slug,
                )
                if radar_path is not None:
                    print(f"  Radar chart written to {radar_path}")

            radar_grid_data[(model_id, strategy_id)] = report["marginals"]

            mean_tv = _mean_tv_distance(report)
            coherence_score = report["coherence"]["score"]

            summary_rows.append({
                "model": model_id,
                "strategy": strategy_id,
                "country": country_id,
                "n": n_pipeline,
                "mean_tv_distance": round(mean_tv, 4),
                "coherence_score": coherence_score,
            })
            print()

        if output_base is None:
            output_base = PROJECT_ROOT / "data" / "analysis"

        summary_dir = output_base / "03_Analysis"
        summary_dir.mkdir(parents=True, exist_ok=True)

        if not args.no_charts and radar_grid_data:
            grid_path = plot_radar_grid(
                radar_grid_data,
                summary_dir,
                prefix=country_id,
            )
            if grid_path is not None:
                print(f"Radar grid written to {grid_path}")

    if not summary_rows:
        print("No pipeline output found for any combination.")
        sys.exit(0)

    print()
    print("=" * 80)
    print(f"{'COUNTRY':<10} {'MODEL':<22} {'STRATEGY':<32} {'N':>5}  {'MEAN TV':>8}  {'COHERENCE':>9}")
    print("-" * 80)
    for row in summary_rows:
        print(
            f"{row['country']:<10} {row['model']:<22} {row['strategy']:<32} {row['n']:>5}  "
            f"{row['mean_tv_distance']:>8.4f}  {row['coherence_score']:>9.4f}"
        )
    print("=" * 80)

    if output_base is None:
        output_base = PROJECT_ROOT / "data" / "analysis"

    summary_dir = output_base / "03_Analysis"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "comparison_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_rows, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written to {summary_path}")


if __name__ == "__main__":
    main()

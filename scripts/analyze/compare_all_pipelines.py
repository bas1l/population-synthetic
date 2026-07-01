"""
compare_all_pipelines.py -- Batch comparison of mapped synthetic populations against a reference.

Consumes the pre-mapped files produced by the map stage (scripts/analyze/map_populations.py):
it iterates {output_base}/03_Analysis/mapped/_index.json, json.loads each mapped synthetic
population and the shared mapped database for its country, runs the statistical comparison, and
aggregates results into a summary table and JSON file. This script performs NO mapping -- run
map_populations.py first.

Usage:
    python scripts/analyze/compare_all_pipelines.py
    python scripts/analyze/compare_all_pipelines.py --country swedish
    python scripts/analyze/compare_all_pipelines.py --country swedish --country italian
    python scripts/analyze/compare_all_pipelines.py --model claude_haiku --model gemini_flash
    python scripts/analyze/compare_all_pipelines.py --strategy all_pick --no-charts
    python scripts/analyze/compare_all_pipelines.py --model claude_haiku --strategy all_pick --radar-tv-only

--country        Country axis ID filter (default: all countries in the mapped index). May be repeated.
--model          Model axis ID filter (e.g. claude_haiku). May be repeated. Default: all models.
--strategy       Strategy axis ID filter (e.g. all_pick). May be repeated. Default: all strategies.
--output-base    Base output directory (the 03_Analysis parent). Default: experiment_defaults.yaml.
--no-charts      Skip chart generation.
--radar-tv-only  On radar chart, show only TV-similarity polygon (omit chi-squared overlay).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from population_synth._paths import PROJECT_ROOT
from population_synth.llm_metrics.cross_run.comparison_loader import decompose_slug
from population_synth.comparison.charts import (
    plot_comparison_charts,
    plot_radar_comparison,
    plot_radar_grid,
)
from population_synth.comparison.country_config import mappings_for_country
from population_synth.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synth.comparison.scheme import load_scheme
from population_synth.identity.manifest_loader import discover_axis_values

_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch comparison of mapped synthetic populations against a reference"
    )
    parser.add_argument(
        "--country",
        dest="countries",
        action="append",
        default=None,
        metavar="COUNTRY_ID",
        help="Country axis ID filter (default: all countries in the mapped index). May be repeated.",
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
        "--output-base",
        default=None,
        help="Base output directory (the 03_Analysis parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
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


def _resolve_output_base(cli_value: str | None) -> Path:
    """Resolve output_base from the CLI flag or experiment_defaults.yaml."""
    if cli_value:
        return Path(cli_value)
    with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
        defaults = yaml.safe_load(f) or {}
    output_base = (defaults.get("parameters") or {}).get("output_base")
    if not output_base:
        print(
            f"ERROR: no output_base in {_DEFAULTS_PATH} and --output-base not given",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(output_base)


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


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
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
    if country_filter:
        _validate_filter_ids(country_filter, all_country_ids, "country")

    # Registries for decomposing {country}_{strategy}_{model} slugs (radar grid keys + filters).
    country_ids = sorted(all_country_ids)
    strategy_ids = sorted(all_strategy_ids)
    model_ids = sorted(all_model_ids)

    output_base = _resolve_output_base(args.output_base)
    mapped_dir = output_base / "03_Analysis" / "mapped"
    comparison_dir = output_base / "03_Analysis" / "comparison"

    index_path = mapped_dir / "_index.json"
    if not index_path.exists():
        print(
            f"ERROR: mapped index not found: {index_path}\n"
            "Run scripts/analyze/map_populations.py first to produce the mapped populations.",
            file=sys.stderr,
        )
        sys.exit(1)

    index_entries = _load_json(index_path)
    print(f"Loaded {len(index_entries)} mapped target(s) from {index_path}")
    print(f"Comparison output dir: {comparison_dir}")
    print()

    summary_rows: list[dict] = []

    # Group entries by country so the shared mapped database is loaded once per country.
    countries_in_index = [c for c in country_ids if any(e["country"] == c for e in index_entries)]
    # Preserve any country present in the index even if not a known axis id.
    for entry in index_entries:
        if entry["country"] not in countries_in_index:
            countries_in_index.append(entry["country"])

    for country_id in countries_in_index:
        if country_filter and country_id not in country_filter:
            continue

        country_entries = [e for e in index_entries if e["country"] == country_id]
        if not country_entries:
            continue

        # Load the shared mapped database for this country once.
        database_pop: dict | None = None
        database_label = f"database_{country_id}"

        mappings_path = mappings_for_country(country_id)
        scheme = load_scheme(country_id, mappings_path=mappings_path)

        print(f"=== {country_id.upper()} ===")
        print()

        radar_grid_data: dict[tuple[str, str], dict] = {}

        for entry in country_entries:
            slug = entry["slug"]

            if entry.get("skipped") is True or entry.get("synthetic_file") is None:
                print(f"[{slug}] SKIP: no mapped synthetic file (skipped during mapping).")
                continue

            # Model/strategy filters apply only when the slug decomposes to a known axis combo.
            decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
            if model_filter or strategy_filter:
                if decomposed is None:
                    print(f"[{slug}] SKIP: cannot apply model/strategy filter to non-axis slug.")
                    continue
                _, strategy_id, model_id = decomposed
                if model_filter and model_id not in model_filter:
                    continue
                if strategy_filter and strategy_id not in strategy_filter:
                    continue

            synthetic_path = mapped_dir / entry["synthetic_file"]
            if not synthetic_path.exists():
                print(f"[{slug}] SKIP: mapped synthetic file not found: {synthetic_path}")
                continue

            if database_pop is None:
                database_file = entry.get("database_file")
                if database_file is None:
                    print(f"[{slug}] SKIP: no mapped database recorded for {country_id}.")
                    continue
                database_path = mapped_dir / database_file
                if not database_path.exists():
                    print(
                        f"ERROR: mapped database not found: {database_path}\n"
                        "Run scripts/analyze/map_populations.py first.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                database_pop = _load_json(database_path)
                database_label = database_path.stem

            print(f"[{slug}] Processing...")
            synthetic_pop = _load_json(synthetic_path)

            n_synthetic = synthetic_pop["metadata"]["n"]
            if n_synthetic < 5:
                print(f"  WARNING: only {n_synthetic} extracted individuals -- statistical tests unreliable")

            evaluator = StatisticalEvaluator(database_pop, synthetic_pop, scheme=scheme)
            report = evaluator.generate_report()

            comparison_output_dir = comparison_dir / slug
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
                    database_pop,
                    synthetic_pop,
                    charts_dir,
                    pop_a_label=database_label,
                    pop_b_label=slug,
                    prefix=slug,
                    attributes=scheme.attributes,
                    categories=scheme.categories,
                )
                print(f"  Charts written to {charts_dir}")
                radar_path = plot_radar_comparison(
                    report["marginals"],
                    charts_dir,
                    pop_a_label=database_label,
                    pop_b_label=slug,
                    show_chi_sq=not args.radar_tv_only,
                    prefix=slug,
                    attributes=scheme.attributes,
                )
                if radar_path is not None:
                    print(f"  Radar chart written to {radar_path}")

            if decomposed is not None:
                _, strategy_id, model_id = decomposed
                radar_grid_data[(model_id, strategy_id)] = report["marginals"]

            mean_tv = _mean_tv_distance(report)
            coherence_score = report["coherence"]["score"]

            summary_rows.append({
                "model": decomposed[2] if decomposed else "",
                "strategy": decomposed[1] if decomposed else "",
                "slug": slug,
                "country": country_id,
                "n": n_synthetic,
                "mean_tv_distance": round(mean_tv, 4),
                "coherence_score": coherence_score,
            })
            print()

        comparison_dir.mkdir(parents=True, exist_ok=True)
        if not args.no_charts and radar_grid_data:
            grid_path = plot_radar_grid(
                radar_grid_data,
                comparison_dir,
                prefix=country_id,
                attributes=scheme.attributes,
            )
            if grid_path is not None:
                print(f"Radar grid written to {grid_path}")

    if not summary_rows:
        print("No mapped synthetic populations found to compare.")
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

    comparison_dir.mkdir(parents=True, exist_ok=True)
    summary_path = comparison_dir / "comparison_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_rows, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written to {summary_path}")


if __name__ == "__main__":
    main()

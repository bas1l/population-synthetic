"""
score_fidelity_all.py -- Batch comparison of mapped synthetic populations against a real population.

Consumes the pre-mapped files produced by the map stage (scripts/analyze/map_populations.py):
it iterates the analysis-stage mapping folder's _index.json, json.loads each mapped synthetic
population and the shared mapped real population for its country, runs the statistical comparison, and
aggregates results into a summary table and JSON file. This script performs NO mapping -- run
map_populations.py first.

Usage:
    python scripts/analyze/score_fidelity_all.py
    python scripts/analyze/score_fidelity_all.py --country swedish
    python scripts/analyze/score_fidelity_all.py --country swedish --country italian
    python scripts/analyze/score_fidelity_all.py --model claude_haiku --model gemini_flash
    python scripts/analyze/score_fidelity_all.py --strategy all_pick --no-charts
    python scripts/analyze/score_fidelity_all.py --model claude_haiku --strategy all_pick --radar-tv-only
    python scripts/analyze/score_fidelity_all.py --slug swedish_all_pick_claude_haiku
    python scripts/analyze/score_fidelity_all.py --n-synthetic 100 --sample-seed 0
    python scripts/analyze/score_fidelity_all.py --force

--country        Country axis ID filter (default: all countries in the mapped index). May be repeated.
--model          Model axis ID filter (e.g. claude_haiku). May be repeated. Default: all models.
--strategy       Strategy axis ID filter (e.g. all_pick). May be repeated. Default: all strategies.
--slug           Exact slug filter ({country}_{strategy}_{model}). May be repeated. Keeps only the
                 mapped entries whose slug is selected. Combines with --model/--strategy/--country.
--output-base    Base output directory (the analysis-stage parent). Default: experiment_defaults.yaml.
--no-charts      Skip chart generation.
--radar-tv-only  On radar chart, show only TV-similarity polygon (omit chi-squared overlay).
--n-synthetic    Cap each synthetic population to this many individuals via a seeded without-replacement
                 draw, restoring equivalent population size for the size-sensitive metrics. Blank/omitted
                 = no cap (current behaviour). Populations smaller than N run in full with a loud warning.
--sample-seed    Seed for the without-replacement subsample draw (default 0; reproducible).
--force          Recompute a slug even if its fidelity/{slug}/{slug}.json already exists (default:
                 reload the existing per-slug report so it still feeds the summary + radar grid).
"""

import argparse
import json
import sys
from pathlib import Path

from population_synthetic.analysis.fidelity.artifacts import write_comparison_artifacts
from population_synthetic.analysis.fidelity.charts import plot_radar_grid
from population_synthetic.analysis.fidelity.evaluator import StatisticalEvaluator
from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.utils.axes import decompose_slug
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.country_config import mappings_for_country
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.analysis.utils.sampling import subsample_population
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch comparison of mapped synthetic populations against a real population"
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
        "--slug",
        dest="slugs",
        action="append",
        default=None,
        metavar="SLUG",
        help="Exact slug filter ({country}_{strategy}_{model}). May be repeated. "
        "Keeps only the mapped entries whose slug is selected.",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the analysis-stage parent). "
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
    parser.add_argument(
        "--n-synthetic",
        type=int,
        default=None,
        metavar="N",
        help="Cap each synthetic population to N individuals via a seeded without-replacement draw "
        "(equivalent-size comparison). Blank/omitted = no cap. Smaller populations run in full with a "
        "loud warning.",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=0,
        metavar="SEED",
        help="Seed for the --n-synthetic without-replacement subsample draw (default: 0; reproducible).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute a slug even if its fidelity/{slug}/{slug}.json already exists "
        "(default: reload the existing per-slug report so it still feeds the summary + radar grid).",
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


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)
    slug_filter = _split_csv(args.slugs)

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

    output_base = resolve_output_base(args.output_base)
    mapped_dir = resolve_mapped_dir(output_base)
    comparison_dir = analysis_output_dir("fidelity", output_base)

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

    # Group entries by country so the shared mapped real population is loaded once per country.
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

        # Load the shared mapped real population for this country once.
        real_pop: dict | None = None
        real_label = f"real_{country_id}"

        mappings_path = mappings_for_country(country_id)
        scheme = load_scheme(country_id, mappings_path=mappings_path)

        print(f"=== {country_id.upper()} ===")
        print()

        radar_grid_data: dict[tuple[str, str], dict] = {}

        for entry in country_entries:
            slug = entry["slug"]

            if slug_filter and slug not in slug_filter:
                continue

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

            comparison_output_dir = comparison_dir / slug
            output_path = comparison_output_dir / f"{slug}.json"

            # Idempotent skip: reload the existing per-slug report rather than recomputing, so it
            # still contributes to the summary + radar grid (Full comparison output invariant). Only
            # recompute when forced or the report is absent. `n` comes from the stored report's
            # population_b block; the stored marginals/coherence feed the aggregates directly.
            if not args.force and output_path.exists():
                report = _load_json(output_path)
                n_synthetic = report["metadata"]["population_b"]["n"]
                print(f"[{slug}] SKIP (exists): {output_path}")
            else:
                if real_pop is None:
                    real_file = entry.get("real_file")
                    if real_file is None:
                        print(f"[{slug}] SKIP: no mapped real population recorded for {country_id}.")
                        continue
                    real_path = mapped_dir / real_file
                    if not real_path.exists():
                        print(
                            f"ERROR: mapped real population not found: {real_path}\n"
                            "Run scripts/analyze/map_populations.py first.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    real_pop = _load_json(real_path)
                    real_label = real_path.stem

                print(f"[{slug}] Processing...")
                synthetic_pop = _load_json(synthetic_path)
                synthetic_pop = subsample_population(synthetic_pop, args.n_synthetic, args.sample_seed)

                n_synthetic = synthetic_pop["metadata"]["n"]
                if n_synthetic < 5:
                    print(f"  WARNING: only {n_synthetic} extracted individuals -- statistical tests unreliable")

                evaluator = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme)
                report = evaluator.generate_report()

                write_comparison_artifacts(
                    report, real_pop, synthetic_pop, output_path, scheme,
                    slug=slug, real_label=real_label,
                    no_charts=args.no_charts, radar_tv_only=args.radar_tv_only,
                )

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

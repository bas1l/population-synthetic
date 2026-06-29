"""
compare_pipeline_to_istat.py -- Extract pipeline persona identities and compare them against
an ISTAT reference population in a single step.

Usage:
    python scripts/compare_pipeline_to_istat.py \\
        --manifest config/seed_manifests/identity_manifest_xxx.yaml \\
        [--reference <istat_population.json>] \\
        [--output comparison_report.json] \\
        [--save-extracted pipeline_population.json] \\
        [--charts-dir <dir>] \\
        [--no-charts] \\
        [--radar-tv-only]

    python scripts/compare_pipeline_to_istat.py \\
        --seed-root <path> \\
        [--reference <istat_population.json>] \\
        [--output comparison_report.json] \\
        [--save-extracted pipeline_population.json] \\
        [--charts-dir <dir>] \\
        [--no-charts] \\
        [--radar-tv-only]

--manifest       Seed manifest YAML; derives --seed-root from parallel.output_dir.
--seed-root      Directory containing persona_XXXXX/identity.json files (pipeline output).
--reference      ISTAT reference population file (default: data/istat_api/istat_population.json).
--output         Path for the JSON comparison report (default: data/comparison_report.json).
--save-extracted If provided, also save the flattened pipeline population to this path.
"""

import argparse
import json
import sys
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.charts import plot_comparison_charts, plot_radar_comparison
from population_synth.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synth.comparison.extractor import extract_population
from population_synth.comparison.normalizer import load_mappings, normalize_if_raw

_DEFAULT_REFERENCE = PROJECT_ROOT / "data" / "istat_api" / "istat_population.json"
_ISTAT_MAPPINGS_PATH = PROJECT_ROOT / "config" / "comparison" / "category_mappings" / "istat"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract pipeline identities and compare against an ISTAT reference population"
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Seed manifest YAML; derives --seed-root from parallel.output_dir",
    )
    parser.add_argument(
        "--model-id", default=None,
        help="Axis model ID (e.g., 'claude_haiku') -- mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--strategy-id", default=None,
        help="Axis strategy ID (e.g., 'all_pick') -- mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--country-id", default=None,
        help="Axis country ID (e.g., 'italian') -- mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--seed-root", default=None,
        help="Pipeline seed output directory",
    )
    parser.add_argument(
        "--reference",
        default=str(_DEFAULT_REFERENCE),
        help=f"ISTAT reference population JSON file (default: {_DEFAULT_REFERENCE.name})",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON report path (default: data/analysis/compare_with_istat/<name>.json)",
    )
    parser.add_argument(
        "--save-extracted",
        default=None,
        help="Optional: save the flattened pipeline population to this path",
    )
    parser.add_argument(
        "--charts-dir",
        default=None,
        help="Directory to write comparison chart PNGs. Defaults to data/analysis/<output_stem>/",
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
    args = parser.parse_args()

    axis_ids = [args.model_id, args.strategy_id, args.country_id]
    if args.manifest and any(x is not None for x in axis_ids):
        parser.error("--manifest is mutually exclusive with --model-id, --strategy-id, and --country-id")

    m = None
    if args.manifest:
        from population_synth.identity.manifest_loader import load_manifest
        m = load_manifest(args.manifest)
        if args.seed_root is None and m.parallel_output_dir is not None:
            args.seed_root = str(m.parallel_output_dir)
    elif args.model_id is not None:
        if args.strategy_id is None or args.country_id is None:
            parser.error("--model-id, --strategy-id, and --country-id must all be provided together")
        from population_synth.identity.manifest_loader import compose_manifest
        m = compose_manifest(args.model_id, args.strategy_id, args.country_id)
        if args.seed_root is None and m.parallel_output_dir is not None:
            args.seed_root = str(m.parallel_output_dir)

    if not args.seed_root:
        parser.error("Either --manifest (with parallel.output_dir) or --seed-root is required")

    seed_root = Path(args.seed_root)
    if not seed_root.exists():
        print(f"ERROR: Seed root does not exist: {seed_root}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    elif m is not None and m.comparison_output_dir is not None:
        output_path = m.comparison_output_dir / f"{seed_root.name}.json"
    else:
        output_path = PROJECT_ROOT / "data" / "analysis" / "compare_with_istat" / f"{seed_root.name}.json"

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"ERROR: Reference file not found: {reference_path}", file=sys.stderr)
        sys.exit(1)

    try:
        pipeline_pop = extract_population(seed_root, country="italian")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.save_extracted:
        save_path = Path(args.save_extracted)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(pipeline_pop, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Extracted population saved to {save_path}")

    with open(reference_path, "r", encoding="utf-8") as f:
        reference_pop = json.load(f)

    mappings = load_mappings(path=_ISTAT_MAPPINGS_PATH)

    reference_pop = normalize_if_raw(reference_pop, mappings, country="italian")

    if pipeline_pop["metadata"]["n"] < 5:
        n = pipeline_pop["metadata"]["n"]
        print(f"WARNING: Pipeline population has only {n} individuals"
              " -- statistical tests will be unreliable.\n")

    evaluator = StatisticalEvaluator(reference_pop, pipeline_pop)
    evaluator.print_summary(args.reference, args.seed_root)

    report = evaluator.generate_report()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to {output_path}")

    csv_path = output_path.with_suffix(".csv")
    write_csv_summary(report, csv_path)
    print(f"CSV summary written to {csv_path}")

    if not args.no_charts:
        import shutil
        if args.charts_dir is not None:
            charts_dir = Path(args.charts_dir)
        else:
            charts_dir = output_path.parent / output_path.stem
        if charts_dir.exists():
            shutil.rmtree(charts_dir)
        plot_comparison_charts(
            reference_pop,
            pipeline_pop,
            charts_dir,
            pop_a_label=Path(args.reference).stem,
            pop_b_label=seed_root.name,
            prefix=seed_root.name,
        )
        print(f"Charts written to {charts_dir}")
        radar_path = plot_radar_comparison(
            report["marginals"],
            charts_dir,
            pop_a_label=Path(args.reference).stem,
            pop_b_label=seed_root.name,
            show_chi_sq=not args.radar_tv_only,
            prefix=seed_root.name,
        )
        if radar_path is not None:
            print(f"Radar chart written to {radar_path}")


if __name__ == "__main__":
    main()

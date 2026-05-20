"""
compare_pipeline_to_scb.py -- Extract pipeline persona identities and compare them against
an SCB reference population in a single step.

Usage:
    python scripts/compare_pipeline_to_scb.py \\
        --manifest config/seed_manifests/identity_manifest_022_claude_sonnet.yaml \\
        [--reference <scb_population.json>] \\
        [--output comparison_report.json] \\
        [--save-extracted pipeline_population.json] \\
        [--charts-dir <dir>] \\
        [--no-charts] \\
        [--radar-tv-only]

    python scripts/compare_pipeline_to_scb.py \\
        --seed-root <path> \\
        [--reference <scb_population.json>] \\
        [--output comparison_report.json] \\
        [--save-extracted pipeline_population.json] \\
        [--charts-dir <dir>] \\
        [--no-charts] \\
        [--radar-tv-only]

--manifest       Seed manifest YAML; derives --seed-root from parallel.output_dir.
--seed-root      Directory containing persona_XXXXX/identity.json files (pipeline output).
--reference      SCB reference population file (default: data/scb_api/scb_population_pop-10000_02.json).
--output         Path for the JSON comparison report (default: data/comparison_report.json).
--save-extracted If provided, also save the flattened pipeline population to this path.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.extractor import extract_individual
from population_synth.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synth.comparison.normalizer import load_mappings, normalize_if_raw
from population_synth.comparison.charts import plot_comparison_charts, plot_radar_comparison

_DEFAULT_REFERENCE = PROJECT_ROOT / "data" / "scb_api" / "scb_population_pop-10000_02.json"


# ---------------------------------------------------------------------------
# Extraction step
# ---------------------------------------------------------------------------

def extract_population(seed_root: Path) -> dict[str, Any]:
    identity_files = sorted(seed_root.glob("persona_*/identity.json"))
    if not identity_files:
        print(f"ERROR: No persona_*/identity.json files found under {seed_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(identity_files)} identity files under {seed_root}")

    individuals: list[dict[str, Any]] = []
    skipped = 0
    for path in identity_files:
        result = extract_individual(path)
        if result is None:
            skipped += 1
        else:
            individuals.append(result)

    if skipped:
        print(f"WARNING: Skipped {skipped} persona(s) due to errors or missing data", file=sys.stderr)

    return {
        "metadata": {
            "source": "pipeline",
            "seed_root": str(seed_root.resolve()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": len(individuals),
            "skipped": skipped,
        },
        "individuals": individuals,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract pipeline identities and compare against an SCB reference population"
    )
    parser.add_argument("--manifest", default=None, help="Seed manifest YAML; derives --seed-root from parallel.output_dir")
    parser.add_argument("--seed-root", default=None, help="Pipeline seed output directory")
    parser.add_argument(
        "--reference",
        default=str(_DEFAULT_REFERENCE),
        help=f"SCB reference population JSON file (default: {_DEFAULT_REFERENCE.name})",
    )
    parser.add_argument("--output", default=None, help="Output JSON report path (default: data/analysis/compare_with_scb02/<seed-root-name>.json)")
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

    if args.manifest:
        from population_synth.identity.manifest_loader import load_manifest
        m = load_manifest(args.manifest)
        if args.seed_root is None and m.parallel_output_dir is not None:
            args.seed_root = str(m.parallel_output_dir)

    if not args.seed_root:
        parser.error("Either --manifest (with parallel.output_dir) or --seed-root is required")

    seed_root = Path(args.seed_root)
    if not seed_root.exists():
        print(f"ERROR: Seed root does not exist: {seed_root}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "analysis" / "compare_with_scb02" / f"{seed_root.name}.json"

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"ERROR: Reference file not found: {reference_path}", file=sys.stderr)
        sys.exit(1)

    pipeline_pop = extract_population(seed_root)

    if args.save_extracted:
        save_path = Path(args.save_extracted)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(pipeline_pop, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Extracted population saved to {save_path}")

    with open(reference_path, "r", encoding="utf-8") as f:
        reference_pop = json.load(f)

    mappings = load_mappings()

    reference_pop = normalize_if_raw(reference_pop, mappings)

    if pipeline_pop["metadata"]["n"] < 5:
        print(f"WARNING: Pipeline population has only {pipeline_pop['metadata']['n']} individuals -- statistical tests will be unreliable.\n")

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
        )
        print(f"Charts written to {charts_dir}")
        radar_path = plot_radar_comparison(
            report["marginals"],
            charts_dir,
            pop_a_label=Path(args.reference).stem,
            pop_b_label=seed_root.name,
            show_chi_sq=not args.radar_tv_only,
        )
        if radar_path is not None:
            print(f"Radar chart written to {radar_path}")


if __name__ == "__main__":
    main()

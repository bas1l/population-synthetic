"""
compare_pipeline_to_istat.py -- Compare a pre-mapped synthetic population against a pre-mapped
ISTAT real population (Italy).

This script performs NO mapping. It consumes the mapped files produced by the map stage
(scripts/analyze/map_populations.py): the mapped synthetic population {mapped-dir}/{slug}.json
and the shared mapped real population {mapped-dir}/real_italian.json. Run map_populations.py first.

Usage:
    python scripts/analyze/compare_pipeline_to_istat.py \\
        --manifest config/synthetic/manifests/identity_manifest_xxx.yaml \\
        [--mapped-dir <dir>] \\
        [--output comparison_report.json] \\
        [--charts-dir <dir>] [--no-charts] [--radar-tv-only]

    python scripts/analyze/compare_pipeline_to_istat.py \\
        --seed-root <path> \\
        [--mapped-dir <dir>] [--output comparison_report.json] ...

    python scripts/analyze/compare_pipeline_to_istat.py \\
        --mapped-synthetic <dir>/<slug>.json \\
        --mapped-real <dir>/real_italian.json

--manifest         Seed manifest YAML; derives the slug from parallel.output_dir basename.
--seed-root        Pipeline seed output directory; the slug is its basename.
--mapped-dir       Directory holding the mapped files (default: {output_base}/03_Analysis/mapped).
--mapped-synthetic Explicit path to the mapped synthetic population JSON (overrides --mapped-dir/{slug}).
--mapped-real      Explicit path to the mapped real population JSON (overrides real_italian.json).
--output           Path for the JSON comparison report (default: 03_Analysis/comparison/{slug}/{slug}.json).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.comparison.charts import plot_comparison_charts, plot_radar_comparison
from population_synthetic.analysis.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synthetic.analysis.comparison.scheme import load_scheme

_COUNTRY = "italian"
_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


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


def _load_mapped(path: Path, label: str) -> dict:
    """json.load a pre-mapped population file, with a clear error if it is absent."""
    if not path.exists():
        print(
            f"ERROR: Mapped {label} file not found: {path}. "
            "Run scripts/analyze/map_populations.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare a pre-mapped synthetic population against a pre-mapped ISTAT real population"
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Seed manifest YAML; derives the slug from parallel.output_dir basename",
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
        help="Pipeline seed output directory; the slug is its basename",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the 03_Analysis parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--mapped-dir",
        default=None,
        help="Directory holding the mapped files (default: {output_base}/03_Analysis/mapped).",
    )
    parser.add_argument(
        "--mapped-synthetic",
        default=None,
        help="Explicit path to the mapped synthetic population JSON (overrides --mapped-dir/{slug}.json).",
    )
    parser.add_argument(
        "--mapped-real",
        default=None,
        help="Explicit path to the mapped real population JSON (overrides real_italian.json).",
    )
    parser.add_argument(
        "--real-label",
        default=None,
        help="Display label for the real population (default: mapped real file stem).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON report path (default: 03_Analysis/comparison/{slug}/{slug}.json)",
    )
    parser.add_argument(
        "--charts-dir",
        default=None,
        help="Directory to write comparison chart PNGs. Defaults to <output_parent>/<output_stem>/.",
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

    manifest = None
    seed_name: str | None = None
    if args.manifest:
        from population_synthetic.generators.synthetic.manifest_loader import load_manifest
        manifest = load_manifest(args.manifest)
        if manifest.parallel_output_dir is not None:
            seed_name = manifest.parallel_output_dir.name
    elif args.model_id is not None:
        if args.strategy_id is None or args.country_id is None:
            parser.error("--model-id, --strategy-id, and --country-id must all be provided together")
        from population_synthetic.generators.synthetic.manifest_loader import compose_manifest
        manifest = compose_manifest(args.model_id, args.strategy_id, args.country_id)
        if manifest.parallel_output_dir is not None:
            seed_name = manifest.parallel_output_dir.name

    if args.seed_root:
        seed_name = Path(args.seed_root).name

    if seed_name is None:
        if args.mapped_synthetic:
            seed_name = Path(args.mapped_synthetic).stem
        else:
            parser.error(
                "Cannot determine the run slug: provide --manifest, the axis IDs, --seed-root, "
                "or an explicit --mapped-synthetic path."
            )
    slug = seed_name

    output_base = _resolve_output_base(args.output_base)
    mapped_dir = Path(args.mapped_dir) if args.mapped_dir else output_base / "03_Analysis" / "mapped"

    synthetic_path = Path(args.mapped_synthetic) if args.mapped_synthetic else mapped_dir / f"{slug}.json"
    real_path = Path(args.mapped_real) if args.mapped_real else mapped_dir / f"real_{_COUNTRY}.json"

    synthetic_pop = _load_mapped(synthetic_path, "synthetic")
    real_pop = _load_mapped(real_path, "real")

    real_label = Path(args.real_label).stem if args.real_label else real_path.stem

    if args.output:
        output_path = Path(args.output)
    elif manifest is not None and manifest.comparison_output_dir is not None:
        output_path = manifest.comparison_output_dir / f"{slug}.json"
    else:
        output_path = output_base / "03_Analysis" / "comparison" / slug / f"{slug}.json"

    if synthetic_pop["metadata"]["n"] < 5:
        n = synthetic_pop["metadata"]["n"]
        print(f"WARNING: Synthetic population has only {n} individuals"
              " -- statistical tests will be unreliable.\n")

    scheme = load_scheme(_COUNTRY)
    evaluator = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme)
    evaluator.print_summary(real_label, slug)

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
            real_pop,
            synthetic_pop,
            charts_dir,
            pop_a_label=real_label,
            pop_b_label=slug,
            prefix=slug,
            attributes=scheme.attributes,
            categories=scheme.categories,
        )
        print(f"Charts written to {charts_dir}")
        radar_path = plot_radar_comparison(
            report["marginals"],
            charts_dir,
            pop_a_label=real_label,
            pop_b_label=slug,
            show_chi_sq=not args.radar_tv_only,
            prefix=slug,
            attributes=scheme.attributes,
        )
        if radar_path is not None:
            print(f"Radar chart written to {radar_path}")


if __name__ == "__main__":
    main()

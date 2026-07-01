"""
compare_populations.py -- Statistical comparison of two demographic population files.

Usage:
    python scripts/analyze/compare_populations.py <pop_a.json> <pop_b.json> [--output data/comparison_report.json]

pop_a is the reference population (treated as "expected" for chi-squared).
pop_b is the population to evaluate (treated as "observed").

This is a thin CLI wrapper that delegates all heavy lifting to
population_synth.comparison.{evaluator, normalizer, charts}.
"""

import argparse
import json
import sys
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.charts import plot_comparison_charts, plot_radar_comparison
from population_synth.comparison.evaluator import StatisticalEvaluator, write_csv_summary
from population_synth.comparison.reference_mapper import normalize_population
from population_synth.comparison.scheme import load_scheme


def _load_population(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two demographic population files statistically")
    parser.add_argument("pop_a", help="Reference population file (expected)")
    parser.add_argument("pop_b", help="Population to evaluate (observed)")
    parser.add_argument(
        "--country",
        required=True,
        choices=("swedish", "italian"),
        help="Country whose comparison scheme (config/mapping/{scb,istat}) defines the "
             "axis and category sets. Required -- there is no in-code default.",
    )
    parser.add_argument("--output", default="data/comparison_report.json", help="Output JSON report path")
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

    pop_a = _load_population(args.pop_a)
    pop_b = _load_population(args.pop_b)

    pop_a = normalize_population(pop_a, country=args.country)
    pop_b = normalize_population(pop_b, country=args.country)

    scheme = load_scheme(args.country)
    evaluator = StatisticalEvaluator(pop_a, pop_b, scheme=scheme)
    evaluator.print_summary(args.pop_a, args.pop_b)

    report = evaluator.generate_report()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport written to {output_path}")

    csv_path = output_path.with_suffix(".csv")
    write_csv_summary(report, csv_path)
    print(f"CSV summary written to {csv_path}")

    if not args.no_charts:
        if args.charts_dir is not None:
            charts_dir = Path(args.charts_dir)
        else:
            charts_dir = PROJECT_ROOT / "data" / "analysis" / output_path.stem
        plot_comparison_charts(
            pop_a,
            pop_b,
            charts_dir,
            pop_a_label=Path(args.pop_a).stem,
            pop_b_label=Path(args.pop_b).stem,
            prefix=Path(args.pop_b).stem,
            attributes=scheme.attributes,
            categories=scheme.categories,
        )
        print(f"Charts written to {charts_dir}")
        radar_path = plot_radar_comparison(
            report["marginals"],
            charts_dir,
            pop_a_label=Path(args.pop_a).stem,
            pop_b_label=Path(args.pop_b).stem,
            show_chi_sq=not args.radar_tv_only,
            prefix=Path(args.pop_b).stem,
            attributes=scheme.attributes,
        )
        if radar_path is not None:
            print(f"Radar chart written to {radar_path}")


if __name__ == "__main__":
    main()

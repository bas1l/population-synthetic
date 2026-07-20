"""
score_fidelity.py -- Statistical comparison of two demographic population files.

Two invocation modes:

Positional-file mode (raw files, mapped on the fly)
    python scripts/analyze/score_fidelity.py <pop_a.json> <pop_b.json> --country swedish \
        [--output <report.json>]

    pop_a is the real population (treated as "expected" for chi-squared).
    pop_b is the population to evaluate (treated as "observed").

Slug mode (exactly two pre-mapped pipelines)
    python scripts/analyze/score_fidelity.py --slug swedish_all_pick_claude_haiku \
        --slug swedish_all_pick_gemini_flash

    Each --slug loads the mapped {slug}.json from the analysis-stage mapping folder (already
    mapped by scripts/analyze/map_populations.py; resolved via the analysis registry). The
    country is derived from the slugs via decompose_slug and both slugs must share one
    country. Fails loudly if a mapped file is missing. The first slug is treated as pop_a
    (expected), the second as pop_b (observed).

By default the report, its CSV summary, and the charts are written under the
``pairwise_comparison`` analysis folder (``{output_base}/03_Analysis/pairwise_comparison/``);
``--output`` / ``--charts-dir`` override the report / chart locations.

--force  Recompute even if the --output report already exists (default: skip if present).
         python scripts/analyze/score_fidelity.py --slug A --slug B --force

This is a thin CLI wrapper that delegates all heavy lifting to
population_synthetic.analysis.fidelity.{evaluator, charts} and
population_synthetic.analysis.mapping.normalizer.
"""

import argparse
import json
import sys
from pathlib import Path

from population_synthetic.analysis.fidelity.charts import plot_comparison_charts, plot_radar_comparison
from population_synthetic.analysis.fidelity.evaluator import StatisticalEvaluator, write_csv_summary
from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.mapping.real_mapper import map_population
from population_synthetic.analysis.utils.axes import decompose_slug
from population_synthetic.analysis.utils.registry import analysis_output_dir, resolve_output_base
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values


def _load_population(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_slug_pair(slugs: list[str], output_base: Path) -> tuple[dict, dict, str, str, str]:
    """Resolve exactly two slugs to (pop_a, pop_b, label_a, label_b, country).

    Loads the pre-mapped {slug}.json from the analysis-stage mapping folder (resolved via
    the registry, with a legacy-read fallback to the pre-rename ``mapped/`` folder) for each
    slug, derives the country from the slugs and validates both share one country. Raises
    loudly on a wrong slug count, an unknown slug, a country mismatch, or a missing mapped
    file.
    """
    if len(slugs) != 2:
        raise ValueError(
            f"--slug mode requires exactly two slugs, got {len(slugs)}: {slugs}"
        )

    country_ids = [d["id"] for d in discover_axis_values("countries")]
    strategy_ids = [d["id"] for d in discover_axis_values("strategies")]
    model_ids = [d["id"] for d in discover_axis_values("models")]

    countries: list[str] = []
    for slug in slugs:
        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            raise ValueError(
                f"--slug {slug!r} is not a known axis combination "
                f"({{country}}_{{strategy}}_{{model}}); cannot derive its country."
            )
        countries.append(decomposed[0])

    if countries[0] != countries[1]:
        raise ValueError(
            f"Both slugs must share one country; got {countries[0]!r} ({slugs[0]}) "
            f"and {countries[1]!r} ({slugs[1]})."
        )
    country = countries[0]

    mapped_dir = analysis_output_dir("mapping", output_base, for_read=True)
    pops: list[dict] = []
    for slug in slugs:
        mapped_path = mapped_dir / f"{slug}.json"
        if not mapped_path.exists():
            raise FileNotFoundError(
                f"Mapped population not found: {mapped_path}\n"
                "Run scripts/analyze/map_populations.py first to produce the mapped populations."
            )
        with open(mapped_path, "r", encoding="utf-8") as f:
            pops.append(json.load(f))

    return pops[0], pops[1], slugs[0], slugs[1], country


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two demographic population files statistically")
    parser.add_argument("pop_a", nargs="?", default=None, help="Real population file (expected)")
    parser.add_argument("pop_b", nargs="?", default=None, help="Population to evaluate (observed)")
    parser.add_argument(
        "--slug",
        dest="slugs",
        action="append",
        default=None,
        metavar="SLUG",
        help="Slug of a pre-mapped pipeline ({country}_{strategy}_{model}); pass exactly twice. "
        "Loads the mapped {slug}.json from the analysis-stage mapping folder and derives "
        "--country from the slugs.",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the 03_Analysis parent). Used to resolve the mapped "
        "inputs (slug mode) and the default report/charts location under the "
        "pairwise_comparison analysis folder. "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--country",
        default=None,
        choices=("swedish", "italian"),
        help="Country whose comparison scheme (config/mapping/{scb,istat}) defines the "
             "axis and category sets. Required for positional-file mode; derived from the "
             "slugs in --slug mode.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON report path. Default: "
        "{output_base}/03_Analysis/pairwise_comparison/comparison_report.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute even if the --output report already exists (default: skip if present).",
    )
    parser.add_argument(
        "--charts-dir",
        default=None,
        help="Directory to write comparison chart PNGs. "
        "Defaults to {output_base}/03_Analysis/pairwise_comparison/<output_stem>/.",
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

    # The output_base anchors both the mapped inputs (slug mode) and the default report /
    # charts location under the pairwise_comparison analysis folder, so resolve it up front.
    output_base = resolve_output_base(args.output_base)
    if args.output is not None:
        output_path = Path(args.output)
    else:
        output_path = analysis_output_dir("pairwise_comparison", output_base) / "comparison_report.json"

    # Idempotent skip: the single JSON report is the unit of work here, so if it already
    # exists and --force was not passed, skip before doing any heavy evaluation.
    if not args.force and output_path.exists():
        print(f"SKIP (exists): {output_path}")
        sys.exit(0)

    if args.slugs is not None:
        # --- Slug mode: exactly two pre-mapped pipelines, country derived from the slugs.
        if args.pop_a is not None or args.pop_b is not None:
            print("ERROR: --slug mode does not take positional pop_a/pop_b files.", file=sys.stderr)
            sys.exit(1)
        pop_a, pop_b, label_a, label_b, country = _resolve_slug_pair(args.slugs, output_base)
    else:
        # --- Positional-file mode: raw files, mapped on the fly.
        if args.pop_a is None or args.pop_b is None:
            print("ERROR: positional pop_a and pop_b are required (or pass --slug twice).", file=sys.stderr)
            sys.exit(1)
        if args.country is None:
            print("ERROR: --country is required in positional-file mode.", file=sys.stderr)
            sys.exit(1)
        country = args.country
        label_a = Path(args.pop_a).stem
        label_b = Path(args.pop_b).stem
        pop_a = map_population(_load_population(args.pop_a), country=country)
        pop_b = map_population(_load_population(args.pop_b), country=country)

    scheme = load_scheme(country)
    evaluator = StatisticalEvaluator(pop_a, pop_b, scheme=scheme)
    evaluator.print_summary(label_a, label_b)

    report = evaluator.generate_report()
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
            charts_dir = analysis_output_dir("pairwise_comparison", output_base) / output_path.stem
        plot_comparison_charts(
            pop_a,
            pop_b,
            charts_dir,
            pop_a_label=label_a,
            pop_b_label=label_b,
            prefix=label_b,
            attributes=scheme.attributes,
            categories=scheme.categories,
        )
        print(f"Charts written to {charts_dir}")
        radar_path = plot_radar_comparison(
            report["marginals"],
            charts_dir,
            pop_a_label=label_a,
            pop_b_label=label_b,
            show_chi_sq=not args.radar_tv_only,
            prefix=label_b,
            attributes=scheme.attributes,
        )
        if radar_path is not None:
            print(f"Radar chart written to {radar_path}")


if __name__ == "__main__":
    main()

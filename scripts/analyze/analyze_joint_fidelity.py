"""
analyze_joint_fidelity.py -- Standalone multivariate joint-fidelity of mapped synthetic populations.

Consumes the pre-mapped files produced by the map stage (scripts/analyze/map_populations.py):
it iterates {output_base}/03_Analysis/mapped/_index.json, json.loads each mapped synthetic
population and the shared mapped real population for its country, recomputes ONLY the
multivariate / joint-fidelity block (C2ST, pairwise Cramer's-V association, per-pair joint TV,
k-way combination plausibility) via the shared StatisticalEvaluator, and writes it to its own
{output_base}/03_Analysis/joint_fidelity/ folder. This is additive: it never touches the
comparison or performance outputs. This script performs NO mapping -- run map_populations.py first.

Usage:
    python scripts/analyze/analyze_joint_fidelity.py
    python scripts/analyze/analyze_joint_fidelity.py --country swedish
    python scripts/analyze/analyze_joint_fidelity.py --slug swedish_all_pick_claude_sonnet
    python scripts/analyze/analyze_joint_fidelity.py --slug swedish_all_pick_claude_sonnet --no-charts

--country      Country axis ID filter (default: all countries in the mapped index). May be repeated.
--slug         Exact slug filter ({country}_{strategy}_{model}). May be repeated. Keeps only the
               mapped entries whose slug is selected. Combines with --country.
--output-base  Base output directory (the 03_Analysis parent). Default: experiment_defaults.yaml.
--no-charts    Skip chart generation.

Outputs, under {output_base}/03_Analysis/joint_fidelity/:
    {slug}/{slug}.json                          per-combo joint-fidelity envelope
    {slug}/{slug}_association.csv               pairwise Cramer's-V fidelity table
    {slug}/{slug}/{slug}_association_heatmap.png per-combo |Delta V| heatmap (opt-out)
    {country}_joint_fidelity.json               per-country roll-up (one row per combo)
    {country}_joint_fidelity.csv                per-country roll-up (one row per combo)
    {country}_c2st_vs_grounded_tv.png           cross-combo C2ST-vs-grounded-TV scatter (opt-out)
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.comparison.evaluator import write_association_csv
from population_synthetic.analysis.comparison.scheme import load_scheme
from population_synthetic.analysis.joint_fidelity.builder import (
    aggregate_joint_fidelity,
    build_joint_fidelity,
    write_joint_fidelity_csv,
    write_joint_fidelity_json,
)
from population_synthetic.analysis.joint_fidelity.charts import (
    plot_c2st_vs_grounded_tv,
    plot_joint_association_heatmap,
)
from population_synthetic.analysis.utils.country_config import mappings_for_country

_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone multivariate joint-fidelity of mapped synthetic populations"
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
        help="Base output directory (the 03_Analysis parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation.",
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
    slug_filter = _split_csv(args.slugs)

    output_base = _resolve_output_base(args.output_base)
    mapped_dir = output_base / "03_Analysis" / "mapped"
    joint_dir = output_base / "03_Analysis" / "joint_fidelity"

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
    print(f"Joint-fidelity output dir: {joint_dir}")
    print()

    # Group entries by country so the shared mapped real population is loaded once per country.
    countries_in_index: list[str] = []
    for entry in index_entries:
        if entry["country"] not in countries_in_index:
            countries_in_index.append(entry["country"])

    processed = 0
    for country_id in countries_in_index:
        if country_filter and country_id not in country_filter:
            continue

        country_entries = [e for e in index_entries if e["country"] == country_id]
        if not country_entries:
            continue

        # Load the shared mapped real population + scheme for this country once.
        real_pop: dict | None = None
        scheme = load_scheme(country_id, mappings_path=mappings_for_country(country_id))

        print(f"=== {country_id.upper()} ===")
        print()

        envelopes: list[dict] = []

        for entry in country_entries:
            slug = entry["slug"]

            if slug_filter and slug not in slug_filter:
                continue

            if entry.get("skipped") is True or entry.get("synthetic_file") is None:
                print(f"[{slug}] SKIP: no mapped synthetic file (skipped during mapping).")
                continue

            synthetic_path = mapped_dir / entry["synthetic_file"]
            if not synthetic_path.exists():
                print(f"[{slug}] SKIP: mapped synthetic file not found: {synthetic_path}")
                continue

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

            print(f"[{slug}] Processing...")
            synthetic_pop = _load_json(synthetic_path)

            n_synthetic = synthetic_pop["metadata"]["n"]
            if n_synthetic < 5:
                print(f"  WARNING: only {n_synthetic} extracted individuals -- statistical tests unreliable")

            envelope = build_joint_fidelity(
                real_pop, synthetic_pop, scheme, slug=slug, country=country_id
            )
            envelopes.append(envelope)

            slug_dir = joint_dir / slug
            output_path = write_joint_fidelity_json(envelope, slug_dir / f"{slug}.json")
            print(f"  Report written to {output_path}")

            association_csv_path = slug_dir / f"{slug}_association.csv"
            write_association_csv(envelope, association_csv_path)
            print(f"  Association CSV written to {association_csv_path}")

            if not args.no_charts:
                charts_dir = slug_dir / slug
                heatmap = plot_joint_association_heatmap(
                    envelope, charts_dir, prefix=slug, attributes=scheme.attributes
                )
                if heatmap is not None:
                    print(f"  Association heatmap written to {heatmap}")

            print()

        if not envelopes:
            continue

        rows = aggregate_joint_fidelity(envelopes)
        joint_dir.mkdir(parents=True, exist_ok=True)

        rollup_json = joint_dir / f"{country_id}_joint_fidelity.json"
        with open(rollup_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print(f"Roll-up written to {rollup_json}")

        rollup_csv = write_joint_fidelity_csv(rows, joint_dir / f"{country_id}_joint_fidelity.csv")
        print(f"Roll-up CSV written to {rollup_csv}")

        if not args.no_charts:
            scatter = plot_c2st_vs_grounded_tv(
                rows, joint_dir / f"{country_id}_c2st_vs_grounded_tv.png", country=country_id
            )
            if scatter is not None:
                print(f"C2ST-vs-grounded-TV scatter written to {scatter}")

        print()
        processed += 1

    if processed == 0:
        print("No mapped synthetic populations found for joint-fidelity analysis.")
        sys.exit(0)


if __name__ == "__main__":
    main()

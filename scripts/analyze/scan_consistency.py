"""
scan_consistency.py -- Detection-only consistency scan of mapped populations.

Consumes the pre-mapped files produced by the map stage (scripts/analyze/map_populations.py):
it iterates the analysis-stage mapping folder's _index.json, and for every country in scope
scans the shared mapped real reference population plus each requested mapped synthetic
population (--slug) against the country's config-driven consistency-rule list
(config/analysis/consistency/{country}.yaml). This never modifies the generator or the
mapped files -- it only reports internally-inconsistent attribute combinations (e.g. a
"retired" individual younger than 55) as violation counts/rates, per rule. This script
performs NO mapping -- run map_populations.py first.

Usage:
    python scripts/analyze/scan_consistency.py
    python scripts/analyze/scan_consistency.py --country swedish
    python scripts/analyze/scan_consistency.py --slug swedish_all_pick_claude_sonnet
    python scripts/analyze/scan_consistency.py --slug swedish_all_pick_claude_sonnet --no-charts
    python scripts/analyze/scan_consistency.py --force

--country      Country axis ID filter (default: all countries in the mapped index). May be repeated.
--slug         Exact slug filter ({country}_{strategy}_{model}). May be repeated. Keeps only the
               mapped entries whose slug is selected. Combines with --country. The mapped real
               reference population for each in-scope country is ALWAYS scanned regardless of
               --slug (this is what answers whether the generator itself produces inconsistent
               combinations, and lets a synthetic slug's rate be compared against it).
--output-base  Base output directory (the analysis-stage parent). Default: experiment_defaults.yaml.
--no-charts    Skip chart generation.
--force        Recompute a country even if its consistency/{country}_consistency.json already
               exists (default: skip a country whose output already exists).

Outputs, under the analysis-stage consistency folder:
    {country}_consistency.json          per-rule counts + rates, one entry per scanned population
    {country}_consistency.csv           flat table (population, rule_id, severity, violations, rate)
    {population}/violations_examples.csv  capped sample of offending records for that population
                                           (population = "real_{country}" or a synthetic slug)
    {country}_consistency_bar.png       per-rule violation-rate bars (unless --no-charts)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from population_synthetic.analysis.consistency.builder import (
    build_summary_rows,
    scan_population,
    write_report_json,
    write_summary_csv,
    write_violations_csv,
)
from population_synthetic.analysis.consistency.charts import plot_violation_rates
from population_synthetic.analysis.consistency.rules import load_rules
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detection-only consistency scan of mapped populations against a config-driven rule list"
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
        "Keeps only the mapped entries whose slug is selected. The real reference "
        "population is always scanned regardless of this filter.",
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
        "--force",
        action="store_true",
        help="Recompute a country even if its consistency/{country}_consistency.json "
        "already exists (default: skip a country whose output already exists).",
    )
    return parser.parse_args()


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

    output_base = resolve_output_base(args.output_base)
    mapped_dir = analysis_output_dir("mapping", output_base, for_read=True)
    consistency_dir = analysis_output_dir("consistency", output_base)

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
    print(f"Consistency-scan output dir: {consistency_dir}")
    print()

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

        rollup_json = consistency_dir / f"{country_id}_consistency.json"
        if not args.force and rollup_json.exists():
            print(f"[{country_id}] SKIP (exists): {rollup_json}")
            print()
            continue

        print(f"=== {country_id.upper()} ===")
        print()

        rules = load_rules(country_id)
        print(f"Loaded {len(rules)} consistency rule(s) for {country_id!r}.")

        real_file = next((e.get("real_file") for e in country_entries if e.get("real_file")), None)
        if real_file is None:
            print(f"[{country_id}] SKIP: no mapped real population recorded.")
            print()
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
        real_population_id = f"real_{country_id}"
        print(f"[{real_population_id}] Scanning (n={real_pop['metadata']['n']})...")
        reports = [
            scan_population(
                real_pop["individuals"], rules, population=real_population_id, country=country_id
            )
        ]

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

            synthetic_pop = _load_json(synthetic_path)
            print(f"[{slug}] Scanning (n={synthetic_pop['metadata']['n']})...")
            reports.append(
                scan_population(synthetic_pop["individuals"], rules, population=slug, country=country_id)
            )

        for report in reports:
            slug_dir = consistency_dir / report.population
            violations_path = write_violations_csv(report, slug_dir / "violations_examples.csv")
            print(f"  [{report.population}] Violations examples written to {violations_path}")

        consistency_dir.mkdir(parents=True, exist_ok=True)
        json_path = write_report_json(reports, rollup_json)
        print(f"Report written to {json_path}")

        rows = build_summary_rows(reports)
        csv_path = write_summary_csv(rows, consistency_dir / f"{country_id}_consistency.csv")
        print(f"Summary CSV written to {csv_path}")

        if not args.no_charts:
            bar_path = plot_violation_rates(
                rows, consistency_dir / f"{country_id}_consistency_bar.png", country=country_id
            )
            if bar_path is not None:
                print(f"Violation-rate bar chart written to {bar_path}")

        print()
        processed += 1

    if processed == 0:
        print("No mapped populations found for consistency scanning.")
        sys.exit(0)


if __name__ == "__main__":
    main()

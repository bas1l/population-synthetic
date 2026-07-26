"""
analyze_real_population_stats.py -- Real-population reference statistics (real-only).

Standalone leaf analysis stage: for one or more countries, reads the already-mapped
real reference population (``03_Analysis/mapping/real_{country}.json``, written by
``map_populations.py``) and renders publication-ready per-category reference
figures -- one bar chart + CSV per analyzed attribute (config-driven via
``ComparisonScheme.attributes``), plus a combined overview panel -- under
``03_Analysis/real_population_stats/{country}/``.

No synthetic population, no comparison metric: this is the real side only, useful
for manuscript reference figures and per-category proportion tables independent of
any model/strategy comparison.

Usage:
    python scripts/analyze/analyze_real_population_stats.py --country-id swedish
    python scripts/analyze/analyze_real_population_stats.py --country-id swedish --country-id italian
    python scripts/analyze/analyze_real_population_stats.py --country-id swedish --force
    python scripts/analyze/analyze_real_population_stats.py --country-id swedish --dpi 300
    python scripts/analyze/analyze_real_population_stats.py --country-id swedish --no-charts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.real_population_stats.artifacts import (
    write_real_population_stats,
)
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.country_config import known_country_ids
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render publication-ready reference figures + CSVs for one or more "
        "countries' real (API-sourced) reference population -- no synthetic comparison."
    )
    parser.add_argument(
        "--country-id",
        dest="country_ids",
        action="append",
        default=None,
        metavar="COUNTRY_ID",
        help="Country axis ID to analyze (e.g. 'swedish'). May be repeated. "
        "Default: every known country id.",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the analysis-stage parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute a country's outputs even if they already exist "
        "(default: skip a country whose output folder already has content).",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="PNG render resolution. Default: 200.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip figure rendering (PNG/SVG, including the overview); still writes "
        "the per-attribute proportion CSVs.",
    )
    return parser.parse_args()


def _load_real_population(country: str, mapping_dir: Path) -> dict:
    """Load ``real_{country}.json`` from the mapping stage; fail-fast if absent."""
    real_path = mapping_dir / f"real_{country}.json"
    if not real_path.is_file():
        raise FileNotFoundError(
            f"No mapped real population for country {country!r}: {real_path} not found. "
            "Run the 'mapping' analysis task first "
            "(python scripts/analyze/map_populations.py --country-id "
            f"{country} --model-id <model> --strategy-id <strategy>, or the batch targets form)."
        )
    with open(real_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _country_has_outputs(country_dir: Path) -> bool:
    """Whether *country_dir* already holds any rendered artifact (idempotent-skip probe)."""
    return country_dir.is_dir() and any(country_dir.iterdir())


def main() -> None:
    args = _parse_args()

    known = known_country_ids()
    country_ids = args.country_ids if args.country_ids else list(known)
    unknown = [cid for cid in country_ids if cid not in known]
    if unknown:
        print(
            f"ERROR: unknown country id(s) {unknown}: valid ids are {sorted(known)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_base = resolve_output_base(args.output_base)
    out_root = analysis_output_dir("real_population_stats", output_base)
    mapping_dir = resolve_mapped_dir(output_base)

    for country in country_ids:
        country_dir = out_root / country
        print(f"=== {country.upper()} ===")

        if not args.force and _country_has_outputs(country_dir):
            print(f"  SKIP (outputs exist): {country_dir}")
            print()
            continue

        real_pop = _load_real_population(country, mapping_dir)
        scheme = load_scheme(country)

        written = write_real_population_stats(
            real_pop,
            scheme,
            country_dir,
            dpi=args.dpi,
            force=args.force,
            charts=not args.no_charts,
        )

        print(f"  {len(written)} file(s) written under {country_dir}")
        print()


if __name__ == "__main__":
    main()

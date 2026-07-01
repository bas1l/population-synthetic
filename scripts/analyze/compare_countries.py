"""Compare marginal distributions across Sweden, Norway, and Italy populations.

Usage:
    python scripts/analyze/compare_countries.py
    python scripts/analyze/compare_countries.py --sweden <path> --norway <path> --italy <path>
    python scripts/analyze/compare_countries.py --output report.json --no-charts
"""

import argparse
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from population_synth.analysis.comparison.evaluator import StatisticalEvaluator
from population_synth.analysis.comparison.scheme import load_scheme
from population_synth.analysis.mapping.flatten_raw import flatten_raw_population
from population_synth.analysis.mapping.reference_mapper.mappings import load_mappings
from population_synth.analysis.utils.country_config import mappings_for_country

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_SWEDEN = "data/scb_api/scb_population_pop-10000_02.json"
_DEFAULT_NORWAY = "data/ssb_api/ssb_10k.json"
_DEFAULT_ITALY = "data/istat_api/istat_population.json"

COMPARABLE_FIELDS = frozenset({
    "age_group",
    "biological_sex",
    "socioeconomic_class",
})


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _marginal(individuals: list[dict], attr: str) -> dict[str, float]:
    counts: Counter = Counter()
    for ind in individuals:
        val = ind.get(attr)
        if val is not None:
            counts[val] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.most_common()}


def _pairwise_report(evaluator: StatisticalEvaluator) -> dict:
    report = evaluator.generate_report()
    return report.get("marginals", {})


def _print_summary(
    populations: dict[str, dict],
    pairwise: dict[str, dict],
    attributes: list[str],
) -> None:
    print("\n==== Cross-Country Population Comparison ====")
    for label, pop in populations.items():
        n = len(pop.get("individuals", []))
        source = pop.get("metadata", {}).get("source", "?")
        print(f"  {label:8s}: n={n:,}  ({source})")

    pair_names = list(pairwise.keys())

    print(f"\n{'Attribute':<28s}", end="")
    for pn in pair_names:
        print(f"  {pn:>12s}", end="")
    print("   Note")
    print("-" * (28 + 14 * len(pair_names) + 8))

    for attr in attributes:
        note = "comparable" if attr in COMPARABLE_FIELDS else "labels differ"
        print(f"{attr:<28s}", end="")
        for pn in pair_names:
            metrics = pairwise[pn].get(attr, {})
            tv = metrics.get("tv_distance", float("nan"))
            if tv != tv:  # NaN check
                print(f"  {'N/A':>12s}", end="")
            else:
                print(f"  {tv:>12.4f}", end="")
        print(f"   {note}")

    print("\n--- Summary (comparable fields only) ---")
    print(f"{'Pair':<16s}  {'Mean TV':>8s}  {'Mean KL':>8s}")
    for pn in pair_names:
        tvs, kls = [], []
        for attr in COMPARABLE_FIELDS:
            m = pairwise[pn].get(attr, {})
            tv = m.get("tv_distance")
            kl = m.get("kl_divergence")
            if tv is not None and tv == tv:
                tvs.append(tv)
            if kl is not None and kl == kl:
                kls.append(kl)
        mean_tv = sum(tvs) / len(tvs) if tvs else float("nan")
        mean_kl = sum(kls) / len(kls) if kls else float("nan")
        print(f"{pn:<16s}  {mean_tv:>8.4f}  {mean_kl:>8.4f}")

    print()


def _build_json_report(
    populations: dict[str, dict],
    pairwise: dict[str, dict],
    paths: dict[str, str],
    attributes: list[str],
) -> dict:
    pop_meta = {}
    for label, pop in populations.items():
        meta = pop.get("metadata", {})
        pop_meta[label] = {
            "source": meta.get("source", "?"),
            "n": len(pop.get("individuals", [])),
            "path": paths.get(label, "?"),
        }

    marginals: dict[str, dict] = {}
    for attr in attributes:
        attr_data: dict[str, dict[str, float]] = {}
        for label, pop in populations.items():
            attr_data[label] = _marginal(pop["individuals"], attr)
        marginals[attr] = attr_data

    comparable_summary: dict[str, dict] = {}
    all_summary: dict[str, dict] = {}
    for pn, metrics in pairwise.items():
        comp_tvs, comp_kls = [], []
        all_tvs, all_kls = [], []
        for attr in attributes:
            m = metrics.get(attr, {})
            tv = m.get("tv_distance")
            kl = m.get("kl_divergence")
            if tv is not None and tv == tv:
                all_tvs.append(tv)
                if attr in COMPARABLE_FIELDS:
                    comp_tvs.append(tv)
            if kl is not None and kl == kl:
                all_kls.append(kl)
                if attr in COMPARABLE_FIELDS:
                    comp_kls.append(kl)
        comparable_summary[pn] = {
            "mean_tv": sum(comp_tvs) / len(comp_tvs) if comp_tvs else None,
            "mean_kl": sum(comp_kls) / len(comp_kls) if comp_kls else None,
        }
        all_summary[pn] = {
            "mean_tv": sum(all_tvs) / len(all_tvs) if all_tvs else None,
            "mean_kl": sum(all_kls) / len(all_kls) if all_kls else None,
        }

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "populations": pop_meta,
            "comparable_fields": sorted(COMPARABLE_FIELDS),
        },
        "marginals": marginals,
        "pairwise": {pn: {a: _sanitize(m) for a, m in metrics.items()} for pn, metrics in pairwise.items()},
        "summary": {
            "comparable_fields_only": comparable_summary,
            "all_fields": all_summary,
        },
    }


def _sanitize(metrics: dict) -> dict:
    """Replace NaN with None for JSON serialization."""
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in metrics.items()}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare population distributions across Sweden, Norway, and Italy"
    )
    parser.add_argument("--sweden", type=str, default=_DEFAULT_SWEDEN, help="Swedish population JSON")
    parser.add_argument("--norway", type=str, default=_DEFAULT_NORWAY, help="Norwegian population JSON")
    parser.add_argument("--italy", type=str, default=_DEFAULT_ITALY, help="Italian population JSON")
    parser.add_argument("--output", type=str, default="data/cross_country/cross_country_report.json")
    parser.add_argument("--charts-dir", type=str, default="data/cross_country/charts")
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation")
    parser.add_argument(
        "--reference-country",
        choices=("swedish", "italian"),
        default="swedish",
        help="Country whose comparison scheme (config/mapping/{scb,istat}) supplies the "
             "shared comparison axis for this cross-country run. The canonical attribute "
             "names are country-independent; category sets come from this scheme.",
    )
    args = parser.parse_args()

    scheme = load_scheme(args.reference_country)
    # Sex vocabulary for the generic flattener comes from the reference country's
    # biological_sex config (not a hardcoded map).
    sex_config = load_mappings(mappings_for_country(args.reference_country))["biological_sex"]

    logger.info("Loading populations...")
    swe_raw = _load_json(args.sweden)
    nor_raw = _load_json(args.norway)
    ita_raw = _load_json(args.italy)

    logger.info("Flattening raw records...")
    swe = flatten_raw_population(swe_raw, sex_config=sex_config, country_label="Sweden")
    nor = flatten_raw_population(nor_raw, sex_config=sex_config, country_label="Norway")
    ita = flatten_raw_population(ita_raw, sex_config=sex_config, country_label="Italy")

    populations = {"Sweden": swe, "Norway": nor, "Italy": ita}
    paths = {"Sweden": args.sweden, "Norway": args.norway, "Italy": args.italy}

    pairs = [
        ("SWE vs NOR", swe, nor),
        ("SWE vs ITA", swe, ita),
        ("NOR vs ITA", nor, ita),
    ]

    logger.info("Running pairwise statistical comparisons...")
    pairwise: dict[str, dict] = {}
    for pair_name, pop_a, pop_b in pairs:
        evaluator = StatisticalEvaluator(pop_a, pop_b, scheme=scheme)
        pairwise[pair_name] = _pairwise_report(evaluator)

    _print_summary(populations, pairwise, scheme.attributes)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = _build_json_report(populations, pairwise, paths, scheme.attributes)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("JSON report written to %s", output_path)

    if not args.no_charts:
        from population_synth.analysis.comparison.charts import (
            plot_3way_comparison_charts,
            plot_3way_radar,
        )

        charts_dir = Path(args.charts_dir)
        logger.info("Generating charts in %s ...", charts_dir)
        plot_3way_comparison_charts(
            swe, nor, ita,
            labels=("Sweden", "Norway", "Italy"),
            output_dir=charts_dir,
            attributes=scheme.attributes,
            prefix="cross_country",
        )
        plot_3way_radar(
            pairwise,
            labels=("SWE vs NOR", "SWE vs ITA", "NOR vs ITA"),
            output_dir=charts_dir,
            attributes=scheme.attributes,
            prefix="cross_country",
        )
        logger.info("Charts written to %s", charts_dir)


if __name__ == "__main__":
    main()

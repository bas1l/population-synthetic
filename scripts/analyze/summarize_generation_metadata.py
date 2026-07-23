"""
summarize_generation_metadata.py -- per country x model x method generation-cost report.

Standalone analysis process ``generation_metadata`` (registry id ==
GUI task key == ``03_Analysis/generation_metadata/`` folder). Reads the 01_Raw
LLM-call telemetry for each discovered ``{country}_{strategy}_{model}`` run slug,
reduces every persona to a per-persona metric record (wall-clock time, input /
output / total tokens, LLM calls, retry & error rates, estimated USD cost from
``config/analysis/model_pricing.yaml``), aggregates per combo into mean/std/n, and
writes one report per country:

    {country}_summary.csv     one row per (model, method); <metric>_{mean,std,n} cols
    {country}_summary.json    nested summary + pricing provenance + skipped list
    charts/{country}_*.png/.svg   per-metric model x method mean-heatmaps

This script recomputes nothing from populations -- it reads only the raw
generation telemetry. It is an isolated island (no dependency on the map/compare
stages).

Usage:
    python scripts/analyze/summarize_generation_metadata.py
    python scripts/analyze/summarize_generation_metadata.py --country swedish
    python scripts/analyze/summarize_generation_metadata.py --model claude_haiku --model gemini_flash
    python scripts/analyze/summarize_generation_metadata.py --strategy all_pick --no-charts
    python scripts/analyze/summarize_generation_metadata.py --slug swedish_all_pick_claude_haiku
    python scripts/analyze/summarize_generation_metadata.py --force --strict

--country       Country axis ID filter. May be repeated. Default: all countries.
--model         Model axis ID filter. May be repeated. Default: all models.
--strategy      Strategy axis ID filter. May be repeated. Default: all strategies.
--slug          Exact slug filter ({country}_{strategy}_{model}). May be repeated.
--output-base   Base output directory (the run base). Default: experiment_defaults.yaml.
--no-charts     Skip chart generation (charts are ON by default).
--strict        Fail on an undecomposable country-prefixed slug (default: skip it).
--force         Recompute a country even if its {country}_summary.csv already exists
                (default: skip that country if present).
"""

import argparse
import sys

from population_synthetic.analysis.generation_metadata import summarize
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Per country x model x method(strategy), summarize the per-persona generation "
            "cost (time, tokens, calls, retry/error rates, estimated USD) from 01_Raw telemetry."
        )
    )
    parser.add_argument(
        "--country", dest="countries", action="append", default=None, metavar="COUNTRY_ID",
        help="Country axis ID filter. May be repeated. Default: all countries.",
    )
    parser.add_argument(
        "--model", dest="models", action="append", default=None, metavar="MODEL_ID",
        help="Model axis ID filter. May be repeated. Default: all models.",
    )
    parser.add_argument(
        "--strategy", dest="strategies", action="append", default=None, metavar="STRATEGY_ID",
        help="Strategy axis ID filter. May be repeated. Default: all strategies.",
    )
    parser.add_argument(
        "--slug", dest="slugs", action="append", default=None, metavar="SLUG",
        help="Exact slug filter ({country}_{strategy}_{model}). May be repeated.",
    )
    parser.add_argument(
        "--output-base", default=None,
        help="Base output directory (the run base). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation.")
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail on an undecomposable country-prefixed slug (default: skip it).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompute a country even if its {country}_summary.csv already exists "
        "(default: skip that country if present).",
    )
    return parser.parse_args()


def _validate_filter_ids(filter_ids: list[str], axis_ids: set[str], axis_name: str) -> None:
    unknown = [fid for fid in filter_ids if fid not in axis_ids]
    if unknown:
        raise ValueError(
            f"Unknown {axis_name} ID(s): {unknown}. Valid IDs are: {sorted(axis_ids)}"
        )


def _split_csv(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [v.strip() for item in values for v in item.split(",") if v.strip()] or None


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)
    slug_filter = _split_csv(args.slugs)

    all_model_ids = {m["id"] for m in discover_axis_values("models")}
    all_strategy_ids = {s["id"] for s in discover_axis_values("strategies")}
    all_country_ids = {c["id"] for c in discover_axis_values("countries")}

    if model_filter:
        _validate_filter_ids(model_filter, all_model_ids, "model")
    if strategy_filter:
        _validate_filter_ids(strategy_filter, all_strategy_ids, "strategy")
    if country_filter:
        _validate_filter_ids(country_filter, all_country_ids, "country")

    try:
        written = summarize(
            output_base=args.output_base,
            countries=country_filter,
            models=model_filter,
            strategies=strategy_filter,
            slugs=slug_filter,
            force=args.force,
            charts=not args.no_charts,
            strict=args.strict,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not written:
        print(
            "No generation-metadata reports written -- either every selected country already "
            "had output (pass --force to recompute) or no matching run slugs were found under 01_Raw."
        )
        return

    for country, paths in sorted(written.items()):
        print(f"=== {country.upper()} ===")
        print(f"CSV written to {paths['csv']}")
        print(f"JSON written to {paths['json']}")
        if not args.no_charts:
            print(f"Charts written to {paths['csv'].parent / 'charts'}")
        print()


if __name__ == "__main__":
    main()

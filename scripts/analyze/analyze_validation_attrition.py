"""
analyze_validation_attrition.py -- Where the validation gate's personas went, per combination.

Reads the gate's three persisted records -- population_cap/_index.json plus the
validate_raw and validate_mapped roll-ups -- and publishes, for every combination the
gate recorded, the five-stage funnel (generated -> raw-valid -> mapped-valid -> clean ->
selected) and the two rates derived from it. It performs no validation, no capping and
no LLM work: it re-reads what the gate already wrote, so running it is free and
repeatable, and it can never change a downstream number.

The row grain is EVERY combination in the cap index, INCLUDING the ones the full-N rule
withdrew. That is the point of the task rather than an edge case: an excluded combination
has no capped mirror, no capped mapped file and no generation_metadata row, so this is
the only artifact in the analysis layer on which it appears at all. Dropping those rows
would leave the sweep looking as though it had consisted solely of what survived.

Two derived rates, denominated deliberately:

  retention_rate          clean / generated -- the share of a generated pool that
                          survived both gates. Empty (never 0.0) when nothing was
                          generated; a measured 0.0 means a pool was generated and
                          wholly discarded, which is a finding, not an absence.
  generation_multiplier   generated / clean -- personas generated per USABLE persona.
                          Deliberately not generated / selected, whose denominator is
                          zero for every withdrawn combination, i.e. undefined exactly
                          where the number matters most.

Outputs, per country, under the analysis-stage validation_attrition folder:
    {country}_attrition.csv     one row per combination (schema v1, 15 columns)
    {country}_attrition.json    counts, both rates, totals, the withdrawn list, provenance
    {country}_attrition_funnel.png/.svg          per-combination normalised funnel
    {country}_mapped_validity_grid.png/.svg      model x method validation-survival grid

The JSON carries no timestamp, so re-running over unchanged gate records rewrites the
CSV and the JSON byte-for-byte. That claim covers the PNGs too but NOT the SVG siblings:
matplotlib stamps every SVG with a creation date, so no SVG in this repository is
byte-stable.

Flags:
--country       Country axis ID filter. Repeatable. Default: all countries.
--model         Model axis ID filter. Repeatable. Default: all models.
--strategy      Strategy axis ID filter. Repeatable. Default: all strategies.
--slug          Exact slug filter ({country}_{strategy}_{model}). Repeatable.
--output-base   Base output directory. Default: config/synthetic/experiment_defaults.yaml.
--no-charts     Skip both figures (the CSV and the JSON are still written).
--strict        Fail instead of skipping a combination missing from a validator roll-up.
--force         Rewrite a country whose {country}_attrition.json already exists.
--dpi           PNG render resolution. Default: 200.
"""

import argparse
import json
import sys
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.model_ranking.hosting import (
    classify_hosting,
    load_hosting_config,
)
from population_synthetic.analysis.utils.attrition_csv import write_attrition_csv
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.analysis.validation_attrition.builder import (
    PROCESS_ID,
    build_document,
    build_rows,
)
from population_synthetic.analysis.validation_attrition.charts import (
    plot_attrition_funnel,
    plot_mapped_validity_grid,
)
from population_synthetic.analysis.validation_attrition.loader import (
    load_attrition_records,
    resolve_sources,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

#: The provider -> local/hosted map the sibling fidelity grids colour their model labels
#: by. Read here, at the CLI edge, and passed down: the chart module holds no default and
#: no config path, so the grid's row colours and the models table's row colours can never
#: come from two different files.
_HOSTING_PATH = PROJECT_ROOT / "config" / "analysis" / "model_ranking" / "provider_hosting.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the validation gate's per-combination attrition: the five-stage "
            "funnel, the retention rate and the generation multiplier, for every "
            "combination the gate recorded -- including the ones it withdrew."
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
        help="Base output directory (the analysis-stage parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--no-charts", action="store_true",
        help="Skip chart generation (the CSV and the JSON are still written).",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail when a selected combination is missing from one of the two validator "
        "roll-ups instead of skipping it. Counts that DISAGREE across the three records "
        "always fail, with or without this flag.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Rewrite a country even if its {country}_attrition.json already exists "
        "(default: skip that country if present).",
    )
    parser.add_argument("--dpi", type=int, default=200, help="PNG render resolution. Default: 200.")
    return parser.parse_args()


def _split_csv(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [v.strip() for item in values for v in item.split(",") if v.strip()] or None


def _validate_filter_ids(filter_ids: list[str], axis_ids: set[str], axis_name: str) -> None:
    unknown = [fid for fid in filter_ids if fid not in axis_ids]
    if unknown:
        raise ValueError(f"Unknown {axis_name} ID(s): {unknown}. Valid IDs are: {sorted(axis_ids)}")


def _write_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def _print_country_summary(document: dict) -> None:
    totals = document["totals"]
    pooled = totals["retention_rate"]
    print("=" * 96)
    print(
        f"{document['n_combinations']} combination(s), {document['n_excluded']} withdrawn "
        f"| pooled: {totals['generated']} generated -> {totals['clean']} clean -> "
        f"{totals['selected']} selected"
        + ("" if pooled is None else f" ({pooled * 100:.1f}% retained)")
    )
    if document["excluded_combinations"]:
        print("-" * 96)
        print("WITHDRAWN (present in no other analysis artifact):")
        for entry in document["excluded_combinations"]:
            print(
                f"  {entry['slug']}: {entry['clean']} clean of {entry['generated']} "
                f"generated, needed {entry['requested_n']} -- {entry['reason']}"
            )
    print("=" * 96)


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)
    slug_filter = _split_csv(args.slugs)

    try:
        all_models = discover_axis_values("models")
        all_model_ids = {m["id"] for m in all_models}
        all_country_ids = {c["id"] for c in discover_axis_values("countries")}
        all_strategy_ids = {s["id"] for s in discover_axis_values("strategies")}
        if country_filter:
            _validate_filter_ids(country_filter, all_country_ids, "country")
        if model_filter:
            _validate_filter_ids(model_filter, all_model_ids, "model")
        if strategy_filter:
            _validate_filter_ids(strategy_filter, all_strategy_ids, "strategy")
        # Fails loudly on a missing config or a provider with no hosting class; it decides
        # a row-label colour and nothing computed, but a silent default here would let the
        # two grids disagree about what "local" means.
        model_hosting = classify_hosting(all_models, load_hosting_config(_HOSTING_PATH))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    output_base = resolve_output_base(args.output_base)
    attrition_dir = analysis_output_dir(PROCESS_ID, output_base)

    try:
        sources = resolve_sources(output_base)
        records, skipped = load_attrition_records(
            output_base,
            countries=country_filter, models=model_filter,
            strategies=strategy_filter, slugs=slug_filter, strict=args.strict,
        )
    except (FileNotFoundError, RuntimeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if skipped:
        print(f"Skipped {len(skipped)} combination(s):")
        for slug, reason in skipped:
            print(f"  {slug}: {reason}")
        print()

    by_country: dict[str, list] = {}
    for record in records:
        by_country.setdefault(record.country, []).append(record)

    if not by_country:
        print(
            "ERROR: no consumable combination found in the validation gate's records. Run "
            "scripts/analyze/cap_populations.py (after the two validators) first.",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = 0
    skipped_existing = 0
    for country in sorted(by_country):
        country_records = by_country[country]
        report_json = attrition_dir / f"{country}_attrition.json"

        if not args.force and report_json.exists():
            print(f"=== {country.upper()} ===  SKIP (exists): {report_json}")
            print()
            skipped_existing += 1
            continue

        print(f"=== {country.upper()} ===  ({len(country_records)} combination(s))")
        country_skipped = [(slug, reason) for slug, reason in skipped if slug.startswith(country)]
        document = build_document(
            country_records, country=country, skipped=country_skipped, sources=sources,
        )

        print(f"Report written to {_write_json(document, report_json)}")
        rows = build_rows(country_records)
        csv_path = write_attrition_csv(rows, attrition_dir / f"{country}_attrition.csv")
        print(f"Attrition CSV written to {csv_path} -- {len(rows)} row(s)")

        if not args.no_charts:
            charts = [
                (f"{country}_attrition_funnel", lambda: plot_attrition_funnel(document)),
                (
                    f"{country}_mapped_validity_grid",
                    lambda: plot_mapped_validity_grid(document, hosting=model_hosting),
                ),
            ]
            for name, build in charts:
                try:
                    saved = save_figure(build(), attrition_dir / f"{name}.png", dpi=args.dpi)
                except ValueError as exc:
                    print(f"WARNING: {name} not rendered: {exc}", file=sys.stderr)
                    continue
                print(f"{name} written to {saved} (+ .svg)")

        print()
        _print_country_summary(document)
        print()
        processed += 1

    if processed == 0:
        if skipped_existing:
            print(
                f"All {skipped_existing} country/countries already have an attrition report; "
                "nothing recomputed (pass --force to recompute)."
            )
            return
        print(
            "ERROR: no country had a consumable combination to report attrition for. Run "
            "scripts/analyze/cap_populations.py for more combinations.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

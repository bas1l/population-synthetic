"""
analyze_cost_efficiency.py -- What each combination's fidelity cost to produce.

Joins three artifacts other tasks already wrote -- the fidelity ranking's accuracy, the
validation gate's attrition counts, and the generation-metadata telemetry roll-up -- and
publishes, per country, each combination's total-variation similarity beside the dollars
its run actually spent. It performs no scoring, no capping and no LLM work.

THE COST DENOMINATOR IS THE POINT. generation_metadata totals its cost over the CAPPED
MIRROR: the ~100 personas each combination was subsampled down to. This task instead
totals the same per-call telemetry over the FULL GENERATED POOL in 01_Raw, because the
discarded personas were paid for. Measured on the live grid the two bases differ by
4.8x on the worst combination (27.28 USD over 549 generated vs 5.73 USD over the 100
selected), and the gap is largest exactly where retention is worst -- so a capped figure
flatters the models that wasted the most tokens, inverting the figure's purpose. The
basis travels as a CSV column and is printed on the figure; it is never left to prose.

THE JOIN KEY IS RECONSTRUCTED. generation_metadata's summary carries model + method
columns and no slug, so the key is rebuilt through
generators/synthetic/manifest_loader.py::axis_slug -- the single source of truth for
{country}_{strategy}_{model}. That reconstruction is verified on every read against the
slug the model_ranking CSV publishes for the same (model, strategy) pair, and the joined
row sets are reconciled: any unmatched key on either side raises, naming the key and both
files, and an empty join raises rather than writing an empty CSV.

THE THREE INPUTS LEGITIMATELY DISAGREE ON MEMBERSHIP. The attrition CSV holds every
combination the gate recorded, INCLUDING the ones the full-N rule withdrew; the other two
hold only combinations that produced a capped mirror. The output row set is therefore the
attrition set MINUS the withdrawals, and a withdrawn combination is reported -- with the
money it cost and the personas it kept -- rather than silently inner-joined away.

NO COMPOSITE SCORE IS COMPUTED. About a third of the model axis is unmetered (priced
{in: 0, out: 0}: the local ollama_* models), so accuracy-per-dollar is undefined for
them; and a composite would bury an exchange rate between fidelity and dollars inside
arithmetic no reader can see. Accuracy and cost are published side by side. Unmetered is
also not FREE -- local inference has a real cost this pipeline does not model -- so the
flag travels as a column and the figure says so on its face.

Outputs, per country, under the analysis-stage cost_efficiency folder:
    {country}_cost_efficiency.csv     one row per joined combination (schema v1)
    {country}_cost_efficiency.json    the same quantities plus totals, the withdrawn
                                      combinations, the membership rule and pricing
                                      provenance
    {country}_cost_vs_fidelity.png/.svg   accuracy against cost, symlog x with the
                                      labelled unmetered band

The JSON carries no timestamp, so re-running over unchanged inputs rewrites the CSV and
the JSON byte-for-byte. That claim covers the PNG too but NOT the SVG sibling: matplotlib
stamps every SVG with a creation date, so no SVG in this repository is byte-stable.

Flags:
--country       Country axis ID filter. Repeatable. Default: every country with an
                attrition CSV under the output base.
--model         Model axis ID filter. Repeatable. Default: all models.
--strategy      Strategy axis ID filter. Repeatable. Default: all strategies.
--slug          Exact slug filter ({country}_{strategy}_{model}). Repeatable.
--output-base   Base output directory. Default: config/synthetic/experiment_defaults.yaml.
--no-charts     Skip the figure (the CSV and the JSON are still written).
--force         Rewrite a country whose {country}_cost_efficiency.json already exists.
--dpi           PNG render resolution. Default: 200.
"""

import argparse
import json
import sys
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.cost_efficiency.builder import (
    PROCESS_ID,
    build_document,
    build_rows,
)
from population_synthetic.analysis.cost_efficiency.charts import plot_cost_vs_accuracy
from population_synthetic.analysis.cost_efficiency.loader import (
    available_countries,
    load_cost_records,
)
from population_synthetic.analysis.cost_efficiency.raw_cost import load_raw_pricing
from population_synthetic.analysis.model_ranking.hosting import (
    classify_hosting,
    load_hosting_config,
)
from population_synthetic.analysis.utils.cost_csv import write_cost_csv
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

#: The provider -> local/hosted map the sibling fidelity grids colour their model labels
#: by. Read here, at the CLI edge, and passed down: the chart module holds no default and
#: no config path, so this figure's marker shapes and the ranking tables' row colours can
#: never come from two different files.
_HOSTING_PATH = PROJECT_ROOT / "config" / "analysis" / "model_ranking" / "provider_hosting.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish each combination's fidelity beside the cost of the run that "
            "produced it, measured over the FULL generated pool rather than the capped "
            "mirror. Withdrawn combinations are reported, never silently dropped."
        )
    )
    parser.add_argument(
        "--country", dest="countries", action="append", default=None, metavar="COUNTRY_ID",
        help="Country axis ID filter. May be repeated. Default: every country with a "
        "validation-attrition CSV under the output base.",
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
        help="Base output directory (the parent of 01_Raw/ and 03_Analysis/). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--no-charts", action="store_true",
        help="Skip the figure (the CSV and the JSON are still written).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Rewrite a country even if its {country}_cost_efficiency.json already exists "
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
    metered = totals["metered"]
    withdrawn = document["withdrawn_totals"]
    membership = document["membership"]
    print("=" * 96)
    print(
        f"{document['n_combinations']} combination(s) joined "
        f"(attrition {membership['attrition_rows']} rows, "
        f"{membership['attrition_withdrawn']} withdrawn; accuracy "
        f"{membership['accuracy_rows']}; telemetry {membership['telemetry_rows']})"
    )
    print(
        f"Cost basis: {document['cost_basis']} | metered: "
        f"{metered['total_cost_usd']:.4f} USD over {metered['clean']} clean personas "
        f"across {metered['n_combinations']} combination(s)"
        + (
            ""
            if metered["cost_per_usable_persona"] is None
            else f" = {metered['cost_per_usable_persona']:.6f} USD/usable persona"
        )
    )
    print(
        f"{totals['n_unmetered_combinations']} unmetered combination(s) "
        f"(measured 0.0, NOT free); {totals['n_without_token_data']} with no token data"
    )
    if withdrawn["n_combinations"]:
        print("-" * 96)
        print(
            f"WITHDRAWN and therefore NOT plotted ({withdrawn['n_combinations']}): "
            f"{withdrawn['generated']} generated -> {withdrawn['clean']} clean, "
            f"{withdrawn['metered_total_cost_usd']:.4f} USD across "
            f"{withdrawn['n_metered_combinations']} metered combination(s)"
        )
        for entry in document["withdrawn_combinations"]:
            cost = entry["total_cost_usd"]
            spent = "no token data" if cost is None else f"{cost:.4f} USD"
            unmetered = " [unmetered]" if entry["unmetered"] else ""
            print(
                f"  {entry['slug']}: {entry['clean']} clean of {entry['generated']} "
                f"generated, {spent}{unmetered} -- {entry['reason']}"
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
        # Fails loudly on a missing config or a provider with no hosting class. It decides
        # a marker shape and nothing computed, but a silent default here would let this
        # figure and the ranking tables disagree about what "local" means.
        model_hosting = classify_hosting(all_models, load_hosting_config(_HOSTING_PATH))
        # Loaded once, at the edge, and passed into every country's join so one report is
        # never priced from two tables.
        pricing = load_raw_pricing()
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    output_base = resolve_output_base(args.output_base)
    cost_dir = analysis_output_dir(PROCESS_ID, output_base)

    countries = available_countries(output_base)
    if country_filter:
        countries = [c for c in countries if c in country_filter]
    if slug_filter:
        countries = [c for c in countries if any(s.startswith(f"{c}_") for s in slug_filter)]

    if not countries:
        print(
            "ERROR: no country has a validation-attrition CSV under "
            f"{output_base}. Run scripts/analyze/analyze_validation_attrition.py "
            "(and the fidelity ranking and generation-metadata summary) first.",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = 0
    skipped_existing = 0
    for country in countries:
        report_json = cost_dir / f"{country}_cost_efficiency.json"
        if not args.force and report_json.exists():
            print(f"=== {country.upper()} ===  SKIP (exists): {report_json}")
            print()
            skipped_existing += 1
            continue

        print(f"=== {country.upper()} ===")
        try:
            result = load_cost_records(
                output_base, country, pricing=pricing,
                models=model_filter, strategies=strategy_filter, slugs=slug_filter,
            )
        except (FileNotFoundError, ValueError, KeyError) as exc:
            print(f"ERROR: {country}: {exc}", file=sys.stderr)
            sys.exit(1)

        document = build_document(result)
        print(f"Report written to {_write_json(document, report_json)}")
        rows = build_rows(result)
        csv_path = write_cost_csv(rows, cost_dir / f"{country}_cost_efficiency.csv")
        print(f"Cost-efficiency CSV written to {csv_path} -- {len(rows)} row(s)")

        if not args.no_charts:
            name = f"{country}_cost_vs_fidelity"
            try:
                saved = save_figure(
                    plot_cost_vs_accuracy(document, hosting=model_hosting),
                    cost_dir / f"{name}.png",
                    dpi=args.dpi,
                )
            except ValueError as exc:
                print(f"WARNING: {name} not rendered: {exc}", file=sys.stderr)
            else:
                print(f"{name} written to {saved} (+ .svg)")

        print()
        _print_country_summary(document)
        print()
        processed += 1

    if processed == 0:
        if skipped_existing:
            print(
                f"All {skipped_existing} country/countries already have a cost-efficiency "
                "report; nothing recomputed (pass --force to recompute)."
            )
            return
        print(
            "ERROR: no country had a consumable combination to report cost efficiency for.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

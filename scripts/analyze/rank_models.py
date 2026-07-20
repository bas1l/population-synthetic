"""
rank_models.py -- Cross-model performance comparison (models x methods per country).

Sits AFTER the compare stage: consumes the per-combo comparison reports written by
score_fidelity_all.py / score_fidelity_sweden.py under
{output_base}/03_Analysis/fidelity/{slug}/{slug}.json and compares the model x strategy
combos against each other per country -- per demographic attribute and overall -- on how
well each matches the real baseline (TV-similarity = 1 - TV distance; coherence as
tie-break). Includes Kruskal-Wallis + Dunn/Holm tests per factor (model / strategy).
This script recomputes nothing from populations -- run map_populations.py and
score_fidelity_all.py first.

Outputs, per country, under {output_base}/03_Analysis/model_ranking/:
    {country}_performance.json    score matrix + ranking + factor statistics
    {country}_performance.csv     one row per combo (rank order)
    {country}_heatmap.png         combos x attributes (+ overall) TV-similarity
    {country}_leaderboard.png     overall ranking with coherence annotations
    {country}_models_table.png    manuscript table: models at the global-best strategy x
                                  axes (+ overall), single inferno ramp with a
                                  hosted/local provenance side-marker (PNG + SVG)
    {country}_methods_table.png   manuscript table: strategies x axes (+ overall),
                                  mean-over-models TV-similarity, inferno ramp (PNG + SVG)
    {country}_models_table.tex    manuscript LaTeX snippet mirroring the models table
                                  (booktabs tabular, inferno cell colours, best-per-column bold)
    {country}_methods_table.tex   manuscript LaTeX snippet mirroring the methods table
    {country}_by_attribute/       one grouped bar chart per attribute (opt-in)

Usage:
    python scripts/analyze/rank_models.py
    python scripts/analyze/rank_models.py --country swedish
    python scripts/analyze/rank_models.py --model claude_haiku --model gemini_flash
    python scripts/analyze/rank_models.py --strategy all_pick --no-charts
    python scripts/analyze/rank_models.py --slug swedish_all_pick_claude_haiku \
        --slug swedish_all_pick_gemini_flash
    python scripts/analyze/rank_models.py --per-attribute-charts --strict
    python scripts/analyze/rank_models.py --force

--country               Country axis ID filter. May be repeated. Default: all countries.
--model                 Model axis ID filter. May be repeated. Default: all models.
--strategy              Strategy axis ID filter. May be repeated. Default: all strategies.
--slug                  Exact slug filter ({country}_{strategy}_{model}). May be repeated.
--output-base           Base output directory (the 03_Analysis parent). Default: experiment_defaults.yaml.
--no-charts             Skip chart generation.
--per-attribute-charts  Also write one grouped bar chart per demographic attribute.
--strict                Fail when any selected combo lacks a comparison report
                        (default: warn and proceed with the combos that have one).
--force                 Recompute a country even if its {country}_performance.json already
                        exists (default: skip that country if present).
"""

import argparse
import sys
from pathlib import Path

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.model_ranking.builder import (
    build_performance_comparison,
    write_performance_csv,
    write_performance_json,
)
from population_synthetic.analysis.model_ranking.charts import (
    plot_attribute_bars,
    plot_c2st_vs_tv,
    plot_performance_heatmap,
    plot_performance_leaderboard,
)
from population_synthetic.analysis.model_ranking.hosting import (
    classify_hosting,
    load_hosting_config,
)
from population_synthetic.analysis.model_ranking.loader import (
    load_combo_performances,
    scheme_attributes,
)
from population_synthetic.analysis.model_ranking.manuscript_tables import (
    plot_method_fidelity_table,
    plot_model_fidelity_table,
    write_method_fidelity_latex,
    write_model_fidelity_latex,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"
_HOSTING_PATH = PROJECT_ROOT / "config" / "analysis" / "model_ranking" / "provider_hosting.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-model performance comparison: rank model x strategy combos per country "
            "on how well they match the real baseline (consumes the comparison reports)."
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
        help="Base output directory (the 03_Analysis parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation.")
    parser.add_argument(
        "--per-attribute-charts", action="store_true",
        help="Also write one grouped bar chart per demographic attribute.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail when any selected combo lacks a comparison report.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompute a country even if its {country}_performance.json already exists "
        "(default: skip that country if present).",
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


def _print_country_summary(result: dict) -> None:
    print("=" * 94)
    print(
        f"{'RANK':>4}  {'MODEL':<24} {'STRATEGY':<34} {'N':>5}  {'OVERALL TV-SIM':>14}  {'COHERENCE':>9}"
    )
    print("-" * 94)
    for slug in result["ranking"]:
        combo = result["combos"][slug]
        print(
            f"{combo['overall']['rank']:>4}  {combo['model']:<24} {combo['strategy']:<34} "
            f"{combo['n']:>5}  {combo['overall']['tv_similarity_mean']:>14.4f}  "
            f"{combo['overall']['coherence_score']:>9.4f}"
        )
    print("=" * 94)

    for factor, factor_label in (("by_model", "by model"), ("by_strategy", "by strategy")):
        block = result["stats"][factor]
        kw = block["kruskal"]
        n_sig = sum(
            1 for d in block.get("dunn", [])
            if d.get("p_holm") is not None and d["p_holm"] < 0.05
        )
        if kw.get("p") is None:
            print(f"{factor_label:12s}: Kruskal-Wallis n/a ({kw.get('note', '')})")
        else:
            print(
                f"{factor_label:12s}: H={kw['H']:.2f}, p={kw['p']:.3g}  "
                f"({n_sig} significant pair(s))"
            )


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)
    slug_filter = _split_csv(args.slugs)

    all_models = discover_axis_values("models")
    all_model_ids = {m["id"] for m in all_models}
    all_strategy_ids = {s["id"] for s in discover_axis_values("strategies")}
    all_country_ids = {c["id"] for c in discover_axis_values("countries")}

    if model_filter:
        _validate_filter_ids(model_filter, all_model_ids, "model")
    if strategy_filter:
        _validate_filter_ids(strategy_filter, all_strategy_ids, "strategy")
    if country_filter:
        _validate_filter_ids(country_filter, all_country_ids, "country")

    # Provenance map (model id -> "local"/"hosted") from config; fails loudly on a
    # missing config or a provider without a hosting class. Embedded in the built
    # performance JSON so the manuscript tables can encode hosting by hue.
    model_hosting = classify_hosting(all_models, load_hosting_config(_HOSTING_PATH))

    output_base = _resolve_output_base(args.output_base)
    performance_dir = output_base / "03_Analysis" / "model_ranking"

    # Attribute axis per country, computed once and shared with the loader.
    attrs_by_country: dict[str, list[str]] = {}

    def _attrs(country: str) -> list[str]:
        if country not in attrs_by_country:
            attrs_by_country[country] = scheme_attributes(country)
        return attrs_by_country[country]

    try:
        records, skipped = load_combo_performances(
            output_base,
            countries=country_filter,
            models=model_filter,
            strategies=strategy_filter,
            slugs=slug_filter,
            strict=args.strict,
            attributes_for_country=_attrs,
        )
    except (FileNotFoundError, RuntimeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if skipped:
        print(f"Skipped {len(skipped)} combo(s):")
        for slug, reason in skipped:
            print(f"  {slug}: {reason}")
        print()

    by_country: dict[str, list] = {}
    for record in records:
        by_country.setdefault(record.country, []).append(record)

    if not by_country:
        print(
            "ERROR: no comparison reports found to compare. "
            "Run scripts/analyze/score_fidelity_all.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = 0
    skipped_existing = 0
    for country in sorted(by_country):
        country_records = by_country[country]

        # Idempotent skip: a country's ranking is one unit of work, so if its performance
        # JSON already exists and --force was not passed, skip the whole country (json/csv/
        # charts) rather than recomputing. Tracked separately from `processed` so an all-skip
        # run is distinguished from a genuine "nothing to compare" below.
        perf_json = performance_dir / f"{country}_performance.json"
        if not args.force and perf_json.exists():
            print(f"=== {country.upper()} ===  SKIP (exists): {perf_json}")
            print()
            skipped_existing += 1
            continue

        print(f"=== {country.upper()} ===  ({len(country_records)} combo(s))")
        if len(country_records) < 2:
            print(
                f"WARNING: only {len(country_records)} combo has a comparison report for "
                f"{country!r} -- need at least 2 to compare; skipping this country.",
                file=sys.stderr,
            )
            print()
            continue

        country_skipped = [
            (slug, reason) for slug, reason in skipped if slug.startswith(country)
        ]
        result = build_performance_comparison(
            country_records, attrs_by_country[country], skipped=country_skipped,
            model_hosting=model_hosting,
        )

        json_path = write_performance_json(result, performance_dir / f"{country}_performance.json")
        print(f"Report written to {json_path}")
        csv_path = write_performance_csv(result, performance_dir / f"{country}_performance.csv")
        print(f"CSV written to {csv_path}")

        if not args.no_charts:
            heatmap = plot_performance_heatmap(result, performance_dir / f"{country}_heatmap.png")
            if heatmap is not None:
                print(f"Heatmap written to {heatmap}")
            leaderboard = plot_performance_leaderboard(
                result, performance_dir / f"{country}_leaderboard.png"
            )
            if leaderboard is not None:
                print(f"Leaderboard written to {leaderboard}")
            c2st_scatter = plot_c2st_vs_tv(
                result, performance_dir / f"{country}_c2st_vs_tv.png"
            )
            if c2st_scatter is not None:
                print(f"C2ST-vs-TV scatter written to {c2st_scatter}")
            models_table = plot_model_fidelity_table(
                result, performance_dir / f"{country}_models_table.png"
            )
            if models_table is not None:
                print(f"Models table written to {models_table}")
            methods_table = plot_method_fidelity_table(
                result, performance_dir / f"{country}_methods_table.png"
            )
            if methods_table is not None:
                print(f"Methods table written to {methods_table}")
            models_tex = write_model_fidelity_latex(
                result, performance_dir / f"{country}_models_table.tex"
            )
            if models_tex is not None:
                print(f"Models LaTeX table written to {models_tex}")
            methods_tex = write_method_fidelity_latex(
                result, performance_dir / f"{country}_methods_table.tex"
            )
            if methods_tex is not None:
                print(f"Methods LaTeX table written to {methods_tex}")
            if args.per_attribute_charts:
                written = plot_attribute_bars(result, performance_dir / f"{country}_by_attribute")
                print(f"Per-attribute charts written to {performance_dir / f'{country}_by_attribute'} "
                      f"({len(written)} file(s))")

        print()
        _print_country_summary(result)
        print()
        processed += 1

    if processed == 0:
        if skipped_existing:
            # Every eligible country already had its ranking on disk and was skipped -- that
            # is a success (idempotent no-op), not the "nothing to compare" error below.
            print(
                f"All {skipped_existing} country/countries already have model-ranking outputs; "
                "nothing recomputed (pass --force to recompute)."
            )
            return
        print(
            "ERROR: no country had the >=2 comparison reports needed to compare. "
            "Run scripts/analyze/score_fidelity_all.py first.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

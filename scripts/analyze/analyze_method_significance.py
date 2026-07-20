"""
analyze_method_significance.py -- Per-category method/model significance for TV fidelity.

Sits AFTER the compare stage (like rank_models.py): consumes the per-combo comparison
reports written by score_fidelity_all.py / score_fidelity_sweden.py under
{output_base}/03_Analysis/fidelity/{slug}/{slug}.json (reused via model_ranking's loader --
no fidelity recomputation) and asks, per country and per demographic attribute, WHICH
factor drives Total-Variation fidelity: the generation *method* (the ordered strategy axis)
or the *model*, and whether the method-trend differs by model.

The escape from the n=1-per-cell wall is to treat the demographic categories as the
blocking/replication factor (Demšar 2006, "classifiers over multiple data sets"): models =
classifiers, categories = datasets. Per attribute it runs Page's L (ordered method trend,
+linear/quadratic contrast) and Friedman (model omnibus), BH-corrected across attributes;
overall it runs the Demšar model comparison (Friedman -> Nemenyi -> critical-difference
diagram), a Page's L method trend, and a logit-linked mixed model whose model x method
interaction term is estimable. The per-category interaction is emitted DESCRIPTIVELY only
(a slope heatmap) -- no p-value is claimed at that grain.

This script recomputes nothing from populations -- run map_populations.py and
score_fidelity_all.py first. It needs the optional analysis extra (statsmodels +
scikit-posthocs): pip install -e .[analysis].

Outputs, per country, under {output_base}/03_Analysis/method_significance/:
    {country}_method_significance.json      per-attribute + overall tests, metadata, caveats
    {country}_method_significance.csv       one row per attribute (method L/p, model chi2/p, BH)
    {country}_method_comparison.json        method-comparison block (Friedman + Nemenyi, models
                                            as blocks): per category + overall omnibus & pairwise p
    {country}_method_comparison.csv         one row per (category|overall, method-pair): omnibus
                                            stat/p/p_bh/W + pairwise p + significance stars
    {country}_method_comparison.png/.svg    bars + model points + significance brackets/stars,
                                            one panel per category + overall (grid)
    {country}_method_comparison_overall.png/.svg  the single Overall headline panel
    {country}_slope_heatmap.png             attribute x model descriptive TV(method) slope
    {country}_cd_diagram.png                model critical-difference diagram (Nemenyi)
    {country}_factor_dominance.png          eta^2 variance shares (model/method/category)
    {country}_method_trends/                one TV(method) trend chart per attribute (line per model)

Usage:
    python scripts/analyze/analyze_method_significance.py
    python scripts/analyze/analyze_method_significance.py --country swedish
    python scripts/analyze/analyze_method_significance.py --model claude_haiku --model claude_sonnet
    python scripts/analyze/analyze_method_significance.py --strategy all_pick --no-charts
    python scripts/analyze/analyze_method_significance.py --slug swedish_all_pick_claude_haiku
    python scripts/analyze/analyze_method_significance.py --strict --force

--country       Country axis ID filter. May be repeated. Default: all countries.
--model         Model axis ID filter. May be repeated. Default: all models.
--strategy      Strategy axis ID filter. May be repeated. Default: all strategies.
--slug          Exact slug filter ({country}_{strategy}_{model}). May be repeated.
--output-base   Base output directory (the 03_Analysis parent). Default: experiment_defaults.yaml.
--no-charts     Skip chart generation.
--strict        Fail when any selected combo lacks a comparison report
                (default: warn and proceed with the combos that have one).
--force         Recompute a country even if its {country}_method_significance.json already
                exists (default: skip that country if present).
"""

import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.method_significance.builder import (
    build_method_significance,
    load_comparison_config,
    write_method_significance_csv,
    write_method_significance_json,
)
from population_synthetic.analysis.method_significance.charts import (
    _p_to_stars,
    plot_cd_diagram,
    plot_factor_dominance,
    plot_method_comparison,
    plot_method_trends,
    plot_slope_heatmap,
)
from population_synthetic.analysis.model_ranking.loader import (
    load_combo_performances,
    scheme_attributes,
    scheme_category_values,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Per-category method/model significance: which factor (generation method vs "
            "model) drives per-attribute TV fidelity (consumes the comparison reports)."
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
        "--strict", action="store_true",
        help="Fail when any selected combo lacks a comparison report.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompute a country even if its {country}_method_significance.json already "
        "exists (default: skip that country if present).",
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


def _fmt_p(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3g}"


def _write_method_comparison_json(result: dict, out_path: Path) -> Path:
    """Dump the ``method_comparison`` block (Friedman + Nemenyi, models as blocks).

    Mirrors ``write_method_significance_json``'s idiom: the serialised block is the
    machine-readable contract; the driver only persists it, never recomputes it.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result.get("method_comparison") or {}, fh, indent=2, ensure_ascii=False)
    return out_path


def _write_method_comparison_csv(result: dict, out_path: Path) -> Path:
    """Flatten the ``method_comparison`` panels to one row per (panel, method-pair).

    Rows iterate categories (in the metadata attribute order) then ``overall``; for
    each panel a row is emitted per unordered method-pair (complexity order),
    carrying the panel-level omnibus (statistic, raw & BH p, Kendall's W) alongside
    that pair's Nemenyi p and its significance stars. A panel with no comparable
    pair (fewer than two methods) still emits one row so its omnibus is not lost.
    The star mapping reuses the renderer's config-driven ``_p_to_stars`` -- no
    threshold logic is duplicated here.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    block = result.get("method_comparison") or {}
    methods: list[str] = block.get("methods") or []
    panels: dict = block.get("panels") or {}
    thresholds = block.get("star_thresholds") or load_comparison_config()["star_thresholds"]
    ns_symbol = block.get("ns_symbol") or load_comparison_config()["ns_symbol"]

    # Categories in the analysed axis order, then the pooled Overall panel.
    panel_order = [a for a in result["metadata"]["attributes"] if a in panels]
    if "overall" in panels:
        panel_order.append("overall")

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "category", "n_models",
            "omnibus_statistic", "omnibus_p", "omnibus_p_bh", "kendall_w",
            "method_a", "method_b", "pairwise_p", "stars",
        ])
        for name in panel_order:
            panel = panels[name]
            omnibus = panel.get("omnibus") or {}
            pairwise_p: dict = panel.get("pairwise_p") or {}
            common = [
                name, panel.get("n_models"),
                omnibus.get("statistic"), omnibus.get("p"),
                omnibus.get("p_bh"), omnibus.get("kendall_w"),
            ]
            pairs = list(combinations(methods, 2))
            if not pairs:
                writer.writerow(common + [None, None, None, None])
                continue
            for a, b in pairs:
                p = pairwise_p.get(f"{a}|{b}")
                writer.writerow(common + [a, b, p, _p_to_stars(p, thresholds, ns_symbol)])
    return out_path


def _print_country_summary(result: dict) -> None:
    meta = result["metadata"]
    attributes = meta["attributes"]
    alpha = meta["alpha"]
    per_attribute = result["per_attribute"]

    print("=" * 96)
    print(
        f"{'ATTRIBUTE':<22} {'METHOD p(BH)':>12} {'MODEL p(BH)':>12} "
        f"{'KENDALL W':>10} {'LIN.SLOPE':>10} {'DOMINANT':>10}"
    )
    print("-" * 96)
    for attr in attributes:
        block = per_attribute[attr]
        method = block["method_trend"]
        model = block["model_omnibus"]
        friedman = model.get("friedman") or {}
        linear = method.get("linear_contrast") or {}
        w = friedman.get("kendalls_w")
        print(
            f"{attr:<22} {_fmt_p(method.get('p_bh')):>12} {_fmt_p(model.get('p_bh')):>12} "
            f"{('n/a' if w is None else f'{w:.3f}'):>10} "
            f"{str(linear.get('slope_sign') or 'n/a'):>10} "
            f"{str(block.get('dominant_factor') or 'n/a'):>10}"
        )
    print("=" * 96)

    overall = result["overall"]
    method_trend = overall["method_trend"].get("page") or {}
    # Two-sided p (either direction) is the honest headline: Page's L is one-sided
    # for an *increasing* trend, so a strong *improving* (negative-slope) trend
    # reads as p~1 one-sided. z carries the direction.
    p_two = method_trend.get("p_two_sided")
    if p_two is None:
        print(f"overall method trend : Page L n/a ({overall['method_trend'].get('note', '')})")
    else:
        flag = "significant" if p_two < alpha else "n.s."
        direction = "improves" if (method_trend.get("z") or 0.0) < 0 else "worsens"
        print(
            f"overall method trend : Page L={method_trend['L']:.1f}, z={method_trend['z']:.2f}, "
            f"p(2-sided)={_fmt_p(p_two)} ({flag}; TV {direction} with complexity)"
        )

    mc = overall["model_comparison"]
    friedman = mc.get("friedman") or {}
    if friedman.get("p") is None:
        print(f"overall model omnibus: Friedman n/a ({mc.get('note', '')})")
    else:
        flag = "significant" if friedman["p"] < alpha else "n.s."
        print(
            f"overall model omnibus: Friedman chi2={friedman['chi2']:.2f}, "
            f"p={_fmt_p(friedman['p'])} ({flag}), W={friedman['kendalls_w']:.3f}, "
            f"{mc.get('n_blocks')} blocks"
        )

    mixed = overall["mixed_logit"]
    interaction = mixed.get("interaction") or {}
    eta = mixed.get("eta_sq")
    conv = "converged" if mixed.get("converged") else "DID NOT converge"
    print(
        f"model x method inter.: Wald p={_fmt_p(interaction.get('p'))} "
        f"(mixed logit {conv})"
    )
    if eta:
        shares = ", ".join(f"{k}={eta[k] * 100:.1f}%" for k in ("model", "method", "category")
                           if k in eta)
        print(f"factor dominance     : {shares}  -> overall dominant: {overall.get('dominant_factor')}")


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

    output_base = _resolve_output_base(args.output_base)
    significance_dir = output_base / "03_Analysis" / "method_significance"

    # Attribute axis per country, computed once and shared with the loader.
    attrs_by_country: dict[str, list[str]] = {}

    def _attrs(country: str) -> list[str]:
        if country not in attrs_by_country:
            attrs_by_country[country] = scheme_attributes(country)
        return attrs_by_country[country]

    # Per-attribute category levels (config-sourced), for the method-comparison
    # panel headers' level counts. Same mapping tier the fidelity reports used.
    cats_by_country: dict[str, dict[str, list[str]]] = {}

    def _cats(country: str) -> dict[str, list[str]]:
        if country not in cats_by_country:
            cats_by_country[country] = scheme_category_values(country)
        return cats_by_country[country]

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
            "ERROR: no comparison reports found to analyse. "
            "Run scripts/analyze/score_fidelity_all.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = 0
    skipped_existing = 0
    for country in sorted(by_country):
        country_records = by_country[country]

        # Idempotent skip: a country's analysis is one unit of work, so if its JSON already
        # exists and --force was not passed, skip the whole country (json/csv/charts).
        result_json = significance_dir / f"{country}_method_significance.json"
        if not args.force and result_json.exists():
            print(f"=== {country.upper()} ===  SKIP (exists): {result_json}")
            print()
            skipped_existing += 1
            continue

        print(f"=== {country.upper()} ===  ({len(country_records)} combo(s))")
        if len(country_records) < 2:
            print(
                f"WARNING: only {len(country_records)} combo has a comparison report for "
                f"{country!r} -- need at least 2 to analyse; skipping this country.",
                file=sys.stderr,
            )
            print()
            continue

        country_skipped = [
            (slug, reason) for slug, reason in skipped if slug.startswith(country)
        ]
        result = build_method_significance(
            country_records, attrs_by_country[country],
            category_values=_cats(country), skipped=country_skipped,
        )

        json_path = write_method_significance_json(result, result_json)
        print(f"Report written to {json_path}")
        csv_path = write_method_significance_csv(
            result, significance_dir / f"{country}_method_significance.csv"
        )
        print(f"CSV written to {csv_path}")

        # Method-comparison results table (data, not a chart -- always written).
        mc_json = _write_method_comparison_json(
            result, significance_dir / f"{country}_method_comparison.json"
        )
        print(f"Method-comparison JSON written to {mc_json}")
        mc_csv = _write_method_comparison_csv(
            result, significance_dir / f"{country}_method_comparison.csv"
        )
        print(f"Method-comparison CSV written to {mc_csv}")

        if not args.no_charts:
            heatmap = plot_slope_heatmap(result, significance_dir / f"{country}_slope_heatmap.png")
            if heatmap is not None:
                print(f"Slope heatmap written to {heatmap}")
            else:
                print("Slope heatmap skipped (no descriptive slopes to plot).")
            cd = plot_cd_diagram(result, significance_dir / f"{country}_cd_diagram.png")
            if cd is not None:
                print(f"CD diagram written to {cd}")
            else:
                print("CD diagram skipped (degenerate model comparison -- no ranks/CD).")
            dominance = plot_factor_dominance(
                result, significance_dir / f"{country}_factor_dominance.png"
            )
            if dominance is not None:
                print(f"Factor-dominance bar written to {dominance}")
            else:
                print("Factor-dominance bar skipped (no eta^2 decomposition / non-convergent fit).")
            trends = plot_method_trends(
                result, country_records, significance_dir / f"{country}_method_trends"
            )
            print(
                f"Method-trend charts written to {significance_dir / f'{country}_method_trends'} "
                f"({len(trends)} file(s))"
            )
            comparison = plot_method_comparison(
                result, significance_dir / f"{country}_method_comparison.png"
            )
            if comparison is not None:
                print(f"Method-comparison grid written to {comparison} (+ .svg)")
            else:
                print("Method-comparison grid skipped (no method-comparison block / nothing plottable).")
            comparison_overall = plot_method_comparison(
                result, significance_dir / f"{country}_method_comparison_overall.png",
                overall_only=True,
            )
            if comparison_overall is not None:
                print(f"Method-comparison Overall panel written to {comparison_overall} (+ .svg)")
            else:
                print("Method-comparison Overall panel skipped (no Overall panel / nothing plottable).")

        print()
        _print_country_summary(result)
        print()
        processed += 1

    if processed == 0:
        if skipped_existing:
            print(
                f"All {skipped_existing} country/countries already have method-significance outputs; "
                "nothing recomputed (pass --force to recompute)."
            )
            return
        print(
            "ERROR: no country had the >=2 comparison reports needed to analyse. "
            "Run scripts/analyze/score_fidelity_all.py first.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

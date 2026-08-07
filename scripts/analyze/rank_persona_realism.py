"""
rank_persona_realism.py -- Cross-combination realism ranking (competitors vs the real population).

Sits AFTER the persona-realism judge: consumes the per-combination artifacts written by
analyze_persona_realism.py under the analysis-stage persona_realism folder
({country}/{combo}/{combo}.json and {combo}_personas.csv) and makes every claim that
needs more than one combination. It performs NO LLM work and re-judges nothing -- the
verdict caches are the expensive artefact and this script never touches them, so running
it is free and repeatable.

Two axes, deliberately opposite in direction:

  Axis A (validity)  impossibility rate. The real (SCB-sampled) population is an
                     ORDINARY RANKED COMPETITOR here, not the origin -- so "are
                     conditionally-chain-sampled personas themselves incoherent?" is a
                     question this ranking can answer rather than one it assumes away.
                     Lower is better, for everyone.
  Axis B (coverage)  typicality dispersion. Here the real population IS the target: the
                     LLM failure mode being guarded against is mode collapse, so the
                     goal is to MATCH the real spread. Distance near zero is better, and
                     a spread far below the real one is as bad as one far above it.

Outputs, per country, under the analysis-stage realism_ranking folder:
    {country}/realism_ranking.json        ranking + contrasts + factor significance + honesty block
    {country}/realism_summary.csv         one row per competitor, in rank order
    {country}/scb_contrast.csv            one row per synthetic competitor vs the real population
    {country}/headline_map.png/.svg       Axis A x Axis B map (real population plotted, not pinned)
    {country}/impossibility_forest.png/.svg  every competitor's rate + bootstrap CI, rank order

Two gates run before any statistic (both failure modes produce plausible-looking wrong
numbers, so neither is a warning): a combination is consumed only if its report, its
per-persona CSV, and the CSV's row count all agree; and every consumed combination must
share one judge_model / prompt_template_sha256 / n_rounds, else the run raises naming
the offending combination.

Usage:
    python scripts/analyze/rank_persona_realism.py
    python scripts/analyze/rank_persona_realism.py --country swedish_02
    python scripts/analyze/rank_persona_realism.py --model claude_haiku --model claude_sonnet
    python scripts/analyze/rank_persona_realism.py --strategy all_pick_v2 --no-charts
    python scripts/analyze/rank_persona_realism.py --slug swedish_02_all_pick_v2_claude_haiku
    python scripts/analyze/rank_persona_realism.py --strict --force

--country       Country axis ID filter. May be repeated. Default: all countries.
--model         Model axis ID filter. May be repeated. Default: all models.
--strategy      Strategy axis ID filter. May be repeated. Default: all strategies.
--slug          Exact slug filter ({country}_{strategy}_{model}). May be repeated.
--output-base   Base output directory (the analysis-stage parent). Default: experiment_defaults.yaml.
--no-charts     Skip chart generation (the JSON and CSVs are still written).
--strict        Fail when any selected combination is not consumable (default: skip it with
                a recorded reason).
--force         Recompute a country even if its realism_ranking.json already exists
                (default: skip that country if present).
--min-combos    Minimum consumable competitors a country needs to be ranked. Default: 2.
--dpi           PNG render resolution. Default: 200.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.realism_ranking.builder import (
    build_ranking,
    scb_contrast_rows,
    summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (
    plot_headline_map,
    plot_impossibility_forest,
)
from population_synthetic.analysis.realism_ranking.loader import load_competitors
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-combination persona-realism ranking: rank every combination -- and the "
            "real population as an ordinary competitor -- on impossibility rate, contrast "
            "typicality dispersion against the real target, and test the model and method "
            "factors."
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
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation.")
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail when any selected combination is not consumable (missing report, missing "
        "per-persona CSV, or a row-count disagreement).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompute a country even if its realism_ranking.json already exists "
        "(default: skip that country if present).",
    )
    parser.add_argument(
        "--min-combos", type=int, default=2, dest="min_combos",
        help="Minimum consumable competitors a country needs to be ranked. Default: 2 "
        "(a one-point ranking is not a ranking).",
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


def _write_csv(rows: list[dict], path: Path) -> Path | None:
    """Write *rows* as CSV; return ``None`` (writing nothing) when there are no rows."""
    if not rows:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _print_country_summary(ranking: dict) -> None:
    print("=" * 104)
    print(f"{'RANK':>4}  {'COMPETITOR':<56} {'N':>5}  {'IMPOSSIBILITY':>13}  {'95% CI':>20}")
    print("-" * 104)
    for entry in ranking["axis_a"]["ranking"]:
        rate = "n/a" if entry["rate"] is None else f"{entry['rate']:.4f}"
        if entry["ci_lo"] is None:
            interval = "n/a"
        else:
            interval = f"[{entry['ci_lo']:.4f}, {entry['ci_hi']:.4f}]"
        marker = " *" if entry["is_real_reference"] else "  "
        print(f"{entry['rank']:>4}{marker}{entry['slug']:<56} {entry['denominator']:>5}  "
              f"{rate:>13}  {interval:>20}")
    print("=" * 104)
    print("* = the real population, ranked as an ordinary competitor on this axis.")

    for factor, label in (("by_model", "by model"), ("by_method", "by method")):
        block = ranking["factor_significance"][factor]
        kw = block.get("kruskal")
        if not kw or kw.get("p") is None:
            note = (kw or {}).get("note", "not computed")
            print(f"{label:10s}: Kruskal-Wallis n/a ({note})")
            continue
        n_sig = sum(1 for d in block.get("dunn", [])
                    if d.get("p_holm") is not None and d["p_holm"] < 0.05)
        print(f"{label:10s}: H={kw['H']:.2f}, p={kw['p']:.3g}  "
              f"({n_sig} significant pair(s), Holm-corrected)")

    for skip in ranking["skipped_tests"]:
        print(f"SKIPPED TEST {skip['test']}: {skip['reason']}")


def main() -> None:
    args = _parse_args()

    country_filter = _split_csv(args.countries)
    model_filter = _split_csv(args.models)
    strategy_filter = _split_csv(args.strategies)
    slug_filter = _split_csv(args.slugs)

    all_country_ids = {c["id"] for c in discover_axis_values("countries")}
    all_model_ids = {m["id"] for m in discover_axis_values("models")}
    all_strategy_ids = {s["id"] for s in discover_axis_values("strategies")}

    try:
        if country_filter:
            _validate_filter_ids(country_filter, all_country_ids, "country")
        if model_filter:
            _validate_filter_ids(model_filter, all_model_ids, "model")
        if strategy_filter:
            _validate_filter_ids(strategy_filter, all_strategy_ids, "strategy")
        # The judge config supplies the bootstrap block and the Levene centring, so the
        # intervals here are seeded exactly as the per-combination ones were. Both are
        # read fail-fast: no in-code default may silently disagree with judge.yaml.
        cfg = JudgeConfig.load(_CONFIG_DIR)
        variance_center = str(cfg.reliability_value("variance_center"))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    output_base = resolve_output_base(args.output_base)
    ranking_dir = analysis_output_dir("realism_ranking", output_base)

    try:
        records, skipped = load_competitors(
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
            "ERROR: no consumable persona-realism combination found to rank. Run "
            "scripts/analyze/analyze_persona_realism.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = 0
    skipped_existing = 0
    for country in sorted(by_country):
        country_records = by_country[country]
        country_dir = ranking_dir / country
        ranking_json = country_dir / "realism_ranking.json"

        if not args.force and ranking_json.exists():
            print(f"=== {country.upper()} ===  SKIP (exists): {ranking_json}")
            print()
            skipped_existing += 1
            continue

        print(f"=== {country.upper()} ===  ({len(country_records)} competitor(s))")
        if len(country_records) < args.min_combos:
            print(
                f"WARNING: only {len(country_records)} consumable competitor(s) for "
                f"{country!r} -- need at least {args.min_combos} to rank; skipping this "
                "country (no one-point map is emitted).",
                file=sys.stderr,
            )
            print()
            continue

        country_skipped = [(slug, reason) for slug, reason in skipped
                           if slug.startswith(country) or slug == f"real_{country}"]
        ranking = build_ranking(
            country_records, country,
            bootstrap=cfg.bootstrap, variance_center=variance_center,
            skipped_combinations=country_skipped,
        )

        print(f"Report written to {_write_json(ranking, ranking_json)}")
        summary_csv = _write_csv(summary_rows(ranking), country_dir / "realism_summary.csv")
        if summary_csv is not None:
            print(f"Summary CSV written to {summary_csv}")
        contrast_csv = _write_csv(scb_contrast_rows(ranking), country_dir / "scb_contrast.csv")
        if contrast_csv is not None:
            print(f"Contrast CSV written to {contrast_csv}")
        else:
            print("No contrast CSV: there is no real competitor to contrast against "
                  "(recorded in skipped_tests).")

        if not args.no_charts:
            for name, build in (
                ("headline_map", lambda: plot_headline_map(ranking)),
                ("impossibility_forest", lambda: plot_impossibility_forest(ranking)),
            ):
                try:
                    saved = save_figure(build(), country_dir / f"{name}.png", dpi=args.dpi)
                except ValueError as exc:
                    print(f"WARNING: {name} not rendered: {exc}", file=sys.stderr)
                    continue
                print(f"{name} written to {saved} (+ .svg)")

        print()
        _print_country_summary(ranking)
        print()
        processed += 1

    if processed == 0:
        if skipped_existing:
            print(
                f"All {skipped_existing} country/countries already have a realism ranking; "
                "nothing recomputed (pass --force to recompute)."
            )
            return
        print(
            f"ERROR: no country had the >={args.min_combos} consumable competitors needed to "
            "rank. Run scripts/analyze/analyze_persona_realism.py for more combinations "
            "(including the real competitor).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

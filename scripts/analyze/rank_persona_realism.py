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
    {country}/impossibility_heatmap.png/.svg model x method grid of the rate, with the real
                                          population as a separate band (grey = not judged,
                                          which is NOT a rate of zero)
    {country}/severity_drivers.csv        what clashed in each cell: the attribute pairs
                                          ranked by how many of that cell's personas
                                          exhibit them, with the cell's own denominator.
                                          All three levels in ONE table, with `severity`
                                          as a column beside `penalised` -- ranks stay
                                          within (competitor, severity) and are never
                                          renumbered across levels.
    {country}/severity_driver_values.csv  the same, one grain finer -- the category
                                          pairs (e.g. Student x Permanent Full-time) under
                                          each ranked attribute pair. Counts are PERSONAS
                                          and are NOT additive: a persona may carry several
                                          clashes, each names two attributes, and the levels
                                          are not a partition -- never a pie, never a
                                          100%-stacked bar.
    {country}/severity_heatmap_s3/s2/s1.png/.svg  same grid layout, one per clash severity:
                                          the share of a combination's personas carrying >=1
                                          clash at that level. Counted INDEPENDENTLY -- a
                                          persona with both an S3 and an S2 appears on both.
                                          Reporting only: no ranking, no test, and the binary
                                          impossibility rate is unaffected. S3/S2 are defects
                                          (lower is better); S1 is unusual-but-possible and is
                                          reported, never penalised, so it uses a neutral ramp.
    {country}/severity_pair_summary_s3/s2/s1.png/.svg  the complement of those heatmaps, one
                                          per level: WHAT clashed, ranked country-wide at the
                                          attribute-pair grain. Computed from every per-clash
                                          row -- NOT from severity_drivers.csv, which is already
                                          cut per cell by --driver-top-n. The synthetic
                                          combinations are pooled into the bars; the real
                                          population is a separate red-diamond series over its
                                          own denominator and is never pooled in.
    {country}/typicality_summary.csv      one row per competitor: the SELF-CONTAINED typicality
                                          statistic (a function of that competitor's own scores
                                          alone), its bootstrap CI, both persona counts under
                                          distinct names -- `denominator` (personas carrying a
                                          typicality) vs `n_personas` (the combination's full
                                          count) -- the under-powered/boundary flags, and the
                                          secondary P(typicality <= k0) column with a Wilson
                                          interval. Reporting only: it replaces nothing, and
                                          axis_b.dispersion_contrast remains the tested contrast.
    {country}/typicality_histogram.csv    the same statistic's published object, one row per
                                          (competitor, level) over the full 0..10 scale, so the
                                          levels nobody scored are explicit zeros.
    {country}/typicality_heatmap.png/.svg model x method grid of that statistic on a DIVERGING
                                          ramp whose midpoint is the real population's own value,
                                          read from the document. There is no better/worse
                                          direction -- the optimum is interior -- so the two ends
                                          are more-collapsed-than-real and more-dispersed-than-
                                          real. Four distinct states: a value, an under-powered
                                          value (hatched), a judged competitor with no
                                          typicality-bearing persona, and an unjudged pair.
    {country}/typicality_by_method.png/.svg the same statistic with methods on x in complexity
                                          order, one mark per model, and the real population as a
                                          horizontal reference line (the only figure here that
                                          draws it as a reference rather than a series -- this
                                          axis ranks nothing).

Two gates run before any statistic (both failure modes produce plausible-looking wrong
numbers, so neither is a warning): a combination is consumed only if its report, its
per-persona CSV, and the CSV's row count all agree; and every consumed combination must
share one judge_model / prompt_template_sha256 / n_rounds, else the run raises naming
the offending combination. Under --rounds the round count becomes a capacity requirement
instead: the judge model and the prompt hash must still match exactly, and every persona
must hold at least the capped number of cached rounds.

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
--rounds        Judge rounds consumed per persona. Must be >= 1. Blank consumes the published
                artifacts; a set differing only on its round count is then re-consumed at the
                shallowest cached depth. When set, every competitor is re-reduced from its
                verdict cache over its first N rounds and a persona holding fewer than N fails
                the run. Nothing is re-judged -- zero LLM calls either way.
--driver-top-n  Severity drivers published per cell per level. Default: 5.
--driver-min-count  Personas a driver needs before it is ranked rather than suppressed-and-
                counted. Default: 3.
--pair-summary-top-n  Attribute pairs drawn on each severity_pair_summary figure. Default: 15.
                What falls below the cut is printed on the figure, never dropped silently.
--typicality-metric   Statistic in each typicality cell. Default: iov (Berry-Mielke, ordinal-
                valid). `mean` selects the mean level, which assumes the 0-10 scale is
                equally spaced -- the caveat then travels as a column on every row.
--typicality-min-n    Typicality-bearing personas a competitor needs before its cell is read
                as powered. Default: 30. Below it the cell is flagged and counted, never dropped.
--typicality-tail-threshold  k0 of the secondary P(typicality <= k0) column. Default: 5.
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
    TYPICALITY_STATISTICS,
    build_ranking,
    scb_contrast_rows,
    severity_driver_rows,
    severity_driver_value_rows,
    severity_pair_summary,
    summary_rows,
    typicality_histogram_rows,
    typicality_summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (
    plot_headline_map,
    plot_impossibility_forest,
    plot_impossibility_heatmap,
    plot_severity_heatmap,
    plot_severity_pair_summary,
    plot_typicality_by_method,
    plot_typicality_heatmap,
)
from population_synthetic.analysis.realism_ranking.loader import load_competitors
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.realism_csv import SEVERITY_LEVELS
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"

#: The judge's typicality scale: levels 0..10, so k = 11. A **prompt-schema constant**,
#: not a tunable -- it is fixed by config/analysis/persona_realism/judge_prompt.md and
#: enforced in persona_realism/judge.py, and moving it would move
#: prompt_template_sha256 and invalidate every cached verdict. judge.yaml carries the
#: scale only in prose, so there is nothing to read it from; it is stated here at the
#: CLI edge, the same mirror-with-a-pointer the per-combination typicality chart uses,
#: rather than defaulted inside the builder where it would become a second source of
#: truth for a number the judge already fixed.
_TYPICALITY_LEVELS = 11

#: Extra spellings accepted for ``--typicality-metric``. The registry key of the
#: interval-assuming alternative is ``mean_level`` (it is a *level*, on a scale whose
#: levels are not evenly spaced -- the caveat the name carries); the plan and the
#: operator guide call the option ``mean``. Both resolve to the one registry entry, and
#: the choices are still derived from :data:`TYPICALITY_STATISTICS` rather than restated,
#: so a new statistic is selectable the moment it is defined.
_TYPICALITY_METRIC_ALIASES = {"mean": "mean_level"}


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
    parser.add_argument(
        "--rounds", type=int, default=None, dest="rounds",
        help="Judge rounds consumed per persona (blank = the published artifacts, or the "
        "shallowest cached depth when the set agrees on everything but its round count). "
        "Must be >= 1. When set, every competitor is re-reduced from its verdict cache "
        "over its first N rounds and a persona holding fewer than N fails the run; "
        "nothing is re-judged and no LLM call is made.",
    )
    parser.add_argument(
        "--driver-top-n", type=int, default=5, dest="driver_top_n",
        help="Severity drivers published per cell per level (attribute pairs, and category "
        "pairs within each). Default: 5. What falls below the cut is counted, not dropped "
        "silently.",
    )
    parser.add_argument(
        "--driver-min-count", type=int, default=3, dest="driver_min_count",
        help="Personas a driver must be exhibited by before it is ranked. Default: 3. Below "
        "it the driver is suppressed and counted -- publishing a rank-1 driver seen in two "
        "personas presents an anecdote as a finding.",
    )
    parser.add_argument(
        "--pair-summary-top-n", type=int, default=15, dest="pair_summary_top_n",
        help="Attribute pairs drawn on each severity_pair_summary figure. Default: 15. What "
        "falls below the cut is printed on the figure itself, never dropped silently.",
    )
    parser.add_argument(
        "--typicality-metric", dest="typicality_metric", default="iov",
        choices=sorted(set(TYPICALITY_STATISTICS) | set(_TYPICALITY_METRIC_ALIASES)),
        help="Statistic in each typicality cell. Default: iov -- Berry-Mielke's index of "
        "ordinal variation, which is invariant to any strictly increasing relabelling of "
        "the levels and separates a {0,10} split from a {9,10} one. 'mean'/'mean_level' "
        "measures location instead and assumes the levels are equally spaced; that caveat "
        "is then published as a column on every emitted row.",
    )
    parser.add_argument(
        "--typicality-min-n", type=int, default=30, dest="typicality_min_n",
        help="Typicality-bearing personas a competitor needs before its cell is read as "
        "powered. Default: 30. A cell below it is flagged under_powered and counted -- "
        "never dropped, and never confused with an unjudged pair.",
    )
    parser.add_argument(
        "--typicality-tail-threshold", type=int, default=5,
        dest="typicality_tail_threshold",
        help="k0 of the secondary P(typicality <= k0) column, on the judge's 0-10 scale. "
        "Default: 5. Deliberately not the per-combination chart's 3.0 (judge.yaml "
        "reliability.tail_threshold, which shades that figure's bars and feeds "
        "tail_coverage): at k0=3 a sixth of the swedish_02 cells sit at exactly 0.000 and "
        "the column carries almost nothing.",
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

    # What the driver tables do not show, on the same screen as what they do. A reader
    # who sees only the top-5 rows would otherwise have no way to tell an exhaustive
    # table from the visible tip of a long tail.
    drivers = ranking["severity_drivers"]
    excluded = drivers["excluded"]
    print(
        f"severity drivers: top {drivers['top_n']} per cell, ranked from "
        f"{drivers['min_count']} persona(s) up. Excluded -- "
        f"{excluded['combinations_skipped']} unconsumable combination(s), "
        f"{excluded['personas_without_a_successful_round']} persona(s) with no successful "
        f"round, {excluded['clashes_unresolved']} clash(es) with no category value to join, "
        f"{excluded['drivers_below_min_count']} driver(s) below min-count, "
        f"{excluded['drivers_below_top_n']} below the top-n cut."
    )

    # Same purpose as the driver line above: the typicality cells a reader must not read
    # as ordinary ones, on the same screen as the axis they belong to. The reference is
    # printed because it is the figure's midpoint -- when it is absent, the heatmap
    # degrades to a neutral ramp and the reader needs to know that from the console too.
    typicality = ranking["typicality"]
    if typicality is not None:
        excluded = typicality["excluded"]
        reference = typicality["reference_value"]
        midpoint = (
            "no real population -- neutral ramp"
            if reference is None
            else f"{typicality['reference_slug']} = {reference:.4f}"
        )
        print(
            f"typicality: {typicality['statistic']} over "
            f"{typicality['n_levels']} levels, min_n {typicality['min_n']}, "
            f"tail P(T<={typicality['tail_threshold']}). Reference midpoint -- {midpoint}. "
            f"Excluded -- {excluded['competitors_under_powered']} under-powered "
            f"competitor(s), {excluded['competitors_without_typicality']} with no "
            f"typicality-bearing persona, {excluded['cells_unjudged']} unjudged cell(s)."
        )

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
        if args.rounds is not None and args.rounds < 1:
            raise ValueError(f"--rounds must be >= 1, got {args.rounds}")
        # The judge config supplies the bootstrap block and the Levene centring, so the
        # intervals here are seeded exactly as the per-combination ones were. Both are
        # read fail-fast: no in-code default may silently disagree with judge.yaml.
        cfg = JudgeConfig.load(_CONFIG_DIR)
        variance_center = str(cfg.reliability_value("variance_center"))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolved once, at the edge, and passed verbatim: the builder holds no default for
    # any of these, so this bundle is the single place a reader finds what the numbers
    # were computed under. `n_levels` is the judge's fixed scale, the other three are
    # this script's flags.
    typicality_options = {
        "statistic": _TYPICALITY_METRIC_ALIASES.get(
            args.typicality_metric, args.typicality_metric
        ),
        "n_levels": _TYPICALITY_LEVELS,
        "min_n": args.typicality_min_n,
        "tail_threshold": args.typicality_tail_threshold,
    }

    output_base = resolve_output_base(args.output_base)
    ranking_dir = analysis_output_dir("realism_ranking", output_base)

    try:
        records, skipped = load_competitors(
            output_base,
            countries=country_filter, models=model_filter,
            strategies=strategy_filter, slugs=slug_filter, strict=args.strict,
            # `cfg` travels unconditionally, not only under --rounds: without it the
            # loader cannot re-derive a set that differs on its round count alone, so a
            # blank --rounds would report the heterogeneity instead of recovering from it.
            rounds_cap=args.rounds, judge_cfg=cfg,
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
            driver_top_n=args.driver_top_n, driver_min_count=args.driver_min_count,
            typicality=typicality_options,
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

        # Two grains, one table each: the attribute pairs that drove each cell, and the
        # category pairs under them. All three severity levels live in the same file
        # with `severity` as a column -- one scannable table per grain rather than one
        # per level, which left a reader diffing three files to compare a competitor
        # against itself. An empty table is a real (and reportable) outcome -- no clash
        # cleared --driver-min-count anywhere at any level -- so the absent file is
        # explained rather than left as a gap in the output set.
        for name, rows, grain in (
            ("severity_drivers.csv", severity_driver_rows(ranking), "attribute pair"),
            ("severity_driver_values.csv", severity_driver_value_rows(ranking), "category pair"),
        ):
            written = _write_csv(rows, country_dir / name)
            if written is not None:
                levels = sorted({row["severity"] for row in rows},
                                key=lambda level: SEVERITY_LEVELS.index(level))
                print(f"Driver CSV ({grain}) written to {written} "
                      f"-- {len(rows)} row(s) across {'/'.join(levels)}")
            else:
                print(f"No {name}: no {grain} reached "
                      f"--driver-min-count={args.driver_min_count} in any cell at any "
                      "severity level.")

        # The typicality axis at both grains: the scalar summary per competitor, and the
        # 11-bin histogram it summarises. The histogram is the published object -- it is
        # the table that survives a change of --typicality-metric -- so it is written
        # beside the summary rather than being reconstructable only from the JSON.
        for name, rows, grain in (
            ("typicality_summary.csv", typicality_summary_rows(ranking), "competitor"),
            ("typicality_histogram.csv", typicality_histogram_rows(ranking),
             "competitor x level"),
        ):
            written = _write_csv(rows, country_dir / name)
            if written is not None:
                print(f"Typicality CSV ({grain}) written to {written} -- {len(rows)} row(s)")
            else:
                print(f"No {name}: no competitor carries a typicality-bearing persona.")

        if not args.no_charts:
            charts = [
                ("headline_map", lambda: plot_headline_map(ranking)),
                ("impossibility_forest", lambda: plot_impossibility_forest(ranking)),
                ("impossibility_heatmap", lambda: plot_impossibility_heatmap(ranking)),
                # The typicality axis, on the same grid as the impossibility one and then
                # on the method axis. Both render the block verbatim -- the midpoint is
                # the real population's own value read from the document, never a literal.
                ("typicality_heatmap", lambda: plot_typicality_heatmap(ranking)),
                ("typicality_by_method", lambda: plot_typicality_by_method(ranking)),
            ]
            # One heatmap per severity level, same layout. `level=level` binds the loop
            # variable at definition time; a bare closure would render S1 three times.
            charts += [
                (f"severity_heatmap_{level.lower()}",
                 lambda level=level: plot_severity_heatmap(ranking, level))
                for level in SEVERITY_LEVELS
            ]
            # The complement of those heatmaps: what clashed, ranked country-wide. Built
            # from the loaded records rather than from `ranking`, because it must see the
            # FULL per-clash series -- the published severity_drivers block is already cut
            # per cell by --driver-top-n, and summing a per-cell top-N into a country total
            # would over-weight pairs that merely clear many cells' cut while erasing pairs
            # that are broad but never locally top-ranked.
            charts += [
                (f"severity_pair_summary_{level.lower()}",
                 lambda level=level: plot_severity_pair_summary(severity_pair_summary(
                     country_records, level, top_n=args.pair_summary_top_n,
                 )))
                for level in SEVERITY_LEVELS
            ]
            for name, build in charts:
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

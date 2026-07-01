"""
compare_runs.py -- Cross-run scientific comparison of run analytics.

Reads the per-run ``run_analytics.json`` files written by ``analyze_run.py`` under
the ``llm_metrics`` master folder, groups metrics by **model** and by
**method/strategy** (country held fixed), runs Kruskal-Wallis + Dunn post-hoc
tests, and writes a comparison report (JSON) plus box / bar / heatmap charts.

Prerequisite: run ``python scripts/analyze/analyze_run.py --all`` first to populate the
per-run analytics under ``{output_base}/03_Analysis/llm_metrics/{slug}/``.

Usage:
    python scripts/analyze/compare_runs.py
    python scripts/analyze/compare_runs.py --root path/to/llm_metrics --country swedish
    python scripts/analyze/compare_runs.py --metrics retry_rate wall_clock --output cmp.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from population_synth._paths import PROJECT_ROOT
from population_synth.llm_metrics.cross_run.comparison_charts import plot_run_comparison
from population_synth.llm_metrics.cross_run.run_comparison import (
    METRIC_SPECS,
    METRIC_SPECS_BY_KEY,
    build_comparison,
    load_run_records,
    write_comparison_json,
)

_CONFIG_PATH = PROJECT_ROOT / "config" / "analysis" / "analyze_defaults.yaml"

# If at least this fraction of *analysed* runs (those that had a run_analytics.json)
# fail to decompose into known axis IDs, treat it as a configuration error rather
# than silently comparing a depleted subset.
_MAX_DECOMPOSE_SKIP_FRACTION = 0.25


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def _default_root(cfg: dict) -> Path | None:
    output_base = cfg.get("output_base")
    analytics = cfg.get("analytics") or {}
    if not output_base:
        return None
    return (
        Path(output_base)
        / analytics.get("analysis_subdir", "03_Analysis")
        / analytics.get("task_subdir", "llm_metrics")
    )


def _print_console_summary(result: dict) -> None:
    print(f"\n=== Cross-Run Comparison ({result['metadata']['n_runs']} runs) ===")
    meta = result["metadata"]
    print(f"  models : {len(meta['models'])}   methods: {len(meta['methods'])}   "
          f"countries: {', '.join(meta['countries']) or '-'}")

    for key, entry in result["metrics"].items():
        print(f"\n{entry['label']}  [{key}]")
        if entry.get("skipped"):
            print(f"  skipped: {entry['skipped']}")
            continue
        for factor, factor_label in (("by_model", "by model"), ("by_method", "by method")):
            block = entry.get(factor)
            if block is None:
                continue
            kw = block["kruskal"]
            n_sig = sum(
                1 for d in block.get("dunn", [])
                if d.get("p_holm") is not None and d["p_holm"] < 0.05
            )
            if kw.get("p") is None:
                print(f"  {factor_label:9s}: Kruskal-Wallis n/a ({kw.get('note', '')})")
            else:
                print(f"  {factor_label:9s}: H={kw['H']:.2f}, p={kw['p']:.3g}  "
                      f"({n_sig} significant pair(s))")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-run scientific comparison of run analytics across models and "
            "methods. Reads per-run run_analytics.json files under the llm_metrics "
            "master folder."
        )
    )
    parser.add_argument(
        "--root", type=Path, default=None, metavar="DIR",
        help="llm_metrics master folder to scan (default: derived from config).",
    )
    parser.add_argument(
        "--output", type=Path, default=None, metavar="PATH",
        help="Write the comparison JSON here (default: {root}/_comparison/comparison.json).",
    )
    parser.add_argument(
        "--charts", type=Path, default=None, metavar="DIR",
        help="Write comparison charts here (default: {root}/_comparison/charts/).",
    )
    parser.add_argument(
        "--country", type=str, default=None,
        help="Restrict comparison to a single country ID (e.g. swedish).",
    )
    parser.add_argument(
        "--metrics", nargs="+", default=None, metavar="KEY",
        help=f"Subset of metrics to compare. Choices: {', '.join(METRIC_SPECS_BY_KEY)}",
    )
    args = parser.parse_args()

    cfg = _load_config()

    root: Path | None = args.root.resolve() if args.root else _default_root(cfg)
    if root is None:
        print("Error: no --root given and 'output_base' missing from config.", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"Error: llm_metrics root not found: {root}\n"
              "Run 'python scripts/analyze/analyze_run.py --all' first to populate it.",
              file=sys.stderr)
        sys.exit(1)

    if args.metrics:
        unknown = [m for m in args.metrics if m not in METRIC_SPECS_BY_KEY]
        if unknown:
            print(f"Error: unknown metric(s): {', '.join(unknown)}\n"
                  f"Valid: {', '.join(METRIC_SPECS_BY_KEY)}", file=sys.stderr)
            sys.exit(1)

    analytics = cfg.get("analytics") or {}
    comparison_dir = root / analytics.get("comparison_subdir", "_comparison")
    out_json = args.output or (comparison_dir / "comparison.json")
    charts_dir = args.charts or (comparison_dir / "charts")
    json_filename = analytics.get("json_filename", "run_analytics.json")

    records, skipped = load_run_records(root, json_filename=json_filename, country=args.country)

    # Separate benign skips (run simply not analysed yet) from decomposition
    # failures (a run HAS analytics but its slug no longer matches the axis IDs --
    # the silent-data-loss case worth guarding).
    decomp_skips = [(n, r) for (n, r) in skipped if r.startswith("slug not decomposable")]
    benign_skips = [(n, r) for (n, r) in skipped if not r.startswith("slug not decomposable")]

    if benign_skips:
        print(f"Skipped {len(benign_skips)} director(ies) with no analytics yet:")
        for name, reason in benign_skips:
            print(f"  {name}: {reason}")

    if decomp_skips:
        eligible = len(records) + len(decomp_skips)
        frac = len(decomp_skips) / eligible if eligible else 0.0
        print(
            f"\nWARNING: {len(decomp_skips)} analysed run(s) ({frac:.0%} of {eligible}) were "
            "EXCLUDED because their slug no longer matches the current model/strategy/country "
            "axis IDs under config/synthetic/axes/{models,strategies,countries}/:",
            file=sys.stderr,
        )
        for name, reason in decomp_skips:
            print(f"  {name}: {reason}", file=sys.stderr)
        if frac >= _MAX_DECOMPOSE_SKIP_FRACTION:
            print(
                f"\nError: {frac:.0%} of analysed runs were dropped as undecomposable "
                f"(threshold {_MAX_DECOMPOSE_SKIP_FRACTION:.0%}). This usually means an axis ID "
                "was renamed or removed. Fix the axis configs (or rename the run dirs) and re-run; "
                "pass nothing to override -- this guard prevents silently comparing a depleted subset.",
                file=sys.stderr,
            )
            sys.exit(1)

    if len(records) < 2:
        print(f"\nError: need at least 2 decodable runs to compare, found {len(records)}.\n"
              "Run 'python scripts/analyze/analyze_run.py --all' to populate more runs.",
              file=sys.stderr)
        sys.exit(1)

    print(f"\nLoaded {len(records)} run(s): "
          f"{len(set(r.model for r in records))} model(s) x "
          f"{len(set(r.strategy for r in records))} method(s).")

    metric_keys = args.metrics or [s.key for s in METRIC_SPECS]
    result = build_comparison(records, metric_keys=metric_keys)

    _print_console_summary(result)

    written_json = write_comparison_json(result, out_json)
    print(f"\nComparison JSON written to: {written_json.resolve()}")

    written = plot_run_comparison(result, charts_dir)
    if written:
        print(f"Charts written to {Path(charts_dir).resolve()}  ({len(written)} file(s))")
    else:
        print("No comparison charts generated (insufficient data).")


if __name__ == "__main__":
    main()

"""
analyze_run.py -- Parse and summarise an identity generation run directory.

Reads `llm_interactions.jsonl` (or `.json`) and `logs/run_*.log` from a run
directory, joins them by timestamp proximity, computes analytics, and prints a
summary table.  Optionally writes the full nested analytics dict to a JSON file.

Supports two directory layouts:

Single-persona dir
    The directory itself contains `llm_interactions.jsonl` (or `.json`) directly.

Batch dir
    The directory contains `persona_*/` subdirectories, each of which is a
    single-persona dir.

Usage:
    python scripts/analyze/analyze_run.py <run_dir> [--output run_analytics.json] [--verbose] [--charts DIR]
    python scripts/analyze/analyze_run.py --all [--verbose]

    <run_dir>         Path to a single-persona or batch run directory.
    --output PATH     Write the full analytics dict to this JSON file.
    --charts DIR      Write analytics charts (PNG) to this directory.
    --verbose         Also print per-persona breakdown after the run summary.
    --all             Discover every run under {output_base}/01_Raw/ and analyse
                      each one into the derived llm_metrics/{slug}/ folder.

Example output:

    === Run Analytics: /path/to/run_dir ===

    SUMMARY
      Total entries   : 42
      Total personas  : 3
      Total retries   : 7  (16.7%)
      Total errors    : 2  (4.8%)
      Token match rate: 100.0%  (42/42 entries matched)

    PER-CATEGORY METRICS
      Category             Calls   Retries   Errors   Tokens (avg)   Latency p95 (ms)
      ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from population_synth._paths import PROJECT_ROOT
from population_synth.analysis.llm_metrics.per_run.aggregator import compute_metrics
from population_synth.analysis.llm_metrics.per_run.charts import plot_run_charts
from population_synth.analysis.llm_metrics.per_run.console_report import print_metrics
from population_synth.analysis.llm_metrics.per_run.interaction_parser import (
    find_interaction_file,
    parse_interactions,
)
from population_synth.analysis.llm_metrics.per_run.joiner import join_entries
from population_synth.analysis.llm_metrics.per_run.log_parser import (
    find_log_files,
    parse_log_file,
    parse_run_summary,
)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG_PATH = PROJECT_ROOT / "config" / "analysis" / "analyze_defaults.yaml"


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def _derive_output_defaults(
    run_dir: Path, cfg: dict
) -> tuple[Path | None, Path | None]:
    """Return (default_json_output, default_charts_dir) derived from config.

    Returns (None, None) when config is absent or run_dir is not under
    the standard 01_Raw layout.
    """
    output_base = cfg.get("output_base")
    analytics = cfg.get("analytics") or {}
    if not output_base:
        return None, None

    raw_dir = Path(output_base) / "01_Raw"
    try:
        run_dir_resolved = run_dir.resolve()
        raw_dir_resolved = raw_dir.resolve()
    except OSError:
        return None, None

    if run_dir_resolved.parent != raw_dir_resolved:
        return None, None

    slug = run_dir_resolved.name
    # New layout: llm_metrics is a single master folder under 03_Analysis, with
    # one subfolder per config combination (slug) nested inside it.
    task_dir = (
        Path(output_base)
        / analytics.get("analysis_subdir", "03_Analysis")
        / analytics.get("task_subdir", "llm_metrics")
        / slug
    )
    default_json = task_dir / analytics.get("json_filename", "run_analytics.json")
    default_charts = task_dir / analytics.get("charts_subdir", "charts")
    return default_json, default_charts


# ---------------------------------------------------------------------------
# Directory detection
# ---------------------------------------------------------------------------

def _find_persona_dirs(run_dir: Path) -> list[Path]:
    """Return sorted list of persona_* subdirectories inside *run_dir*."""
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("persona_"))


def _is_single_persona_dir(run_dir: Path) -> bool:
    """Return True if *run_dir* directly contains an interaction file."""
    return find_interaction_file(run_dir) is not None


# ---------------------------------------------------------------------------
# Per-persona processing
# ---------------------------------------------------------------------------

def _process_persona_dir(persona_dir: Path) -> tuple[list[dict], dict | None]:
    """Parse, join, and return (enriched_entries, run_summary) for one persona dir.

    Returns ([], None) if no interaction file is found.
    """
    interaction_file = find_interaction_file(persona_dir)
    if interaction_file is None:
        return [], None

    jsonl_entries = parse_interactions(interaction_file)

    log_files = find_log_files(persona_dir)
    log_entries: list[dict] = []
    run_summary: dict | None = None

    for lf in log_files:
        log_entries.extend(parse_log_file(lf))

    # Use the last log file for run summary (most recent run wins)
    if log_files:
        run_summary = parse_run_summary(log_files[-1])

    enriched = join_entries(jsonl_entries, log_entries)
    return enriched, run_summary


# ---------------------------------------------------------------------------
# Batch aggregation
# ---------------------------------------------------------------------------

def _process_batch_dir(run_dir: Path) -> dict[str, Any]:
    """Process a batch run directory with persona_* subdirs.

    Returns a combined analytics dict.  Per-persona entries are tagged with a
    ``persona_id`` field so ``compute_metrics`` can group them correctly.
    """
    persona_dirs = _find_persona_dirs(run_dir)

    all_entries: list[dict] = []
    combined_run_summary: dict | None = None

    for persona_dir in persona_dirs:
        entries, run_summary = _process_persona_dir(persona_dir)
        # Tag each entry with the persona folder name so aggregator can group them
        for entry in entries:
            entry["persona_id"] = persona_dir.name
        all_entries.extend(entries)
        # Prefer the summary that reports success/failed counts across all personas
        if run_summary is not None:
            combined_run_summary = run_summary

    # Parallel runs typically write a single top-level master log holding the
    # token/timing call records for every persona (the persona_* dirs carry no
    # logs/ of their own).  Parse it for both the run summary AND the call
    # records, and join those records against the combined persona entries so the
    # token/latency metrics are populated.  The join is exact when the records
    # carry a (persona_id, call_index) correlation key (runs that emit "corr=");
    # for older runs without it the join falls back to timestamp proximity, where
    # an interleaved parallel call may attach to the wrong persona's entry --
    # acceptable for aggregate/category token distributions but approximate
    # per-persona.
    top_level_logs = find_log_files(run_dir)
    top_level_log_entries: list[dict] = []
    for lf in top_level_logs:
        top_level_log_entries.extend(parse_log_file(lf))
    if top_level_logs:
        top_summary = parse_run_summary(top_level_logs[-1])
        if top_summary is not None:
            combined_run_summary = top_summary
    if top_level_log_entries:
        all_entries = join_entries(all_entries, top_level_log_entries)

    return compute_metrics(all_entries, run_summary=combined_run_summary)


def _compute_run_metrics(run_dir: Path) -> dict[str, Any] | None:
    """Compute the analytics dict for a run directory.

    Handles both single-persona dirs (interaction file directly inside) and
    batch dirs (persona_* subdirs).  Returns ``None`` when the directory holds
    no interaction data to analyse.
    """
    if _is_single_persona_dir(run_dir):
        entries, run_summary = _process_persona_dir(run_dir)
        return compute_metrics(entries, run_summary=run_summary)
    persona_dirs = _find_persona_dirs(run_dir)
    if persona_dirs:
        return _process_batch_dir(run_dir)
    return None


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def _write_json(metrics: dict[str, Any], run_dir: Path, output_path: Path) -> None:
    export = {"run_dir": str(run_dir.resolve())}
    export.update(metrics)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(export, fh, indent=2, ensure_ascii=False)
    print(f"Analytics written to: {output_path.resolve()}")


# ---------------------------------------------------------------------------
# Batch mode (--all)
# ---------------------------------------------------------------------------

def _run_all(cfg: dict) -> None:
    """Analyse every run under {output_base}/01_Raw/ into llm_metrics/{slug}/."""
    output_base = cfg.get("output_base")
    if not output_base:
        print("Error: --all requires 'output_base' in config/analysis/analyze_defaults.yaml", file=sys.stderr)
        sys.exit(1)

    raw_dir = Path(output_base) / "01_Raw"
    if not raw_dir.is_dir():
        print(f"Error: 01_Raw directory not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    run_dirs = sorted(d for d in raw_dir.iterdir() if d.is_dir())
    processed: list[str] = []
    skipped: list[str] = []
    total_charts = 0

    for run_dir in run_dirs:
        run_dir = run_dir.resolve()
        metrics = _compute_run_metrics(run_dir)
        if metrics is None:
            skipped.append(run_dir.name)
            continue

        default_json, default_charts = _derive_output_defaults(run_dir, cfg)
        if default_json is not None:
            _write_json(metrics, run_dir, default_json)
        n_charts = 0
        if default_charts is not None:
            written = plot_run_charts(metrics, default_charts)
            n_charts = len(written)
            total_charts += n_charts

        summary = metrics["summary"]
        print(
            f"  {run_dir.name}: {summary['total_personas']} personas, "
            f"{summary['total_entries']} entries, {n_charts} charts"
        )
        processed.append(run_dir.name)

    print(
        f"\nBatch complete: {len(processed)} run(s) processed, "
        f"{len(skipped)} skipped, {total_charts} chart(s) written."
    )
    if skipped:
        print(f"Skipped (no interaction data): {', '.join(skipped)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse and summarise an identity generation run directory. "
            "Supports single-persona dirs (contain llm_interactions.jsonl directly) "
            "and batch dirs (contain persona_* subdirs)."
        )
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Path to a single-persona or batch run directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write the full analytics dict to this JSON file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also print per-persona breakdown after the run summary.",
    )
    parser.add_argument(
        "--charts",
        type=Path,
        default=None,
        metavar="DIR",
        help="Write analytics charts (PNG) to this directory.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyse every run under {output_base}/01_Raw/ into llm_metrics/{slug}/.",
    )
    args = parser.parse_args()

    cfg = _load_config()

    if args.all:
        _run_all(cfg)
        return

    if args.run_dir is None:
        print("Error: run_dir is required (or pass --all).", file=sys.stderr)
        sys.exit(1)

    run_dir: Path = args.run_dir.resolve()

    # Apply config-derived defaults for --output and --charts when not provided
    default_json, default_charts = _derive_output_defaults(run_dir, cfg)
    if args.output is None and default_json is not None:
        args.output = default_json
    if args.charts is None and default_charts is not None:
        args.charts = default_charts

    if not run_dir.exists():
        print(f"Error: run_dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(1)
    if not run_dir.is_dir():
        print(f"Error: run_dir is not a directory: {run_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine directory type and process
    metrics = _compute_run_metrics(run_dir)
    if metrics is None:
        print(
            f"Warning: no interaction file found in {run_dir} and no persona_* "
            "subdirs detected. Nothing to analyse.",
            file=sys.stderr,
        )
        sys.exit(1)

    print_metrics(metrics, run_dir, verbose=args.verbose)

    if args.output is not None:
        _write_json(metrics, run_dir, args.output)

    if args.charts is not None:
        written = plot_run_charts(metrics, args.charts)
        if written:
            print(f"Charts written to {args.charts.resolve()}  ({len(written)} file(s))")
            for p in written:
                print(f"  {p.name}")
        else:
            print("No charts generated (insufficient data).")


if __name__ == "__main__":
    main()

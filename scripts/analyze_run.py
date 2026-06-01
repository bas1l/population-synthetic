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
    python scripts/analyze_run.py <run_dir> [--output run_analytics.json] [--verbose]

    <run_dir>         Path to a single-persona or batch run directory.
    --output PATH     Write the full analytics dict to this JSON file.
    --verbose         Also print per-persona breakdown after the run summary.

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

from population_synth.analysis.interaction_parser import (
    find_interaction_file,
    parse_interactions,
)
from population_synth.analysis.log_parser import (
    find_log_files,
    parse_log_file,
    parse_run_summary,
)
from population_synth.analysis.joiner import join_entries
from population_synth.analysis.aggregator import compute_metrics


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

    # Also look for a top-level log (some parallel runs write one master log)
    top_level_logs = find_log_files(run_dir)
    top_level_log_entries: list[dict] = []
    for lf in top_level_logs:
        top_level_log_entries.extend(parse_log_file(lf))
    if top_level_logs:
        top_summary = parse_run_summary(top_level_logs[-1])
        if top_summary is not None:
            combined_run_summary = top_summary

    return compute_metrics(all_entries, run_summary=combined_run_summary)


# ---------------------------------------------------------------------------
# Console formatting helpers
# ---------------------------------------------------------------------------

_COL_SEP = "  "


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{100.0 * numerator / denominator:.1f}%"


def _fmt_float(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def _print_summary(metrics: dict[str, Any], run_dir: Path) -> None:
    summary = metrics["summary"]
    total = summary["total_entries"]
    personas = summary["total_personas"]
    retries = summary["total_retries"]
    errors = summary["total_errors"]
    match_rate = summary["token_match_rate"]
    run_sum = summary.get("run_summary")

    print(f"\n=== Run Analytics: {run_dir.resolve()} ===\n")
    print("SUMMARY")
    print(f"  Total entries   : {total}")
    print(f"  Total personas  : {personas}")

    retry_pct = f"  ({_fmt_pct(retries, total)})" if total else ""
    print(f"  Total retries   : {retries}{retry_pct}")

    error_pct = f"  ({_fmt_pct(errors, total)})" if total else ""
    print(f"  Total errors    : {errors}{error_pct}")

    if match_rate is not None:
        matched_count = round(match_rate * total)
        print(f"  Token match rate: {match_rate * 100:.1f}%  ({matched_count}/{total} entries matched)")
    else:
        print("  Token match rate: n/a  (no log data)")

    if run_sum is not None:
        print(f"  Run wall clock  : {run_sum['elapsed_s']:.1f}s  "
              f"(success={run_sum['success']}, failed={run_sum['failed']})")


def _print_per_category(metrics: dict[str, Any]) -> None:
    per_cat = metrics.get("per_category", {})
    if not per_cat:
        return

    latency = metrics.get("latency_by_category") or {}
    tok_cat = metrics.get("token_consumption_per_category") or {}
    has_tokens = bool(tok_cat)
    has_latency = bool(latency)

    # Determine column widths
    cat_width = max(len("Category"), max(len(c) for c in per_cat))
    cat_width = min(cat_width, 40)  # cap at 40 chars

    headers = ["Category", "Calls", "Retries", "Errors"]
    if has_tokens:
        headers.append("Tokens (avg)")
    if has_latency:
        headers.append("Latency p95 (ms)")

    row_fmt_parts = [f"{{:<{cat_width}}}", "{:>6}", "{:>8}", "{:>7}"]
    if has_tokens:
        row_fmt_parts.append("{:>13}")
    if has_latency:
        row_fmt_parts.append("{:>17}")
    row_fmt = _COL_SEP.join(row_fmt_parts)

    separator_width = (
        cat_width + 6 + 8 + 7
        + (13 if has_tokens else 0)
        + (17 if has_latency else 0)
        + len(_COL_SEP) * (len(headers) - 1)
    )

    print("\nPER-CATEGORY METRICS")
    print("  " + row_fmt.format(*headers))
    print("  " + "─" * separator_width)

    for cat in sorted(per_cat):
        info = per_cat[cat]
        calls = info["call_count"]
        retries_c = info["retry_count"]
        errors_c = sum(info["error_taxonomy"].values())

        row_vals: list[Any] = [cat[:cat_width], calls, retries_c, errors_c]

        if has_tokens:
            cat_tok = tok_cat.get(cat)
            if cat_tok and calls > 0:
                avg_tok = (cat_tok["prompt_tokens"] + cat_tok["completion_tokens"]) / calls
                row_vals.append(f"{avg_tok:.0f}")
            else:
                row_vals.append("—")

        if has_latency:
            lat = latency.get(cat)
            p95 = lat["p95_ms"] if lat else None
            row_vals.append(_fmt_float(p95, 0) if p95 is not None else "—")

        print("  " + row_fmt.format(*row_vals))


def _print_method_distribution(metrics: dict[str, Any]) -> None:
    dist = metrics.get("method_distribution", {})
    if not dist:
        return
    print("\nMETHOD DISTRIBUTION")
    parts = [f"{method}: {count}" for method, count in sorted(dist.items())]
    print("  " + "  ".join(parts))


def _print_value_diversity(metrics: dict[str, Any]) -> None:
    diversity = metrics.get("value_diversity", {})
    if not diversity:
        return
    print("\nVALUE DIVERSITY (Shannon entropy bits)")
    parts = []
    for cat in sorted(diversity):
        info = diversity[cat]
        parts.append(f"{cat}: {info['entropy_bits']:.2f}")
    # Print in rows of ~5 entries for readability
    chunk = 5
    for i in range(0, len(parts), chunk):
        print("  " + "  ".join(parts[i:i + chunk]))


def _print_token_budget(metrics: dict[str, Any]) -> None:
    budget = metrics.get("token_budget_by_step_type")
    if not budget:
        return
    print("\nTOKEN BUDGET BY STEP TYPE")
    step_width = max(len("Step"), max(len(s) for s in budget))
    step_width = min(step_width, 20)

    row_fmt = f"  {{:<{step_width}}}" + _COL_SEP + "{:>8}" + _COL_SEP + "{:>12}" + _COL_SEP + "{:>13}"
    print(row_fmt.format("Step", "Calls", "Prompt tok", "Completion tok"))
    print("  " + "─" * (step_width + 8 + 12 + 13 + len(_COL_SEP) * 3))
    for stype in sorted(budget):
        info = budget[stype]
        print(row_fmt.format(
            stype[:step_width],
            info["call_count"],
            info["prompt_tokens"],
            info["completion_tokens"],
        ))


def _print_per_persona_verbose(metrics: dict[str, Any]) -> None:
    wall = metrics.get("wall_clock_per_persona", {})
    tok_per = metrics.get("token_consumption_per_persona") or {}

    if not wall and not tok_per:
        return

    print("\nPER-PERSONA BREAKDOWN")
    all_pids = sorted(set(list(wall.keys()) + list(tok_per.keys())))

    pid_width = max(len("Persona"), max(len(p) for p in all_pids)) if all_pids else 7
    pid_width = min(pid_width, 30)

    has_wall = bool(wall)
    has_tok = bool(tok_per)

    header_parts = [f"{'Persona':<{pid_width}}"]
    if has_wall:
        header_parts.append(f"{'Wall (s)':>10}")
    if has_tok:
        header_parts.append(f"{'Prompt tok':>12}")
        header_parts.append(f"{'Compl tok':>11}")
    print("  " + _COL_SEP.join(header_parts))

    sep_width = pid_width + (10 if has_wall else 0) + (12 if has_tok else 0) + (11 if has_tok else 0)
    sep_width += len(_COL_SEP) * (len(header_parts) - 1)
    print("  " + "─" * sep_width)

    for pid in all_pids:
        row_parts = [f"{pid[:pid_width]:<{pid_width}}"]
        if has_wall:
            w = wall.get(pid)
            row_parts.append(f"{_fmt_float(w, 1):>10}")
        if has_tok:
            t = tok_per.get(pid)
            pt = t["prompt_tokens"] if t else 0
            ct = t["completion_tokens"] if t else 0
            row_parts.append(f"{pt:>12}")
            row_parts.append(f"{ct:>11}")
        print("  " + _COL_SEP.join(row_parts))


def _print_metrics(metrics: dict[str, Any], run_dir: Path, verbose: bool) -> None:
    _print_summary(metrics, run_dir)
    _print_per_category(metrics)
    _print_method_distribution(metrics)
    _print_value_diversity(metrics)
    _print_token_budget(metrics)
    if verbose:
        _print_per_persona_verbose(metrics)
    print()


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
    args = parser.parse_args()

    run_dir: Path = args.run_dir.resolve()

    if not run_dir.exists():
        print(f"Error: run_dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(1)
    if not run_dir.is_dir():
        print(f"Error: run_dir is not a directory: {run_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine directory type and process
    if _is_single_persona_dir(run_dir):
        entries, run_summary = _process_persona_dir(run_dir)
        metrics = compute_metrics(entries, run_summary=run_summary)
    else:
        persona_dirs = _find_persona_dirs(run_dir)
        if persona_dirs:
            metrics = _process_batch_dir(run_dir)
        else:
            print(
                f"Warning: no interaction file found in {run_dir} and no persona_* "
                "subdirs detected. Nothing to analyse.",
                file=sys.stderr,
            )
            sys.exit(1)

    _print_metrics(metrics, run_dir, verbose=args.verbose)

    if args.output is not None:
        _write_json(metrics, run_dir, args.output)


if __name__ == "__main__":
    main()

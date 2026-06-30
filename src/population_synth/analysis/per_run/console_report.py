"""
console_report.py -- Render run-analytics metrics as console text tables.

Turns the nested metrics dict produced by
:func:`population_synth.analysis.per_run.aggregator.compute_metrics` into the
human-readable summary tables printed by ``scripts/analyze/analyze_run.py``.  This is the
presentation concern only -- no orchestration, I/O, or metric computation.

Entry point: :func:`print_metrics`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    print("  " + "-" * separator_width)

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
    print("  " + "-" * (step_width + 8 + 12 + 13 + len(_COL_SEP) * 3))
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
    print("  " + "-" * sep_width)

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


def print_metrics(metrics: dict[str, Any], run_dir: Path, verbose: bool) -> None:
    _print_summary(metrics, run_dir)
    _print_per_category(metrics)
    _print_method_distribution(metrics)
    _print_value_diversity(metrics)
    _print_token_budget(metrics)
    if verbose:
        _print_per_persona_verbose(metrics)
    print()

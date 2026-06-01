"""Compute v1 analytics metrics from interaction data.

Entry point: :func:`compute_metrics`.

Accepts:
- ``entries``      — list of enriched dicts from :func:`joiner.join_entries`
                     (or plain JSONL dicts from :func:`interaction_parser.parse_interactions`
                     when no log data is available)
- ``run_summary``  — optional dict ``{elapsed_s, success, failed}`` from
                     :func:`log_parser.parse_run_summary`

Returns a nested dict with the following top-level keys:

``summary``
    Overview counts and match quality.

``per_category``
    Per-category call counts, retry rates, and error taxonomy.

``method_distribution``
    Raw counts per generation method string.

``prompt_size_growth``
    Ordered list of ``{position, category, prompt_len}`` pairs.

``response_verbosity``
    Per-entry ratio of ``len(raw_response)`` to ``len(json.dumps(parsed_value))``.

``wall_clock_per_persona``
    First-to-last timestamp span in seconds per persona_id.

``value_diversity``
    Shannon entropy (bits) per category computed from the distribution of
    resolved values across entries.

``token_consumption_per_persona``
    Sum of prompt + completion tokens per persona_id (None when no token data).

``token_consumption_per_category``
    Token sums by category (None when no token data).

``tokens_per_second``
    Completion tokens / (elapsed_ms / 1000) per entry (where available).

``latency_by_category``
    Median, p95, and max elapsed_ms per category (None when no timing data).

``token_budget_by_step_type``
    prompt_tokens and completion_tokens summed by step type classification
    (None when no token data).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string into a UTC datetime.  Returns None on failure."""
    if not ts:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(ts.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _median(values: list[float]) -> float | None:
    """Return the median of a non-empty list of floats."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def _percentile(values: list[float], p: float) -> float | None:
    """Return the *p*-th percentile (0–100) using nearest-rank method."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    # nearest-rank: ceil(p/100 * n) - 1 (0-based), clamped
    idx = max(0, min(n - 1, int(math.ceil(p / 100.0 * n)) - 1))
    return s[idx]


def _shannon_entropy(counts: dict[str, int]) -> float:
    """Compute Shannon entropy in bits for a frequency distribution."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def _classify_step(step: str | None) -> str:
    """Map a step string to a coarse step type category."""
    if step is None:
        return "unknown"
    s = step.lower()
    if s.endswith("_retry"):
        return "retry"
    if "enumerate" in s:
        return "enumerate"
    if "evaluate" in s:
        return "evaluate"
    if "pick" in s:
        return "pick"
    return "other"


def _resolved_value(entry: dict[str, Any]) -> str | None:
    """Extract the resolved scalar value from a parsed_value dict (or raw value)."""
    pv = entry.get("parsed_value")
    if pv is None:
        return None
    if isinstance(pv, dict):
        # Most entries: {"value": <scalar>}
        v = pv.get("value")
        if v is not None:
            return str(v)
        # Fallback: stringify the whole dict
        return json.dumps(pv, ensure_ascii=False)
    return str(pv)


def _persona_id(entry: dict[str, Any], index: int) -> str:
    """Return a stable persona identifier for grouping.

    Entries from multi-persona runs have a ``persona_id`` field injected by the
    batch aggregation layer (see :func:`compute_metrics`).  Single-persona runs
    produce entries without that field; all entries are grouped under ``"single"``.
    """
    return entry.get("persona_id") or "single"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_metrics(
    entries: list[dict[str, Any]],
    run_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute all v1 analytics metrics for a single run.

    Parameters
    ----------
    entries:
        Enriched interaction dicts from :func:`joiner.join_entries`, or plain
        JSONL dicts from :func:`interaction_parser.parse_interactions`.  Each
        entry must contain at minimum the fields defined by ``LLMInteractionEntry``
        (``category``, ``method``, ``step``, ``prompt``, ``raw_response``,
        ``parsed_value``, ``error``, ``attempt``, ``timestamp``).  Token/timing
        fields (``prompt_tokens``, ``completion_tokens``, ``elapsed_ms``) are
        optional; if absent or all-``None``, the corresponding metric groups are
        omitted from the output.
    run_summary:
        Optional summary dict from :func:`log_parser.parse_run_summary`.

    Returns
    -------
    dict
        Nested analytics dict described in the module docstring.
    """
    if not entries:
        return {
            "summary": {
                "total_entries": 0,
                "total_personas": 0,
                "total_retries": 0,
                "total_errors": 0,
                "token_match_rate": None,
                "run_summary": run_summary,
            },
            "per_category": {},
            "method_distribution": {},
            "prompt_size_growth": [],
            "response_verbosity": [],
            "wall_clock_per_persona": {},
            "value_diversity": {},
            "token_consumption_per_persona": None,
            "token_consumption_per_category": None,
            "tokens_per_second": None,
            "latency_by_category": None,
            "token_budget_by_step_type": None,
        }

    # ------------------------------------------------------------------
    # Derived flags
    # ------------------------------------------------------------------
    has_token_data = any(
        e.get("prompt_tokens") is not None or e.get("completion_tokens") is not None
        for e in entries
    )

    # ------------------------------------------------------------------
    # Summary counters
    # ------------------------------------------------------------------
    total_entries = len(entries)
    total_retries = sum(
        1 for e in entries if (e.get("step") or "").endswith("_retry")
    )
    total_errors = sum(1 for e in entries if e.get("error") is not None)

    persona_ids: set[str] = set()
    for i, e in enumerate(entries):
        persona_ids.add(_persona_id(e, i))
    total_personas = len(persona_ids)

    token_matched = sum(
        1 for e in entries
        if e.get("prompt_tokens") is not None or e.get("completion_tokens") is not None
    )
    token_match_rate: float | None = (
        token_matched / total_entries if has_token_data else None
    )

    # ------------------------------------------------------------------
    # per_category
    # ------------------------------------------------------------------
    # Structure per category:
    #   call_count, retry_count, retry_rate, error_taxonomy, method_retry_counts
    cat_call: dict[str, int] = defaultdict(int)
    cat_retry: dict[str, int] = defaultdict(int)
    cat_errors: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cat_method_retries: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for e in entries:
        cat = e.get("category") or "__unknown__"
        step = e.get("step") or ""
        method = e.get("method") or "__unknown__"
        is_retry = step.endswith("_retry")

        cat_call[cat] += 1
        if is_retry:
            cat_retry[cat] += 1
            cat_method_retries[cat][method] += 1
        if e.get("error") is not None:
            # Use first "word" of the error string as error type
            error_str = str(e["error"])
            error_type = error_str.split(":")[0].split("\n")[0].strip()
            cat_errors[cat][error_type] += 1

    per_category: dict[str, Any] = {}
    all_cats = set(cat_call) | set(cat_retry)
    for cat in all_cats:
        calls = cat_call.get(cat, 0)
        retries = cat_retry.get(cat, 0)
        per_category[cat] = {
            "call_count": calls,
            "retry_count": retries,
            "retry_rate": round(retries / calls, 4) if calls > 0 else 0.0,
            "error_taxonomy": dict(cat_errors.get(cat, {})),
            "method_retry_counts": dict(cat_method_retries.get(cat, {})),
        }

    # ------------------------------------------------------------------
    # method_distribution
    # ------------------------------------------------------------------
    method_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        method = e.get("method") or "__unknown__"
        method_counts[method] += 1
    method_distribution = dict(method_counts)

    # ------------------------------------------------------------------
    # prompt_size_growth
    # ------------------------------------------------------------------
    # Ordered by entry position (chain position within a persona).
    # For multi-persona runs, group by persona then record position within group.
    persona_positions: dict[str, int] = defaultdict(int)
    prompt_size_growth: list[dict[str, Any]] = []
    for i, e in enumerate(entries):
        pid = _persona_id(e, i)
        pos = persona_positions[pid]
        persona_positions[pid] += 1
        prompt_text = e.get("prompt") or ""
        prompt_size_growth.append(
            {
                "global_index": i,
                "persona_id": pid,
                "chain_position": pos,
                "category": e.get("category"),
                "prompt_len": len(prompt_text),
            }
        )

    # ------------------------------------------------------------------
    # response_verbosity
    # ------------------------------------------------------------------
    response_verbosity: list[dict[str, Any]] = []
    for i, e in enumerate(entries):
        raw = e.get("raw_response") or ""
        pv = e.get("parsed_value")
        try:
            parsed_str = json.dumps(pv, ensure_ascii=False) if pv is not None else ""
        except (TypeError, ValueError):
            parsed_str = str(pv) if pv is not None else ""
        raw_len = len(raw)
        parsed_len = len(parsed_str)
        ratio = round(raw_len / parsed_len, 4) if parsed_len > 0 else None
        response_verbosity.append(
            {
                "global_index": i,
                "persona_id": _persona_id(e, i),
                "category": e.get("category"),
                "raw_response_len": raw_len,
                "parsed_value_len": parsed_len,
                "verbosity_ratio": ratio,
            }
        )

    # ------------------------------------------------------------------
    # wall_clock_per_persona
    # ------------------------------------------------------------------
    persona_timestamps: dict[str, list[datetime]] = defaultdict(list)
    for i, e in enumerate(entries):
        pid = _persona_id(e, i)
        dt = _parse_iso(e.get("timestamp"))
        if dt is not None:
            persona_timestamps[pid].append(dt)

    wall_clock_per_persona: dict[str, float | None] = {}
    for pid, dts in persona_timestamps.items():
        if len(dts) >= 2:
            span = (max(dts) - min(dts)).total_seconds()
            wall_clock_per_persona[pid] = round(span, 3)
        else:
            wall_clock_per_persona[pid] = None

    # ------------------------------------------------------------------
    # value_diversity (Shannon entropy per category)
    # ------------------------------------------------------------------
    cat_value_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        cat = e.get("category") or "__unknown__"
        val = _resolved_value(e)
        if val is not None:
            cat_value_counts[cat][val] += 1

    value_diversity: dict[str, Any] = {}
    for cat, counts in cat_value_counts.items():
        entropy = _shannon_entropy(counts)
        value_diversity[cat] = {
            "entropy_bits": round(entropy, 4),
            "unique_values": len(counts),
            "value_counts": dict(counts),
        }

    # ------------------------------------------------------------------
    # Token metrics (only when token data is present)
    # ------------------------------------------------------------------
    token_consumption_per_persona: dict[str, Any] | None = None
    token_consumption_per_category: dict[str, Any] | None = None
    tokens_per_second: list[dict[str, Any]] | None = None
    latency_by_category: dict[str, Any] | None = None
    token_budget_by_step_type: dict[str, Any] | None = None

    if has_token_data:
        # token_consumption_per_persona
        persona_prompt: dict[str, int] = defaultdict(int)
        persona_completion: dict[str, int] = defaultdict(int)
        for i, e in enumerate(entries):
            pid = _persona_id(e, i)
            pt = e.get("prompt_tokens")
            ct = e.get("completion_tokens")
            if pt is not None:
                persona_prompt[pid] += pt
            if ct is not None:
                persona_completion[pid] += ct
        token_consumption_per_persona = {
            pid: {
                "prompt_tokens": persona_prompt.get(pid, 0),
                "completion_tokens": persona_completion.get(pid, 0),
                "total_tokens": persona_prompt.get(pid, 0) + persona_completion.get(pid, 0),
            }
            for pid in persona_ids
        }

        # token_consumption_per_category
        cat_prompt: dict[str, int] = defaultdict(int)
        cat_completion: dict[str, int] = defaultdict(int)
        for e in entries:
            cat = e.get("category") or "__unknown__"
            pt = e.get("prompt_tokens")
            ct = e.get("completion_tokens")
            if pt is not None:
                cat_prompt[cat] += pt
            if ct is not None:
                cat_completion[cat] += ct
        all_token_cats = set(cat_prompt) | set(cat_completion)
        token_consumption_per_category = {
            cat: {
                "prompt_tokens": cat_prompt.get(cat, 0),
                "completion_tokens": cat_completion.get(cat, 0),
                "total_tokens": cat_prompt.get(cat, 0) + cat_completion.get(cat, 0),
            }
            for cat in all_token_cats
        }

        # tokens_per_second (per entry)
        tokens_per_second = []
        for i, e in enumerate(entries):
            ct = e.get("completion_tokens")
            elapsed = e.get("elapsed_ms")
            if ct is not None and elapsed is not None and elapsed > 0:
                tps = round(ct / (elapsed / 1000.0), 2)
            else:
                tps = None
            tokens_per_second.append(
                {
                    "global_index": i,
                    "persona_id": _persona_id(e, i),
                    "category": e.get("category"),
                    "completion_tokens": ct,
                    "elapsed_ms": elapsed,
                    "tokens_per_second": tps,
                }
            )

        # latency_by_category
        cat_latencies: dict[str, list[float]] = defaultdict(list)
        for e in entries:
            elapsed = e.get("elapsed_ms")
            if elapsed is not None:
                cat = e.get("category") or "__unknown__"
                cat_latencies[cat].append(elapsed)

        latency_by_category = {}
        for cat, lats in cat_latencies.items():
            latency_by_category[cat] = {
                "median_ms": _median(lats),
                "p95_ms": _percentile(lats, 95),
                "max_ms": max(lats) if lats else None,
                "count": len(lats),
            }

        # token_budget_by_step_type
        step_type_prompt: dict[str, int] = defaultdict(int)
        step_type_completion: dict[str, int] = defaultdict(int)
        step_type_count: dict[str, int] = defaultdict(int)
        for e in entries:
            stype = _classify_step(e.get("step"))
            pt = e.get("prompt_tokens")
            ct = e.get("completion_tokens")
            step_type_count[stype] += 1
            if pt is not None:
                step_type_prompt[stype] += pt
            if ct is not None:
                step_type_completion[stype] += ct
        all_step_types = set(step_type_prompt) | set(step_type_completion) | set(step_type_count)
        token_budget_by_step_type = {
            stype: {
                "call_count": step_type_count.get(stype, 0),
                "prompt_tokens": step_type_prompt.get(stype, 0),
                "completion_tokens": step_type_completion.get(stype, 0),
                "total_tokens": (
                    step_type_prompt.get(stype, 0)
                    + step_type_completion.get(stype, 0)
                ),
            }
            for stype in all_step_types
        }

    # ------------------------------------------------------------------
    # Assemble output
    # ------------------------------------------------------------------
    return {
        "summary": {
            "total_entries": total_entries,
            "total_personas": total_personas,
            "total_retries": total_retries,
            "total_errors": total_errors,
            "token_match_rate": (
                round(token_match_rate, 4) if token_match_rate is not None else None
            ),
            "run_summary": run_summary,
        },
        "per_category": per_category,
        "method_distribution": method_distribution,
        "prompt_size_growth": prompt_size_growth,
        "response_verbosity": response_verbosity,
        "wall_clock_per_persona": wall_clock_per_persona,
        "value_diversity": value_diversity,
        "token_consumption_per_persona": token_consumption_per_persona,
        "token_consumption_per_category": token_consumption_per_category,
        "tokens_per_second": tokens_per_second,
        "latency_by_category": latency_by_category,
        "token_budget_by_step_type": token_budget_by_step_type,
    }

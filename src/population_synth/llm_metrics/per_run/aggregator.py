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
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from population_synth.llm_metrics.shared._stats import median, percentile, shannon_entropy

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
# Per-metric-family computations
#
# Each helper consumes the entry list (plus any cross-cutting context it needs)
# and returns exactly one slice of the final metrics dict.  ``compute_metrics``
# is a thin assembler over these.  The five token-gated families are only called
# when ``has_token_data`` is true; otherwise the assembler emits ``None``.
# ---------------------------------------------------------------------------

def _summary(
    entries: list[dict[str, Any]],
    persona_ids: set[str],
    has_token_data: bool,
    run_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Overview counts and token-match quality."""
    total_entries = len(entries)
    total_retries = sum(1 for e in entries if (e.get("step") or "").endswith("_retry"))
    total_errors = sum(1 for e in entries if e.get("error") is not None)

    token_matched = sum(
        1 for e in entries
        if e.get("prompt_tokens") is not None or e.get("completion_tokens") is not None
    )
    token_match_rate: float | None = (
        token_matched / total_entries if has_token_data and total_entries else None
    )
    return {
        "total_entries": total_entries,
        "total_personas": len(persona_ids),
        "total_retries": total_retries,
        "total_errors": total_errors,
        "token_match_rate": (
            round(token_match_rate, 4) if token_match_rate is not None else None
        ),
        "run_summary": run_summary,
    }


def _per_category(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-category call counts, retry rates, error taxonomy, method retries."""
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
    return per_category


def _method_distribution(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Raw counts per generation method string."""
    method_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        method = e.get("method") or "__unknown__"
        method_counts[method] += 1
    return dict(method_counts)


def _prompt_size_growth(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prompt length tagged with per-persona chain position."""
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
    return prompt_size_growth


def _response_verbosity(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-entry ratio of raw-response length to serialized parsed-value length."""
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
    return response_verbosity


def _wall_clock_per_persona(entries: list[dict[str, Any]]) -> dict[str, float | None]:
    """First-to-last timestamp span (seconds) per persona."""
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
    return wall_clock_per_persona


def _value_diversity(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Shannon entropy (bits) of resolved values per category."""
    cat_value_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        cat = e.get("category") or "__unknown__"
        val = _resolved_value(e)
        if val is not None:
            cat_value_counts[cat][val] += 1

    value_diversity: dict[str, Any] = {}
    for cat, counts in cat_value_counts.items():
        entropy = shannon_entropy(counts)
        value_diversity[cat] = {
            "entropy_bits": round(entropy, 4),
            "unique_values": len(counts),
            "value_counts": dict(counts),
        }
    return value_diversity


def _token_consumption_per_persona(
    entries: list[dict[str, Any]],
    persona_ids: set[str],
) -> dict[str, Any]:
    """Prompt/completion/total token sums per persona."""
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
    return {
        pid: {
            "prompt_tokens": persona_prompt.get(pid, 0),
            "completion_tokens": persona_completion.get(pid, 0),
            "total_tokens": persona_prompt.get(pid, 0) + persona_completion.get(pid, 0),
        }
        for pid in persona_ids
    }


def _token_consumption_per_category(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Prompt/completion/total token sums per category."""
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
    return {
        cat: {
            "prompt_tokens": cat_prompt.get(cat, 0),
            "completion_tokens": cat_completion.get(cat, 0),
            "total_tokens": cat_prompt.get(cat, 0) + cat_completion.get(cat, 0),
        }
        for cat in all_token_cats
    }


def _tokens_per_second(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-entry completion-tokens-per-second (None when timing unavailable)."""
    tokens_per_second: list[dict[str, Any]] = []
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
    return tokens_per_second


def _latency_by_category(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Median, p95 (nearest-rank), and max elapsed_ms per category."""
    cat_latencies: dict[str, list[float]] = defaultdict(list)
    for e in entries:
        elapsed = e.get("elapsed_ms")
        if elapsed is not None:
            cat = e.get("category") or "__unknown__"
            cat_latencies[cat].append(elapsed)

    latency_by_category: dict[str, Any] = {}
    for cat, lats in cat_latencies.items():
        latency_by_category[cat] = {
            "median_ms": median(lats),
            "p95_ms": percentile(lats, 95),
            "max_ms": max(lats) if lats else None,
            "count": len(lats),
        }
    return latency_by_category


def _token_budget_by_step_type(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Call counts and token sums grouped by coarse step type."""
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
    return {
        stype: {
            "call_count": step_type_count.get(stype, 0),
            "prompt_tokens": step_type_prompt.get(stype, 0),
            "completion_tokens": step_type_completion.get(stype, 0),
            "total_tokens": (
                step_type_prompt.get(stype, 0) + step_type_completion.get(stype, 0)
            ),
        }
        for stype in all_step_types
    }


def _token_metrics(
    entries: list[dict[str, Any]],
    persona_ids: set[str],
    has_token_data: bool,
) -> dict[str, Any]:
    """Bundle the five token-gated families.

    Returns all five sub-dicts together so the assembler can spread them into the
    final metrics dict in order.  When ``has_token_data`` is false every value is
    ``None`` (matching the token-less run contract); otherwise each family is
    computed from its own helper.
    """
    if not has_token_data:
        return {
            "token_consumption_per_persona": None,
            "token_consumption_per_category": None,
            "tokens_per_second": None,
            "latency_by_category": None,
            "token_budget_by_step_type": None,
        }
    return {
        "token_consumption_per_persona": _token_consumption_per_persona(entries, persona_ids),
        "token_consumption_per_category": _token_consumption_per_category(entries),
        "tokens_per_second": _tokens_per_second(entries),
        "latency_by_category": _latency_by_category(entries),
        "token_budget_by_step_type": _token_budget_by_step_type(entries),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_metrics(
    entries: list[dict[str, Any]],
    run_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute all v1 analytics metrics for a single run.

    Thin assembler over the per-family ``_compute_*`` helpers above.  The five
    token-gated families (token consumption per persona/category, tokens/second,
    latency, step-type budgets) are only computed when at least one entry carries
    token data; otherwise they are emitted as ``None``.

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

    has_token_data = any(
        e.get("prompt_tokens") is not None or e.get("completion_tokens") is not None
        for e in entries
    )
    persona_ids: set[str] = {_persona_id(e, i) for i, e in enumerate(entries)}

    return {
        "summary": _summary(entries, persona_ids, has_token_data, run_summary),
        "per_category": _per_category(entries),
        "method_distribution": _method_distribution(entries),
        "prompt_size_growth": _prompt_size_growth(entries),
        "response_verbosity": _response_verbosity(entries),
        "wall_clock_per_persona": _wall_clock_per_persona(entries),
        "value_diversity": _value_diversity(entries),
        **_token_metrics(entries, persona_ids, has_token_data),
    }

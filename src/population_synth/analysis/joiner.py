"""Join JSONL interaction entries with log-file call records.

The join is two-phase:

1. **Exact correlation-ID match.**  When both an entry and a log record carry a
   ``(persona_id, call_index)`` key (emitted by parallel runs as a ``corr=``
   suffix), they are matched on that key, 1-to-1.  This is exact even when many
   personas' calls interleave within the log.

2. **Timestamp-proximity fallback.**  Any entry left unmatched after phase 1 is
   matched to the nearest unmatched log record whose timestamp falls within a
   tolerance window (default 2 seconds) -- the legacy behaviour, used for runs
   that predate the correlation key (no ``corr`` present).

Each JSONL entry has an ISO 8601 ``timestamp``; each log entry a
``"YYYY-MM-DD HH:MM:SS"`` timestamp.  Returns enriched dicts: all JSONL fields
plus ``prompt_tokens``, ``completion_tokens``, and ``elapsed_ms`` from the
matched log entry (``None`` when no log entry could be matched).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

# Pattern to parse the log file timestamp format "YYYY-MM-DD HH:MM:SS"
_LOG_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _to_datetime(ts: str | None) -> datetime | None:
    """Parse a timestamp string to a timezone-aware UTC datetime.

    Accepts both ISO 8601 (``"2026-05-21T16:13:27.335972"``) and
    log-file format (``"2026-05-21 16:13:27"``).  Returns ``None`` if the
    value is absent or unparsable.
    """
    if not ts:
        return None
    ts = ts.strip()
    # Log file format: "YYYY-MM-DD HH:MM:SS"
    if _LOG_TS_PATTERN.match(ts):
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None
    # ISO 8601 variants (with or without fractional seconds, with or without Z/offset)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _corr_key(d: dict[str, Any]) -> tuple[str, int] | None:
    """Return the ``(persona_id, call_index)`` key, or ``None`` when incomplete."""
    pid = d.get("persona_id")
    cidx = d.get("call_index")
    if pid is not None and cidx is not None:
        return pid, cidx
    return None


def join_entries(
    jsonl_entries: list[dict[str, Any]],
    log_entries: list[dict[str, Any]],
    tolerance_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Match log records to JSONL entries (exact corr key, then timestamp).

    Phase 1 matches on ``(persona_id, call_index)`` when both sides carry it.
    Phase 2 matches any remaining entry to the nearest unmatched log record
    within *tolerance_s* seconds (legacy behaviour).  Sequential ordering is the
    tiebreaker for phase 2.

    Parameters
    ----------
    jsonl_entries:
        Normalised dicts from :func:`interaction_parser.parse_interactions`.
    log_entries:
        Dicts from :func:`log_parser.parse_log_file`.
    tolerance_s:
        Maximum allowed absolute time difference (seconds) for a *fallback*
        match to be accepted.  Default is 2.0 seconds.

    Returns
    -------
    list[dict]
        One enriched dict per JSONL entry.  Each dict contains all original
        JSONL fields plus ``prompt_tokens``, ``completion_tokens``, and
        ``elapsed_ms`` from the matched log entry (``None`` if unmatched).
    """
    # Track which log entries have already been matched (one-to-one)
    log_matched: list[bool] = [False] * len(log_entries)
    # Build result list, keeping a reference to the matched log index per entry
    matched_log_index: list[int | None] = [None] * len(jsonl_entries)

    # --- Phase 1: exact correlation-ID match --------------------------------
    log_by_corr: dict[tuple[str, int], list[int]] = defaultdict(list)
    for k, lr in enumerate(log_entries):
        ck = _corr_key(lr)
        if ck is not None:
            log_by_corr[ck].append(k)

    for i, entry in enumerate(jsonl_entries):
        ck = _corr_key(entry)
        if ck is not None and log_by_corr.get(ck):
            k = log_by_corr[ck].pop(0)
            log_matched[k] = True
            matched_log_index[i] = k

    # --- Phase 2: timestamp-proximity fallback ------------------------------
    jsonl_times: list[datetime | None] = [
        _to_datetime(e.get("timestamp")) for e in jsonl_entries
    ]
    log_times: list[datetime | None] = [
        _to_datetime(e.get("timestamp")) for e in log_entries
    ]

    for i, jdt in enumerate(jsonl_times):
        if matched_log_index[i] is not None or jdt is None:
            continue
        best_idx: int | None = None
        best_diff: float = float("inf")
        for k, ldt in enumerate(log_times):
            if log_matched[k] or ldt is None:
                continue
            diff = abs((jdt - ldt).total_seconds())
            if diff <= tolerance_s and diff < best_diff:
                best_diff = diff
                best_idx = k
        if best_idx is not None:
            log_matched[best_idx] = True
            matched_log_index[i] = best_idx

    # Build enriched output dicts
    result: list[dict[str, Any]] = []
    for i, entry in enumerate(jsonl_entries):
        enriched = dict(entry)
        log_idx = matched_log_index[i]
        if log_idx is not None:
            log_rec = log_entries[log_idx]
            enriched["prompt_tokens"] = log_rec.get("prompt_tokens")
            enriched["completion_tokens"] = log_rec.get("completion_tokens")
            enriched["elapsed_ms"] = log_rec.get("elapsed_ms")
        else:
            enriched.setdefault("prompt_tokens", None)
            enriched.setdefault("completion_tokens", None)
            enriched.setdefault("elapsed_ms", None)
        result.append(enriched)

    return result

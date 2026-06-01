"""Join JSONL interaction entries with log-file call records by timestamp proximity.

Each JSONL entry has an ISO 8601 ``timestamp`` field.
Each log entry has a ``timestamp`` field in ``"YYYY-MM-DD HH:MM:SS"`` format.

The join works by matching every log entry to the nearest unmatched JSONL entry
whose timestamp falls within a configurable tolerance window (default 2 seconds).
When two log entries are equidistant from the same JSONL entry the earlier log
entry wins (first-come, first-served in sequential order).

Returns enriched dicts: all JSONL fields plus ``prompt_tokens``,
``completion_tokens``, and ``elapsed_ms`` from the matched log entry.
Fields are ``None`` when no log entry could be matched.
"""

from __future__ import annotations

import re
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


def join_entries(
    jsonl_entries: list[dict[str, Any]],
    log_entries: list[dict[str, Any]],
    tolerance_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Match log entries to JSONL entries by timestamp proximity.

    Each log entry is matched to the nearest unmatched JSONL entry whose
    timestamp falls within *tolerance_s* seconds.  Sequential ordering is used
    as a tiebreaker: when two JSONL entries are equally close to a log entry the
    one that appears earlier in *jsonl_entries* is preferred.

    Parameters
    ----------
    jsonl_entries:
        Normalised dicts from :func:`interaction_parser.parse_interactions`.
    log_entries:
        Dicts from :func:`log_parser.parse_log_file`.
    tolerance_s:
        Maximum allowed absolute time difference (seconds) for a match to be
        accepted.  Default is 2.0 seconds.

    Returns
    -------
    list[dict]
        One enriched dict per JSONL entry.  Each dict contains all original
        JSONL fields plus ``prompt_tokens``, ``completion_tokens``, and
        ``elapsed_ms`` from the matched log entry (``None`` if unmatched).
    """
    # Pre-parse all timestamps once
    jsonl_times: list[datetime | None] = [
        _to_datetime(e.get("timestamp")) for e in jsonl_entries
    ]
    log_times: list[datetime | None] = [
        _to_datetime(e.get("timestamp")) for e in log_entries
    ]

    # Track which log entries have already been matched (one-to-one)
    log_matched: list[bool] = [False] * len(log_entries)

    # Build result list, keeping a reference to the matched log index per entry
    matched_log_index: list[int | None] = [None] * len(jsonl_entries)

    for i, jdt in enumerate(jsonl_times):
        if jdt is None:
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

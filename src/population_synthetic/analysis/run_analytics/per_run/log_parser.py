"""Parse structured call lines from identity generation run log files.

Log files are produced by the Python `logging` module and live at
``logs/run_YYYYMMDD_HHMMSS.log``.  Each line follows the format::

    2026-05-21 15:45:27 INFO: <message>

or, when the generation script's ``_ElapsedFormatter`` is installed, with an
injected elapsed-time suffix between the timestamp and the level::

    2026-07-06 15:45:27 [+1.2s] INFO: <message>

Five call-line patterns are recognised:

1. **Ollama** ::

       ollama call: model=<m> base_url=<u> elapsed_ms=<n> prompt_tokens=<n> completion_tokens=<n>

2. **OpenAI-compat** (same shape as Ollama) ::

       openai_compat call: model=<m> base_url=<u> elapsed_ms=<n> prompt_tokens=<n> completion_tokens=<n>

3. **Claude** (separate launch and inference timings; tokens optional -- present
   on runs where the CLI ``result`` message carried a ``usage`` block) ::

       claude call: model=<m> t_launch_ms=<n> t_inference_ms=<n>
       claude call: model=<m> t_launch_ms=<n> t_inference_ms=<n> prompt_tokens=<n> completion_tokens=<n>

4. **Gemini** (no ``base_url``, unlike Ollama/OpenAI-compat) ::

       gemini call: model=<m> elapsed_ms=<n> prompt_tokens=<n> completion_tokens=<n>

5. **Parallel run summary** ::

       Done in <n>s. Success: <n>, Failed: <n>

All returned dicts share the normalised schema::

    {
        "timestamp":          str | None,   # ISO-like "YYYY-MM-DD HH:MM:SS"
        "provider":           str,          # "ollama" | "openai_compat" | "claude" | "gemini"
        "model":              str,
        "elapsed_ms":         float | None,
        "prompt_tokens":      int | None,
        "completion_tokens":  int | None,
        "persona_id":         str | None,   # from optional "corr=" suffix
        "call_index":         int | None,   # from optional "corr=" suffix
    }

Lines may carry an optional trailing ``corr=<persona_id>:<call_index>`` token
(emitted by parallel runs) which the joiner uses for exact attribution; legacy
lines without it parse with ``persona_id`` / ``call_index`` set to ``None``.

For Claude calls, ``elapsed_ms`` is the sum of ``t_launch_ms`` and
``t_inference_ms``.  Token counts are ``None`` for Claude lines predating the
``usage`` block (older logs); newer lines carry real counts.

Token values logged as the string ``"None"`` (Python's str() of None) are
converted to Python ``None``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Log line timestamp prefix:  "2026-05-21 15:45:27 INFO: <message>"
# Also tolerates the "_ElapsedFormatter" suffix injected between the timestamp
# and the level, e.g. "2026-07-06 15:45:27 [+1.2s] INFO: <message>".
_RE_TIMESTAMP = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?:\[\+[^\]]+\]\s+)?\w+:\s+(?P<msg>.+)$"
)

# Optional trailing correlation key:  " corr=<persona_id>:<call_index>"
_CORR_SUFFIX = r"(?:\s+corr=(?P<corr>\S+))?"

# Ollama / OpenAI-compat call line
_RE_OLLAMA_OPENAI = re.compile(
    r"^(?P<provider>ollama|openai_compat) call:\s+"
    r"model=(?P<model>\S+)\s+"
    r"base_url=(?P<base_url>\S+)\s+"
    r"elapsed_ms=(?P<elapsed_ms>[\d.]+)\s+"
    r"prompt_tokens=(?P<prompt_tokens>\S+)\s+"
    r"completion_tokens=(?P<completion_tokens>\S+)"
    + _CORR_SUFFIX
)

# Claude call line.  ``prompt_tokens``/``completion_tokens`` are optional --
# present only on newer logs where the CLI ``result`` message carried a
# ``usage`` block; legacy lines lack them entirely.
_RE_CLAUDE = re.compile(
    r"^claude call:\s+"
    r"model=(?P<model>\S+)\s+"
    r"t_launch_ms=(?P<t_launch_ms>[\d.]+)\s+"
    r"t_inference_ms=(?P<t_inference_ms>[\d.]+)"
    r"(?:\s+prompt_tokens=(?P<prompt_tokens>\S+)\s+completion_tokens=(?P<completion_tokens>\S+))?"
    + _CORR_SUFFIX
)

# Gemini call line.  Unlike Ollama/OpenAI-compat, Gemini has no ``base_url`` field.
_RE_GEMINI = re.compile(
    r"^gemini call:\s+"
    r"model=(?P<model>\S+)\s+"
    r"elapsed_ms=(?P<elapsed_ms>[\d.]+)\s+"
    r"prompt_tokens=(?P<prompt_tokens>\S+)\s+"
    r"completion_tokens=(?P<completion_tokens>\S+)"
    + _CORR_SUFFIX
)

# Parallel run summary line
_RE_DONE = re.compile(
    r"^Done in\s+(?P<elapsed_s>[\d.]+)s\.\s+"
    r"Success:\s+(?P<success>\d+),\s+"
    r"Failed:\s+(?P<failed>\d+)"
)


# ---------------------------------------------------------------------------
# Token value helpers
# ---------------------------------------------------------------------------

def _parse_token_count(raw: str) -> int | None:
    """Convert a token-count string to int, returning None for "None" / empty."""
    raw = raw.strip()
    if not raw or raw.lower() == "none":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_corr(raw: str | None) -> tuple[str | None, int | None]:
    """Split a ``<persona_id>:<call_index>`` correlation token.

    Returns ``(persona_id, call_index)``; either element is ``None`` when the
    token is absent or malformed.  ``persona_id`` may itself contain no colon
    (e.g. ``persona_00001``), so we split on the final ``:``.
    """
    if not raw:
        return None, None
    persona_id, sep, idx = raw.rpartition(":")
    if not sep:
        return None, None
    try:
        return persona_id, int(idx)
    except ValueError:
        return persona_id or None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_log_file(path: Path | str) -> list[dict[str, Any]]:
    """Parse a single run log file and return a list of call-record dicts.

    Each dict represents one LLM call and contains the normalised fields
    documented in the module docstring.  Summary lines (``Done in ...``) are
    not included in the returned list; retrieve them with
    :func:`parse_run_summary` instead.

    Parameters
    ----------
    path:
        Path to a ``logs/run_*.log`` file.

    Returns
    -------
    list[dict]
        One dict per recognised call line.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    records: list[dict[str, Any]] = []

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            ts, msg = _split_log_line(line)
            if msg is None:
                continue

            record = _try_parse_call(msg, ts)
            if record is not None:
                records.append(record)

    return records


def parse_run_summary(path: Path | str) -> dict[str, Any] | None:
    """Extract the parallel-run summary line from a log file, if present.

    Returns a dict ``{elapsed_s, success, failed}`` or ``None`` if no summary
    line is found.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            _, msg = _split_log_line(line)
            if msg is None:
                continue
            m = _RE_DONE.match(msg)
            if m:
                return {
                    "elapsed_s": float(m.group("elapsed_s")),
                    "success": int(m.group("success")),
                    "failed": int(m.group("failed")),
                }
    return None


def find_log_files(directory: Path | str) -> list[Path]:
    """Return all ``run_*.log`` files inside *directory/logs/*, sorted by name.

    If ``directory/logs/`` does not exist, returns an empty list.
    """
    directory = Path(directory)
    logs_dir = directory / "logs"
    if not logs_dir.is_dir():
        return []
    return sorted(logs_dir.glob("run_*.log"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_log_line(line: str) -> tuple[str | None, str | None]:
    """Split a log line into (timestamp, message).

    Returns (None, None) if the line does not match the expected format.
    """
    m = _RE_TIMESTAMP.match(line)
    if not m:
        return None, None
    return m.group("ts"), m.group("msg")


def _try_parse_call(msg: str, timestamp: str | None) -> dict[str, Any] | None:
    """Attempt to parse *msg* as a call line; return a record dict or None."""
    # Ollama / OpenAI-compat
    m = _RE_OLLAMA_OPENAI.match(msg)
    if m:
        persona_id, call_index = _parse_corr(m.group("corr"))
        return {
            "timestamp": timestamp,
            "provider": m.group("provider"),
            "model": m.group("model"),
            "elapsed_ms": float(m.group("elapsed_ms")),
            "prompt_tokens": _parse_token_count(m.group("prompt_tokens")),
            "completion_tokens": _parse_token_count(m.group("completion_tokens")),
            "persona_id": persona_id,
            "call_index": call_index,
        }

    # Claude
    m = _RE_CLAUDE.match(msg)
    if m:
        t_launch = float(m.group("t_launch_ms"))
        t_inference = float(m.group("t_inference_ms"))
        persona_id, call_index = _parse_corr(m.group("corr"))
        raw_prompt_tokens = m.group("prompt_tokens")
        raw_completion_tokens = m.group("completion_tokens")
        return {
            "timestamp": timestamp,
            "provider": "claude",
            "model": m.group("model"),
            "elapsed_ms": t_launch + t_inference,
            "prompt_tokens": (
                _parse_token_count(raw_prompt_tokens) if raw_prompt_tokens is not None else None
            ),
            "completion_tokens": (
                _parse_token_count(raw_completion_tokens)
                if raw_completion_tokens is not None
                else None
            ),
            "persona_id": persona_id,
            "call_index": call_index,
        }

    # Gemini
    m = _RE_GEMINI.match(msg)
    if m:
        persona_id, call_index = _parse_corr(m.group("corr"))
        return {
            "timestamp": timestamp,
            "provider": "gemini",
            "model": m.group("model"),
            "elapsed_ms": float(m.group("elapsed_ms")),
            "prompt_tokens": _parse_token_count(m.group("prompt_tokens")),
            "completion_tokens": _parse_token_count(m.group("completion_tokens")),
            "persona_id": persona_id,
            "call_index": call_index,
        }

    return None

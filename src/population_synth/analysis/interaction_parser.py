"""Parse LLM interaction log files produced by LLMInteractionCollector.

Supports two on-disk formats transparently:
- `llm_interactions.jsonl`  — line-delimited JSON (one object per line)
- `llm_interactions.json`   — a JSON array of objects

Both formats contain the fields defined by LLMInteractionEntry:
    category, method, step, prompt, raw_response,
    parsed_value, error, attempt, timestamp

Fields that are absent or null in a record are normalised to their default
values so callers can always rely on the same keys being present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Fields and their default values as specified by LLMInteractionEntry
_FIELD_DEFAULTS: dict[str, Any] = {
    "category": None,
    "method": None,
    "step": None,
    "prompt": None,
    "raw_response": None,
    "parsed_value": None,
    "error": None,
    "attempt": 1,
    "timestamp": None,
}


def _normalise(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *record* with all expected fields present."""
    out = dict(_FIELD_DEFAULTS)
    out.update(record)
    return out


def _iter_jsonl(path: Path):
    """Yield parsed dicts from a line-delimited JSON file, skipping blank lines."""
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {lineno} of {path}: {exc}"
                ) from exc


def _iter_json_array(path: Path):
    """Yield parsed dicts from a JSON array file."""
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array in {path}, got {type(data).__name__}"
        )
    yield from data


def parse_interactions(path: Path | str) -> list[dict[str, Any]]:
    """Parse an interaction log file and return a list of normalised entry dicts.

    The file may be in JSONL format (one JSON object per line) or JSON array
    format.  The format is detected automatically: if the first non-whitespace
    character of the file is ``[`` it is treated as a JSON array; otherwise it
    is treated as JSONL.

    Parameters
    ----------
    path:
        Path to `llm_interactions.jsonl` or `llm_interactions.json`.

    Returns
    -------
    list[dict]
        One dict per interaction entry.  All `LLMInteractionEntry` fields are
        guaranteed to be present; missing fields are filled with their default
        values (``None`` for string/object fields, ``1`` for ``attempt``).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file cannot be parsed as valid JSON / JSONL.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Interaction log not found: {path}")

    # Peek at the first non-whitespace byte to detect format
    with open(path, encoding="utf-8") as fh:
        first_char = ""
        for chunk in iter(lambda: fh.read(64), ""):
            stripped = chunk.lstrip()
            if stripped:
                first_char = stripped[0]
                break

    if first_char == "[":
        records = list(_iter_json_array(path))
    else:
        records = list(_iter_jsonl(path))

    return [_normalise(r) for r in records]


def find_interaction_file(directory: Path | str) -> Path | None:
    """Return the interaction log file inside *directory*, or None if absent.

    Checks for ``llm_interactions.jsonl`` first, then ``llm_interactions.json``.
    """
    directory = Path(directory)
    for name in ("llm_interactions.jsonl", "llm_interactions.json"):
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None

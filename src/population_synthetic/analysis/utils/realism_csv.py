"""realism_csv.py -- the per-persona tidy CSV shared by ``persona_realism`` -> ``realism_ranking``.

The **inter-task contract**. ``persona_realism`` judges one combination and writes
``{combo}_personas.csv`` (one row per judged persona); ``realism_ranking`` reads
those files back and runs every cross-combination statistic on them. Neither task
imports the other -- they agree only on this schema, defined once here, with the
writer used by the producer and the reader by the consumer (the same shape as
:mod:`population_synthetic.analysis.utils.validity_csv`).

The file-backed seam is what lets the expensive LLM judging be cached once while the
statistical battery downstream keeps evolving: re-running the aggregator re-reads
these rows, it never re-judges.

Three properties the schema is built to keep:

* **Absent is not zero.** A persona whose every successful round was judged
  *impossible* has no typicality at all; its ``typicality_mean`` is written empty and
  reads back as ``None``, never ``0.0`` (which would be the lowest possible rating --
  a real, very different claim).
* **Counts stay counts.** Round and vote counts round-trip as ``int``; a value that
  will not parse as one raises rather than becoming a float or a string.
* **The rows carry their own denominators.** ``n_rounds_attempted`` and
  ``n_rounds_successful`` travel on every row, so a per-persona rate downstream is
  never computed over an unreported base.

One row == one persona that has **at least one successful round**. A persona whose
every round failed is not judged-with-a-verdict at all: it is absent from the verdict
cache by construction and is counted in the combination report's ``n_failed``. That is
what makes the row count exactly equal the report's ``n_personas`` -- the completeness
check the aggregator gates on.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "FIELDNAMES",
    "RealismPersonaRow",
    "SCHEMA_VERSION",
    "read_realism_personas_csv",
    "write_realism_personas_csv",
]

#: Bumped whenever a column is added, removed, or re-typed. Recorded by the producer
#: in its combination report so a reader can name the mismatch instead of guessing.
SCHEMA_VERSION = 1

#: Separator for the per-round typicality series inside a single cell. Chosen because
#: it never occurs in an integer rating and needs no CSV quoting.
_ROUND_SEP = "|"

_TRUE = "true"
_FALSE = "false"


@dataclass(frozen=True)
class RealismPersonaRow:
    """One judged persona's tidy record.

    ``slug`` is the combination label -- a synthetic ``{country}_{strategy}_{model}``
    or the real competitor ``real_{country}``. ``model``/``strategy`` are empty for
    the real competitor (it is not a model x method cell), which is exactly what
    ``is_real_reference`` marks so downstream factor tests can hold it out without
    string-sniffing the slug.

    ``typicality_rounds`` is the raw per-round ordinal series (empty entry for a round
    judged impossible, which carries no typicality), retained so the aggregator can
    run rank-based tests on rounds rather than only on the per-persona mean.

    ``max_severity`` is the worst clash severity the judge raised for this persona
    across all rounds (``S3`` > ``S2`` > ``S1``), empty when it raised none;
    ``clash_count`` is the number of *distinct* ``(attribute-pair, severity)`` clashes,
    not the number of rounds in which they appeared.
    """

    persona_id: str
    slug: str
    country: str
    model: str
    strategy: str
    is_real_reference: bool
    n_rounds_attempted: int
    n_rounds_successful: int
    can_exist_true_votes: int
    can_exist_majority: bool
    typicality_mean: float | None
    typicality_sd: float | None
    typicality_rounds: tuple[int | None, ...]
    max_severity: str
    clash_count: int


#: Column order == :class:`RealismPersonaRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(RealismPersonaRow))

_BOOL_FIELDS = ("is_real_reference", "can_exist_majority")
_INT_FIELDS = ("n_rounds_attempted", "n_rounds_successful", "can_exist_true_votes", "clash_count")
_OPTIONAL_FLOAT_FIELDS = ("typicality_mean", "typicality_sd")


def _encode(field_name: str, value: Any) -> str:
    """Serialise one cell, keeping ``None`` (absent) distinct from ``0`` (a value)."""
    if field_name == "typicality_rounds":
        return _ROUND_SEP.join("" if t is None else str(int(t)) for t in value)
    if field_name in _BOOL_FIELDS:
        return _TRUE if value else _FALSE
    if value is None:
        return ""
    return str(value)


def write_realism_personas_csv(rows: Sequence[RealismPersonaRow], path: Path) -> Path:
    """Write *rows* to *path* with the :data:`FIELDNAMES` columns; return *path*.

    The file is written **whole** (truncating mode), never appended, so writing it N
    times is indistinguishable from writing it once -- the idempotency the aggregator's
    row-count check depends on. Rows are emitted in the given order; the producer sorts
    by ``persona_id`` so two runs over the same cache produce byte-identical files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELDNAMES)
        for row in rows:
            record = asdict(row)
            writer.writerow([_encode(name, record[name]) for name in FIELDNAMES])
    return path


def _parse_int(raw: str, *, column: str, path: Path, persona: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path}: persona {persona!r} column {column!r} is {raw!r}, which is not an "
            "integer count. The file is malformed; re-run the persona_realism judge for "
            "this combination to rewrite it."
        ) from exc


def _parse_bool(raw: str, *, column: str, path: Path, persona: str) -> bool:
    token = str(raw).strip().lower()
    if token == _TRUE:
        return True
    if token == _FALSE:
        return False
    raise ValueError(
        f"{path}: persona {persona!r} column {column!r} is {raw!r}, which is neither "
        f"{_TRUE!r} nor {_FALSE!r}."
    )


def _parse_optional_float(raw: str, *, column: str, path: Path, persona: str) -> float | None:
    """Empty -> ``None`` (the metric is undefined), never ``0.0``."""
    if raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path}: persona {persona!r} column {column!r} is {raw!r}, which is neither "
            "empty (undefined) nor a number."
        ) from exc


def _parse_rounds(raw: str, *, path: Path, persona: str) -> tuple[int | None, ...]:
    if raw == "":
        return ()
    parsed: list[int | None] = []
    for item in raw.split(_ROUND_SEP):
        if item == "":
            parsed.append(None)  # a round judged impossible carries no typicality
            continue
        try:
            parsed.append(int(item))
        except ValueError as exc:
            raise ValueError(
                f"{path}: persona {persona!r} column 'typicality_rounds' holds {item!r}, "
                "which is neither empty nor an integer rating."
            ) from exc
    return tuple(parsed)


def read_realism_personas_csv(path: Path, *, expected_rows: int | None = None) -> list[RealismPersonaRow]:
    """Read *path* back into typed rows, validating the schema (fail-fast).

    Raises ``FileNotFoundError`` when the file is absent (the producing task has not
    run for this combination) and ``ValueError`` when the header is missing a column,
    a cell will not parse as its declared type, or -- when *expected_rows* is given --
    the row count disagrees with it.

    *expected_rows* is the combination report's ``n_personas``. A disagreement means
    the CSV and the report were written from different states of the verdict cache, so
    every rate the aggregator computes would be over the wrong base; that is a hard
    error, never a warning.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Per-persona realism CSV not found: {path}. Run "
            "scripts/analyze/analyze_persona_realism.py for this combination first."
        )

    rows: list[RealismPersonaRow] = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = [name for name in FIELDNAMES if name not in header]
        if missing:
            raise ValueError(
                f"{path}: per-persona realism CSV is missing required column(s) {missing}; "
                f"header is {list(header)}. Expected schema v{SCHEMA_VERSION}: {list(FIELDNAMES)}."
            )
        for record in reader:
            persona = record.get("persona_id") or "<unnamed>"
            values: dict[str, Any] = {
                "persona_id": persona,
                "slug": record["slug"],
                "country": record["country"],
                "model": record["model"],
                "strategy": record["strategy"],
                "max_severity": record["max_severity"],
                "typicality_rounds": _parse_rounds(record["typicality_rounds"], path=path, persona=persona),
            }
            for column in _BOOL_FIELDS:
                values[column] = _parse_bool(record[column], column=column, path=path, persona=persona)
            for column in _INT_FIELDS:
                values[column] = _parse_int(record[column], column=column, path=path, persona=persona)
            for column in _OPTIONAL_FLOAT_FIELDS:
                values[column] = _parse_optional_float(
                    record[column], column=column, path=path, persona=persona
                )
            rows.append(RealismPersonaRow(**values))

    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(
            f"{path}: holds {len(rows)} persona row(s) but the combination report declares "
            f"n_personas={expected_rows}. The CSV and the report were written from different "
            "states of the verdict cache -- re-run scripts/analyze/analyze_persona_realism.py "
            "for this combination (with --rewrite-artifacts) to regenerate both."
        )
    return rows

"""attrition_csv.py -- the tidy per-combination validation-attrition contract.

One row per combination that entered the validation gate, carrying the five funnel
counts (generated -> raw-valid -> mapped-valid -> clean -> selected) and the two rates
derived from them. ``validation_attrition`` writes it; ``cost_efficiency`` reads it
back as a declared input, because the generation multiplier recorded here is exactly
the factor that corrects a cost figure measured on the capped mirror -- so the
correction and its source travel through one dependency edge instead of being
recomputed in two places that can drift.

The row grain is **every** combination the gate recorded, including the ones it
withdrew. An excluded combination has no capped mirror, no capped mapped file and no
``generation_metadata`` row, so this file is the only artifact in the analysis layer
that reports it at all. Dropping those rows would leave the sweep looking as though it
had consisted solely of the combinations that survived.

Three properties the schema is built to keep:

* **Absent is not zero.** A rate whose denominator is zero is *undefined*, not ``0.0``
  and not infinite. It is written as an empty cell and reads back as ``None`` (guide
  03 sect. 6 -- keep "zero" distinct from "absent"). A ``retention_rate`` of ``0.0`` is
  a real and very different claim: it says a combination generated personas and none
  survived.
* **Counts stay counts.** Every funnel stage round-trips as ``int``; only the two
  derived rates are floats.
* **Rates carry their denominators.** ``retention_rate`` and ``generation_multiplier``
  both ship beside ``generated`` and ``clean``, the two counts they are quotients of,
  so neither is ever read over an unreported base (guide 03 sect. 4).

Boundary: this module knows nothing about figures, about which country is being
analysed, about how the counts were obtained, or about which process wrote the file.
It is the schema and nothing else.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Sequence

from population_synthetic.analysis.utils.tidy_csv import (
    encode_bool,
    missing_columns,
    parse_bool,
    parse_int,
    parse_optional_float,
    stale_schema_error,
    write_rows,
)

__all__ = [
    "FIELDNAMES",
    "MALFORMED_REMEDY",
    "SCHEMA_VERSION",
    "STALE_SCHEMA_REMEDY",
    "AttritionRow",
    "read_attrition_csv",
    "write_attrition_csv",
]

#: Bumped whenever a column is added, removed, or re-typed.
#:
#: v1 is the first published shape: the four axis-identity columns, ``requested_n``,
#: the five funnel counts, the two derived rates, and the three verdict columns.
#:
#: Every column is **required**, never optional, and the reader raises on a file that
#: lacks one rather than filling it in. The reason is the same for all three groups and
#: is worth stating once: a tolerated absence is indistinguishable from a real value.
#: A missing count column would default to zero, which reads as "this combination
#: generated nothing" -- a stronger claim than any measurement here makes. A missing
#: rate column would default to absent, which says the denominator was zero rather than
#: that the file predates the derivation. A missing ``excluded`` would default to false,
#: silently converting a withdrawn combination back into a surviving one -- precisely
#: the fact this artifact exists to publish.
SCHEMA_VERSION = 1

#: Appended to a malformed-cell error. The file is derived wholly from the gate's own
#: records, so the fix is always to rewrite it rather than to hand-edit a cell.
MALFORMED_REMEDY = (
    "The file is malformed; re-run scripts/analyze/analyze_validation_attrition.py "
    "--force for this country to rewrite it from the gate's records."
)

#: Appended to the stale-schema error: the command that rewrites the file. It is cheap
#: -- the gate's ``population_cap/_index.json`` and the two validator roll-ups already
#: hold everything any new column needs, so nothing has to be re-validated or re-capped.
STALE_SCHEMA_REMEDY = (
    "scripts/analyze/analyze_validation_attrition.py --force (no gate re-run needed; "
    "the population_cap index and the two validator summaries already hold every count)."
)


@dataclass(frozen=True)
class AttritionRow:
    """One combination's attrition record.

    ``slug`` is the combination label ``{country}_{strategy}_{model}``, with
    ``country``/``model``/``strategy`` carried alongside it so a consumer never has to
    re-parse the slug (neither strategy nor model ids are ``_``-free, so a naive split
    is wrong).

    The five counts are the funnel, widest first:

    ``generated``
        The generated pool as the cap observed it on disk -- ``CapSummary.raw_total``.
    ``raw_valid``
        Personas passing the raw-completeness gate.
    ``mapped_valid``
        Personas passing the mapped-value gate.
    ``clean``
        Personas passing **both** gates: the pool the cap actually draws from.
    ``selected``
        Personas the cap drew. **Zero for every excluded combination**, by design --
        which is why no rate here is denominated on it.

    ``retention_rate`` is ``clean / generated``; ``generation_multiplier`` is
    ``generated / clean`` -- personas generated per *usable* persona. The multiplier is
    deliberately not ``generated / selected``: that denominator is zero for every
    withdrawn combination, i.e. undefined exactly where the number matters most. Both
    are ``None`` when their own denominator is zero, never ``0.0`` and never infinite.

    ``excluded`` is the gate's verdict: the combination held fewer than ``requested_n``
    clean personas and was withdrawn, so it has no capped mirror and no capped mapped
    file. ``exclusion_reason`` carries the gate's own sentence, empty when it did not
    exclude; ``excluded`` is the authoritative flag, not the emptiness of the reason.

    ``had_surplus`` is ``CapSummary.truncated`` under a name that cannot be misread: it
    means ``clean > requested_n``, i.e. a surplus was cut down. It is **not** a
    shortfall marker, and reading it as one inverts the meaning of every row.
    """

    slug: str
    country: str
    model: str
    strategy: str
    requested_n: int
    generated: int
    raw_valid: int
    mapped_valid: int
    clean: int
    selected: int
    retention_rate: float | None
    generation_multiplier: float | None
    excluded: bool
    exclusion_reason: str
    had_surplus: bool


#: Column order == :class:`AttritionRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(AttritionRow))

_BOOL_FIELDS = ("excluded", "had_surplus")
_INT_FIELDS = ("requested_n", "generated", "raw_valid", "mapped_valid", "clean", "selected")
_OPTIONAL_FLOAT_FIELDS = ("retention_rate", "generation_multiplier")
_TEXT_FIELDS = ("slug", "country", "model", "strategy", "exclusion_reason")


def _encode(field_name: str, value: Any) -> str:
    """Serialise one cell, keeping ``None`` (undefined) distinct from ``0`` (a value)."""
    if field_name in _BOOL_FIELDS:
        return encode_bool(value)
    if value is None:
        return ""
    return str(value)


def write_attrition_csv(rows: Sequence[AttritionRow], path: Path) -> Path:
    """Write *rows* to *path* with the :data:`FIELDNAMES` columns; return *path*.

    The file is written **whole** (truncating), never appended, so writing it N times
    is indistinguishable from writing it once (guide 02 sect. 5) -- the idempotency the
    downstream row-count and join checks depend on. Rows are emitted in the order
    given; the producer sorts by ``slug``, so two runs over the same gate records
    produce byte-identical files.
    """
    encoded = []
    for row in rows:
        record = asdict(row)
        encoded.append([_encode(name, record[name]) for name in FIELDNAMES])
    return write_rows(path, FIELDNAMES, encoded)


def read_attrition_csv(path: Path, *, expected_rows: int | None = None) -> list[AttritionRow]:
    """Read *path* back into typed rows, validating the schema (fail-fast).

    Raises ``FileNotFoundError`` when the file is absent (``validation_attrition`` has
    not run for this country) and ``ValueError`` when the header is missing a column,
    a cell will not parse as its declared type, or -- when *expected_rows* is given --
    the row count disagrees with it.

    *expected_rows* is the number of combinations the caller expects to join against,
    normally the record count of ``population_cap/_index.json``. A disagreement means
    the CSV and the gate index describe different states of the pipeline, so every
    joined row would attribute a cost or a rate to a combination set that no longer
    exists; that is a hard error, never a warning.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Validation-attrition CSV not found: {path}. Run "
            "scripts/analyze/analyze_validation_attrition.py for this country first."
        )

    rows: list[AttritionRow] = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, FIELDNAMES)
        if missing:
            raise stale_schema_error(
                path,
                label="validation-attrition CSV",
                missing=missing,
                header=header,
                schema_version=SCHEMA_VERSION,
                fieldnames=FIELDNAMES,
                remedy=STALE_SCHEMA_REMEDY,
            )
        for record in reader:
            slug = record.get("slug") or "<unnamed>"
            unit = f"combination {slug!r}"
            values: dict[str, Any] = {name: record[name] for name in _TEXT_FIELDS}
            values["slug"] = slug
            for column in _BOOL_FIELDS:
                values[column] = parse_bool(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
            for column in _INT_FIELDS:
                values[column] = parse_int(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
            for column in _OPTIONAL_FLOAT_FIELDS:
                values[column] = parse_optional_float(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
            rows.append(AttritionRow(**values))

    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(
            f"{path}: holds {len(rows)} combination row(s) but the caller expects "
            f"{expected_rows}. The CSV and the population-cap index were written from "
            "different states of the pipeline -- re-run "
            "scripts/analyze/analyze_validation_attrition.py --force for this country "
            "to regenerate it from the current gate records."
        )
    return rows

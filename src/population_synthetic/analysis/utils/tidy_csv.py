"""tidy_csv.py -- the primitives the analysis tidy-CSV contracts are built from.

Several modules in this package publish a *tidy CSV contract*: a flat file written by
one task and read back by another, with a fixed column order, a strict reader, and (for
the versioned ones) a schema version. ``realism_csv``, ``realism_clash_csv`` and
``validity_csv`` are the three current cases. They agree on how a **cell** is spelled
and how a **header** is checked; they disagree -- correctly -- on everything else: which
columns exist, what one row means, which task rewrites the file, and what the
remediation sentence is. This module holds only the part they genuinely share.

What lives here is therefore deliberately narrow:

* **Cell codecs.** ``true``/``false`` for a boolean; ``""`` for an absent optional
  number. The empty cell is the load-bearing one: an absent metric must read back as
  ``None``, **never** as ``0.0``, because ``0.0`` is a real and very different claim
  (guide 03 sect. 6 -- keep "zero" distinct from "absent"). Every codec raises with the
  file, the offending row, and the column named rather than substituting a default.
* **Header validation.** The required-columns subset check plus the stale-schema error
  shape, so a file written under an older schema names its remedy instead of being
  silently tolerated -- a tolerated old file reports every new column as zero, which is
  indistinguishable from a genuinely clean unit.
* **The whole-file writer.** Truncating, never appending, so writing a unit's file N
  times is indistinguishable from writing it once (guide 02 sect. 5).

Boundary (guide 02 sect. 2): this module knows nothing about any specific column set,
unit of analysis, severity level, persona, clash, task, or output layout. The caller
supplies the offending row's identity phrase and the remediation sentence; a schema
module owns its own fieldnames and its own version.

These are primitives, not a framework: there is no schema-driven codec registry here,
because each contract's reader is small, explicit, and reads better as straight-line
code than as a declaration consumed by machinery.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "FALSE_TOKEN",
    "TRUE_TOKEN",
    "TRUTHY_TOKENS",
    "encode_bool",
    "is_truthy",
    "missing_columns",
    "parse_bool",
    "parse_int",
    "parse_optional_float",
    "parse_optional_int",
    "stale_schema_error",
    "write_rows",
]

#: The canonical boolean spelling every writer here emits.
TRUE_TOKEN = "true"
FALSE_TOKEN = "false"

#: The spellings a **lenient** reader accepts as true. Wider than
#: :data:`TRUE_TOKEN` on purpose: the validity CSVs are written by two independent
#: tasks whose detail columns come from their own row builders (a Python ``True``
#: renders as ``True``, a flag as ``1``), so their reader takes the union. A contract
#: whose single writer always emits :data:`TRUE_TOKEN` uses :func:`parse_bool`
#: instead, which rejects everything else -- an unexpected token there means the file
#: was not written by that writer, and guessing at its meaning is exactly the silent
#: corruption these contracts exist to prevent.
TRUTHY_TOKENS: tuple[str, ...] = (TRUE_TOKEN, "1", "yes")


def encode_bool(value: Any) -> str:
    """Serialise *value* as the canonical :data:`TRUE_TOKEN`/:data:`FALSE_TOKEN`."""
    return TRUE_TOKEN if value else FALSE_TOKEN


def is_truthy(raw: Any) -> bool:
    """Lenient truth test: is *raw* one of :data:`TRUTHY_TOKENS` (case/space-insensitive)?

    Anything else -- including an empty cell -- is false. Used by readers whose file
    may carry any of several true spellings; use :func:`parse_bool` where the writer is
    known and a stray token should raise.
    """
    return str(raw).strip().lower() in TRUTHY_TOKENS


def _cell_error(
    *, path: Path, unit: str, column: str, raw: Any, complaint: str, remedy: str
) -> ValueError:
    """Build the shared malformed-cell error: file, row, column, value, complaint."""
    tail = f" {remedy}" if remedy else ""
    return ValueError(
        f"{path}: {unit} column {column!r} is {raw!r}, which is {complaint}.{tail}"
    )


def parse_int(raw: str, *, column: str, path: Path, unit: str, remedy: str = "") -> int:
    """Parse a count cell, raising with *path*/*unit*/*column* named on failure.

    *unit* is a short phrase identifying the offending row (e.g. ``persona 'p_007'``);
    *remedy* is the caller's optional "how to fix this file" sentence, appended verbatim.
    """
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise _cell_error(
            path=path, unit=unit, column=column, raw=raw,
            complaint="not an integer count", remedy=remedy,
        ) from exc


def parse_bool(raw: str, *, column: str, path: Path, unit: str, remedy: str = "") -> bool:
    """Parse a boolean cell **strictly**: only :data:`TRUE_TOKEN`/:data:`FALSE_TOKEN`.

    A third spelling means the file was not written by this contract's writer, so it
    raises rather than being coerced (see :data:`TRUTHY_TOKENS` for the lenient case).
    """
    token = str(raw).strip().lower()
    if token == TRUE_TOKEN:
        return True
    if token == FALSE_TOKEN:
        return False
    raise _cell_error(
        path=path, unit=unit, column=column, raw=raw,
        complaint=f"neither {TRUE_TOKEN!r} nor {FALSE_TOKEN!r}", remedy=remedy,
    )


def parse_optional_float(
    raw: str, *, column: str, path: Path, unit: str, remedy: str = ""
) -> float | None:
    """Parse an optional number: empty -> ``None`` (undefined), never ``0.0``.

    The whole point of the empty cell. Returning ``0.0`` for an undefined metric would
    assert the lowest possible value, which is a real and entirely fabricated claim.
    """
    if raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise _cell_error(
            path=path, unit=unit, column=column, raw=raw,
            complaint="neither empty (undefined) nor a number", remedy=remedy,
        ) from exc


def parse_optional_int(
    raw: str, *, column: str, path: Path, unit: str, remedy: str = ""
) -> int | None:
    """Parse an optional count: empty -> ``None`` (undefined), never ``0``.

    The integer counterpart of :func:`parse_optional_float`, for a count that a
    producer may legitimately not have observed at all -- a token total over a run
    that reported no token telemetry, say. ``0`` would claim the run consumed no
    tokens, which is a measurement; the empty cell claims nothing. Counts stay
    integers on the way back in, so an absent count and a present one never differ in
    type as well as in value (guide 02 sect. 3).
    """
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise _cell_error(
            path=path, unit=unit, column=column, raw=raw,
            complaint="neither empty (undefined) nor an integer count", remedy=remedy,
        ) from exc


def missing_columns(header: Sequence[str] | None, required: Sequence[str]) -> list[str]:
    """Names in *required* absent from *header*, in *required* order.

    A **subset** check, not an equality check: a file carrying extra columns is
    readable, a file missing one is not.
    """
    present = set(header or ())
    return [name for name in required if name not in present]


def stale_schema_error(
    path: Path,
    *,
    label: str,
    missing: Sequence[str],
    header: Sequence[str] | None,
    schema_version: int,
    fieldnames: Sequence[str],
    remedy: str,
) -> ValueError:
    """Build the shared "this file predates the current schema" error.

    Names what is missing, what was found, what was expected at *schema_version*, and
    the caller's *remedy* -- the command that rewrites the file. Tolerating the old file
    instead would report every column added since as absent/zero, which downstream is
    indistinguishable from a genuinely empty result.
    """
    return ValueError(
        f"{path}: {label} is missing required column(s) {list(missing)}; "
        f"header is {list(header or ())}. Expected schema v{schema_version}: "
        f"{list(fieldnames)}. The file predates the current schema -- regenerate it "
        f"with {remedy}"
    )


def write_rows(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Path:
    """Write *header* + *rows* to *path* whole (truncating, never appending); return *path*.

    N writes of the same rows are indistinguishable from one -- the idempotency every
    downstream row-count and reconciliation check depends on (guide 02 sect. 5). Cells
    are written in the order given; encoding each cell is the caller's job, so the
    absent-vs-zero decision stays with the schema that understands the column.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))
    return path

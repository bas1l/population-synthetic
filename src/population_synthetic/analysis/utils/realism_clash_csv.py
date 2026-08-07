"""realism_clash_csv.py -- the per-clash tidy CSV shared by ``persona_realism`` -> ``realism_ranking``.

The **second** file on the same inter-task seam as
:mod:`population_synthetic.analysis.utils.realism_csv`, one grain finer.
``persona_realism`` judges one combination and writes ``{combo}_clashes.csv`` (one row
per ``(persona, round, attribute-pair, severity)`` clash); ``realism_ranking`` reads it
back to answer the one question the per-persona file cannot: not *how much* of a
model x method cell carries a clash at a given severity, but **what clashed** -- which
attribute pair, and which two category values.

Why a second file rather than more columns on the first
-------------------------------------------------------
Grain. A persona carries 0..N clashes, so putting them on the per-persona row forces one
of two bad shapes: a repeating group (``clash_1_attr_a``, ``clash_2_attr_a``, ...) whose
width depends on the data and whose columns are positional rather than named, or a lossy
top-1 truncation that silently discards every clash after the first. Either destroys the
property that makes the per-persona file useful -- fixed width, one row == one persona.
Two tidy files, each at its own grain, keep both readable and both strict.

The deliberate divergence: no denominator on the row
----------------------------------------------------
``realism_csv`` states as its third property that *the rows carry their own
denominators*. This file deliberately does **not**, because the denominator of any rate
computed from it is a count of **personas** (how many of the cell's personas exhibit this
clash), which is a property of the sibling per-persona file and not of a clash. Repeating
a per-combination constant on a variable number of rows would additionally let a reader
compute a prevalence from this file alone that silently disagrees with the sibling
whenever the two are out of step.

The compensating join: the consumer reads **both** files for a combination and joins on
``persona_id`` -- the per-persona file supplies the base, this file the numerator. What
makes that join safe is the reconciliation check in :func:`read_realism_clashes_csv`: the
number of distinct ``(persona_id, attr_a, attr_b, severity)`` tuples at level *L* must
equal the sum of the sibling's ``clash_count_s{L}`` column. Both are counts of *distinct
clashes per persona*, so they are the same number computed two ways; a disagreement means
the two files were written from different states of the verdict cache, and every rate
joined across them would be over the wrong base. That is a hard error, never a warning.

Row grain and determinism
-------------------------
One row per ``(persona_id, round_index, attr_a, attr_b, severity)``, deduplicated
*within* a round exactly as the producer's per-persona reduction does (a clash the judge
repeats inside one round is one row). Consequently the rows for a given
``(persona, pair, severity)`` number exactly the rounds in which it was seen, and the
count of distinct ``(persona, pair, severity)`` is the per-persona clash count. The
writer sorts on that same key -- total, with no residual ties, since a duplicate key is
rejected -- so the byte stream is a function of the row *set*, never of the order the
producer happened to build it in.

``attr_a``/``attr_b`` are the **sorted** pair, matching the producer's canonical clash
identity: a judge naming ``(b, a)`` in one round and ``(a, b)`` in another describes one
clash, and an uncanonicalised pair would split one driver into two ranks. This module
*enforces* that ordering; it does not perform it (canonicalisation belongs to the
derivation that builds the rows).

``value_a``/``value_b`` are the persona's own category values for those two attributes.
They are empty **iff** the value join failed -- ``unresolved`` is the explicit marker for
that, so an empty cell is never mistaken for a real value and no value is ever
substituted for an absent one. A join fails when the judge names an attribute the persona
does not have; the clash is still real and still counted, which is why an unresolved row
is written rather than dropped.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from operator import attrgetter
from pathlib import Path
from typing import Any, Mapping, Sequence

from population_synthetic.analysis.utils.realism_csv import (
    SEVERITY_COUNT_FIELDS,
    SEVERITY_LEVELS,
)
from population_synthetic.analysis.utils.tidy_csv import (
    encode_bool,
    missing_columns,
    parse_bool,
    parse_int,
    stale_schema_error,
    write_rows,
)

__all__ = [
    "FIELDNAMES",
    "RealismClashRow",
    "SCHEMA_VERSION",
    "read_realism_clashes_csv",
    "write_realism_clashes_csv",
]

#: Bumped whenever a column is added, removed, or re-typed. Stamped by the producer into
#: its combination report (as its own key, beside the per-persona schema version) so a
#: reader can name a mismatch instead of guessing at it.
SCHEMA_VERSION = 1

#: Appended to a malformed-cell error: this file is a derived artifact, so the fix is
#: always to rewrite it from the verdict cache rather than to hand-edit it.
_MALFORMED_REMEDY = (
    "The file is malformed; re-run the persona_realism judge for this combination to "
    "rewrite it."
)

#: The command that rewrites the file, and why it is free (the verdict caches already
#: hold every field these columns are derived from -- no judging, no LLM calls).
_REWRITE_COMMAND = (
    "scripts/analyze/analyze_persona_realism.py --rewrite-artifacts (zero LLM calls; "
    "the verdict caches already hold everything these columns are derived from)."
)

#: Used in an error when the caller did not name where its expected counts came from.
_DEFAULT_COUNTS_SOURCE = "the sibling per-persona realism CSV"


@dataclass(frozen=True)
class RealismClashRow:
    """One clash the judge raised, in one round, for one persona.

    ``slug``/``country``/``model``/``strategy``/``is_real_reference`` repeat the sibling
    per-persona file's identity block verbatim, so a consumer can group these rows by
    competitor without re-parsing the slug and can hold the real competitor out of the
    model x method factor tests by flag rather than by string-sniffing.

    ``round_index`` is the 0-based position of the round among the persona's
    **successful** rounds -- the same series the per-persona file's ``typicality_rounds``
    indexes -- so round-level detail survives instead of being collapsed at write time.

    ``attr_a``/``attr_b`` are the clashing axes as the sorted pair; ``value_a``/``value_b``
    are that persona's category values for them, empty iff ``unresolved``. ``severity`` is
    one of :data:`~population_synthetic.analysis.utils.realism_csv.SEVERITY_LEVELS`.

    ``unresolved`` marks a clash whose attribute name is absent from the persona's own
    attribute map (a judge naming an axis that does not exist). The clash is genuine and
    is counted; only its values are unknown.
    """

    persona_id: str
    slug: str
    country: str
    model: str
    strategy: str
    is_real_reference: bool
    round_index: int
    attr_a: str
    attr_b: str
    value_a: str
    value_b: str
    severity: str
    unresolved: bool


#: Column order == :class:`RealismClashRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(RealismClashRow))

_BOOL_FIELDS = ("is_real_reference", "unresolved")
_INT_FIELDS = ("round_index",)
#: Every remaining column: plain text, read verbatim (``persona_id`` is read separately
#: because it is also the row's identity in every error this module raises).
_TEXT_FIELDS = tuple(
    name for name in FIELDNAMES
    if name not in (*_BOOL_FIELDS, *_INT_FIELDS, "persona_id")
)

#: The grain: one row per this tuple, and (because a duplicate of it is rejected) the
#: writer's *total* sort key. Defined once and read both ways, so the ordering can never
#: drift from the uniqueness the reconciliation check counts against.
_GRAIN_FIELDS: tuple[str, ...] = ("persona_id", "round_index", "attr_a", "attr_b", "severity")

#: ``row -> tuple`` over :data:`_GRAIN_FIELDS`.
_sort_key = attrgetter(*_GRAIN_FIELDS)


def _unit(persona_id: str, attr_a: Any, attr_b: Any) -> str:
    """The identity phrase a malformed-cell / invalid-row error names the offender by."""
    return f"persona {persona_id!r} clash ({attr_a!r}, {attr_b!r})"


def _validate_row(row: RealismClashRow, *, path: Path, unit: str) -> None:
    """Enforce the schema invariants one row must satisfy (fail-fast, no coercion)."""
    if row.severity not in SEVERITY_LEVELS:
        raise ValueError(
            f"{path}: {unit} has severity {row.severity!r}, which is not one of "
            f"{list(SEVERITY_LEVELS)}. {_MALFORMED_REMEDY}"
        )
    if row.round_index < 0:
        raise ValueError(
            f"{path}: {unit} has round_index {row.round_index!r}; a round index is the "
            f"0-based position among the persona's successful rounds. {_MALFORMED_REMEDY}"
        )
    if row.attr_a > row.attr_b:
        raise ValueError(
            f"{path}: {unit} carries the attribute pair ({row.attr_a!r}, {row.attr_b!r}) "
            "unsorted. The pair is the canonical clash identity and must be sorted, or "
            "one clash ranks twice under two spellings."
        )
    if not isinstance(row.value_a, str) or not isinstance(row.value_b, str):
        raise ValueError(
            f"{path}: {unit} carries a non-string category value "
            f"({row.value_a!r}, {row.value_b!r}); use '' for an absent value so the "
            "empty cell keeps meaning absent."
        )
    if row.unresolved and (row.value_a or row.value_b):
        raise ValueError(
            f"{path}: {unit} is marked unresolved but carries the value(s) "
            f"({row.value_a!r}, {row.value_b!r}). An unresolved clash is one whose "
            "attribute names are absent from the persona, so it has no values to carry."
        )


def _validate_rows(rows: Sequence[RealismClashRow], *, path: Path) -> None:
    """Validate every row and enforce the grain (no two rows share the grain key)."""
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        unit = _unit(row.persona_id, row.attr_a, row.attr_b)
        _validate_row(row, path=path, unit=unit)
        key = _sort_key(row)
        if key in seen:
            raise ValueError(
                f"{path}: two rows share the clash grain key {key!r}. The grain is one "
                "row per (persona, round, sorted attribute pair, severity) -- a clash "
                "repeated inside one round is deduplicated to a single row."
            )
        seen.add(key)


def _text_cell(record: Mapping[str, Any], column: str, *, path: Path, unit: str) -> str:
    """Read one text cell, raising when the row is short (``DictReader`` yields ``None``).

    A truncated row must not become a row with silently empty text: an empty ``value_a``
    means "this clash has no value", which is a claim, not a missing field.
    """
    raw = record.get(column)
    if raw is None:
        raise ValueError(
            f"{path}: {unit} has no cell for column {column!r} -- the row is shorter than "
            f"the header. {_MALFORMED_REMEDY}"
        )
    return str(raw)


def _encode(field_name: str, value: Any) -> str:
    """Serialise one cell. Booleans take the canonical tokens; everything else is text."""
    if field_name in _BOOL_FIELDS:
        return encode_bool(value)
    return str(value)


def write_realism_clashes_csv(rows: Sequence[RealismClashRow], path: Path) -> Path:
    """Write *rows* to *path* with the :data:`FIELDNAMES` columns; return *path*.

    Written **whole** (truncating), never appended, and **sorted** on the grain key, so
    the bytes are a function of the row set alone: writing the same clashes twice, or in
    a different order, yields an identical file. That is what makes the artifact
    order-independent across combinations and safe to regenerate.

    An empty *rows* writes a header-only file rather than no file at all, so "this
    combination has no clashes" stays distinguishable from "this combination was never
    processed" -- the reader raises only on the latter.

    Raises ``ValueError`` when a row violates the schema (unknown severity, unsorted
    attribute pair, an unresolved row carrying values, a negative round index) or when
    two rows share the grain key -- all producer bugs, caught before they reach disk.
    """
    ordered = sorted(rows, key=_sort_key)
    _validate_rows(ordered, path=Path(path))
    encoded = []
    for row in ordered:
        record = asdict(row)
        encoded.append([_encode(name, record[name]) for name in FIELDNAMES])
    return write_rows(path, FIELDNAMES, encoded)


def _distinct_clash_counts(rows: Sequence[RealismClashRow]) -> dict[str, int]:
    """Per level, the number of distinct ``(persona, attr_a, attr_b)`` clashes.

    Rounds collapse here: a clash seen in three rounds of one persona is three rows but
    one distinct clash, which is the unit the sibling per-persona file counts.
    """
    seen: dict[str, set[tuple[str, str, str]]] = {level: set() for level in SEVERITY_LEVELS}
    for row in rows:
        seen[row.severity].add((row.persona_id, row.attr_a, row.attr_b))
    return {level: len(members) for level, members in seen.items()}


def _reconcile(
    rows: Sequence[RealismClashRow],
    expected_counts: Mapping[str, int],
    *,
    path: Path,
    source: str,
) -> None:
    """Check the per-level distinct-clash totals against the sibling file's counts."""
    unknown = sorted(set(expected_counts) - set(SEVERITY_LEVELS))
    if unknown:
        raise ValueError(
            f"{path}: expected_counts names unknown severity level(s) {unknown}; the "
            f"judge emits {list(SEVERITY_LEVELS)}."
        )
    actual = _distinct_clash_counts(rows)
    for level in SEVERITY_LEVELS:
        # A level the caller omitted is asserted to be zero, never skipped: skipping it
        # would drop the invariant silently for exactly the level that went missing.
        expected = int(expected_counts.get(level, 0))
        if actual[level] != expected:
            raise ValueError(
                f"{path}: holds {actual[level]} distinct (persona, attribute-pair) "
                f"clash(es) at {level}, but {source} declares {expected} (the sum of its "
                f"{SEVERITY_COUNT_FIELDS[level]!r} column). The two files were written "
                "from different states of the verdict cache, so every rate joined across "
                f"them would be over the wrong base -- regenerate both with {_REWRITE_COMMAND}"
            )


def read_realism_clashes_csv(
    path: Path,
    *,
    expected_counts: Mapping[str, int] | None = None,
    expected_counts_source: Path | str | None = None,
) -> list[RealismClashRow]:
    """Read *path* back into typed rows, validating the schema (fail-fast).

    Raises ``FileNotFoundError`` when the file is **absent** -- the producing task has
    not run for this combination -- and ``ValueError`` when the header is missing a
    column, a cell will not parse as its declared type, a row violates a schema
    invariant, or the reconciliation below fails. A file that is *present but holds only
    its header* is valid and returns ``[]``: that is a combination the judge found no
    clash in, a real and different fact from an unprocessed one.

    *expected_counts* maps each severity level to the number of distinct
    ``(persona, attribute-pair)`` clashes the sibling per-persona CSV declares at that
    level (the sum of its ``clash_count_s{L}`` column over the combination's rows). When
    given, the same quantity is recomputed from these rows and any disagreement raises,
    naming both files and the regeneration command. Passing ``None`` skips the check --
    used by tests and by callers that hold only this file; the loader always passes it.
    *expected_counts_source* is the path those counts were read from, used only to name
    the second file in that error.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Per-clash realism CSV not found: {path}. Run "
            "scripts/analyze/analyze_persona_realism.py for this combination first "
            "(--rewrite-artifacts if its other artifacts already exist)."
        )

    rows: list[RealismClashRow] = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, FIELDNAMES)
        if missing:
            raise stale_schema_error(
                path,
                label="per-clash realism CSV",
                missing=missing,
                header=header,
                schema_version=SCHEMA_VERSION,
                fieldnames=FIELDNAMES,
                remedy=_REWRITE_COMMAND,
            )
        for record in reader:
            persona = record.get("persona_id") or "<unnamed>"
            unit = _unit(persona, record.get("attr_a"), record.get("attr_b"))
            values: dict[str, Any] = {"persona_id": persona}
            for column in _TEXT_FIELDS:
                values[column] = _text_cell(record, column, path=path, unit=unit)
            for column in _BOOL_FIELDS:
                values[column] = parse_bool(
                    record[column], column=column, path=path, unit=unit,
                    remedy=_MALFORMED_REMEDY,
                )
            for column in _INT_FIELDS:
                values[column] = parse_int(
                    record[column], column=column, path=path, unit=unit,
                    remedy=_MALFORMED_REMEDY,
                )
            rows.append(RealismClashRow(**values))

    _validate_rows(rows, path=path)

    if expected_counts is not None:
        _reconcile(
            rows, expected_counts, path=path,
            source=str(expected_counts_source) if expected_counts_source else _DEFAULT_COUNTS_SOURCE,
        )
    return rows

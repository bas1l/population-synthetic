"""cost_csv.py -- the tidy per-combination cost-efficiency contract.

One row per combination that has **both** an accuracy score and a measured generation
cost: the fidelity ranking's ``overall_tv_similarity`` beside the USD the run actually
spent, plus the counts both quantities are denominated on. ``cost_efficiency`` writes
it; the accuracy-vs-cost scatter reads it back.

Two columns exist because a number here is uninterpretable without them, and both are
columns rather than caption prose because the table travels without the code that wrote
it (ADR 2026-08-07: caveats travel as data fields):

``cost_basis``
    Which persona population the cost was totalled over. Two are possible -- the full
    generated pool in ``01_Raw``, or the ~100-persona capped mirror -- and they differ
    by up to 5.5x on the live grid, in a direction that varies by model. A cost figure
    whose basis is not stated is not a figure, it is a number.
``unmetered``
    True for a model priced ``{in: 0, out: 0}`` -- the nine local ``ollama_*`` models,
    about a third of the axis. Their ``total_cost_usd`` is a **measured** ``0.0``, not
    an absent one, and unmetered is emphatically not *free*: local inference has a real
    cost this pipeline's pricing config does not model. The flag is what lets a
    consumer render that caveat instead of publishing local models as costless.

Three properties the schema keeps, matching its ``attrition_csv`` sibling:

* **Absent is not zero.** A combination that reported no token telemetry has an empty
  ``total_cost_usd``, which reads back as ``None``. ``0.0`` there would assert a free
  run (guide 03 sect. 6). The same holds for the three token totals.
* **Counts stay counts.** Every persona, call and token count round-trips as ``int``.
* **Rates carry their denominators.** ``cost_per_usable_persona`` ships beside
  ``total_cost_usd`` and ``clean``, the two numbers it is the quotient of;
  ``overall_tv_similarity`` ships beside ``n_scored``, the population it was scored
  over; ``generation_multiplier`` ships beside ``generated`` and ``clean`` (guide 03
  sect. 4).

**There is deliberately no composite score.** No "accuracy per dollar", no value index,
no rank. Two thirds of the axis would divide by zero, and a composite would encode a
directional claim -- that a point of fidelity is worth some number of dollars -- into
arithmetic where no reader can see it or disagree with it (ADR 2026-08-07 Decision 2).
Accuracy and cost are published side by side and the trade-off is the reader's to make.

Boundary: this module knows nothing about figures, about how the join was performed, or
about which process wrote the file. It is the schema and nothing else.
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
    parse_optional_int,
    stale_schema_error,
    write_rows,
)

__all__ = [
    "FIELDNAMES",
    "MALFORMED_REMEDY",
    "PRICING_FLAG_SEPARATOR",
    "SCHEMA_VERSION",
    "STALE_SCHEMA_REMEDY",
    "CostRow",
    "decode_pricing_flags",
    "encode_pricing_flags",
    "read_cost_csv",
    "write_cost_csv",
]

#: Bumped whenever a column is added, removed, or re-typed.
#:
#: v1 is the first published shape: the four axis-identity columns, the accuracy pair,
#: the four gate counts, the four telemetry counts, the two cost quantities, and the
#: five provenance columns.
#:
#: Every column is **required**, and the reader raises on a file lacking one rather
#: than filling it in, for the reason the sibling attrition schema states: a tolerated
#: absence is indistinguishable from a real value. Two cases here are worse than the
#: general one. A missing ``cost_basis`` would leave a cost column with no denominator,
#: which is the exact defect this process exists to correct. A missing ``unmetered``
#: would default to false, turning nine local models' measured zero into an apparent
#: free lunch on a metered axis.
# v2 (2026-08-21): added cost_per_100_usable_personas. Required rather than optional
# because a reader that tolerated its absence would have to rescale the per-persona
# column itself, which is exactly the hand-multiplication this column exists to remove.
SCHEMA_VERSION = 2

#: Separator for the pricing config's caveat tags inside the single ``pricing_flags``
#: cell. Semicolon rather than comma so the cell never needs CSV quoting to be read by
#: eye, and the tags themselves are bracketed words with no semicolons in them.
PRICING_FLAG_SEPARATOR = ";"

#: Appended to a malformed-cell error. The file is derived wholly from artifacts other
#: tasks already wrote, so the fix is always to rewrite it rather than to edit a cell.
MALFORMED_REMEDY = (
    "The file is malformed; re-run scripts/analyze/analyze_cost_efficiency.py --force "
    "for this country to rewrite it from the ranking, attrition and telemetry records."
)

#: Appended to the stale-schema error: the command that rewrites the file. Cheap -- no
#: generation, no validation and no capping is re-run, only three existing artifacts
#: re-read and the raw-pool telemetry re-totalled.
STALE_SCHEMA_REMEDY = (
    "scripts/analyze/analyze_cost_efficiency.py --force (nothing upstream is re-run; "
    "the ranking CSV, the attrition CSV and the 01_Raw telemetry already hold every "
    "quantity)."
)


@dataclass(frozen=True)
class CostRow:
    """One combination's accuracy beside the cost of producing it.

    ``slug`` is ``{country}_{strategy}_{model}``, with the three axis ids carried
    alongside so a consumer never re-parses it (neither strategy nor model ids are
    ``_``-free, so a naive split is wrong) and so the join key can be re-derived and
    re-checked without a registry lookup.

    **Accuracy.** ``overall_tv_similarity`` is the fidelity ranking's headline score for
    this combination, and ``n_scored`` the capped population it was computed over. The
    two always travel together: the score is a mean over a population, and comparing
    scores computed over different populations is only legitimate once that is visible.

    **The gate counts**, from the attrition contract. ``generated`` is the pool the run
    actually produced, ``clean`` the personas that passed both validity gates,
    ``selected`` what the cap drew. ``generation_multiplier`` (``generated / clean``) is
    carried because it is what explains a high cost per usable persona -- a model that
    wastes nine personas in ten pays for ten. It is **not** used to correct the cost:
    the cost here is measured over the generated pool directly, and the discarded
    personas turn out to be systematically cheaper than the kept ones, so multiplying a
    capped figure by this factor would over-correct.

    **The telemetry counts** are summed over the same pool ``cost_basis`` names.
    ``n_calls`` is every LLM call in it; the three token totals are ``None`` when no
    call reported that field, never ``0``.

    **The cost.** ``total_cost_usd`` is the whole combination's spend over the
    ``cost_basis`` population; ``cost_per_usable_persona`` is that divided by ``clean``
    -- dollars per persona the pipeline could actually use, which is the only cost
    number comparable across combinations whose pools differ by 5x. Both are ``None``
    when there is no telemetry to price or no usable persona to divide by, and a
    measured ``0.0`` when the model is unmetered.

    **Pricing provenance.** ``price_in``/``price_out`` are the USD-per-million-token
    rates actually applied, and ``pricing_flags`` the bracketed caveats the pricing
    config's own comment carries for this model (e.g. ``VERIFY``), joined by
    :data:`PRICING_FLAG_SEPARATOR`. An empty cell is a positive statement that the row
    is untagged. ``has_token_data`` is the availability gate: false means the run left
    no token counts, so the cost is absent rather than zero.
    """

    slug: str
    country: str
    model: str
    strategy: str
    overall_tv_similarity: float
    n_scored: int
    generated: int
    clean: int
    selected: int
    generation_multiplier: float | None
    n_calls: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    total_cost_usd: float | None
    cost_per_usable_persona: float | None
    #: The same quantity per 100 usable personas -- the unit the figures and the
    #: manuscript quote, because a per-persona cost of 0.0049 USD is unreadable and
    #: invites a silent factor-of-100 slip when someone rescales it by hand. Derived
    #: in the builder, never at render time.
    cost_per_100_usable_personas: float | None
    cost_basis: str
    unmetered: bool
    has_token_data: bool
    price_in: float
    price_out: float
    pricing_flags: str


#: Column order == :class:`CostRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(CostRow))

_BOOL_FIELDS = ("unmetered", "has_token_data")
_INT_FIELDS = ("n_scored", "generated", "clean", "selected", "n_calls")
_OPTIONAL_INT_FIELDS = ("input_tokens", "output_tokens", "total_tokens")
_FLOAT_FIELDS = ("overall_tv_similarity", "price_in", "price_out")
_OPTIONAL_FLOAT_FIELDS = (
    "generation_multiplier",
    "total_cost_usd",
    "cost_per_usable_persona",
    "cost_per_100_usable_personas",
)
_TEXT_FIELDS = ("slug", "country", "model", "strategy", "cost_basis", "pricing_flags")


def encode_pricing_flags(flags: Sequence[str]) -> str:
    """Join the pricing config's caveat tags into one cell.

    An empty sequence encodes as ``""``, which the reader gives back as an empty
    tuple: "this row carries no caveats", a statement, not a missing value.
    """
    return PRICING_FLAG_SEPARATOR.join(str(flag) for flag in flags)


def decode_pricing_flags(cell: str) -> tuple[str, ...]:
    """Split a ``pricing_flags`` cell back into its tags (empty cell -> empty tuple)."""
    return tuple(part.strip() for part in cell.split(PRICING_FLAG_SEPARATOR) if part.strip())


def _encode(field_name: str, value: Any) -> str:
    """Serialise one cell, keeping ``None`` (undefined) distinct from ``0`` (a value)."""
    if field_name in _BOOL_FIELDS:
        return encode_bool(value)
    if value is None:
        return ""
    return str(value)


def write_cost_csv(rows: Sequence[CostRow], path: Path) -> Path:
    """Write *rows* to *path* with the :data:`FIELDNAMES` columns; return *path*.

    Written **whole** (truncating), never appended, so writing it N times is
    indistinguishable from writing it once (guide 02 sect. 5). Rows are emitted in the
    order given; the producer sorts by ``slug``, so two runs over the same inputs
    produce byte-identical files.
    """
    encoded = []
    for row in rows:
        record = asdict(row)
        encoded.append([_encode(name, record[name]) for name in FIELDNAMES])
    return write_rows(path, FIELDNAMES, encoded)


def read_cost_csv(path: Path, *, expected_rows: int | None = None) -> list[CostRow]:
    """Read *path* back into typed rows, validating the schema (fail-fast).

    Raises ``FileNotFoundError`` when the file is absent (``cost_efficiency`` has not
    run for this country) and ``ValueError`` when the header is missing a column, a
    cell will not parse as its declared type, or -- when *expected_rows* is given --
    the row count disagrees with it.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Cost-efficiency CSV not found: {path}. Run "
            "scripts/analyze/analyze_cost_efficiency.py for this country first."
        )

    rows: list[CostRow] = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, FIELDNAMES)
        if missing:
            raise stale_schema_error(
                path,
                label="cost-efficiency CSV",
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
            for column in _OPTIONAL_INT_FIELDS:
                values[column] = parse_optional_int(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
            for column in _FLOAT_FIELDS:
                parsed = parse_optional_float(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
                if parsed is None:
                    raise ValueError(
                        f"{path}: {unit} column {column!r} is empty, but it is a required "
                        f"measurement -- a row without it could not have been joined. "
                        f"{MALFORMED_REMEDY}"
                    )
                values[column] = parsed
            for column in _OPTIONAL_FLOAT_FIELDS:
                values[column] = parse_optional_float(
                    record[column], column=column, path=path, unit=unit,
                    remedy=MALFORMED_REMEDY,
                )
            rows.append(CostRow(**values))

    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(
            f"{path}: holds {len(rows)} combination row(s) but the caller expects "
            f"{expected_rows}. The CSV and the caller's combination set were written "
            "from different states of the pipeline -- re-run "
            "scripts/analyze/analyze_cost_efficiency.py --force for this country."
        )
    return rows

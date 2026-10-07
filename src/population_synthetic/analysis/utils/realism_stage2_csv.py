"""realism_stage2_csv.py -- the stage-2 impossibility-class CSVs shared by ``persona_realism`` -> ``realism_ranking``.

Stage 1 of the persona-realism judge sees only a persona's mapped categories and reports
hard contradictions (S3 clashes). Stage 2 re-reads every S3 clash beside the persona's
own raw free-text answers and says **why** it arose -- the raw text itself is impossible,
a real situation got mutually exclusive labels, the text is too thin to tell, one
attribute was mis-coded by the mapper, or stage 1 applied a wrong rule. This module owns
the two files that carry that classification out of the producing task:

- ``{combo}_stage2.csv`` -- one row per ``(persona_id, round_index, attr_a, attr_b)``
  S3 clash: its class, the stage-2 reason, the listed legal fact an age-based
  ``raw_impossible`` rests on, the attribute the mapper mis-read (``mapping_error``
  only), the raw quotes stage 2 relied on, and the two attributes' own raw answers
  read straight from ``identity.json``.
- ``{combo}_stage2_personas.csv`` -- one row per persona holding >= 1 S3 clash, with the
  persona-level class (see :func:`persona_class`).

Grain and reconciliation
------------------------
The issue file's grain is the per-clash contract's (``realism_clash_csv``) restricted to
severity S3: the same ``(persona_id, round_index, sorted attribute pair)`` key, so the
two join row-for-row. Every S3 clash has a row here **including** the ones stage 2 did
not classify (``unclassified``: the call failed, or stage 2 is switched off) and the ones
it cannot classify (``not_applicable_no_free_text``: the real SCB reference has no free
text). :func:`reconcile_with_clashes` checks that key set against the sibling clash rows
and raises on any difference -- a stage-2 count over a different set of clashes would be
a numerator from one state of the verdict cache over a base from another.

Classes
-------
:data:`STAGE2_CLASSES` are the five classes the stage-2 prompt defines (a protocol
constant, like the S1/S2/S3 severities). :data:`UNCLASSIFIED` and :data:`NOT_APPLICABLE`
are pipeline states, never answers. The persona-level class ranks the five by the order
declared in ``judge.yaml`` (``stage2.persona_class_order``), stamped into each report's
provenance so a consumer re-deriving the class under a round cap uses the order the
producer used. Two fixed rules place the pipeline states: a persona whose issues are all
``not_applicable_no_free_text`` is that class (a mix with real classes raises -- one
persona cannot both have and lack free text); otherwise an ``unclassified`` issue yields
``unclassified`` unless an issue is already the top-ranked class, because a classified
top issue settles the persona whatever the unclassified one would have been.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from operator import attrgetter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from population_synthetic.analysis.utils.tidy_csv import (
    missing_columns,
    parse_int,
    stale_schema_error,
    write_rows,
)

__all__ = [
    "ISSUE_FIELDNAMES",
    "NOT_APPLICABLE",
    "PERSONA_FIELDNAMES",
    "SCHEMA_VERSION",
    "STAGE2_CLASSES",
    "UNCLASSIFIED",
    "Stage2IssueRow",
    "Stage2PersonaRow",
    "class_counts",
    "persona_class",
    "persona_rows_from_issues",
    "read_stage2_issues_csv",
    "reconcile_with_clashes",
    "validate_class_order",
    "write_stage2_issues_csv",
    "write_stage2_personas_csv",
]

#: Bumped whenever a column of either file is added, removed, or re-typed. Stamped by the
#: producer into its combination report as ``stage2_csv_schema_version``.
SCHEMA_VERSION = 1

#: The classes the stage-2 prompt defines (``config/analysis/persona_realism/stage2_prompt.md``).
STAGE2_CLASSES: tuple[str, ...] = (
    "raw_impossible", "label_clash", "ambiguous", "mapping_error", "judge_error",
)
#: An S3 clash stage 2 has not classified (its call failed after every retry, or stage 2
#: is disabled in ``judge.yaml``). A pipeline state, never a stage-2 answer.
UNCLASSIFIED = "unclassified"
#: An S3 clash of a persona with no free text to read (the real SCB reference).
NOT_APPLICABLE = "not_applicable_no_free_text"

_ALL_CLASSES = frozenset((*STAGE2_CLASSES, UNCLASSIFIED, NOT_APPLICABLE))

_REMEDY = (
    "The file is derived from the stage-2 cache; regenerate it with "
    "scripts/analyze/analyze_persona_realism.py --rewrite-artifacts (zero LLM calls)."
)


def validate_class_order(order: Sequence[str], *, where: str) -> tuple[str, ...]:
    """Return *order* as a tuple, raising unless it permutes :data:`STAGE2_CLASSES`."""
    order = tuple(str(c) for c in order)
    if sorted(order) != sorted(STAGE2_CLASSES) or len(set(order)) != len(order):
        raise ValueError(
            f"{where}: the persona-class order must list each stage-2 class exactly once "
            f"({list(STAGE2_CLASSES)}), got {list(order)}"
        )
    return order


def persona_class(classes: Iterable[str], order: Sequence[str]) -> str:
    """The persona-level class of a persona's S3 issue classes (see the module docstring)."""
    classes = list(classes)
    if not classes:
        raise ValueError("persona_class needs at least one issue class")
    unknown = sorted(set(classes) - _ALL_CLASSES)
    if unknown:
        raise ValueError(f"unknown stage-2 class(es) {unknown}")
    if NOT_APPLICABLE in classes:
        if set(classes) != {NOT_APPLICABLE}:
            raise ValueError(
                f"a persona mixes {NOT_APPLICABLE!r} with other classes {sorted(set(classes))}: "
                "one persona cannot both have and lack free text"
            )
        return NOT_APPLICABLE
    known = [c for c in classes if c in STAGE2_CLASSES]
    top = min(known, key=order.index) if known else None
    if UNCLASSIFIED in classes and top != order[0]:
        return UNCLASSIFIED
    return top  # type: ignore[return-value]


@dataclass(frozen=True)
class Stage2IssueRow:
    """One S3 clash, in one round, for one persona, with its stage-2 class.

    ``attr_a``/``attr_b`` are the sorted pair (the per-clash contract's identity).
    ``raw_a``/``raw_b`` are those two attributes' raw answers from the persona's
    ``identity.json`` (empty for the real reference and for an attribute the identity
    does not carry). ``raw_quotes`` is the JSON object of raw answers stage 2 quoted;
    ``reason`` its one sentence; ``legal_fact`` the title of the listed legal fact an
    age-based ``raw_impossible`` rests on, or ``unlisted: <rule>`` for an issue left
    ``ambiguous`` because it rests on a rule the prompt does not list; ``misread_attribute`` the attribute a
    ``mapping_error`` names. All four are empty when stage 2 gave no answer.
    """

    persona_id: str
    round_index: int
    attr_a: str
    attr_b: str
    stage2_class: str
    misread_attribute: str
    legal_fact: str
    reason: str
    raw_a: str
    raw_b: str
    raw_quotes: str


@dataclass(frozen=True)
class Stage2PersonaRow:
    """One persona with >= 1 S3 clash: how many rounds and clashes, and its class."""

    persona_id: str
    n_s3_rounds: int
    n_s3_issues: int
    persona_class: str


ISSUE_FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(Stage2IssueRow))
PERSONA_FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(Stage2PersonaRow))
_ISSUE_GRAIN: tuple[str, ...] = ("persona_id", "round_index", "attr_a", "attr_b")
_issue_key = attrgetter(*_ISSUE_GRAIN)


def _validate_issue_rows(rows: Sequence[Stage2IssueRow], *, path: Path) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        unit = f"persona {row.persona_id!r} round {row.round_index} ({row.attr_a!r}, {row.attr_b!r})"
        if row.stage2_class not in _ALL_CLASSES:
            raise ValueError(f"{path}: {unit} has unknown stage-2 class {row.stage2_class!r}. {_REMEDY}")
        if row.attr_a > row.attr_b:
            raise ValueError(f"{path}: {unit} carries an unsorted attribute pair. {_REMEDY}")
        if row.round_index < 0:
            raise ValueError(f"{path}: {unit} has a negative round_index. {_REMEDY}")
        if row.stage2_class == "mapping_error" and not row.misread_attribute:
            raise ValueError(f"{path}: {unit} is mapping_error but names no misread_attribute. {_REMEDY}")
        key = _issue_key(row)
        if key in seen:
            raise ValueError(f"{path}: two rows share the stage-2 grain key {key!r}. {_REMEDY}")
        seen.add(key)


def write_stage2_issues_csv(rows: Sequence[Stage2IssueRow], path: Path) -> Path:
    """Write the issue-grain file whole, sorted on its grain key (header-only when empty)."""
    ordered = sorted(rows, key=_issue_key)
    _validate_issue_rows(ordered, path=Path(path))
    encoded = [[str(asdict(row)[name]) for name in ISSUE_FIELDNAMES] for row in ordered]
    return write_rows(path, ISSUE_FIELDNAMES, encoded)


def write_stage2_personas_csv(rows: Sequence[Stage2PersonaRow], path: Path) -> Path:
    """Write the persona-grain file whole, sorted by persona id (header-only when empty)."""
    ordered = sorted(rows, key=attrgetter("persona_id"))
    ids = [row.persona_id for row in ordered]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: a persona appears twice in the stage-2 persona rows")
    for row in ordered:
        if row.persona_class not in _ALL_CLASSES:
            raise ValueError(f"{path}: persona {row.persona_id!r} has unknown class {row.persona_class!r}")
    encoded = [[str(asdict(row)[name]) for name in PERSONA_FIELDNAMES] for row in ordered]
    return write_rows(path, PERSONA_FIELDNAMES, encoded)


def persona_rows_from_issues(rows: Sequence[Stage2IssueRow], order: Sequence[str]) -> list[Stage2PersonaRow]:
    """Fold issue rows into one :class:`Stage2PersonaRow` per persona (sorted by id)."""
    by_persona: dict[str, list[Stage2IssueRow]] = {}
    for row in rows:
        by_persona.setdefault(row.persona_id, []).append(row)
    out = []
    for pid in sorted(by_persona):
        issues = by_persona[pid]
        out.append(
            Stage2PersonaRow(
                persona_id=pid,
                n_s3_rounds=len({r.round_index for r in issues}),
                n_s3_issues=len(issues),
                persona_class=persona_class([r.stage2_class for r in issues], order),
            )
        )
    return out


def read_stage2_issues_csv(path: Path) -> list[Stage2IssueRow]:
    """Read the issue-grain file back into typed rows (fail-fast; absent -> FileNotFoundError)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Stage-2 issue CSV not found: {path}")
    rows: list[Stage2IssueRow] = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        missing = missing_columns(header, ISSUE_FIELDNAMES)
        if missing:
            raise stale_schema_error(
                path, label="stage-2 issue CSV", missing=missing, header=header,
                schema_version=SCHEMA_VERSION, fieldnames=ISSUE_FIELDNAMES, remedy=_REMEDY,
            )
        for record in reader:
            unit = f"persona {record.get('persona_id')!r}"
            values: dict[str, Any] = {}
            for name in ISSUE_FIELDNAMES:
                raw = record.get(name)
                if raw is None:
                    raise ValueError(f"{path}: {unit} has no cell for column {name!r}. {_REMEDY}")
                values[name] = raw
            values["round_index"] = parse_int(
                values["round_index"], column="round_index", path=path, unit=unit, remedy=_REMEDY,
            )
            rows.append(Stage2IssueRow(**values))
    _validate_issue_rows(rows, path=path)
    return rows


def reconcile_with_clashes(
    stage2_rows: Sequence[Stage2IssueRow],
    clash_keys: Iterable[tuple[str, int, str, str]],
    *,
    label: str,
) -> None:
    """Raise unless the stage-2 rows cover exactly the S3 clashes *clash_keys* names.

    *clash_keys* is the ``(persona_id, round_index, attr_a, attr_b)`` set of the sibling
    per-clash rows at severity S3.
    """
    have = {_issue_key(r) for r in stage2_rows}
    want = set(clash_keys)
    if have != want:
        extra = sorted(have - want)[:5]
        lacking = sorted(want - have)[:5]
        raise ValueError(
            f"{label}: the stage-2 rows and the S3 clash rows describe different clashes "
            f"(stage-2 only: {extra}; S3 clash only: {lacking}). Both are derived from the "
            f"same verdict cache; regenerate them together. {_REMEDY}"
        )


def class_counts(personas: Mapping[str, str], classes: Sequence[str]) -> dict[str, int]:
    """Count *personas* (``{persona_id: class}``) per class, every class keyed (zeros kept)."""
    counts = {c: 0 for c in classes}
    for cls in personas.values():
        if cls not in counts:
            raise ValueError(f"class {cls!r} is not one of {list(classes)}")
        counts[cls] += 1
    return counts

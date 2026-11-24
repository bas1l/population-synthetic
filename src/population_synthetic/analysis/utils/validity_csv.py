"""validity_csv.py -- shared read/write helpers for the per-combo persona validity CSVs.

Both atomistic validation tasks (``validate_raw`` and ``validate_mapped``) emit one CSV
per combo with a stable leading header ``persona_id, passed, ...`` followed by
task-specific detail columns. ``population_cap`` reads these CSVs to select only the
personas that pass every gate, so the writers and the cap reader must agree on the
format -- that agreement lives here.

The helpers are deliberately format-only: they know nothing about *what* makes a persona
valid, only how a validity verdict is serialized and how the passing ids are read back.
The cell/header/whole-file primitives they are built on are shared with the other tidy
CSV contracts in :mod:`population_synthetic.analysis.utils.tidy_csv`; what stays here is
this format's own rule -- the ``persona_id, passed`` prefix and the lenient truth test
its two independent writers require.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from population_synthetic.analysis.utils.tidy_csv import is_truthy, missing_columns, write_rows

# Every validity CSV starts with these two columns; detail columns follow.
PERSONA_ID_COLUMN = "persona_id"
PASSED_COLUMN = "passed"

# The columns the shared reader needs, whatever detail columns a task appends.
_REQUIRED_COLUMNS = (PERSONA_ID_COLUMN, PASSED_COLUMN)


def write_validity_csv(
    out_path: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
) -> None:
    """Write a validity CSV with ``header`` and ``rows`` (fail-fast on a malformed header).

    ``header`` must begin with ``persona_id, passed`` so the shared reader can locate the
    verdict regardless of the task's detail columns.
    """
    if list(header[:2]) != list(_REQUIRED_COLUMNS):
        raise ValueError(
            f"Validity CSV header must start with {PERSONA_ID_COLUMN!r}, {PASSED_COLUMN!r}; "
            f"got {list(header)!r}."
        )
    write_rows(out_path, header, rows)


def read_passed_ids(csv_path: Path) -> set[str]:
    """Return the set of ``persona_id`` whose ``passed`` column is truthy.

    Raises:
        FileNotFoundError: If the CSV is absent -- the validation gate has not run for
            this combo (fail-fast; no silent empty-set).
        ValueError: If the CSV lacks the required ``persona_id``/``passed`` columns.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Validity CSV not found: {csv_path}. "
            f"Run the validation task that produces it before population_cap."
        )
    passed: set[str] = set()
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if missing_columns(fields, _REQUIRED_COLUMNS):
            raise ValueError(
                f"Validity CSV {csv_path} missing required column(s) "
                f"{PERSONA_ID_COLUMN!r}/{PASSED_COLUMN!r}; header is {fields!r}."
            )
        for row in reader:
            if is_truthy(row[PASSED_COLUMN]):
                passed.add(row[PERSONA_ID_COLUMN])
    return passed


def upsert_summary_row(
    summary_path: Path,
    header: Sequence[str],
    row: Sequence[object],
) -> None:
    """Insert or replace one combo's row in a per-task ``_summary.csv`` (keyed on col 0).

    Per-combo tasks run one invocation per combo, so the folder-level summary must
    accumulate rather than clobber siblings: this reads the existing summary, replaces the
    row whose first cell (the slug) matches ``row[0]`` (else appends), sorts by slug for a
    stable glanceable order, and rewrites the file with ``header``. The first cell of both
    ``header`` and ``row`` is the slug key.
    """
    key = str(row[0])
    rows: list[list[str]] = []
    if summary_path.is_file():
        with open(summary_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # drop the existing header
            rows = [r for r in reader if r]
    new_row = [str(cell) for cell in row]
    for i, existing in enumerate(rows):
        if existing and existing[0] == key:
            rows[i] = new_row
            break
    else:
        rows.append(new_row)
    rows.sort(key=lambda r: r[0])
    write_rows(summary_path, header, rows)

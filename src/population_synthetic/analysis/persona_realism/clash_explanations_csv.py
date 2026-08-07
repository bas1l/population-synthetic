"""clash_explanations_csv.py -- the judge's free text for each clash, as a side file.

A **task-local** sink, deliberately outside the ``persona_realism`` ->
``realism_ranking`` contract. ``{combo}_clashes.csv`` (the contract, see
:mod:`population_synthetic.analysis.utils.realism_clash_csv`) carries the countable
part of a clash -- which axes, which category values, which severity. This file
carries the part that is *not* countable: the sentence the judge wrote. Nothing
downstream reads it, and nothing downstream may: counting explanation text would
require a classifier, and the pipeline counts and ranks only. It exists so a human
reading a driver table can open the rows behind a rank and see what the judge
actually said.

Hence a separate module rather than more columns on the contract row: a column the
aggregator must ignore is a column the aggregator will eventually be asked to use.
Keeping the text in its own file keeps the contract's every column load-bearing, and
keeps this file free to change shape without a schema version -- there is no reader
to break. That is also why it carries no ``SCHEMA_VERSION``: a version number is a
promise to a reader, and this file has none.

Its rows are keyed **identically** to the contract's -- one row per
``(persona_id, round_index, attr_a, attr_b, severity)``, the same sorted pair, the
same within-round dedupe -- so the two files join row-for-row on that key. Both are
derived in one pass from the same verdict cache
(:func:`~population_synthetic.analysis.persona_realism.reduce.clash_rows` and
:func:`~population_synthetic.analysis.persona_realism.reduce.clash_explanation_rows`)
and written under the same ``force`` gate, so they can never be one generation apart.

It is written **whenever its primary is**, including when there is nothing to write:
an empty combination gets a header-only file, so "the judge found no clash" stays
distinguishable from "this combination was never processed" -- the convention the
per-slug miss sidecar in ``map_populations.py`` already established. The hazard is
the same one that file documents (a stale side file read as current), and the
mitigation is the same: it is regenerated in the same block as its primary, never
on its own.

The identity columns (``slug``/``country``/``model``/``strategy``) are **absent** on
purpose. They are constant within a combination, they exist on the contract row only
because the aggregator groups across combinations, and no such grouping happens here
-- the file is read beside its own directory or not at all.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from operator import attrgetter
from pathlib import Path
from typing import Any, Sequence

from population_synthetic.analysis.utils.tidy_csv import write_rows

__all__ = [
    "FIELDNAMES",
    "ClashExplanationRow",
    "write_clash_explanations_csv",
]


@dataclass(frozen=True)
class ClashExplanationRow:
    """The judge's explanation for one clash, in one round, for one persona.

    ``attr_a``/``attr_b`` are the sorted pair and ``round_index`` the 0-based
    position among the persona's **successful** rounds -- the same key the per-clash
    contract row carries, so a reader can join the two files without re-deriving
    anything.

    ``explanation`` is free text, quoted by the CSV writer when it contains a
    separator or a newline. It is provenance for a human, never an input to a
    number.
    """

    persona_id: str
    round_index: int
    attr_a: str
    attr_b: str
    severity: str
    explanation: str


#: Column order == :class:`ClashExplanationRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(ClashExplanationRow))

#: The shared grain: one row per this tuple, in both this file and its primary.
_GRAIN_FIELDS: tuple[str, ...] = ("persona_id", "round_index", "attr_a", "attr_b", "severity")

#: ``row -> tuple`` over :data:`_GRAIN_FIELDS`; the writer's *total* sort key, since a
#: duplicate of it is rejected below.
_sort_key = attrgetter(*_GRAIN_FIELDS)


def write_clash_explanations_csv(rows: Sequence[ClashExplanationRow], path: Path) -> Path:
    """Write *rows* to *path* with the :data:`FIELDNAMES` columns; return *path*.

    Written **whole** (truncating), never appended, and **sorted** on the grain key,
    so the bytes are a function of the row set alone -- the same order-independence
    the primary guarantees, and what lets the two files be compared byte-for-byte
    across runs.

    An empty *rows* writes a header-only file rather than no file at all.

    Raises ``ValueError`` when two rows share the grain key: that would mean this
    file and its primary disagree about the within-round dedupe, and the join between
    them would silently multiply rows.
    """
    ordered = sorted(rows, key=_sort_key)
    seen: set[tuple[Any, ...]] = set()
    for row in ordered:
        key = _sort_key(row)
        if key in seen:
            raise ValueError(
                f"{Path(path)}: two explanation rows share the clash grain key {key!r}. "
                "The grain is one row per (persona, round, sorted attribute pair, "
                "severity) -- the same key the per-clash CSV uses, so a duplicate here "
                "would break the join between the two files."
            )
        seen.add(key)
    encoded = []
    for row in ordered:
        record = asdict(row)
        encoded.append([str(record[name]) for name in FIELDNAMES])
    return write_rows(path, FIELDNAMES, encoded)

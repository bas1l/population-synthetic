"""Unit tests for the per-clash tidy CSV -- the finer half of the persona_realism ->
realism_ranking contract.

This file exists so a reader of a severity heatmap can learn *what* clashed, which means
the rows have to survive a write/read round trip with their types and, crucially, their
*absences* intact: an unresolved clash has no category values, and an empty cell that
quietly became a value would fabricate the single most actionable fact the judge
produces. The reconciliation check against the sibling per-persona file is tested here
too, because it is what makes joining the two files safe.
"""

from __future__ import annotations

import csv
import dataclasses
import random

import pytest

from population_synthetic.analysis.utils.realism_clash_csv import (
    FIELDNAMES,
    RealismClashRow,
    read_realism_clashes_csv,
    write_realism_clashes_csv,
)


def _row(**overrides) -> RealismClashRow:
    base = dict(
        persona_id="persona_00000",
        slug="swedish_02_all_pick_v2_claude_haiku",
        country="swedish_02",
        model="claude_haiku",
        strategy="all_pick_v2",
        is_real_reference=False,
        round_index=0,
        attr_a="employment_status",
        attr_b="employment_type",
        value_a="Student",
        value_b="Permanent Full-time",
        severity="S3",
        unresolved=False,
    )
    base.update(overrides)
    return RealismClashRow(**base)


def test_round_trip_preserves_types(tmp_path):
    path = write_realism_clashes_csv([_row()], tmp_path / "c_clashes.csv")
    (back,) = read_realism_clashes_csv(path)
    assert back == _row()
    assert isinstance(back.round_index, int)
    assert isinstance(back.is_real_reference, bool)
    assert isinstance(back.unresolved, bool)


def test_fieldnames_match_the_dataclass_field_order():
    assert FIELDNAMES == tuple(f.name for f in dataclasses.fields(RealismClashRow))


def test_the_column_order_is_the_published_contract():
    """Pinned literally: the column order IS the contract, so a reorder must be seen."""
    assert FIELDNAMES == (
        "persona_id", "slug", "country", "model", "strategy", "is_real_reference",
        "round_index", "attr_a", "attr_b", "value_a", "value_b", "severity", "unresolved",
    )


def test_the_real_competitor_round_trips_with_empty_model_and_strategy(tmp_path):
    """SCB is an ordinary competitor here: flagged, not a model x method cell."""
    row = _row(slug="real_swedish_02", model="", strategy="", is_real_reference=True)
    path = write_realism_clashes_csv([row], tmp_path / "c_clashes.csv")
    (back,) = read_realism_clashes_csv(path)
    assert back.is_real_reference is True
    assert (back.model, back.strategy) == ("", "")


# --------------------------------------------------------------------------- #
# absence: an unresolved clash has no values, and never acquires any           #
# --------------------------------------------------------------------------- #


def test_unresolved_row_keeps_its_values_empty_on_disk_and_back(tmp_path):
    """A judge-hallucinated attribute name yields a real clash with unknown values.

    Coercing the empty cells to anything -- a placeholder, the attribute name, the other
    side's value -- would invent a category pair that no persona ever held.
    """
    row = _row(attr_b="favourite_colour", value_a="", value_b="", unresolved=True)
    path = write_realism_clashes_csv([row], tmp_path / "c_clashes.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        record = next(csv.DictReader(fh))
    assert record["value_a"] == "" and record["value_b"] == ""
    (back,) = read_realism_clashes_csv(path)
    assert back.value_a == "" and back.value_b == ""
    assert back.unresolved is True


def test_unresolved_row_carrying_a_value_is_rejected_by_the_writer(tmp_path):
    with pytest.raises(ValueError, match="unresolved"):
        write_realism_clashes_csv(
            [_row(value_a="Student", value_b="", unresolved=True)], tmp_path / "c_clashes.csv"
        )


def test_a_resolved_row_keeps_its_values(tmp_path):
    """The complement: real values must not be dropped on the way through."""
    path = write_realism_clashes_csv([_row()], tmp_path / "c_clashes.csv")
    (back,) = read_realism_clashes_csv(path)
    assert (back.value_a, back.value_b) == ("Student", "Permanent Full-time")
    assert back.unresolved is False


# --------------------------------------------------------------------------- #
# determinism                                                                  #
# --------------------------------------------------------------------------- #


def _spread() -> list[RealismClashRow]:
    return [
        _row(),
        _row(severity="S2"),
        _row(round_index=1),
        _row(attr_a="age", attr_b="income_bracket", value_a="18-24", value_b="High"),
        _row(persona_id="persona_00001"),
    ]


def test_write_is_whole_file_so_n_writes_equal_one(tmp_path):
    path = tmp_path / "c_clashes.csv"
    write_realism_clashes_csv(_spread(), path)
    first = path.read_bytes()
    write_realism_clashes_csv(_spread(), path)
    assert path.read_bytes() == first           # truncating, never appending
    assert len(read_realism_clashes_csv(path)) == len(_spread())


def test_shuffling_the_input_order_changes_nothing(tmp_path):
    """The bytes are a function of the row SET -- the order-independence the aggregator
    relies on when the same combination is regenerated from a differently-ordered walk."""
    ordered = write_realism_clashes_csv(_spread(), tmp_path / "a_clashes.csv").read_bytes()
    shuffled_rows = _spread()
    random.Random(20260807).shuffle(shuffled_rows)
    shuffled = write_realism_clashes_csv(shuffled_rows, tmp_path / "b_clashes.csv").read_bytes()
    assert shuffled == ordered


def test_rows_are_emitted_in_the_grain_sort_order(tmp_path):
    path = write_realism_clashes_csv(_spread(), tmp_path / "c_clashes.csv")
    back = read_realism_clashes_csv(path)
    keys = [(r.persona_id, r.round_index, r.attr_a, r.attr_b, r.severity) for r in back]
    assert keys == sorted(keys)


def test_two_rows_sharing_the_grain_key_raise(tmp_path):
    """The grain is one row per (persona, round, pair, severity); a duplicate would
    double-count a round and break the reconciliation invariant silently."""
    with pytest.raises(ValueError, match="grain"):
        write_realism_clashes_csv([_row(), _row()], tmp_path / "c_clashes.csv")


def test_an_unsorted_attribute_pair_is_rejected(tmp_path):
    """Canonicalisation happens upstream; this contract enforces it, so one clash can
    never rank twice under two spellings of the same pair."""
    with pytest.raises(ValueError, match="sorted"):
        write_realism_clashes_csv(
            [_row(attr_a="employment_type", attr_b="employment_status")],
            tmp_path / "c_clashes.csv",
        )


def test_an_unknown_severity_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="S4"):
        write_realism_clashes_csv([_row(severity="S4")], tmp_path / "c_clashes.csv")


# --------------------------------------------------------------------------- #
# present-but-empty vs absent                                                  #
# --------------------------------------------------------------------------- #


def test_header_only_file_is_a_clean_combination_not_a_missing_one(tmp_path):
    path = write_realism_clashes_csv([], tmp_path / "c_clashes.csv")
    assert path.is_file()
    assert path.read_text(encoding="utf-8").splitlines() == [",".join(FIELDNAMES)]
    assert read_realism_clashes_csv(path) == []


def test_missing_file_raises_pointing_at_the_producing_script(tmp_path):
    with pytest.raises(FileNotFoundError, match="analyze_persona_realism.py"):
        read_realism_clashes_csv(tmp_path / "absent_clashes.csv")


# --------------------------------------------------------------------------- #
# schema strictness                                                            #
# --------------------------------------------------------------------------- #


def _drop_column(path, column: str) -> None:
    """Column surgery: rewrite *path* without *column*, simulating an older schema."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    keep = [i for i, name in enumerate(rows[0]) if name != column]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([[row[i] for i in keep] for row in rows])


def test_a_file_missing_a_column_raises_naming_rewrite_artifacts(tmp_path):
    path = write_realism_clashes_csv([_row()], tmp_path / "c_clashes.csv")
    _drop_column(path, "value_a")
    with pytest.raises(ValueError, match="--rewrite-artifacts"):
        read_realism_clashes_csv(path)
    _drop_column(path, "value_b")  # the message must also name what is missing
    with pytest.raises(ValueError, match="value_b"):
        read_realism_clashes_csv(path)


def test_an_unparseable_round_index_raises_naming_the_persona_and_column(tmp_path):
    path = write_realism_clashes_csv([_row()], tmp_path / "c_clashes.csv")
    path.write_text(
        path.read_text(encoding="utf-8").replace(",false,0,", ",false,first,"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="persona_00000"):
        read_realism_clashes_csv(path)
    with pytest.raises(ValueError, match="round_index"):
        read_realism_clashes_csv(path)


# --------------------------------------------------------------------------- #
# reconciliation against the sibling per-persona CSV                           #
# --------------------------------------------------------------------------- #


def test_reconciliation_passes_when_the_two_files_agree(tmp_path):
    rows = [
        _row(),                                  # persona_00000, pair 1, S3
        _row(round_index=1),                     # same clash, second round -> same clash
        _row(severity="S2"),                     # persona_00000, pair 1, S2
        _row(persona_id="persona_00001"),        # persona_00001, pair 1, S3
    ]
    path = write_realism_clashes_csv(rows, tmp_path / "c_clashes.csv")
    back = read_realism_clashes_csv(path, expected_counts={"S3": 2, "S2": 1, "S1": 0})
    assert len(back) == 4                        # four rows ...
    # ... but only three distinct clashes, because rounds collapse.


def test_reconciliation_mismatch_raises_naming_both_files_and_the_remedy(tmp_path):
    personas_csv = tmp_path / "c_personas.csv"
    path = write_realism_clashes_csv([_row()], tmp_path / "c_clashes.csv")
    with pytest.raises(ValueError) as excinfo:
        read_realism_clashes_csv(
            path,
            expected_counts={"S3": 4, "S2": 0, "S1": 0},
            expected_counts_source=personas_csv,
        )
    message = str(excinfo.value)
    assert str(path) in message
    assert str(personas_csv) in message
    assert "--rewrite-artifacts" in message
    assert "clash_count_s3" in message


def test_an_omitted_level_is_asserted_zero_rather_than_skipped(tmp_path):
    """A level missing from the counts must not silently skip its invariant."""
    path = write_realism_clashes_csv([_row(severity="S1", value_b="Retired")], tmp_path / "c.csv")
    with pytest.raises(ValueError, match="S1"):
        read_realism_clashes_csv(path, expected_counts={"S3": 0, "S2": 0})


def test_an_unknown_expected_level_raises(tmp_path):
    path = write_realism_clashes_csv([], tmp_path / "c_clashes.csv")
    with pytest.raises(ValueError, match="S9"):
        read_realism_clashes_csv(path, expected_counts={"S3": 0, "S2": 0, "S1": 0, "S9": 1})


def test_unresolved_clashes_still_count_toward_reconciliation(tmp_path):
    """An unresolved clash is a real clash with unknown values -- the sibling file counts
    it, so this file must too, or the two can never agree."""
    rows = [_row(attr_b="favourite_colour", value_a="", value_b="", unresolved=True)]
    path = write_realism_clashes_csv(rows, tmp_path / "c_clashes.csv")
    assert len(read_realism_clashes_csv(path, expected_counts={"S3": 1, "S2": 0, "S1": 0})) == 1


def test_multi_round_rows_collapse_to_one_distinct_clash(tmp_path):
    """Exercises the round dimension the live n_rounds=1 data never reaches."""
    rows = [_row(round_index=i) for i in range(3)]
    path = write_realism_clashes_csv(rows, tmp_path / "c_clashes.csv")
    back = read_realism_clashes_csv(path, expected_counts={"S3": 1, "S2": 0, "S1": 0})
    assert [r.round_index for r in back] == [0, 1, 2]

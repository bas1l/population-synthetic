"""Unit tests for the per-persona tidy CSV -- the persona_realism -> realism_ranking contract.

The whole point of this file format is that the expensive LLM judging is cached once and
read back many times, so the read side has to be strict: a column that silently changes
type, or an empty cell quietly becoming ``0.0``, would corrupt every statistic computed
downstream while leaving the file looking fine.
"""

from __future__ import annotations

import csv

import pytest

from population_synthetic.analysis.utils.realism_csv import (
    FIELDNAMES,
    RealismPersonaRow,
    read_realism_personas_csv,
    write_realism_personas_csv,
)


def _row(**overrides) -> RealismPersonaRow:
    base = dict(
        persona_id="persona_00000",
        slug="swedish_all_pick_claude_haiku",
        country="swedish",
        model="claude_haiku",
        strategy="all_pick",
        is_real_reference=False,
        n_rounds_attempted=3,
        n_rounds_successful=2,
        can_exist_true_votes=2,
        can_exist_majority=True,
        typicality_mean=6.5,
        typicality_sd=0.7071067811865476,
        typicality_rounds=(6, 7),
        max_severity="",
        clash_count=0,
    )
    base.update(overrides)
    return RealismPersonaRow(**base)


def test_round_trip_preserves_types(tmp_path):
    path = write_realism_personas_csv([_row()], tmp_path / "c_personas.csv")
    (back,) = read_realism_personas_csv(path)
    original = _row()
    assert back == original
    # Counts stay ints across the round trip -- not floats, not strings.
    for field in ("n_rounds_attempted", "n_rounds_successful", "can_exist_true_votes",
                  "clash_count"):
        assert isinstance(getattr(back, field), int)
    assert isinstance(back.is_real_reference, bool)
    assert isinstance(back.can_exist_majority, bool)


def test_absent_typicality_stays_absent_and_never_becomes_zero(tmp_path):
    """A persona judged impossible in every round has NO typicality.

    Reading it back as ``0.0`` would claim the judge rated it the least typical person
    possible, which is a strong and entirely fabricated statement.
    """
    row = _row(typicality_mean=None, typicality_sd=None, typicality_rounds=(None, None),
               can_exist_majority=False, can_exist_true_votes=0, max_severity="S3",
               clash_count=2)
    path = write_realism_personas_csv([row], tmp_path / "c_personas.csv")
    (back,) = read_realism_personas_csv(path)
    assert back.typicality_mean is None
    assert back.typicality_sd is None
    assert back.typicality_rounds == (None, None)
    # ... and the cell really is empty on disk, not the string "None".
    with open(path, newline="", encoding="utf-8") as fh:
        record = next(csv.DictReader(fh))
    assert record["typicality_mean"] == ""


def test_a_genuine_zero_typicality_survives_as_zero(tmp_path):
    """The complement of the previous test: 0.0 is a real rating and must not go empty."""
    path = write_realism_personas_csv(
        [_row(typicality_mean=0.0, typicality_rounds=(0, 0))], tmp_path / "c_personas.csv"
    )
    (back,) = read_realism_personas_csv(path)
    assert back.typicality_mean == 0.0
    assert back.typicality_rounds == (0, 0)


def test_mixed_round_series_keeps_the_gap_positionally(tmp_path):
    """An impossible round sits inside the series as a gap, not as a dropped element."""
    path = write_realism_personas_csv(
        [_row(typicality_rounds=(6, None, 8))], tmp_path / "c_personas.csv"
    )
    (back,) = read_realism_personas_csv(path)
    assert back.typicality_rounds == (6, None, 8)


def test_write_is_whole_file_so_n_writes_equal_one(tmp_path):
    path = tmp_path / "c_personas.csv"
    write_realism_personas_csv([_row(), _row(persona_id="persona_00001")], path)
    first = path.read_bytes()
    write_realism_personas_csv([_row(), _row(persona_id="persona_00001")], path)
    assert path.read_bytes() == first          # truncating, never appending
    assert len(read_realism_personas_csv(path)) == 2


def test_missing_column_raises_naming_the_file(tmp_path):
    path = tmp_path / "c_personas.csv"
    write_realism_personas_csv([_row()], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [i for i, name in enumerate(FIELDNAMES) if name != "clash_count"]
    trimmed = [",".join(line.split(",")[i] for i in kept) for line in lines]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clash_count"):
        read_realism_personas_csv(path)


def test_unparseable_count_raises_naming_the_persona_and_column(tmp_path):
    path = tmp_path / "c_personas.csv"
    write_realism_personas_csv([_row()], path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(",2,2,", ",two,2,"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="persona_00000"):
        read_realism_personas_csv(path)


def test_row_count_disagreement_with_the_report_raises(tmp_path):
    path = write_realism_personas_csv([_row()], tmp_path / "c_personas.csv")
    with pytest.raises(ValueError, match="n_personas=4"):
        read_realism_personas_csv(path, expected_rows=4)


def test_missing_file_raises_pointing_at_the_producing_script(tmp_path):
    with pytest.raises(FileNotFoundError, match="analyze_persona_realism.py"):
        read_realism_personas_csv(tmp_path / "absent_personas.csv")


def test_fieldnames_match_the_dataclass_field_order():
    import dataclasses

    assert FIELDNAMES == tuple(f.name for f in dataclasses.fields(RealismPersonaRow))

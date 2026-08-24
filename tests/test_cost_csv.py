"""Unit tests for the tidy cost-efficiency CSV contract.

The property that carries the most weight here is the one the sibling schemas share and
that this file exists to pin: an **empty cell reads back as ``None``, never ``0.0``**. A
zero cost is a claim -- the run was unmetered and free at the meter -- and an absent cost
is the refusal to make any claim. Collapsing them turns every untelemetered run into an
apparent bargain.

The two provenance columns are checked for existence as well as for round-trip, because
they are the columns a reader of the table alone depends on: ``cost_basis`` (which
persona population the dollars were counted over) and ``unmetered`` (whether the zero is
measured or merely unpriced).
"""

from __future__ import annotations

import csv

import pytest

from population_synthetic.analysis.utils.cost_csv import (
    FIELDNAMES,
    SCHEMA_VERSION,
    CostRow,
    decode_pricing_flags,
    encode_pricing_flags,
    read_cost_csv,
    write_cost_csv,
)


def _row(**overrides) -> CostRow:
    base = dict(
        slug="swedish_02_all_pick_v2_claude_haiku",
        country="swedish_02",
        model="claude_haiku",
        strategy="all_pick_v2",
        overall_tv_similarity=0.81,
        n_scored=100,
        generated=150,
        clean=120,
        selected=100,
        generation_multiplier=1.25,
        n_calls=450,
        input_tokens=1_000,
        output_tokens=2_000,
        total_tokens=3_000,
        total_cost_usd=1.5,
        cost_per_usable_persona=0.0125,
        cost_per_100_usable_personas=1.25,
        cost_basis="generated_pool_01_raw",
        unmetered=False,
        has_token_data=True,
        price_in=1.0,
        price_out=10.0,
        pricing_flags="",
    )
    base.update(overrides)
    return CostRow(**base)


def test_fieldnames_match_dataclass_order() -> None:
    assert FIELDNAMES[0] == "slug"
    assert "cost_basis" in FIELDNAMES
    assert "unmetered" in FIELDNAMES
    assert len(set(FIELDNAMES)) == len(FIELDNAMES)


def test_schema_version_is_declared() -> None:
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 1


def test_round_trip_preserves_every_field(tmp_path) -> None:
    row = _row()
    path = write_cost_csv([row], tmp_path / "c.csv")
    assert read_cost_csv(path) == [row]


def test_empty_optional_cell_reads_back_as_none_never_zero(tmp_path) -> None:
    row = _row(
        total_cost_usd=None,
        cost_per_usable_persona=None,
        cost_per_100_usable_personas=None,
        generation_multiplier=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        has_token_data=False,
    )
    path = write_cost_csv([row], tmp_path / "c.csv")

    with open(path, newline="", encoding="utf-8") as fh:
        raw = next(csv.DictReader(fh))
    for column in ("total_cost_usd", "cost_per_usable_persona", "cost_per_100_usable_personas",
                   "generation_multiplier",
                   "input_tokens", "output_tokens", "total_tokens"):
        assert raw[column] == "", column

    back = read_cost_csv(path)[0]
    for column in ("total_cost_usd", "cost_per_usable_persona", "cost_per_100_usable_personas",
                   "generation_multiplier",
                   "input_tokens", "output_tokens", "total_tokens"):
        value = getattr(back, column)
        assert value is None, column
        assert value != 0.0


def test_measured_zero_survives_as_zero_not_none(tmp_path) -> None:
    # The unmetered case: a MEASURED 0.0 must stay 0.0, or every local model becomes
    # indistinguishable from an unpriced one.
    row = _row(total_cost_usd=0.0, cost_per_usable_persona=0.0,
               cost_per_100_usable_personas=0.0, unmetered=True,
               price_in=0.0, price_out=0.0)
    back = read_cost_csv(write_cost_csv([row], tmp_path / "c.csv"))[0]
    assert back.total_cost_usd == 0.0
    assert back.cost_per_usable_persona == 0.0
    assert back.cost_per_100_usable_personas == 0.0
    assert back.unmetered is True


def test_counts_round_trip_as_ints(tmp_path) -> None:
    back = read_cost_csv(write_cost_csv([_row()], tmp_path / "c.csv"))[0]
    for column in ("n_scored", "generated", "clean", "selected", "n_calls",
                   "input_tokens", "output_tokens", "total_tokens"):
        assert isinstance(getattr(back, column), int), column


def test_pricing_flags_round_trip() -> None:
    assert decode_pricing_flags(encode_pricing_flags(("VERIFY", "effective/discounted"))) == (
        "VERIFY", "effective/discounted",
    )
    # An empty cell is a positive statement that the row carries no caveat.
    assert decode_pricing_flags("") == ()


def test_write_is_truncating_not_appending(tmp_path) -> None:
    path = tmp_path / "c.csv"
    write_cost_csv([_row(), _row(slug="b")], path)
    write_cost_csv([_row()], path)
    assert len(read_cost_csv(path)) == 1


def test_missing_column_raises_naming_the_remedy(tmp_path) -> None:
    path = write_cost_csv([_row()], tmp_path / "c.csv")
    text = path.read_text(encoding="utf-8").splitlines()
    header = text[0].split(",")
    drop = header.index("cost_basis")
    path.write_text(
        "\n".join(
            ",".join(c for i, c in enumerate(line.split(",")) if i != drop) for line in text
        ) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cost_basis"):
        read_cost_csv(path)


def test_required_measurement_left_empty_raises(tmp_path) -> None:
    path = write_cost_csv([_row()], tmp_path / "c.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    cells = lines[1].split(",")
    cells[header.index("overall_tv_similarity")] = ""
    path.write_text(lines[0] + "\n" + ",".join(cells) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overall_tv_similarity"):
        read_cost_csv(path)


def test_expected_rows_mismatch_raises(tmp_path) -> None:
    path = write_cost_csv([_row()], tmp_path / "c.csv")
    with pytest.raises(ValueError, match="expects 2"):
        read_cost_csv(path, expected_rows=2)


def test_absent_file_raises_naming_the_producer(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="analyze_cost_efficiency.py"):
        read_cost_csv(tmp_path / "nope.csv")

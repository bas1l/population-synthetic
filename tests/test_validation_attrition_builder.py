"""Unit tests for the ``validation_attrition`` builder and its tidy CSV contract.

Two things are pinned here, and nothing else: the arithmetic of the two rates
(including every denominator that can be zero), and the round-trip of the schema that
carries them. The builder is pure, so no test in this file touches the disk except the
round-trip ones, which write into ``tmp_path``.

The distinction the whole file turns on is **absent is not zero**. An undefined rate is
``None`` and an empty cell; ``0.0`` is a measurement (a pool was generated and none of
it survived) and infinity is not a value at all. A rate that degraded to either would
still plot, still sort and still average, which is why the degenerate cases are tested
one by one rather than as a single "handles edge cases" assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from population_synthetic.analysis.utils.attrition_csv import (
    FIELDNAMES,
    SCHEMA_VERSION,
    AttritionRow,
    read_attrition_csv,
    write_attrition_csv,
)
from population_synthetic.analysis.validation_attrition.builder import (
    build_document,
    build_rows,
    generation_multiplier,
    retention_rate,
)
from population_synthetic.analysis.validation_attrition.loader import (
    AttritionRecord,
    AttritionSources,
)

_COUNTRY = "swedish"


def _record(
    slug: str,
    *,
    generated: int,
    raw_valid: int | None = None,
    mapped_valid: int | None = None,
    clean: int,
    selected: int = 100,
    requested_n: int = 100,
    excluded: bool = False,
    exclusion_reason: str = "",
    had_surplus: bool = True,
    model: str = "claude_haiku",
    strategy: str = "all_pick",
) -> AttritionRecord:
    """One loaded record. The two intermediate gate counts default to the funnel bounds."""
    return AttritionRecord(
        slug=slug,
        country=_COUNTRY,
        model=model,
        strategy=strategy,
        requested_n=requested_n,
        generated=generated,
        raw_valid=generated if raw_valid is None else raw_valid,
        mapped_valid=clean if mapped_valid is None else mapped_valid,
        clean=clean,
        selected=selected,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        had_surplus=had_surplus,
    )


def _sources(tmp_path: Path) -> AttritionSources:
    return AttritionSources(
        cap_index=tmp_path / "cap_index.json",
        validate_raw_summary=tmp_path / "raw_summary.csv",
        validate_mapped_summary=tmp_path / "mapped_summary.csv",
    )


def _row(**overrides: object) -> AttritionRow:
    """A complete row; ``overrides`` replaces named fields."""
    base = dict(
        slug=f"{_COUNTRY}_all_pick_claude_haiku",
        country=_COUNTRY,
        model="claude_haiku",
        strategy="all_pick",
        requested_n=100,
        generated=150,
        raw_valid=150,
        mapped_valid=120,
        clean=120,
        selected=100,
        retention_rate=0.8,
        generation_multiplier=1.25,
        excluded=False,
        exclusion_reason="",
        had_surplus=True,
    )
    base.update(overrides)
    return AttritionRow(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# the two rates                                                                 #
# --------------------------------------------------------------------------- #


def test_hand_computed_funnel() -> None:
    """Known counts in, known rates out. 200 generated, 50 usable."""
    assert retention_rate(200, 50) == pytest.approx(0.25)
    assert generation_multiplier(200, 50) == pytest.approx(4.0)


def test_excluded_combination_still_yields_both_rates() -> None:
    """The degenerate case the multiplier's denominator was chosen for.

    150 generated, 9 clean, 0 selected. ``generated / selected`` would divide by zero;
    ``generated / clean`` is 16.67 -- the number that says this arm wasted 16 personas
    for every usable one.
    """
    record = _record(
        "s", generated=150, raw_valid=150, mapped_valid=9, clean=9,
        selected=0, excluded=True, exclusion_reason="only 9 clean persona(s)", had_surplus=False,
    )

    (row,) = build_rows([record])

    assert row.selected == 0
    assert row.retention_rate == pytest.approx(0.06)
    assert row.generation_multiplier == pytest.approx(150 / 9)
    assert row.excluded is True


def test_zero_clean_over_a_real_pool_keeps_retention_a_measured_zero() -> None:
    """Nothing survived a pool of 150: retention is a real ``0.0``, the multiplier absent.

    The two halves are deliberately asymmetric, and only one denominator is zero here.
    ``0/150`` is the strongest fidelity claim this artifact can make about a
    combination -- it generated a pool and kept none of it -- and reporting it as
    absent would erase exactly that finding. The multiplier's denominator *is* zero, so
    it is undefined. Absent and zero are different facts, and a combination that
    generated nothing (below) is a third.
    """
    (row,) = build_rows([_record("s", generated=150, mapped_valid=0, clean=0, selected=0)])

    assert row.retention_rate == pytest.approx(0.0)
    assert row.generation_multiplier is None


def test_zero_generated_makes_both_rates_absent() -> None:
    """An empty pool supports no rate claim at all -- and never raises."""
    (row,) = build_rows([_record("s", generated=0, raw_valid=0, mapped_valid=0, clean=0, selected=0)])

    assert row.retention_rate is None
    assert row.generation_multiplier is None


def test_rates_are_never_infinite() -> None:
    """The undefined multiplier is ``None``, not ``inf`` -- ``inf`` would still plot."""
    assert generation_multiplier(150, 0) is None
    assert retention_rate(0, 0) is None


def test_the_row_carries_the_counts_its_rates_are_quotients_of() -> None:
    """Guide 03 sect. 4: a rate never travels without its denominator."""
    (row,) = build_rows([_record("s", generated=150, mapped_valid=120, clean=120)])

    assert row.retention_rate == pytest.approx(row.clean / row.generated)
    assert row.generation_multiplier == pytest.approx(row.generated / row.clean)


# --------------------------------------------------------------------------- #
# row assembly                                                                  #
# --------------------------------------------------------------------------- #


def test_rows_are_sorted_by_slug() -> None:
    """Sorted, not index-ordered, so two runs write byte-identical files."""
    records = [
        _record("swedish_z", generated=150, clean=120),
        _record("swedish_a", generated=150, clean=120),
    ]

    assert [row.slug for row in build_rows(records)] == ["swedish_a", "swedish_z"]


def test_every_loaded_field_reaches_the_row() -> None:
    record = _record(
        "s", generated=549, raw_valid=488, mapped_valid=132, clean=132,
        selected=100, model="gemini_flash", strategy="all_generate_pick",
    )

    (row,) = build_rows([record])

    assert (row.model, row.strategy) == ("gemini_flash", "all_generate_pick")
    assert (row.generated, row.raw_valid, row.mapped_valid, row.clean) == (549, 488, 132, 132)


# --------------------------------------------------------------------------- #
# the JSON document                                                             #
# --------------------------------------------------------------------------- #


def test_document_reports_withdrawals_separately(tmp_path: Path) -> None:
    """The only artifact where a withdrawn combination appears; it appears twice."""
    records = [
        _record("swedish_a", generated=150, clean=120),
        _record(
            "swedish_b", generated=150, mapped_valid=9, clean=9, selected=0,
            excluded=True, exclusion_reason="only 9 clean persona(s)", had_surplus=False,
        ),
    ]

    document = build_document(records, country=_COUNTRY, skipped=[], sources=_sources(tmp_path))

    assert document["n_combinations"] == 2
    assert document["n_excluded"] == 1
    assert [e["slug"] for e in document["excluded_combinations"]] == ["swedish_b"]
    assert document["excluded_combinations"][0]["reason"] == "only 9 clean persona(s)"
    assert [c["excluded"] for c in document["combinations"]] == [False, True]


def test_document_totals_pool_the_counts_not_the_rates(tmp_path: Path) -> None:
    """A pooled rate is a count-weighted mean, not the mean of two per-combo rates."""
    records = [
        _record("swedish_a", generated=100, clean=100),
        _record("swedish_b", generated=900, clean=100),
    ]

    totals = build_document(records, country=_COUNTRY, skipped=[], sources=_sources(tmp_path))["totals"]

    assert totals["generated"] == 1000
    assert totals["clean"] == 200
    assert totals["retention_rate"] == pytest.approx(0.2)  # not (1.0 + 1/9) / 2
    assert totals["generation_multiplier"] == pytest.approx(5.0)


def test_document_carries_skips_and_source_paths(tmp_path: Path) -> None:
    """What was dropped is reported, and every number is retraceable to a file."""
    sources = _sources(tmp_path)

    document = build_document(
        [_record("swedish_a", generated=150, clean=120)],
        country=_COUNTRY,
        skipped=[("swedish_b", "no row in validate_mapped/_summary.csv")],
        sources=sources,
    )

    assert document["skipped_combinations"] == [
        {"slug": "swedish_b", "reason": "no row in validate_mapped/_summary.csv"}
    ]
    assert document["provenance"]["consumed_artifacts"] == [
        str(sources.cap_index),
        str(sources.validate_raw_summary),
        str(sources.validate_mapped_summary),
    ]
    assert document["schema_version"] == SCHEMA_VERSION


def test_document_carries_no_timestamp(tmp_path: Path) -> None:
    """Byte-reproducible for a fixed input; the driver stamps a time if it wants one."""
    records = [_record("swedish_a", generated=150, clean=120)]
    sources = _sources(tmp_path)

    first = build_document(records, country=_COUNTRY, skipped=[], sources=sources)
    second = build_document(records, country=_COUNTRY, skipped=[], sources=sources)

    assert "generated_at" not in first
    assert first == second


# --------------------------------------------------------------------------- #
# the tidy CSV contract                                                         #
# --------------------------------------------------------------------------- #


def test_fieldnames_follow_the_dataclass_field_order() -> None:
    """One source of truth for the column order."""
    assert FIELDNAMES[:4] == ("slug", "country", "model", "strategy")
    assert set(FIELDNAMES) == {f for f in AttritionRow.__dataclass_fields__}


def test_round_trip_preserves_every_typed_cell(tmp_path: Path) -> None:
    rows = [
        _row(),
        _row(slug="swedish_b", excluded=True, exclusion_reason="only 9 clean", had_surplus=False),
    ]
    path = tmp_path / "swedish_attrition.csv"

    write_attrition_csv(rows, path)

    assert read_attrition_csv(path, expected_rows=2) == rows


def test_an_undefined_rate_round_trips_as_none_never_zero(tmp_path: Path) -> None:
    """The load-bearing cell: an empty rate must not come back as the lowest value."""
    path = tmp_path / "swedish_attrition.csv"
    write_attrition_csv([_row(retention_rate=None, generation_multiplier=None)], path)

    assert path.read_text(encoding="utf-8").splitlines()[1].count(",,") >= 1
    (row,) = read_attrition_csv(path)
    assert row.retention_rate is None
    assert row.generation_multiplier is None


def test_writing_twice_is_indistinguishable_from_writing_once(tmp_path: Path) -> None:
    """``write_rows`` truncates, so the artifact is idempotent."""
    path = tmp_path / "swedish_attrition.csv"
    rows = build_rows([_record("swedish_a", generated=150, clean=120)])

    write_attrition_csv(rows, path)
    first = path.read_bytes()
    write_attrition_csv(rows, path)

    assert path.read_bytes() == first


def test_a_file_missing_a_column_raises_naming_the_remedy(tmp_path: Path) -> None:
    """A tolerated v0 file would report every new column as absent or zero."""
    path = tmp_path / "swedish_attrition.csv"
    write_attrition_csv([_row()], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [i for i, name in enumerate(FIELDNAMES) if name != "excluded"]
    trimmed = [",".join([line.split(",")[i] for i in kept]) for line in lines]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        read_attrition_csv(path)

    message = str(excinfo.value)
    assert "'excluded'" in message
    assert f"schema v{SCHEMA_VERSION}" in message
    assert "analyze_validation_attrition.py --force" in message


def test_a_row_count_disagreement_raises(tmp_path: Path) -> None:
    """The CSV and the gate index must describe the same set of combinations."""
    path = tmp_path / "swedish_attrition.csv"
    write_attrition_csv([_row()], path)

    with pytest.raises(ValueError, match="holds 1 combination row"):
        read_attrition_csv(path, expected_rows=2)


def test_a_malformed_count_cell_raises_naming_the_column(tmp_path: Path) -> None:
    path = tmp_path / "swedish_attrition.csv"
    write_attrition_csv([_row()], path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(",150,", ",one-fifty,", 1), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="not an integer count"):
        read_attrition_csv(path)


def test_an_absent_csv_raises_naming_the_producing_script(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="analyze_validation_attrition.py"):
        read_attrition_csv(tmp_path / "absent.csv")

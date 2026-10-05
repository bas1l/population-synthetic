"""realism_ranking's two reporting-only stage-2 blocks: the impossible breakdown and the worst-clash split."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.realism_ranking import builder
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord
from population_synthetic.analysis.utils.realism_csv import RealismPersonaRow
from population_synthetic.analysis.utils.realism_stage2_csv import Stage2IssueRow

_ORDER = ["raw_impossible", "label_clash", "ambiguous", "mapping_error", "judge_error"]
_SPLIT_CONFIG = PROJECT_ROOT / "config" / "analysis" / "realism_ranking" / "worst_clash_split.yaml"


def _persona(pid, slug, worst, *, impossible):
    return RealismPersonaRow(
        persona_id=pid, slug=slug, country="swedish_02", model="m", strategy="s",
        is_real_reference=slug.startswith("real_"), n_rounds_attempted=1, n_rounds_successful=1,
        can_exist_true_votes=0 if impossible else 1, can_exist_majority=not impossible,
        typicality_mean=None if impossible else 7.0, typicality_sd=None,
        typicality_rounds=(None,) if impossible else (7,), max_severity=worst,
        clash_count=0 if worst == "" else 1,
    )


def _s2(pid, cls, pair=("employment_status", "employment_type")):
    return Stage2IssueRow(pid, 0, pair[0], pair[1], cls, "", "", "r", "", "", "")


def _record(slug, personas, stage2, *, real=False):
    return CompetitorRecord(
        slug=slug, country="swedish_02", model="" if real else "m", strategy="" if real else "s",
        is_real_reference=real, n_personas=len(personas), n_failed=0, personas=tuple(personas),
        impossibility={}, dispersion={}, reliability={},
        provenance={"stage2_persona_class_order": _ORDER, "stage2_prompt_sha256": None if real else "h"},
        report_path=Path(f"/fake/{slug}.json"), personas_csv_path=Path(f"/fake/{slug}_personas.csv"),
        stage2=None if stage2 is None else tuple(stage2),
    )


def _records():
    synth = _record("syn", [
        _persona("p1", "syn", "S3", impossible=True),
        _persona("p2", "syn", "S3", impossible=True),
        _persona("p3", "syn", "S3", impossible=True),
        _persona("p4", "syn", "S2", impossible=False),
        _persona("p5", "syn", "", impossible=False),
    ], [_s2("p1", "raw_impossible"), _s2("p2", "ambiguous"),
        _s2("p2", "mapping_error", ("employment_status", "industry_sector")), _s2("p3", "judge_error")])
    real = _record("real_swedish_02", [
        _persona("q1", "real_swedish_02", "S3", impossible=True),
        _persona("q2", "real_swedish_02", "S1", impossible=False),
    ], [_s2("q1", "not_applicable_no_free_text")], real=True)
    return [synth, real]


def _split_options():
    return builder.worst_clash_split_options(yaml.safe_load(_SPLIT_CONFIG.read_text(encoding="utf-8")))


def test_worst_clash_split_places_s3_by_stage2_class_and_keeps_the_reference_unsplit():
    block = builder._worst_clash_split(_records(), _split_options(), [])
    by = {row["slug"]: row["counts"] for row in block["competitors"]}
    assert by["syn"] == {"none": 1, "S1": 0, "S2": 1, "S3b": 1, "S3a": 1, "S3": 0, "pipeline": 1}
    assert by["real_swedish_02"] == {"none": 0, "S1": 1, "S2": 0, "S3b": 0, "S3a": 0, "S3": 1, "pipeline": 0}
    # each individual counted once
    for row in block["competitors"]:
        assert sum(row["counts"].values()) == row["n_individuals"]
    rows = builder.worst_clash_split_rows({"worst_clash_split": block})
    assert rows[0]["n_S3a"] == 1 and "n_pipeline" in rows[0]


def test_impossible_breakdown_counts_only_the_axis_a_impossible_set():
    block = builder._stage2_breakdown(_records(), [])
    by = {row["slug"]: row for row in block["competitors"]}
    assert by["syn"]["impossible_count"] == 3
    assert by["syn"]["by_class"]["raw_impossible"] == 1
    assert by["syn"]["by_class"]["ambiguous"] == 1      # ambiguous outranks mapping_error
    assert by["syn"]["by_class"]["judge_error"] == 1
    assert by["real_swedish_02"]["by_class"]["not_applicable_no_free_text"] == 1


def test_blocks_skip_when_no_competitor_has_stage2_and_raise_when_only_some_do():
    none = [dataclasses.replace(r, stage2=None) for r in _records()]
    skips: list = []
    assert builder._stage2_breakdown(none, skips) is None
    assert builder._worst_clash_split(none, _split_options(), skips) is None
    assert {s.test for s in skips} == {"stage2_breakdown", "worst_clash_split"}
    partial = [_records()[0], dataclasses.replace(_records()[1], stage2=None)]
    with pytest.raises(ValueError, match="carry no stage-2 CSV"):
        builder._stage2_breakdown(partial, [])


def test_split_config_must_map_every_class():
    spec = yaml.safe_load(_SPLIT_CONFIG.read_text(encoding="utf-8"))
    del spec["s3_split"]["judge_error"]
    with pytest.raises(ValueError, match="must map exactly"):
        builder.worst_clash_split_options(spec)


def test_every_split_category_has_a_label_and_a_colour():
    from population_synthetic.analysis.utils.labels import worst_clash_label
    from population_synthetic.analysis.utils.palette import worst_clash_color

    for category in _split_options()["categories"]:
        assert worst_clash_label(category)
        assert worst_clash_color(category).startswith("#")

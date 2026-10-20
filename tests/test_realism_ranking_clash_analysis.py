"""realism_ranking's clash analysis: the worst-clash states against the reference, C excluded."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest
import yaml
from scipy import stats

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.realism_ranking import builder
from population_synthetic.analysis.realism_ranking.clash_analysis import (
    CLASH_STATES,
    ClashGroup,
    clash_analysis,
)
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord
from population_synthetic.analysis.utils.realism_csv import RealismPersonaRow
from population_synthetic.analysis.utils.realism_stage2_csv import Stage2IssueRow
from population_synthetic.analysis.utils.stats_tests import clopper_pearson_interval, fisher_exact_test

_ORDER = ["raw_impossible", "label_clash", "ambiguous", "mapping_error", "judge_error"]
_SPLIT_CONFIG = PROJECT_ROOT / "config" / "analysis" / "realism_ranking" / "worst_clash_split.yaml"
_RESAMPLING = {
    "ci_level": 0.95, "bootstrap_iterations": 200, "bootstrap_seed": 1,
    "permutation_iterations": 199, "permutation_seed": 2,
    "noise_iterations": 200, "noise_seed": 3, "noise_quantile": 0.95,
}
_MODELS = ("m1", "m2", "m3")
_STRATEGIES = ("all_pick_v2", "all_pick_dag_v2")


def _spec():
    return yaml.safe_load(_SPLIT_CONFIG.read_text(encoding="utf-8"))


def _options():
    return builder.worst_clash_split_options(_spec())


# ---------------------------------------------------------------- config ---


def test_live_config_excludes_c_and_pipeline_and_keeps_the_unsplit_s3_at_rank_3():
    spec = _options()["clash_analysis"]
    assert spec["excluded"] == ["c_scb_category_limitation", "pipeline"]
    assert spec["states"]["S3"] == ["r3_impossible", "S3"]
    assert list(spec["rates"]) == ["any_clash", "rank_2_or_3", "rank_3"]
    assert spec["decomposed_rates"] == ["rank_2_or_3", "rank_3"]


def test_missing_clash_analysis_block_raises():
    spec = _spec()
    del spec["clash_analysis"]
    with pytest.raises(ValueError, match="missing 'clash_analysis'"):
        builder.worst_clash_split_options(spec)


@pytest.mark.parametrize("mutate, match", [
    (lambda s: s["clash_analysis"]["excluded"].append("r3_impossible"), "exactly once"),
    (lambda s: s["clash_analysis"].update(excluded=[]), "exactly once"),
    (lambda s: s["clash_analysis"]["states"].update(S2=["S2", "r3_impossible"]), "must hold only"),
    (lambda s: s["clash_analysis"]["states"].pop("S1"), "must map exactly"),
    (lambda s: s["clash_analysis"]["rates"].update(bad=["S4"]), "rates.bad"),
    (lambda s: s["clash_analysis"].update(decomposed_rates=["nope"]), "decomposed_rates"),
    (lambda s: s["clash_analysis"].update(alpha=1.5), "alpha"),
    (lambda s: s["clash_analysis"].pop("alpha"), "missing"),
    (lambda s: s["clash_analysis"].update(extra=1), "unknown"),
])
def test_malformed_clash_analysis_config_raises(mutate, match):
    spec = copy.deepcopy(_spec())
    mutate(spec)
    with pytest.raises(ValueError, match=match):
        builder.worst_clash_split_options(spec)


# --------------------------------------------------------- stats primitives ---


def test_fisher_and_clopper_pearson_match_scipy_and_the_closed_form():
    result = fisher_exact_test(8, 96, 0, 100)
    assert result["p"] == pytest.approx(stats.fisher_exact([[8, 88], [0, 100]])[1])
    assert result["diff"] == pytest.approx(8 / 96)
    lo, hi = clopper_pearson_interval(0, 100, ci_level=0.95)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 100))
    with pytest.raises(ValueError):
        fisher_exact_test(5, 4, 0, 10)
    with pytest.raises(ValueError):
        clopper_pearson_interval(1, 0, ci_level=0.95)


# ------------------------------------------------------------- pure block ---


def _units(none, s1, s2, s3):
    rows = []
    for state, k in zip(CLASH_STATES, (none, s1, s2, s3)):
        unit = np.zeros(len(CLASH_STATES))
        unit[CLASH_STATES.index(state)] = 1.0
        rows.extend([unit] * k)
    return np.array(rows)


def _group(model, strategy, counts, excluded=0, pairs=None):
    return ClashGroup(slug=f"c_{strategy}_{model}", model=model, strategy=strategy, units=_units(*counts),
                      n_excluded=excluded, rank3_pairs=pairs or {})


def _grid():
    counts = {
        ("m1", "all_pick_v2"): ((10, 8, 1, 1), 0), ("m2", "all_pick_v2"): ((12, 6, 0, 0), 2),
        ("m3", "all_pick_v2"): ((5, 12, 2, 1), 0), ("m1", "all_pick_dag_v2"): ((15, 5, 0, 0), 0),
        ("m2", "all_pick_dag_v2"): ((9, 9, 1, 0), 1), ("m3", "all_pick_dag_v2"): ((14, 4, 1, 1), 0),
    }
    return [_group(m, s, c, e, {("a", "b"): c[3]} if c[3] else None) for (m, s), (c, e) in counts.items()]


def test_rates_tests_and_denominators_follow_the_analysed_individuals_only():
    groups = _grid()
    reference = _group("", "", (2, 16, 2, 0))
    block, skips = clash_analysis(groups, reference, models=_MODELS, strategies=_STRATEGIES,
                                  spec=_options()["clash_analysis"], resampling=_RESAMPLING)
    # a 6-cell toy grid can hit a degenerate bootstrap replicate; that drops only the share
    # intervals, recorded, never folded in
    assert all(test.endswith(".decomposition_intervals") for test, _ in skips)
    by = {(row["model"], row["strategy"]): row for row in block["competitors"] if not row["is_real_reference"]}
    cell = by[("m2", "all_pick_v2")]
    assert (cell["n_judged"], cell["n_excluded"], cell["n"]) == (20, 2, 18)
    assert cell["rates"]["any_clash"] == pytest.approx({**cell["rates"]["any_clash"], "count": 6, "n": 18,
                                                        "rate": 6 / 18})
    any_ref = 18 / 20
    assert cell["vs_reference"]["any_clash"]["diff"] == pytest.approx(6 / 18 - any_ref)
    assert cell["vs_reference"]["any_clash"]["p_fisher"] == pytest.approx(
        stats.fisher_exact([[6, 12], [18, 2]])[1])
    # Holm over the six combinations of one rate
    raw = [row["vs_reference"]["rank_3"]["p_fisher"] for row in block["competitors"][:-1]]
    holm = [row["vs_reference"]["rank_3"]["p_holm"] for row in block["competitors"][:-1]]
    assert holm == pytest.approx(builder.holm_adjust(raw))
    # TV similarity over the four states
    p = np.array([12, 6, 0, 0]) / 18
    q = np.array([2, 16, 2, 0]) / 20
    assert cell["tv_similarity"]["value"] == pytest.approx(1 - 0.5 * np.abs(p - q).sum())
    assert block["totals"]["n_excluded"] == 3 and block["totals"]["n_combinations_with_exclusions"] == 2
    assert block["totals"]["n"] == sum(row["n"] for row in block["competitors"][:-1])
    pooled_a = next(lv for lv in block["pooled"]["strategy"] if lv["level"] == "all_pick_v2")
    assert pooled_a["n"] == 20 + 18 + 20 and pooled_a["n_excluded"] == 2
    assert pooled_a["rank_3"]["rate"] == pytest.approx(2 / 58)
    assert block["rank3_pairs"]["pairs"] == [{"attr_a": "a", "attr_b": "b", "n_individuals": 3}]
    assert set(block["decomposition"]) == {"rank_2_or_3", "rank_3"}
    assert block["decomposition"]["rank_3"]["permutation"]["strategy"]["iterations"] == 199
    assert sum(block["holm_summary"]["any_clash"].values()) == len(groups)


def test_a_unit_row_that_is_not_one_hot_raises():
    bad = ClashGroup(slug="x", model="m1", strategy="all_pick_v2", units=np.full((2, 4), 0.25),
                     n_excluded=0, rank3_pairs={})
    with pytest.raises(ValueError, match="one-hot"):
        clash_analysis([bad], _group("", "", (1, 1, 0, 0)), models=_MODELS, strategies=_STRATEGIES,
                       spec=_options()["clash_analysis"], resampling=_RESAMPLING)


# ------------------------------------------------------- builder adapter ---


def _persona(pid, slug, worst, *, model, strategy):
    impossible = worst == "S3"
    return RealismPersonaRow(
        persona_id=pid, slug=slug, country="swedish_02", model=model, strategy=strategy,
        is_real_reference=slug.startswith("real_"), n_rounds_attempted=1, n_rounds_successful=1,
        can_exist_true_votes=0 if impossible else 1, can_exist_majority=not impossible,
        typicality_mean=None if impossible else 7.0, typicality_sd=None,
        typicality_rounds=(None,) if impossible else (7,), max_severity=worst,
        clash_count=0 if worst == "" else 1,
    )


def _s2(pid, cls, pair=("employment_status", "employment_type")):
    return Stage2IssueRow(pid, 0, pair[0], pair[1], cls, "", "", "r", "", "", "")


def _record(slug, model, strategy, worsts, stage2, *, real=False):
    personas = [_persona(f"p{i}", slug, w, model=model, strategy=strategy) for i, w in enumerate(worsts)]
    return CompetitorRecord(
        slug=slug, country="swedish_02", model=model, strategy=strategy, is_real_reference=real,
        n_personas=len(personas), n_failed=0, personas=tuple(personas), impossibility={}, dispersion={},
        reliability={},
        provenance={"stage2_persona_class_order": _ORDER, "stage2_prompt_sha256": None if real else "h"},
        report_path=Path(f"/fake/{slug}.json"), personas_csv_path=Path(f"/fake/{slug}_personas.csv"),
        stage2=tuple(stage2),
    )


def test_builder_excludes_c_and_pipeline_individuals_and_reports_them_in_the_split_rows():
    syn = [
        # p0 R3 (raw_impossible + a label-clash pair that is not a rank-3 pair), p1 C (ambiguous),
        # p2 pipeline (judge_error) -> excluded like C, p3 S2, p4 none
        _record("swedish_02_all_pick_v2_m1", "m1", "all_pick_v2", ["S3", "S3", "S3", "S2", ""],
                [_s2("p0", "raw_impossible"), _s2("p0", "label_clash", ("age_group", "income_source")),
                 _s2("p1", "ambiguous"), _s2("p2", "judge_error", ("age_group", "employment_status"))]),
        _record("swedish_02_all_pick_dag_v2_m1", "m1", "all_pick_dag_v2", ["S1", "", "S3"],
                [_s2("p2", "label_clash")]),
    ]
    real = _record("real_swedish_02", "", "", ["S1", "S1", ""], [], real=True)
    skips: list = []
    block = builder._clash_analysis(syn, real, _spec(), resampling=_RESAMPLING, skips=skips)
    by = {row["slug"]: row for row in block["competitors"]}
    a = by["swedish_02_all_pick_v2_m1"]
    assert (a["n_judged"], a["n_excluded"], a["n"]) == (5, 2, 3)
    assert a["counts"] == {"none": 1, "S1": 0, "S2": 1, "S3": 1}
    b = by["swedish_02_all_pick_dag_v2_m1"]
    assert (b["n_excluded"], b["counts"]) == (1, {"none": 1, "S1": 1, "S2": 0, "S3": 0})
    assert by["real_swedish_02"]["n_excluded"] == 0
    pairs = {(p["attr_a"], p["attr_b"]): p["n_individuals"] for p in block["rank3_pairs"]["pairs"]}
    assert pairs == {("employment_status", "employment_type"): 1}
    split = builder._worst_clash_split([*syn, real], _spec(), [])
    rows = {row["slug"]: row for row in builder.worst_clash_split_rows({"worst_clash_split": split})}
    assert rows["swedish_02_all_pick_v2_m1"]["n_excluded_from_clash_analysis"] == 2
    assert split["clash_analysis_excluded"] == ["c_scb_category_limitation", "pipeline"]
    flat = builder.clash_analysis_rows({"clash_analysis": block})
    assert flat[-1]["is_real_reference"] and flat[0]["excluded_categories"] == "c_scb_category_limitation;pipeline"
    assert {row["rate_name"] for row in builder.clash_analysis_pooled_rows({"clash_analysis": block})} == {
        "any_clash", "rank_2_or_3", "rank_3"}


def test_builder_skips_without_stage2_or_reference():
    syn = [_record("swedish_02_all_pick_v2_m1", "m1", "all_pick_v2", [""], [])]
    skips: list = []
    assert builder._clash_analysis(syn, None, _spec(), resampling=_RESAMPLING, skips=skips) is None
    real = _record("real_swedish_02", "", "", [""], [], real=True)
    import dataclasses

    assert builder._clash_analysis([dataclasses.replace(syn[0], stage2=None)], real, _spec(),
                                   resampling=_RESAMPLING, skips=skips) is None
    assert [s.test for s in skips] == ["clash_analysis", "clash_analysis"]

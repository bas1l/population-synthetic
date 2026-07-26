"""Unit tests for the persona-realism reliability / dispersion / resampling primitives.

Validates ``bootstrap_ci``, ``icc``, ``krippendorff_alpha`` and
``variance_equality_test`` (all added to
:mod:`population_synthetic.analysis.utils.stats_tests` for the persona-realism
judge process) against hand-computed known answers, and pins the library-backed
Levene test to scipy's own output on a fixture -- per the statistical-software
guide (validate against an authority, compare floats approximately, cover
degenerate inputs). Every degenerate case asserts an explicit skipped-reason
(``None`` + ``"note"``), never a bare ``NaN``.

Hand derivations are recorded inline next to each expected value so the fixtures
are checkable without rerunning the code.
"""

from __future__ import annotations

import pytest
from scipy import stats

from population_synthetic.analysis.utils.stats_tests import (
    bootstrap_ci,
    icc,
    krippendorff_alpha,
    variance_equality_test,
)

# --------------------------------------------------------------------------- #
# bootstrap_ci                                                                 #
# --------------------------------------------------------------------------- #


def test_bootstrap_ci_constant_sample_is_exact():
    # Every resample of a constant sample is that constant -> lo == hi == point.
    res = bootstrap_ci([0.4, 0.4, 0.4, 0.4], iterations=500, seed=7)
    assert res["point"] == pytest.approx(0.4)
    assert res["lo"] == pytest.approx(0.4)
    assert res["hi"] == pytest.approx(0.4)
    assert res["n"] == 4 and res["iterations"] == 500 and res["method"] == "percentile"


def test_bootstrap_ci_single_element_sample_is_exact():
    res = bootstrap_ci([1.0], iterations=100, seed=1)
    assert res["point"] == pytest.approx(1.0)
    assert res["lo"] == pytest.approx(1.0)
    assert res["hi"] == pytest.approx(1.0)


def test_bootstrap_ci_brackets_point_and_is_deterministic():
    # A 0/1 sample -> mean is the rate; the interval must bracket the point and be
    # byte-identical for a fixed seed (default_rng, not global np.random.seed).
    values = [0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    a = bootstrap_ci(values, iterations=1000, ci_level=0.95, seed=42)
    b = bootstrap_ci(values, iterations=1000, ci_level=0.95, seed=42)
    assert a["point"] == pytest.approx(0.3)
    assert a["lo"] <= a["point"] <= a["hi"]
    assert 0.0 <= a["lo"] and a["hi"] <= 1.0
    assert a["lo"] == pytest.approx(b["lo"]) and a["hi"] == pytest.approx(b["hi"])


def test_bootstrap_ci_different_seed_may_differ_but_stays_bounded():
    values = [0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    a = bootstrap_ci(values, iterations=1000, seed=1)
    b = bootstrap_ci(values, iterations=1000, seed=2)
    assert a["lo"] <= a["point"] <= a["hi"]
    assert b["lo"] <= b["point"] <= b["hi"]


def test_bootstrap_ci_empty_is_skipped_not_nan():
    res = bootstrap_ci([], iterations=100, seed=0)
    assert res["point"] is None and res["lo"] is None and res["hi"] is None
    assert "note" in res


def test_bootstrap_ci_rejects_malformed_request():
    with pytest.raises(ValueError):
        bootstrap_ci([1.0, 2.0], iterations=0)
    with pytest.raises(ValueError):
        bootstrap_ci([1.0, 2.0], ci_level=1.0)
    with pytest.raises(ValueError):
        bootstrap_ci([1.0, 2.0], ci_level=0.0)


# --------------------------------------------------------------------------- #
# icc -- ICC(1,1), hand-computed                                              #
# --------------------------------------------------------------------------- #


def test_icc_known_answer():
    # 3 subjects x 2 rounds. grand = 33/6 = 5.5.
    # SSB = 2*[(8.5-5.5)^2 + 0 + (2.5-5.5)^2] = 36 -> MSB = 36/2 = 18.
    # SSW = 6*0.25 = 1.5 -> MSW = 1.5/(3*1) = 0.5.
    # ICC = (18 - 0.5) / (18 + 1*0.5) = 17.5/18.5 = 35/37.
    ratings = [[9, 8], [5, 6], [2, 3]]
    res = icc(ratings)
    assert res["icc"] == pytest.approx(35.0 / 37.0)
    assert res["n"] == 3 and res["k"] == 2 and res["model"] == "ICC(1,1)"
    assert res["msb"] == pytest.approx(18.0) and res["msw"] == pytest.approx(0.5)


def test_icc_perfect_agreement_is_one():
    # Zero within-subject variance, non-zero between -> MSW = 0 -> ICC = 1.
    res = icc([[10, 10], [4, 4], [7, 7]])
    assert res["icc"] == pytest.approx(1.0)


def test_icc_single_round_is_skipped_not_nan():
    res = icc([[1], [2], [3]])
    assert res["icc"] is None
    assert res["k"] == 1 and "note" in res


def test_icc_fewer_than_two_subjects_is_skipped():
    res = icc([[1, 2, 3]])
    assert res["icc"] is None and "note" in res


def test_icc_all_identical_is_skipped_not_nan():
    res = icc([[5, 5], [5, 5], [5, 5]])
    assert res["icc"] is None and "note" in res


def test_icc_ragged_rows_raise():
    with pytest.raises(ValueError):
        icc([[1, 2], [3, 4, 5]])


# --------------------------------------------------------------------------- #
# krippendorff_alpha -- hand-computed nominal and interval                    #
# --------------------------------------------------------------------------- #


def test_krippendorff_nominal_known_answer():
    # 4 units x 2 coders, binary. Coincidences: o[1][1]=4, o[0][0]=2,
    # o[0][1]=o[1][0]=1. n_0=3, n_1=5, n=8.
    # Do = (o[0][1]+o[1][0])/n = 2/8 = 0.25.
    # De = (n_0*n_1 + n_1*n_0)/(n*(n-1)) = 30/56.
    # alpha = 1 - (0.25)/(30/56) = 1 - 14/30 = 16/30 = 8/15.
    data = [[1, 1], [1, 0], [0, 0], [1, 1]]
    res = krippendorff_alpha(data, level="nominal")
    assert res["alpha"] == pytest.approx(8.0 / 15.0)
    assert res["n_units"] == 4 and res["n_values"] == 2 and res["level"] == "nominal"


def test_krippendorff_interval_known_answer():
    # 3 units x 2 coders, values {1,2,3}. o[1][1]=2, o[3][3]=2, o[2][3]=o[3][2]=1.
    # n_1=2, n_2=1, n_3=3, n=6.
    # Do = (o[2][3]*1 + o[3][2]*1)/6 = 2/6.
    # De = 58/(6*5) = 58/30  (sum over ordered unequal pairs of n_c*n_k*(c-k)^2).
    # alpha = 1 - (2/6)/(58/30) = 1 - 5/29 = 24/29.
    data = [[1, 1], [2, 3], [3, 3]]
    res = krippendorff_alpha(data, level="interval")
    assert res["alpha"] == pytest.approx(24.0 / 29.0)
    assert res["n_units"] == 3 and res["n_values"] == 3


def test_krippendorff_perfect_agreement_is_one():
    # No within-unit disagreement, >=2 distinct values overall -> Do=0 -> alpha=1.
    data = [[7, 7], [3, 3], [9, 9]]
    for level in ("nominal", "interval", "ordinal"):
        res = krippendorff_alpha(data, level=level)
        assert res["alpha"] == pytest.approx(1.0), level


def test_krippendorff_handles_missing_ratings():
    # A None (failed round) is dropped; a unit left with <2 ratings is excluded.
    data = [[1, 1, None], [0, 0, 0], [1, None, None], [0, 1]]
    res = krippendorff_alpha(data, level="nominal")
    # Unit index 2 has only one non-None rating -> excluded; 3 usable units remain.
    assert res["n_units"] == 3
    assert res["alpha"] is not None


def test_krippendorff_single_value_is_skipped_not_nan():
    res = krippendorff_alpha([[4, 4], [4, 4], [4, 4]], level="interval")
    assert res["alpha"] is None and "note" in res


def test_krippendorff_too_few_units_is_skipped():
    res = krippendorff_alpha([[1, 0]], level="nominal")
    assert res["alpha"] is None and "note" in res


def test_krippendorff_empty_is_skipped():
    res = krippendorff_alpha([], level="nominal")
    assert res["alpha"] is None and "note" in res


def test_krippendorff_rejects_unknown_level():
    with pytest.raises(ValueError):
        krippendorff_alpha([[1, 0], [1, 1]], level="ratio")


# --------------------------------------------------------------------------- #
# variance_equality_test -- pinned to scipy.stats.levene                      #
# --------------------------------------------------------------------------- #


def test_variance_equality_matches_scipy_brown_forsythe():
    groups = {"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [2.0, 2.0, 2.1, 6.0, 9.0]}
    res = variance_equality_test(groups, center="median")
    stat, p = stats.levene(groups["a"], groups["b"], center="median")
    assert res["statistic"] == pytest.approx(float(stat))
    assert res["p"] == pytest.approx(float(p))
    assert res["k"] == 2 and res["center"] == "median" and res["n"] == 10


def test_variance_equality_mean_center_is_classic_levene():
    groups = {"a": [1.0, 2.0, 3.0, 4.0], "b": [10.0, 20.0, 30.0, 40.0]}
    res = variance_equality_test(groups, center="mean")
    stat, p = stats.levene(groups["a"], groups["b"], center="mean")
    assert res["statistic"] == pytest.approx(float(stat))
    assert res["p"] == pytest.approx(float(p))


def test_variance_equality_too_few_groups_is_skipped():
    res = variance_equality_test({"a": [1.0, 2.0, 3.0]}, center="median")
    assert res["statistic"] is None and res["p"] is None and "note" in res


def test_variance_equality_zero_variance_everywhere_is_skipped_not_nan():
    res = variance_equality_test({"a": [3.0, 3.0, 3.0], "b": [3.0, 3.0, 3.0]})
    assert res["statistic"] is None and res["p"] is None and "note" in res


def test_variance_equality_drops_singleton_groups():
    # Group "b" has a single sample -> excluded; only one usable group -> skipped.
    res = variance_equality_test({"a": [1.0, 2.0, 3.0], "b": [5.0]})
    assert res["statistic"] is None and res["k"] == 1 and "note" in res


def test_variance_equality_rejects_bad_center():
    with pytest.raises(ValueError):
        variance_equality_test({"a": [1.0, 2.0], "b": [3.0, 4.0]}, center="trimmed")


# =========================================================================== #
# Phase 3: reduction (round -> persona -> combo), combo stats, and the        #
# hard-rules validation subset. Fixtures build RoundVerdict DTOs directly (no  #
# live judge) so the pure reduction/stats layers are exercised in isolation.   #
# =========================================================================== #

import dataclasses  # noqa: E402
import json  # noqa: E402

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.persona_realism.judge import Issue, RoundVerdict  # noqa: E402
from population_synthetic.analysis.persona_realism.reduce import (  # noqa: E402
    ClashKey,
    LoadedPersona,
    load_combo_verdicts,
    load_persona_verdicts,
    reduce_combo,
    reduce_persona,
)
from population_synthetic.analysis.persona_realism.stats import compute_realism_stats  # noqa: E402
from population_synthetic.analysis.persona_realism.validation import (  # noqa: E402
    HardRule,
    load_hard_rules,
    rule_fires,
    rules_verdict,
    validate_against_hard_rules,
)

_HARD_RULES_PATH = PROJECT_ROOT / "config" / "analysis" / "persona_realism" / "hard_rules.yaml"
_BOOT = {"iterations": 300, "seed": 20260723, "ci_level": 0.95}


def _possible(typicality, issues=()):
    return RoundVerdict(can_exist=True, typicality=typicality, issues=tuple(issues), reasoning="")


def _impossible(issues=(Issue(("age_group", "education_level"), "S3", "x"),)):
    return RoundVerdict(can_exist=False, typicality=None, issues=tuple(issues), reasoning="")


# --------------------------------------------------------------------------- #
# reduce_persona                                                               #
# --------------------------------------------------------------------------- #


def test_reduce_persona_fraction_typicality_and_clashes():
    clash_ab = Issue(("age_group", "income"), "S1", "unusual")
    clash_ba = Issue(("income", "age_group"), "S1", "same clash, reversed order")
    clash_ac = Issue(("age_group", "education_level"), "S3", "hard")
    rounds = [
        _possible(8, [clash_ab]),
        _possible(6, [clash_ba]),
        _impossible([clash_ac]),
    ]
    pv = reduce_persona(rounds, persona_id="persona_00001")
    assert pv.n_rounds == 3
    assert pv.n_possible == 2
    assert pv.p_possible == pytest.approx(2.0 / 3.0)
    assert pv.possible_majority is True
    # typicality mean/SD over the two scored (possible) rounds only.
    assert pv.typicality_mean == pytest.approx(7.0)
    assert pv.typicality_sd == pytest.approx(2.0 ** 0.5)  # sample SD of [8, 6]
    assert pv.can_exist_rounds == (True, True, False)
    assert pv.typicality_rounds == (8, 6, None)
    # (age_group, income)/S1 appeared in 2 of 3 rounds despite reversed naming;
    # the S3 clash in 1 round. Pair keys are canonically sorted.
    assert pv.clash_frequency[ClashKey(("age_group", "income"), "S1")] == 2
    assert pv.clash_frequency[ClashKey(("age_group", "education_level"), "S3")] == 1


def test_reduce_persona_single_scored_round_sd_none():
    pv = reduce_persona([_possible(5)], persona_id="p")
    assert pv.n_rounds == 1
    assert pv.typicality_mean == pytest.approx(5.0)
    assert pv.typicality_sd is None  # sample SD undefined for one point (not NaN)


def test_reduce_persona_all_impossible_has_no_typicality():
    pv = reduce_persona([_impossible(), _impossible()], persona_id="p")
    assert pv.possible_majority is False
    assert pv.typicality_mean is None and pv.typicality_sd is None


def test_reduce_persona_empty_raises():
    # A fully-failed persona must be represented as None at the combo layer, not
    # reduced here.
    with pytest.raises(ValueError, match="requires >=1 successful round"):
        reduce_persona([], persona_id="p")


# --------------------------------------------------------------------------- #
# reduce_combo                                                                 #
# --------------------------------------------------------------------------- #


def _make_combo():
    p1 = reduce_persona([_possible(8), _possible(9)], persona_id="p1")   # possible, mean 8.5
    p2 = reduce_persona([_possible(3), _possible(4)], persona_id="p2")   # possible, mean 3.5
    p3 = reduce_persona([_impossible(), _impossible()], persona_id="p3")  # impossible
    return reduce_combo([p1, p2, p3, None], "combo_x")


def test_reduce_combo_carries_n_and_failed_and_rate():
    combo = _make_combo()
    assert combo.n_personas == 3        # successful personas
    assert combo.n_failed == 1          # the None slot (all rounds failed / absent)
    assert combo.impossible_count == 1
    assert combo.impossibility_rate == pytest.approx(1.0 / 3.0)
    assert combo.impossible_indicators == (0, 0, 1)
    # typicality distribution over the can_exist (majority-possible) subset only.
    assert combo.typicality_means == pytest.approx((8.5, 3.5))
    # reliability inputs retain the raw per-round series (None for impossible rounds)
    assert combo.can_exist_rounds_by_persona == ((True, True), (True, True), (False, False))
    assert combo.typicality_rounds_by_persona == ((8, 9), (3, 4), (None, None))


def test_reduce_combo_all_failed_is_empty_base():
    combo = reduce_combo([None, None], "combo_dead")
    assert combo.n_personas == 0 and combo.n_failed == 2
    assert combo.impossibility_rate is None
    assert combo.impossible_indicators == ()
    assert combo.typicality_means == ()


# --------------------------------------------------------------------------- #
# compute_realism_stats                                                        #
# --------------------------------------------------------------------------- #


def _scb_ref():
    return reduce_combo(
        [reduce_persona([_possible(5), _possible(5)], persona_id=f"s{i}") for i in range(3)],
        "real_swedish",
    )


def test_stats_impossibility_bootstrap_over_personas():
    combo = _make_combo()
    rs = compute_realism_stats(combo, _scb_ref(), bootstrap=_BOOT)
    imp = rs.impossibility
    assert imp["point"] == pytest.approx(1.0 / 3.0)  # rate == mean of indicators
    assert imp["rate"] == pytest.approx(1.0 / 3.0)
    assert imp["lo"] <= imp["point"] <= imp["hi"]
    assert imp["successful_count"] == 3 and imp["failed_count"] == 1
    assert imp["n"] == 3  # the resampled unit is the persona


def test_stats_dispersion_measures_and_distance_to_scb():
    combo = _make_combo()  # typicality_means (8.5, 3.5)
    rs = compute_realism_stats(combo, _scb_ref(), bootstrap=_BOOT, tail_threshold=3.0)
    disp = rs.dispersion
    assert disp["n"] == 2
    assert disp["variance"] == pytest.approx(12.5)         # sample var of [8.5, 3.5]
    assert disp["tail_coverage"] == pytest.approx(0.0)     # neither <= 3.0
    assert disp["scb_reference"] == "real_swedish"
    # SCB [5,5,5] -> variance 0 -> distance 12.5; entropy: SCB single bucket -> 0.
    assert disp["distance_to_scb"]["variance"] == pytest.approx(12.5)
    assert "statistic" in disp["variance_equality"]


def test_stats_reliability_is_named_self_consistency_not_accuracy():
    combo = _make_combo()
    rs = compute_realism_stats(combo, None, bootstrap=_BOOT, typicality_level="ordinal")
    rel = rs.reliability
    # can_exist rounds are perfectly consistent within each persona -> alpha 1.
    assert rel["can_exist_alpha"]["alpha"] == pytest.approx(1.0)
    assert rel["typicality_alpha"]["level"] == "ordinal"
    assert rel["typicality_alpha"]["alpha"] is not None
    assert rel["typicality_icc"]["model"] == "ICC(1,1)"
    assert rel["typicality_level"] == "ordinal"
    # No SCB reference -> distance/variance-equality skipped, not crashed.
    assert rs.dispersion["variance_equality"]["statistic"] is None
    assert rs.dispersion["distance_to_scb"]["variance"] is None


def test_stats_single_round_reliability_is_skipped_not_nan():
    combo = reduce_combo(
        [reduce_persona([_possible(5)], persona_id="a"),
         reduce_persona([_possible(7)], persona_id="b")],
        "combo_1r",
    )
    rs = compute_realism_stats(combo, None, bootstrap=_BOOT)
    assert rs.reliability["can_exist_alpha"]["alpha"] is None
    assert "note" in rs.reliability["can_exist_alpha"]
    assert rs.reliability["typicality_icc"]["icc"] is None
    assert "note" in rs.reliability["typicality_icc"]


def test_stats_empty_can_exist_set_dispersion_skipped():
    combo = reduce_combo(
        [reduce_persona([_impossible(), _impossible()], persona_id="a"),
         reduce_persona([_impossible(), _impossible()], persona_id="b")],
        "combo_all_impossible",
    )
    rs = compute_realism_stats(combo, None, bootstrap=_BOOT)
    assert rs.dispersion["variance"] is None
    assert rs.dispersion["tail_coverage"] is None
    assert "note" in rs.dispersion
    # impossibility rate still well-defined (both impossible -> 1.0).
    assert rs.impossibility["point"] == pytest.approx(1.0)


def test_stats_all_failed_combo_impossibility_skipped():
    combo = reduce_combo([None, None, None], "combo_dead")
    rs = compute_realism_stats(combo, None, bootstrap=_BOOT)
    assert rs.impossibility["point"] is None and "note" in rs.impossibility
    assert rs.impossibility["successful_count"] == 0 and rs.impossibility["failed_count"] == 3


# --------------------------------------------------------------------------- #
# cache loader (round-trips Phase 2's dataclasses.asdict)                      #
# --------------------------------------------------------------------------- #


def _cache_payload(persona_id, attributes, verdicts, failed_rounds=0):
    return {
        "persona_id": persona_id,
        "combo": "combo_x",
        "judge_model": "claude-fable-5",
        "n_rounds": len(verdicts) + failed_rounds,
        "successful_rounds": len(verdicts),
        "failed_rounds": failed_rounds,
        "status": "complete" if failed_rounds == 0 else "partial",
        "attributes": attributes,
        "rounds": [dataclasses.asdict(v) for v in verdicts],
    }


def test_loader_round_trips_asdict_cache(tmp_path):
    combo_dir = tmp_path / "combo_x"  # per-persona files live at the combo root (no raw/)
    combo_dir.mkdir()
    verdicts = [_possible(8, [Issue(("age_group", "income"), "S1", "hi")]), _impossible()]
    payload = _cache_payload("persona_00007", {"age_group": "25-34", "sex": "female"}, verdicts)
    (combo_dir / "persona_00007.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_persona_verdicts(combo_dir / "persona_00007.json")
    assert isinstance(loaded, LoadedPersona)
    assert loaded.persona_id == "persona_00007"
    assert loaded.attributes == {"age_group": "25-34", "sex": "female"}
    assert loaded.rounds[0].can_exist is True and loaded.rounds[0].typicality == 8
    # Issue attributes survive the tuple->list->tuple JSON round-trip.
    assert loaded.rounds[0].issues[0] == Issue(("age_group", "income"), "S1", "hi")
    assert loaded.rounds[1].can_exist is False and loaded.rounds[1].typicality is None


def test_load_combo_marks_absent_expected_ids_as_none(tmp_path):
    combo_dir = tmp_path / "combo_x"
    combo_dir.mkdir()
    payload = _cache_payload("persona_00001", {"age_group": "25-34"}, [_possible(5)])
    (combo_dir / "persona_00001.json").write_text(json.dumps(payload), encoding="utf-8")

    result = load_combo_verdicts(combo_dir, expected_ids=["persona_00001", "persona_00002"])
    assert result["persona_00001"] is not None
    assert result["persona_00002"] is None  # selected but no cache file == failed/absent


def test_load_combo_without_expected_ids_returns_only_present(tmp_path):
    combo_dir = tmp_path / "combo_x"
    combo_dir.mkdir()
    payload = _cache_payload("persona_00003", {"age_group": "25-34"}, [_possible(5)])
    (combo_dir / "persona_00003.json").write_text(json.dumps(payload), encoding="utf-8")
    result = load_combo_verdicts(combo_dir)
    assert list(result) == ["persona_00003"]
    assert all(v is not None for v in result.values())


def test_loader_reduce_pipeline_end_to_end(tmp_path):
    # loader dict -> reduce_persona each present value -> reduce_combo.
    combo_dir = tmp_path / "combo_x"
    combo_dir.mkdir()
    for i, verdicts in enumerate([[_possible(8), _possible(9)], [_impossible(), _impossible()]], start=1):
        payload = _cache_payload(f"persona_{i:05d}", {"age_group": "25-34"}, verdicts)
        (combo_dir / f"persona_{i:05d}.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_combo_verdicts(combo_dir, expected_ids=[f"persona_{i:05d}" for i in (1, 2, 3)])
    personas = [reduce_persona(v.rounds, persona_id=k) if v is not None else None
                for k, v in loaded.items()]
    combo = reduce_combo(personas, "combo_x")
    assert combo.n_personas == 2 and combo.n_failed == 1  # persona_00003 absent
    assert combo.impossible_count == 1


# --------------------------------------------------------------------------- #
# hard-rules validation subset (the validity anchor)                          #
# --------------------------------------------------------------------------- #


def test_load_hard_rules_from_config():
    rules = load_hard_rules(_HARD_RULES_PATH)
    assert len(rules) >= 1
    rule = rules[0]
    assert rule.id == "postgraduate_before_adult_completion_age"
    assert rule.type == "incompatible_pair"
    assert "18-24" in rule.forbid_equals


def test_load_hard_rules_rejects_unsupported_type(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "rules:\n  - id: x\n    type: mystery_type\n    when: {attribute: a, equals: [1]}\n"
        "    forbid: {attribute: b, equals: [2]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported type"):
        load_hard_rules(bad)


def test_load_hard_rules_rejects_malformed(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules:\n  - id: x\n    type: incompatible_pair\n    when: {attribute: a}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_hard_rules(bad)


_RULE = HardRule(
    id="pg_age", description="", type="incompatible_pair",
    when_attribute="education_level", when_equals=frozenset({"Post-Graduate (ISCED 6)"}),
    forbid_attribute="age_group", forbid_equals=frozenset({"18-24"}), severity="S3",
)


def test_rule_fires_on_impossible_pair():
    assert rule_fires(_RULE, {"education_level": "Post-Graduate (ISCED 6)", "age_group": "18-24"}) is True
    assert rule_fires(_RULE, {"education_level": "Post-Graduate (ISCED 6)", "age_group": "35-44"}) is False


def test_rule_fires_missing_axis_raises():
    with pytest.raises(KeyError, match="age_group"):
        rule_fires(_RULE, {"education_level": "Post-Graduate (ISCED 6)"})


def test_rules_verdict_reports_fired_ids():
    impossible, fired = rules_verdict(
        [_RULE], {"education_level": "Post-Graduate (ISCED 6)", "age_group": "18-24"}
    )
    assert impossible is True and fired == ("pg_age",)


def _loaded(persona_id, attributes, verdicts):
    return LoadedPersona(persona_id=persona_id, attributes=attributes,
                         rounds=tuple(verdicts), failed_rounds=0)


def test_validate_against_hard_rules_confusion_and_recall():
    pg = {"education_level": "Post-Graduate (ISCED 6)", "age_group": "18-24"}   # rule fires
    ok = {"education_level": "Upper-Secondary", "age_group": "35-44"}            # rule silent
    personas = [
        _loaded("p1", pg, [_impossible()]),   # rule impossible + judge impossible -> both_impossible
        _loaded("p2", pg, [_possible(5)]),    # rule impossible + judge possible   -> judge MISS
        _loaded("p3", ok, [_possible(9)]),    # rule silent + judge possible       -> both_possible
        _loaded("p4", ok, [_impossible()]),   # rule silent + judge impossible     -> judge-only find
    ]
    res = validate_against_hard_rules(personas, [_RULE])
    assert res.n_sampled == 4
    assert res.n_rule_impossible == 2
    assert res.both_impossible == 1
    assert res.rule_impossible_judge_possible == 1
    assert res.both_possible == 1
    assert res.rule_possible_judge_impossible == 1
    assert res.agreement == pytest.approx(2.0 / 4.0)
    assert res.recall_on_rule_impossibilities == pytest.approx(1.0 / 2.0)
    assert res.fired_rule_counts == {"pg_age": 2}


def test_validate_no_rule_fires_recall_none():
    ok = {"education_level": "Upper-Secondary", "age_group": "35-44"}
    res = validate_against_hard_rules([_loaded("p", ok, [_possible(5)])], [_RULE])
    assert res.n_rule_impossible == 0
    assert res.recall_on_rule_impossibilities is None  # 0 denominator -> None, not NaN
    assert res.agreement == pytest.approx(1.0)


def test_validate_seeded_subsample_is_deterministic():
    ok = {"education_level": "Upper-Secondary", "age_group": "35-44"}
    personas = [_loaded(f"p{i:03d}", ok, [_possible(5)]) for i in range(20)]
    a = validate_against_hard_rules(personas, [_RULE], sample_size=5, seed=1)
    b = validate_against_hard_rules(personas, [_RULE], sample_size=5, seed=1)
    assert a.n_sampled == 5 and b.n_sampled == 5
    assert a.both_possible == b.both_possible

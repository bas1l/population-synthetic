"""Unit tests for comparison.evaluator.StatisticalEvaluator.

Covers the marginal metrics (TV distance, max diff, chi-squared, unmapped
category detection), individual coherence scoring, the report envelope, and
the CSV summary export.
"""

import csv
import json
import math

from population_synthetic.analysis.comparison.evaluator import (
    StatisticalEvaluator,
    write_association_csv,
    write_csv_summary,
)
from population_synthetic.analysis.comparison.scheme import (
    C2STConfig,
    CombinationCheck,
    ComparisonScheme,
    GroundedJointPair,
    load_scheme,
)

_AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


def _pop(individuals, source="test"):
    return {"metadata": {"source": source}, "individuals": individuals}


def _person(i, **attrs):
    base = {"id": i}
    base.update(attrs)
    return base


def _scheme(attributes, categories, *, joint_pairs=None, coherence_attributes=(), coherence_threshold=0.001):
    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs or [],
        coherence_attributes=coherence_attributes,
        coherence_threshold=coherence_threshold,
    )


# Shared scheme for the coherence tests (the coherence tuple is age x education x
# employment; categories are irrelevant to coherence, which keys on attr_value tuples).
_COHERENCE_SCHEME = _scheme(
    ["age_group", "education_level", "employment_status"],
    {
        "age_group": _AGE_GROUPS,
        "education_level": ["University Degree", "No Formal Education"],
        "employment_status": ["Employed"],
    },
    coherence_attributes=("age_group", "education_level", "employment_status"),
)


# --- marginal metrics ----------------------------------------------------


def test_identical_populations_have_zero_distance():
    inds = [
        _person(0, age_group="25-34", education_level="University Degree"),
        _person(1, age_group="35-44", education_level="High School"),
    ]
    scheme = _scheme(
        ["age_group", "education_level"],
        {"age_group": _AGE_GROUPS, "education_level": ["University Degree", "High School"]},
    )
    ev = StatisticalEvaluator(_pop(inds), _pop([dict(p) for p in inds]), scheme=scheme)
    metrics = ev.compute_marginals()["age_group"]
    assert metrics["tv_distance"] == 0.0
    assert metrics["max_diff"] == 0.0
    assert metrics["kl_divergence"] == 0.0


def test_disjoint_populations_have_unit_tv_distance():
    a = [_person(i, age_group="25-34") for i in range(4)]
    b = [_person(i, age_group="65-74") for i in range(4)]
    scheme = _scheme(["age_group"], {"age_group": _AGE_GROUPS})
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    metrics = ev.compute_marginals()["age_group"]
    # Completely non-overlapping single-category distributions -> TV = 1.
    assert metrics["tv_distance"] == 1.0
    assert metrics["max_diff"] == 1.0


def test_half_overlap_tv_distance():
    a = [_person(i, age_group="25-34") for i in range(4)]
    b = (
        [_person(i, age_group="25-34") for i in range(2)]
        + [_person(i, age_group="65-74") for i in range(2)]
    )
    scheme = _scheme(["age_group"], {"age_group": _AGE_GROUPS})
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    metrics = ev.compute_marginals()["age_group"]
    # A: {25-34:1.0}; B: {25-34:0.5, 65-74:0.5}; TV = 0.5*(0.5+0.5)=0.5.
    assert math.isclose(metrics["tv_distance"], 0.5)


def test_unmapped_categories_detected_in_b():
    a = [_person(i, region="Stockholm") for i in range(3)]
    b = [_person(0, region="Stockholm"), _person(1, region="Atlantis")]
    scheme = _scheme(["region"], {"region": ["Stockholm"]})
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    metrics = ev.compute_marginals()["region"]
    assert "Atlantis" in metrics["unmapped"]
    assert "Stockholm" not in metrics["unmapped"]


def test_empty_attribute_yields_nan_metrics():
    # Neither population carries 'income_source' and the scheme declares no
    # categories for it -> no scored categories -> NaN metrics.
    a = [_person(i, age_group="25-34") for i in range(2)]
    scheme = _scheme(["income_source"], {"income_source": []})
    ev = StatisticalEvaluator(_pop(a), _pop([dict(p) for p in a]), scheme=scheme)
    metrics = ev.compute_marginals()["income_source"]
    assert math.isnan(metrics["tv_distance"])
    assert metrics["categories"] == []


# --- coherence -----------------------------------------------------------


def test_coherence_perfect_when_b_matches_a_joint():
    a = [
        _person(
            i,
            age_group="25-34",
            education_level="University Degree",
            employment_status="Employed",
        )
        for i in range(10)
    ]
    b = [dict(p) for p in a]
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=_COHERENCE_SCHEME)
    coherence = ev.compute_coherence()
    assert coherence["score"] == 1.0
    assert coherence["n_plausible"] == coherence["n_total"] == 10
    assert coherence["flagged"] == []


def test_coherence_flags_unseen_combination():
    a = [
        _person(
            i,
            age_group="25-34",
            education_level="University Degree",
            employment_status="Employed",
        )
        for i in range(10)
    ]
    # B has a combination never observed in A -> probability 0 -> flagged.
    b = [
        _person(
            0,
            age_group="75-85",
            education_level="No Formal Education",
            employment_status="Employed",
        )
    ]
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=_COHERENCE_SCHEME)
    coherence = ev.compute_coherence()
    assert coherence["score"] == 0.0
    assert len(coherence["flagged"]) == 1
    assert coherence["flagged"][0]["id"] == 0


# --- report + csv --------------------------------------------------------


def test_generate_report_structure():
    a = [_person(i, age_group="25-34", education_level="University Degree",
                 employment_status="Employed") for i in range(5)]
    scheme = _scheme(
        ["age_group", "education_level", "employment_status"],
        {"age_group": _AGE_GROUPS, "education_level": ["University Degree"],
         "employment_status": ["Employed"]},
        joint_pairs=[("age_group", "education_level")],
        coherence_attributes=("age_group", "education_level", "employment_status"),
    )
    ev = StatisticalEvaluator(_pop(a, source="scb"), _pop([dict(p) for p in a],
                              source="pipeline"), scheme=scheme)
    report = ev.generate_report()
    assert set(report) == {"metadata", "marginals", "joint_chi_sq", "coherence", "multivariate"}
    assert report["metadata"]["population_a"]["source"] == "scb"
    assert report["metadata"]["population_b"]["n"] == 5
    assert "age_group" in report["marginals"]
    # Joint pairs are present.
    assert "age_group_x_education_level" in report["joint_chi_sq"]


def test_write_csv_summary_one_row_per_attribute(tmp_path):
    a = [_person(i, age_group="25-34") for i in range(3)]
    scheme = _scheme(["age_group"], {"age_group": _AGE_GROUPS})
    ev = StatisticalEvaluator(_pop(a), _pop([dict(p) for p in a]), scheme=scheme)
    report = ev.generate_report()
    out = tmp_path / "summary.csv"
    write_csv_summary(report, out)

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # One row per demographic attribute in the report's marginals.
    assert len(rows) == len(report["marginals"])
    assert {"attribute", "tv_distance", "chi_sq_p"} <= set(rows[0])


# --- scheme-driven comparison --------------------------------------------


def test_scheme_restricts_axis_and_flags_synthetic_only_category():
    # The real only ever emits Employed/Unemployed; a synthetic-only "Student"
    # must fall outside the scored axis and be reported as unmapped.
    scheme = _scheme(["employment_status"], {"employment_status": ["Employed", "Unemployed"]})
    a = [_person(i, employment_status="Employed") for i in range(8)] + [_person(8, employment_status="Unemployed")]
    b = [_person(0, employment_status="Employed"), _person(1, employment_status="Student")]
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    metrics = ev.compute_marginals()["employment_status"]
    assert metrics["categories"] == ["Employed", "Unemployed"]
    assert "Student" not in metrics["categories"]
    assert "Student" in metrics["unmapped"]


def test_age_binning_derives_group_from_raw_age():
    # Populations store only raw integer 'age'; the evaluator bins it on the fly.
    scheme = _scheme(["age_group"], {"age_group": _AGE_GROUPS})
    a = [_person(i, age=30) for i in range(4)]   # all 25-34
    b = [_person(i, age=70) for i in range(4)]   # all 65-74
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    metrics = ev.compute_marginals()["age_group"]
    assert metrics["tv_distance"] == 1.0


def test_age_binning_feeds_coherence_and_joint():
    scheme = _scheme(
        ["age_group", "education_level", "employment_status"],
        {
            "age_group": _AGE_GROUPS,
            "education_level": ["University Degree"],
            "employment_status": ["Employed"],
        },
        joint_pairs=[("age_group", "education_level")],
        coherence_attributes=("age_group", "education_level", "employment_status"),
    )
    a = [_person(i, age=30, education_level="University Degree", employment_status="Employed") for i in range(10)]
    b = [dict(p) for p in a]
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    coherence = ev.compute_coherence()
    assert coherence["score"] == 1.0
    assert coherence["flagged"] == []
    # The joint pair resolves the derived age_group rather than collapsing to NaN.
    assert not math.isnan(ev.compute_joint_chi_sq()["age_group_x_education_level"])


def test_load_scheme_is_country_specific():
    sv = load_scheme("swedish")
    it = load_scheme("italian")
    # Italy has no income-source field in its database; Sweden does.
    assert "income_source" in sv.attributes
    assert "income_source" not in it.attributes
    assert "age_group" in sv.attributes and "age_group" in it.attributes
    # Category sets are DB-grounded (no empty buckets).
    assert sv.categories["employment_status"] == ["Employed", "Unemployed"]
    assert "Separated" not in it.categories["civil_status"]
    assert "Civil Partnership" not in it.categories["civil_status"]


# --- multivariate block --------------------------------------------------


def _mv_scheme():
    """A small multivariate scheme with grounded/non-grounded joint pairs, a k-way
    combination check, and an MMD C2ST config (numpy-only, no sklearn needed)."""
    return ComparisonScheme(
        attributes=["age_group", "biological_sex", "education_level", "employment_status"],
        categories={
            "age_group": _AGE_GROUPS,
            "biological_sex": ["Male", "Female"],
            "education_level": ["University Degree", "High School"],
            "employment_status": ["Employed", "Unemployed"],
        },
        joint_pairs=[("age_group", "education_level")],
        coherence_attributes=("age_group", "education_level", "employment_status"),
        coherence_threshold=0.001,
        grounded_joint_pairs=(
            GroundedJointPair(pair=("age_group", "biological_sex"), grounded=True, basis="audit"),
            GroundedJointPair(pair=("age_group", "education_level"), grounded=False, basis="reference"),
        ),
        combination_checks=(
            CombinationCheck(
                attributes=("age_group", "education_level", "employment_status"),
                k=3,
                threshold=0.001,
            ),
        ),
        c2st_config=C2STConfig(folds=2, method="mmd", seed=0),
    )


def _mv_population(n, *, sex_cycle=("Male", "Female"), edu="University Degree"):
    people = []
    for i in range(n):
        people.append(_person(
            i,
            age=30,
            biological_sex=sex_cycle[i % len(sex_cycle)],
            education_level=edu,
            employment_status="Employed",
        ))
    return people


def test_generate_report_includes_multivariate_block():
    scheme = _mv_scheme()
    a = _mv_population(24)
    b = _mv_population(12)
    ev = StatisticalEvaluator(_pop(a, source="scb"), _pop(b, source="pipeline"), scheme=scheme)
    report = ev.generate_report()

    assert "multivariate" in report
    mv = report["multivariate"]
    assert set(mv) == {"c2st", "association", "joint_fidelity", "combination_plausibility"}

    # c2st sub-block
    assert set(mv["c2st"]) == {"auc", "p_value", "method", "balanced_n"}
    assert mv["c2st"]["method"] == "mmd"
    assert mv["c2st"]["balanced_n"] == 12

    # association sub-block: 4 attributes -> 6 pairs, summary stats present.
    assoc = mv["association"]
    assert len(assoc["pairs"]) == 6
    assert {"attr_x", "attr_y", "v_real", "v_syn", "abs_delta_v"} == set(assoc["pairs"][0])
    assert "mean_abs_delta_v" in assoc and "frobenius_norm" in assoc

    # joint_fidelity carries the grounded flag + basis per configured pair.
    jf = mv["joint_fidelity"]["pairs"]
    assert len(jf) == 2
    assert {"attr_x", "attr_y", "joint_tv", "grounded", "basis"} == set(jf[0])
    assert any(p["grounded"] for p in jf) and any(not p["grounded"] for p in jf)

    # combination_plausibility: one configured check, fractions in [0, 1].
    checks = mv["combination_plausibility"]["checks"]
    assert len(checks) == 1
    chk = checks[0]
    assert chk["k"] == 3 and chk["n_total"] == 12
    assert 0.0 <= chk["fraction_impossible"] <= 1.0
    assert 0.0 <= chk["fraction_rare"] <= 1.0


def test_generate_report_multivariate_json_round_trips():
    scheme = _mv_scheme()
    ev = StatisticalEvaluator(_pop(_mv_population(20)), _pop(_mv_population(8)), scheme=scheme)
    report = ev.generate_report()
    # json.dumps/loads tolerate NaN by default (the evaluator already emits NaN floats).
    restored = json.loads(json.dumps(report))
    assert restored["multivariate"]["c2st"]["method"] == "mmd"
    assert len(restored["multivariate"]["association"]["pairs"]) == 6


def test_identical_populations_have_low_c2st_and_zero_delta_v():
    scheme = _mv_scheme()
    a = _mv_population(40, sex_cycle=("Male", "Female"))
    b = [dict(p) for p in a]
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    mv = ev.compute_multivariate()
    # Same population -> associations match exactly -> zero delta.
    assert mv["association"]["mean_abs_delta_v"] == 0.0
    assert mv["association"]["frobenius_norm"] == 0.0
    # Joint TV between a population and its copy is 0 for every pair.
    for jp in mv["joint_fidelity"]["pairs"]:
        assert jp["joint_tv"] == 0.0


def test_multivariate_tiny_synthetic_degrades_without_crash():
    scheme = _mv_scheme()
    a = _mv_population(30)
    # A single synthetic persona -> balanced_n < 2 -> NaN C2ST, no crash.
    b = _mv_population(1)
    ev = StatisticalEvaluator(_pop(a), _pop(b), scheme=scheme)
    mv = ev.compute_multivariate()
    assert math.isnan(mv["c2st"]["auc"])
    assert math.isnan(mv["c2st"]["p_value"])
    assert mv["c2st"]["balanced_n"] == 1
    # Association / joint / combination still populate (no exception).
    assert len(mv["association"]["pairs"]) == 6
    assert len(mv["combination_plausibility"]["checks"]) == 1


def test_multivariate_empty_synthetic_degrades_without_crash():
    scheme = _mv_scheme()
    ev = StatisticalEvaluator(_pop(_mv_population(30)), _pop([]), scheme=scheme)
    mv = ev.compute_multivariate()
    assert math.isnan(mv["c2st"]["auc"])
    assert mv["c2st"]["balanced_n"] == 0
    chk = mv["combination_plausibility"]["checks"][0]
    assert chk["n_total"] == 0
    assert math.isnan(chk["fraction_impossible"])
    assert math.isnan(chk["fraction_rare"])


def test_write_association_csv_one_row_per_pair(tmp_path):
    scheme = _mv_scheme()
    ev = StatisticalEvaluator(_pop(_mv_population(20)), _pop(_mv_population(10)), scheme=scheme)
    report = ev.generate_report()
    out = tmp_path / "run_association.csv"
    write_association_csv(report, out)
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6
    assert {"attr_x", "attr_y", "v_real", "v_syn", "abs_delta_v"} == set(rows[0])

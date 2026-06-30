"""Unit tests for comparison.evaluator.StatisticalEvaluator.

Covers the marginal metrics (TV distance, max diff, chi-squared, unmapped
category detection), individual coherence scoring, the report envelope, and
the CSV summary export.
"""

import csv
import math

from population_synth.comparison.evaluator import (
    StatisticalEvaluator,
    write_csv_summary,
)


def _pop(individuals, source="test"):
    return {"metadata": {"source": source}, "individuals": individuals}


def _person(i, **attrs):
    base = {"id": i}
    base.update(attrs)
    return base


# --- marginal metrics ----------------------------------------------------


def test_identical_populations_have_zero_distance():
    inds = [
        _person(0, age_group="25-34", education_level="University Degree"),
        _person(1, age_group="35-44", education_level="High School"),
    ]
    ev = StatisticalEvaluator(_pop(inds), _pop([dict(p) for p in inds]))
    metrics = ev.compute_marginals()["age_group"]
    assert metrics["tv_distance"] == 0.0
    assert metrics["max_diff"] == 0.0
    assert metrics["kl_divergence"] == 0.0


def test_disjoint_populations_have_unit_tv_distance():
    a = [_person(i, age_group="25-34") for i in range(4)]
    b = [_person(i, age_group="65-74") for i in range(4)]
    ev = StatisticalEvaluator(_pop(a), _pop(b))
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
    ev = StatisticalEvaluator(_pop(a), _pop(b))
    metrics = ev.compute_marginals()["age_group"]
    # A: {25-34:1.0}; B: {25-34:0.5, 65-74:0.5}; TV = 0.5*(0.5+0.5)=0.5.
    assert math.isclose(metrics["tv_distance"], 0.5)


def test_unmapped_categories_detected_in_b():
    a = [_person(i, region="Stockholm") for i in range(3)]
    b = [_person(0, region="Stockholm"), _person(1, region="Atlantis")]
    ev = StatisticalEvaluator(_pop(a), _pop(b))
    metrics = ev.compute_marginals()["region"]
    assert "Atlantis" in metrics["unmapped"]
    assert "Stockholm" not in metrics["unmapped"]


def test_empty_attribute_yields_nan_metrics():
    # Neither population carries 'income_source' -> no categories.
    a = [_person(i, age_group="25-34") for i in range(2)]
    ev = StatisticalEvaluator(_pop(a), _pop([dict(p) for p in a]))
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
    ev = StatisticalEvaluator(_pop(a), _pop(b))
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
    ev = StatisticalEvaluator(_pop(a), _pop(b))
    coherence = ev.compute_coherence()
    assert coherence["score"] == 0.0
    assert len(coherence["flagged"]) == 1
    assert coherence["flagged"][0]["id"] == 0


# --- report + csv --------------------------------------------------------


def test_generate_report_structure():
    a = [_person(i, age_group="25-34", education_level="University Degree",
                 employment_status="Employed") for i in range(5)]
    ev = StatisticalEvaluator(_pop(a, source="scb"), _pop([dict(p) for p in a],
                              source="pipeline"))
    report = ev.generate_report()
    assert set(report) == {"metadata", "marginals", "joint_chi_sq", "coherence"}
    assert report["metadata"]["population_a"]["source"] == "scb"
    assert report["metadata"]["population_b"]["n"] == 5
    assert "age_group" in report["marginals"]
    # Joint pairs are present.
    assert "age_group_x_education_level" in report["joint_chi_sq"]


def test_write_csv_summary_one_row_per_attribute(tmp_path):
    a = [_person(i, age_group="25-34") for i in range(3)]
    ev = StatisticalEvaluator(_pop(a), _pop([dict(p) for p in a]))
    report = ev.generate_report()
    out = tmp_path / "summary.csv"
    write_csv_summary(report, out)

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # One row per demographic attribute in the report's marginals.
    assert len(rows) == len(report["marginals"])
    assert {"attribute", "tv_distance", "chi_sq_p"} <= set(rows[0])

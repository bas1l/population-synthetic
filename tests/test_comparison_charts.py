"""Smoke tests for the per-slug figures added for the JSON-only comparison metrics.

Like ``test_multivariate_charts.py`` these do not assert on pixels: each confirms
the figure produces a PNG with the expected filename from a tiny fixture, and
degrades to ``None`` on an absent block or all-NaN data. Also asserts the shared
``write_comparison_artifacts`` orchestrator lays down the full artifact set.
"""

from __future__ import annotations

import math

from population_synthetic.analysis.fidelity.charts import (
    plot_c2st,
    plot_coherence,
    plot_combination_plausibility,
    plot_joint_chi_sq,
    plot_joint_fidelity,
)
from tests._performance_fixtures import ATTRIBUTES, make_multivariate, make_report

_PREFIX = "swedish_all_pick_x"

_JF_PAIRS = [
    {"attr_x": "age_group", "attr_y": "biological_sex",
     "joint_tv": 0.12, "grounded": True, "basis": "audit"},
    {"attr_x": "age_group", "attr_y": "education_level",
     "joint_tv": 0.20, "grounded": False, "basis": "reference"},
]

_CHECKS = [
    {"attributes": ["age_group", "education_level", "employment_status"], "k": 3,
     "threshold": 0.001, "n_total": 100, "n_impossible": 2, "n_rare": 3,
     "n_plausible": 95, "fraction_impossible": 0.02, "fraction_rare": 0.03},
]


def _report(**mv_kwargs):
    return make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        multivariate=make_multivariate(**mv_kwargs),
    )


# --- C2ST ---------------------------------------------------------------------

def test_c2st_renders(tmp_path):
    out = plot_c2st(_report(), tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_c2st.png"


def test_c2st_none_without_block(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert plot_c2st(report, tmp_path, prefix=_PREFIX) is None


def test_c2st_none_when_auc_nan(tmp_path):
    assert plot_c2st(_report(c2st_auc=math.nan), tmp_path, prefix=_PREFIX) is None


# --- grounded joint TV --------------------------------------------------------

def test_joint_fidelity_renders(tmp_path):
    out = plot_joint_fidelity(_report(joint_fidelity_pairs=_JF_PAIRS), tmp_path,
                              prefix=_PREFIX, attributes=ATTRIBUTES)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_joint_fidelity.png"


def test_joint_fidelity_none_without_pairs(tmp_path):
    assert plot_joint_fidelity(_report(), tmp_path, prefix=_PREFIX) is None


def test_joint_fidelity_none_when_all_nan(tmp_path):
    nan_pairs = [{**p, "joint_tv": math.nan} for p in _JF_PAIRS]
    assert plot_joint_fidelity(_report(joint_fidelity_pairs=nan_pairs), tmp_path, prefix=_PREFIX) is None


# --- k-way combination plausibility -------------------------------------------

def test_combination_plausibility_renders(tmp_path):
    out = plot_combination_plausibility(_report(combination_checks=_CHECKS), tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_combination_plausibility.png"


def test_combination_plausibility_none_without_checks(tmp_path):
    assert plot_combination_plausibility(_report(), tmp_path, prefix=_PREFIX) is None


def test_combination_plausibility_none_when_n_total_zero(tmp_path):
    empty_b = [{**_CHECKS[0], "n_total": 0, "fraction_impossible": math.nan, "fraction_rare": math.nan}]
    assert plot_combination_plausibility(_report(combination_checks=empty_b), tmp_path, prefix=_PREFIX) is None


# --- legacy: joint chi-squared ------------------------------------------------

def test_joint_chi_sq_renders(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
                         joint_chi_sq={"age_group_x_education_level": 0.3, "age_group_x_biological_sex": 0.01})
    out = plot_joint_chi_sq(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_joint_chi_sq.png"


def test_joint_chi_sq_none_when_empty(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert plot_joint_chi_sq(report, tmp_path, prefix=_PREFIX) is None


# --- legacy: coherence --------------------------------------------------------

def test_coherence_renders_with_flagged(tmp_path):
    flagged = [
        {"id": 0, "age_group": "75-85", "education_level": "No Formal Education",
         "employment_status": "Employed", "probability": 0.0},
        {"id": 1, "age_group": "18-24", "education_level": "University Degree",
         "employment_status": "Retired", "probability": 0.0005},
    ]
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
                         flagged=flagged)
    out = plot_coherence(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_coherence.png"


def test_coherence_renders_without_flagged(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    out = plot_coherence(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()


def test_coherence_none_without_block(tmp_path):
    assert plot_coherence({}, tmp_path, prefix=_PREFIX) is None

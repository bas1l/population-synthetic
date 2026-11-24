"""Unit tests for comparison.multivariate -- the joint / multivariate metric primitives.

Covers Cramer's V (bias correction, degenerate/single-category tables), the
scheme-driven one-hot encoder (synthetic-only -> "other" block), joint TV distance
(identical -> 0, disjoint -> 1), the pairwise association matrix, and the C2ST
(indistinguishable -> AUC ~ 0.5, separable -> AUC ~ 1.0, deterministic, tiny-n guard).

The C2ST tests exercise whichever backend is installed: they force ``method="mmd"``
(numpy/scipy fallback, always available) and additionally run the scikit-learn path
when it imports.
"""

import math

import numpy as np
import pytest

from population_synthetic.analysis.fidelity.multivariate import (
    _sklearn_available,
    association_matrix,
    c2st,
    cramers_v,
    joint_tv,
    one_hot_encode,
)
from population_synthetic.analysis.fidelity.scheme import ComparisonScheme

_AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


def _scheme(attributes, categories, *, joint_pairs=None, coherence_attributes=(), coherence_threshold=0.001):
    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs or [],
        coherence_attributes=coherence_attributes,
        coherence_threshold=coherence_threshold,
    )


def _person(i, **attrs):
    base = {"id": i}
    base.update(attrs)
    return base


# --- Cramer's V ----------------------------------------------------------


def test_cramers_v_perfect_association_is_one():
    # 2x2 diagonal table -> perfect association; bias correction still yields 1.0.
    assert math.isclose(cramers_v([[10, 0], [0, 10]]), 1.0, abs_tol=1e-12)


def test_cramers_v_independent_table_is_zero():
    # Uniform table -> chi2 = 0 -> V = 0.
    assert cramers_v([[5, 5], [5, 5]]) == 0.0


def test_cramers_v_bias_corrected_exact_value():
    # Hand-computed Bergsma-corrected V for [[3,1],[1,3]]:
    #   chi2 = 2, n = 8, phi2 = 0.25
    #   phi2_corr = 0.25 - (1*1)/7 = 0.107142857
    #   r_corr - 1 = c_corr - 1 = (2 - 1/7) - 1 = 6/7
    #   V = sqrt(0.107142857 / (6/7)) = sqrt(0.125) = 0.35355339
    assert math.isclose(cramers_v([[3, 1], [1, 3]]), math.sqrt(0.125), rel_tol=1e-9)


def test_bias_correction_reduces_v_for_sparse_table():
    # Uncorrected V for [[3,1],[1,3]] is sqrt(phi2/min(r-1,c-1)) = sqrt(0.25) = 0.5.
    corrected = cramers_v([[3, 1], [1, 3]])
    assert corrected < 0.5


def test_cramers_v_single_category_returns_zero_no_divzero():
    assert cramers_v([[5, 3]]) == 0.0          # single row
    assert cramers_v([[5], [3]]) == 0.0        # single column
    assert cramers_v([[0, 0], [0, 0]]) == 0.0  # empty table


# --- one-hot encoding ----------------------------------------------------


def test_one_hot_identical_populations_encode_identically():
    scheme = _scheme(
        ["age_group", "employment_status"],
        {"age_group": _AGE_GROUPS, "employment_status": ["Employed", "Unemployed"]},
    )
    inds = [
        _person(0, age=30, employment_status="Employed"),   # 25-34
        _person(1, age=70, employment_status="Unemployed"),  # 65-74
    ]
    a = one_hot_encode(inds, scheme)
    b = one_hot_encode([dict(p) for p in inds], scheme)
    assert a.shape == (2, len(_AGE_GROUPS) + 2)
    assert np.array_equal(a, b)
    # Each individual sets exactly one column per attribute block.
    assert a.sum() == 4


def test_one_hot_synthetic_only_value_maps_to_other_all_zero_block():
    scheme = _scheme(["employment_status"], {"employment_status": ["Employed", "Unemployed"]})
    inds = [
        _person(0, employment_status="Employed"),
        _person(1, employment_status="Student"),  # synthetic-only, not in categories
        _person(2, employment_status=None),
    ]
    matrix = one_hot_encode(inds, scheme)
    assert matrix.shape == (3, 2)
    assert np.array_equal(matrix[0], [1.0, 0.0])   # Employed
    assert np.array_equal(matrix[1], [0.0, 0.0])   # Student -> all-zero "other"
    assert np.array_equal(matrix[2], [0.0, 0.0])   # None -> all-zero


def test_one_hot_raises_when_attribute_has_no_categories():
    scheme = _scheme(["mystery"], {})  # attribute declared, no category list
    with pytest.raises(KeyError):
        one_hot_encode([_person(0, mystery="x")], scheme)


# --- joint TV ------------------------------------------------------------


_JOINT_SCHEME = _scheme(
    ["age_group", "employment_status"],
    {"age_group": _AGE_GROUPS, "employment_status": ["Employed", "Unemployed"]},
)


def test_joint_tv_identical_populations_is_zero():
    a = [_person(i, age=30, employment_status="Employed") for i in range(5)]
    b = [dict(p) for p in a]
    assert joint_tv(a, b, "age_group", "employment_status", _JOINT_SCHEME) == 0.0


def test_joint_tv_disjoint_supports_is_one():
    a = [_person(i, age=30, employment_status="Employed") for i in range(5)]     # (25-34, Employed)
    b = [_person(i, age=70, employment_status="Unemployed") for i in range(5)]   # (65-74, Unemployed)
    assert math.isclose(joint_tv(a, b, "age_group", "employment_status", _JOINT_SCHEME), 1.0)


def test_joint_tv_empty_population_is_nan():
    a = [_person(i, age=30, employment_status="Employed") for i in range(3)]
    b = [_person(0, age=30, employment_status="Student")]  # out-of-grid -> no in-grid mass
    assert math.isnan(joint_tv(a, b, "age_group", "employment_status", _JOINT_SCHEME))


# --- association matrix --------------------------------------------------


def test_association_matrix_identical_populations_zero_delta():
    scheme = _scheme(
        ["age_group", "employment_status", "education_level"],
        {
            "age_group": _AGE_GROUPS,
            "employment_status": ["Employed", "Unemployed"],
            "education_level": ["University Degree", "High School"],
        },
    )
    rng = np.random.default_rng(0)
    ages = rng.integers(20, 80, size=40)
    emp = rng.choice(["Employed", "Unemployed"], size=40)
    edu = rng.choice(["University Degree", "High School"], size=40)
    inds = [_person(i, age=int(ages[i]), employment_status=emp[i], education_level=edu[i]) for i in range(40)]

    attrs = ["age_group", "employment_status", "education_level"]
    v_a = association_matrix(inds, attrs, scheme)
    v_b = association_matrix([dict(p) for p in inds], attrs, scheme)
    assert set(v_a) == {
        ("age_group", "employment_status"),
        ("age_group", "education_level"),
        ("employment_status", "education_level"),
    }
    # Identical populations -> zero |Delta V| on every pair.
    for pair in v_a:
        assert math.isclose(v_a[pair], v_b[pair], abs_tol=1e-12)


# --- C2ST ----------------------------------------------------------------


def _c2st_methods():
    methods = ["mmd"]
    if _sklearn_available():
        methods.append("sklearn")
    return methods


@pytest.mark.parametrize("method", _c2st_methods())
def test_c2st_indistinguishable_auc_near_half(method):
    rng = np.random.default_rng(0)
    x_real = rng.integers(0, 2, size=(200, 6)).astype(float)
    x_syn = rng.integers(0, 2, size=(120, 6)).astype(float)  # same distribution
    out = c2st(x_real, x_syn, method=method, folds=5, seed=1, n_repeats=3, n_permutations=50)
    assert out["method"] == method
    assert out["balanced_n"] == 120
    assert 0.35 < out["auc"] < 0.65
    assert 0.0 <= out["p_value"] <= 1.0


@pytest.mark.parametrize("method", _c2st_methods())
def test_c2st_separable_auc_near_one(method):
    rng = np.random.default_rng(0)
    x_real = rng.normal(0.0, 0.1, size=(200, 4))
    x_syn = rng.normal(1.0, 0.1, size=(120, 4))  # clearly separated
    out = c2st(x_real, x_syn, method=method, folds=5, seed=1, n_repeats=3, n_permutations=50)
    assert out["auc"] > 0.9


def test_c2st_deterministic_under_fixed_seed():
    rng = np.random.default_rng(7)
    x_real = rng.integers(0, 2, size=(150, 5)).astype(float)
    x_syn = rng.integers(0, 2, size=(80, 5)).astype(float)
    first = c2st(x_real, x_syn, method="mmd", folds=5, seed=3, n_repeats=3, n_permutations=40)
    second = c2st(x_real, x_syn, method="mmd", folds=5, seed=3, n_repeats=3, n_permutations=40)
    assert first == second


def test_c2st_tiny_population_degrades_to_nan():
    rng = np.random.default_rng(0)
    x_real = rng.integers(0, 2, size=(100, 4)).astype(float)
    x_syn = rng.integers(0, 2, size=(1, 4)).astype(float)  # balanced_n = 1 < 2
    out = c2st(x_real, x_syn, method="mmd", folds=5, seed=1)
    assert out["balanced_n"] == 1
    assert math.isnan(out["auc"])
    assert math.isnan(out["p_value"])


def test_c2st_unknown_method_raises():
    with pytest.raises(ValueError):
        c2st(np.zeros((10, 2)), np.zeros((10, 2)), method="bogus")

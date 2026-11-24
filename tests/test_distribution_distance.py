"""Unit tests for the shared distribution distances (TV, TV similarity, Cramer).

Hand-worked values, broadcasting, and the closeness prototype's golden per-combination
TV and Cramer distances (``closeness_shape/combination_outcomes.csv``) recomputed from
the first-round histograms.
"""

from __future__ import annotations

import numpy as np
import pytest

from population_synthetic.analysis.utils.distribution_distance import (
    cramer_distance,
    total_variation_distance,
    total_variation_similarity,
)
from tests._closeness_fixtures import combination_outcomes, first_round_histograms


def test_total_variation_hand_worked():
    p = [0.5, 0.5, 0.0]
    q = [0.0, 0.5, 0.5]
    assert total_variation_distance(p, q) == pytest.approx(0.5)
    assert total_variation_similarity(p, q) == pytest.approx(0.5)
    assert total_variation_distance(p, p) == 0.0
    assert total_variation_distance([1.0, 0.0], [0.0, 1.0]) == 1.0
    assert isinstance(total_variation_distance(p, q), float)


def test_cramer_hand_worked_and_order_awareness():
    # CDF gaps over the first two cut points: (0.5 - 0) and (1.0 - 0.5) -> sqrt(0.5).
    assert cramer_distance([0.5, 0.5, 0.0], [0.0, 0.5, 0.5]) == pytest.approx(np.sqrt(0.5))
    # Moving all mass one level vs two levels: TV cannot tell, Cramer can.
    near = cramer_distance([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    far = cramer_distance([1.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    assert near == pytest.approx(1.0) and far == pytest.approx(np.sqrt(2.0))
    assert total_variation_distance([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == total_variation_distance(
        [1.0, 0.0, 0.0], [0.0, 0.0, 1.0])


def test_broadcasting_over_leading_axes():
    rng = np.random.default_rng(1)
    p = rng.dirichlet(np.ones(5), size=(4, 3))
    q = rng.dirichlet(np.ones(5))
    tv = total_variation_distance(p, q)
    assert tv.shape == (4, 3)
    assert tv[2, 1] == pytest.approx(total_variation_distance(p[2, 1], q))
    assert cramer_distance(p, q[None, None, :]).shape == (4, 3)


def test_mismatched_level_axes_raise():
    with pytest.raises(ValueError):
        total_variation_distance([0.5, 0.5], [1.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        cramer_distance(0.5, [1.0])


def test_golden_tv_and_cramer_per_combination():
    keys, counts, reference = first_round_histograms()
    expected = {(r["model"], r["strategy"]): r for r in combination_outcomes()}
    p = counts / counts.sum(axis=1, keepdims=True)
    q = reference / reference.sum()
    tv = total_variation_distance(p, q)
    cramer = cramer_distance(p, q)
    for key, got_tv, got_cramer in zip(keys, tv, cramer):
        assert got_tv == pytest.approx(expected[key]["tv"], abs=1e-12)
        assert got_cramer == pytest.approx(expected[key]["cramer"], abs=1e-12)

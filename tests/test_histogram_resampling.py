"""Unit tests for the individual-level histogram bootstrap.

Shapes, totals, determinism, independence from unit order, the multinomial shortcut
against a naive unit-by-unit draw, validation, and the closeness prototype's
sampling-noise floor (``closeness_shape/shape_meta.json``, ``null_floor``).
"""

from __future__ import annotations

import numpy as np
import pytest

from population_synthetic.analysis.utils.distribution_distance import cramer_distance, total_variation_distance
from population_synthetic.analysis.utils.histogram_resampling import (
    joint_bootstrap_histograms,
    reference_self_resampling,
)
from population_synthetic.analysis.utils.stats_tests import cliffs_delta_from_histograms
from tests._closeness_fixtures import first_round_histograms, one_hot_units


def _units(levels, k=5):
    return np.eye(k)[np.asarray(levels)]


def test_joint_shapes_totals_and_seed():
    groups = [_units([0, 1, 1, 4]), _units([2, 2, 3])]
    ref = _units([0, 1, 2, 3, 4, 4])
    g, r = joint_bootstrap_histograms(groups, ref, iterations=50, seed=1)
    assert g.shape == (50, 2, 5) and r.shape == (50, 5)
    assert np.all(g[:, 0].sum(axis=1) == 4) and np.all(g[:, 1].sum(axis=1) == 3) and np.all(r.sum(axis=1) == 6)
    g2, r2 = joint_bootstrap_histograms(groups, ref, iterations=50, seed=1)
    assert np.array_equal(g, g2) and np.array_equal(r, r2)
    g3, _ = joint_bootstrap_histograms(groups, ref, iterations=50, seed=2)
    assert not np.array_equal(g, g3)


def test_unit_order_does_not_matter():
    levels = [0, 3, 1, 1, 4, 2, 2, 2]
    shuffled = [2, 1, 2, 4, 0, 2, 3, 1]
    ref = _units([0, 1, 2, 3, 4])
    a, ra = joint_bootstrap_histograms([_units(levels)], ref, iterations=30, seed=7)
    b, rb = joint_bootstrap_histograms([_units(shuffled)], ref[::-1], iterations=30, seed=7)
    assert np.array_equal(a, b) and np.array_equal(ra, rb)


def test_fractional_units_resample_as_whole_individuals():
    # An individual scored (8, 9) carries 0.5 on each; it is drawn whole, so every
    # replicate's weight at 8 equals its weight at 9 when this is the only split unit.
    split = np.zeros(11)
    split[[8, 9]] = 0.5
    units = np.vstack([split, np.eye(11)[10], np.eye(11)[10]])
    g, _ = joint_bootstrap_histograms([units], np.eye(11)[[3, 4]], iterations=200, seed=3)
    assert np.array_equal(g[:, 0, 8], g[:, 0, 9])
    assert np.allclose(g[:, 0].sum(axis=1), 3.0)


def test_multinomial_shortcut_matches_a_naive_unit_draw():
    rng = np.random.default_rng(12)
    levels = rng.integers(0, 5, size=40)
    ref_levels = rng.integers(0, 5, size=30)
    g, r = joint_bootstrap_histograms([_units(levels)], _units(ref_levels), iterations=6000, seed=4)
    fast = cliffs_delta_from_histograms(g[:, 0], r)
    naive_rng = np.random.default_rng(5)
    naive = np.array([
        cliffs_delta_from_histograms(np.bincount(naive_rng.choice(levels, 40), minlength=5),
                                     np.bincount(naive_rng.choice(ref_levels, 30), minlength=5))
        for _ in range(6000)
    ])
    assert fast.mean() == pytest.approx(naive.mean(), abs=0.01)
    assert fast.std() == pytest.approx(naive.std(), rel=0.05)


def test_reference_is_drawn_once_per_replicate():
    # Two identical groups against one reference: their deltas differ replicate by
    # replicate (own draws) but share the reference's draw, so their correlation is high.
    rng = np.random.default_rng(6)
    group = _units(rng.integers(0, 5, size=200))
    ref = _units(rng.integers(0, 5, size=20))
    g, r = joint_bootstrap_histograms([group, group], ref, iterations=3000, seed=8)
    d = cliffs_delta_from_histograms(g, r[:, None, :])
    assert not np.array_equal(d[:, 0], d[:, 1])
    assert np.corrcoef(d[:, 0], d[:, 1])[0, 1] > 0.7


@pytest.mark.parametrize(
    "groups,reference",
    [
        ([], np.eye(3)),
        ([np.eye(3)], np.eye(4)),
        ([np.zeros((0, 3))], np.eye(3)),
        ([np.array([[0.5, 0.4, 0.0]])], np.eye(3)),
        ([np.array([[1.5, -0.5, 0.0]])], np.eye(3)),
        ([np.array([[np.nan, 1.0, 0.0]])], np.eye(3)),
    ],
)
def test_invalid_populations_raise(groups, reference):
    with pytest.raises(ValueError):
        joint_bootstrap_histograms(groups, reference, iterations=5, seed=0)


def test_bad_counts_raise():
    with pytest.raises(ValueError):
        joint_bootstrap_histograms([np.eye(3)], np.eye(3), iterations=0, seed=0)
    with pytest.raises(ValueError):
        reference_self_resampling(np.eye(3), n_sample=0, iterations=5, seed=0)


def test_self_resampling_shapes_and_sizes():
    sample, ref = reference_self_resampling(_units([0, 1, 1, 2, 4]), n_sample=12, iterations=40, seed=2)
    assert sample.shape == ref.shape == (40, 5)
    assert np.all(sample.sum(axis=1) == 12) and np.all(ref.sum(axis=1) == 5)


def test_golden_sampling_noise_floor():
    # closeness_shape/shape_meta.json null_floor["100_vs_100"] (20,000 replicates): mean TV
    # 0.17186, mean Cramer 0.17173, mean |delta| 0.06521 for two independent 100-draws
    # from the reference's first-round distribution.
    _, _, reference = first_round_histograms()
    sample, ref = reference_self_resampling(one_hot_units(reference), n_sample=100, iterations=20000, seed=1)
    p = sample / sample.sum(axis=1, keepdims=True)
    q = ref / ref.sum(axis=1, keepdims=True)
    assert total_variation_distance(p, q).mean() == pytest.approx(0.17185950000000003, abs=0.002)
    assert cramer_distance(p, q).mean() == pytest.approx(0.17172748560181986, abs=0.004)
    assert np.abs(cliffs_delta_from_histograms(sample, ref)).mean() == pytest.approx(0.06520821, abs=0.002)

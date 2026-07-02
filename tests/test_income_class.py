"""Unit tests for population.income_class bracket → socioeconomic classifier.

Covers ``median_from_brackets`` and ``classify_brackets``: threshold banding,
proportional splitting of brackets that straddle a class boundary, probability
normalisation, and the loud-failure paths.
"""

import math

import pytest

from population_synthetic.generators.real.income_class import (
    classify_brackets,
    median_from_brackets,
)


# --- median_from_brackets ------------------------------------------------


def test_median_picks_bracket_at_50th_percentile():
    # Cumulative counts: 10, 30, 60 -> target 30 reached at the 2nd midpoint.
    midpoints = [50.0, 150.0, 250.0]
    counts = [10.0, 20.0, 30.0]
    assert median_from_brackets(midpoints, counts) == 150.0


def test_median_returns_last_midpoint_when_target_unreached():
    # Degenerate: a single bracket always returns its own midpoint.
    assert median_from_brackets([100.0], [5.0]) == 100.0


def test_median_raises_on_nonpositive_total():
    with pytest.raises(ValueError, match="positive"):
        median_from_brackets([50.0, 150.0], [0.0, 0.0])


def test_median_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        median_from_brackets([50.0, 150.0], [10.0])


# --- classify_brackets ---------------------------------------------------


def test_classify_single_bracket_below_poverty():
    # median=100 -> poverty < 60. Bracket (0, 60) sits entirely in Poverty.
    probs = classify_brackets(edges=[(0.0, 60.0)], counts=[10.0], median=100.0)
    assert probs["Poverty"] == 1.0
    assert probs["Working Class"] == 0.0
    assert probs["Middle Class"] == 0.0
    assert probs["Wealthy"] == 0.0


def test_classify_splits_bracket_straddling_threshold():
    # median=100 -> poverty cutoff at 60. Bracket (40, 80) is split by width:
    # (40,60) -> Poverty, (60,80) -> Working Class, 50/50.
    probs = classify_brackets(edges=[(40.0, 80.0)], counts=[10.0], median=100.0)
    assert probs["Poverty"] == pytest.approx(0.5)
    assert probs["Working Class"] == pytest.approx(0.5)


def test_classify_probabilities_sum_to_one():
    edges = [(0.0, 60.0), (60.0, 100.0), (100.0, 200.0), (200.0, 500.0)]
    counts = [5.0, 8.0, 12.0, 3.0]
    probs = classify_brackets(edges=edges, counts=counts, median=100.0)
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-9)
    # Each bracket lands in its own class here (no straddling).
    assert probs["Poverty"] == pytest.approx(5 / 28)
    assert probs["Wealthy"] == pytest.approx(3 / 28)


def test_classify_skips_zero_count_brackets():
    probs = classify_brackets(
        edges=[(0.0, 60.0), (200.0, 500.0)], counts=[10.0, 0.0], median=100.0
    )
    assert probs["Poverty"] == 1.0
    assert probs["Wealthy"] == 0.0


def test_classify_zero_width_bracket_uses_lower_edge():
    probs = classify_brackets(edges=[(50.0, 50.0)], counts=[7.0], median=100.0)
    assert probs["Poverty"] == 1.0


def test_classify_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        classify_brackets(edges=[(0.0, 60.0)], counts=[1.0, 2.0], median=100.0)


def test_classify_raises_on_nonpositive_median():
    with pytest.raises(ValueError, match="median must be positive"):
        classify_brackets(edges=[(0.0, 60.0)], counts=[1.0], median=0.0)


def test_classify_raises_when_all_counts_zero():
    with pytest.raises(ValueError, match="cannot classify"):
        classify_brackets(edges=[(0.0, 60.0)], counts=[0.0], median=100.0)

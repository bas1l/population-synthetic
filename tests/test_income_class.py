"""Unit tests for population.income_class bracket → socioeconomic classifier.

Covers ``median_from_brackets`` and ``classify_brackets``: threshold banding,
proportional splitting of brackets that straddle a class boundary, probability
normalisation, and the loud-failure paths.
"""

import json
import math
from pathlib import Path

import pytest

from population_synthetic.generators.real.income_class import (
    classify_brackets,
    median_from_brackets,
)

# --- median_from_brackets ------------------------------------------------


def test_median_interpolates_inside_the_median_bracket():
    # Cumulative 10, 30, 60; target 30 is reached exactly at the top of bracket 2.
    edges = [(0.0, 100.0), (100.0, 200.0), (200.0, 300.0)]
    assert median_from_brackets(edges, [10.0, 20.0, 30.0]) == pytest.approx(200.0)
    # Target 25 lies 15/20 of the way through bracket 2 (not its midpoint 150).
    assert median_from_brackets(edges, [10.0, 20.0, 20.0]) == pytest.approx(175.0)


def test_median_of_a_single_bracket_is_its_centre():
    assert median_from_brackets([(50.0, 150.0)], [5.0]) == pytest.approx(100.0)


def test_median_skips_empty_brackets():
    # The empty middle bracket cannot hold the median even when the cumulative
    # count sits exactly on the target at its lower edge.
    edges = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
    assert median_from_brackets(edges, [5.0, 0.0, 5.0]) == pytest.approx(10.0)


def test_median_raises_on_nonpositive_total():
    with pytest.raises(ValueError, match="positive"):
        median_from_brackets([(0.0, 100.0), (100.0, 200.0)], [0.0, 0.0])


def test_median_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        median_from_brackets([(0.0, 100.0), (100.0, 200.0)], [10.0])


def test_median_raises_on_negative_count():
    with pytest.raises(ValueError, match="non-negative"):
        median_from_brackets([(0.0, 100.0), (100.0, 200.0)], [10.0, -1.0])


def test_median_raises_on_unordered_edges():
    with pytest.raises(ValueError, match="ascending"):
        median_from_brackets([(100.0, 200.0), (0.0, 100.0)], [1.0, 1.0])


_ORACLE = Path(__file__).parent / "data" / "income_class" / "scb_median_oracle_2024.json"


def _oracle_cells():
    data = json.loads(_ORACLE.read_text(encoding="utf-8"))
    edges = [tuple(e) for e in data["edges_tkr"]]
    return [(edges, c) for c in data["cells"]]


@pytest.mark.parametrize(
    "edges, cell", _oracle_cells(), ids=lambda v: f"{v['age_band']}-{v['sex']}" if isinstance(v, dict) else ""
)
def test_median_matches_scb_published_median(edges, cell):
    # Regression oracle: SCB's own published 2024 median (SamForvInk1, HE0110J8)
    # for each 5-year band x sex, against the median interpolated from the same
    # year's bracket counts (SamForvInk1a). The bracket-midpoint estimator this
    # replaced was off by up to 45.3 tkr here (men 45-49: 550 vs 504.7);
    # interpolation is within 3.3 tkr in all 20 cells.
    estimate = median_from_brackets(edges, cell["counts"])
    assert abs(estimate - cell["published_median_tkr"]) <= 5.0


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

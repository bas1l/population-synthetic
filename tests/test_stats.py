"""Numeric tests for the median / percentile / entropy primitives.

These pin the **nearest-rank** percentile convention chosen for the project.
The import is repointed to ``analysis._stats`` in Phase 2; the asserted values
do not change because the convention is preserved.
"""

from __future__ import annotations

import math

import pytest

from population_synth.llm_metrics.shared._stats import median as _median
from population_synth.llm_metrics.shared._stats import percentile as _percentile
from population_synth.llm_metrics.shared._stats import shannon_entropy as _shannon_entropy


def test_median_odd_even_empty():
    assert _median([3, 1, 2]) == 2
    assert _median([4, 1, 3, 2]) == 2.5
    assert _median([]) is None
    assert _median([7]) == 7


def test_percentile_nearest_rank():
    data = [10, 20, 30, 40]
    # nearest-rank idx = ceil(p/100 * n) - 1, clamped to [0, n-1]
    assert _percentile(data, 25) == 10   # ceil(1.0)-1 = 0
    assert _percentile(data, 50) == 20   # ceil(2.0)-1 = 1
    assert _percentile(data, 75) == 30   # ceil(3.0)-1 = 2
    assert _percentile(data, 95) == 40   # ceil(3.8)-1 = 3
    assert _percentile(data, 100) == 40
    # Nearest-rank always returns a value actually present in the sample.
    assert _percentile(data, 95) in data


def test_percentile_single_and_empty():
    assert _percentile([5], 95) == 5
    assert _percentile([], 50) is None


def test_shannon_entropy():
    assert _shannon_entropy({}) == 0.0
    assert _shannon_entropy({"a": 1}) == 0.0
    assert _shannon_entropy({"a": 1, "b": 1}) == pytest.approx(1.0)
    assert _shannon_entropy({"a": 2, "b": 2}) == pytest.approx(1.0)
    # -(0.75*log2 0.75 + 0.25*log2 0.25)
    expected = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
    assert _shannon_entropy({"a": 3, "b": 1}) == pytest.approx(expected)

"""distribution_distance.py -- Distances between two discrete distributions.

The one home of the distribution distances the analysis layer computes, so the
attribute-level fidelity score and any later closeness measure share a single
definition rather than an inline copy each:

* :func:`total_variation_distance` -- ``TV(p, q) = 1/2 sum_i |p_i - q_i|`` in ``[0, 1]``
  (Levin, Peres & Wilmer). Order-blind: it treats the levels as nominal.
* :func:`total_variation_similarity` -- ``1 - TV``, the higher-is-better form the
  fidelity figures and rankings read.
* :func:`cramer_distance` -- the L2 distance between the two cumulative distribution
  functions over **ordered** levels, ``sqrt(sum_{c < K-1} (F_p(c) - F_q(c))^2)``; unlike
  TV it grows with how far probability mass moved, not only with how much moved.

All three take probability vectors along the **last** axis and broadcast over leading
axes (bootstrap replicates, groups). They do not normalise: a caller holding counts
divides by the total first, so a zero-total histogram is the caller's decision, never
silently mapped to a distance.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _pair(p: Any, q: Any) -> tuple[np.ndarray, np.ndarray]:
    """Both inputs as float arrays over the same number of levels, or ``ValueError``."""
    a = np.asarray(p, dtype=float)
    b = np.asarray(q, dtype=float)
    if a.ndim == 0 or b.ndim == 0 or a.shape[-1] != b.shape[-1]:
        raise ValueError(f"distributions must share their last (level) axis, got shapes {a.shape} and {b.shape}")
    return a, b


def _scalar_or_array(result: np.ndarray) -> float | np.ndarray:
    return float(result) if result.ndim == 0 else result


def total_variation_distance(p: Any, q: Any) -> float | np.ndarray:
    """``1/2 sum_i |p_i - q_i|`` along the last axis (a float for two 1-D inputs).

    Raises ``ValueError`` when the two inputs do not share their last-axis length.
    """
    a, b = _pair(p, q)
    return _scalar_or_array(0.5 * np.abs(a - b).sum(axis=-1))


def total_variation_similarity(p: Any, q: Any) -> float | np.ndarray:
    """``1 - TV(p, q)``: 1 for identical distributions, 0 for disjoint supports."""
    return _scalar_or_array(1.0 - np.asarray(total_variation_distance(p, q)))


def cramer_distance(p: Any, q: Any) -> float | np.ndarray:
    """L2 distance between the CDFs of *p* and *q* over ascending ordered levels.

    ``sqrt(sum_{c=0}^{K-2} (F_p(c) - F_q(c))^2)`` with ``F(c) = sum_{i <= c} p_i``; the
    last cut point is omitted because both CDFs reach 1 there. Its range is
    ``[0, sqrt(K - 1)]``.

    Raises ``ValueError`` when the two inputs do not share their last-axis length.
    """
    a, b = _pair(p, q)
    gap = np.cumsum(a, axis=-1) - np.cumsum(b, axis=-1)
    return _scalar_or_array(np.sqrt((gap[..., :-1] ** 2).sum(axis=-1)))

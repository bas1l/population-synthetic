"""histogram_resampling.py -- Bootstrap resampling of individuals summarised as histograms.

A population here is a set of **units** (individuals), each carrying a weight vector
over ``K`` ordered levels that sums to 1: a one-hot row for an individual with one
score, or ``1/r`` on each of its ``r`` scored rounds. A population's histogram is the
column sum of its unit rows. Resampling units with replacement and re-summing is the
individual-level bootstrap; everything downstream (a distance to a reference, Cliff's
delta, a decomposition over many populations) is a function of the resampled
histograms and belongs to the caller.

* :func:`joint_bootstrap_histograms` -- one replicate resamples **every** group and the
  reference together, the reference **once**. Because the reference is shared by every
  group-vs-reference outcome, redrawing it once per replicate is what carries its
  sampling error into a statistic computed across the groups; drawing it afresh per
  group would understate that shared component.
* :func:`reference_self_resampling` -- the sampling-noise baseline: two independent
  resamples of the reference itself, one at a matched size ``n``, so the distance a
  group of ``n`` individuals would show *with no difference at all* can be read beside
  the observed one.

Drawing ``n`` units with replacement is the multinomial over the population's
**distinct** unit rows, so the draw is made on those counts (``O(distinct rows)`` per
replicate). Distinct rows are found by :func:`numpy.unique`, which sorts them, so the
result does not depend on the order in which a population's units are listed.
Randomness is one local :func:`numpy.random.default_rng` per call, seeded by the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

#: Tolerance on each unit row summing to 1.
_ROW_SUM_TOLERANCE = 1e-9


def _unit_rows(units: Any, name: str, n_levels: int | None) -> np.ndarray:
    """A population's ``(n, K)`` unit-weight rows, validated, or ``ValueError``."""
    arr = np.asarray(units, dtype=float)
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise ValueError(f"{name} must be a non-empty (units, levels) array, got shape {arr.shape}")
    if n_levels is not None and arr.shape[1] != n_levels:
        raise ValueError(f"{name} has {arr.shape[1]} levels, expected {n_levels}")
    if not np.isfinite(arr).all() or (arr < 0).any():
        raise ValueError(f"{name} holds a negative, NaN or inf weight")
    bad = np.flatnonzero(np.abs(arr.sum(axis=1) - 1.0) > _ROW_SUM_TOLERANCE)
    if bad.size:
        raise ValueError(f"{name}: {bad.size} unit row(s) do not sum to 1 (first at index {int(bad[0])})")
    return arr


def _resample(rows: np.ndarray, size: int, iterations: int, rng: np.random.Generator) -> np.ndarray:
    """``(iterations, K)`` histograms of *size* units drawn with replacement from *rows*."""
    patterns, counts = np.unique(rows, axis=0, return_counts=True)
    draws = rng.multinomial(size, counts / counts.sum(), size=iterations)
    return draws.astype(float) @ patterns


def _check_count(value: int, name: str) -> int:
    if isinstance(value, bool) or int(value) != value or value < 1:
        raise ValueError(f"{name} must be an integer >= 1, got {value!r}")
    return int(value)


def joint_bootstrap_histograms(
    groups: Sequence[Any],
    reference: Any,
    *,
    iterations: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Joint individual-level bootstrap of every group and one shared reference.

    *groups* is a sequence of ``(n_g, K)`` unit-weight arrays and *reference* one
    ``(n_ref, K)`` array, all over the same ``K`` levels. Each replicate resamples the
    reference once and every group within itself, each at its own size.

    Returns ``(group_histograms, reference_histograms)`` of shapes
    ``(iterations, len(groups), K)`` and ``(iterations, K)``; each histogram sums to its
    population's unit count.

    The draw order is the reference, then the groups in the order given, so the group
    order is part of the input: a caller wanting output independent of its processing
    order sorts the groups by a stable key first.

    Raises ``ValueError`` when there are no groups, a population is empty, the level
    counts differ, a weight is negative/NaN/inf, a unit row does not sum to 1, or
    ``iterations < 1``.
    """
    iterations = _check_count(iterations, "iterations")
    if len(groups) == 0:
        raise ValueError("joint_bootstrap_histograms needs at least one group")
    ref = _unit_rows(reference, "reference", None)
    rows = [_unit_rows(g, f"groups[{i}]", ref.shape[1]) for i, g in enumerate(groups)]
    rng = np.random.default_rng(seed)
    ref_hists = _resample(ref, ref.shape[0], iterations, rng)
    group_hists = np.empty((iterations, len(rows), ref.shape[1]), dtype=float)
    for g, unit_rows in enumerate(rows):
        group_hists[:, g, :] = _resample(unit_rows, unit_rows.shape[0], iterations, rng)
    return group_hists, ref_hists


def reference_self_resampling(
    reference: Any,
    *,
    n_sample: int,
    iterations: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Two independent resamples of the reference: the no-difference baseline.

    Each replicate draws ``n_sample`` units and, independently, ``n_ref`` units (the
    reference's own size) with replacement from the reference. A distance between the
    two is what a population of ``n_sample`` individuals drawn from the reference
    itself would show against the observed reference -- pure sampling noise -- so an
    observed group-vs-reference distance is read against it at the group's own ``n``.

    Returns ``(sample_histograms, reference_histograms)``, both ``(iterations, K)``
    (drawn in that order from one local generator seeded with *seed*).

    Raises ``ValueError`` on an invalid reference (see :func:`joint_bootstrap_histograms`)
    or when ``n_sample`` or ``iterations`` is below 1.
    """
    iterations = _check_count(iterations, "iterations")
    n_sample = _check_count(n_sample, "n_sample")
    ref = _unit_rows(reference, "reference", None)
    rng = np.random.default_rng(seed)
    sample_hists = _resample(ref, n_sample, iterations, rng)
    ref_hists = _resample(ref, ref.shape[0], iterations, rng)
    return sample_hists, ref_hists

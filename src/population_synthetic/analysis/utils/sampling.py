"""sampling.py -- Seeded, size-equalising subsample of a mapped population.

Fidelity and multivariate metrics (C2ST, joint chi-squared, per-pair joint TV)
are sample-size sensitive, so comparing a 100-person synthetic population against
a 250-person one is not apples-to-apples. :func:`subsample_population` caps a
mapped population's ``individuals`` list to a requested size ``n`` with a seeded,
without-replacement draw, restoring equivalent population size for the calculation.

The draw reuses the RNG idiom already used by the C2ST test
(:mod:`population_synthetic.analysis.fidelity.multivariate`):
``np.random.default_rng(seed).choice(len(individuals), size=n, replace=False)``.
Drawn indices are sorted so the capped list preserves the original relative order
of the retained rows and the same (seed, population) pair always yields the same
subset -- a reproducibility requirement for cross-model comparison.

Undersize handling is loud, not silent: a population with fewer than ``n``
individuals cannot meet the requested equalised size, so the full population is
returned and a warning is printed (the comparison still runs, just below the
requested size). ``n=None`` disables capping entirely and returns the population
unchanged.
"""

from __future__ import annotations

import numpy as np


def select_indices(total: int, n: int, seed: int = 0) -> list[int]:
    """Return a reproducible, sorted, without-replacement draw of *n* indices in ``[0, total)``.

    The shared index-selection primitive behind both the fidelity subsample
    (:func:`subsample_population`) and the population-cap task, so the two stay
    algorithmically consistent. It uses the project's established RNG idiom --
    ``np.random.default_rng(seed).choice(total, size=n, replace=False)`` -- and sorts
    the drawn indices so retained items keep their original relative order and a given
    ``(total, n, seed)`` triple always reproduces the same subset.

    Args:
        total: Number of available items to draw from (the population/collection size).
        n: Number of indices to draw. When ``n >= total`` every index is returned
            (there is nothing to subsample).
        seed: Seed for the without-replacement draw (default ``0``); the same seed and
            ``(total, n)`` reproduce the same indices.

    Returns:
        A sorted ``list[int]`` of distinct indices in ``range(total)``: all ``total``
        indices when ``n >= total``, otherwise exactly ``n`` seeded-drawn indices.

    Raises:
        ValueError: If ``total`` or ``n`` is negative.
    """
    if total < 0:
        raise ValueError(f"select_indices requires a non-negative total; got {total!r}.")
    if n < 0:
        raise ValueError(f"select_indices requires a non-negative n; got {n!r}.")
    if n >= total:
        return list(range(total))
    idx = np.random.default_rng(seed).choice(total, size=n, replace=False)
    return [int(i) for i in sorted(idx)]


def subsample_population(population: dict, n: int | None, seed: int = 0) -> dict:
    """Return a copy of *population* with ``individuals`` capped to *n*.

    The cap is a seeded, without-replacement draw of *n* row indices, sorted so the
    retained rows keep their original relative order and the draw is reproducible
    for a given ``(seed, population)`` pair. ``metadata['n']`` is updated to the
    retained count.

    Args:
        population: A mapped population dict with an ``individuals`` list and a
            ``metadata`` dict (``metadata['n']`` is the recorded size).
        n: Target size. ``None`` disables capping and returns the population
            unchanged. Must be a positive integer otherwise.
        seed: Seed for the without-replacement draw (default ``0``); the same seed
            and population reproduce the same subset.

    Returns:
        The population unchanged when ``n`` is ``None``, when the population
        already holds exactly ``n`` individuals (silently -- the requested size is
        met, there is simply nothing to draw), or when it holds fewer than ``n``
        (a loud warning is printed in that case alone, since the requested
        equalised size cannot be met). Otherwise a
        shallow copy whose ``individuals`` list holds the ``n`` drawn rows (in
        original order, referenced not copied) and whose ``metadata`` copy records
        ``metadata['n'] = n``.

    Raises:
        ValueError: If ``n`` is not ``None`` and is zero or negative.
    """
    if n is None:
        return population

    if n <= 0:
        raise ValueError(f"subsample_population requires a positive n or None; got {n!r}.")

    individuals = population["individuals"]
    available = len(individuals)

    if available == n:
        return population

    if available < n:
        print(
            f"WARNING: requested subsample size n={n} but population has only "
            f"{available} individuals; using the full population (equalised size not met)."
        )
        return population

    idx = select_indices(available, n, seed)
    subset = [individuals[i] for i in idx]

    capped = dict(population)
    capped["individuals"] = subset
    capped["metadata"] = {**population.get("metadata", {}), "n": len(subset)}
    return capped

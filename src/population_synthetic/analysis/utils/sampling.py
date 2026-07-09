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
        The population unchanged when ``n`` is ``None`` or when the population
        already has ``<= n`` individuals (a loud warning is printed in the latter
        case, since the requested equalised size cannot be met). Otherwise a
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

    if available <= n:
        print(
            f"WARNING: requested subsample size n={n} but population has only "
            f"{available} individuals; using the full population (equalised size not met)."
        )
        return population

    idx = np.random.default_rng(seed).choice(available, size=n, replace=False)
    subset = [individuals[i] for i in sorted(idx)]

    capped = dict(population)
    capped["individuals"] = subset
    capped["metadata"] = {**population.get("metadata", {}), "n": len(subset)}
    return capped

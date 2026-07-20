"""marginals.py -- per-category marginal proportions for one attribute over one population.

Pure, chart-agnostic, country-agnostic computation shared by the fidelity charts
(``analysis/fidelity/charts.py``) and the method-significance marginal-progression
charts. This module knows nothing about matplotlib, countries, strategies, file
paths, or the real-vs-synthetic distinction -- it is arithmetic over a list of
individual records only.

The single authority for the proportion definition (``count / total_non_null``)
lives here so the fidelity evaluator and every descriptive chart agree exactly.
"""

from __future__ import annotations

import logging
from collections import Counter

from population_synthetic.analysis.fidelity.evaluator import attr_value

logger = logging.getLogger(__name__)


def compute_proportions(
    individuals: list[dict],
    attr: str,
    categories: list[str],
) -> tuple[dict[str, float], list[str]]:
    """Per-category proportion vector for one *attr* over one population.

    Proportion definition matches the fidelity evaluator:
    ``count(category) / total_non_null``, where *total_non_null* is the number of
    individuals whose value for *attr* is non-null. Extraction goes through
    :func:`attr_value`, so the on-demand ``age_group`` binning stays identical to
    the evaluator's (a population that stores raw integer ``age`` is binned here
    exactly as it is when scored).

    Args:
        individuals: population records, each a ``dict``.
        attr: the attribute whose marginal is computed.
        categories: the requested category axis (config-driven ordering). A
            category with zero occurrences yields an explicit ``0.0`` bar --
            distinct from a category absent from this list. Must not be ``None``:
            the axis is a required, config-sourced input, so a missing axis fails
            loud rather than silently defaulting to the observed set.

    Returns:
        ``(proportions, extra_categories)`` where

        * ``proportions`` maps **every** requested category to its proportion.
          A category that never occurs is an explicit ``0.0``; when the attribute
          is null for every individual (``total_non_null == 0``) every requested
          category is ``0.0``.
        * ``extra_categories`` lists categories observed in the data but absent
          from *categories*, in first-seen order. These are surfaced (returned
          and logged at ``WARNING``) rather than silently dropped, so an axis that
          does not cover the data is visible to the caller.

    Raises:
        TypeError: if *categories* is ``None`` (the axis is required).
    """
    if categories is None:
        raise TypeError(
            "compute_proportions requires an explicit `categories` axis "
            "(config-sourced); got None."
        )

    counts: Counter = Counter()
    for ind in individuals:
        val = attr_value(ind, attr)
        if val is not None:
            counts[val] += 1

    total = sum(counts.values())
    if total == 0:
        proportions = {cat: 0.0 for cat in categories}
    else:
        proportions = {cat: counts.get(cat, 0) / total for cat in categories}

    requested = set(categories)
    extra_categories = [cat for cat in counts if cat not in requested]
    if extra_categories:
        logger.warning(
            "compute_proportions(attr=%r): %d category value(s) present in the "
            "data but absent from the requested axis (surfaced, not dropped): %s",
            attr,
            len(extra_categories),
            extra_categories,
        )

    return proportions, extra_categories

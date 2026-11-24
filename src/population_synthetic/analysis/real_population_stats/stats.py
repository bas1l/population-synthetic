"""stats.py -- per-category counts/N/proportion/percent for one attribute, one population.

Pure computation over a list of individual records. Knows nothing about matplotlib,
file paths, country ids, or the analysis registry -- it is arithmetic only.

The proportion itself is not re-derived here: it is taken verbatim from
:func:`population_synthetic.analysis.utils.marginals.compute_proportions`, the single
authority for ``count / total_non_null`` shared with the fidelity evaluator and every
descriptive chart, so this module can never drift from that definition. The only
genuinely new computation is the per-category raw ``count`` and the shared
``total_non_null`` (N), neither of which ``compute_proportions`` returns. Both are
derived from the SAME :func:`attr_value` extraction ``compute_proportions`` uses
internally, so ``age`` is binned into ``age_group`` identically here.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass

from population_synthetic.analysis.fidelity.evaluator import attr_value
from population_synthetic.analysis.utils.marginals import compute_proportions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CategoryStat:
    """One config-axis category's stats for one attribute, one population.

    ``total`` is the attribute's shared denominator (``total_non_null``, i.e. N) and
    is identical across every :class:`CategoryStat` returned for the same
    ``compute_category_stats`` call -- a genuine 0% (``total > 0``) is thereby
    distinguishable from an all-null attribute (``total == 0``) purely by inspecting
    any one row's ``total``.
    """

    value: str
    count: int
    total: int
    proportion: float
    percent: float


def compute_category_stats(
    individuals: list[dict],
    attr: str,
    categories: list[str],
) -> tuple[list[CategoryStat], list[str]]:
    """Per-category :class:`CategoryStat` rows for one *attr* over one population.

    Args:
        individuals: population records, each a ``dict``.
        attr: the attribute whose per-category stats are computed.
        categories: the requested category axis (config-driven ordering, e.g.
            ``ComparisonScheme.categories[attr]``). Required -- see
            :func:`compute_proportions` for the fail-fast contract on ``None``.

    Returns:
        ``(rows, extra_categories)`` where:

        * ``rows`` has exactly one :class:`CategoryStat` per requested category, in
          the given order. A category with zero occurrences yields an explicit
          ``count=0, proportion=0.0, percent=0.0`` row (a real zero). When the
          attribute is null for every individual (``total_non_null == 0``), every
          row carries ``total=0`` -- the caller detects this "all-null" case by
          checking ``rows[0].total == 0`` (equivalently, any row, since ``total``
          is shared) and should skip rendering/writing for that attribute rather
          than emit an all-zero figure.
        * ``extra_categories`` lists category values observed in the data but
          absent from *categories*, in first-seen order (mirrors
          :func:`compute_proportions`, which already logs these at ``WARNING`` --
          not re-logged here to avoid a duplicate warning per call).

    Raises:
        TypeError: if *categories* is ``None`` (propagated from
            :func:`compute_proportions`).
    """
    proportions, extra_categories = compute_proportions(individuals, attr, categories)

    counts: Counter = Counter()
    for ind in individuals:
        val = attr_value(ind, attr)
        if val is not None:
            counts[val] += 1
    total = sum(counts.values())

    rows = [
        CategoryStat(
            value=cat,
            count=counts.get(cat, 0),
            total=total,
            proportion=proportions[cat],
            percent=proportions[cat] * 100.0,
        )
        for cat in categories
    ]

    return rows, extra_categories

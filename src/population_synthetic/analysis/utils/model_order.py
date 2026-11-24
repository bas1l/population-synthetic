"""model_order.py -- ``model_ranking``'s published model order, as a reusable ranking.

The model x method heatmap of ``model_ranking`` orders its rows by a two-tier rule: a
model with at least one full-n cell is **Tier 1** and ranks on its full-n cells by
``(-max, -mean, model_id)``; a model with none is **Tier 2** and ranks, provisionally, on
all of its cells by ``(-max, model_id)``. Other figures that set models side by side must
put them in that same order, or two sibling figures of one manuscript would disagree on
which model comes first. This module is the rule's one home: ``model_ranking/charts.py``
draws through it, and every other consumer asks it rather than re-deriving the order.

It computes a ranking, so it is **not** part of the presentation layer: it sits beside
:mod:`~population_synthetic.analysis.utils.cap_index`, whose full-n predicate it applies.

The module knows nothing about matplotlib, display labels, which figure or process is
asking, or where the performance result lives on disk -- the caller loads the
``{country}_performance.json`` dict and the cap index and hands both in.

Failure policy: fail-fast. A combination the cap index does not carry raises (through
:meth:`CapIndex.is_full_n`), an unknown strategy id raises (through
:func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`), and
:func:`align_to_ranking` raises on a ranked model its caller does not hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.cap_index import CapIndex


@dataclass(frozen=True)
class _ModelRow:
    """One model's row of the grid, with its tier and its ordering key.

    *values* holds the overall TV-similarity per method in column order, ``NaN`` where
    the ``(model, method)`` combination is absent from the run. *counts* holds the
    persona count per method (``None`` for an absent combination) and *full* whether
    that cell met its own slug's requested cap.

    The ordering key is recorded alongside the row rather than recomputed at sort time
    because the row marginal prints it: the figure must show the quantity the rows were
    actually sorted by, and a second derivation could disagree with the first.
    """

    model: str
    values: np.ndarray
    counts: list[int | None]
    full: list[bool]
    tier: int
    best_value: float | None
    best_method: str | None
    key_mean: float | None
    key_cells: int


def _row_summary(
    values: np.ndarray,
    scope: list[int],
    strategies: list[str],
) -> tuple[float | None, str | None, float | None, int]:
    """``(max, argmax method, mean, count)`` over the finite cells of *scope*.

    *scope* is given in column (complexity) order and the comparison is strict, so a
    within-row tie on the maximum resolves to the first method in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`. NaN
    cells are excluded from all four outputs -- a missing value is not a zero, and
    must not enter an ordering key. Returns ``(None, None, None, 0)`` when *scope*
    holds no finite cell, which is a defined state (the row has no ordering key), not
    an error.
    """
    best_value: float | None = None
    best_method: str | None = None
    total = 0.0
    count = 0
    for j in scope:
        v = float(values[j])
        if np.isnan(v):
            continue
        count += 1
        total += v
        if best_value is None or v > best_value:
            best_value = v
            best_method = strategies[j]
    if count == 0:
        return None, None, None, 0
    return best_value, best_method, total / count, count


def _model_method_rows(
    result: dict[str, Any],
    requested_n: CapIndex,
    models: list[str],
    strategies: list[str],
) -> list[_ModelRow]:
    """Regroup ``result["combos"]`` into one :class:`_ModelRow` per model.

    The tier partition and the ordering key are computed here, from ``n`` against each
    slug's own ``requested_n`` (:class:`~population_synthetic.analysis.utils.cap_index.CapIndex`) --
    Tier 1 is a model with at least one full-n cell and ranks on those cells only;
    Tier 2 is a model with none and ranks, provisionally, on all of its cells. A cell
    the run never produced is neither: it contributes no evidence and no value.
    """
    by_cell = {
        (combo["model"], combo["strategy"]): (slug, combo)
        for slug, combo in result["combos"].items()
    }

    rows: list[_ModelRow] = []
    for model in models:
        values = np.full(len(strategies), np.nan)
        counts: list[int | None] = []
        full: list[bool] = []
        for j, strategy in enumerate(strategies):
            entry = by_cell.get((model, strategy))
            if entry is None:
                counts.append(None)
                full.append(False)
                continue
            slug, combo = entry
            values[j] = float(combo["overall"]["tv_similarity_mean"])
            n = int(combo["n"])
            counts.append(n)
            full.append(requested_n.is_full_n(slug, n))

        tier = 1 if any(full) else 2
        if tier == 1:
            scope = [j for j in range(len(strategies)) if full[j]]
        else:
            scope = [j for j in range(len(strategies)) if counts[j] is not None]
        best_value, best_method, key_mean, key_cells = _row_summary(values, scope, strategies)
        rows.append(
            _ModelRow(
                model=model, values=values, counts=counts, full=full, tier=tier,
                best_value=best_value, best_method=best_method,
                key_mean=key_mean, key_cells=key_cells,
            )
        )
    return rows


def _tier1_sort_key(row: _ModelRow) -> tuple[int, float, float, str]:
    """``(-max_over_full_n, -mean_over_full_n, model_id)``, keyless rows last.

    A row whose full-n cells are all NaN has no defined key: it sorts last *within its
    tier* by the explicit leading flag rather than by comparing against NaN, and it
    stays in Tier 1 -- it has full-n cells, their values are missing, which is a
    different failure from thin evidence.
    """
    if row.best_value is None:
        return (1, 0.0, 0.0, row.model)
    return (0, -row.best_value, -(row.key_mean or 0.0), row.model)


def _tier2_sort_key(row: _ModelRow) -> tuple[int, float, str]:
    """``(-max_over_all_cells, model_id)``, keyless rows last (same explicit rule)."""
    if row.best_value is None:
        return (1, 0.0, row.model)
    return (0, -row.best_value, row.model)


def ranked_model_order(result: dict[str, Any], requested_n: CapIndex) -> list[str]:
    """Model ids in ``model_ranking``'s published order: Tier 1, then Tier 2.

    Reads ``models`` and ``strategies`` off ``result["metadata"]`` and applies the same
    rows and keys the model x method heatmap sorts by, with the strategies in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order` so every
    ordering key is accumulated in the heatmap's own column order.

    Args:
        result: The built performance comparison
            (``model_ranking.builder.build_performance_comparison``, or the
            ``{country}_performance.json`` it was serialised to).
        requested_n: The gate's per-slug requested cap
            (:func:`~population_synthetic.analysis.utils.cap_index.load_cap_index`).

    Returns:
        Every model id of ``result["metadata"]["models"]``, ranked; empty when the
        result carries no model.

    Raises:
        KeyError: If a combination of *result* has no entry in *requested_n*.
        ValueError: If a strategy id is unknown to the strategy family config.
    """
    metadata = result["metadata"]
    models: list[str] = metadata["models"]
    strategies = strategy_complexity_order(metadata["strategies"])
    rows = _model_method_rows(result, requested_n, models, strategies)
    tier1 = sorted([r for r in rows if r.tier == 1], key=_tier1_sort_key)
    tier2 = sorted([r for r in rows if r.tier == 2], key=_tier2_sort_key)
    return [row.model for row in tier1 + tier2]


def align_to_ranking(present: list[str], ranked: list[str]) -> tuple[list[str], int]:
    """Order the models a figure holds by *ranked*, unranked ones last.

    Args:
        present: The model ids the caller's grid actually holds, in any order.
        ranked: The published order (:func:`ranked_model_order`).

    Returns:
        ``(ordered, first_unranked)``: *ranked* followed by the models of *present* the
        ranking does not know, in their *present* order, and the index at which those
        unranked models begin -- the datum a separating rule is drawn from. It equals
        ``len(ordered)`` when every present model is ranked.

    Raises:
        ValueError: If either list repeats an id, or if *ranked* holds a model absent
            from *present* -- the ranking and the grid then describe different runs,
            and silently dropping the model would hide that.
    """
    for name, ids in (("present", present), ("ranked", ranked)):
        duplicates = sorted({m for m in ids if ids.count(m) > 1})
        if duplicates:
            raise ValueError(f"Model ids repeat in {name}: {duplicates}")
    held = set(present)
    missing = [m for m in ranked if m not in held]
    if missing:
        raise ValueError(
            f"The model ranking holds model(s) {missing} that the grid does not. The ranking "
            f"and the grid must describe the same run; re-run the upstream task that dropped "
            f"them rather than aligning a partial grid. Grid models: {sorted(present)}"
        )
    known = set(ranked)
    unranked = [m for m in present if m not in known]
    return list(ranked) + unranked, len(ranked)


def ranked_grid_columns(present: list[str], ranked: list[str]) -> list[str]:
    """The models a fixed-width grid draws as columns, in the published order.

    A stricter reading of the same ranking than :func:`align_to_ranking`, for a figure
    with no room for a labelled "unranked" group:

    * a ranked model the grid does not hold is **not a column** -- it has nothing to draw
      (a model whose every combination was withdrawn by the gate is the live case), so
      *ranked* is first narrowed to the models of *present*;
    * a grid model the ranking does not know **raises** -- appending it after the ranked
      ones would publish a column order no sibling figure shares.

    It composes :func:`align_to_ranking` rather than changing its contract.

    Raises:
        ValueError: If either list repeats an id, or a model of *present* is absent
            from *ranked*.
    """
    held = set(present)
    ordered, first_unranked = align_to_ranking(present, [m for m in ranked if m in held])
    if first_unranked < len(ordered):
        raise ValueError(
            f"Model(s) {ordered[first_unranked:]} are on the grid but not in the model "
            "ranking, so they have no published column position. Re-run "
            "scripts/analyze/rank_models.py over the same models."
        )
    return ordered

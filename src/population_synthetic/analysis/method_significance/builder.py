"""builder.py -- Build the per-country method/model significance analysis.

Assembles, for one country's
:class:`~population_synthetic.analysis.model_ranking.loader.ComboPerformance`
records, the per-attribute significance of the generation **method** (the ordered
strategy axis) and the **model** on Total-Variation fidelity, plus the overall
Demšar model comparison and the estimable model x method interaction.

Design constraints (governed by the data reality, see the plan and
``docs/development/model-method-significance-recap.md``):

* **n = 1 per (model, method, category) cell** -- LLM generation has no seed, so
  there are no within-cell replicates. The demographic categories (attributes)
  are used as the blocking/replication factor (Demšar 2006).
* **Absent != zero.** A combo that was not run, or an attribute whose
  ``tv_distance`` is ``NaN`` (degenerate marginal), is an *absent* cell recorded
  with an explicit ``None`` marker -- never imputed and never confused with a
  real TV of ``0.0``. Every blocked test (Friedman, Page's L) requires complete
  blocks, so incomplete rows/columns are dropped **and recorded**, not silently
  discarded.
* **Rank-based first.** TV is bounded ``[0, 1]`` and heteroscedastic near ``0``,
  so the headline tests are rank-based (Page's L, Friedman/Kendall's W) with a
  logit-linked mixed model for the estimable overall interaction; polynomial
  contrasts test -- rather than assume -- monotonicity.
* **Multiplicity is named.** The per-attribute method and model p-values are each
  Benjamini-Hochberg (FDR) corrected across attributes; both raw and adjusted are
  stored.

The built structure is directly JSON-serialisable;
:func:`write_method_significance_json` and :func:`write_method_significance_csv`
persist it.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.model_ranking.loader import ComboPerformance
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.stats_tests import (
    benjamini_hochberg,
    friedman_test,
    mixed_logit_interaction,
    nemenyi_pairwise,
    nemenyi_posthoc,
    page_trend_test,
)

# Config-driven method-comparison figure settings (bracketed-pair mode + star
# thresholds); the single source of truth is the JSON, loaded fail-fast below.
DEFAULT_COMPARISON_CONFIG_PATH = (
    PROJECT_ROOT / "config" / "analysis" / "method_significance" / "comparison.json"
)

# Separator for a method-pair key in the serialised pairwise-p / bracket maps.
_PAIR_SEP = "|"

def _orthogonal_contrasts(k: int) -> tuple[np.ndarray, np.ndarray]:
    """Linear and quadratic orthogonal polynomial contrasts for *k* ordered levels.

    The method axis is equally spaced by construction (rank 1..k), so the classical
    coefficients are just the centred level index and its centred square. For the
    canonical ``k = 5`` axis this reproduces the textbook vectors exactly --
    ``[-2, -1, 0, 1, 2]`` and ``[2, -1, -2, -1, 2]`` -- so no published contrast
    estimate moves; for other *k* the coefficients are proportional to the classical
    table, which leaves the t/p and the slope sign unchanged.

    Used to *test*, not assume, monotonicity.
    """
    index = np.arange(k, dtype=float)
    linear = index - index.mean()
    squared = linear ** 2
    return linear, squared - squared.mean()

_CAVEATS = (
    "n = 1 per (model, method, category) cell -- LLM generation has no seed, so "
    "there are no within-cell replicates; the demographic categories are used as "
    "the blocking/replication factor (Demšar 2006), which is why the *overall* "
    "model x method interaction is estimable but the *per-category* interaction is "
    "descriptive only (no p-value is claimed at that grain). Categories are not "
    "independent replicates (age/income/region correlate), so they are modelled as "
    "a random effect in the mixed model and treated as pseudo-replicates elsewhere; "
    "the per-attribute p-values are indicative evidence, BH-FDR corrected across "
    "attributes. TV is bounded [0,1] and heteroscedastic near 0, hence rank-based "
    "tests plus a logit-linked mixed model rather than raw-TV ANOVA."
)


def load_comparison_config(path: str | Path = DEFAULT_COMPARISON_CONFIG_PATH) -> dict[str, Any]:
    """Load and validate the method-comparison figure config (fail-fast).

    The config declares ``pairs_mode`` (which method pairs get a significance
    bracket) constrained to ``allowed_pairs_modes``, plus ``star_thresholds`` (the
    p-value -> star-symbol cutoffs) and the ``ns_symbol`` for a non-significant
    pair. Everything the figure needs about pair selection and star mapping lives
    here, not in code -- there is no baked-in mode list or threshold fallback.

    Raises :class:`FileNotFoundError` when the file is missing and
    :class:`ValueError` when its shape is malformed or ``pairs_mode`` is not one of
    the declared ``allowed_pairs_modes``.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Method-comparison config not found: {path}. Expected "
            "config/analysis/method_significance/comparison.json."
        )
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Method-comparison config must be a JSON object, got {type(raw).__name__}: {path}")

    allowed = raw.get("allowed_pairs_modes")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(m, str) for m in allowed):
        raise ValueError(
            f"Method-comparison config {path} must have a non-empty 'allowed_pairs_modes' "
            f"list of strings, got {allowed!r}."
        )

    pairs_mode = raw.get("pairs_mode")
    if pairs_mode not in allowed:
        raise ValueError(
            f"Method-comparison config {path} has unknown pairs_mode {pairs_mode!r}; "
            f"must be one of {allowed}."
        )

    thresholds = raw.get("star_thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        raise ValueError(
            f"Method-comparison config {path} must have a non-empty 'star_thresholds' list, "
            f"got {thresholds!r}."
        )
    for entry in thresholds:
        if (not isinstance(entry, dict) or not isinstance(entry.get("max_p"), (int, float))
                or not isinstance(entry.get("symbol"), str)):
            raise ValueError(
                f"Method-comparison config {path} star_thresholds entries must be "
                f"{{'max_p': number, 'symbol': str}}, got {entry!r}."
            )

    if not isinstance(raw.get("ns_symbol"), str):
        raise ValueError(
            f"Method-comparison config {path} must have a string 'ns_symbol', got {raw.get('ns_symbol')!r}."
        )
    return raw


def significance_cutoff(star_thresholds: list[dict[str, Any]]) -> float:
    """The p below which a pair earns *at least one* star (the loosest star cutoff).

    Returns ``max(max_p)`` over the config ``star_thresholds`` -- i.e. the ``*``
    cutoff (``0.05`` in the standard convention). By construction this is exactly
    the boundary at which :func:`_p_to_stars` stops returning the ``ns`` symbol, so
    "significant" == "has at least one star". The cutoff is **read from config**
    (single source of truth); it is never a hardcoded literal.

    Raises :class:`ValueError` on an empty ``star_thresholds`` list (fail-fast).
    """
    if not star_thresholds:
        raise ValueError("significance_cutoff needs a non-empty star_thresholds list")
    return max(float(entry["max_p"]) for entry in star_thresholds)


def resolve_pairs(
    methods: list[str],
    pairs_mode: str,
    *,
    pairwise_p: dict[str, float] | None = None,
    alpha: float | None = None,
) -> list[tuple[str, str]]:
    """Resolve which method pairs get a bracket, from the config ``pairs_mode``.

    *methods* are the compared methods in complexity order. Modes:

    * ``adjacent`` -- consecutive complexity steps ``(m_i, m_{i+1})``.
    * ``all`` -- every unordered pair.
    * ``vs-baseline`` -- every method vs the simplest (``methods[0]``).
    * ``significant-only`` -- **every** unordered pair (not just adjacent) filtered
      to those whose Nemenyi p (from *pairwise_p*) is ``<= alpha``; requires both
      *pairwise_p* (a ``"a|b" -> p`` map) and *alpha* (the config-derived
      significance cutoff, see :func:`significance_cutoff`). Non-significant pairs
      get no bracket, so ``ns`` is never drawn in this mode.

    Pairs are returned in complexity order (left method simpler than right). An
    unknown *pairs_mode*, or ``significant-only`` without its *pairwise_p*/*alpha*,
    raises :class:`ValueError` (fail-fast; never a silent default).
    """
    all_pairs = [(a, b) for a, b in combinations(methods, 2)]
    if pairs_mode == "adjacent":
        return list(zip(methods[:-1], methods[1:]))
    if pairs_mode == "all":
        return all_pairs
    if pairs_mode == "vs-baseline":
        if not methods:
            return []
        base = methods[0]
        return [(base, m) for m in methods[1:]]
    if pairs_mode == "significant-only":
        if pairwise_p is None:
            raise ValueError("pairs_mode 'significant-only' needs pairwise_p to select pairs")
        if alpha is None:
            raise ValueError(
                "pairs_mode 'significant-only' needs alpha (the config-derived "
                "significance cutoff, e.g. significance_cutoff(star_thresholds))"
            )
        selected: list[tuple[str, str]] = []
        for a, b in all_pairs:
            p = pairwise_p.get(_pair_key(a, b))
            if p is not None and p <= alpha:
                selected.append((a, b))
        return selected
    raise ValueError(
        f"Unknown pairs_mode {pairs_mode!r}; expected one of "
        "'adjacent', 'all', 'vs-baseline', 'significant-only'."
    )


def _pair_key(a: str, b: str) -> str:
    """Serialised key for a method pair (``"a|b"``), stable in the given order."""
    return f"{a}{_PAIR_SEP}{b}"


def _library_versions() -> dict[str, str | None]:
    """Record acting library versions for provenance (``None`` if absent)."""
    out: dict[str, str | None] = {}
    for dist, key in (("statsmodels", "statsmodels"),
                      ("scikit-posthocs", "scikit_posthocs"),
                      ("scipy", "scipy")):
        try:
            out[key] = version(dist)
        except PackageNotFoundError:
            out[key] = None
    return out


def _tv(record: ComboPerformance, attr: str) -> float | None:
    """TV distance of *record* at *attr*, or ``None`` for an absent cell (NaN).

    Returns an explicit ``None`` absent marker for a ``NaN`` ``tv_distance``
    (degenerate marginal) so it is never imputed nor confused with a real ``0``.
    """
    value = record.marginals[attr].get("tv_distance")
    if value is None:
        return None
    val = float(value)
    return val if val == val else None  # NaN -> absent


def _slope_sign(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _polynomial_contrast(complete_matrix: np.ndarray, coeffs: np.ndarray) -> dict[str, Any]:
    """A repeated-measures polynomial contrast over 5 ordered methods.

    *complete_matrix* is ``models x 5`` (only models with all 5 methods present).
    Per model the contrast value ``c . tv`` is formed, then a one-sample t-test
    across models tests whether its mean differs from 0. Fewer than 2 models, or
    zero between-model variance, yields ``p = None`` with a note (no bogus test).
    """
    if complete_matrix.shape[0] < 2:
        return {"estimate": None, "t": None, "p": None, "slope_sign": None,
                "note": "need >=2 complete models for the contrast"}
    per_model = complete_matrix @ coeffs
    estimate = float(np.mean(per_model))
    if float(np.std(per_model)) == 0.0:
        return {"estimate": estimate, "t": None, "p": None,
                "slope_sign": _slope_sign(estimate),
                "note": "zero between-model variance in the contrast"}
    t_stat, p_val = stats.ttest_1samp(per_model, 0.0)
    return {"estimate": estimate, "t": float(t_stat), "p": float(p_val),
            "slope_sign": _slope_sign(estimate)}


def _attribute_grid(
    by_ms: dict[tuple[str, str], ComboPerformance],
    models: list[str],
    attr: str,
    method_order: list[str],
) -> dict[str, Any]:
    """Build one attribute's model x method cell grid and its complete sub-grid.

    *method_order* is the resolved method axis (complexity order); rank = index + 1.
    Returns the raw ``cells`` (``model -> {rank -> tv|None}``, the absent marker
    preserved), the ``complete_models`` (present and non-absent under every method),
    the ``models x k`` complete matrix, and the count of absent cells.
    """
    k = len(method_order)
    cells: dict[str, dict[int, float | None]] = {}
    absent = 0
    for model in models:
        row: dict[int, float | None] = {}
        for rank, strategy in enumerate(method_order, start=1):
            record = by_ms.get((model, strategy))
            value = _tv(record, attr) if record is not None else None
            row[rank] = value
            if value is None:
                absent += 1
        cells[model] = row

    complete_models = [m for m in models if all(cells[m][r] is not None for r in range(1, k + 1))]
    matrix = np.array(
        [[float(cells[m][r]) for r in range(1, k + 1)] for m in complete_models],
        dtype=float,
    ) if complete_models else np.empty((0, k))
    return {"cells": cells, "complete_models": complete_models,
            "matrix": matrix, "absent_cells": absent}


def _per_attribute_tests(
    matrix: np.ndarray,
    complete_models: list[str],
    all_models: list[str],
    k: int,
) -> dict[str, Any]:
    """Per-attribute method trend (Page's L + contrasts) and model omnibus (Friedman).

    *matrix* is ``complete_models x k`` (methods in complexity order). Fewer than
    2 complete models makes both tests degenerate -> a recorded skip note.
    """
    dropped = [m for m in all_models if m not in complete_models]
    if matrix.shape[0] < 2:
        note = f"need >=2 models complete across all {k} methods, got {matrix.shape[0]}"
        return {
            "n_models_complete": int(matrix.shape[0]),
            "dropped_models": dropped,
            "method_trend": {"page": None, "linear_contrast": None,
                             "quadratic_contrast": None, "p_raw": None, "note": note},
            "model_omnibus": {"friedman": None, "p_raw": None, "note": note},
        }

    # Page's L: blocks = complete models (rows), treatments = the k ordered methods.
    order = list(range(k))
    page = page_trend_test(matrix, order)
    p_one = page.get("p")
    # Either-direction trend: two-sided p from the one-sided ordered p.
    p_two = None if p_one is None else float(2.0 * min(p_one, 1.0 - p_one))
    page["p_two_sided"] = p_two

    linear_coeffs, quadratic_coeffs = _orthogonal_contrasts(k)
    linear = _polynomial_contrast(matrix, linear_coeffs)
    quadratic = _polynomial_contrast(matrix, quadratic_coeffs)

    # Friedman over models: blocks = the k methods (rows), treatments = models.
    friedman = friedman_test(matrix.T)

    return {
        "n_models_complete": int(matrix.shape[0]),
        "dropped_models": dropped,
        "method_trend": {"page": page, "linear_contrast": linear,
                         "quadratic_contrast": quadratic, "p_raw": p_two},
        "model_omnibus": {"friedman": friedman, "p_raw": friedman.get("p")},
    }


def _per_attribute_model_trends(cells: dict[str, dict[int, float | None]], k: int) -> dict[str, Any]:
    """Descriptive TV(method) trend per model (OLS slope, Spearman rho, Delta).

    Flagged ``n = k`` descriptive -- **no p-value is claimed at this grain**
    (per-category interaction is not estimable at n = 1). ``delta_m5_m1`` keeps its
    name for output-schema stability (the canonical axis has five methods); it is
    always the *last minus first* method on the resolved axis.
    """
    out: dict[str, Any] = {}
    for model, row in cells.items():
        ranks = [r for r in range(1, k + 1) if row[r] is not None]
        values = [float(row[r]) for r in ranks]
        n = len(values)
        slope: float | None = None
        rho: float | None = None
        delta: float | None = None
        if n >= 2 and len(set(values)) > 1:
            slope = float(np.polyfit(ranks, values, 1)[0])
        if n >= 3 and len(set(values)) > 1:
            rho = float(stats.spearmanr(ranks, values).statistic)
        if row[1] is not None and row[k] is not None:
            delta = float(row[k]) - float(row[1])
        out[model] = {
            "n_methods": n,
            "ols_slope": slope,
            "slope_sign": _slope_sign(slope),
            "spearman_rho": rho,
            "delta_m5_m1": delta,
            "descriptive": True,
        }
    return out


def _overall_model_comparison(
    by_ms: dict[tuple[str, str], ComboPerformance],
    models: list[str],
    attributes: list[str],
    method_order: list[str],
) -> dict[str, Any]:
    """Demšar model comparison: Friedman across models over category x method blocks.

    Each block is a (category, method) cell measured once per model; only blocks
    complete across every model are used. Feeds Friedman + Nemenyi (with the CD
    value) for a critical-difference diagram in Phase 3.
    """
    block_rows: list[list[float]] = []
    for attr in attributes:
        for strategy in method_order:
            values = [_tv(by_ms.get((m, strategy)), attr) if by_ms.get((m, strategy)) is not None else None
                      for m in models]
            if all(v is not None for v in values):
                block_rows.append([float(v) for v in values])
    n_blocks = len(block_rows)
    if len(models) < 2 or n_blocks < 2:
        return {"models": models, "n_blocks": n_blocks, "block_type": "category_x_method",
                "friedman": None, "nemenyi": None,
                "note": f"need >=2 models and >=2 complete blocks, got {len(models)} models / {n_blocks} blocks"}
    matrix = np.array(block_rows, dtype=float)
    friedman = friedman_test(matrix)
    nemenyi = nemenyi_posthoc(matrix)
    # Average Friedman rank per model (1 = lowest TV = best) over the blocks, for
    # the critical-difference diagram. Computed here (not in charts) so rendering
    # stays strictly downstream of the statistics.
    block_ranks = np.vstack([stats.rankdata(row) for row in matrix])
    avg_ranks = {m: float(r) for m, r in zip(models, block_ranks.mean(axis=0))}
    return {"models": models, "n_blocks": n_blocks, "block_type": "category_x_method",
            "friedman": friedman, "nemenyi": nemenyi, "avg_ranks": avg_ranks}


def _overall_method_trend(
    by_ms: dict[tuple[str, str], ComboPerformance],
    models: list[str],
    attributes: list[str],
    method_order: list[str],
) -> dict[str, Any]:
    """Overall Page's L method trend: blocks = category x model, treatments = k methods."""
    block_rows: list[list[float]] = []
    for attr in attributes:
        for model in models:
            values = [_tv(by_ms.get((model, s)), attr) if by_ms.get((model, s)) is not None else None
                      for s in method_order]
            if all(v is not None for v in values):
                block_rows.append([float(v) for v in values])
    n_blocks = len(block_rows)
    if n_blocks < 2:
        return {"page": None, "n_blocks": n_blocks,
                "note": f"need >=2 complete (category x model) blocks, got {n_blocks}"}
    matrix = np.array(block_rows, dtype=float)
    page = page_trend_test(matrix, list(range(len(method_order))))
    p_one = page.get("p")
    page["p_two_sided"] = None if p_one is None else float(2.0 * min(p_one, 1.0 - p_one))
    return {"page": page, "n_blocks": n_blocks}


def _overall_interaction(
    by_ms: dict[tuple[str, str], ComboPerformance],
    attributes: list[str],
    method_rank: dict[str, int],
) -> dict[str, Any]:
    """Long-format ``logit(TV) ~ model*method_rank + (1|category)`` mixed fit."""
    import pandas as pd

    rows: list[dict[str, Any]] = []
    for attr in attributes:
        for (model, strategy), record in by_ms.items():
            value = _tv(record, attr)
            if value is not None:
                rows.append({"tv": value, "model": model,
                             "method_rank": method_rank[strategy], "category": attr})
    frame = pd.DataFrame(rows)
    if frame.empty or frame["model"].nunique() < 2 or frame["category"].nunique() < 2:
        return {"interaction": None, "eta_sq": None, "converged": False,
                "note": "need >=2 models and >=2 categories with present cells for the interaction fit"}
    return mixed_logit_interaction(frame)


def _dominant_factor(method_p_bh: float | None, model_p_bh: float | None, alpha: float) -> str | None:
    """Per-attribute dominant factor from the BH-adjusted method vs model p-values."""
    m_sig = method_p_bh is not None and method_p_bh < alpha
    o_sig = model_p_bh is not None and model_p_bh < alpha
    if m_sig and o_sig:
        return "method" if method_p_bh <= model_p_bh else "model"
    if m_sig:
        return "method"
    if o_sig:
        return "model"
    if method_p_bh is None and model_p_bh is None:
        return None
    return "none"


def _overall_dominant_factor(eta_sq: dict[str, float] | None) -> str | None:
    """Overall factor dominance from the mixed model's eta^2 decomposition."""
    if not eta_sq:
        return None
    share = {k: eta_sq[k] for k in ("model", "method") if k in eta_sq}
    if not share:
        return None
    return max(share, key=share.get)


# =========================================================================== #
# Method-comparison figure statistics (models as blocks, methods as treatments) #
#                                                                             #
# This block keys on **TV-similarity = 1 - tv_distance** (higher = better),   #
# unlike the per-attribute trend/omnibus blocks above (which key on raw TV-   #
# distance). The rank-based Friedman/Nemenyi p-values are invariant to that    #
# monotone sign flip, but the reported per-method ``means`` are on the         #
# similarity scale so the figure's bars read "taller = more faithful".         #
# Minimum 3 complete models required to *chart* a panel (recorded but flagged  #
# below that).                                                                 #
# =========================================================================== #

_MIN_COMPLETE_MODELS = 3  # panels with fewer complete models are recorded but not charted


def _tv_sim(record: ComboPerformance | None, attr: str) -> float | None:
    """TV-*similarity* (``1 - tv_distance``) of *record* at *attr*, or ``None``.

    Reads the loader-computed ``tv_similarity`` map, which already omits NaN /
    degenerate attributes -- so a missing key is an *absent* cell (never imputed,
    never confused with a real ``0.0`` similarity).
    """
    if record is None:
        return None
    return record.tv_similarity.get(attr)


def _overall_tv_sim(record: ComboPerformance | None) -> float | None:
    """A model's overall TV-similarity: mean across its scorable categories.

    Mirrors ``model_ranking``'s ``overall.tv_similarity_mean`` (mean of the
    per-attribute ``tv_similarity`` values, NaN attributes already excluded).
    Returns ``None`` when no attribute is scorable (an absent overall cell).
    """
    if record is None:
        return None
    values = list(record.tv_similarity.values())
    if not values:
        return None
    return float(np.mean(values))


def _complete_case_matrix(
    per_model: dict[str, dict[str, float | None]],
    models: list[str],
    methods: list[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    """Build the complete-case ``models x methods`` TV-similarity matrix.

    *per_model* maps ``model -> {method -> tv_similarity | None}``. A model is
    *complete* iff it has a non-``None`` value under **every** compared method
    (Friedman requires complete blocks); incomplete models are dropped and
    returned separately (no imputation). Returns ``(matrix, complete_models,
    dropped_models)`` with *matrix* shaped ``len(complete_models) x len(methods)``.
    """
    complete = [m for m in models if all(per_model[m].get(s) is not None for s in methods)]
    dropped = [m for m in models if m not in complete]
    matrix = np.array(
        [[float(per_model[m][s]) for s in methods] for m in complete],
        dtype=float,
    ) if complete else np.empty((0, len(methods)))
    return matrix, complete, dropped


def _method_panel(
    matrix: np.ndarray,
    methods: list[str],
    complete_models: list[str],
    dropped_models: list[str],
) -> dict[str, Any]:
    """One panel: Friedman omnibus + Nemenyi pairwise over methods on *matrix*.

    *matrix* is ``complete_models x methods`` TV-similarity (no NaN). Records the
    per-method means (over the complete-case models actually entering the test),
    ``n_models`` / ``n_dropped``, the Friedman omnibus (statistic, p, Kendall's W),
    and the Nemenyi ``pairwise_p`` map (``"a|b" -> p``). Panels with fewer than
    ``_MIN_COMPLETE_MODELS`` complete models are flagged ``insufficient_n`` (the
    chart skips them); the omnibus still runs when Friedman is computable
    (``n >= 2``) so the number is available, but is ``None`` below that.
    """
    n = int(matrix.shape[0])
    k = len(methods)
    means: dict[str, float | None] = (
        {s: float(np.mean(matrix[:, j])) for j, s in enumerate(methods)}
        if n else {s: None for s in methods}
    )
    # Per-model TV-similarity under each method, over the complete-case models
    # actually entering the test (matrix rows aligned to *complete_models*). This
    # is the individual-point / paired-line source for the comparison figure; the
    # renderer stays a pure consumer (no recomputation, no re-derivation from combos).
    per_model: dict[str, dict[str, float]] = {
        complete_models[i]: {methods[j]: float(matrix[i, j]) for j in range(k)}
        for i in range(n)
    }

    if n < 2 or k < 2:
        omnibus = {"test": "friedman", "statistic": None, "p": None, "p_bh": None,
                   "kendall_w": None,
                   "note": f"need >=2 methods and >=2 complete models, got {k} methods / {n} models"}
        pairwise_p: dict[str, float] = {}
    else:
        friedman = friedman_test(matrix)
        omnibus = {"test": "friedman", "statistic": friedman.get("chi2"),
                   "p": friedman.get("p"), "p_bh": None,
                   "kendall_w": friedman.get("kendalls_w")}
        if "note" in friedman:
            omnibus["note"] = friedman["note"]
        nemenyi = nemenyi_pairwise(matrix, labels=methods)
        pairwise_p = {}
        p_matrix = nemenyi.get("p_matrix")
        if p_matrix is not None:
            for i, j in combinations(range(k), 2):
                pairwise_p[_pair_key(methods[i], methods[j])] = float(p_matrix[i][j])

    panel: dict[str, Any] = {
        "n_models": n,
        "n_dropped": len(dropped_models),
        "dropped_models": dropped_models,
        "means": means,
        "per_model": per_model,
        "omnibus": omnibus,
        "pairwise_p": pairwise_p,
        "insufficient_n": n < _MIN_COMPLETE_MODELS,
    }
    if n < _MIN_COMPLETE_MODELS:
        panel["note"] = (
            f"{n} complete model(s) < {_MIN_COMPLETE_MODELS}; recorded but not charted"
        )
    return panel


def _method_comparison(
    by_ms: dict[tuple[str, str], ComboPerformance],
    models: list[str],
    attributes: list[str],
    methods: list[str],
    config: dict[str, Any],
    category_values: dict[str, list[str]],
) -> dict[str, Any]:
    """Per-category (+ Overall) method comparison: Friedman + Nemenyi, models as blocks.

    For each demographic category builds the complete-case ``models x methods``
    TV-similarity matrix and runs :func:`_method_panel`; the ``overall`` panel
    uses each model's overall TV-similarity (mean across categories) under each
    method. The category omnibus p-values are Benjamini-Hochberg (FDR) corrected
    across categories (``p_bh`` stored alongside raw ``p``); the Overall panel is a
    single pooled test and is not part of that family (``p_bh`` stays ``None``).

    Each category panel also carries ``n_category_values`` -- the count of that
    attribute's declared category levels, taken from *category_values* (the scheme's
    config-sourced ``values`` list, single source of truth). It is stored here so the
    renderer stays a pure consumer. Fail-fast: an analysed attribute with no resolved
    (or empty) ``values`` raises. The Overall panel spans all categories, so it has no
    single level count and omits the key.

    *methods* are the compared methods in complexity order; *config* supplies
    ``pairs_mode`` (exposed for the renderer, which resolves the bracketed pairs).
    The block is a pure serialisable contract -- no colormaps, no bracket geometry.
    """
    panels: dict[str, Any] = {}

    for attr in attributes:
        per_model = {
            m: {s: _tv_sim(by_ms.get((m, s)), attr) for s in methods} for m in models
        }
        matrix, complete, dropped = _complete_case_matrix(per_model, models, methods)
        panel = _method_panel(matrix, methods, complete, dropped)
        values = category_values.get(attr)
        if not values:
            raise ValueError(
                f"method_comparison: no category values resolved for analysed attribute "
                f"{attr!r}; its level count cannot be computed. The scheme's per-attribute "
                "'values' list is the single source of truth -- expected a non-empty list."
            )
        panel["n_category_values"] = len(values)
        panels[attr] = panel

    # Overall panel: per-model overall TV-similarity under each method.
    per_model_overall = {
        m: {s: _overall_tv_sim(by_ms.get((m, s))) for s in methods} for m in models
    }
    o_matrix, o_complete, o_dropped = _complete_case_matrix(per_model_overall, models, methods)
    panels["overall"] = _method_panel(o_matrix, methods, o_complete, o_dropped)

    # BH-FDR across the *category* omnibus p-values (Overall excluded: single test).
    indexed = [(attr, panels[attr]["omnibus"].get("p")) for attr in attributes]
    have = [(attr, p) for attr, p in indexed if p is not None]
    adjusted = benjamini_hochberg([p for _, p in have]) if have else []
    bh_by_attr = {attr: adj for (attr, _), adj in zip(have, adjusted)}
    for attr in attributes:
        panels[attr]["omnibus"]["p_bh"] = bh_by_attr.get(attr)

    return {
        "response": "tv_similarity",
        "block_factor": "model",
        "compared_factor": "method",
        "methods": methods,
        "pairs_mode": config["pairs_mode"],
        "min_complete_models": _MIN_COMPLETE_MODELS,
        "multiplicity_correction": "benjamini_hochberg_fdr_over_categories",
        # Echo the star mapping so the renderer reads it from *result* and stays a
        # pure consumer (falls back to load_comparison_config only if absent).
        "star_thresholds": config.get("star_thresholds"),
        "ns_symbol": config.get("ns_symbol"),
        "panels": panels,
    }


def build_method_significance(
    records: list[ComboPerformance],
    attributes: list[str],
    *,
    category_values: dict[str, list[str]],
    skipped: list[tuple[str, str]] | None = None,
    comparison_config: dict[str, Any] | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Build the serialisable method/model significance analysis for one country.

    *records* are the country's :class:`ComboPerformance` records (from
    ``model_ranking.loader``); *attributes* is the country's config-sourced
    comparison axis (ordered). *category_values* maps each analysed attribute to its
    declared category ``values`` list (the scheme's config-sourced levels); the
    method-comparison panels record each attribute's level count from it (fail-fast
    when an analysed attribute is missing or empty). *skipped* (``(slug, reason)``
    from the loader) is recorded in the metadata.

    The ordered **method axis** is the set of strategies present in *records*, put in
    config-derived complexity order by
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`.
    Method levels are keyed on the **strategy id**, so a versioned id (``all_pick_v2``)
    is its own level next to its v1 sibling: versions are never pooled, and the ``n = 1``
    per (model, method, category) design holds whichever mix of versions is handed over.
    The interpretive caveat is that on a mixed-version axis the ordered-trend test
    (Page's L) runs along an ordering that interleaves method complexity with version.

    Raises when there are no usable records, when the records span multiple
    countries (malformed input), or when a record carries a strategy id the axis
    config does not know. A country with < 2 models, or an attribute with
    a degenerate grid, does **not** raise: the affected test records a skip note
    (matching the primitives' ``None`` + ``note`` convention) rather than
    emitting a bogus statistic.
    """
    if not records:
        raise ValueError("build_method_significance needs at least one record")
    countries = {r.country for r in records}
    if len(countries) != 1:
        raise ValueError(
            f"build_method_significance analyses one country at a time, got {sorted(countries)}"
        )
    country = next(iter(countries))

    # The ordered method axis, resolved once from the strategies actually present.
    # An id the strategy-axis config does not know raises here rather than being
    # quietly dropped: a chart whose x-axis lost a method is indistinguishable from
    # one whose run lost a method.
    method_order = strategy_complexity_order(sorted({r.strategy for r in records}))
    method_rank = {strategy: rank for rank, strategy in enumerate(method_order, start=1)}
    k_methods = len(method_order)

    by_ms: dict[tuple[str, str], ComboPerformance] = {}
    for r in records:
        key = (r.model, r.strategy)
        if key in by_ms:
            raise ValueError(f"Duplicate (model, strategy) combo for country {country!r}: {key}")
        by_ms[key] = r
    models = sorted({r.model for r in records})

    # ---- Per attribute -------------------------------------------------- #
    per_attribute: dict[str, Any] = {}
    per_attribute_model: dict[str, Any] = {}
    total_absent = 0
    for attr in attributes:
        grid = _attribute_grid(by_ms, models, attr, method_order)
        total_absent += grid["absent_cells"]
        tests = _per_attribute_tests(grid["matrix"], grid["complete_models"], models, k_methods)
        tests["absent_cells"] = grid["absent_cells"]
        per_attribute[attr] = tests
        per_attribute_model[attr] = _per_attribute_model_trends(grid["cells"], k_methods)

    # ---- BH-FDR across attributes (per family) -------------------------- #
    _apply_bh(per_attribute, attributes, family="method_trend")
    _apply_bh(per_attribute, attributes, family="model_omnibus")

    # ---- Per-attribute dominant factor (from BH-adjusted p) ------------- #
    for attr in attributes:
        block = per_attribute[attr]
        block["dominant_factor"] = _dominant_factor(
            block["method_trend"].get("p_bh"), block["model_omnibus"].get("p_bh"), alpha
        )

    # ---- Overall (categories as blocks) --------------------------------- #
    model_comparison = _overall_model_comparison(by_ms, models, attributes, method_order)
    method_trend = _overall_method_trend(by_ms, models, attributes, method_order)
    interaction = _overall_interaction(by_ms, attributes, method_rank)
    overall = {
        "model_comparison": model_comparison,
        "method_trend": method_trend,
        "mixed_logit": interaction,
        "dominant_factor": _overall_dominant_factor(interaction.get("eta_sq")),
        "caveats": _CAVEATS,
    }

    # ---- Method-comparison figure statistics (models-as-blocks) --------- #
    # Config is the single source of truth for pair mode + star thresholds;
    # load it here (fail-fast) unless the caller injected one (tests).
    cmp_config = comparison_config if comparison_config is not None else load_comparison_config()
    method_comparison = _method_comparison(
        by_ms, models, list(attributes), method_order, cmp_config, category_values
    )

    return {
        "metadata": {
            "country": country,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "alpha": alpha,
            "n_combos": len(records),
            "models": models,
            "strategies": method_order,
            "method_order": method_order,
            "method_ranks": method_rank,
            "attributes": list(attributes),
            "multiplicity_correction": "benjamini_hochberg_fdr",
            "absent_cells_total": total_absent,
            "library_versions": _library_versions(),
            "skipped": [{"slug": slug, "reason": reason} for slug, reason in (skipped or [])],
            # Retained for output-schema stability, and now always empty: a record on a
            # strategy the axis config does not declare raises at method-axis resolution
            # instead of being silently dropped into this list.
            "dropped_combos": [],
        },
        "per_attribute": per_attribute,
        "per_attribute_model": per_attribute_model,
        "overall": overall,
        "method_comparison": method_comparison,
    }


def _apply_bh(per_attribute: dict[str, Any], attributes: list[str], *, family: str) -> None:
    """BH-FDR correct one family's raw p-values across attributes, in place.

    Attributes whose test was skipped (``p_raw is None``) are excluded from the
    correction and get ``p_bh = None`` (their evidence was never computed).
    """
    indexed = [(attr, per_attribute[attr][family].get("p_raw")) for attr in attributes]
    have = [(attr, p) for attr, p in indexed if p is not None]
    adjusted = benjamini_hochberg([p for _, p in have]) if have else []
    bh_by_attr = {attr: adj for (attr, _), adj in zip(have, adjusted)}
    for attr in attributes:
        per_attribute[attr][family]["p_bh"] = bh_by_attr.get(attr)


def write_method_significance_json(result: dict[str, Any], out_path: str | Path) -> Path:
    """Write the method/model significance analysis to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    return out_path


def write_method_significance_csv(result: dict[str, Any], out_path: str | Path) -> Path:
    """Write one row per attribute: method L/p (raw+BH), model chi2/p (raw+BH), etc."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    attributes: list[str] = result["metadata"]["attributes"]
    per_attribute: dict[str, Any] = result["per_attribute"]

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "attribute", "n_models_complete",
            "method_L", "method_z", "method_p_raw", "method_p_bh",
            "model_chi2", "model_p_raw", "model_p_bh", "model_kendalls_w",
            "linear_slope_sign", "dominant_factor",
        ])
        for attr in attributes:
            block = per_attribute[attr]
            method = block["method_trend"]
            model = block["model_omnibus"]
            page = method.get("page") or {}
            friedman = model.get("friedman") or {}
            linear = method.get("linear_contrast") or {}
            writer.writerow([
                attr,
                block.get("n_models_complete"),
                page.get("L"),
                page.get("z"),
                method.get("p_raw"),
                method.get("p_bh"),
                friedman.get("chi2"),
                model.get("p_raw"),
                model.get("p_bh"),
                friedman.get("kendalls_w"),
                linear.get("slope_sign"),
                block.get("dominant_factor"),
            ])
    return out_path

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
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from population_synthetic.analysis.model_ranking.loader import ComboPerformance
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER
from population_synthetic.analysis.utils.stats_tests import (
    benjamini_hochberg,
    friedman_test,
    mixed_logit_interaction,
    nemenyi_posthoc,
    page_trend_test,
)

# The 5 canonical ordered strategies define the method axis; rank = index + 1
# (1 = simplest). Combos on any other strategy are dropped (recorded).
_METHOD_ORDER: list[str] = list(STRATEGY_COMPLEXITY_ORDER)
_METHOD_RANK: dict[str, int] = {s: i + 1 for i, s in enumerate(_METHOD_ORDER)}

# Orthogonal polynomial contrast coefficients for 5 equally-spaced ordered
# levels (methods 1..5). Used to test, not assume, monotonicity.
_LINEAR_CONTRAST = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
_QUADRATIC_CONTRAST = np.array([2.0, -1.0, -2.0, -1.0, 2.0])

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
) -> dict[str, Any]:
    """Build one attribute's model x method cell grid and its complete sub-grid.

    Returns the raw ``cells`` (``model -> {rank -> tv|None}``, the absent marker
    preserved), the ``complete_models`` (present and non-absent for all 5
    methods), the ``models x 5`` complete matrix, and the count of absent cells.
    """
    cells: dict[str, dict[int, float | None]] = {}
    absent = 0
    for model in models:
        row: dict[int, float | None] = {}
        for strategy in _METHOD_ORDER:
            rank = _METHOD_RANK[strategy]
            record = by_ms.get((model, strategy))
            value = _tv(record, attr) if record is not None else None
            row[rank] = value
            if value is None:
                absent += 1
        cells[model] = row

    complete_models = [m for m in models if all(cells[m][r] is not None for r in range(1, 6))]
    matrix = np.array(
        [[float(cells[m][r]) for r in range(1, 6)] for m in complete_models],
        dtype=float,
    ) if complete_models else np.empty((0, 5))
    return {"cells": cells, "complete_models": complete_models,
            "matrix": matrix, "absent_cells": absent}


def _per_attribute_tests(matrix: np.ndarray, complete_models: list[str], all_models: list[str]) -> dict[str, Any]:
    """Per-attribute method trend (Page's L + contrasts) and model omnibus (Friedman).

    *matrix* is ``complete_models x 5`` (methods in complexity order). Fewer than
    2 complete models makes both tests degenerate -> a recorded skip note.
    """
    dropped = [m for m in all_models if m not in complete_models]
    if matrix.shape[0] < 2:
        note = f"need >=2 models complete across all 5 methods, got {matrix.shape[0]}"
        return {
            "n_models_complete": int(matrix.shape[0]),
            "dropped_models": dropped,
            "method_trend": {"page": None, "linear_contrast": None,
                             "quadratic_contrast": None, "p_raw": None, "note": note},
            "model_omnibus": {"friedman": None, "p_raw": None, "note": note},
        }

    # Page's L: blocks = complete models (rows), treatments = 5 ordered methods.
    order = list(range(5))
    page = page_trend_test(matrix, order)
    p_one = page.get("p")
    # Either-direction trend: two-sided p from the one-sided ordered p.
    p_two = None if p_one is None else float(2.0 * min(p_one, 1.0 - p_one))
    page["p_two_sided"] = p_two

    linear = _polynomial_contrast(matrix, _LINEAR_CONTRAST)
    quadratic = _polynomial_contrast(matrix, _QUADRATIC_CONTRAST)

    # Friedman over models: blocks = the 5 methods (rows), treatments = models.
    friedman = friedman_test(matrix.T)

    return {
        "n_models_complete": int(matrix.shape[0]),
        "dropped_models": dropped,
        "method_trend": {"page": page, "linear_contrast": linear,
                         "quadratic_contrast": quadratic, "p_raw": p_two},
        "model_omnibus": {"friedman": friedman, "p_raw": friedman.get("p")},
    }


def _per_attribute_model_trends(cells: dict[str, dict[int, float | None]]) -> dict[str, Any]:
    """Descriptive TV(method) trend per model (OLS slope, Spearman rho, Delta).

    Flagged ``n = 5`` descriptive -- **no p-value is claimed at this grain**
    (per-category interaction is not estimable at n = 1).
    """
    out: dict[str, Any] = {}
    for model, row in cells.items():
        ranks = [r for r in range(1, 6) if row[r] is not None]
        values = [float(row[r]) for r in ranks]
        n = len(values)
        slope: float | None = None
        rho: float | None = None
        delta: float | None = None
        if n >= 2 and len(set(values)) > 1:
            slope = float(np.polyfit(ranks, values, 1)[0])
        if n >= 3 and len(set(values)) > 1:
            rho = float(stats.spearmanr(ranks, values).statistic)
        if row[1] is not None and row[5] is not None:
            delta = float(row[5]) - float(row[1])
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
) -> dict[str, Any]:
    """Demšar model comparison: Friedman across models over category x method blocks.

    Each block is a (category, method) cell measured once per model; only blocks
    complete across every model are used. Feeds Friedman + Nemenyi (with the CD
    value) for a critical-difference diagram in Phase 3.
    """
    block_rows: list[list[float]] = []
    for attr in attributes:
        for strategy in _METHOD_ORDER:
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
) -> dict[str, Any]:
    """Overall Page's L method trend: blocks = category x model, treatments = 5 methods."""
    block_rows: list[list[float]] = []
    for attr in attributes:
        for model in models:
            values = [_tv(by_ms.get((model, s)), attr) if by_ms.get((model, s)) is not None else None
                      for s in _METHOD_ORDER]
            if all(v is not None for v in values):
                block_rows.append([float(v) for v in values])
    n_blocks = len(block_rows)
    if n_blocks < 2:
        return {"page": None, "n_blocks": n_blocks,
                "note": f"need >=2 complete (category x model) blocks, got {n_blocks}"}
    matrix = np.array(block_rows, dtype=float)
    page = page_trend_test(matrix, list(range(5)))
    p_one = page.get("p")
    page["p_two_sided"] = None if p_one is None else float(2.0 * min(p_one, 1.0 - p_one))
    return {"page": page, "n_blocks": n_blocks}


def _overall_interaction(
    by_ms: dict[tuple[str, str], ComboPerformance],
    attributes: list[str],
) -> dict[str, Any]:
    """Long-format ``logit(TV) ~ model*method_rank + (1|category)`` mixed fit."""
    import pandas as pd

    rows: list[dict[str, Any]] = []
    for attr in attributes:
        for (model, strategy), record in by_ms.items():
            value = _tv(record, attr)
            if value is not None:
                rows.append({"tv": value, "model": model,
                             "method_rank": _METHOD_RANK[strategy], "category": attr})
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


def build_method_significance(
    records: list[ComboPerformance],
    attributes: list[str],
    *,
    skipped: list[tuple[str, str]] | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Build the serialisable method/model significance analysis for one country.

    *records* are the country's :class:`ComboPerformance` records (from
    ``model_ranking.loader``); *attributes* is the country's config-sourced
    comparison axis (ordered). *skipped* (``(slug, reason)`` from the loader) is
    recorded in the metadata. Records on a strategy outside the 5 canonical
    ordered strategies are dropped and recorded.

    Raises when there are no usable records or the records span multiple
    countries (malformed input). A country with < 2 models, or an attribute with
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

    # Filter to the 5 canonical ordered strategies (record the drops).
    kept: list[ComboPerformance] = []
    dropped_combos: list[dict[str, str]] = []
    for r in records:
        if r.strategy in _METHOD_RANK:
            kept.append(r)
        else:
            dropped_combos.append(
                {"slug": r.slug, "reason": f"strategy {r.strategy!r} is not one of the 5 ordered methods"}
            )
    if not kept:
        raise ValueError(
            "No records remain after filtering to the 5 ordered strategies "
            f"({_METHOD_ORDER}); nothing to analyse."
        )

    by_ms: dict[tuple[str, str], ComboPerformance] = {}
    for r in kept:
        key = (r.model, r.strategy)
        if key in by_ms:
            raise ValueError(f"Duplicate (model, strategy) combo for country {country!r}: {key}")
        by_ms[key] = r
    models = sorted({r.model for r in kept})
    strategies_present = [s for s in _METHOD_ORDER if any((m, s) in by_ms for m in models)]

    # ---- Per attribute -------------------------------------------------- #
    per_attribute: dict[str, Any] = {}
    per_attribute_model: dict[str, Any] = {}
    total_absent = 0
    for attr in attributes:
        grid = _attribute_grid(by_ms, models, attr)
        total_absent += grid["absent_cells"]
        tests = _per_attribute_tests(grid["matrix"], grid["complete_models"], models)
        tests["absent_cells"] = grid["absent_cells"]
        per_attribute[attr] = tests
        per_attribute_model[attr] = _per_attribute_model_trends(grid["cells"])

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
    model_comparison = _overall_model_comparison(by_ms, models, attributes)
    method_trend = _overall_method_trend(by_ms, models, attributes)
    interaction = _overall_interaction(by_ms, attributes)
    overall = {
        "model_comparison": model_comparison,
        "method_trend": method_trend,
        "mixed_logit": interaction,
        "dominant_factor": _overall_dominant_factor(interaction.get("eta_sq")),
        "caveats": _CAVEATS,
    }

    return {
        "metadata": {
            "country": country,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "alpha": alpha,
            "n_combos": len(kept),
            "models": models,
            "strategies": strategies_present,
            "method_order": _METHOD_ORDER,
            "method_ranks": _METHOD_RANK,
            "attributes": list(attributes),
            "multiplicity_correction": "benjamini_hochberg_fdr",
            "absent_cells_total": total_absent,
            "library_versions": _library_versions(),
            "skipped": [{"slug": slug, "reason": reason} for slug, reason in (skipped or [])],
            "dropped_combos": dropped_combos,
        },
        "per_attribute": per_attribute,
        "per_attribute_model": per_attribute_model,
        "overall": overall,
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

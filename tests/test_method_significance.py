"""Tests for the method/model significance builder.

Builds a synthetic (model x strategy x attribute) grid over the 5 canonical
ordered strategies with:

* a **planted monotonic method trend** in ``trend_attr`` (TV strictly increases
  with method rank for every model) -> Page's L must flag it and survive BH;
* a **null trend** in ``null_attr`` laid out as a 5x5 Latin square (each method
  receives each value exactly once across models) so the column rank sums are
  equal, Page's L lands exactly on its null mean (z = 0), and BH keeps it
  non-significant.

The whole builder depends on ``benjamini_hochberg`` (statsmodels),
``nemenyi_posthoc`` (scikit-posthocs) and ``mixed_logit_interaction``
(statsmodels), so the module is skipped without the ``[analysis]`` extra.
"""

from __future__ import annotations

import csv
import math

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")

from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    build_method_significance,
    write_method_significance_csv,
    write_method_significance_json,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

MODELS = ["model_a", "model_b", "model_c", "model_d", "model_e"]
# The five v1 families, ordered by the config-derived accessor (the same order
# every consumer resolves; asserted against the legacy sequence in test_axes.py).
STRATEGIES = strategy_complexity_order([
    "all_generate_evaluate_random_pick",
    "all_generate_evaluate_pick",
    "all_generate_pick",
    "all_pick_dag",
    "all_pick",
])
ATTRS = ["trend_attr", "null_attr"]
# Config-sourced category levels per attribute (drives the method-comparison panel
# level counts); required by build_method_significance.
CATEGORY_VALUES = {"trend_attr": ["a", "b", "c", "d"], "null_attr": ["p", "q", "r"]}
# Distinct values for the Latin-square null (each appears once per method column).
_NULL_VALUES = [0.10, 0.20, 0.30, 0.40, 0.50]


def _trend_tv(m_idx: int, rank: int) -> float:
    """Strictly increasing in method rank (monotonic planted trend)."""
    return round(0.05 + 0.15 * (rank - 1) + 0.004 * m_idx, 4)


def _null_tv(m_idx: int, rank: int) -> float:
    """5x5 Latin square: equal column rank sums -> exact null for Page's L."""
    return _NULL_VALUES[(m_idx + (rank - 1)) % 5]


def _full_grid(*, drop=None, nan_cell=None):
    """Build the full 5x5 grid of ComboPerformance records.

    *drop* = optional ``(model, strategy)`` combo to omit entirely (absent cell).
    *nan_cell* = optional ``(model, strategy, attr)`` to set to ``NaN`` (absent).
    """
    combos = []
    for m_idx, model in enumerate(MODELS):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            if drop is not None and (model, strategy) == drop:
                continue
            tv_by_attr = {
                "trend_attr": _trend_tv(m_idx, rank),
                "null_attr": _null_tv(m_idx, rank),
            }
            if nan_cell is not None and (model, strategy) == nan_cell[:2]:
                tv_by_attr[nan_cell[2]] = float("nan")
            combos.append(
                make_combo(
                    slug=f"swedish_{strategy}_{model}",
                    strategy=strategy,
                    model=model,
                    tv_by_attr=tv_by_attr,
                )
            )
    return combos


# --------------------------------------------------------------------------- #
# Planted trend vs null                                                        #
# --------------------------------------------------------------------------- #


def test_page_flags_planted_trend_bh_keeps_null_non_significant():
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)

    trend = result["per_attribute"]["trend_attr"]["method_trend"]
    null = result["per_attribute"]["null_attr"]["method_trend"]

    # Planted monotonic trend: significant after BH.
    assert trend["p_bh"] is not None
    assert trend["p_bh"] < 0.05
    assert trend["linear_contrast"]["slope_sign"] == "positive"

    # Latin-square null: Page's L on its null mean (z == 0), BH stays ~1.
    assert null["page"]["z"] == pytest.approx(0.0, abs=1e-9)
    assert null["p_raw"] == pytest.approx(1.0, abs=1e-9)
    assert null["p_bh"] > 0.05

    # Dominant factor for the planted attribute is the method.
    assert result["per_attribute"]["trend_attr"]["dominant_factor"] == "method"


def test_friedman_and_kendalls_w_present_per_attribute():
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)
    omni = result["per_attribute"]["trend_attr"]["model_omnibus"]["friedman"]
    assert omni["chi2"] is not None
    assert 0.0 <= omni["kendalls_w"] <= 1.0
    assert omni["k"] == len(MODELS)  # treatments = models


# --------------------------------------------------------------------------- #
# JSON / CSV shape                                                             #
# --------------------------------------------------------------------------- #


def test_builder_json_shape():
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)

    assert set(result) == {"metadata", "per_attribute", "per_attribute_model", "overall",
                           "method_comparison"}

    meta = result["metadata"]
    for key in ("country", "generated_at", "alpha", "n_combos", "models", "strategies",
                "method_order", "method_ranks", "attributes", "multiplicity_correction",
                "library_versions", "skipped", "dropped_combos"):
        assert key in meta, key
    assert meta["country"] == "swedish"
    assert meta["method_order"] == STRATEGIES
    assert set(meta["library_versions"]) == {"statsmodels", "scikit_posthocs", "scipy"}

    for attr in ATTRS:
        block = result["per_attribute"][attr]
        assert set(block["method_trend"]) >= {"page", "linear_contrast", "quadratic_contrast",
                                              "p_raw", "p_bh"}
        assert set(block["model_omnibus"]) >= {"friedman", "p_raw", "p_bh"}
        assert "dominant_factor" in block
        # Per-attribute-model trend flagged descriptive (no p-value claimed).
        for model in MODELS:
            pam = result["per_attribute_model"][attr][model]
            assert pam["descriptive"] is True
            assert pam["n_methods"] == len(STRATEGIES)

    overall = result["overall"]
    assert set(overall) == {"model_comparison", "method_trend", "mixed_logit",
                            "dominant_factor", "caveats"}
    assert overall["model_comparison"]["nemenyi"]["cd"] is not None
    assert overall["model_comparison"]["models"] == MODELS
    assert "n = 1" in overall["caveats"]


def test_writers_roundtrip(tmp_path):
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)

    json_path = write_method_significance_json(result, tmp_path / "swedish_method_significance.json")
    csv_path = write_method_significance_csv(result, tmp_path / "swedish_method_significance.csv")
    assert json_path.is_file()
    assert csv_path.is_file()

    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    assert header[0] == "attribute"
    for col in ("method_L", "method_p_raw", "method_p_bh", "model_chi2", "model_p_raw",
                "model_p_bh", "model_kendalls_w", "linear_slope_sign", "dominant_factor"):
        assert col in header
    assert len(rows) == 1 + len(ATTRS)  # header + one row per attribute


# --------------------------------------------------------------------------- #
# Overall (mixed model / Demšar)                                              #
# --------------------------------------------------------------------------- #


def test_overall_mixed_logit_and_model_comparison():
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)
    overall = result["overall"]

    mixed = overall["mixed_logit"]
    assert "interaction" in mixed and "eta_sq" in mixed and "converged" in mixed

    mc = overall["model_comparison"]
    assert mc["friedman"] is not None
    assert mc["nemenyi"]["p_matrix"] is not None
    assert mc["n_blocks"] == len(ATTRS) * len(STRATEGIES)  # category x method blocks


# --------------------------------------------------------------------------- #
# Absent cell / unbalanced grid                                               #
# --------------------------------------------------------------------------- #


def test_absent_and_unbalanced_grid_recorded_not_imputed():
    # Drop one combo entirely, and NaN out another attribute cell.
    grid = _full_grid(
        drop=("model_e", "all_generate_evaluate_random_pick"),
        nan_cell=("model_a", "all_pick", "null_attr"),
    )
    result = build_method_significance(grid, ATTRS, category_values=CATEGORY_VALUES)

    # trend_attr: model_e is now incomplete (missing method 5) -> dropped from the
    # complete set; the test still runs on the remaining 4 models.
    trend = result["per_attribute"]["trend_attr"]
    assert trend["n_models_complete"] == 4
    assert "model_e" in trend["dropped_models"]
    assert trend["absent_cells"] >= 1
    # Still flags the (strong) planted trend on the 4 complete models.
    assert trend["method_trend"]["p_bh"] < 0.05

    # null_attr: model_a's all_pick cell is NaN -> absent, so model_a incomplete.
    null = result["per_attribute"]["null_attr"]
    assert "model_a" in null["dropped_models"]
    assert null["absent_cells"] >= 1

    assert result["metadata"]["absent_cells_total"] >= 2


def test_degenerate_single_model_records_skip_note():
    # One model only across 5 strategies: both per-attribute tests are degenerate.
    combos = []
    for rank, strategy in enumerate(STRATEGIES, start=1):
        combos.append(
            make_combo(
                slug=f"swedish_{strategy}_solo",
                strategy=strategy,
                model="solo",
                tv_by_attr={"trend_attr": _trend_tv(0, rank), "null_attr": _null_tv(0, rank)},
            )
        )
    result = build_method_significance(combos, ATTRS, category_values=CATEGORY_VALUES)
    block = result["per_attribute"]["trend_attr"]
    assert block["n_models_complete"] == 1
    assert block["method_trend"]["page"] is None
    assert "note" in block["method_trend"]
    assert block["method_trend"]["p_raw"] is None
    assert block["method_trend"]["p_bh"] is None


# --------------------------------------------------------------------------- #
# Fail-fast                                                                    #
# --------------------------------------------------------------------------- #


def test_multiple_countries_raises():
    a = make_combo(slug="swedish_all_pick_model_a", strategy="all_pick", model="model_a",
                   tv_by_attr={"trend_attr": 0.1, "null_attr": 0.2}, country="swedish")
    b = make_combo(slug="italian_all_pick_model_a", strategy="all_pick", model="model_a",
                   tv_by_attr={"trend_attr": 0.1, "null_attr": 0.2}, country="italian")
    with pytest.raises(ValueError, match="one country"):
        build_method_significance([a, b], ATTRS, category_values=CATEGORY_VALUES)


def test_unknown_strategy_records_raise():
    """An off-axis strategy raises at method-axis resolution (never a silent drop)."""
    off = make_combo(slug="swedish_seed_model_a", strategy="seed", model="model_a",
                     tv_by_attr={"trend_attr": 0.1, "null_attr": 0.2})
    with pytest.raises(ValueError, match="Unknown strategy id"):
        build_method_significance([off], ATTRS, category_values=CATEGORY_VALUES)


def test_empty_records_raises():
    with pytest.raises(ValueError, match="at least one record"):
        build_method_significance([], ATTRS, category_values=CATEGORY_VALUES)


def test_null_page_matches_hand_computation():
    """Sanity: the Latin-square null truly has z == 0 (mu == L)."""
    result = build_method_significance(_full_grid(), ATTRS, category_values=CATEGORY_VALUES)
    page = result["per_attribute"]["null_attr"]["method_trend"]["page"]
    n, k = page["n"], page["k"]
    mu = n * k * (k + 1) ** 2 / 4.0
    assert page["L"] == pytest.approx(mu)
    assert not math.isnan(page["z"])

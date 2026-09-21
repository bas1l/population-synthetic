"""Tests for the shared ``model_ranking`` model order (``analysis/utils/model_order.py``).

The ordering used to be tested only indirectly, by rendering the model x method heatmap
and reading its tick labels back. These tests pin it directly: the tier split, the two
sort keys, the agreement of :func:`ranked_model_order` with the order the heatmap actually
draws (which is what makes the lift out of ``model_ranking/charts.py`` behaviour-neutral),
a fixture mirroring the live tiers, and :func:`align_to_ranking`.

The in-memory grids are the ones ``tests/test_model_ranking_charts.py`` renders, imported
rather than copied, so both files keep describing the same cells. Their cap is 40, not the
production 100, so a hardcoded threshold cannot pass by coincidence.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pytest

from population_synthetic.analysis.utils import model_order
from population_synthetic.analysis.utils.cap_index import INDEX_FILENAME, CapIndex
from population_synthetic.analysis.utils.model_order import (
    _model_method_rows,
    _ModelRow,
    _tier1_sort_key,
    _tier2_sort_key,
    align_to_ranking,
    ranked_model_order,
)
from tests.test_model_ranking_charts import (
    REQUESTED_N,
    S1,
    S2,
    STRATEGIES,
    _cap,
    _full_grid,
    _mixed_grid,
    _render,
    _result,
    _row_models,
)


def _row(model: str, best: float | None, mean: float | None = None, tier: int = 1) -> _ModelRow:
    """A row carrying only what the sort keys read."""
    return _ModelRow(
        model=model, values=np.array([]), counts=[], full=[], tier=tier,
        best_value=best, best_method=None, key_mean=mean, key_cells=0 if best is None else 1,
    )


# ------------------------------------------------------------------
# The tier split
# ------------------------------------------------------------------

def test_tier_split_is_on_having_any_full_n_cell():
    cells = _mixed_grid()
    rows = _model_method_rows(_result(cells), _cap(cells), ["claude_haiku", "claude_sonnet", "gemini_flash"],
                              list(STRATEGIES))

    assert {row.model: row.tier for row in rows} == {
        "claude_haiku": 1, "claude_sonnet": 1, "gemini_flash": 2,
    }


def test_tier1_key_rests_on_full_n_cells_only():
    """``claude_sonnet``'s best cell is thin, so its key is its weaker full-n cell."""
    cells = _mixed_grid()
    rows = {row.model: row for row in _model_method_rows(
        _result(cells), _cap(cells), ["claude_sonnet"], list(STRATEGIES))}

    sonnet = rows["claude_sonnet"]
    assert sonnet.best_value == pytest.approx(0.60)
    assert sonnet.best_method == S1
    assert sonnet.key_cells == 1


def test_a_slug_missing_from_the_cap_index_raises():
    cells = _full_grid()
    partial = CapIndex({}, source=Path("fixture") / INDEX_FILENAME, withdrawn=())

    with pytest.raises(KeyError):
        ranked_model_order(_result(cells), partial)


# ------------------------------------------------------------------
# The two sort keys
# ------------------------------------------------------------------

def test_tier1_key_orders_by_max_then_mean_then_id():
    rows = [_row("b", 0.9, 0.5), _row("a", 0.9, 0.5), _row("c", 0.9, 0.7), _row("d", 0.95, 0.1)]

    assert [r.model for r in sorted(rows, key=_tier1_sort_key)] == ["d", "c", "a", "b"]


def test_tier2_key_ignores_the_mean():
    rows = [_row("b", 0.9, 0.9, tier=2), _row("a", 0.9, 0.1, tier=2)]

    assert [r.model for r in sorted(rows, key=_tier2_sort_key)] == ["a", "b"]


@pytest.mark.parametrize("key", [_tier1_sort_key, _tier2_sort_key])
def test_keyless_rows_sort_last_without_comparing_nan(key):
    rows = [_row("a", None), _row("z", 0.1, 0.1)]

    assert [r.model for r in sorted(rows, key=key)] == ["z", "a"]


# ------------------------------------------------------------------
# ranked_model_order agrees with the heatmap it was lifted from
# ------------------------------------------------------------------

_NAN = float("nan")

_GRIDS = {
    "full": _full_grid(),
    "mixed": _mixed_grid(),
    "tier2-beats-tier1-on-value": [
        ("claude_haiku", S1, 0.10, REQUESTED_N), ("claude_haiku", S2, 0.20, REQUESTED_N),
        ("openrouter_kimi_k3", S1, 0.99, REQUESTED_N - 1), ("openrouter_kimi_k3", S2, 0.98, 3),
    ],
    "keyless-rows": [
        ("claude_haiku", S1, 0.90, REQUESTED_N), ("claude_haiku", S2, 0.80, REQUESTED_N),
        ("claude_sonnet", S1, _NAN, REQUESTED_N), ("claude_sonnet", S2, _NAN, REQUESTED_N),
        ("gemini_flash", S1, 0.50, 5), ("gemini_flash", S2, 0.40, 5),
        ("ollama_qwen3_14b", S1, _NAN, 5), ("ollama_qwen3_14b", S2, _NAN, 5),
    ],
}


@pytest.mark.parametrize("name", sorted(_GRIDS))
def test_ranked_order_is_the_order_the_heatmap_draws(name, tmp_path):
    cells = _GRIDS[name]
    _out, ax = _render(cells, tmp_path)

    assert ranked_model_order(_result(cells), _cap(cells)) == _row_models(ax)


def test_empty_result_ranks_nothing():
    result = {"metadata": {"models": [], "strategies": []}, "combos": {}}
    empty = CapIndex({}, source=Path("fixture") / INDEX_FILENAME, withdrawn=())

    assert ranked_model_order(result, empty) == []


# A fixture mirroring the live swedish_02 tiers: every cell at the cap (all Tier 1), overall
# TV-similarity per model in the strategy order below, rounded to 6 d.p. The expected order is
# the ``model_order`` the typicality prototype derived from the same performance JSON.
_LIVE_STRATEGIES = [
    "all_pick_v2", "all_pick_dag_v2", "all_generate_pick_v2",
    "all_generate_evaluate_pick_v2", "all_generate_evaluate_random_pick_v2",
]
_LIVE_CAP = 100
_LIVE_CELLS = {
    "claude_haiku": (0.513379, 0.526943, 0.5735, 0.643486, 0.840818),
    "claude_sonnet": (0.4522, 0.444236, 0.465707, 0.581664, 0.839141),
    "ollama_deepseek_r1_14b": (0.560143, 0.574929, 0.581686, 0.675397, None),
    "ollama_gemma4_e4b": (0.515586, 0.521814, 0.563843, 0.630364, None),
    "ollama_mistral_nemo_12b": (0.525779, 0.497086, 0.494993, 0.579493, 0.754234),
    "openrouter_glm_52": (0.498357, 0.531686, 0.478007, 0.541786, 0.817195),
    "openrouter_gpt56_sol": (0.473779, 0.463571, 0.483586, 0.560836, 0.820517),
    "openrouter_gpt_oss_120b": (0.512014, 0.462793, 0.542593, 0.550486, 0.79041),
    "openrouter_kimi_k3": (0.526193, 0.513736, 0.517764, 0.542057, 0.841979),
    "openrouter_mistral_medium": (0.513136, 0.51995, 0.606464, 0.562793, 0.787962),
    "openrouter_opus_5": (0.505636, 0.433164, 0.456629, 0.532686, 0.83175),
    "openrouter_qwen35_flash": (0.514414, 0.479793, 0.516121, 0.554893, 0.81031),
}
_LIVE_ORDER = [
    "openrouter_kimi_k3", "claude_haiku", "claude_sonnet", "openrouter_opus_5",
    "openrouter_gpt56_sol", "openrouter_glm_52", "openrouter_qwen35_flash",
    "openrouter_gpt_oss_120b", "openrouter_mistral_medium", "ollama_mistral_nemo_12b",
    "ollama_deepseek_r1_14b", "ollama_gemma4_e4b",
]


def test_ranked_order_reproduces_the_live_tiers():
    combos = {}
    for model, values in _LIVE_CELLS.items():
        for strategy, value in zip(_LIVE_STRATEGIES, values):
            if value is None:  # withdrawn by the gate: absent from the ranking
                continue
            combos[f"swedish_02_{strategy}_{model}"] = {
                "model": model, "strategy": strategy, "n": _LIVE_CAP,
                "overall": {"tv_similarity_mean": value},
            }
    result = {
        "metadata": {"models": sorted(_LIVE_CELLS), "strategies": sorted(_LIVE_STRATEGIES)},
        "combos": combos,
    }
    cap = CapIndex({slug: _LIVE_CAP for slug in combos}, source=Path("fixture") / INDEX_FILENAME,
                   withdrawn=())

    assert ranked_model_order(result, cap) == _LIVE_ORDER


# ------------------------------------------------------------------
# align_to_ranking
# ------------------------------------------------------------------

def test_align_orders_present_models_by_the_ranking():
    ordered, first_unranked = align_to_ranking(["c", "a", "b"], ["b", "a", "c"])

    assert ordered == ["b", "a", "c"]
    assert first_unranked == 3


def test_align_appends_unranked_models_in_their_given_order():
    ordered, first_unranked = align_to_ranking(["z", "a", "y", "b"], ["b", "a"])

    assert ordered == ["b", "a", "z", "y"]
    assert first_unranked == 2


def test_align_raises_on_a_ranked_model_the_grid_does_not_hold():
    with pytest.raises(ValueError) as exc:
        align_to_ranking(["a"], ["a", "unknown_model"])

    assert "unknown_model" in str(exc.value)


@pytest.mark.parametrize(
    ("present", "ranked"),
    [pytest.param(["a", "a"], ["a"], id="present"), pytest.param(["a"], ["a", "a"], id="ranked")],
)
def test_align_raises_on_a_repeated_id(present, ranked):
    with pytest.raises(ValueError):
        align_to_ranking(present, ranked)


# ------------------------------------------------------------------
# Boundary: a ranking, not a figure
# ------------------------------------------------------------------

def test_module_imports_no_plotting_and_no_analysis_subpackage():
    tree = ast.parse(inspect.getsource(model_order))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}

    assert not any(name.startswith("matplotlib") for name in imported)
    analysis = [name for name in imported if name.startswith("population_synthetic.analysis.")]
    assert all(name.startswith("population_synthetic.analysis.utils.") for name in analysis)

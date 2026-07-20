"""Smoke tests for the method/model significance charts (matplotlib Agg backend).

Builds a small (model x strategy x attribute) grid, runs the builder, then drives
every chart function and asserts the expected files are written. Charts are pure
rendering downstream of the builder's serialisable result (+ the loader records
for the raw TV trend lines), so this just guards that they execute and emit files.

Skipped without the ``[analysis]`` extra (the builder needs statsmodels +
scikit-posthocs).
"""

from __future__ import annotations

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    build_method_significance,
)
from population_synthetic.analysis.method_significance.charts import (  # noqa: E402
    plot_cd_diagram,
    plot_factor_dominance,
    plot_method_trends,
    plot_slope_heatmap,
)
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

MODELS = ["model_a", "model_b", "model_c", "model_d"]
STRATEGIES = list(STRATEGY_COMPLEXITY_ORDER)
ATTRS = ["trend_attr", "null_attr"]
CATEGORY_VALUES = {"trend_attr": ["a", "b", "c", "d"], "null_attr": ["p", "q", "r"]}
_NULL_VALUES = [0.10, 0.20, 0.30, 0.40, 0.50]


def _grid():
    combos = []
    for m_idx, model in enumerate(MODELS):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            combos.append(
                make_combo(
                    slug=f"swedish_{strategy}_{model}",
                    strategy=strategy,
                    model=model,
                    tv_by_attr={
                        "trend_attr": round(0.05 + 0.15 * (rank - 1) + 0.004 * m_idx, 4),
                        "null_attr": _NULL_VALUES[(m_idx + (rank - 1)) % 5],
                    },
                )
            )
    return combos


def test_all_charts_write_files(tmp_path):
    records = _grid()
    result = build_method_significance(records, ATTRS, category_values=CATEGORY_VALUES)

    heatmap = plot_slope_heatmap(result, tmp_path / "swedish_slope_heatmap.png")
    cd = plot_cd_diagram(result, tmp_path / "swedish_cd_diagram.png")
    dominance = plot_factor_dominance(result, tmp_path / "swedish_factor_dominance.png")
    trends = plot_method_trends(result, records, tmp_path / "swedish_method_trends")

    assert heatmap is not None and heatmap.is_file()
    assert cd is not None and cd.is_file()
    assert dominance is not None and dominance.is_file()
    assert len(trends) == len(ATTRS)
    for path in trends:
        assert path.is_file()

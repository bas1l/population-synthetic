"""Unit tests for the ``real_population_stats`` analysis subpackage (Phase 3).

Covers, in order:

- ``stats.py::compute_category_stats`` -- proportions agree with the shared
  ``compute_proportions`` authority, counts/total bookkeeping, the absent-category
  and all-null-attribute signals, ``age_group`` binning, and ``extra_categories``.
- ``csv_writer.py::write_proportions_csv`` -- exact header, one row per category,
  ``percent == proportion * 100``, round-trip via ``csv.DictReader``.
- ``charts.py::plot_category_bars`` / ``plot_overview_panel`` -- pure ``Figure``
  return (no disk I/O), fixed [0, 100] y-limits, the four dashed reference lines,
  and on-bar percent labels. Headless ``Agg`` backend throughout.
- ``gui/commands.py::build_per_country_cmds`` -- combo-to-distinct-country
  collapsing, ``--force``/option placement, and the no-model/strategy-flags
  contract.
- Registry + workflow-engine wiring for the new ``per_country`` dispatch mode.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.figure
import matplotlib.pyplot as plt
import pytest

from population_synthetic.analysis.real_population_stats.charts import (
    plot_category_bars,
    plot_overview_panel,
)
from population_synthetic.analysis.real_population_stats.csv_writer import write_proportions_csv
from population_synthetic.analysis.real_population_stats.stats import (
    CategoryStat,
    compute_category_stats,
)
from population_synthetic.analysis.utils.marginals import compute_proportions
from population_synthetic.analysis.utils.registry import get_process
from population_synthetic.gui.commands import build_per_country_cmds
from population_synthetic.gui.workflow_state import WorkflowState

# ---------------------------------------------------------------------------
# compute_category_stats
# ---------------------------------------------------------------------------


def _inds(attr: str, values: list) -> list[dict]:
    return [{attr: v} for v in values]


def test_proportions_match_compute_proportions_for_same_input():
    inds = _inds("biological_sex", ["male", "male", "female"])
    rows, extra = compute_category_stats(inds, "biological_sex", ["male", "female"])
    expected_props, expected_extra = compute_proportions(inds, "biological_sex", ["male", "female"])

    assert extra == expected_extra
    for row in rows:
        assert row.proportion == pytest.approx(expected_props[row.value])
        assert row.percent == pytest.approx(expected_props[row.value] * 100.0)


def test_per_category_counts_sum_to_total_when_no_extras():
    inds = _inds("biological_sex", ["male", "male", "male", "female", "female"])
    rows, extra = compute_category_stats(inds, "biological_sex", ["male", "female"])

    assert extra == []
    assert sum(row.count for row in rows) == rows[0].total
    assert rows[0].total == 5


def test_total_equals_non_null_count():
    inds = _inds("biological_sex", ["male", None, "female", None])
    rows, _extra = compute_category_stats(inds, "biological_sex", ["male", "female"])

    # 2 non-null out of 4 records -- the None values are excluded from N.
    assert rows[0].total == 2
    by_value = {row.value: row for row in rows}
    assert by_value["male"].count == 1
    assert by_value["female"].count == 1


def test_absent_config_value_is_explicit_zero():
    inds = _inds("biological_sex", ["male", "male", "male"])
    rows, extra = compute_category_stats(inds, "biological_sex", ["male", "female"])

    by_value = {row.value: row for row in rows}
    assert by_value["female"].count == 0
    assert by_value["female"].proportion == 0.0
    assert by_value["female"].percent == 0.0
    assert extra == []


def test_age_group_binned_from_raw_age():
    inds = [{"age": 20}, {"age": 21}, {"age": 30}]
    rows, extra = compute_category_stats(inds, "age_group", ["18-24", "25-34"])

    by_value = {row.value: row for row in rows}
    assert by_value["18-24"].count == 2
    assert by_value["25-34"].count == 1
    assert by_value["18-24"].proportion == pytest.approx(2 / 3)
    assert by_value["25-34"].proportion == pytest.approx(1 / 3)
    assert extra == []


def test_all_null_attribute_signals_zero_total_not_silent_zero():
    # Phase 1 contract (stats.py docstring): every row carries total == 0, a real
    # signal the caller inspects (rows[0].total == 0) to skip rendering --
    # compute_category_stats itself does not raise for an all-null attribute.
    inds = [{"biological_sex": None} for _ in range(3)]
    rows, extra = compute_category_stats(inds, "biological_sex", ["male", "female"])

    assert extra == []
    assert all(row.total == 0 for row in rows)
    assert all(row.count == 0 for row in rows)
    assert all(row.proportion == 0.0 for row in rows)


def test_extra_categories_returned_and_excluded_from_rows():
    inds = _inds("region", ["north", "south", "unmapped", "unmapped"])
    rows, extra = compute_category_stats(inds, "region", ["north", "south"])

    assert extra == ["unmapped"]
    assert [row.value for row in rows] == ["north", "south"]
    # total_non_null counts every observed value, including the unmapped ones.
    assert rows[0].total == 4


# ---------------------------------------------------------------------------
# write_proportions_csv
# ---------------------------------------------------------------------------


def _csv_rows() -> list[CategoryStat]:
    return [
        CategoryStat(value="a", count=3, total=4, proportion=0.75, percent=75.0),
        CategoryStat(value="b", count=1, total=4, proportion=0.25, percent=25.0),
    ]


def test_write_proportions_csv_exact_header(tmp_path: Path):
    path = write_proportions_csv(_csv_rows(), tmp_path / "attr.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == ["value", "count", "total", "proportion", "percent"]


def test_write_proportions_csv_one_row_per_category(tmp_path: Path):
    rows = _csv_rows()
    path = write_proportions_csv(rows, tmp_path / "attr.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        records = list(csv.DictReader(fh))
    assert len(records) == len(rows)
    assert [r["value"] for r in records] == [row.value for row in rows]


def test_write_proportions_csv_percent_equals_proportion_times_100(tmp_path: Path):
    path = write_proportions_csv(_csv_rows(), tmp_path / "attr.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        records = list(csv.DictReader(fh))
    for record in records:
        assert float(record["percent"]) == pytest.approx(float(record["proportion"]) * 100.0)


def test_write_proportions_csv_round_trips(tmp_path: Path):
    rows = _csv_rows()
    path = write_proportions_csv(rows, tmp_path / "attr.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        records = list(csv.DictReader(fh))
    assert int(records[0]["count"]) == rows[0].count
    assert int(records[0]["total"]) == rows[0].total
    assert float(records[0]["proportion"]) == pytest.approx(rows[0].proportion)


def test_write_proportions_csv_creates_parent_dir(tmp_path: Path):
    nested = tmp_path / "nested" / "dir" / "attr.csv"
    path = write_proportions_csv(_csv_rows(), nested)
    assert path == nested
    assert path.is_file()


# ---------------------------------------------------------------------------
# charts.py -- plot_category_bars / plot_overview_panel
# ---------------------------------------------------------------------------


def _chart_rows(n: int = 3) -> list[CategoryStat]:
    return [
        CategoryStat(value=f"c{i}", count=i, total=10, proportion=i / 10, percent=i * 10.0)
        for i in range(1, n + 1)
    ]


def test_plot_category_bars_returns_figure_no_disk_write(tmp_path: Path):
    before = set(tmp_path.iterdir())
    fig = plot_category_bars(_chart_rows(), "some_attr")
    try:
        assert isinstance(fig, matplotlib.figure.Figure)
        assert set(tmp_path.iterdir()) == before  # nothing written to disk
    finally:
        plt.close(fig)


def test_plot_category_bars_ylim_fixed_0_100():
    fig = plot_category_bars(_chart_rows(), "some_attr")
    try:
        ax = fig.axes[0]
        assert ax.get_ylim() == (0.0, 100.0)
    finally:
        plt.close(fig)


def test_plot_category_bars_has_four_dashed_reference_lines():
    fig = plot_category_bars(_chart_rows(), "some_attr")
    try:
        ax = fig.axes[0]
        horizontal_ys = set()
        for line in ax.get_lines():
            ydata = line.get_ydata()
            if len(set(ydata)) == 1:
                horizontal_ys.add(round(float(ydata[0])))
        assert {25, 50, 75, 100} <= horizontal_ys
    finally:
        plt.close(fig)


def test_plot_category_bars_has_per_bar_labels():
    rows = _chart_rows(4)
    fig = plot_category_bars(rows, "some_attr")
    try:
        ax = fig.axes[0]
        assert len(ax.texts) == len(rows)
    finally:
        plt.close(fig)


def test_plot_overview_panel_returns_figure(tmp_path: Path):
    before = set(tmp_path.iterdir())
    stats_by_attr = {"attr1": _chart_rows(2), "attr2": _chart_rows(3)}
    fig = plot_overview_panel(stats_by_attr)
    try:
        assert isinstance(fig, matplotlib.figure.Figure)
        assert set(tmp_path.iterdir()) == before
    finally:
        plt.close(fig)


def test_plot_overview_panel_has_one_axes_per_attribute_at_least():
    stats_by_attr = {"attr1": _chart_rows(2), "attr2": _chart_rows(3), "attr3": _chart_rows(2)}
    fig = plot_overview_panel(stats_by_attr)
    try:
        assert len(fig.axes) >= len(stats_by_attr)
    finally:
        plt.close(fig)


def test_plot_overview_panel_empty_raises():
    with pytest.raises(ValueError):
        plot_overview_panel({})


# ---------------------------------------------------------------------------
# gui/commands.py -- build_per_country_cmds
# ---------------------------------------------------------------------------

SCRIPT = Path("scripts/analyze/analyze_real_population_stats.py")


def test_build_per_country_cmds_dedupes_3x2_combos_to_one_country():
    combos = [
        (model, strategy, "swedish")
        for model in ("claude_haiku", "claude_sonnet", "gemini_flash")
        for strategy in ("all_pick", "free_gen")
    ]
    cmds = build_per_country_cmds(SCRIPT, combos, force=False, options={})

    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd == [sys.executable, str(SCRIPT), "--country-id", "swedish"]
    assert "--model-id" not in cmd
    assert "--strategy-id" not in cmd


def test_build_per_country_cmds_two_countries_first_seen_order():
    combos = [
        ("claude_haiku", "all_pick", "swedish"),
        ("claude_haiku", "all_pick", "italian"),
        ("gemini_flash", "free_gen", "swedish"),
    ]
    cmds = build_per_country_cmds(SCRIPT, combos, force=False, options={})

    assert len(cmds) == 2
    assert cmds[0] == [sys.executable, str(SCRIPT), "--country-id", "swedish"]
    assert cmds[1] == [sys.executable, str(SCRIPT), "--country-id", "italian"]


def test_build_per_country_cmds_force_appends_flag():
    combos = [("claude_haiku", "all_pick", "swedish")]
    cmds = build_per_country_cmds(SCRIPT, combos, force=True, options={})
    assert "--force" in cmds[0]


def test_build_per_country_cmds_without_force_omits_flag():
    combos = [("claude_haiku", "all_pick", "swedish")]
    cmds = build_per_country_cmds(SCRIPT, combos, force=False, options={})
    assert "--force" not in cmds[0]


def test_build_per_country_cmds_option_args_translate_correctly():
    combos = [("claude_haiku", "all_pick", "swedish")]
    options = {"dpi": 300, "no-charts": True, "output-base": None, "verbose": False}
    cmds = build_per_country_cmds(SCRIPT, combos, force=False, options=options)
    cmd = cmds[0]

    assert "--dpi" in cmd
    assert cmd[cmd.index("--dpi") + 1] == "300"
    assert "--no-charts" in cmd
    assert "--output-base" not in cmd
    assert "--verbose" not in cmd


def test_build_per_country_cmds_empty_combos_raises():
    with pytest.raises(ValueError, match="no combos"):
        build_per_country_cmds(SCRIPT, [], force=False, options={})


# ---------------------------------------------------------------------------
# Registry + workflow-engine wiring for the new `per_country` dispatch
# ---------------------------------------------------------------------------


def test_real_population_stats_registry_dispatch_is_per_country():
    proc = get_process("real_population_stats")
    assert proc.dispatch == "per_country"
    assert proc.folder == "real_population_stats"


def _workflow_task(script: str = "task.py", dispatch: str = "per_country", enabled: bool = True,
                    depends_on: list[str] | None = None) -> dict:
    return {
        "label": "T",
        "script": script,
        "dispatch": dispatch,
        "enabled": enabled,
        "options": {},
        "depends_on": depends_on if depends_on is not None else [],
    }


@pytest.fixture
def workflow_root(tmp_path: Path) -> Path:
    (tmp_path / "task.py").write_text("# stub\n", encoding="utf-8")
    return tmp_path


def test_workflow_state_validates_a_per_country_node(workflow_root: Path):
    state = WorkflowState({"tasks": {"a": _workflow_task(dispatch="per_country")}}, workflow_root)
    state.validate()  # must not raise

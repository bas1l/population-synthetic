"""Tests for the axis chip-row *defaults* in the Flow Runner's Global tab.

Sibling of ``test_axis_version_filter.py``, which covers the filter mechanism
itself. This file covers which chips a freshly built :class:`AxisSelector` opens
with, and the config metadata those defaults are read from:

* models — an ``Active`` / ``Discarded`` split from each model axis YAML's
  top-level ``discarded`` key (**absent means active**), opening on ``Active``;
* strategies — ``v{n}`` chips from each strategy's ``version``, opening on the
  **highest** discovered version.

Both defaults are derived, never literal: no test here writes ``"v2"``, so a v3
strategy config extends these assertions instead of breaking them. The retaining
rule (``visible = matches(active chips) OR isChecked()``) is re-asserted against
the narrowed defaults, since a default filter is exactly the situation where a
selected-but-filtered-out row would go missing.
"""

from __future__ import annotations

import os
import shutil

import pytest
import yaml

pytest.importorskip("PyQt5")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.utils.axes import strategy_versions  # noqa: E402
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values  # noqa: E402
from population_synthetic.gui.flow_config_model import FlowConfigModel  # noqa: E402
from population_synthetic.gui.widgets.axis_selector import (  # noqa: E402
    AxisSelector,
    axis_facets,
    model_status_facet_groups,
)
from population_synthetic.gui.widgets.checkable_axis_list import CheckableAxisList  # noqa: E402

FLOW_YAML = PROJECT_ROOT / "config" / "gui" / "flows" / "generate_parallel.yaml"

# The five models retired from the sweep. Named here so the test pins the intent
# ("these five, and only these five") rather than restating whatever config says.
DISCARDED_MODEL_IDS = {
    "ollama_gemma2_9b",
    "ollama_llama32_3b",
    "ollama_llama33_70b",
    "ollama_lucie_7b",
    "ollama_qwen3_14b",
}


@pytest.fixture(scope="session")
def qapp():
    """One offscreen QApplication for the whole session (Qt allows only one)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def selector(qapp):
    widget = AxisSelector()
    yield widget
    widget.deleteLater()


def _chip_state(axis_list: CheckableAxisList) -> dict[str, bool]:
    return {chip.text(): chip.isChecked() for chip, _members in axis_list._facet_boxes}


def _highest_version_ids() -> tuple[int, list[str]]:
    versions = strategy_versions([item["id"] for item in discover_axis_values("strategies")])
    highest = max(versions.values())
    return highest, sorted(sid for sid, v in versions.items() if v == highest)


# ----------------------------------------------------------------------
# 1. `discarded` is structured config, not label text
# ----------------------------------------------------------------------


def test_discarded_models_declare_the_key_and_carry_a_clean_label():
    items = {item["id"]: item for item in discover_axis_values("models")}
    assert DISCARDED_MODEL_IDS <= set(items)

    for model_id in DISCARDED_MODEL_IDS:
        item = items[model_id]
        assert item["discarded"] is True, f"{model_id} must declare discarded: true"
        assert "discarded" not in item["label"].lower(), f"{model_id} label still encodes its status"


def test_no_model_label_encodes_a_discarded_status():
    """The status moved out of the label string entirely — no residue anywhere."""
    for item in discover_axis_values("models"):
        assert "(discarded" not in item["label"].lower()


def test_absent_discarded_key_means_active():
    """The 15 live files carry no key at all — the default must be documented, not `false`."""
    items = discover_axis_values("models")
    active = {item["id"] for item in items} - DISCARDED_MODEL_IDS
    assert active, "config should discover at least one active model"
    for item in items:
        if item["id"] in active:
            assert "discarded" not in item, f"{item['id']} should omit the key, not set it false"

    groups = dict(model_status_facet_groups(items))
    assert set(groups["Active"]) == active
    assert set(groups["Discarded"]) == DISCARDED_MODEL_IDS


def test_model_status_groups_reject_a_non_boolean_flag():
    with pytest.raises(ValueError, match="must be a boolean"):
        model_status_facet_groups([{"id": "m", "label": "M", "discarded": "yes"}])


def test_model_status_groups_always_emit_both_chips():
    """Both labels exist even when a side is empty, so `initially_checked` can always name them."""
    groups = model_status_facet_groups([{"id": "m", "label": "M"}])
    assert [label for label, _ids in groups] == ["Active", "Discarded"]
    assert dict(groups)["Discarded"] == []


# ----------------------------------------------------------------------
# 2. set_facets(initially_checked=...) is fail-fast
# ----------------------------------------------------------------------


def _bare_list(qapp) -> CheckableAxisList:
    widget = CheckableAxisList("T")
    widget.populate([{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    return widget


def test_set_facets_raises_on_unknown_initially_checked_group(qapp):
    widget = _bare_list(qapp)
    with pytest.raises(ValueError, match="unknown chips"):
        widget.set_facets("G", [("x", ["a"]), ("y", ["b"])], initially_checked={"x", "typo"})


def test_set_facets_raises_on_duplicate_chip_labels(qapp):
    widget = _bare_list(qapp)
    with pytest.raises(ValueError, match="duplicate chip labels"):
        widget.set_facets("G", [("x", ["a"]), ("x", ["b"])])


def test_set_facets_without_initially_checked_keeps_the_old_behaviour(qapp):
    """The default stays `None` == every chip checked, for any caller that had one."""
    widget = _bare_list(qapp)
    widget.set_facets("G", [("x", ["a"]), ("y", ["b"])])
    assert _chip_state(widget) == {"x": True, "y": True}
    assert widget.visible_ids() == ["a", "b"]


def test_set_facets_checks_exactly_the_named_groups(qapp):
    widget = _bare_list(qapp)
    widget.set_facets("G", [("x", ["a"]), ("y", ["b"])], initially_checked={"y"})
    assert _chip_state(widget) == {"x": False, "y": True}
    assert widget.visible_ids() == ["b"]


def test_set_facets_accepts_an_empty_initially_checked(qapp):
    """Not the same as None: no chip checked hides every *unchecked* row."""
    widget = _bare_list(qapp)
    widget.set_facets("G", [("x", ["a"]), ("y", ["b"])], initially_checked=set())
    assert _chip_state(widget) == {"x": False, "y": False}
    assert widget.visible_ids() == []


# ----------------------------------------------------------------------
# 3. The defaults the two faceted axes actually open with
# ----------------------------------------------------------------------


def test_strategies_open_on_the_highest_version_only(selector):
    highest, highest_ids = _highest_version_ids()
    state = _chip_state(selector._axis_lists["strategies"])

    assert len(state) > 1, "config should discover at least two strategy versions for this to bite"
    assert state[f"v{highest}"] is True
    assert [label for label, checked in state.items() if checked] == [f"v{highest}"]
    # Nothing is selected on a fresh widget, so the filter alone decides the view.
    assert selector._axis_lists["strategies"].visible_ids() == highest_ids


def test_the_highest_version_default_is_derived_not_hardcoded(monkeypatch):
    """A hypothetical extra version becomes the default with no code change."""
    import population_synthetic.gui.widgets.axis_selector as mod

    fake = {"s1": 1, "s2": 2, "s3": 7}
    monkeypatch.setattr(
        mod, "strategy_versions", lambda ids, *, strategies_dir=None: {i: fake[i] for i in ids}
    )

    title, groups, initially_checked = axis_facets("strategies", [{"id": i} for i in fake])

    assert title == "Version"
    assert [label for label, _ids in groups] == ["v1", "v2", "v7"]
    assert initially_checked == {"v7"}


def test_models_open_on_active_only(selector):
    axis_list = selector._axis_lists["models"]
    assert _chip_state(axis_list) == {"Active": True, "Discarded": False}

    discovered = {item["id"] for item in discover_axis_values("models")}
    assert set(axis_list.visible_ids()) == discovered - DISCARDED_MODEL_IDS


def test_countries_stay_unfaceted(selector):
    assert axis_facets("countries", discover_axis_values("countries")) is None
    assert selector._axis_lists["countries"]._facet_boxes == []
    assert selector._axis_lists["countries"].visible_ids() == [
        item["id"] for item in discover_axis_values("countries")
    ]


# ----------------------------------------------------------------------
# 4. THE INVARIANT, under the narrowed defaults
# ----------------------------------------------------------------------


def test_a_flow_selecting_an_out_of_default_strategy_is_checked_and_visible(selector, tmp_path):
    """The whole point of the retaining rule: a default filter cannot hide a run."""
    versions = strategy_versions([item["id"] for item in discover_axis_values("strategies")])
    lowest = min(versions.values())
    assert lowest != max(versions.values())
    old_id = sorted(sid for sid, v in versions.items() if v == lowest)[0]

    axis_list = selector._axis_lists["strategies"]
    # Untouched defaults: the lowest-version chip is off.
    assert _chip_state(axis_list)[f"v{lowest}"] is False

    path = tmp_path / "flow.yaml"
    shutil.copyfile(FLOW_YAML, path)
    staged = FlowConfigModel(path)
    staged.set_selection("strategies", [old_id])
    staged.save()
    selector.bind(FlowConfigModel(path))

    assert axis_list.selected_ids() == [old_id]
    assert old_id in axis_list.visible_ids()
    assert set(axis_list.visible_ids()) >= set(axis_list.selected_ids())
    # ...and the chip stayed off: binding a flow is not allowed to widen the view.
    assert _chip_state(axis_list)[f"v{lowest}"] is False


def test_the_invariant_holds_on_every_axis_right_after_bind(selector, tmp_path):
    path = tmp_path / "flow.yaml"
    shutil.copyfile(FLOW_YAML, path)
    selector.bind(FlowConfigModel(path))

    for axis in ("models", "strategies", "countries"):
        axis_list = selector._axis_lists[axis]
        assert set(axis_list.visible_ids()) >= set(axis_list.selected_ids()), axis


# ----------------------------------------------------------------------
# 5. The shipped flow default
# ----------------------------------------------------------------------


def test_flow_default_selects_exactly_the_highest_version_strategies():
    _highest, highest_ids = _highest_version_ids()
    with open(FLOW_YAML, "r", encoding="utf-8") as fh:
        selection = yaml.safe_load(fh)["selection"]
    assert sorted(selection["strategies"]) == highest_ids

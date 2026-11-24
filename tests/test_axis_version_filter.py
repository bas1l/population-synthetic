"""Tests for the strategy-axis version filter in the Flow Runner's Global tab.

The filter is a **retaining** view control on :class:`CheckableAxisList`:

    visible = matches(active facets) OR isChecked()

so a checked item is never hidden and the invariant
``set(visible_ids()) >= set(selected_ids())`` — everything that will run is on
screen — holds at all times. The chips carry no state: toggling one emits no
``selection_changed``, changes no check, and never dirties the bound flow YAML.

Everything version-shaped here is derived from ``strategy_versions()`` over the
discovered axis files; no test hardcodes ``["v1", "v2"]``, so adding a v3
strategy config extends these assertions instead of breaking them.

These are the first Qt-widget tests in the suite, hence the local session-scoped
``QApplication`` fixture (offscreen platform) rather than a conftest change.
"""

from __future__ import annotations

import os
import shutil

import pytest

pytest.importorskip("PyQt5")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.utils.axes import strategy_versions  # noqa: E402
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values  # noqa: E402
from population_synthetic.gui.flow_config_model import FlowConfigModel  # noqa: E402
from population_synthetic.gui.widgets.axis_selector import AxisSelector, mixed_version_notice  # noqa: E402
from population_synthetic.gui.widgets.checkable_axis_list import CheckableAxisList  # noqa: E402

FLOW_YAML = PROJECT_ROOT / "config" / "gui" / "flows" / "generate_parallel.yaml"


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


def _strategy_list(selector: AxisSelector) -> CheckableAxisList:
    return selector._axis_lists["strategies"]


def _discovered_versions() -> dict[str, int]:
    items = discover_axis_values("strategies")
    return strategy_versions([item["id"] for item in items])


def _chip(axis_list: CheckableAxisList, label: str):
    for chip, _members in axis_list._facet_boxes:
        if chip.text() == label:
            return chip
    raise AssertionError(f"no chip labelled {label!r} (have {[c.text() for c, _ in axis_list._facet_boxes]})")


def _unfilter(axis_list: CheckableAxisList) -> None:
    """Check every chip, i.e. show everything.

    The axis opens on a *narrowed* default (highest version only — see
    ``test_axis_facet_defaults.py``); tests below that reason about the
    unfiltered list widen it explicitly first rather than relying on the default.
    """
    for chip, _members in axis_list._facet_boxes:
        chip.setChecked(True)


def _flow_copy(tmp_path, strategy_ids: list[str] | None = None) -> FlowConfigModel:
    """A clean FlowConfigModel over a temp copy of the generate flow YAML."""
    path = tmp_path / "flow.yaml"
    shutil.copyfile(FLOW_YAML, path)
    if strategy_ids is not None:
        staged = FlowConfigModel(path)
        staged.set_selection("strategies", strategy_ids)
        staged.save()
    return FlowConfigModel(path)  # freshly loaded => not dirty


# ----------------------------------------------------------------------
# 1. Chips come from config
# ----------------------------------------------------------------------


def test_chip_labels_and_membership_match_config_versions(selector):
    versions = _discovered_versions()
    expected = {
        f"v{v}": {sid for sid, sv in versions.items() if sv == v}
        for v in sorted(set(versions.values()))
    }

    axis_list = _strategy_list(selector)
    actual = {chip.text(): set(members) for chip, members in axis_list._facet_boxes}

    assert actual == expected
    assert len(expected) > 1, "config should discover at least two strategy versions for this test to bite"
    # Chips partition the populated ids; checking them all shows everything.
    assert set().union(*actual.values()) == set(versions)
    _unfilter(axis_list)
    assert set(axis_list.visible_ids()) == set(versions)


def test_the_countries_axis_is_unfaceted(selector):
    """Countries declare neither `version` nor `discarded`, so nothing to facet on."""
    assert _strategy_list(selector)._facet_boxes
    assert selector._axis_lists["countries"]._facet_boxes == []
    # No facets == no filtering: every populated id stays visible.
    assert selector._axis_lists["countries"].visible_ids() == [
        item["id"] for item in discover_axis_values("countries")
    ]


# ----------------------------------------------------------------------
# 2. THE INVARIANT
# ----------------------------------------------------------------------


def test_checked_items_are_never_hidden(selector):
    versions = _discovered_versions()
    lowest = min(versions.values())
    axis_list = _strategy_list(selector)
    axis_list.set_selected(list(versions))
    _unfilter(axis_list)

    before = axis_list.selected_ids()
    _chip(axis_list, f"v{lowest}").setChecked(False)
    after = axis_list.selected_ids()

    assert set(axis_list.visible_ids()) >= set(after)
    assert after == before  # a view control must not touch the selection


def test_invariant_holds_for_every_chip_subset(selector):
    """Retaining rule, exhaustively: no chip combination can hide a checked row."""
    versions = _discovered_versions()
    axis_list = _strategy_list(selector)
    axis_list.set_selected(list(versions))
    chips = [chip for chip, _ in axis_list._facet_boxes]

    for mask in range(2 ** len(chips)):
        for i, chip in enumerate(chips):
            chip.setChecked(bool(mask >> i & 1))
        assert set(axis_list.visible_ids()) >= set(axis_list.selected_ids())


def test_unfiltered_rows_hide_when_unchecked(selector):
    """The filter really filters: an unchecked, out-of-facet row leaves the view."""
    versions = _discovered_versions()
    lowest = min(versions.values())
    axis_list = _strategy_list(selector)
    axis_list.set_selected([])
    _unfilter(axis_list)

    _chip(axis_list, f"v{lowest}").setChecked(False)

    hidden = {sid for sid, v in versions.items() if v == lowest}
    assert set(axis_list.visible_ids()) == set(versions) - hidden


# ----------------------------------------------------------------------
# 3-4. The chip row is not state
# ----------------------------------------------------------------------


def test_chip_toggle_neither_dirties_the_model_nor_emits(selector, tmp_path):
    model = _flow_copy(tmp_path)
    selector.bind(model)
    assert not model.is_dirty

    emissions = []
    selector.selection_changed.connect(lambda: emissions.append(1))

    versions = _discovered_versions()
    for v in sorted(set(versions.values())):
        chip = _chip(_strategy_list(selector), f"v{v}")
        chip.setChecked(False)
        chip.setChecked(True)

    assert not model.is_dirty
    assert emissions == []
    assert model.get_selection("strategies") == FlowConfigModel(model.path).get_selection("strategies")


def test_combo_count_is_indifferent_to_chip_state(selector, tmp_path):
    selector.bind(_flow_copy(tmp_path))
    baseline = len(selector.checked_combos())
    assert baseline > 0

    versions = _discovered_versions()
    for v in sorted(set(versions.values())):
        _chip(_strategy_list(selector), f"v{v}").setChecked(False)
        assert len(selector.checked_combos()) == baseline
    for v in sorted(set(versions.values())):
        _chip(_strategy_list(selector), f"v{v}").setChecked(True)
        assert len(selector.checked_combos()) == baseline


# ----------------------------------------------------------------------
# 5. Loading an older flow through a narrower filter
# ----------------------------------------------------------------------


def test_binding_an_out_of_filter_selection_retains_it(selector, tmp_path):
    versions = _discovered_versions()
    lowest, highest = min(versions.values()), max(versions.values())
    assert lowest != highest
    old_ids = sorted(sid for sid, v in versions.items() if v == lowest)

    axis_list = _strategy_list(selector)
    # Filter narrowed to the newest version only...
    for v in sorted(set(versions.values())):
        _chip(axis_list, f"v{v}").setChecked(v == highest)

    # ...then an older flow, selecting only lowest-version strategies, is loaded.
    selector.bind(_flow_copy(tmp_path, strategy_ids=old_ids))

    assert axis_list.selected_ids() == old_ids
    assert set(axis_list.visible_ids()) >= set(old_ids)
    assert set(axis_list.visible_ids()) >= set(axis_list.selected_ids())


# ----------------------------------------------------------------------
# 6. set_facets is a strict partition (fail-fast)
# ----------------------------------------------------------------------


def _bare_list(qapp) -> CheckableAxisList:
    widget = CheckableAxisList("T")
    widget.populate([{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    return widget


def test_set_facets_raises_on_ungrouped_id(qapp):
    widget = _bare_list(qapp)
    with pytest.raises(ValueError, match="belong to no group"):
        widget.set_facets("Version", [("x", ["a"])])


def test_set_facets_raises_on_duplicated_id(qapp):
    widget = _bare_list(qapp)
    with pytest.raises(ValueError, match="appears in"):
        widget.set_facets("Version", [("x", ["a", "b"]), ("y", ["b"])])


def test_set_facets_raises_on_unknown_id(qapp):
    widget = _bare_list(qapp)
    with pytest.raises(ValueError, match="not a populated item"):
        widget.set_facets("Version", [("x", ["a", "b"]), ("y", ["zzz"])])


# ----------------------------------------------------------------------
# 7. The advisory notice
# ----------------------------------------------------------------------


def test_mixed_version_notice_is_none_for_a_single_version():
    versions = _discovered_versions()
    lowest = min(versions.values())
    same = [sid for sid, v in versions.items() if v == lowest]
    assert mixed_version_notice(same) is None
    assert mixed_version_notice([]) is None


def test_mixed_version_notice_names_both_versions():
    versions = _discovered_versions()
    lowest, highest = min(versions.values()), max(versions.values())
    mixed = [
        next(sid for sid, v in versions.items() if v == lowest),
        next(sid for sid, v in versions.items() if v == highest),
    ]
    notice = mixed_version_notice(mixed)
    assert notice is not None
    assert f"v{lowest}" in notice and f"v{highest}" in notice


def test_version_warning_label_follows_the_selection(selector, tmp_path):
    versions = _discovered_versions()
    lowest = min(versions.values())
    selector.bind(_flow_copy(tmp_path))
    axis_list = _strategy_list(selector)

    axis_list.set_selected([next(sid for sid, v in versions.items() if v == lowest)])
    assert selector._version_warning.text() == ""
    assert selector._version_warning.isHidden()

    axis_list.set_selected(list(versions))
    assert selector._version_warning.text() == mixed_version_notice(list(versions))
    # Advisory only: the mixed selection is still fully selectable and runnable.
    assert len(selector.checked_combos()) > 0


# ----------------------------------------------------------------------
# 8. The retained marker is recomputed, never appended
# ----------------------------------------------------------------------


def test_retained_marker_does_not_accumulate(selector):
    versions = _discovered_versions()
    lowest = min(versions.values())
    axis_list = _strategy_list(selector)
    axis_list.set_selected(list(versions))
    _unfilter(axis_list)
    chip = _chip(axis_list, f"v{lowest}")

    retained_index = next(i for i, item in enumerate(axis_list._items) if versions[item["id"]] == lowest)
    box = axis_list._checkboxes[retained_index]
    base_label = axis_list._items[retained_index]["label"]

    chip.setChecked(False)
    marked = box.text()
    assert marked != base_label and base_label in marked and f"v{lowest}" in marked

    for _ in range(4):
        chip.setChecked(True)
        assert box.text() == base_label  # marker removed, not stacked
        chip.setChecked(False)
        assert box.text() == marked

    chip.setChecked(True)
    assert box.text() == base_label

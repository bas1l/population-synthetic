"""AxisSelector — the Options column's *Global* tab: three checkable axis lists.

Composes three reused :class:`CheckableAxisList` widgets (models, strategies,
countries — mirroring the legacy ``ExperimentSelector`` composition)
populated from
``discover_axis_values``, plus a "Combos: N" label showing the
cartesian-product count and a "Force reprocessing" checkbox shown only for
flows whose YAML declares a top-level ``force:`` key (generate flows).

Persistence goes through the bound :class:`FlowConfigModel` — checks write
``selection:``/``force:`` via ``set_selection``/``set_force`` (marking the
model dirty). This widget never reads or writes ``config/gui/state.json``;
that file belongs to the legacy launcher.
"""

from __future__ import annotations

import itertools
from functools import partial
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from population_synthetic.analysis.utils.axes import strategy_versions
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values
from population_synthetic.gui.flow_config_model import FlowConfigModel
from population_synthetic.gui.widgets.checkable_axis_list import CheckableAxisList

# Axis keys in flow-YAML `selection:` order == cartesian-product significance
# order (model-major, country fastest) — same ordering as the legacy
# `ExperimentSelection.combinations()` (`gui/manifest_model.py`).
#
# The third field is the vertical stretch weight: how the column's height is
# shared between the three lists. Models carries the most values and so the most
# weight, but deliberately sub-proportionally — a strict 20:5:3 split starves the
# strategy list. Qt allocates proportionally to these weights subject to each
# list's floor (~3 rows) and its content ceiling (see
# CheckableAxisList._apply_content_ceiling), so countries settles on its floor
# and the models/strategies pair splits what remains ~11:8. These are
# visual-balance numbers for this widget only; they are not data config and
# nothing outside the layout reads them.
_AXES: tuple[tuple[str, str, int], ...] = (
    ("models", "Models", 11),
    ("strategies", "Strategies", 8),
    ("countries", "Countries", 2),
)

# Which axes get a version chip row. Structural, not vocabulary: only strategy
# axis files declare a `version:` key, so only that axis can be faceted by one.
# The chip labels themselves are always derived from the config values.
_VERSION_FACETED_AXES = frozenset({"strategies"})


def cartesian_combos(
    model_ids: list[str], strategy_ids: list[str], country_ids: list[str]
) -> list[tuple[str, str, str]]:
    """Deterministic cartesian product of the three checked-id lists.

    Pure helper (no Qt) so combo ordering is unit-testable headlessly.
    Order is model-major, then strategy, then country — each axis in its
    input order (the discovered sorted-by-id order for GUI callers), matching
    the legacy launcher's ``ExperimentSelection.combinations()``.
    """
    return list(itertools.product(model_ids, strategy_ids, country_ids))


def version_facet_groups(
    items: list[dict], *, strategies_dir: str | Path | None = None
) -> list[tuple[str, list[str]]]:
    """Partition *items* into ``[("v{n}", [ids]), ...]``, ascending version.

    Pure helper (no Qt). The chip labels come from the strategies' declared
    ``version:`` values, never from a hardcoded ``["v1", "v2"]`` — a v3 axis file
    appears as a chip the moment it is dropped into the config directory.
    Raises (via :func:`strategy_versions`) when any id lacks a valid version.
    """
    versions = strategy_versions([item["id"] for item in items], strategies_dir=strategies_dir)
    return [
        (f"v{version}", [i for i, v in versions.items() if v == version])
        for version in sorted(set(versions.values()))
    ]


def mixed_version_notice(
    strategy_ids: list[str], *, strategies_dir: str | Path | None = None
) -> str | None:
    """Advisory text when *strategy_ids* span more than one version, else ``None``.

    Pure helper (no Qt) so the wording is unit-testable headlessly. Strictly
    **advisory**: versions of one family are separate experimental arms, and
    generating both arms in a single run is legitimate — nothing here blocks or
    vetoes the selection; it only makes the mix visible before Run.
    """
    if not strategy_ids:
        return None
    versions = sorted(set(strategy_versions(list(strategy_ids), strategies_dir=strategies_dir).values()))
    if len(versions) < 2:
        return None
    listed = ", ".join(f"v{v}" for v in versions)
    return (
        f"Mixed strategy versions selected ({listed}). Versions are separate experimental "
        "arms, not replicates — check this is intended."
    )


class AxisSelector(QWidget):
    """Three flat checkable axis lists driving the flow's combo selection.

    API: :meth:`bind` (re)targets a :class:`FlowConfigModel` (``None`` →
    disabled/empty); :meth:`checked_combos` returns the cartesian product of
    the checked ids; :attr:`selection_changed` fires after any check or force
    toggle has been written through the model (which is then dirty).
    """

    selection_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: FlowConfigModel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._axis_lists: dict[str, CheckableAxisList] = {}
        self._known_ids: dict[str, set[str]] = {}
        for axis, title, weight in _AXES:
            axis_list = CheckableAxisList(title, self)
            # discover_axis_values raises on a malformed axis file — fail-fast.
            items = discover_axis_values(axis)
            axis_list.populate(items)
            if axis in _VERSION_FACETED_AXES:
                # version_facet_groups raises on a strategy missing `version:`.
                axis_list.set_facets("Version", version_facet_groups(items))
            self._known_ids[axis] = {item["id"] for item in items}
            axis_list.selection_changed.connect(partial(self._on_axis_changed, axis))
            layout.addWidget(axis_list, stretch=weight)  # see _AXES on the weights
            self._axis_lists[axis] = axis_list

        self._combos_label = QLabel()
        layout.addWidget(self._combos_label)

        # Advisory only — never a veto. A run mixing versions is legitimate;
        # this label just makes the mix impossible to miss before Run.
        self._version_warning = QLabel()
        self._version_warning.setWordWrap(True)
        self._version_warning.setVisible(False)
        layout.addWidget(self._version_warning)

        self._force_checkbox = QCheckBox("Force reprocessing")
        self._force_checkbox.setVisible(False)  # generate flows only (YAML has a `force:` key)
        self._force_checkbox.toggled.connect(self._on_force_toggled)
        layout.addWidget(self._force_checkbox)

        # Stretch factor 0: this spacer claims nothing while any axis list can
        # still grow, and only collects the leftover once every list has hit its
        # content ceiling (a very tall window) — where the alternative is Qt
        # spreading that leftover as gaps between the group boxes.
        layout.addStretch(0)

        self._update_combos_label()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bind(self, model: FlowConfigModel | None) -> None:
        """(Re)target *model*: restore checks/force from its YAML blocks.

        ``None`` detaches: all checks cleared, widget disabled. Restoring
        never writes back (the model stays clean). Fail-fast: a missing
        ``selection:`` axis or an id unknown to the discovered axis values
        raises *before* any widget state is touched, so the previously bound
        flow's checks survive a failed bind.
        """
        if model is None:
            self._model = None
            for axis_list in self._axis_lists.values():
                axis_list.set_selected([])
            self._force_checkbox.setVisible(False)
            self._update_combos_label()
            self.setEnabled(False)
            return

        # Validate everything before mutating any widget state.
        selection = {axis: model.get_selection(axis) for axis, _title, _weight in _AXES}
        for axis, ids in selection.items():
            unknown = [i for i in ids if i not in self._known_ids[axis]]
            if unknown:
                raise ValueError(
                    f"Flow config {model.path}: selection '{axis}' contains unknown ids {unknown} "
                    f"(discovered: {sorted(self._known_ids[axis])})"
                )
        force = model.get_force() if model.has_force() else None

        self._model = None  # detach while restoring so checks are not written back
        for axis, ids in selection.items():
            self._axis_lists[axis].set_selected(ids)
        self._force_checkbox.blockSignals(True)
        self._force_checkbox.setVisible(force is not None)
        self._force_checkbox.setChecked(bool(force))
        self._force_checkbox.blockSignals(False)
        self._model = model
        self._update_combos_label()
        self.setEnabled(True)

    def checked_combos(self) -> list[tuple[str, str, str]]:
        """Cartesian product of the checked (model_id, strategy_id, country_id) ids."""
        return cartesian_combos(
            self._axis_lists["models"].selected_ids(),
            self._axis_lists["strategies"].selected_ids(),
            self._axis_lists["countries"].selected_ids(),
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_axis_changed(self, axis: str, ids: list) -> None:
        """A CheckableAxisList changed — write through the model and notify."""
        self._update_combos_label()
        if self._model is None:
            return  # detached (or mid-bind restore): display-only update
        self._model.set_selection(axis, list(ids))  # marks the model dirty
        self.selection_changed.emit()

    def _on_force_toggled(self, checked: bool) -> None:
        if self._model is None:
            return
        self._model.set_force(checked)  # marks the model dirty
        self.selection_changed.emit()

    def _update_combos_label(self) -> None:
        self._combos_label.setText(f"Combos: {len(self.checked_combos())}")
        notice = mixed_version_notice(self._axis_lists["strategies"].selected_ids())
        self._version_warning.setText(notice or "")
        self._version_warning.setVisible(notice is not None)

"""ConfigurationPanel — middle column combining selector and parameters.

``ConfigurationPanel`` is a ``QWidget`` that stacks an ``ExperimentSelector``
(model/strategy/country axes) above a ``ParameterPanel`` (per-action CLI
overrides), toggling the selector's visibility by whether the action requires
a manifest and re-emitting ``selection_changed``.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from population_synthetic.gui.launcher_config import ActionEntry
from population_synthetic.gui.manifest_model import ExperimentSelection, ManifestDisplayInfo
from population_synthetic.gui.widgets.manifest_selector import ExperimentSelector
from population_synthetic.gui.widgets.parameter_panel import ParameterPanel


class ConfigurationPanel(QWidget):
    """Middle-column widget: composes ExperimentSelector and ParameterPanel."""

    selection_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._experiment_selector = ExperimentSelector(self)
        self._parameter_panel = ParameterPanel(self)

        layout.addWidget(self._experiment_selector)
        layout.addWidget(self._parameter_panel)
        layout.addStretch()

        self._experiment_selector.selection_changed.connect(self.selection_changed)

    def update_for_action(self, action: ActionEntry) -> None:
        """Toggle experiment selector visibility and repopulate parameters."""
        self._experiment_selector.setVisible(action.axis_mode in {"per_combo", "batch"})
        self._parameter_panel.populate(action.parameters, self.current_manifest())

    def current_selection(self) -> ExperimentSelection:
        return self._experiment_selector.current_selection()

    def current_manifest(self) -> ManifestDisplayInfo | None:
        return self._experiment_selector.first_manifest()

    def get_overrides(self) -> dict:
        return self._parameter_panel.get_overrides()

    @property
    def force(self) -> bool:
        return self._experiment_selector.force

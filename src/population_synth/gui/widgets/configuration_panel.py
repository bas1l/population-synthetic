from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from population_synth.gui.launcher_config import ActionEntry
from population_synth.gui.manifest_model import ManifestDisplayInfo
from population_synth.gui.widgets.manifest_selector import ExperimentSelector
from population_synth.gui.widgets.parameter_panel import ParameterPanel


class ConfigurationPanel(QWidget):
    """Middle-column widget: composes ExperimentSelector and ParameterPanel."""

    manifest_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._experiment_selector = ExperimentSelector(self)
        self._parameter_panel = ParameterPanel(self)

        layout.addWidget(self._experiment_selector)
        layout.addWidget(self._parameter_panel)
        layout.addStretch()

        # Re-emit manifest_changed from internal ExperimentSelector
        self._experiment_selector.manifest_changed.connect(self.manifest_changed)

    def update_for_action(self, action: ActionEntry) -> None:
        """Toggle experiment selector visibility and repopulate parameters."""
        self._experiment_selector.setVisible(action.requires_manifest)
        self._parameter_panel.populate(action.parameters, self.current_manifest())

    def current_manifest(self) -> ManifestDisplayInfo | None:
        return self._experiment_selector.current_manifest()

    def get_overrides(self) -> dict:
        return self._parameter_panel.get_overrides()

    @property
    def force(self) -> bool:
        return self._experiment_selector.force

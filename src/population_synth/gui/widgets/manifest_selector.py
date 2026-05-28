from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from population_synth.gui.manifest_model import ManifestDisplayInfo
from population_synth.identity.manifest_loader import discover_axis_values


class ExperimentSelector(QWidget):
    manifest_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        axis_box = QGroupBox("Model Selection")
        axis_form = QFormLayout(axis_box)
        axis_form.setContentsMargins(4, 4, 4, 4)

        self._model_combo = QComboBox()
        self._strategy_combo = QComboBox()
        self._country_combo = QComboBox()

        axis_form.addRow("Model:", self._model_combo)
        axis_form.addRow("Strategy:", self._strategy_combo)
        axis_form.addRow("Country:", self._country_combo)
        layout.addWidget(axis_box)

        self._force_checkbox = QCheckBox("Force reprocessing")
        layout.addWidget(self._force_checkbox)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        self._model_combo.currentIndexChanged.connect(self._on_selection_changed)
        self._strategy_combo.currentIndexChanged.connect(self._on_selection_changed)
        self._country_combo.currentIndexChanged.connect(self._on_selection_changed)
        self._populate()

    @property
    def force(self) -> bool:
        return self._force_checkbox.isChecked()

    def current_manifest(self) -> ManifestDisplayInfo | None:
        model_id = self._model_combo.currentData()
        strategy_id = self._strategy_combo.currentData()
        country_id = self._country_combo.currentData()
        if not model_id or not strategy_id or not country_id:
            return None
        try:
            return ManifestDisplayInfo.from_axis(model_id, strategy_id, country_id)
        except Exception as e:
            print(f"[ExperimentSelector] compose_manifest failed: {e}", flush=True)
            return None

    def refresh(self) -> None:
        self._populate()

    def _populate(self) -> None:
        prev_model = self._model_combo.currentData()
        prev_strategy = self._strategy_combo.currentData()
        prev_country = self._country_combo.currentData()

        for combo, axis in (
            (self._model_combo, "models"),
            (self._strategy_combo, "strategies"),
            (self._country_combo, "countries"),
        ):
            combo.blockSignals(True)
            combo.clear()
            try:
                items = discover_axis_values(axis)
            except Exception:
                items = []
            for item in items:
                combo.addItem(item["label"], userData=item["id"])
            combo.blockSignals(False)

        for combo, prev in (
            (self._model_combo, prev_model),
            (self._strategy_combo, prev_strategy),
            (self._country_combo, prev_country),
        ):
            if prev:
                idx = combo.findData(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        self.manifest_changed.emit(self.current_manifest())

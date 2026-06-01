from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from population_synth.gui.manifest_model import ExperimentSelection, ManifestDisplayInfo
from population_synth.gui.widgets.checkable_axis_list import CheckableAxisList
from population_synth.identity.manifest_loader import discover_axis_values


class ExperimentSelector(QWidget):
    selection_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._model_list = CheckableAxisList("Models", self)
        self._strategy_list = CheckableAxisList("Strategies", self)
        self._country_list = CheckableAxisList("Countries", self)

        layout.addWidget(self._model_list)
        layout.addWidget(self._strategy_list)
        layout.addWidget(self._country_list)

        self._force_checkbox = QCheckBox("Force reprocessing")
        layout.addWidget(self._force_checkbox)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        self._model_list.selection_changed.connect(self._on_selection_changed)
        self._strategy_list.selection_changed.connect(self._on_selection_changed)
        self._country_list.selection_changed.connect(self._on_selection_changed)
        self._populate()

    @property
    def force(self) -> bool:
        return self._force_checkbox.isChecked()

    def current_selection(self) -> ExperimentSelection:
        return ExperimentSelection(
            model_ids=self._model_list.selected_ids(),
            strategy_ids=self._strategy_list.selected_ids(),
            country_ids=self._country_list.selected_ids(),
        )

    def first_manifest(self) -> ManifestDisplayInfo | None:
        combo = self.current_selection().first_combo()
        if combo is None:
            return None
        try:
            return ManifestDisplayInfo.from_axis(*combo)
        except Exception as e:
            print(f"[ExperimentSelector] compose_manifest failed: {e}", flush=True)
            return None

    def refresh(self) -> None:
        self._populate()

    def _populate(self) -> None:
        for list_widget, axis in (
            (self._model_list, "models"),
            (self._strategy_list, "strategies"),
            (self._country_list, "countries"),
        ):
            try:
                items = discover_axis_values(axis)
            except Exception:
                items = []
            list_widget.populate(items)

        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.current_selection())

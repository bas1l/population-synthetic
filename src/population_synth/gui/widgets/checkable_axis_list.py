from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class CheckableAxisList(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._checkboxes: list[QCheckBox] = []

        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(2)

        btn_row = QHBoxLayout()
        self._btn_all = QPushButton("All")
        self._btn_none = QPushButton("None")
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_none)
        btn_row.addStretch()
        group_layout.addLayout(btn_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(180)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._scroll_layout.setSpacing(1)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)
        group_layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(group)

        self._btn_all.clicked.connect(self._select_all)
        self._btn_none.clicked.connect(self._select_none)

    def populate(self, items: list[dict]) -> None:
        previously_checked = set(self.selected_ids())

        for cb in self._checkboxes:
            cb.setParent(None)
        self._checkboxes.clear()

        stretch = self._scroll_layout.takeAt(self._scroll_layout.count() - 1)

        self._items = list(items)
        for item in self._items:
            cb = QCheckBox(item["label"])
            cb.setChecked(item["id"] in previously_checked)
            cb.toggled.connect(self._on_toggle)
            self._scroll_layout.addWidget(cb)
            self._checkboxes.append(cb)

        self._scroll_layout.addStretch()

    def selected_ids(self) -> list[str]:
        return [
            self._items[i]["id"]
            for i, cb in enumerate(self._checkboxes)
            if cb.isChecked()
        ]

    def set_selected(self, ids: list[str]) -> None:
        id_set = set(ids)
        for i, cb in enumerate(self._checkboxes):
            cb.blockSignals(True)
            cb.setChecked(self._items[i]["id"] in id_set)
            cb.blockSignals(False)
        self.selection_changed.emit(self.selected_ids())

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self.selection_changed.emit(self.selected_ids())

    def _select_none(self) -> None:
        for cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.selection_changed.emit(self.selected_ids())

    def _on_toggle(self) -> None:
        self.selection_changed.emit(self.selected_ids())

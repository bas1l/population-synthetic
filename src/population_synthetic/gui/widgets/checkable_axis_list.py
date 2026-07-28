"""CheckableAxisList — scrollable checkbox list for one selection axis.

``CheckableAxisList`` is a ``QWidget`` holding a titled group box of
``QCheckBox`` items inside a ``QScrollArea``, with All/None buttons. It backs
one axis (models, strategies, or countries) and emits ``selection_changed``
with the checked item IDs.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
        # Height is the parent layout's call, not the content's: `Ignored`
        # drops the "as tall as my N checkboxes" size hint, so an axis gets
        # exactly the share its AxisSelector stretch weight asks for (a 20-item
        # axis would otherwise claim 20 rows before stretch ever applies). The
        # minimum keeps a short axis readable — roughly three rows — instead of
        # collapsing to the scrollbar.
        self._scroll.setMinimumHeight(60)
        self._scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
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

        self._scroll_layout.takeAt(self._scroll_layout.count() - 1)

        self._items = list(items)
        for item in self._items:
            cb = QCheckBox(item["label"])
            cb.setChecked(item["id"] in previously_checked)
            cb.toggled.connect(self._on_toggle)
            self._scroll_layout.addWidget(cb)
            self._checkboxes.append(cb)

        self._scroll_layout.addStretch()
        self._apply_content_ceiling()

    def _apply_content_ceiling(self) -> None:
        """Cap the list at the height its own items need.

        Without a ceiling a short axis handed a tall column keeps the surplus as
        blank space below its last checkbox. Capping at the content height sends
        that surplus back to the layout, which passes it to an axis that still
        has rows to reveal. Recomputed on every :meth:`populate` so the ceiling
        follows the discovered item count — never a fixed pixel budget.
        """
        content_height = self._scroll_content.sizeHint().height() + 2 * self._scroll.frameWidth()
        self._scroll.setMaximumHeight(max(content_height, self._scroll.minimumHeight()))
        # Qt does not propagate a layout's maximum up to the parent widget, so
        # the ceiling has to be restated on this widget or the group box keeps
        # the surplus as padding under the capped list. Chrome (group title +
        # All/None row + margins) is this widget's minimum minus the list's.
        chrome = max(self.minimumSizeHint().height() - self._scroll.minimumHeight(), 0)
        self.setMaximumHeight(chrome + self._scroll.maximumHeight())

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

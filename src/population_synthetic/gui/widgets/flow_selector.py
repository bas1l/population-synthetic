"""Flow selector widget — a full-width horizontal bar of tab-styled buttons.

Sits at the very top of the central widget (mirroring the run bar at the
bottom): one checkable button per :class:`FlowEntry`, laid out left to right
and grouped by category via an inline grey label, with a vertical separator
between groups and a horizontal rail beneath the whole row so the checked
button reads as the active tab. Emits ``flow_changed`` with the selected
entry.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from population_synthetic.gui.menu_config import FlowEntry

# Tab look: square bottom corners and no bottom border, so a checked button
# sits directly on the rail drawn under the row.
_TAB_BUTTON_STYLE = (
    "QPushButton { padding: 5px 14px; border: 1px solid #b8b8b8; border-bottom: none;"
    " border-top-left-radius: 4px; border-top-right-radius: 4px; }"
    "QPushButton:checked { background-color: #4a90d9; color: white; font-weight: bold; }"
)

_CATEGORY_LABEL_STYLE = (
    "QLabel { font-size: 10px; font-weight: bold; color: #888888; margin-left: 8px; margin-right: 2px; }"
)


class FlowSelector(QWidget):
    """Top-bar widget with exclusive tab-styled toggle buttons for each flow entry."""

    flow_changed = pyqtSignal(object)  # emits FlowEntry

    def __init__(self, entries: list[FlowEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[FlowEntry] = []
        self._buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button_row = QWidget()
        self._btn_layout = QHBoxLayout(button_row)
        self._btn_layout.setContentsMargins(6, 4, 6, 0)
        self._btn_layout.setSpacing(4)
        layout.addWidget(button_row)

        # The rail the tabs sit on (their own bottom border is suppressed).
        rail = QFrame()
        rail.setFrameShape(QFrame.HLine)
        rail.setFrameShadow(QFrame.Sunken)
        layout.addWidget(rail)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._btn_group.idClicked.connect(self._on_button_clicked)

        # A top bar claims only its natural height; the splitter below takes the rest.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._populate(entries)

    # ------------------------------------------------------------------

    def _populate(self, entries: list[FlowEntry]) -> None:
        """Build buttons left to right, grouped by category, from *entries*."""
        self._entries = list(entries)
        current_category: str | None = None
        for i, entry in enumerate(self._entries):
            if entry.category != current_category:
                if current_category is not None:  # separate this group from the previous one
                    sep = QFrame()
                    sep.setFrameShape(QFrame.VLine)
                    sep.setFrameShadow(QFrame.Sunken)
                    self._btn_layout.addWidget(sep)
                current_category = entry.category
                header = QLabel(current_category)
                header.setStyleSheet(_CATEGORY_LABEL_STYLE)
                self._btn_layout.addWidget(header)

            btn = QPushButton(entry.name)
            btn.setCheckable(True)
            btn.setToolTip(str(entry.config))
            btn.setStyleSheet(_TAB_BUTTON_STYLE)
            self._btn_group.addButton(btn, i)
            self._btn_layout.addWidget(btn)
            self._buttons.append(btn)

        self._btn_layout.addStretch()  # left-align the tabs

    def _on_button_clicked(self, btn_id: int) -> None:
        if 0 <= btn_id < len(self._entries):
            self.flow_changed.emit(self._entries[btn_id])

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def current_entry(self) -> FlowEntry | None:
        btn_id = self._btn_group.checkedId()
        if 0 <= btn_id < len(self._entries):
            return self._entries[btn_id]
        return None

    def select_entry(self, entry: FlowEntry) -> None:
        """Programmatically select a flow by its entry (matched on config path)."""
        for i, e in enumerate(self._entries):
            if e is entry or e.config == entry.config:
                self._buttons[i].setChecked(True)
                return

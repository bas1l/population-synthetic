"""TaskSelector — left-column action chooser with Run/Abort controls.

``TaskSelector`` is a ``QWidget`` presenting launcher actions as grouped
exclusive ``QRadioButton`` entries under section headers, plus Run and Abort
buttons. It emits ``action_changed``, ``run_clicked``, and ``abort_clicked``.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from population_synthetic.gui.launcher_config import ActionEntry, LauncherConfig


class TaskSelector(QWidget):
    """Left-column widget: grouped radio buttons for action selection, plus Run/Abort."""

    action_changed = pyqtSignal(object)
    run_clicked = pyqtSignal()
    abort_clicked = pyqtSignal()

    def __init__(self, config: LauncherConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._actions = config.actions
        default_id = config.default_action_id or config.actions[0].id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        # Build grouped radio buttons under section headers
        actions_by_group = config.actions_by_group()
        group_labels = {g.id: g.label for g in config.groups}

        button_index = 0
        for group in config.groups:
            group_actions = actions_by_group.get(group.id, [])
            if not group_actions:
                continue

            header = QLabel(group_labels[group.id])
            header.setStyleSheet("font-weight: bold;")
            layout.addWidget(header)

            for action in group_actions:
                radio = QRadioButton(action.label)
                self._button_group.addButton(radio, button_index)
                layout.addWidget(radio)
                if action.id == default_id:
                    radio.setChecked(True)
                button_index += 1

        layout.addStretch()

        # Run / Abort buttons
        button_row = QHBoxLayout()
        self._run_btn = QPushButton("Run")
        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setEnabled(False)
        button_row.addWidget(self._run_btn)
        button_row.addWidget(self._abort_btn)
        layout.addLayout(button_row)

        # Signals
        self._button_group.buttonClicked.connect(self._on_button_clicked)
        self._run_btn.clicked.connect(self.run_clicked)
        self._abort_btn.clicked.connect(self.abort_clicked)

    def _on_button_clicked(self, button: QRadioButton) -> None:
        idx = self._button_group.id(button)
        self.action_changed.emit(self._actions[idx])

    def current_action(self) -> ActionEntry | None:
        if not self._actions:
            return None
        checked = self._button_group.checkedButton()
        if checked is None:
            return None
        return self._actions[self._button_group.id(checked)]

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_btn.setEnabled(enabled)

    def set_abort_enabled(self, enabled: bool) -> None:
        self._abort_btn.setEnabled(enabled)

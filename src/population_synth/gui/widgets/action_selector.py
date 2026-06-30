"""ActionSelector — exclusive radio-button list of launcher actions.

``ActionSelector`` is a ``QWidget`` wrapping a ``QButtonGroup`` of
``QRadioButton`` entries (one per ``ActionEntry``) inside an "Action" group
box, emitting ``action_changed`` when the chosen action changes.
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QButtonGroup, QGroupBox, QRadioButton, QVBoxLayout, QWidget

from population_synth.gui.launcher_config import ActionEntry


class ActionSelector(QWidget):
    action_changed = pyqtSignal(object)

    def __init__(self, actions: list[ActionEntry], parent=None):
        super().__init__(parent)
        self._actions = actions

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        group_box = QGroupBox("Action")
        inner_layout = QVBoxLayout(group_box)
        outer_layout.addWidget(group_box)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        for i, entry in enumerate(actions):
            radio = QRadioButton(entry.label)
            self._button_group.addButton(radio, i)
            inner_layout.addWidget(radio)
            if i == 0:
                radio.setChecked(True)

        self._button_group.buttonClicked.connect(self._on_button_clicked)

    def _on_button_clicked(self, button) -> None:
        idx = self._button_group.id(button)
        self.action_changed.emit(self._actions[idx])

    def current_action(self) -> ActionEntry | None:
        if not self._actions:
            return None
        checked = self._button_group.checkedButton()
        if checked is None:
            return None
        return self._actions[self._button_group.id(checked)]

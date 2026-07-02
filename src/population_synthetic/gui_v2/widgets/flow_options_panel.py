"""Shape-dispatching options editor for a flow's ``options:`` block.

Slim port of the reference AnalysisRunnerGUI ``task_detail_panel.py``
(``social-touch-semi-controlled-analysis``): one editor row per option key,
with the widget shape decided by the current YAML value's type (see
:func:`option_widget_kind`). Edits write straight through
:meth:`FlowConfigModel.set_option` (which marks the model dirty) and emit
:attr:`FlowOptionsPanel.option_changed` so the window can refresh its title.

Per-option UI metadata never lives in the flow YAML — it lives in the
module-level declarative tables below, keyed by option name (CLI flag form):

- ``_OPTION_ENUMS`` — options rendered as a dropdown of (label, saved) pairs.
- ``_OPTION_VISIBILITY`` — controller option -> {dependent option: values for
  which the dependent row is visible}.
- ``_OPTION_GROUPS`` / ``_OPTION_GROUP_OF`` — optional collapsible grouping;
  when groups are declared, every option must be classified (fail-fast).
"""

from __future__ import annotations

import io
from typing import Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from population_synthetic.gui_v2.flow_config_model import FlowConfigModel
from population_synthetic.gui_v2.widgets.collapsible_section import CollapsibleSection

_COMPLEX_FG = QColor("#336699")

# Options rendered as a dropdown. Values are (display_label, saved_value)
# pairs; a saved_value of None writes YAML null (= "use the script default").
# Currently empty: the shipped flows' options are all bool/int/str/null.
_OPTION_ENUMS: dict[str, list[tuple[str, object]]] = {}

# Conditional visibility: controller option -> {dependent option: set of
# controller values for which the dependent row is shown}.
_OPTION_VISIBILITY: dict[str, dict[str, set]] = {}

# Ordered catalogue of option groups (render order + display label). When this
# is non-empty, every rendered option MUST be classified in _OPTION_GROUP_OF
# (enforced at render, fail-fast); when empty, options render flat.
_OPTION_GROUPS: list[tuple[str, str]] = []

# Which group each option key belongs to. One group per key.
_OPTION_GROUP_OF: dict[str, str] = {}


def option_widget_kind(key: str, value: Any) -> str:
    """Return the editor-widget kind for option *key* with current *value*.

    Pure shape-dispatch decision (no Qt), factored out so it can be unit
    tested headlessly. Kinds:

    - ``"enum"``    — key declared in :data:`_OPTION_ENUMS` -> combo box
    - ``"bool"``    — checkbox
    - ``"int"`` / ``"float"`` — line edit with cast-back to the numeric type
    - ``"none"``    — YAML null -> placeholder line edit ("(default)")
    - ``"str"``     — line edit
    - ``"complex"`` — list/dict -> raw-YAML dialog fallback

    Raises:
        TypeError: If *value* has a type the editor cannot represent.
    """
    if key in _OPTION_ENUMS:
        return "enum"
    if isinstance(value, bool):  # before int — bool is an int subclass
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if value is None:
        return "none"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (list, dict)):
        return "complex"
    raise TypeError(f"Option '{key}' has unsupported type {type(value).__name__} for the options editor")


def _option_header(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").title()


def _preview_text(val: Any) -> str:
    if isinstance(val, list):
        items = [str(v) for v in val[:3]]
        preview = "[" + ", ".join(items) + (", ..." if len(val) > 3 else "") + "]"
        return f"{preview} ({len(val)} items)"
    if isinstance(val, dict):
        keys = list(val.keys())[:3]
        preview = "{" + ", ".join(str(k) for k in keys) + (", ..." if len(val) > 3 else "") + "}"
        return f"{preview} ({len(val)} keys)"
    return str(val)


class _RawYamlDialog(QDialog):
    """Minimal raw-YAML editor fallback for list/dict option values."""

    def __init__(self, key: str, value: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit '{key}' (raw YAML)")
        self.resize(480, 320)
        self._yaml = YAML()  # round-trip so edited structures flow back losslessly
        self._yaml.preserve_quotes = True
        self._value: Any = value

        layout = QVBoxLayout(self)
        buf = io.StringIO()
        self._yaml.dump(value, buf)
        self._edit = QPlainTextEdit(buf.getvalue())
        self._edit.setFont(QFont("Consolas"))
        layout.addWidget(self._edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:  # noqa: D102 — Qt override
        try:
            self._value = self._yaml.load(self._edit.toPlainText())
        except YAMLError as exc:
            QMessageBox.critical(self, "Invalid YAML", f"Could not parse the edited YAML:\n\n{exc}")
            return  # keep the dialog open for correction
        super().accept()

    def value(self) -> Any:
        return self._value


class FlowOptionsPanel(QWidget):
    """Panel with a pinned header and one shape-dispatched editor row per option.

    Call :meth:`populate` with a :class:`FlowConfigModel` for ``kind: script``
    flows, or :meth:`show_placeholder` for flows without a flat ``options:``
    block (workflow flows until Phase 7). Emits :attr:`option_changed` with
    the option key whenever an edit is written through to the model.
    """

    option_changed = pyqtSignal(str)  # option key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: FlowConfigModel | None = None
        self._sections: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Pinned header — always visible above the scroll area
        self._header = QLabel()
        font = QFont()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        self._header.setFont(font)
        self._header.setStyleSheet("padding: 4px 8px; background: #e8e8e8; border-bottom: 1px solid #c0c0c0;")
        outer.addWidget(self._header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        scroll.setWidget(self._content)

        self.show_placeholder("Select a flow")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, model: FlowConfigModel) -> None:
        """Clear the panel and rebuild one editor row per key in ``options:``."""
        self._model = model
        self._header.setText(model.path.name)
        self._clear_sections()

        options = model.get_options()
        if not options:
            lbl = QLabel("No options")
            lbl.setStyleSheet("color: #888;")
            self._layout.insertWidget(0, lbl)
            return

        sections: list[tuple[str, QWidget]] = []
        for key, val in options.items():
            widget = self._build_option_section(key, val)
            self._sections[key] = widget
            sections.append((key, widget))

        if _OPTION_GROUPS:
            self._insert_grouped(options, sections)
        else:
            for i, (_key, widget) in enumerate(sections):
                self._layout.insertWidget(i, widget)

        self._apply_visibility(options)

    def show_placeholder(self, text: str) -> None:
        """Detach from any model and show a centered gray *text* instead of rows."""
        self._model = None
        self._header.setText("Options")
        self._clear_sections()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #888888;")
        self._layout.insertWidget(0, lbl)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _clear_sections(self) -> None:
        """Remove all option rows, keeping only the trailing stretch."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections.clear()

    def _insert_grouped(self, options: dict[str, Any], sections: list[tuple[str, QWidget]]) -> None:
        """Insert *sections* into collapsible group containers by option group.

        Every option must be classified in :data:`_OPTION_GROUP_OF` (fail-fast).
        Groups render in :data:`_OPTION_GROUPS` order; empty groups are
        omitted; option order within a group follows YAML order.
        """
        for key in options:
            if key not in _OPTION_GROUP_OF:
                raise ValueError(f"Option '{key}' has no group in _OPTION_GROUP_OF while _OPTION_GROUPS is declared")

        widget_of = dict(sections)
        insert_at = 0
        for group_key, group_label in _OPTION_GROUPS:
            members = [k for k in options if _OPTION_GROUP_OF[k] == group_key]
            if not members:
                continue
            container = CollapsibleSection(group_label, expanded=True)
            for key in members:
                container.add_widget(widget_of[key])
            self._layout.insertWidget(insert_at, container)
            insert_at += 1

    def _apply_visibility(self, options: dict[str, Any]) -> None:
        for controller, dependents in _OPTION_VISIBILITY.items():
            if controller not in options:
                continue
            current_val = options[controller]
            for dep_key, visible_when in dependents.items():
                if dep_key in self._sections:
                    self._sections[dep_key].setVisible(current_val in visible_when)

    # ------------------------------------------------------------------
    # Section builders (shape dispatch)
    # ------------------------------------------------------------------

    def _build_option_section(self, key: str, val: Any) -> QWidget:
        """Dispatch *key*/*val* to the matching per-option section builder."""
        kind = option_widget_kind(key, val)
        builder = {
            "enum": self._make_enum_section,
            "bool": self._make_bool_section,
            "int": self._make_number_section,
            "float": self._make_number_section,
            "none": self._make_nullable_section,
            "str": self._make_str_section,
            "complex": self._make_complex_section,
        }[kind]
        return builder(key, val)

    @staticmethod
    def _boxed(key: str) -> tuple[QGroupBox, QHBoxLayout]:
        """Return a titled group box with a single content row layout."""
        box = QGroupBox(_option_header(key))
        outer = QVBoxLayout(box)
        outer.setContentsMargins(6, 4, 6, 4)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(row)
        return box, row_layout

    def _make_enum_section(self, key: str, val: Any) -> QWidget:
        """QComboBox for options with a fixed set of allowed values."""
        box, row_layout = self._boxed(key)
        entries = _OPTION_ENUMS[key]
        combo = QComboBox()
        current_idx = 0
        for i, (label, saved) in enumerate(entries):
            combo.addItem(label)
            if val == saved:
                current_idx = i
        combo.setCurrentIndex(current_idx)
        combo.currentIndexChanged.connect(self._make_enum_handler(key, entries))
        row_layout.addWidget(combo)
        row_layout.addStretch()
        return box

    def _make_bool_section(self, key: str, val: bool) -> QWidget:
        box, row_layout = self._boxed(key)
        cb = QCheckBox("Enabled")
        cb.setChecked(val)
        cb.stateChanged.connect(self._make_bool_handler(key, cb))
        row_layout.addWidget(cb)
        row_layout.addStretch()
        return box

    def _make_number_section(self, key: str, val: int | float) -> QWidget:
        """Line edit that casts back to the value's numeric type; invalid input reverts."""
        box, row_layout = self._boxed(key)
        edit = QLineEdit(str(val))
        edit.setFixedWidth(120)
        edit.editingFinished.connect(self._make_number_handler(key, type(val), edit))
        row_layout.addWidget(edit)
        row_layout.addStretch()
        return box

    def _make_nullable_section(self, key: str, _val: None) -> QWidget:
        """Placeholder line edit for a YAML null: blank = script default."""
        box, row_layout = self._boxed(key)
        edit = QLineEdit("")
        edit.setPlaceholderText("(default)")
        edit.setToolTip("Blank writes YAML null — the script uses its own default.")
        edit.editingFinished.connect(self._make_nullable_handler(key, edit))
        row_layout.addWidget(edit)
        row_layout.addStretch()
        return box

    def _make_str_section(self, key: str, val: str) -> QWidget:
        box, row_layout = self._boxed(key)
        edit = QLineEdit(val)
        edit.editingFinished.connect(self._make_str_handler(key, edit))
        row_layout.addWidget(edit)
        row_layout.addStretch()
        return box

    def _make_complex_section(self, key: str, val: Any) -> QWidget:
        """Clickable preview label opening the raw-YAML dialog fallback."""
        box, row_layout = self._boxed(key)
        lbl = QLabel(_preview_text(val))
        lbl.setStyleSheet(f"color: {_COMPLEX_FG.name()};")
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip("Click to edit in the raw-YAML editor")
        lbl.mousePressEvent = self._make_complex_click_handler(key, lbl)
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        return box

    # ------------------------------------------------------------------
    # Handler factories
    # ------------------------------------------------------------------

    def _write_option(self, key: str, value: Any) -> None:
        """Write *value* through the model (marks it dirty) and notify listeners."""
        assert self._model is not None
        self._model.set_option(key, value)
        self.option_changed.emit(key)

    def _make_enum_handler(self, key: str, entries: list[tuple[str, object]]):
        def _handler(index: int) -> None:
            if self._model is None:
                return
            _, saved_val = entries[index]
            self._write_option(key, saved_val)
            if key in _OPTION_VISIBILITY:
                for dep_key, visible_when in _OPTION_VISIBILITY[key].items():
                    if dep_key in self._sections:
                        self._sections[dep_key].setVisible(saved_val in visible_when)

        return _handler

    def _make_bool_handler(self, key: str, cb: QCheckBox):
        def _handler(_state: int) -> None:
            if self._model is None:
                return
            self._write_option(key, cb.isChecked())

        return _handler

    def _make_number_handler(self, key: str, cast: type, edit: QLineEdit):
        def _handler() -> None:
            if self._model is None:
                return
            current = self._model.get_option(key)
            try:
                new_val = cast(edit.text())
            except (ValueError, TypeError):
                edit.setText(str(current))  # invalid input — revert, no write
                return
            if new_val == current:
                return  # editingFinished also fires on plain focus-out
            self._write_option(key, new_val)

        return _handler

    def _make_nullable_handler(self, key: str, edit: QLineEdit):
        def _handler() -> None:
            if self._model is None:
                return
            text = edit.text().strip()
            new_val: str | None = text if text else None
            if new_val == self._model.get_option(key):
                return
            self._write_option(key, new_val)

        return _handler

    def _make_str_handler(self, key: str, edit: QLineEdit):
        def _handler() -> None:
            if self._model is None:
                return
            new_val = edit.text()
            if new_val == self._model.get_option(key):
                return
            self._write_option(key, new_val)

        return _handler

    def _make_complex_click_handler(self, key: str, lbl: QLabel):
        def _handler(_event) -> None:
            if self._model is None:
                return
            dlg = _RawYamlDialog(key, self._model.get_option(key), self)
            if dlg.exec_() == QDialog.Accepted:
                new_value = dlg.value()
                self._write_option(key, new_value)
                lbl.setText(_preview_text(new_value))

        return _handler

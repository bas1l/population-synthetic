from typing import Any

from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from population_synth.gui.launcher_config import ActionParameter
from population_synth.gui.manifest_model import ManifestDisplayInfo


class ParameterPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._form_widget: QWidget | None = None
        self._widgets: dict[str, QWidget] = {}

    def populate(self, parameters: list[ActionParameter], manifest: ManifestDisplayInfo | None) -> None:
        if self._form_widget is not None:
            self._outer_layout.removeWidget(self._form_widget)
            self._form_widget.deleteLater()
            self._form_widget = None
        self._widgets = {}

        self._form_widget = QWidget()
        form = QFormLayout(self._form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.addWidget(self._form_widget)

        for param in parameters:
            default = self._resolve_default(param, manifest)
            widget = self._build_widget(param, default)
            self._widgets[param.key] = widget
            form.addRow(QLabel(param.label), widget if not isinstance(widget, QHBoxLayout) else self._wrap_layout(widget))

    def _resolve_default(self, param: ActionParameter, manifest: ManifestDisplayInfo | None) -> Any:
        if param.default_from_manifest and manifest is not None:
            return getattr(manifest.config, param.default_from_manifest, param.default)
        return param.default

    def _build_widget(self, param: ActionParameter, default: Any) -> QWidget:
        if param.type == "int":
            spin = QSpinBox()
            spin.setRange(1, 9999)
            if default is not None:
                try:
                    spin.setValue(int(default))
                except (ValueError, TypeError):
                    pass
            return spin

        if param.type == "bool":
            box = QCheckBox()
            if default:
                box.setChecked(bool(default))
            return box

        if param.type == "file":
            container = QWidget()
            h = QHBoxLayout(container)
            h.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit()
            if default is not None:
                line.setText(str(default))
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda _checked, le=line: self._browse_file(le))
            h.addWidget(line)
            h.addWidget(browse_btn)
            container.setProperty("_line_edit", line)
            return container

        line = QLineEdit()
        if default is not None:
            line.setText(str(default))
        return line

    def _wrap_layout(self, layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _browse_file(self, line_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select file")
        if path:
            line_edit.setText(path)

    def get_overrides(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QSpinBox):
                result[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                text = widget.text().strip()
                if text:
                    result[key] = text
            elif widget.property("_line_edit") is not None:
                line = widget.property("_line_edit")
                text = line.text().strip()
                if text:
                    result[key] = text
        return result

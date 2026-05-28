from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from population_synth.gui.manifest_model import ManifestDisplayInfo

_DASH = "—"


class ManifestOverview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        group_box = QGroupBox("Overview")
        form = QFormLayout(group_box)
        outer_layout.addWidget(group_box)

        self._name_label = QLabel(_DASH)
        self._provider_label = QLabel(_DASH)
        self._model_label = QLabel(_DASH)
        self._mode_label = QLabel(_DASH)
        self._strategy_label = QLabel(_DASH)
        self._config_path_label = QLabel(_DASH)
        self._config_path_label.setWordWrap(True)
        self._parallel_workers_label = QLabel(_DASH)
        self._output_dir_label = QLabel(_DASH)
        self._output_dir_label.setWordWrap(True)
        self._personas_label = QLabel(_DASH)

        form.addRow("Name:", self._name_label)
        form.addRow("Provider:", self._provider_label)
        form.addRow("Model:", self._model_label)
        form.addRow("Mode:", self._mode_label)
        form.addRow("Strategy:", self._strategy_label)
        form.addRow("Config Path:", self._config_path_label)
        form.addRow("Parallel Workers:", self._parallel_workers_label)
        form.addRow("Output Dir:", self._output_dir_label)
        form.addRow("Personas:", self._personas_label)

    def populate(self, info: ManifestDisplayInfo | None) -> None:
        if info is None:
            for label in (
                self._name_label,
                self._provider_label,
                self._model_label,
                self._mode_label,
                self._strategy_label,
                self._config_path_label,
                self._parallel_workers_label,
                self._output_dir_label,
                self._personas_label,
            ):
                label.setText(_DASH)
            return

        cfg = info.config
        self._name_label.setText(info.display_name)
        self._provider_label.setText(cfg.provider or _DASH)
        self._model_label.setText(cfg.model or _DASH)
        self._mode_label.setText(cfg.mode or _DASH)
        self._strategy_label.setText(info.strategy_name or _DASH)
        self._config_path_label.setText(str(cfg.config_path) if cfg.config_path else _DASH)
        self._parallel_workers_label.setText(str(cfg.parallel_workers) if cfg.parallel_workers is not None else _DASH)
        self._output_dir_label.setText(str(cfg.parallel_output_dir) if cfg.parallel_output_dir else _DASH)
        count = info.existing_persona_count
        self._personas_label.setText(str(count) if count is not None else _DASH)

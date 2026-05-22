from __future__ import annotations

import subprocess
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from population_synth.gui.launcher_config import ActionEntry
from population_synth.gui.manifest_model import ManifestDisplayInfo
from population_synth.gui.widgets.action_selector import ActionSelector
from population_synth.gui.widgets.console_widget import ConsoleWidget, ProcessOutputReader
from population_synth.gui.widgets.dag_graph_widget import DagGraphWidget
from population_synth.gui.widgets.manifest_overview import ManifestOverview
from population_synth.gui.widgets.manifest_selector import ExperimentSelector
from population_synth.gui.widgets.parameter_panel import ParameterPanel


class LauncherWindow(QMainWindow):
    def __init__(self, actions: list[ActionEntry], parent=None):
        super().__init__(parent)
        self._actions = actions
        self._process: subprocess.Popen | None = None
        self._reader: ProcessOutputReader | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_process)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)

        v_splitter = QSplitter(Qt.Vertical)
        outer.addWidget(v_splitter)

        h_splitter = QSplitter(Qt.Horizontal)
        v_splitter.addWidget(h_splitter)

        left_widget = QWidget()
        left_widget.setFixedWidth(280)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._experiment_selector = ExperimentSelector()
        left_layout.addWidget(self._experiment_selector)

        self._action_selector = ActionSelector(actions)
        left_layout.addWidget(self._action_selector)

        self._params = ParameterPanel()
        left_layout.addWidget(self._params)

        left_layout.addStretch()

        btn_layout = QHBoxLayout()
        self._run_btn = QPushButton("Run")
        self._run_btn.setEnabled(bool(actions))
        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setEnabled(False)
        btn_layout.addWidget(self._run_btn)
        btn_layout.addWidget(self._abort_btn)
        left_layout.addLayout(btn_layout)

        h_splitter.addWidget(left_widget)

        right_tabs = QTabWidget()
        self._overview = ManifestOverview()
        right_tabs.addTab(self._overview, "Overview")
        self._dag_widget = DagGraphWidget()
        right_tabs.addTab(self._dag_widget, "DAG View")
        h_splitter.addWidget(right_tabs)
        h_splitter.setStretchFactor(1, 1)

        self._console = ConsoleWidget()
        v_splitter.addWidget(self._console)
        v_splitter.setSizes([550, 200])

        self._experiment_selector.manifest_changed.connect(self._on_manifest_changed)
        self._action_selector.action_changed.connect(self._on_action_changed)
        self._run_btn.clicked.connect(self._run)
        self._abort_btn.clicked.connect(self._abort)

        initial_manifest = self._experiment_selector.current_manifest()
        self._on_manifest_changed(initial_manifest)
        initial_action = self._action_selector.current_action()
        if initial_action is not None:
            self._on_action_changed(initial_action)
        self._dag_widget.populate(initial_manifest.strategy_path if initial_manifest else None)
        self._dag_widget.node_clicked.connect(
            lambda name: self.statusBar().showMessage(f"Category: {name}")
        )

    def _on_manifest_changed(self, info: ManifestDisplayInfo | None) -> None:
        self._overview.populate(info)
        self._dag_widget.populate(info.strategy_path if info else None)
        action = self._action_selector.current_action()
        if action is not None:
            self._params.populate(action.parameters, info)

    def _on_action_changed(self, action: ActionEntry) -> None:
        manifest = self._experiment_selector.current_manifest()
        self._params.populate(action.parameters, manifest)
        self._experiment_selector.setEnabled(action.requires_manifest)

    def _build_command(
        self,
        action: ActionEntry,
        manifest: ManifestDisplayInfo | None,
        overrides: dict,
    ) -> list[str]:
        cmd = [sys.executable, str(action.script)]
        if action.requires_manifest and manifest:
            if manifest.model_id is not None:
                cmd += ["--model-id", manifest.model_id]
                cmd += ["--strategy-id", manifest.strategy_id]
                cmd += ["--country-id", manifest.country_id]
                if self._experiment_selector.force:
                    cmd.append("--force")
            elif manifest.path is not None:
                cmd += ["--manifest", str(manifest.path)]
        for key, value in overrides.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            elif value is not None and value != "":
                cmd += [f"--{key}", str(value)]
        return cmd

    def _run(self) -> None:
        action = self._action_selector.current_action()
        if action is None:
            return
        manifest = self._experiment_selector.current_manifest()
        if action.requires_manifest and manifest is None:
            QMessageBox.warning(self, "No Manifest", "Please select a manifest before running.")
            return
        overrides = self._params.get_overrides()
        cmd = self._build_command(action, manifest, overrides)

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )

        self._reader = ProcessOutputReader(self._process)
        self._reader.line_received.connect(self._console.append_line)
        self._reader.cr_line_received.connect(self._console.append_cr_line)
        self._reader.start()

        self._run_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self.statusBar().showMessage(f"Running: {action.script.name}...")
        self._poll_timer.start(500)

    def _check_process(self) -> None:
        if self._process is None:
            self._poll_timer.stop()
            return
        code = self._process.poll()
        if code is not None:
            self._poll_timer.stop()
            if code == 0:
                self.statusBar().showMessage("Finished (exit 0)")
            else:
                self.statusBar().showMessage(f"Failed (exit {code})")
            self._run_btn.setEnabled(True)
            self._abort_btn.setEnabled(False)
            self._process = None

    def _abort(self) -> None:
        if self._process is not None:
            self._process.terminate()
        self.statusBar().showMessage("Aborted")

    def closeEvent(self, event) -> None:
        if self._process is not None:
            self._process.terminate()
        super().closeEvent(event)

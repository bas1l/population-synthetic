from __future__ import annotations

import subprocess
import sys

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from population_synth.gui.launcher_config import ActionEntry, LauncherConfig
from population_synth.gui.manifest_model import ExperimentSelection, ManifestDisplayInfo
from population_synth.gui.widgets.configuration_panel import ConfigurationPanel
from population_synth.gui.widgets.console_widget import ConsoleWidget, ProcessOutputReader
from population_synth.gui.widgets.dag_graph_widget import DagGraphWidget
from population_synth.gui.widgets.manifest_overview import ManifestOverview
from population_synth.gui.widgets.task_selector import TaskSelector


class CombinationRunner(QThread):
    combo_started = pyqtSignal(int, int, str, str, str)
    line_received = pyqtSignal(str)
    cr_line_received = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(
        self,
        combos: list[tuple[str, str, str]],
        action: ActionEntry,
        overrides: dict,
        force: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._combos = combos
        self._action = action
        self._overrides = overrides
        self._force = force
        self._abort_flag = False

    def abort(self) -> None:
        self._abort_flag = True

    def run(self) -> None:
        total = len(self._combos)
        for i, (model_id, strategy_id, country_id) in enumerate(self._combos):
            self.combo_started.emit(i + 1, total, model_id, strategy_id, country_id)
            banner = (
                f"{'=' * 60}\n"
                f"  RUN {i + 1}/{total}: {model_id} × {strategy_id} × {country_id}\n"
                f"{'=' * 60}"
            )
            self.line_received.emit(banner)

            cmd = [
                sys.executable,
                str(self._action.script),
                "--model-id", model_id,
                "--strategy-id", strategy_id,
                "--country-id", country_id,
            ]
            if self._force:
                cmd.append("--force")
            for key, value in self._overrides.items():
                if isinstance(value, bool):
                    if value:
                        cmd.append(f"--{key}")
                elif value is not None and value != "":
                    cmd += [f"--{key}", str(value)]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.decode(errors="replace").rstrip("\n")
                self.line_received.emit(line)
            process.wait()

            if self._abort_flag:
                break

        self.finished_all.emit()


class LauncherWindow(QMainWindow):
    def __init__(self, config: LauncherConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._process: subprocess.Popen | None = None
        self._reader: ProcessOutputReader | None = None
        self._runner: CombinationRunner | None = None
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

        self._task_selector = TaskSelector(config)
        self._task_selector.setFixedWidth(200)
        h_splitter.addWidget(self._task_selector)

        self._config_panel = ConfigurationPanel()
        h_splitter.addWidget(self._config_panel)

        right_tabs = QTabWidget()
        self._overview = ManifestOverview()
        right_tabs.addTab(self._overview, "Overview")
        self._dag_widget = DagGraphWidget()
        right_tabs.addTab(self._dag_widget, "DAG View")
        h_splitter.addWidget(right_tabs)

        h_splitter.setStretchFactor(0, 0)
        h_splitter.setStretchFactor(1, 1)
        h_splitter.setStretchFactor(2, 3)

        self._console = ConsoleWidget()
        v_splitter.addWidget(self._console)
        v_splitter.setSizes([550, 200])

        self._task_selector.action_changed.connect(self._on_action_changed)
        self._task_selector.run_clicked.connect(self._run)
        self._task_selector.abort_clicked.connect(self._abort)
        self._config_panel.selection_changed.connect(self._on_selection_changed)

        initial_selection = self._config_panel.current_selection()
        self._on_selection_changed(initial_selection)
        initial_action = self._task_selector.current_action()
        if initial_action is not None:
            self._on_action_changed(initial_action)
        self._dag_widget.node_clicked.connect(
            lambda name: self.statusBar().showMessage(f"Category: {name}")
        )

    def _on_selection_changed(self, selection: ExperimentSelection) -> None:
        self._overview.populate_selection(selection)
        strategy_path = None
        combo = selection.first_combo()
        if combo is not None:
            try:
                info = ManifestDisplayInfo.from_axis(*combo)
                strategy_path = info.strategy_path
            except Exception:
                pass
        self._dag_widget.populate(strategy_path)

    def _on_action_changed(self, action: ActionEntry) -> None:
        self._config_panel.update_for_action(action)

    def _build_command(
        self,
        action: ActionEntry,
        overrides: dict,
    ) -> list[str]:
        cmd = [sys.executable, str(action.script)]
        for key, value in overrides.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            elif value is not None and value != "":
                cmd += [f"--{key}", str(value)]
        return cmd

    def _run(self) -> None:
        action = self._task_selector.current_action()
        if action is None:
            return
        overrides = self._config_panel.get_overrides()

        if not action.requires_manifest:
            cmd = self._build_command(action, overrides)
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
            self._task_selector.set_run_enabled(False)
            self._task_selector.set_abort_enabled(True)
            self.statusBar().showMessage(f"Running: {action.script.name}...")
            self._poll_timer.start(500)
            return

        selection = self._config_panel.current_selection()
        combos = selection.combinations()
        if not combos:
            QMessageBox.warning(
                self,
                "No Selection",
                "No selection — please check at least one item in each axis.",
            )
            return

        if len(combos) > 20:
            answer = QMessageBox.question(
                self,
                "Large Batch",
                f"This will run {len(combos)} combinations. Proceed?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        runner = CombinationRunner(combos, action, overrides, self._config_panel.force)
        runner.combo_started.connect(self._on_combo_started)
        runner.line_received.connect(self._console.append_line)
        runner.cr_line_received.connect(self._console.append_cr_line)
        runner.finished_all.connect(self._on_runner_finished)
        self._runner = runner
        self._runner.start()
        self._task_selector.set_run_enabled(False)
        self._task_selector.set_abort_enabled(True)

    def _on_combo_started(
        self, idx: int, total: int, model_id: str, strategy_id: str, country_id: str
    ) -> None:
        self.statusBar().showMessage(
            f"Running {idx}/{total}: {model_id} × {strategy_id} × {country_id}"
        )

    def _on_runner_finished(self) -> None:
        self._task_selector.set_run_enabled(True)
        self._task_selector.set_abort_enabled(False)
        self.statusBar().showMessage("Finished all combinations")
        self._runner = None

    def _check_process(self) -> None:
        if self._runner is not None:
            return
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
            self._task_selector.set_run_enabled(True)
            self._task_selector.set_abort_enabled(False)
            self._process = None

    def _abort(self) -> None:
        if self._runner is not None:
            self._runner.abort()
        elif self._process is not None:
            self._process.terminate()
        self.statusBar().showMessage("Aborted")

    def closeEvent(self, event) -> None:
        if self._runner is not None:
            self._runner.abort()
        if self._process is not None:
            self._process.terminate()
        super().closeEvent(event)

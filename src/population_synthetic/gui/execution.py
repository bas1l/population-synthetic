"""Shared execution substrate: process-tree kill, action descriptor, combo runner.

Extracted from the removed v1 launcher (``gui/launcher_config.py`` +
``gui/main_window.py``) so this package is self-contained.
``_kill_process_tree`` force-kills a subprocess and all of its descendants.
``ActionEntry`` is the minimal descriptor ``CombinationRunner`` needs to build
and label each per-combo subprocess invocation. ``CombinationRunner`` (a
``QThread``) runs the cartesian product of selected axes sequentially, one
subprocess per combo, with process-tree kill on abort.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal


@dataclass
class ActionEntry:
    id: str
    label: str
    script: Path
    requires_manifest: bool
    axis_mode: str  # normalised: "none" | "per_combo" | "batch"
    group: str = ""
    parameters: list[Any] = field(default_factory=list)
    min_combos: int | None = None
    max_combos: int | None = None


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Force-kill a subprocess and all of its descendants.

    ``Popen.terminate()`` only kills the immediate process; LLM generation
    spawns grandchildren (e.g. the persistent ``claude`` CLI), which would be
    orphaned. ``taskkill /F /T`` on Windows (and ``killpg`` on POSIX) takes
    down the whole tree.
    """
    if process.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


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
        self._process: subprocess.Popen | None = None

    def abort(self) -> None:
        self._abort_flag = True
        if self._process is not None:
            _kill_process_tree(self._process)

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

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            assert self._process.stdout is not None
            for raw in self._process.stdout:
                line = raw.decode(errors="replace").rstrip("\n")
                self.line_received.emit(line)
            self._process.wait()
            self._process = None

            if self._abort_flag:
                break

        self.finished_all.emit()

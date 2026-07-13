"""PersonaCountWorker — off-UI-thread persona counter for the population summary.

Extracted from the deprecated v1 launcher's ``manifest_overview.py`` (the
``ManifestOverview`` widget it was mixed with stays in v1 and is not moved).
``PersonaCountWorker`` (a ``QThread``) globs each combination's output dir
off the UI thread to count existing personas without blocking the GUI.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal


class PersonaCountWorker(QThread):
    """Globs each combination's output dir off the UI thread to count existing personas."""

    count_ready = pyqtSignal(int, int, int)  # generation, row, count

    def __init__(self, generation: int, rows: list[tuple[int, Path | None]], parent=None):
        super().__init__(parent)
        self._generation = generation
        self._rows = rows

    def run(self) -> None:
        for row, output_dir in self._rows:
            try:
                if output_dir is not None and output_dir.exists():
                    count = len(list(output_dir.glob("persona_*/identity.json")))
                else:
                    count = 0
            except Exception:
                count = 0
            self.count_ready.emit(self._generation, row, count)

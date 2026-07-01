"""ManifestOverview — table previewing selected axis combinations.

``ManifestOverview`` is a ``QWidget`` with a ``QTableWidget`` that lists each
model/strategy/country combination composed from the current selection, with
provider, mode, worker, and persona-count columns. ``PersonaCountWorker`` (a
``QThread``) globs each run's output dir off the UI thread to fill counts.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from population_synthetic.generators.synthetic.manifest_loader import compose_manifest, discover_axis_values
from population_synthetic.gui.manifest_model import ExperimentSelection

_DASH = "—"
_PENDING = "…"
_COLUMNS = ["Model", "Strategy", "Country", "Provider", "Mode", "Workers", "Personas"]
_PERSONAS_COL = _COLUMNS.index("Personas")
_NO_SELECTION = "No selection — check at least one item in each axis."


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


class ManifestOverview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        group_box = QGroupBox("Overview")
        group_layout = QVBoxLayout(group_box)
        outer_layout.addWidget(group_box)

        self._summary_label = QLabel(_NO_SELECTION)
        self._summary_label.setWordWrap(True)
        group_layout.addWidget(self._summary_label)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        group_layout.addWidget(self._table)

        self._generation = 0
        self._count_worker: PersonaCountWorker | None = None

    def populate_selection(self, selection: ExperimentSelection) -> None:
        combos = selection.combinations()
        self._generation += 1
        country_labels = {c["id"]: c["label"] for c in discover_axis_values("countries")}

        if not combos:
            self._table.setRowCount(0)
            self._summary_label.setText(_NO_SELECTION)
            return

        self._summary_label.setText(self._summary_text(selection, len(combos)))

        self._table.setRowCount(len(combos))
        worker_rows: list[tuple[int, Path | None]] = []
        for row, (model_id, strategy_id, country_id) in enumerate(combos):
            try:
                cfg = compose_manifest(model_id, strategy_id, country_id)
            except Exception as e:
                self._set_row(row, [model_id, strategy_id, country_labels.get(country_id, country_id), f"error: {e}", "", "", _DASH])
                continue

            workers = str(cfg.parallel_workers) if cfg.parallel_workers is not None else _DASH
            self._set_row(
                row,
                [model_id, strategy_id, country_labels.get(country_id, country_id), cfg.provider or _DASH, cfg.mode or _DASH, workers, _PENDING],
            )
            tooltip = cfg.name
            if cfg.parallel_output_dir is not None:
                tooltip = f"{cfg.name}\n{cfg.parallel_output_dir}"
            for col in range(len(_COLUMNS)):
                item = self._table.item(row, col)
                if item is not None:
                    item.setToolTip(tooltip)
            worker_rows.append((row, cfg.parallel_output_dir))

        if worker_rows:
            worker = PersonaCountWorker(self._generation, worker_rows, self)
            worker.count_ready.connect(self._on_count_ready)
            self._count_worker = worker
            worker.start()

    def _set_row(self, row: int, values: list[str]) -> None:
        for col, value in enumerate(values):
            self._table.setItem(row, col, QTableWidgetItem(value))

    def _on_count_ready(self, generation: int, row: int, count: int) -> None:
        if generation != self._generation or row >= self._table.rowCount():
            return
        item = self._table.item(row, _PERSONAS_COL)
        if item is not None:
            item.setText(str(count))

    @staticmethod
    def _summary_text(selection: ExperimentSelection, n: int) -> str:
        if n == 1:
            return "1 run"
        return (
            f"{n} runs ({len(selection.model_ids)} models"
            f" × {len(selection.strategy_ids)} strategies"
            f" × {len(selection.country_ids)} countries)"
        )

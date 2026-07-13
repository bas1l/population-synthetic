"""PopulationSummaryPanel — live per-combo persona-generation summary.

A ``QWidget`` with a ``QTableWidget`` listing each checked
model/strategy/country combo with provider, workers, a ``generated / total``
count and a progress bar. Counts come from re-globbing each combo's output dir
off the UI thread via :class:`PersonaCountWorker`, so the panel ticks up live
while a generation run is in progress.

Unlike the legacy ``ManifestOverview`` (a static disk snapshot refreshed only
on selection change), :meth:`refresh_counts` is driven by a repeating timer in
the main window during a run, giving a live "individuals generated so far" view.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from population_synthetic.generators.synthetic.manifest_loader import compose_manifest, discover_axis_values
from population_synthetic.gui.widgets.persona_count_worker import PersonaCountWorker

_DASH = "—"
_PENDING = "…"
_COLUMNS = ["Model", "Strategy", "Country", "Provider", "Workers", "Generated", "Progress"]
_PROGRESS_COL = _COLUMNS.index("Progress")
_GENERATED_COL = _COLUMNS.index("Generated")
_NO_SELECTION = "No selection — check at least one item in each axis to preview the population summary."
_ACTIVE_BG = QColor(45, 90, 45)  # subtle green highlight for the currently-running combo


class PopulationSummaryPanel(QWidget):
    """Live table of per-combo persona-generation progress.

    :meth:`populate_combos` (re)builds the rows from a list of
    ``(model_id, strategy_id, country_id)`` tuples; :meth:`refresh_counts`
    re-globs the output dirs and updates the ``generated / total`` cells and
    progress bars; :meth:`set_active_combo` highlights the running row.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._summary_label = QLabel(_NO_SELECTION)
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet("font-weight: bold; padding: 2px 4px;")
        layout.addWidget(self._summary_label)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_PROGRESS_COL, QHeaderView.Stretch)
        layout.addWidget(self._table)

        self._generation = 0
        self._count_worker: PersonaCountWorker | None = None
        # Per-row state, parallel to the table rows.
        self._combos: list[tuple[str, str, str]] = []
        self._totals: list[int | None] = []
        self._output_dirs: list[Path | None] = []
        self._counts: list[int] = []
        self._active_row: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate_combos(
        self,
        combos: list[tuple[str, str, str]],
        total_override: int | None = None,
    ) -> None:
        """(Re)build the table from *combos* and kick a background count refresh.

        *total_override* is the flow YAML's ``n`` option (what the GUI actually
        sends to the script as ``--n``); when given it is the per-combo total
        for every row. When ``None`` each row falls back to
        ``compose_manifest(...).parallel_n`` (the experiment-defaults value).
        """
        self._generation += 1
        self._combos = list(combos)
        self._totals = []
        self._output_dirs = []
        self._counts = []
        self._active_row = None

        country_labels = {c["id"]: c["label"] for c in discover_axis_values("countries")}

        if not combos:
            self._table.setRowCount(0)
            self._summary_label.setText(_NO_SELECTION)
            return

        self._table.setRowCount(len(combos))
        for row, (model_id, strategy_id, country_id) in enumerate(combos):
            country_label = country_labels.get(country_id, country_id)
            axis_cols = [model_id, strategy_id, country_label]
            try:
                cfg = compose_manifest(model_id, strategy_id, country_id)
            except Exception as e:  # noqa: BLE001 - surfaced in the row, not swallowed
                self._set_row(row, [*axis_cols, f"error: {e}", "", _DASH])
                self._totals.append(None)
                self._output_dirs.append(None)
                self._counts.append(0)
                continue

            workers = str(cfg.parallel_workers) if cfg.parallel_workers is not None else _DASH
            total = total_override if total_override is not None else cfg.parallel_n
            generated = f"{_PENDING} / {total}" if total is not None else _PENDING
            self._set_row(row, [*axis_cols, cfg.provider or _DASH, workers, generated])

            self._totals.append(total)
            self._output_dirs.append(cfg.parallel_output_dir)
            self._counts.append(0)
            self._install_progress_bar(row, total)

            tooltip = cfg.name
            if cfg.parallel_output_dir is not None:
                tooltip = f"{cfg.name}\n{cfg.parallel_output_dir}"
            for col in range(_GENERATED_COL + 1):
                item = self._table.item(row, col)
                if item is not None:
                    item.setToolTip(tooltip)

        self._refresh_summary_label()
        self._spawn_count_worker()

    def refresh_counts(self) -> None:
        """Re-glob every combo's output dir off-thread (called by the live timer)."""
        if self._combos:
            self._spawn_count_worker()

    def set_active_combo(self, model_id: str, strategy_id: str, country_id: str) -> None:
        """Highlight the row for the currently-running combo (sequential runner)."""
        combo = (model_id, strategy_id, country_id)
        try:
            row = self._combos.index(combo)
        except ValueError:
            return
        self._set_active_row(row)

    def clear_active_combo(self) -> None:
        """Drop the running-row highlight (e.g. when a run finishes)."""
        self._set_active_row(None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _spawn_count_worker(self) -> None:
        rows = [(row, output_dir) for row, output_dir in enumerate(self._output_dirs)]
        if not rows:
            return
        self._generation += 1
        worker = PersonaCountWorker(self._generation, rows, self)
        worker.count_ready.connect(self._on_count_ready)
        self._count_worker = worker
        worker.start()

    def _on_count_ready(self, generation: int, row: int, count: int) -> None:
        if generation != self._generation or row >= self._table.rowCount():
            return
        self._counts[row] = count
        total = self._totals[row]
        item = self._table.item(row, _GENERATED_COL)
        if item is not None:
            item.setText(f"{count} / {total}" if total is not None else str(count))
        bar = self._table.cellWidget(row, _PROGRESS_COL)
        if isinstance(bar, QProgressBar):
            bar.setValue(count)
        self._refresh_summary_label()

    def _install_progress_bar(self, row: int, total: int | None) -> None:
        if total is None or total <= 0:
            return
        bar = QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(total)
        bar.setValue(0)
        bar.setFormat("%v / %m (%p%)")
        bar.setTextVisible(True)
        self._table.setCellWidget(row, _PROGRESS_COL, bar)

    def _set_row(self, row: int, values: list[str]) -> None:
        for col, value in enumerate(values):
            self._table.setItem(row, col, QTableWidgetItem(value))

    def _set_active_row(self, row: int | None) -> None:
        if row == self._active_row:
            return
        default = self._table.palette().base().color()
        if self._active_row is not None:
            self._paint_row(self._active_row, default)
        if row is not None:
            self._paint_row(row, _ACTIVE_BG)
        self._active_row = row

    def _paint_row(self, row: int, color: QColor) -> None:
        if row >= self._table.rowCount():
            return
        for col in range(len(_COLUMNS)):
            item = self._table.item(row, col)
            if item is not None:
                item.setBackground(color)

    def _refresh_summary_label(self) -> None:
        n = len(self._combos)
        if n == 0:
            self._summary_label.setText(_NO_SELECTION)
            return
        generated = sum(self._counts)
        totals = [t for t in self._totals if t is not None]
        total_str = f"{sum(totals):,}" if len(totals) == n else "?"
        combo_word = "combo" if n == 1 else "combos"
        self._summary_label.setText(
            f"{generated:,} / {total_str} individuals generated ({n} {combo_word})"
        )

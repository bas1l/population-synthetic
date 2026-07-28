"""Main window for the gui Flow Runner.

Port of the reference AnalysisRunnerGUI ``runner_window.py`` (minus Prefect).
Layout, top to bottom: the :class:`FlowSelector` as a full-width tab bar, a
two-column horizontal splitter, and the Run/Abort bar (the selector and the
run bar bracket the splitter). The splitter's left side stacks the graph
column over the reused :class:`ConsoleWidget`; its right side is the
full-height **Options** column — a ``QTabWidget`` whose *Global* tab holds
the :class:`AxisSelector` and whose *Task* tab holds the options of whatever
is loaded. The graph column is a ``QStackedWidget`` swapping by flow kind:
script flows show the strategy DAG, workflow flows the task DAG.

Selecting a flow loads its editable YAML into a :class:`FlowConfigModel`
(``kind: script``) or a :class:`WorkflowConfigModel` (``kind: workflow``); the
Task tab edits it via the shape-dispatching :class:`FlowOptionsPanel` (one
panel per flow kind, stacked and raised by kind — a script flow's flat
``options:`` block, or the clicked node's options for a workflow); the Global
tab binds the ``selection:`` block (and ``force:`` for generate flows) to
three checkable axis lists; the script page renders the strategy DAG of the
first checked axis combo; the workflow page renders the task DAG with
per-node Enabled/Force checkboxes and a live run-state overlay. A
Save/Save-As toolbar writes the YAML back losslessly, with a dirty ``*`` in
the title and confirm-discard on flow switch and close.

Execution: Run saves the flow YAML, then — for ``kind: script`` — dispatches
the checked axis combos through the reused :class:`CombinationRunner`
(from :mod:`population_synthetic.gui.execution`, one subprocess per combo,
sequential); for ``kind: workflow`` it snapshots + validates a
:class:`WorkflowState` and runs the enabled chain through
:class:`WorkflowRunner`. Abort kills the whole process tree via the runner's
``abort`` → ``_kill_process_tree``.

Execution contract: on Run, the GUI TRANSLATES the flow's YAML into CLI
invocations of the existing scripts — the spawned scripts do NOT read the
flow YAML. Save is persistence only.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.generators.synthetic.manifest_loader import compose_manifest
from population_synthetic.gui.execution import ActionEntry, CombinationRunner
from population_synthetic.gui.flow_config_model import FlowConfigModel
from population_synthetic.gui.menu_config import FlowEntry
from population_synthetic.gui.widgets.axis_selector import AxisSelector
from population_synthetic.gui.widgets.console_widget import ConsoleWidget
from population_synthetic.gui.widgets.dag_graph_widget import DagGraphWidget
from population_synthetic.gui.widgets.flow_options_panel import FlowOptionsPanel
from population_synthetic.gui.widgets.flow_selector import FlowSelector
from population_synthetic.gui.widgets.population_summary import PopulationSummaryPanel
from population_synthetic.gui.widgets.workflow_graph_view import WorkflowGraphView
from population_synthetic.gui.workflow_config_model import WorkflowConfigModel
from population_synthetic.gui.workflow_runner import WorkflowRunner
from population_synthetic.gui.workflow_state import TaskStatus, WorkflowState

_BASE_TITLE = "Population Synth Flow Runner"


class _StrategyDagView(DagGraphWidget):
    """Reused :class:`DagGraphWidget` taught to accept YAML strategy files.

    The old-GUI widget (reused by import, never edited) parses the strategy
    file with ``json.loads``, but ``compose_manifest().strategy_path`` now
    points at the axis strategy *YAML* itself. Convert the YAML to a JSON
    twin in a per-user temp cache and delegate; the widget's ``.layout.json``
    sidecar then lives next to the cache file instead of inside ``config/``.
    """

    def populate(self, strategy_path: Path | None) -> None:  # noqa: D102 — see class docstring
        if strategy_path is not None and strategy_path.suffix in {".yaml", ".yml"}:
            strategy_path = self._yaml_strategy_as_json(strategy_path)
        super().populate(strategy_path)

    @staticmethod
    def _yaml_strategy_as_json(strategy_path: Path) -> Path:
        """Write a JSON twin of the YAML strategy file into the temp cache."""
        with strategy_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Strategy file must be a YAML mapping: {strategy_path}")
        cache_dir = Path(tempfile.gettempdir()) / "population_synthetic_gui" / "strategy_dag_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        json_path = cache_dir / f"{strategy_path.stem}.json"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return json_path


class _TaskOptionsAdapter:
    """Make a :class:`WorkflowConfigModel` + task name look like a flat-``options`` model.

    :class:`FlowOptionsPanel` edits a flow's flat ``options:`` block via
    ``model.path`` / ``get_options`` / ``get_option`` / ``set_option``. A
    workflow task's options live under ``tasks.<name>.options`` instead, so
    this thin adapter retargets those four calls at one task. Writes go
    straight through the underlying model (marking it dirty), so Ctrl+S
    round-trips per-task edits with the rest of the workflow YAML.
    """

    def __init__(self, model: WorkflowConfigModel, task_name: str) -> None:
        self._model = model
        self._task_name = task_name
        self._label = model.get_task_meta(task_name)["label"]

    @property
    def path(self) -> Path:
        # Only ``.name`` is read (as the options-panel header) — surface the task.
        return Path(f"{self._label}  ({self._task_name})")

    def get_options(self) -> dict:
        return self._model.get_task_options(self._task_name)

    def get_option(self, key: str):
        options = self._model.get_task_options(self._task_name)
        if key not in options:
            raise KeyError(f"Task '{self._task_name}' has no option '{key}'")
        return options[key]

    def set_option(self, key: str, value) -> None:
        self._model.set_task_option(self._task_name, key, value)


class FlowRunnerWindow(QMainWindow):
    """Flow-runner GUI: flow tab bar (top), graph + console (left), Options column (right)."""

    def __init__(self, entries: list[FlowEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries = entries
        self._current_entry: FlowEntry | None = None
        self._model: FlowConfigModel | None = None
        self._runner: CombinationRunner | WorkflowRunner | None = None
        self._abort_requested = False

        # Live-refresh timer for the population summary page: while a generate
        # run is in progress it re-globs each combo's output dir once per tick
        # so the "generated so far" counts and progress bars tick up.
        self._summary_timer = QTimer(self)
        self._summary_timer.setInterval(1000)

        self.setWindowTitle(_BASE_TITLE)
        self.resize(1300, 750)

        self._build_toolbar()
        self._build_ui()
        self._summary_timer.timeout.connect(self._summary_panel.refresh_counts)
        self.setStatusBar(QStatusBar())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("File", self)
        toolbar.setMovable(False)

        self._save_action = QAction("Save", self)
        self._save_action.setShortcut(QKeySequence("Ctrl+S"))
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._on_save)
        toolbar.addAction(self._save_action)

        self._save_as_action = QAction("Save As…", self)
        self._save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._save_as_action.setEnabled(False)
        self._save_as_action.triggered.connect(self._on_save_as)
        toolbar.addAction(self._save_as_action)

        self.addToolBar(toolbar)

    def _build_ui(self) -> None:
        # --- Top bar: the flow selector as a full-width row of tabs ---
        self._flow_selector = FlowSelector(self._entries)

        # --- Graph column: a QStackedWidget swapping pages by flow kind ---
        # Script flows show the strategy DAG, workflow flows the task DAG; both
        # kinds' options live in the right-hand Options column instead of under
        # the graph, so a page here is a single widget.
        self._center_stack = QStackedWidget()

        # Script page: the strategy DAG (or an empty-state message).
        self._dag_view = _StrategyDagView()
        self._dag_message = self._build_placeholder("Select a flow to view its strategy DAG")
        self._dag_message.setWordWrap(True)
        self._dag_stack = QStackedWidget()
        self._dag_stack.addWidget(self._dag_message)
        self._dag_stack.addWidget(self._dag_view)
        # The script page IS the DAG stack (message/graph); named separately
        # because the view toggle and _load_flow raise it in the center stack.
        self._script_page: QWidget = self._dag_stack
        self._center_stack.addWidget(self._script_page)

        # Workflow page: the task DAG. Clicking a node retargets the Task tab
        # of the Options column, so selecting a node never hides the graph.
        self._workflow_graph = WorkflowGraphView()
        self._workflow_graph.node_clicked.connect(self._on_workflow_node_clicked)
        self._workflow_graph.enabled_changed.connect(self._on_task_enabled_changed)
        self._workflow_graph.force_changed.connect(self._on_task_force_changed)
        self._workflow_page: QWidget = self._workflow_graph
        self._center_stack.addWidget(self._workflow_page)

        # Population summary page: a live per-combo persona-generation table,
        # shown for script (generate) flows via the toggle bar below and
        # auto-shown while a generate run is in progress.
        self._summary_panel = PopulationSummaryPanel()
        self._center_stack.addWidget(self._summary_panel)

        # Center column = a toggle bar (Configure | Population Summary, script
        # flows only) stacked over the page-swapping center stack.
        self._center_column = QWidget()
        center_layout = QVBoxLayout(self._center_column)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)
        center_layout.addWidget(self._build_view_toggle())
        center_layout.addWidget(self._center_stack, stretch=1)

        # --- Console panel (reused from the legacy launcher, import only) ---
        self._console = ConsoleWidget()

        # --- Left side: graph column (top) over the console (bottom) ---
        # The console spans only this side; the Options column to its right is
        # full height.
        self._vsplitter = QSplitter(Qt.Vertical)
        self._vsplitter.addWidget(self._center_column)
        self._vsplitter.addWidget(self._console)
        self._vsplitter.setStretchFactor(0, 6)
        self._vsplitter.setStretchFactor(1, 4)
        # Terminal defaults to 40% of the left side's height.
        self._vsplitter.setSizes([600, 400])

        # --- Two-column horizontal splitter: graph+console | Options ---
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._vsplitter)
        self._splitter.addWidget(self._build_options_column())
        self._splitter.setStretchFactor(0, 12)  # graph + console
        self._splitter.setStretchFactor(1, 5)   # options (axis lists + option rows)
        # Pin the initial widths (stretch only governs resize, not the first
        # layout): the Options column is ~⅓ of the row.
        self._splitter.setSizes([700, 330])

        # --- Central widget: flow tabs, the splitter, and the run bar ---
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._flow_selector)
        layout.addWidget(self._splitter, stretch=1)
        layout.addWidget(self._build_run_bar())
        self.setCentralWidget(central)

        # --- Signals ---
        self._flow_selector.flow_changed.connect(self._load_flow)

    def _build_options_column(self) -> QWidget:
        """Right column: one "Options" header over a Global | Task tab set.

        *Global* is the :class:`AxisSelector` — three checkable lists bound to
        the flow YAML's ``selection:`` block (plus ``force:``), shown for BOTH
        ``three_axis`` and ``workflow`` flows since the checked combos feed the
        per-combo invocations / ``--slug`` lists at run time.

        *Task* is the options of whatever is loaded. The two flow kinds get one
        :class:`FlowOptionsPanel` each — a widget can live in only one place, and
        the workflow panel carries an extra task-description label — stacked
        here and raised by kind in :meth:`_load_flow`.
        """
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QLabel("Options")
        header.setStyleSheet("font-weight: bold; padding: 2px 4px;")
        layout.addWidget(header)

        self._options_tabs = QTabWidget()

        self._axis_selector = AxisSelector()
        self._axis_selector.selection_changed.connect(self._on_selection_changed)
        self._options_tabs.addTab(self._axis_selector, "Global")

        self._task_stack = QStackedWidget()

        # Script flows: the flat `options:` block of the flow YAML.
        self._options_panel = FlowOptionsPanel()
        self._options_panel.option_changed.connect(self._on_option_changed)
        self._task_stack.addWidget(self._options_panel)

        # Workflow flows: the clicked node's options, under a read-only
        # description sourced from the analysis registry via
        # WorkflowConfigModel.get_task_meta (secondary/subtle text).
        self._workflow_task_pane = QWidget()
        workflow_task_layout = QVBoxLayout(self._workflow_task_pane)
        workflow_task_layout.setContentsMargins(0, 0, 0, 0)
        workflow_task_layout.setSpacing(2)
        self._workflow_task_desc = QLabel()
        self._workflow_task_desc.setWordWrap(True)
        self._workflow_task_desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._workflow_task_desc.setStyleSheet("color: #888888; padding: 0px 4px 4px 4px;")
        self._workflow_task_desc.setVisible(False)  # shown once a node is clicked
        workflow_task_layout.addWidget(self._workflow_task_desc)
        self._workflow_options_panel = FlowOptionsPanel()
        self._workflow_options_panel.option_changed.connect(self._on_option_changed)
        workflow_task_layout.addWidget(self._workflow_options_panel)
        self._task_stack.addWidget(self._workflow_task_pane)

        self._options_tabs.addTab(self._task_stack, "Task")
        layout.addWidget(self._options_tabs, stretch=1)
        return column

    @staticmethod
    def _build_placeholder(text: str) -> QLabel:
        placeholder = QLabel(text)
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("QLabel { color: #888888; }")
        return placeholder

    def _build_view_toggle(self) -> QWidget:
        """Two exclusive toggle buttons flipping a script flow's center view.

        Shown only for ``kind: script`` flows (which produce personas); hidden
        for workflow flows. "Configure" shows the strategy-DAG + options page;
        "Population Summary" shows the live per-combo generation table.
        """
        self._view_toggle_bar = QWidget()
        hbox = QHBoxLayout(self._view_toggle_bar)
        hbox.setContentsMargins(4, 2, 4, 0)
        hbox.setSpacing(4)

        self._configure_button = QPushButton("Configure")
        self._summary_button = QPushButton("Population Summary")
        self._view_toggle_group = QButtonGroup(self)
        for button in (self._configure_button, self._summary_button):
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { padding: 3px 12px; }"
                " QPushButton:checked { font-weight: bold; background-color: #4CAF50; color: white; }"
            )
            self._view_toggle_group.addButton(button)
            hbox.addWidget(button)
        self._configure_button.setChecked(True)
        self._configure_button.clicked.connect(lambda: self._center_stack.setCurrentWidget(self._script_page))
        self._summary_button.clicked.connect(lambda: self._center_stack.setCurrentWidget(self._summary_panel))
        hbox.addStretch()

        self._view_toggle_bar.setVisible(False)  # shown per-flow in _load_flow
        return self._view_toggle_bar

    def _show_summary_page(self) -> None:
        """Switch the center to the summary page and sync the toggle."""
        self._center_stack.setCurrentWidget(self._summary_panel)
        self._summary_button.setChecked(True)

    def _show_configure_page(self) -> None:
        """Switch the center to the script config page and sync the toggle."""
        self._center_stack.setCurrentWidget(self._script_page)
        self._configure_button.setChecked(True)

    def _build_run_bar(self) -> QWidget:
        bar = QWidget()
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(6, 4, 6, 4)

        self._run_label = QLabel("No flow selected")
        self._run_label.setStyleSheet("color: gray;")
        hbox.addWidget(self._run_label, stretch=1)

        self._run_button = QPushButton("Run")
        self._run_button.setEnabled(False)  # enabled once a flow is loaded
        self._run_button.clicked.connect(self._on_run)
        self._run_button.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-size: 18px;"
            " padding: 8px 24px; border-radius: 4px; }"
            " QPushButton:hover { background-color: #45A049; }"
            " QPushButton:disabled { background-color: #A5D6A7; color: #E8E8E8; }"
        )
        hbox.addWidget(self._run_button)

        self._abort_button = QPushButton("Abort")
        self._abort_button.setVisible(False)  # shown only while a run is live
        self._abort_button.clicked.connect(self._on_abort)
        self._abort_button.setStyleSheet(
            "QPushButton { background-color: #F44336; color: white; font-size: 18px;"
            " padding: 8px 24px; border-radius: 4px; }"
            " QPushButton:hover { background-color: #D32F2F; }"
        )
        hbox.addWidget(self._abort_button)

        return bar

    # ------------------------------------------------------------------
    # Flow loading
    # ------------------------------------------------------------------

    def _load_flow(self, entry: FlowEntry) -> None:
        """FlowSelector → FlowConfigModel: load the flow's editable YAML."""
        if entry is self._current_entry and self._model is not None:
            return  # re-click on the already-loaded flow
        if self._runner is not None:
            self.statusBar().showMessage("A run is in progress — abort it before switching flows", 5000)
            self._revert_selector()
            return
        if not self._confirm_discard():
            self._revert_selector()
            return
        try:
            # Pick the model class by flow kind: workflow flows use `tasks:`
            # (the WorkflowConfigModel adds per-task accessors the graph panel
            # and runner need); script flows use the flat `options:` schema.
            model_cls = WorkflowConfigModel if entry.kind == "workflow" else FlowConfigModel
            model = model_cls(entry.config)
            # bind() validates the YAML selection ids against the discovered
            # axes BEFORE mutating any checks, so a failure here leaves the
            # previously bound flow's selector state intact.
            self._axis_selector.bind(model)
        except Exception as exc:  # fail-fast: surface the load error, keep the previous flow
            QMessageBox.critical(self, "Flow config error", f"Could not load {entry.config}:\n\n{exc}")
            self._revert_selector()
            return
        self._model = model
        self._current_entry = entry
        self._save_action.setEnabled(True)
        self._save_as_action.setEnabled(True)
        self._run_button.setEnabled(True)
        self._run_label.setText(f"{entry.category} / {entry.name}  [{entry.kind}]")
        # Both kinds open on the Global tab — combos are picked before options.
        self._options_tabs.setCurrentWidget(self._axis_selector)
        if entry.kind == "script":
            self._task_stack.setCurrentWidget(self._options_panel)
            self._options_panel.populate(model)
            self.refresh_dag(model)
            # Preview existing on-disk counts and expose the Configure/Summary toggle.
            self._summary_panel.populate_combos(
                self._axis_selector.checked_combos(),
                self._effective_total(),
                self._effective_ollama_host(),
            )
            self._view_toggle_bar.setVisible(True)
            self._show_configure_page()
        else:  # workflow
            self._view_toggle_bar.setVisible(False)
            self._center_stack.setCurrentWidget(self._workflow_page)
            self._task_stack.setCurrentWidget(self._workflow_task_pane)
            self._workflow_graph.populate(model)  # type: ignore[arg-type]
            self._workflow_task_desc.clear()
            self._workflow_task_desc.setVisible(False)
            self._workflow_options_panel.show_placeholder("Select a task node to edit its options")
        self._refresh_title()
        self.statusBar().showMessage(f"Loaded {entry.config.name}", 3000)

    def _revert_selector(self) -> None:
        """Re-check the previously loaded flow's button after a cancelled switch."""
        if self._current_entry is not None:
            self._flow_selector.select_entry(self._current_entry)

    def _effective_total(self) -> int | None:
        """The flow YAML's ``n`` option (what the GUI sends as ``--n``), or None.

        None => the summary panel falls back to ``compose_manifest().parallel_n``
        (flows without an ``n`` option, e.g. analysis flows). Uses
        ``get_options().get("n")`` — a native-typed plain dict — rather than
        ``get_option("n")``, which raises KeyError on flows lacking the key.
        """
        if self._model is None:
            return None
        n = self._model.get_options().get("n")
        return int(n) if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None

    def _effective_ollama_host(self) -> str | None:
        """The flow YAML's ``ollama-host`` option (sent as ``--ollama-host``), or None.

        The summary panel needs the *selected* host id, not the registry default:
        ``compose_manifest`` resolves ``default_host`` when given none, so without this
        the Workers column would show one GPU's numbers while the run targets another.
        None => flows with no ``ollama-host`` key (analysis/compare flows), where the
        panel keeps the composed scalar. Uses ``get_options().get(...)`` rather than
        ``get_option(...)``, which raises KeyError on flows lacking the key.
        """
        if self._model is None:
            return None
        host = self._model.get_options().get("ollama-host")
        return str(host) if host else None

    def _on_option_changed(self, key: str) -> None:
        """FlowOptionsPanel wrote through the model (now dirty) — reflect it in the title.

        ``ollama-host`` additionally feeds the summary panel's Workers column (worker
        capacity is per host), so switching hosts re-renders the preview immediately
        instead of leaving stale numbers on screen until the next axis tick. Only
        while idle — during a run the summary_timer owns refreshes.
        """
        self._refresh_title()
        if (
            key == "ollama-host"
            and self._runner is None
            and self._current_entry is not None
            and self._current_entry.kind == "script"
        ):
            self._summary_panel.populate_combos(
                self._axis_selector.checked_combos(),
                self._effective_total(),
                self._effective_ollama_host(),
            )

    def _on_selection_changed(self) -> None:
        """AxisSelector wrote through the model (now dirty) — title + DAG re-fire.

        The DAG re-render matters because the first checked combo (which the
        strategy-DAG View follows) may have changed. Workflow flows have no
        strategy-DAG tab, so only their title refreshes.
        """
        self._refresh_title()
        if self._current_entry is not None and self._current_entry.kind == "script":
            self.refresh_dag(self._model)
            # Only re-glob counts while idle — during a run the summary_timer owns refreshes.
            if self._runner is None:
                self._summary_panel.populate_combos(
                    self._axis_selector.checked_combos(),
                    self._effective_total(),
                    self._effective_ollama_host(),
                )

    # ------------------------------------------------------------------
    # Workflow graph interaction
    # ------------------------------------------------------------------

    def _on_workflow_node_clicked(self, name: str) -> None:
        """Retarget the Options column's Task tab onto the clicked task."""
        if not isinstance(self._model, WorkflowConfigModel):
            return
        # Registry-sourced description (see WorkflowConfigModel.get_task_meta).
        description = self._model.get_task_meta(name).get("description", "")
        self._workflow_task_desc.setText(description)
        self._workflow_task_desc.setVisible(bool(description))
        adapter = _TaskOptionsAdapter(self._model, name)
        self._workflow_options_panel.populate(adapter)  # type: ignore[arg-type]
        # Raise the Task tab — otherwise the click has no visible effect while
        # the Global tab is showing.
        self._options_tabs.setCurrentWidget(self._task_stack)
        self._workflow_graph.select_task(name)

    def _on_task_enabled_changed(self, name: str, enabled: bool) -> None:
        """Node Enabled checkbox → WorkflowConfigModel (dirty ``*``)."""
        if not isinstance(self._model, WorkflowConfigModel):
            return
        self._model.set_task_enabled(name, enabled)
        self._refresh_title()

    def _on_task_force_changed(self, name: str, force: bool) -> None:
        """Node Force checkbox → WorkflowConfigModel (dirty ``*``)."""
        if not isinstance(self._model, WorkflowConfigModel):
            return
        self._model.set_task_force(name, force)
        self._refresh_title()

    # ------------------------------------------------------------------
    # DAG View tab
    # ------------------------------------------------------------------

    def refresh_dag(self, model: FlowConfigModel | None) -> None:
        """Render the strategy DAG for the first selected combo of *model*.

        Uses the first ids of the flow YAML ``selection:`` block
        (models[0] × strategies[0] × countries[0]). The AxisSelector writes
        checks through the model, so this is the first *checked* combo — the
        model stays the single source of truth. A missing/empty selection or
        a composition error shows an informative empty state instead of
        crashing.
        """
        if model is None:
            self._show_dag_message("Select a flow to view its strategy DAG")
            return
        try:
            models = model.get_selection("models")
            strategies = model.get_selection("strategies")
            countries = model.get_selection("countries")
        except (KeyError, ValueError) as exc:
            self._show_dag_message(f"No usable 'selection:' block in {model.path.name}:\n\n{exc}")
            return
        if not (models and strategies and countries):
            self._show_dag_message(
                f"The 'selection:' block in {model.path.name} has an empty axis —\n"
                "check at least one model, strategy, and country to render a strategy DAG."
            )
            return
        combo = (models[0], strategies[0], countries[0])
        try:
            manifest = compose_manifest(*combo)
            self._dag_view.populate(manifest.strategy_path)
        except Exception as exc:  # surface loudly in the tab, keep the GUI alive
            self._show_dag_message(f"Could not compose the strategy DAG for {' × '.join(combo)}:\n\n{exc}")
            return
        self._dag_stack.setCurrentWidget(self._dag_view)

    def _show_dag_message(self, text: str) -> None:
        self._dag_message.setText(text)
        self._dag_stack.setCurrentWidget(self._dag_message)

    # ------------------------------------------------------------------
    # Execution (Run / Abort)
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        """Save the flow YAML, then dispatch the checked combos.

        EXECUTION CONTRACT: the GUI TRANSLATES the saved flow YAML into CLI
        invocations of the flow's existing script — the spawned script does
        NOT read the flow YAML (there is no ``--flow-config`` arg; do not add
        one). Save-before-run is persistence only, so what runs is what the
        user sees on disk.
        """
        if self._model is None or self._current_entry is None or self._runner is not None:
            return
        entry = self._current_entry

        # Save first (persistence only — see contract above). Abort on failure.
        if self._model.is_dirty and not self._on_save():
            return

        if entry.kind == "workflow":
            self._run_workflow()
            return
        if entry.axis_mode != "three_axis":
            self.statusBar().showMessage(f"Unsupported axis_mode: {entry.axis_mode}", 5000)
            return

        # Guards ported from the legacy launcher's `_run` (per_combo branch).
        combos = self._axis_selector.checked_combos()
        if not combos:
            QMessageBox.warning(
                self,
                "No Selection",
                "No selection — please check at least one item in each axis.",
            )
            return
        options = self._model.get_options()
        force = self._model.get_force() if self._model.has_force() else False

        # CombinationRunner (reused from the legacy launcher, import only)
        # only reads `action.script`; the rest is a minimal stand-in built
        # from the FlowEntry so the proven runner + process-tree kill are
        # reused verbatim. It builds each per-combo command with the same
        # translation rules as `commands.build_per_combo_cmds`.
        action = ActionEntry(
            id=entry.name,
            label=entry.name,
            script=entry.script,
            requires_manifest=True,
            axis_mode="per_combo",
        )
        # Rebuild the summary for exactly the combos about to run and auto-show it.
        self._summary_panel.populate_combos(combos, self._effective_total(), self._effective_ollama_host())
        self._show_summary_page()

        runner = CombinationRunner(combos, action, options, force)
        runner.combo_started.connect(self._on_combo_started)
        runner.line_received.connect(self._console.append_line)
        runner.cr_line_received.connect(self._console.append_cr_line)
        runner.finished_all.connect(self._on_runner_finished)
        self._runner = runner
        self._abort_requested = False
        self._set_running(True)
        runner.start()

    def _run_workflow(self) -> None:
        """Validate + snapshot the workflow, then run the enabled chain GUI-side.

        EXECUTION CONTRACT: the GUI TRANSLATES each task into CLI invocations
        of the task's script — the spawned scripts do NOT read the workflow
        YAML. The :class:`WorkflowState` is built from a plain
        :meth:`WorkflowConfigModel.to_plain` snapshot so the run is isolated
        from concurrent GUI edits; ``validate()`` surfaces a bad DAG loudly in
        the console and aborts the run without crashing the GUI.
        """
        assert isinstance(self._model, WorkflowConfigModel)
        combos = self._axis_selector.checked_combos()
        if not combos:
            QMessageBox.warning(
                self,
                "No Selection",
                "No selection — please check at least one item in each axis.",
            )
            return
        try:
            state = WorkflowState(self._model.to_plain(), PROJECT_ROOT)
            state.validate()
        except (ValueError, KeyError) as exc:
            self._console.append_line(f"!! Workflow validation failed: {exc}")
            QMessageBox.critical(self, "Workflow validation failed", str(exc))
            return

        self._workflow_graph.reset_statuses()
        runner = WorkflowRunner(state, combos, PROJECT_ROOT)
        runner.task_started.connect(self._on_task_started)
        runner.task_finished.connect(self._on_task_finished)
        runner.line_received.connect(self._console.append_line)
        runner.cr_line_received.connect(self._console.append_cr_line)
        runner.finished_all.connect(self._on_workflow_finished)
        self._runner = runner
        self._abort_requested = False
        self._set_running(True)
        runner.start()

    def _on_task_started(self, idx: int, total: int, name: str) -> None:
        self.statusBar().showMessage(f"TASK {idx}/{total}: {name}")

    def _on_task_finished(self, name: str, status: TaskStatus) -> None:
        self._workflow_graph.set_task_status(name, status)

    def _on_workflow_finished(self, aborted: bool) -> None:
        self._runner = None
        self._abort_requested = False
        self._set_running(False)
        self.statusBar().showMessage("Aborted" if aborted else "Workflow finished")

    def _on_abort(self) -> None:
        """Kill the live run (whole process tree — no orphaned grandchildren)."""
        if self._runner is None:
            return
        self._abort_requested = True
        self._runner.abort()  # sets the abort flag + _kill_process_tree on the live process
        self.statusBar().showMessage("Aborting…")

    def _on_combo_started(self, idx: int, total: int, model_id: str, strategy_id: str, country_id: str) -> None:
        self.statusBar().showMessage(f"Running {idx}/{total}: {model_id} × {strategy_id} × {country_id}")
        self._summary_panel.set_active_combo(model_id, strategy_id, country_id)

    def _on_runner_finished(self) -> None:
        aborted = self._abort_requested
        self._runner = None
        self._abort_requested = False
        self._set_running(False)
        self.statusBar().showMessage("Aborted" if aborted else "Finished all combinations")

    def _set_running(self, running: bool) -> None:
        """Run/Abort state machine: Run while idle, Abort while a run is live."""
        self._run_button.setEnabled(not running and self._current_entry is not None)
        self._abort_button.setVisible(running)
        self._abort_button.setEnabled(running)

        # Drive the live population-summary refresh only for generate (script) runs.
        is_script_run = self._current_entry is not None and self._current_entry.kind == "script"
        if running and is_script_run:
            self._summary_timer.start()
        else:
            self._summary_timer.stop()
            if is_script_run:
                # Settle on the true final counts, then drop the running-row highlight.
                self._summary_panel.refresh_counts()
                self._summary_panel.clear_active_combo()

    # ------------------------------------------------------------------
    # Dirty state / persistence
    # ------------------------------------------------------------------

    def _refresh_title(self) -> None:
        """Window title = base — flow name, with a ``*`` suffix while dirty."""
        title = _BASE_TITLE
        if self._current_entry is not None:
            title += f" — {self._current_entry.name}"
        if self._model is not None and self._model.is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _confirm_discard(self) -> bool:
        """Return True when it is safe to leave the current flow.

        Clean model → True. Dirty model → Save / Discard / Cancel dialog:
        Save saves (True on success), Discard → True, Cancel → False.
        """
        if self._model is None or not self._model.is_dirty:
            return True
        choice = QMessageBox.warning(
            self,
            "Unsaved changes",
            f"'{self._model.path.name}' has unsaved changes.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Save:
            return self._on_save()
        return choice == QMessageBox.Discard

    def _on_save(self) -> bool:
        """Save the current model back to its YAML; return True on success."""
        if self._model is None:
            return False
        try:
            self._model.save()
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save {self._model.path}:\n\n{exc}")
            return False
        self._refresh_title()
        self.statusBar().showMessage(f"Saved {self._model.path.name}", 3000)
        return True

    def _on_save_as(self) -> None:
        """Export the current model to a chosen path (model stays bound to its original file)."""
        if self._model is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save flow config as", str(self._model.path), "YAML files (*.yaml *.yml)"
        )
        if not path_str:
            return
        try:
            self._model.save_as(Path(path_str))
        except OSError as exc:
            QMessageBox.critical(self, "Save As failed", f"Could not save {path_str}:\n\n{exc}")
            return
        self._refresh_title()
        self.statusBar().showMessage(f"Saved {Path(path_str).name}", 3000)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Abort a live run (kill the whole process tree) BEFORE the dirty
        # confirm — a `claude`/`ollama` grandchild must never outlive the
        # window, however the confirm dialog is answered.
        if self._runner is not None:
            self._abort_requested = True
            self._runner.abort()
            self._runner.wait(5000)  # let the QThread drain and emit finished_all
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

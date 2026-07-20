"""Round-trip editable model for a workflow flow's YAML (``tasks:`` schema).

:class:`WorkflowConfigModel` extends :class:`FlowConfigModel` with per-task
accessors operating on the ``tasks:`` mapping — same ruamel round-trip
guarantees (comments, key order, quoting survive save), same fail-fast
convention (unknown task names and unknown option keys raise; nothing can be
added from the GUI).

:meth:`to_plain` snapshots the whole document into plain Python containers —
the input shape :class:`~population_synthetic.gui.workflow_state.WorkflowState`
is built from, so a run is isolated from concurrent GUI edits.

Execution contract: Save is persistence only — on Run the GUI TRANSLATES each
task into CLI invocations of the task's script; the spawned scripts do NOT
read this file.
"""

from __future__ import annotations

from typing import Any

from population_synthetic.analysis.utils.registry import get_process
from population_synthetic.gui.flow_config_model import FlowConfigModel

_MISSING = object()


class WorkflowConfigModel(FlowConfigModel):
    """In-memory representation of one workflow YAML with round-trip fidelity."""

    # ------------------------------------------------------------------
    # Task lookup
    # ------------------------------------------------------------------

    def _tasks_block(self) -> dict:
        tasks = self._data.get("tasks", _MISSING)
        if tasks is _MISSING:
            raise KeyError(f"Workflow config {self._path} has no 'tasks:' block")
        if not isinstance(tasks, dict):  # CommentedMap is a dict subclass
            raise ValueError(f"Workflow config {self._path}: 'tasks:' must be a mapping, got {type(tasks).__name__}")
        return tasks

    def _task(self, name: str) -> dict:
        tasks = self._tasks_block()
        if name not in tasks:
            raise KeyError(f"Workflow config {self._path}: unknown task '{name}' (known: {list(tasks)})")
        task = tasks[name]
        if not isinstance(task, dict):
            raise ValueError(f"Workflow config {self._path}: task '{name}' must be a mapping")
        return task

    def get_task_names(self) -> list[str]:
        """Task names in YAML authoring order."""
        return [str(name) for name in self._tasks_block()]

    # ------------------------------------------------------------------
    # Enabled / force (the two node checkboxes)
    # ------------------------------------------------------------------

    def is_task_enabled(self, name: str) -> bool:
        task = self._task(name)
        if "enabled" not in task:
            raise KeyError(f"Workflow config {self._path}: task '{name}' has no 'enabled' key")
        value = task["enabled"]
        if not isinstance(value, bool):
            raise ValueError(f"Workflow config {self._path}: task '{name}' 'enabled' must be a boolean, got {value!r}")
        return bool(value)

    def set_task_enabled(self, name: str, enabled: bool) -> None:
        task = self._task(name)
        if "enabled" not in task:
            raise KeyError(f"Workflow config {self._path}: task '{name}' has no 'enabled' key")
        task["enabled"] = bool(enabled)
        self._dirty = True

    def get_task_force(self, name: str) -> bool:
        """Return the task's ``force`` value (tasks with ``supports_force`` only)."""
        task = self._task(name)
        if "force" not in task:
            raise KeyError(
                f"Workflow config {self._path}: task '{name}' has no 'force' key (supports_force tasks only)"
            )
        value = task["force"]
        if not isinstance(value, bool):
            raise ValueError(f"Workflow config {self._path}: task '{name}' 'force' must be a boolean, got {value!r}")
        return bool(value)

    def set_task_force(self, name: str, force: bool) -> None:
        task = self._task(name)
        if "force" not in task:
            raise KeyError(
                f"Workflow config {self._path}: task '{name}' has no 'force' key (supports_force tasks only)"
            )
        task["force"] = bool(force)
        self._dirty = True

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    def _task_options_block(self, name: str) -> dict:
        task = self._task(name)
        options = task.get("options", _MISSING)
        if options is _MISSING:
            raise KeyError(f"Workflow config {self._path}: task '{name}' has no 'options:' block")
        if not isinstance(options, dict):
            raise ValueError(
                f"Workflow config {self._path}: task '{name}' 'options:' must be a mapping, "
                f"got {type(options).__name__}"
            )
        return options

    def get_task_options(self, name: str) -> dict[str, Any]:
        """Plain-dict snapshot of the task's ``options:`` block (values normalized)."""
        return {key: self._native_type(value) for key, value in self._task_options_block(name).items()}

    def set_task_option(self, name: str, key: str, value: Any) -> None:
        """Set an existing task option (fail-fast on unknown keys — keys are CLI flag names)."""
        options = self._task_options_block(name)
        if key not in options:
            raise KeyError(
                f"Workflow config {self._path}: task '{name}' has no option '{key}' — "
                f"options cannot be added from the GUI"
            )
        options[key] = self._native_type(value)
        self._dirty = True

    # ------------------------------------------------------------------
    # Dependencies / metadata
    # ------------------------------------------------------------------

    def get_task_dependencies(self, name: str) -> list[str]:
        task = self._task(name)
        if "depends_on" not in task:
            raise KeyError(f"Workflow config {self._path}: task '{name}' has no 'depends_on' key")
        value = task["depends_on"]
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(
                f"Workflow config {self._path}: task '{name}' 'depends_on' must be a list, got {type(value).__name__}"
            )
        return [str(dep) for dep in value]

    def get_task_meta(self, name: str) -> dict[str, Any]:
        """Non-editable task metadata for the graph panel and dispatch.

        The task key is the canonical analysis-registry id: ``label``,
        ``description``, ``script`` (project-relative string) and ``dispatch``
        are resolved from ``config/analysis/analysis_registry.yaml`` (their
        single source of truth -- they are NOT duplicated in the flow YAML).
        The GUI-only orchestration fields ``supports_force`` (default
        ``False``) and ``min_combos``/``max_combos`` (default ``None``) are
        read from this task's flow YAML mapping.

        Fails loudly (raises :class:`KeyError`) when the flow task id is not a
        registered analysis process -- a config error, never a silent default.
        """
        task = self._task(name)
        try:
            process = get_process(name)
        except KeyError as exc:
            raise KeyError(
                f"Workflow config {self._path}: task '{name}' is not a registered analysis "
                f"process id -- label/description/script/dispatch are owned by the analysis "
                f"registry (config/analysis/analysis_registry.yaml)."
            ) from exc
        return {
            "label": process.label,
            "description": process.description,
            "script": process.script,
            "dispatch": process.dispatch,
            "supports_force": bool(task.get("supports_force", False)),
            "min_combos": self._native_type(task.get("min_combos")),
            "max_combos": self._native_type(task.get("max_combos")),
        }

    # ------------------------------------------------------------------
    # Snapshot for WorkflowState
    # ------------------------------------------------------------------

    def to_plain(self) -> dict[str, Any]:
        """Recursively convert the document to plain dict/list/scalar containers.

        The snapshot feeds :class:`WorkflowState` so the running workflow is
        decoupled from the live ruamel tree (and from subsequent GUI edits).

        Each task is enriched with its registry-owned ``label``/``script``/
        ``dispatch`` (stripped from the flow YAML -- the analysis registry is
        their single source of truth), so the plain snapshot is a complete
        :class:`WorkflowState` input without re-duplicating those fields on
        disk. Enrichment routes through :meth:`get_task_meta`, so an
        unregistered task id fails loudly here too.
        """
        plain = self._to_plain_value(self._data)
        tasks = plain.get("tasks")
        if isinstance(tasks, dict):
            for task_name, task in tasks.items():
                if not isinstance(task, dict):
                    continue
                meta = self.get_task_meta(str(task_name))
                task["label"] = meta["label"]
                task["script"] = meta["script"]
                task["dispatch"] = meta["dispatch"]
        return plain

    @classmethod
    def _to_plain_value(cls, value: Any) -> Any:
        if isinstance(value, dict):  # CommentedMap is a dict subclass
            return {str(key): cls._to_plain_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):  # CommentedSeq is a list subclass
            return [cls._to_plain_value(item) for item in value]
        return cls._native_type(value)

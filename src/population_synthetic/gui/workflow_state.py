"""Headless workflow engine — DAG parse / validate / order / gate.

Mirror of the reference AnalysisRunnerGUI ``DagConfigHandler``
(``social-touch-semi-controlled-analysis``,
``src/_vendor/_vendor_pipeline_config_manager.py``): ``can_run(name)`` =
enabled AND ``depends_on`` ⊆ completed; ``mark_completed(name)`` unlocks
dependents. On top of that mirror this adds fail-fast validation (the
reference silently skips unknown tasks — we raise), a deterministic
topological order, per-run task statuses, and min/max-combo guard checks.

This module is deliberately Qt-free so the whole engine is unit-testable
headlessly; the Phase-7 ``WorkflowRunner`` (QThread) drives it.

Execution contract: the GUI walks tasks in :meth:`WorkflowState.ordered_tasks`
order and TRANSLATES each into CLI invocations of the task's script via the
pure builders in :mod:`population_synthetic.gui.commands` — the spawned
scripts do NOT read the workflow YAML.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_VALID_DISPATCH = ("per_combo", "slugs")

_REQUIRED_TASK_KEYS = ("label", "script", "dispatch", "enabled", "options", "depends_on")
_OPTIONAL_TASK_KEYS = ("supports_force", "force", "min_combos", "max_combos")


class TaskStatus(Enum):
    """Per-run state of one workflow task (transient — never written to YAML)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_DEP = "skipped_dep"
    SKIPPED_GUARD = "skipped_guard"
    ABORTED = "aborted"


@dataclass
class WorkflowTask:
    """One task of the workflow DAG (mirror of the YAML task schema)."""

    name: str
    label: str
    script: Path  # resolved against the project root
    dispatch: str  # 'per_combo' | 'slugs'
    enabled: bool
    supports_force: bool
    force: bool
    options: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    min_combos: int | None = None
    max_combos: int | None = None


class WorkflowState:
    """DAG of :class:`WorkflowTask` with gating and per-run statuses.

    Built from a **plain-python snapshot** of the workflow YAML (a dict from
    ``yaml.safe_load`` or :meth:`WorkflowConfigModel.to_plain`) plus the
    project root for script resolution — never from live ruamel containers,
    so a run is isolated from concurrent GUI edits.
    """

    def __init__(self, snapshot: Mapping[str, Any], project_root: Path) -> None:
        self._project_root = Path(project_root)
        tasks_block = snapshot.get("tasks")
        if not isinstance(tasks_block, Mapping) or not tasks_block:
            raise ValueError("Workflow config needs a non-empty 'tasks:' mapping")
        # dict preserves the YAML authoring order — the ordered_tasks tie-break.
        self.tasks: dict[str, WorkflowTask] = {
            str(name): self._parse_task(str(name), raw) for name, raw in tasks_block.items()
        }
        self.completed_tasks: set[str] = set()
        #: Per-run statuses; the runner overwrites entries as tasks progress.
        self.status: dict[str, TaskStatus] = {name: TaskStatus.PENDING for name in self.tasks}

    def _parse_task(self, name: str, raw: Any) -> WorkflowTask:
        """Parse one task mapping fail-fast (missing/unknown keys raise)."""
        if not isinstance(raw, Mapping):
            raise ValueError(f"Workflow task '{name}': expected a mapping, got {type(raw).__name__}")
        missing = [key for key in _REQUIRED_TASK_KEYS if key not in raw]
        if missing:
            raise ValueError(f"Workflow task '{name}': missing required key(s) {missing}")
        unknown = [key for key in raw if key not in _REQUIRED_TASK_KEYS + _OPTIONAL_TASK_KEYS]
        if unknown:
            raise ValueError(f"Workflow task '{name}': unknown key(s) {unknown}")

        options = raw["options"]
        if not isinstance(options, Mapping):
            raise ValueError(f"Workflow task '{name}': 'options' must be a mapping, got {type(options).__name__}")
        depends_on = raw["depends_on"]
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            raise ValueError(f"Workflow task '{name}': 'depends_on' must be a list, got {type(depends_on).__name__}")

        def _bool(key: str, default: bool | None = None) -> bool:
            value = raw.get(key, default)
            if not isinstance(value, bool):
                raise ValueError(f"Workflow task '{name}': '{key}' must be a boolean, got {value!r}")
            return value

        def _combo_bound(key: str) -> int | None:
            value = raw.get(key)
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Workflow task '{name}': '{key}' must be an integer, got {value!r}")
            return value

        return WorkflowTask(
            name=name,
            label=str(raw["label"]),
            script=self._project_root / str(raw["script"]),
            dispatch=str(raw["dispatch"]),
            enabled=_bool("enabled"),
            supports_force=_bool("supports_force", default=False),
            force=_bool("force", default=False),
            options=dict(options),
            depends_on=[str(dep) for dep in depends_on],
            min_combos=_combo_bound("min_combos"),
            max_combos=_combo_bound("max_combos"),
        )

    def _task(self, name: str) -> WorkflowTask:
        if name not in self.tasks:
            raise KeyError(f"Unknown workflow task '{name}' (known: {list(self.tasks)})")
        return self.tasks[name]

    # ------------------------------------------------------------------
    # Validation (fail-fast at flow load)
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Raise :class:`ValueError` on any structural problem in the DAG.

        Checks, in order: dispatch value, script existence on disk,
        ``min_combos``/``max_combos`` consistency, unknown ``depends_on``
        targets, and cycles (via Kahn — the leftover members are named).
        """
        for name, task in self.tasks.items():
            if task.dispatch not in _VALID_DISPATCH:
                raise ValueError(
                    f"Workflow task '{name}': dispatch '{task.dispatch}' is not one of {_VALID_DISPATCH}"
                )
            if not task.script.is_file():
                raise ValueError(f"Workflow task '{name}': script not found on disk: {task.script}")
            if task.min_combos is not None and task.max_combos is not None and task.min_combos > task.max_combos:
                raise ValueError(
                    f"Workflow task '{name}': min_combos ({task.min_combos}) > max_combos ({task.max_combos})"
                )
            for dep in task.depends_on:
                if dep not in self.tasks:
                    raise ValueError(f"Workflow task '{name}': unknown depends_on target '{dep}'")
        self.ordered_tasks()  # raises on cycles, naming the members

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def ordered_tasks(self) -> list[WorkflowTask]:
        """Kahn topological sort with YAML authoring order as the tie-break.

        Among all ready tasks (in-degree zero), the one appearing earliest in
        the YAML is emitted first — deterministic across runs by construction.

        Raises:
            ValueError: On a dependency cycle; the tasks left after Kahn
                (the cycle members and everything downstream of them) are
                named in the message.
        """
        pending_deps = {name: set(task.depends_on) for name, task in self.tasks.items()}
        authoring_order = list(self.tasks)
        ordered: list[WorkflowTask] = []
        while pending_deps:
            ready = [name for name in authoring_order if name in pending_deps and not pending_deps[name]]
            if not ready:
                leftover = [name for name in authoring_order if name in pending_deps]
                raise ValueError(f"Workflow has a dependency cycle involving: {leftover}")
            for name in ready:
                ordered.append(self.tasks[name])
                del pending_deps[name]
                for deps in pending_deps.values():
                    deps.discard(name)
        return ordered

    # ------------------------------------------------------------------
    # Gating (mirror of the reference DagConfigHandler)
    # ------------------------------------------------------------------

    def can_run(self, name: str) -> bool:
        """True iff the task is enabled AND all its dependencies completed."""
        task = self._task(name)
        return task.enabled and set(task.depends_on).issubset(self.completed_tasks)

    def mark_completed(self, name: str) -> None:
        """Mark a task completed (status ``COMPLETED``), unlocking dependents.

        Only called on success (all invocations exited 0) — skipped or failed
        tasks are never marked, so their dependents stay dep-blocked.
        """
        self._task(name)
        self.completed_tasks.add(name)
        self.status[name] = TaskStatus.COMPLETED

    # ------------------------------------------------------------------
    # Combo-count guards
    # ------------------------------------------------------------------

    def guard_violation(self, name: str, n_combos: int) -> str | None:
        """Human message when *n_combos* violates the task's min/max guard, else None.

        The runner prefixes it with ``!! SKIP <task>: `` and continues the run
        (loud skip; the task is not marked completed, so dependents dep-skip).
        """
        task = self._task(name)
        lo, hi = task.min_combos, task.max_combos
        if lo is not None and hi is not None and lo == hi:
            if n_combos != lo:
                return f"needs exactly {lo} selected combinations, got {n_combos}"
            return None
        if lo is not None and n_combos < lo:
            return f"needs at least {lo} selected combinations, got {n_combos}"
        if hi is not None and n_combos > hi:
            return f"needs at most {hi} selected combinations, got {n_combos}"
        return None

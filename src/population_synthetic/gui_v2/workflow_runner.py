"""Workflow runner — a Qt-free execution core plus its ``QThread`` driver.

The DAG-walking decision logic lives in the pure :func:`execute_workflow`
helper (no Qt, no subprocess of its own — it calls injected ``run_cmd`` /
``emit`` callables), so the whole runner is unit-testable headlessly. The
:class:`WorkflowRunner` ``QThread`` is a thin adapter: it wires ``run_cmd`` to
a live ``subprocess.Popen`` (streaming stdout, reused from the legacy
``CombinationRunner`` pattern) and ``emit`` to its Qt signals.

Execution contract: on Run the GUI TRANSLATES each workflow task into CLI
invocations of the task's script via the pure builders in
:mod:`population_synthetic.gui_v2.commands` — the spawned scripts do NOT read
the workflow YAML (there is no ``--flow-config`` argument; do not add one).

Execution semantics (per task, in :meth:`WorkflowState.ordered_tasks` order):

1. disabled          -> ``SKIPPED_DISABLED``, ``-- SKIP <name> (disabled)``.
2. dep not completed  -> ``SKIPPED_DEP``, names the first unmet dependency.
3. combo-count guard  -> ``SKIPPED_GUARD``, LOUD ``!! SKIP <name>: <message>``.
4. run                -> per-task banner; ``per_combo`` runs one subprocess per
   combo (first nonzero exit fails the whole task, remaining combos skipped);
   ``slugs`` runs one subprocess. All exit 0 -> ``COMPLETED``; else ``FAILED``
   (``!! TASK FAILED (exit N)``). The loop continues regardless, so
   independent branches still run.

Abort: :meth:`WorkflowRunner.abort` sets a flag and kills the live process
tree; the running task and every not-yet-started task become ``ABORTED`` and
``finished_all(aborted=True)`` is emitted.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from population_synthetic.gui_v2.commands import build_per_combo_cmds, build_slugs_cmd
from population_synthetic.gui_v2.workflow_state import TaskStatus, WorkflowState, WorkflowTask

Combo = tuple[str, str, str]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BANNER_RULE = "=" * 60


# ---------------------------------------------------------------------------
# Events emitted by the Qt-free core (mapped to Qt signals by WorkflowRunner)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsoleLine:
    """A console line (banner / skip notice) — maps to ``line_received``."""

    text: str


@dataclass(frozen=True)
class TaskStarted:
    """A task began running — maps to ``task_started(idx, total, name)``."""

    idx: int
    total: int
    name: str


@dataclass(frozen=True)
class TaskFinished:
    """A task reached a terminal state — maps to ``task_finished(name, status)``.

    Emitted for EVERY task (skipped/failed/completed/aborted) so the graph
    panel repaints each node exactly once per run.
    """

    name: str
    status: TaskStatus


@dataclass(frozen=True)
class FinishedAll:
    """The whole walk finished — maps to ``finished_all(aborted)``."""

    aborted: bool


# ---------------------------------------------------------------------------
# Qt-free execution core
# ---------------------------------------------------------------------------


def _task_banner(idx: int, total: int, task: WorkflowTask, combos: Sequence[Combo]) -> str:
    """CombinationRunner-style banner for the start of a task's turn."""
    lines = [
        _BANNER_RULE,
        f"  TASK {idx}/{total}: {task.name} — {task.script.name}",
    ]
    if task.dispatch == "per_combo":
        lines.append(f"    dispatch: per_combo ({len(combos)} combo(s))")
        if task.supports_force and task.force:
            lines.append("    force: on")
    else:  # slugs
        from population_synthetic.generators.synthetic.manifest_loader import axis_slug

        slugs = [axis_slug(m, s, c) for m, s, c in combos]
        lines.append(f"    dispatch: slugs ({len(slugs)} pipeline(s))")
        lines.append(f"    slugs: {', '.join(slugs)}")
    lines.append(_BANNER_RULE)
    return "\n".join(lines)


def _run_task(
    task: WorkflowTask,
    combos: Sequence[Combo],
    run_cmd: Callable[[list[str]], int],
    emit: Callable[[object], None],
    is_aborted: Callable[[], bool],
) -> int:
    """Run one enabled, un-guarded task; return its exit code (first nonzero wins)."""
    if task.dispatch == "per_combo":
        cmds = build_per_combo_cmds(task.script, combos, task.options, task.force)
        total = len(cmds)
        for i, (cmd, combo) in enumerate(zip(cmds, combos), start=1):
            if is_aborted():
                return 1
            emit(ConsoleLine(f"  -- combo {i}/{total}: {' × '.join(combo)}"))
            code = run_cmd(cmd)
            if code != 0:
                return code  # first nonzero exit fails the whole task
        return 0
    # dispatch == "slugs": one invocation total
    cmd = build_slugs_cmd(task.script, combos, task.options, task.force)
    return run_cmd(cmd)


def execute_workflow(
    state: WorkflowState,
    combos: Sequence[Combo],
    run_cmd: Callable[[list[str]], int],
    emit: Callable[[object], None],
    is_aborted: Callable[[], bool] = lambda: False,
) -> None:
    """Walk *state* in dependency order, running each task via *run_cmd*.

    Pure orchestration: no Qt, no subprocess, no I/O of its own. ``run_cmd``
    runs one CLI invocation and returns its exit code; ``emit`` receives the
    event objects above; ``is_aborted`` is polled between tasks and combos.
    Mutates ``state.status`` / ``state.completed_tasks`` in place.
    """
    ordered = state.ordered_tasks()
    total = len(ordered)
    n_combos = len(combos)

    for idx, task in enumerate(ordered, start=1):
        name = task.name

        if is_aborted():
            state.status[name] = TaskStatus.ABORTED
            emit(TaskFinished(name, TaskStatus.ABORTED))
            continue

        # 1. Disabled — skip, do not complete.
        if not task.enabled:
            state.status[name] = TaskStatus.SKIPPED_DISABLED
            emit(ConsoleLine(f"-- SKIP {name} (disabled)"))
            emit(TaskFinished(name, TaskStatus.SKIPPED_DISABLED))
            continue

        # 2. A dependency did not complete — skip, name the first unmet dep.
        if not state.can_run(name):
            unmet = next((dep for dep in task.depends_on if dep not in state.completed_tasks), None)
            state.status[name] = TaskStatus.SKIPPED_DEP
            emit(ConsoleLine(f"-- SKIP {name} (dependency '{unmet}' did not complete)"))
            emit(TaskFinished(name, TaskStatus.SKIPPED_DEP))
            continue

        # 3. Combo-count guard — LOUD skip, run continues.
        violation = state.guard_violation(name, n_combos)
        if violation is not None:
            state.status[name] = TaskStatus.SKIPPED_GUARD
            emit(ConsoleLine(f"{_BANNER_RULE}\n!! SKIP {name}: {violation}\n{_BANNER_RULE}"))
            emit(TaskFinished(name, TaskStatus.SKIPPED_GUARD))
            continue

        # 4. Run.
        state.status[name] = TaskStatus.RUNNING
        emit(TaskStarted(idx, total, name))
        emit(ConsoleLine(_task_banner(idx, total, task, combos)))
        exit_code = _run_task(task, combos, run_cmd, emit, is_aborted)

        if is_aborted():
            state.status[name] = TaskStatus.ABORTED
            emit(ConsoleLine(f"!! ABORTED: {name}"))
            emit(TaskFinished(name, TaskStatus.ABORTED))
            continue
        if exit_code == 0:
            state.mark_completed(name)  # sets COMPLETED
            emit(TaskFinished(name, TaskStatus.COMPLETED))
        else:
            state.status[name] = TaskStatus.FAILED
            emit(ConsoleLine(f"!! TASK FAILED (exit {exit_code}): {name} — dependents will be skipped"))
            emit(TaskFinished(name, TaskStatus.FAILED))

    emit(FinishedAll(aborted=is_aborted()))


# ---------------------------------------------------------------------------
# QThread driver
# ---------------------------------------------------------------------------


class WorkflowRunner(QThread):
    """Runs :func:`execute_workflow` off the GUI thread, streaming to signals.

    Signals
    -------
    task_started(idx, total, name)
    task_finished(name, status)      # status is a TaskStatus
    line_received(text)
    cr_line_received(text)           # \\r in-place progress updates
    finished_all(aborted)
    """

    task_started = pyqtSignal(int, int, str)
    task_finished = pyqtSignal(str, object)  # (name, TaskStatus)
    line_received = pyqtSignal(str)
    cr_line_received = pyqtSignal(str)
    finished_all = pyqtSignal(bool)

    def __init__(
        self,
        state: WorkflowState,
        combos: Sequence[Combo],
        project_root: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._combos = list(combos)
        self._project_root = Path(project_root)
        self._abort_flag = False
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------

    def abort(self) -> None:
        """Flag the run aborted and kill the live process tree (no orphans)."""
        # Imported lazily to keep this file's headless-testable `execute_workflow`
        # core decoupled from the CombinationRunner/ActionEntry classes defined
        # alongside `_kill_process_tree` in `gui_v2.execution`.
        from population_synthetic.gui_v2.execution import _kill_process_tree

        self._abort_flag = True
        if self._process is not None:
            _kill_process_tree(self._process)

    def run(self) -> None:  # noqa: D102 — QThread entry point
        execute_workflow(
            self._state,
            self._combos,
            run_cmd=self._run_cmd,
            emit=self._emit,
            is_aborted=lambda: self._abort_flag,
        )

    # ------------------------------------------------------------------

    def _emit(self, event: object) -> None:
        """Fan an execution-core event out to the matching Qt signal."""
        if isinstance(event, ConsoleLine):
            self.line_received.emit(event.text)
        elif isinstance(event, TaskStarted):
            self.task_started.emit(event.idx, event.total, event.name)
        elif isinstance(event, TaskFinished):
            self.task_finished.emit(event.name, event.status)
        elif isinstance(event, FinishedAll):
            self.finished_all.emit(event.aborted)
        else:
            raise TypeError(f"WorkflowRunner: unknown execution event {event!r}")

    def _run_cmd(self, cmd: list[str]) -> int:
        """Run one subprocess, streaming stdout live; return its exit code.

        Byte-oriented read (mirrors ``ProcessOutputReader``) so ``\\r`` progress
        updates route to ``cr_line_received`` while normal lines go to
        ``line_received``. The live handle is stored so :meth:`abort` can kill
        the whole tree.
        """
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        stdout = self._process.stdout
        assert stdout is not None
        buffer = b""
        while True:
            chunk = stdout.read(1)
            if not chunk:
                break
            buffer += chunk
            if chunk in (b"\n", b"\r"):
                text = _ANSI_RE.sub("", buffer.decode("utf-8", errors="replace"))
                if text.endswith("\r") and not text.endswith("\n"):
                    self.cr_line_received.emit(text.rstrip("\r"))
                else:
                    self.line_received.emit(text.rstrip("\n").rstrip("\r"))
                buffer = b""
        if buffer:
            text = _ANSI_RE.sub("", buffer.decode("utf-8", errors="replace")).rstrip("\r\n")
            if text:
                self.line_received.emit(text)
        code = self._process.wait()
        self._process = None
        return code

"""Headless tests for the gui workflow runner (``workflow_runner.py``).

These exercise the Qt-free :func:`execute_workflow` decision core directly —
no display, no real subprocesses, no ``QApplication``. The runner is factored
so the DAG-walking logic takes injected callables:

- ``run_cmd(cmd) -> int`` — stands in for one subprocess; here it records the
  command and returns a scripted exit code (nonzero for chosen scripts).
- ``emit(event)`` — collects the emitted :class:`ConsoleLine` /
  :class:`TaskStarted` / :class:`TaskFinished` / :class:`FinishedAll` events.
- ``is_aborted()`` — polled between tasks/combos to model an abort.

Covered: (a) map failure dep-skips its dependents while an enabled island
still runs; (b) a min/max-combo guard yields a loud ``!! SKIP`` and the run
continues; (c) the happy path completes the main chain in dependency order;
plus an abort marking the running + pending tasks ``ABORTED``.
"""

from __future__ import annotations

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui.workflow_runner import (
    ConsoleLine,
    FinishedAll,
    TaskFinished,
    TaskStarted,
    execute_workflow,
)
from population_synthetic.gui.workflow_state import TaskStatus, WorkflowState

COMBO_A = ("claude_haiku", "all_pick", "swedish")
COMBO_B = ("claude_sonnet", "all_pick", "swedish")
COMBO_C = ("gemini_flash", "all_pick", "swedish")


def _task(script: str, dispatch: str = "per_combo", enabled: bool = True,
          depends_on: list[str] | None = None, **extra) -> dict:
    task = {
        "label": script,
        "script": script,
        "dispatch": dispatch,
        "enabled": enabled,
        "options": {},
        "depends_on": depends_on if depends_on is not None else [],
    }
    task.update(extra)
    return task


def _main_chain_snapshot(**enabled: bool) -> dict:
    """map (per_combo) -> compare (slugs) -> perf (slugs); plus a disabled llm island."""
    return {
        "tasks": {
            "map": _task("scripts/map.py", dispatch="per_combo", enabled=enabled.get("map", True)),
            "compare": _task("scripts/compare.py", dispatch="slugs",
                             enabled=enabled.get("compare", True), depends_on=["map"]),
            "perf": _task("scripts/perf.py", dispatch="slugs",
                          enabled=enabled.get("perf", True), depends_on=["compare"]),
            "llm": _task("scripts/llm.py", dispatch="slugs", enabled=enabled.get("llm", False)),
        }
    }


class _Recorder:
    """Collects emitted events and scripts subprocess exit codes by script name."""

    def __init__(self, fail_substrings: tuple[str, ...] = ()) -> None:
        self.events: list[object] = []
        self.commands: list[list[str]] = []
        self._fail = fail_substrings

    def run_cmd(self, cmd: list[str]) -> int:
        self.commands.append(cmd)
        script = cmd[1]
        return 1 if any(sub in script for sub in self._fail) else 0

    def emit(self, event: object) -> None:
        self.events.append(event)

    def finished(self) -> dict[str, TaskStatus]:
        return {e.name: e.status for e in self.events if isinstance(e, TaskFinished)}

    def lines(self) -> list[str]:
        return [e.text for e in self.events if isinstance(e, ConsoleLine)]

    def started_order(self) -> list[str]:
        return [e.name for e in self.events if isinstance(e, TaskStarted)]

    def script_calls(self, name: str) -> int:
        return sum(1 for cmd in self.commands if name in cmd[1])


# ---------------------------------------------------------------------------
# (c) Happy path — main chain all enabled, 2 combos
# ---------------------------------------------------------------------------

def test_happy_path_main_chain_completed_in_order():
    state = WorkflowState(_main_chain_snapshot(), PROJECT_ROOT)
    rec = _Recorder()

    execute_workflow(state, [COMBO_A, COMBO_B], rec.run_cmd, rec.emit)

    fin = rec.finished()
    assert fin["map"] is TaskStatus.COMPLETED
    assert fin["compare"] is TaskStatus.COMPLETED
    assert fin["perf"] is TaskStatus.COMPLETED
    assert fin["llm"] is TaskStatus.SKIPPED_DISABLED  # disabled island

    order = rec.started_order()
    assert order.index("map") < order.index("compare") < order.index("perf")

    # per_combo map ran once per combo; slugs tasks ran once total.
    assert rec.script_calls("map.py") == 2
    assert rec.script_calls("compare.py") == 1
    assert rec.script_calls("perf.py") == 1

    assert any(isinstance(e, FinishedAll) and not e.aborted for e in rec.events)
    # every task got exactly one TaskFinished (so the graph repaints each once)
    assert len([e for e in rec.events if isinstance(e, TaskFinished)]) == 4


# ---------------------------------------------------------------------------
# (a) map fails -> dependents SKIPPED_DEP; enabled island still runs
# ---------------------------------------------------------------------------

def test_map_failure_dep_skips_dependents_but_island_runs():
    state = WorkflowState(_main_chain_snapshot(llm=True), PROJECT_ROOT)
    rec = _Recorder(fail_substrings=("map.py",))

    execute_workflow(state, [COMBO_A, COMBO_B], rec.run_cmd, rec.emit)

    fin = rec.finished()
    assert fin["map"] is TaskStatus.FAILED
    assert fin["compare"] is TaskStatus.SKIPPED_DEP
    assert fin["perf"] is TaskStatus.SKIPPED_DEP
    assert fin["llm"] is TaskStatus.COMPLETED  # independent island unaffected

    assert any("!! TASK FAILED (exit 1): map" in line for line in rec.lines())
    assert any("dependency 'map' did not complete" in line for line in rec.lines())
    assert any("dependency 'compare' did not complete" in line for line in rec.lines())

    # per_combo first nonzero exit fails the task — remaining combos not run.
    assert rec.script_calls("map.py") == 1
    assert not any(isinstance(e, FinishedAll) and e.aborted for e in rec.events)


# ---------------------------------------------------------------------------
# (b) guard violation -> loud SKIPPED_GUARD, run continues
# ---------------------------------------------------------------------------

def test_guard_violation_loud_skip_and_run_continues():
    snapshot = _main_chain_snapshot()
    snapshot["tasks"]["compare_pops"] = _task(
        "scripts/compare_pops.py", dispatch="slugs", enabled=True,
        depends_on=["map"], min_combos=2, max_combos=2,
    )
    state = WorkflowState(snapshot, PROJECT_ROOT)
    rec = _Recorder()

    execute_workflow(state, [COMBO_A, COMBO_B, COMBO_C], rec.run_cmd, rec.emit)  # 3 combos

    fin = rec.finished()
    assert fin["compare_pops"] is TaskStatus.SKIPPED_GUARD
    assert any(
        "!! SKIP compare_pops: needs exactly 2 selected combinations, got 3" in line
        for line in rec.lines()
    )
    # The guard is a loud skip, not a hard stop — the rest of the run proceeds.
    assert fin["map"] is TaskStatus.COMPLETED
    assert fin["compare"] is TaskStatus.COMPLETED
    assert rec.script_calls("compare_pops.py") == 0  # never invoked


# ---------------------------------------------------------------------------
# Abort — running task + not-yet-started tasks become ABORTED
# ---------------------------------------------------------------------------

def test_abort_marks_running_and_pending_aborted():
    state = WorkflowState(_main_chain_snapshot(), PROJECT_ROOT)
    rec = _Recorder()
    flag = {"aborted": False}

    def run_cmd(cmd: list[str]) -> int:
        rec.commands.append(cmd)
        flag["aborted"] = True  # user aborts mid-map; killed process exits nonzero
        return 1

    execute_workflow(state, [COMBO_A, COMBO_B], run_cmd, rec.emit,
                     is_aborted=lambda: flag["aborted"])

    fin = rec.finished()
    assert fin["map"] is TaskStatus.ABORTED
    assert fin["compare"] is TaskStatus.ABORTED
    assert fin["perf"] is TaskStatus.ABORTED
    assert fin["llm"] is TaskStatus.ABORTED
    assert any(isinstance(e, FinishedAll) and e.aborted for e in rec.events)
    assert rec.script_calls("map.py") == 1  # aborted before the second combo

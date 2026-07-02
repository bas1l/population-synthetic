"""Headless tests for the gui_v2 workflow engine (``workflow_state.py``).

Covers fail-fast validation (unknown dep, cycles, missing script, bad
dispatch, min>max), deterministic Kahn ordering for the shipped
``analysis_workflow.yaml``, DagConfigHandler-mirror gating
(enabled ∧ deps ⊆ completed), and min/max-combo guard messages.
No Qt required.
"""

from __future__ import annotations

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui_v2.workflow_state import TaskStatus, WorkflowState

SHIPPED_WORKFLOW = PROJECT_ROOT / "config" / "gui" / "v2" / "flows" / "analysis_workflow.yaml"


def _task(script: str = "task.py", dispatch: str = "per_combo", enabled: bool = True,
          depends_on: list[str] | None = None, **extra) -> dict:
    task = {
        "label": "T",
        "script": script,
        "dispatch": dispatch,
        "enabled": enabled,
        "options": {},
        "depends_on": depends_on if depends_on is not None else [],
    }
    task.update(extra)
    return task


@pytest.fixture
def root(tmp_path):
    """A project root containing the stub script every synthetic task points at."""
    (tmp_path / "task.py").write_text("# stub\n", encoding="utf-8")
    return tmp_path


def _shipped_state() -> WorkflowState:
    with SHIPPED_WORKFLOW.open(encoding="utf-8") as fh:
        snapshot = yaml.safe_load(fh)
    return WorkflowState(snapshot, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# validate() — fail-fast cases
# ---------------------------------------------------------------------------

def test_validate_unknown_dependency_raises(root):
    state = WorkflowState({"tasks": {"a": _task(depends_on=["ghost"])}}, root)
    with pytest.raises(ValueError, match="unknown depends_on target 'ghost'"):
        state.validate()


def test_validate_two_node_cycle_raises_naming_members(root):
    snapshot = {"tasks": {"a": _task(depends_on=["b"]), "b": _task(depends_on=["a"])}}
    with pytest.raises(ValueError, match=r"cycle involving.*'a'.*'b'"):
        WorkflowState(snapshot, root).validate()


def test_validate_self_loop_raises(root):
    state = WorkflowState({"tasks": {"a": _task(depends_on=["a"])}}, root)
    with pytest.raises(ValueError, match=r"cycle involving.*'a'"):
        state.validate()


def test_validate_missing_script_raises_naming_path(root):
    state = WorkflowState({"tasks": {"a": _task(script="nowhere/missing.py")}}, root)
    with pytest.raises(ValueError, match=r"script not found on disk.*missing\.py"):
        state.validate()


def test_validate_bad_dispatch_raises(root):
    state = WorkflowState({"tasks": {"a": _task(dispatch="targets")}}, root)
    with pytest.raises(ValueError, match="dispatch 'targets'"):
        state.validate()


def test_validate_min_greater_than_max_raises(root):
    state = WorkflowState({"tasks": {"a": _task(min_combos=3, max_combos=2)}}, root)
    with pytest.raises(ValueError, match=r"min_combos \(3\) > max_combos \(2\)"):
        state.validate()


def test_parse_missing_required_key_raises(root):
    with pytest.raises(ValueError, match="missing required key"):
        WorkflowState({"tasks": {"a": {"label": "T", "script": "task.py"}}}, root)


def test_parse_unknown_key_raises(root):
    with pytest.raises(ValueError, match="unknown key.*depend_on"):
        WorkflowState({"tasks": {"a": _task(depend_on=["b"])}}, root)


def test_parse_empty_tasks_raises(root):
    with pytest.raises(ValueError, match="non-empty 'tasks:'"):
        WorkflowState({"tasks": {}}, root)


# ---------------------------------------------------------------------------
# ordered_tasks() — shipped analysis_workflow.yaml
# ---------------------------------------------------------------------------

def test_shipped_workflow_validates():
    _shipped_state().validate()


def test_shipped_workflow_ordering():
    order = [task.name for task in _shipped_state().ordered_tasks()]
    assert set(order) == {
        "map_populations", "compare_synth_real", "model_performance",
        "compare_pops", "llm_metrics_per_run", "llm_metrics_cross_run",
    }
    assert order.index("map_populations") < order.index("compare_synth_real")
    assert order.index("compare_synth_real") < order.index("model_performance")
    assert order.index("map_populations") < order.index("compare_pops")


def test_shipped_workflow_ordering_deterministic():
    # Authoring-order tie-break: identical output across independent builds.
    order_a = [task.name for task in _shipped_state().ordered_tasks()]
    order_b = [task.name for task in _shipped_state().ordered_tasks()]
    assert order_a == order_b
    # Roots emit in authoring order before released dependents.
    assert order_a[0] == "map_populations"


# ---------------------------------------------------------------------------
# Gating — can_run / mark_completed / status
# ---------------------------------------------------------------------------

def test_disabled_task_cannot_run():
    state = _shipped_state()
    assert not state.can_run("llm_metrics_per_run")  # enabled: false in YAML


def test_dep_incomplete_blocks_then_mark_completed_unlocks():
    state = _shipped_state()
    assert state.can_run("map_populations")  # no deps, enabled
    assert not state.can_run("compare_synth_real")  # dep incomplete
    assert not state.can_run("model_performance")

    state.mark_completed("map_populations")
    assert state.can_run("compare_synth_real")
    assert not state.can_run("model_performance")  # transitive dep still incomplete

    state.mark_completed("compare_synth_real")
    assert state.can_run("model_performance")


def test_guard_skip_does_not_mark_completed():
    state = _shipped_state()
    state.mark_completed("map_populations")
    # compare_synth_real hits a guard: runner records the skip WITHOUT completing.
    state.status["compare_synth_real"] = TaskStatus.SKIPPED_GUARD
    assert "compare_synth_real" not in state.completed_tasks
    assert not state.can_run("model_performance")  # dependents stay blocked


def test_status_lifecycle():
    state = _shipped_state()
    assert all(status is TaskStatus.PENDING for status in state.status.values())
    state.mark_completed("map_populations")
    assert state.status["map_populations"] is TaskStatus.COMPLETED
    assert state.status["compare_synth_real"] is TaskStatus.PENDING


def test_unknown_task_name_raises():
    state = _shipped_state()
    with pytest.raises(KeyError, match="ghost"):
        state.can_run("ghost")
    with pytest.raises(KeyError, match="ghost"):
        state.mark_completed("ghost")
    with pytest.raises(KeyError, match="ghost"):
        state.guard_violation("ghost", 2)


# ---------------------------------------------------------------------------
# guard_violation()
# ---------------------------------------------------------------------------

def test_guard_exactly_message():
    state = _shipped_state()  # compare_pops: min_combos=2, max_combos=2
    assert state.guard_violation("compare_pops", 3) == "needs exactly 2 selected combinations, got 3"
    assert state.guard_violation("compare_pops", 1) == "needs exactly 2 selected combinations, got 1"
    assert state.guard_violation("compare_pops", 2) is None


def test_guard_min_only_message():
    state = _shipped_state()  # model_performance: min_combos=2
    assert state.guard_violation("model_performance", 1) == "needs at least 2 selected combinations, got 1"
    assert state.guard_violation("model_performance", 2) is None
    assert state.guard_violation("model_performance", 5) is None


def test_guard_max_only_message(root):
    state = WorkflowState({"tasks": {"a": _task(max_combos=4)}}, root)
    assert state.guard_violation("a", 5) == "needs at most 4 selected combinations, got 5"
    assert state.guard_violation("a", 4) is None


def test_guard_unbounded_task_never_violates():
    state = _shipped_state()
    assert state.guard_violation("map_populations", 1) is None
    assert state.guard_violation("map_populations", 99) is None

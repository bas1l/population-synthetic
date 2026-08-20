"""Headless tests for the gui workflow engine (``workflow_state.py``).

Covers fail-fast validation (unknown dep, cycles, missing script, bad
dispatch, min>max), deterministic Kahn ordering for the shipped
``analysis_workflow.yaml``, DagConfigHandler-mirror gating
(enabled ∧ deps ⊆ completed), the ``bypass`` key (required, boolean) and
``mark_bypassed`` as the second writer of ``completed_tasks``, and
min/max-combo guard messages. No Qt required.
"""

from __future__ import annotations

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui.workflow_config_model import WorkflowConfigModel
from population_synthetic.gui.workflow_state import TaskStatus, WorkflowState

SHIPPED_WORKFLOW = PROJECT_ROOT / "config" / "gui" / "flows" / "analysis_workflow.yaml"


def _task(script: str = "task.py", dispatch: str = "per_combo", enabled: bool = True,
          depends_on: list[str] | None = None, bypass: bool = False, **extra) -> dict:
    task = {
        "label": "T",
        "script": script,
        "dispatch": dispatch,
        "enabled": enabled,
        "bypass": bypass,
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
    # Build via the model so the snapshot is enriched with the registry-owned
    # label/script/dispatch (stripped from the flow YAML) -- exactly the path
    # the runner takes (main_window._run_workflow -> WorkflowConfigModel.to_plain).
    snapshot = WorkflowConfigModel(SHIPPED_WORKFLOW).to_plain()
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


def test_parse_missing_bypass_raises_naming_the_key(root):
    """'bypass' is required (no supports_ gate, so an absent key is a config error)."""
    task = _task()
    del task["bypass"]
    with pytest.raises(ValueError, match=r"missing required key\(s\).*bypass"):
        WorkflowState({"tasks": {"a": task}}, root)


def test_parse_non_boolean_bypass_raises(root):
    with pytest.raises(ValueError, match="'bypass' must be a boolean"):
        WorkflowState({"tasks": {"a": _task(bypass="yes")}}, root)


def test_validate_accepts_disabled_and_bypassed(root):
    """enabled: false + bypass: true is legal and inert, not a config error."""
    WorkflowState({"tasks": {"a": _task(enabled=False, bypass=True)}}, root).validate()


# ---------------------------------------------------------------------------
# ordered_tasks() — shipped analysis_workflow.yaml
# ---------------------------------------------------------------------------

def test_shipped_workflow_validates():
    _shipped_state().validate()


def test_shipped_workflow_ordering():
    order = [task.name for task in _shipped_state().ordered_tasks()]
    assert set(order) == {
        "validate_raw", "mapping", "validate_mapped", "population_cap",
        "fidelity", "multivariate_fidelity", "consistency",
        "model_ranking", "method_significance", "pairwise_comparison", "real_population_stats",
        "generation_metadata", "persona_realism", "realism_ranking",
        "validation_attrition",
    }
    # validate_raw is the DAG root; the validation gate is a linear chain
    # validate_raw -> mapping -> validate_mapped -> population_cap, and every
    # downstream analysis depends on population_cap (the last gate node).
    assert order.index("validate_raw") < order.index("mapping")
    assert order.index("mapping") < order.index("validate_mapped")
    assert order.index("validate_mapped") < order.index("population_cap")
    assert order.index("population_cap") < order.index("fidelity")
    assert order.index("population_cap") < order.index("multivariate_fidelity")
    assert order.index("population_cap") < order.index("consistency")
    assert order.index("population_cap") < order.index("pairwise_comparison")
    assert order.index("population_cap") < order.index("real_population_stats")
    assert order.index("population_cap") < order.index("generation_metadata")
    assert order.index("population_cap") < order.index("persona_realism")
    assert order.index("fidelity") < order.index("model_ranking")
    assert order.index("fidelity") < order.index("method_significance")
    # The cross-combination ranking consumes the per-combination judge output, so it
    # can never be scheduled before it.
    assert order.index("persona_realism") < order.index("realism_ranking")
    # The attrition report re-reads the gate's own records, so it hangs off the gate's
    # last node like every other leaf rather than off an analysis process.
    assert order.index("population_cap") < order.index("validation_attrition")


def test_shipped_workflow_ordering_deterministic():
    # Authoring-order tie-break: identical output across independent builds.
    order_a = [task.name for task in _shipped_state().ordered_tasks()]
    order_b = [task.name for task in _shipped_state().ordered_tasks()]
    assert order_a == order_b
    # validate_raw is the sole DAG root, emitted before every released dependent.
    assert order_a[0] == "validate_raw"


# ---------------------------------------------------------------------------
# Gating — can_run / mark_completed / status
# ---------------------------------------------------------------------------

def test_disabled_task_cannot_run():
    state = _shipped_state()
    # Satisfy pairwise_comparison's only dependency so the sole blocker under test
    # is its `enabled: false` flag (the last remaining disabled node in the YAML).
    state.mark_completed("mapping")
    assert not state.can_run("pairwise_comparison")  # enabled: false in YAML


def test_dep_incomplete_blocks_then_mark_completed_unlocks():
    state = _shipped_state()
    assert state.can_run("validate_raw")  # the DAG root: no deps, enabled
    assert not state.can_run("mapping")  # depends on validate_raw
    assert not state.can_run("validate_mapped")  # transitive dep incomplete
    assert not state.can_run("population_cap")
    assert not state.can_run("fidelity")  # dep incomplete
    assert not state.can_run("model_ranking")

    state.mark_completed("validate_raw")
    assert state.can_run("mapping")  # root satisfied -> mapping released

    state.mark_completed("mapping")
    assert state.can_run("validate_mapped")
    assert not state.can_run("population_cap")  # still needs validate_mapped

    state.mark_completed("validate_mapped")
    assert state.can_run("population_cap")  # gate satisfied -> cap released

    state.mark_completed("population_cap")
    # fidelity is disabled in the shipped YAML (opt-in), so it never runs itself; but its
    # dependent model_ranking stays blocked until fidelity is marked completed (as the
    # runner would when the node is enabled).
    assert not state.can_run("model_ranking")  # transitive dep still incomplete

    state.mark_completed("fidelity")
    assert state.can_run("model_ranking")


def test_guard_skip_does_not_mark_completed():
    state = _shipped_state()
    state.mark_completed("mapping")
    # fidelity hits a guard: runner records the skip WITHOUT completing.
    state.status["fidelity"] = TaskStatus.SKIPPED_GUARD
    assert "fidelity" not in state.completed_tasks
    assert not state.can_run("model_ranking")  # dependents stay blocked


def test_status_lifecycle():
    state = _shipped_state()
    assert all(status is TaskStatus.PENDING for status in state.status.values())
    state.mark_completed("mapping")
    assert state.status["mapping"] is TaskStatus.COMPLETED
    assert state.status["fidelity"] is TaskStatus.PENDING


def test_mark_bypassed_completes_without_the_completed_status():
    state = _shipped_state()
    state.mark_bypassed("mapping")
    assert "mapping" in state.completed_tasks  # counts as completed for gating
    assert state.status["mapping"] is TaskStatus.BYPASSED  # but stays distinct


def test_mark_bypassed_unlocks_dependents():
    state = _shipped_state()
    assert not state.can_run("validate_mapped")  # depends on mapping
    state.mark_bypassed("validate_raw")
    state.mark_bypassed("mapping")
    assert state.can_run("validate_mapped")


def test_unknown_task_name_raises():
    state = _shipped_state()
    with pytest.raises(KeyError, match="ghost"):
        state.can_run("ghost")
    with pytest.raises(KeyError, match="ghost"):
        state.mark_completed("ghost")
    with pytest.raises(KeyError, match="ghost"):
        state.mark_bypassed("ghost")
    with pytest.raises(KeyError, match="ghost"):
        state.guard_violation("ghost", 2)


# ---------------------------------------------------------------------------
# guard_violation()
# ---------------------------------------------------------------------------

def test_guard_exactly_message():
    state = _shipped_state()  # pairwise_comparison: min_combos=2, max_combos=2
    assert state.guard_violation("pairwise_comparison", 3) == "needs exactly 2 selected combinations, got 3"
    assert state.guard_violation("pairwise_comparison", 1) == "needs exactly 2 selected combinations, got 1"
    assert state.guard_violation("pairwise_comparison", 2) is None


def test_guard_min_only_message():
    state = _shipped_state()  # model_ranking: min_combos=2
    assert state.guard_violation("model_ranking", 1) == "needs at least 2 selected combinations, got 1"
    assert state.guard_violation("model_ranking", 2) is None
    assert state.guard_violation("model_ranking", 5) is None


def test_guard_max_only_message(root):
    state = WorkflowState({"tasks": {"a": _task(max_combos=4)}}, root)
    assert state.guard_violation("a", 5) == "needs at most 4 selected combinations, got 5"
    assert state.guard_violation("a", 4) is None


def test_guard_unbounded_task_never_violates():
    state = _shipped_state()
    assert state.guard_violation("mapping", 1) is None
    assert state.guard_violation("mapping", 99) is None

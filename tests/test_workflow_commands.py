"""Headless tests for the gui_v2 command builders and WorkflowConfigModel.

Covers the pure ``build_per_combo_cmds`` / ``build_slugs_cmd`` arg vectors
(bool→flag, None/blank→omit, slugs via ``axis_slug``) and the
``WorkflowConfigModel`` per-task accessors + ruamel round-trip (comments,
key order, and value types preserved across save → reload). No Qt required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from population_synthetic.gui_v2.commands import build_per_combo_cmds, build_slugs_cmd
from population_synthetic.gui_v2.workflow_config_model import WorkflowConfigModel

SCRIPT = Path("scripts/analyze/map_populations.py")
COMBOS = [
    ("claude_haiku", "all_pick", "swedish"),
    ("gemini_flash", "free_gen", "norwegian"),
]
OPTIONS = {
    "n": 5,                 # value option → --n 5
    "verbose": True,        # true flag → --verbose
    "no-charts": False,     # false flag → omitted
    "output-base": None,    # None → omitted
    "charts": "",           # blank → omitted
}


# ---------------------------------------------------------------------------
# build_per_combo_cmds
# ---------------------------------------------------------------------------

def test_per_combo_one_vector_per_combo_with_force():
    cmds = build_per_combo_cmds(SCRIPT, COMBOS, OPTIONS, force=True)
    assert len(cmds) == len(COMBOS)
    assert cmds[0] == [
        sys.executable, str(SCRIPT),
        "--model-id", "claude_haiku",
        "--strategy-id", "all_pick",
        "--country-id", "swedish",
        "--force",
        "--n", "5",
        "--verbose",
    ]
    assert cmds[1][2:8] == [
        "--model-id", "gemini_flash",
        "--strategy-id", "free_gen",
        "--country-id", "norwegian",
    ]


def test_per_combo_without_force_omits_flag():
    cmds = build_per_combo_cmds(SCRIPT, COMBOS[:1], OPTIONS, force=False)
    assert "--force" not in cmds[0]


def test_per_combo_falsy_options_omitted():
    (cmd,) = build_per_combo_cmds(SCRIPT, COMBOS[:1], OPTIONS, force=False)
    for absent in ("--no-charts", "--output-base", "--charts"):
        assert absent not in cmd


def test_per_combo_empty_combos_raises():
    with pytest.raises(ValueError, match="no combos"):
        build_per_combo_cmds(SCRIPT, [], OPTIONS, force=False)


# ---------------------------------------------------------------------------
# build_slugs_cmd
# ---------------------------------------------------------------------------

def test_slugs_single_vector_one_slug_per_combo():
    cmd = build_slugs_cmd(SCRIPT, COMBOS, {"no-charts": True, "output-base": None}, force=False)
    # Slug format is {country}_{strategy}_{model} (axis_slug).
    assert cmd == [
        sys.executable, str(SCRIPT),
        "--slug", "swedish_all_pick_claude_haiku",
        "--slug", "norwegian_free_gen_gemini_flash",
        "--no-charts",
    ]
    assert "--force" not in cmd


def test_slugs_with_force_inserts_flag():
    cmd = build_slugs_cmd(SCRIPT, COMBOS, {"no-charts": True}, force=True)
    # --force lands immediately after the script path, before the first --slug.
    assert cmd[:3] == [sys.executable, str(SCRIPT), "--force"]
    assert cmd.index("--force") < cmd.index("--slug")


def test_slugs_empty_combos_raises():
    with pytest.raises(ValueError, match="no combos"):
        build_slugs_cmd(SCRIPT, [], {}, force=False)


# ---------------------------------------------------------------------------
# WorkflowConfigModel — accessors + round-trip
# ---------------------------------------------------------------------------

WORKFLOW_YAML = """\
# Workflow header comment (must survive save).
tasks:
  map_populations:
    label: Map Populations
    script: scripts/analyze/map_populations.py
    dispatch: per_combo
    enabled: true
    supports_force: true          # force checkbox comment
    force: false
    options:
      output-base:                # blank = script default
    depends_on: []

  compare:
    label: Compare
    script: scripts/analyze/score_fidelity_all.py
    dispatch: slugs
    enabled: true
    min_combos: 2
    options:
      no-charts: false
      workers: 4
    depends_on: [map_populations]

selection:
  models:     [claude_haiku]
  strategies: [all_pick]
  countries:  [swedish]
"""


@pytest.fixture
def model(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text(WORKFLOW_YAML, encoding="utf-8")
    return WorkflowConfigModel(path)


def test_task_accessors(model):
    assert model.get_task_names() == ["map_populations", "compare"]
    assert model.is_task_enabled("compare") is True
    assert model.get_task_force("map_populations") is False
    assert model.get_task_options("compare") == {"no-charts": False, "workers": 4}
    assert model.get_task_dependencies("compare") == ["map_populations"]
    assert model.get_task_dependencies("map_populations") == []
    meta = model.get_task_meta("compare")
    assert meta == {
        "label": "Compare",
        "script": "scripts/analyze/score_fidelity_all.py",
        "dispatch": "slugs",
        "supports_force": False,
        "min_combos": 2,
        "max_combos": None,
    }
    assert model.get_task_meta("map_populations")["supports_force"] is True


def test_unknown_task_and_option_raise(model):
    with pytest.raises(KeyError, match="unknown task 'ghost'"):
        model.is_task_enabled("ghost")
    with pytest.raises(KeyError, match="no option 'made-up'"):
        model.set_task_option("compare", "made-up", 1)
    with pytest.raises(KeyError, match="no 'force' key"):
        model.get_task_force("compare")  # compare has no supports_force/force


def test_mutations_mark_dirty(model):
    assert not model.is_dirty
    model.set_task_enabled("compare", False)
    assert model.is_dirty


def test_round_trip_preserves_comments_order_and_types(model):
    model.set_task_enabled("compare", False)
    model.set_task_force("map_populations", True)
    model.set_task_option("compare", "workers", 8)
    model.set_task_option("map_populations", "output-base", "out/mapped")
    model.save()
    assert not model.is_dirty

    text = model.path.read_text(encoding="utf-8")
    assert "# Workflow header comment (must survive save)." in text
    assert "# force checkbox comment" in text
    assert "# blank = script default" in text
    # Key order preserved: map_populations still authored before compare.
    assert text.index("map_populations:") < text.index("compare:")

    reloaded = WorkflowConfigModel(model.path)
    assert reloaded.is_task_enabled("compare") is False
    assert reloaded.get_task_force("map_populations") is True
    options = reloaded.get_task_options("compare")
    assert options["workers"] == 8
    assert type(options["workers"]) is int  # not the string "8"
    assert reloaded.get_task_options("map_populations")["output-base"] == "out/mapped"


def test_to_plain_returns_plain_containers(model):
    plain = model.to_plain()
    assert type(plain) is dict
    assert type(plain["tasks"]) is dict
    assert type(plain["tasks"]["compare"]["depends_on"]) is list
    assert type(plain["tasks"]["compare"]["options"]["workers"]) is int
    assert type(plain["tasks"]["compare"]["enabled"]) is bool
    assert plain["tasks"]["map_populations"]["options"]["output-base"] is None
    assert plain["selection"]["models"] == ["claude_haiku"]


def test_to_plain_feeds_workflow_state(model):
    """A to_plain() snapshot is directly consumable by WorkflowState."""
    from population_synthetic._paths import PROJECT_ROOT
    from population_synthetic.gui_v2.workflow_state import WorkflowState

    state = WorkflowState(model.to_plain(), PROJECT_ROOT)
    state.validate()  # scripts exist in the real repo; DAG is acyclic
    assert [task.name for task in state.ordered_tasks()] == ["map_populations", "compare"]

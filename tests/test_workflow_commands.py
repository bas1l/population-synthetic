"""Headless tests for the gui command builders and WorkflowConfigModel.

Covers the pure ``build_per_combo_cmds`` / ``build_slugs_cmd`` arg vectors
(bool→flag, None/blank→omit, slugs via ``axis_slug``) and the
``WorkflowConfigModel`` per-task accessors + ruamel round-trip (comments,
key order, and value types preserved across save → reload). No Qt required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui.commands import build_per_combo_cmds, build_slugs_cmd
from population_synthetic.gui.workflow_config_model import WorkflowConfigModel

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


def test_per_combo_ollama_host_translates_to_flag_and_value():
    """The GUI's ``ollama-host`` selection reaches the script as ``--ollama-host <id>``.

    The GUI translates the flow YAML into CLI flags — spawned scripts never read
    the flow YAML — so the host id can only reach a run through this vector. The
    builders need no per-option knowledge: a plain string value is enough.
    """
    (cmd,) = build_per_combo_cmds(
        SCRIPT, COMBOS[:1], {"ollama-host": "windows_4070tis"}, force=False
    )
    assert cmd[-2:] == ["--ollama-host", "windows_4070tis"]


def test_generate_flow_yaml_turns_ollama_reconfigure_into_a_bare_flag():
    """The shipped generate flow's ``ollama-reconfigure: true`` reaches the script as a bare flag.

    Read from the real ``config/gui/flows/generate_parallel.yaml`` rather than a
    literal, because the whole feature is switched on by that one YAML key: the
    argparse default is ``False``, so the GUI is the only thing that turns
    reconfiguration on, and a key removed or flipped there silently disables it.
    The builders stay option-agnostic — a ``True`` boolean is all they need.
    """
    flow = yaml.safe_load(
        (PROJECT_ROOT / "config" / "gui" / "flows" / "generate_parallel.yaml").read_text(
            encoding="utf-8"
        )
    )
    options = flow["options"]
    assert options["ollama-reconfigure"] is True

    (cmd,) = build_per_combo_cmds(SCRIPT, COMBOS[:1], options, force=False)
    assert "--ollama-reconfigure" in cmd
    # Bare flag: the next token is another flag (or nothing), never a value.
    tail = cmd[cmd.index("--ollama-reconfigure") + 1:]
    assert not tail or tail[0].startswith("--")


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

# Task keys are canonical analysis-registry ids; label/script/dispatch are
# registry-owned and NOT authored in the flow YAML (get_task_meta resolves them).
WORKFLOW_YAML = """\
# Workflow header comment (must survive save).
tasks:
  mapping:
    enabled: true
    bypass: false                 # assume already done -> unlock dependents, run nothing
    supports_force: true          # force checkbox comment
    force: false
    options:
      output-base:                # blank = script default
    depends_on: []

  fidelity:
    enabled: true
    bypass: false
    min_combos: 2
    options:
      no-charts: false
      workers: 4
    depends_on: [mapping]

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
    from population_synthetic.analysis.utils.registry import get_process

    assert model.get_task_names() == ["mapping", "fidelity"]
    assert model.is_task_enabled("fidelity") is True
    assert model.get_task_force("mapping") is False
    assert model.get_task_bypass("mapping") is False
    assert model.get_task_bypass("fidelity") is False
    assert model.get_task_options("fidelity") == {"no-charts": False, "workers": 4}
    assert model.get_task_dependencies("fidelity") == ["mapping"]
    assert model.get_task_dependencies("mapping") == []
    # label/description/script/dispatch are registry-owned; GUI orchestration
    # fields (supports_force/min_combos/max_combos) come from the flow YAML.
    proc = get_process("fidelity")
    assert model.get_task_meta("fidelity") == {
        "label": proc.label,
        "description": proc.description,
        "script": proc.script,
        "dispatch": proc.dispatch,
        "supports_force": False,
        "min_combos": 2,
        "max_combos": None,
    }
    assert model.get_task_meta("mapping")["supports_force"] is True


def test_get_task_meta_unregistered_task_raises(tmp_path):
    """A flow task id absent from the registry fails loudly (config error)."""
    path = tmp_path / "bad.yaml"
    path.write_text(
        "tasks:\n"
        "  not_a_process:\n"
        "    enabled: true\n"
        "    options: {}\n"
        "    depends_on: []\n"
        "selection:\n"
        "  models: [claude_haiku]\n"
        "  strategies: [all_pick]\n"
        "  countries: [swedish]\n",
        encoding="utf-8",
    )
    model = WorkflowConfigModel(path)
    with pytest.raises(KeyError, match="not a registered analysis process id"):
        model.get_task_meta("not_a_process")


def test_unknown_task_and_option_raise(model):
    with pytest.raises(KeyError, match="unknown task 'ghost'"):
        model.is_task_enabled("ghost")
    with pytest.raises(KeyError, match="no option 'made-up'"):
        model.set_task_option("fidelity", "made-up", 1)
    with pytest.raises(KeyError, match="no 'force' key"):
        model.get_task_force("fidelity")  # fidelity has no supports_force/force


def test_mutations_mark_dirty(model):
    assert not model.is_dirty
    model.set_task_enabled("fidelity", False)
    assert model.is_dirty


def test_round_trip_preserves_comments_order_and_types(model):
    model.set_task_enabled("fidelity", False)
    model.set_task_force("mapping", True)
    model.set_task_bypass("fidelity", True)
    model.set_task_option("fidelity", "workers", 8)
    model.set_task_option("mapping", "output-base", "out/mapped")
    model.save()
    assert not model.is_dirty

    text = model.path.read_text(encoding="utf-8")
    assert "# Workflow header comment (must survive save)." in text
    assert "# force checkbox comment" in text
    assert "# assume already done -> unlock dependents, run nothing" in text
    assert "# blank = script default" in text
    # Key order preserved: mapping still authored before fidelity.
    assert text.index("mapping:") < text.index("fidelity:")

    reloaded = WorkflowConfigModel(model.path)
    assert reloaded.is_task_enabled("fidelity") is False
    assert reloaded.get_task_force("mapping") is True
    assert reloaded.get_task_bypass("fidelity") is True
    options = reloaded.get_task_options("fidelity")
    assert options["workers"] == 8
    assert type(options["workers"]) is int  # not the string "8"
    assert reloaded.get_task_options("mapping")["output-base"] == "out/mapped"


def test_to_plain_returns_plain_containers(model):
    plain = model.to_plain()
    assert type(plain) is dict
    assert type(plain["tasks"]) is dict
    assert type(plain["tasks"]["fidelity"]["depends_on"]) is list
    assert type(plain["tasks"]["fidelity"]["options"]["workers"]) is int
    assert type(plain["tasks"]["fidelity"]["enabled"]) is bool
    assert plain["tasks"]["mapping"]["options"]["output-base"] is None
    assert plain["selection"]["models"] == ["claude_haiku"]
    # to_plain enriches each task with the registry-owned label/script/dispatch.
    assert plain["tasks"]["fidelity"]["script"] == "scripts/analyze/score_fidelity_all.py"
    assert plain["tasks"]["fidelity"]["dispatch"] == "slugs"


def test_to_plain_feeds_workflow_state(model):
    """A to_plain() snapshot is directly consumable by WorkflowState."""
    from population_synthetic._paths import PROJECT_ROOT
    from population_synthetic.gui.workflow_state import WorkflowState

    state = WorkflowState(model.to_plain(), PROJECT_ROOT)
    state.validate()  # scripts exist in the real repo; DAG is acyclic
    assert [task.name for task in state.ordered_tasks()] == ["mapping", "fidelity"]

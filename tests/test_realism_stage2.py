"""Stage 2 of the persona-realism judge: classification contract, cache/resume, CSVs, config."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.persona_realism import stage2
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.judge import Issue, RoundVerdict
from population_synthetic.analysis.persona_realism.reduce import LoadedPersona
from population_synthetic.analysis.utils.realism_stage2_csv import (
    NOT_APPLICABLE,
    UNCLASSIFIED,
    Stage2IssueRow,
    persona_class,
    persona_rows_from_issues,
    read_stage2_issues_csv,
    reconcile_with_clashes,
    write_stage2_issues_csv,
)

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"
_ORDER = ("raw_impossible", "label_clash", "ambiguous", "mapping_error", "judge_error")
_ATTRS = ["age_group", "employment_status", "employment_type", "income_source"]
_SEL = ["persona_00001"]  # the selected roster the fixtures persona belongs to


# --------------------------------------------------------------------------- #
# persona class                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("classes", "want"),
    [
        (["judge_error", "label_clash"], "label_clash"),
        (["mapping_error", "ambiguous"], "ambiguous"),
        (["raw_impossible", UNCLASSIFIED], "raw_impossible"),  # a classified top issue settles it
        (["label_clash", UNCLASSIFIED], UNCLASSIFIED),          # the unclassified one could outrank it
        ([NOT_APPLICABLE, NOT_APPLICABLE], NOT_APPLICABLE),
    ],
)
def test_persona_class_rules(classes, want):
    assert persona_class(classes, _ORDER) == want


def test_persona_class_refuses_free_text_mix():
    with pytest.raises(ValueError, match="cannot both have and lack free text"):
        persona_class([NOT_APPLICABLE, "label_clash"], _ORDER)


# --------------------------------------------------------------------------- #
# response contract                                                            #
# --------------------------------------------------------------------------- #


def _response(*issues, persona_class_="label_clash"):
    return json.dumps({"issues": list(issues), "persona_class": persona_class_})


def _issue(a, b, cls="label_clash", misread=None, legal=None):
    return {"attributes": [a, b], "class": cls, "misread_attribute": misread, "legal_fact": legal,
            "raw_quotes": {a: "x"}, "reason": "one sentence"}


def test_parse_returns_issues_in_expected_order_and_tolerates_a_fence():
    raw = "```json\n" + _response(_issue("income_source", "employment_status"),
                                  _issue("employment_type", "employment_status", "ambiguous")) + "\n```"
    out = stage2.parse_stage2_response(raw, [("employment_status", "employment_type"),
                                             ("employment_status", "income_source")])
    assert [o["class"] for o in out] == ["ambiguous", "label_clash"]
    assert out[1]["pair"] == ["employment_status", "income_source"]


@pytest.mark.parametrize(
    ("issues", "match"),
    [
        ([_issue("a", "b")], "expected exactly the stage-1 S3 pairs"),
        ([_issue("employment_status", "employment_type", "nonsense")], "not one of"),
        ([_issue("employment_status", "employment_type", "mapping_error")], "misread_attribute"),
    ],
)
def test_parse_rejects_off_contract_answers(issues, match):
    with pytest.raises(ValueError, match=match):
        stage2.parse_stage2_response(_response(*issues), [("employment_status", "employment_type")])


# --------------------------------------------------------------------------- #
# fan-out, cache, resume, force                                                #
# --------------------------------------------------------------------------- #


class _StubClient:
    def __init__(self, answers):
        self.answers = answers
        self.calls = 0
        self.last_metadata = {}

    def generate_content(self, user_str, **_):
        from population_synthetic.analysis.persona_realism.runner import JUDGE_CONTEXT_ISOLATION

        self.calls += 1
        self.last_metadata = {"context_isolation": JUDGE_CONTEXT_ISOLATION, "model": "stub",
                              "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        return self.answers(user_str)


def _persona(pid="persona_00001", explanation="Retired cannot hold a contract"):
    rounds = (
        RoundVerdict(can_exist=False, typicality=None, issues=(
            Issue(("employment_type", "employment_status"), "S3", explanation),
            Issue(("age_group", "income_source"), "S1", "unusual"),
        )),
    )
    attributes = {"age_group": "65-74", "employment_status": "Retired",
                  "employment_type": "Permanent Full-time", "income_source": "Pension"}
    return LoadedPersona(persona_id=pid, attributes=attributes, rounds=rounds, failed_rounds=0,
                         context_isolation="fresh_process_per_call_v1",
                         prompt_template_sha256="p", persona_rendering_sha256="r")


@pytest.fixture()
def cfg():
    return dataclasses.replace(JudgeConfig.load(_CONFIG_DIR), workers=2)


def _raw(_pid):
    return {"age": 70, "employment_status": "Retired", "employment_type": "former permanent full-time",
            "income_source": "Pension"}


def _answer(_user):
    return _response(_issue("employment_status", "employment_type", "mapping_error", "employment_type"))


def test_run_writes_cache_resumes_and_force_reclassifies(tmp_path, cfg):
    client = _StubClient(_answer)
    persona = _persona()
    s = stage2.run_combo_stage2([persona], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                                client_factory=lambda: client)
    assert (s.classified, s.skipped, s.failed, client.calls) == (1, 0, 0, 1)
    cache = json.loads((tmp_path / "stage2" / "persona_00001.json").read_text(encoding="utf-8"))
    assert cache["rounds"][0]["issues"][0]["class"] == "mapping_error"
    assert (tmp_path / "stage2" / "persona_00001.jsonl").is_file()
    # resume: nothing to do
    s = stage2.run_combo_stage2([persona], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                                client_factory=lambda: client)
    assert (s.classified, s.skipped, client.calls) == (0, 1, 1)
    # the rows carry the cached class and the raw answers read from identity
    rows = stage2.stage2_issue_rows([persona], tmp_path, raw_identity=_raw, enabled=True)
    assert [(r.stage2_class, r.misread_attribute, r.raw_b) for r in rows] == [
        ("mapping_error", "employment_type", "former permanent full-time")]
    # force classifies again from scratch
    s = stage2.run_combo_stage2([persona], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                                force=True, client_factory=lambda: client)
    assert (s.classified, client.calls) == (1, 2)


def test_a_changed_stage1_verdict_is_refused_on_resume(tmp_path, cfg):
    client = _StubClient(_answer)
    stage2.run_combo_stage2([_persona()], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                            client_factory=lambda: client)
    changed = _persona(explanation="a different stage-1 verdict")
    with pytest.raises(ValueError, match="--force"):
        stage2.run_combo_stage2([changed], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                                client_factory=lambda: client)


def test_a_failed_call_stays_uncached_and_reads_as_unclassified(tmp_path, cfg):
    client = _StubClient(lambda _u: "not json")
    s = stage2.run_combo_stage2([_persona()], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=_raw,
                                client_factory=lambda: client)
    assert (s.classified, s.failed, client.calls) == (0, 1, 3)
    assert not (tmp_path / "stage2" / "persona_00001.json").exists()
    rows = stage2.stage2_issue_rows([_persona()], tmp_path, raw_identity=_raw, enabled=True)
    assert [r.stage2_class for r in rows] == [UNCLASSIFIED]


def test_no_free_text_makes_no_call_and_is_not_applicable(tmp_path, cfg):
    client = _StubClient(_answer)
    s = stage2.run_combo_stage2([_persona()], "real", _ATTRS, tmp_path, cfg, selected_ids=_SEL, raw_identity=None,
                                client_factory=lambda: client)
    assert (s.not_applicable, client.calls) == (1, 0)
    rows = stage2.stage2_issue_rows([_persona()], tmp_path, raw_identity=None, enabled=True)
    assert [(r.stage2_class, r.raw_a) for r in rows] == [(NOT_APPLICABLE, "")]


def test_rendered_block_shows_raw_mapped_and_s3_issues_only(cfg):
    persona = _persona()
    block = stage2.render_stage2_block(_raw("x"), persona, _ATTRS, stage2.s3_rounds(persona)[0],
                                       rendering=cfg.persona_rendering)
    assert "employment_type: former permanent full-time" in block
    assert "employment_type: Permanent Full-time" in block
    assert "1. attributes: employment_status x employment_type" in block
    assert "unusual" not in block  # S1 issues are not stage-2 input


# --------------------------------------------------------------------------- #
# CSV contract                                                                 #
# --------------------------------------------------------------------------- #


def _row(pid="persona_00001", rnd=0, cls="label_clash"):
    return Stage2IssueRow(pid, rnd, "employment_status", "employment_type", cls, "", "", "r", "a", "b", "{}")


def test_issue_csv_round_trips_and_folds_to_personas(tmp_path):
    rows = [_row(), _row("persona_00002", cls="raw_impossible")]
    path = write_stage2_issues_csv(rows, tmp_path / "x_stage2.csv")
    assert read_stage2_issues_csv(path) == sorted(rows, key=lambda r: r.persona_id)
    folded = persona_rows_from_issues(rows, _ORDER)
    assert [(p.persona_id, p.persona_class) for p in folded] == [
        ("persona_00001", "label_clash"), ("persona_00002", "raw_impossible")]


def test_reconcile_raises_on_a_different_clash_set():
    reconcile_with_clashes([_row()], [("persona_00001", 0, "employment_status", "employment_type")], label="t")
    with pytest.raises(ValueError, match="different clashes"):
        reconcile_with_clashes([_row()], [("persona_00009", 0, "employment_status", "employment_type")],
                               label="t")


# --------------------------------------------------------------------------- #
# config                                                                       #
# --------------------------------------------------------------------------- #


def _copy_config(tmp_path: Path, mutate) -> Path:
    for name in ("judge.yaml", "judge_prompt.md", "hard_rules.yaml", "stage2_prompt.md"):
        (tmp_path / name).write_bytes((_CONFIG_DIR / name).read_bytes())
    data = yaml.safe_load((tmp_path / "judge.yaml").read_text(encoding="utf-8"))
    data["persona_rendering"]["mapping_tier"] = str(PROJECT_ROOT / "config" / "mapping" / "scb_native")
    mutate(data)
    (tmp_path / "judge.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return tmp_path


def test_real_config_loads_stage2():
    cfg = JudgeConfig.load(_CONFIG_DIR)
    assert cfg.stage2_enabled is True
    assert cfg.stage2_persona_class_order == _ORDER
    assert Path(cfg.stage2_prompt_template).name == "stage2_prompt.md"


def test_config_without_stage2_block_raises(tmp_path):
    with pytest.raises(ValueError, match="stage2"):
        JudgeConfig.load(_copy_config(tmp_path, lambda d: d.pop("stage2")))


def test_config_order_disagreeing_with_the_prompt_raises(tmp_path):
    def swap(d):
        d["stage2"]["persona_class_order"] = ["label_clash", "raw_impossible", "ambiguous",
                                              "mapping_error", "judge_error"]
    with pytest.raises(ValueError, match="does not state the configured persona-class order"):
        JudgeConfig.load(_copy_config(tmp_path, swap))


# --------------------------------------------------------------------------- #
# the roster: stage 2 classifies the capped selection only                     #
# --------------------------------------------------------------------------- #


def test_a_persona_outside_the_roster_is_refused(tmp_path, cfg):
    """Stage 2 is handed the selected personas only; a leftover reaching it is a caller bug."""
    client = _StubClient(_answer)
    with pytest.raises(ValueError, match="outside the selected roster"):
        stage2.run_combo_stage2([_persona(), _persona("persona_00099")], "combo", _ATTRS, tmp_path, cfg,
                                selected_ids=_SEL, raw_identity=_raw, client_factory=lambda: client)
    assert client.calls == 0


def test_force_clears_the_selected_personas_files_only(tmp_path, cfg):
    """--force re-classifies the selection; a leftover's stage-2 files are kept, never deleted."""
    client = _StubClient(_answer)
    s2_dir = tmp_path / "stage2"
    s2_dir.mkdir()
    leftover = {s2_dir / "persona_00099.json": '{"stage2_prompt_sha256": "other", "rounds": []}',
                s2_dir / "persona_00099.jsonl": ""}
    for path, text in leftover.items():
        path.write_text(text, encoding="utf-8")
    stage2.run_combo_stage2([_persona()], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL,
                            raw_identity=_raw, client_factory=lambda: client)
    s = stage2.run_combo_stage2([_persona()], "combo", _ATTRS, tmp_path, cfg, selected_ids=_SEL,
                                raw_identity=_raw, force=True, client_factory=lambda: client)
    assert (s.classified, client.calls) == (1, 2)
    assert {path: path.read_text(encoding="utf-8") for path in leftover} == leftover

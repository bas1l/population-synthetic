"""Judge-facing category rendering (``judge.yaml`` ``persona_rendering``).

Covers the three guarantees the rendering makes:

* it changes **only** the persona lines the judge reads -- the persona dict, the
  verdict cache's ``attributes`` and everything derived from them stay canonical;
* the loader fails loudly unless each rendered attribute covers exactly its mapping
  tier's canonical categories with distinct, non-empty labels;
* the map enters the prompt identity stamped into every verdict cache and report, so
  a cache judged under another rendering is refused on resume.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.model_ranking.loader import scheme_attributes
from population_synthetic.analysis.persona_realism import prompt
from population_synthetic.analysis.persona_realism.config import (
    PROMPT_IDENTITY_KEYS,
    JudgeConfig,
    persona_rendering_sha256,
)
from population_synthetic.analysis.persona_realism.runner import (
    JUDGE_CONTEXT_ISOLATION,
    run_combo_judgements,
)
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"
_TIER_DIR = PROJECT_ROOT / "config" / "mapping" / "scb_native"
_PHD = "Post-Graduate (ISCED 6)"


def _education_values() -> list[str]:
    return json.loads((_TIER_DIR / "education.json").read_text(encoding="utf-8"))["values"]


def _config_copy(tmp_path: Path, mutate) -> Path:
    """Copy the shipped judge config into *tmp_path*, apply *mutate* to the parsed YAML.

    The mapping tier is re-anchored on the repository (it is relative to the config
    directory), so only the mutation under test differs from the shipped file.
    """
    data = yaml.safe_load((_CONFIG_DIR / "judge.yaml").read_text(encoding="utf-8"))
    data["persona_rendering"]["mapping_tier"] = _TIER_DIR.as_posix()
    mutate(data)
    (tmp_path / "judge.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (tmp_path / "judge_prompt.md").write_text(
        (_CONFIG_DIR / "judge_prompt.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# the shipped config                                                           #
# --------------------------------------------------------------------------- #


def test_shipped_rendering_covers_exactly_the_canonical_education_categories():
    cfg = JudgeConfig.load(_CONFIG_DIR)
    assert set(cfg.persona_rendering) == {"education_level"}
    assert set(cfg.persona_rendering["education_level"]) == set(_education_values())
    assert "Research degree" in cfg.persona_rendering["education_level"][_PHD]


# --------------------------------------------------------------------------- #
# rendering is applied to the prompt only                                      #
# --------------------------------------------------------------------------- #


def test_rendering_reaches_the_prompt_and_leaves_the_persona_untouched():
    cfg = JudgeConfig.load(_CONFIG_DIR)
    persona = {"age_group": "25-34", "education_level": _PHD}
    snapshot = dict(persona)
    _, user = prompt.build_prompts(
        persona, ["age_group", "education_level"], "SYS", "P: {persona_block}",
        rendering=cfg.persona_rendering,
    )
    assert f"education_level: {cfg.persona_rendering['education_level'][_PHD]}" in user
    assert _PHD not in user
    assert persona == snapshot


def test_unrendered_attributes_and_unmapped_values_pass_through():
    rendering = {"education_level": {_PHD: "Research degree"}}
    block = prompt.render_persona_block(
        {"age_group": "25-34", "education_level": UNMAPPED}, ["age_group", "education_level"],
        rendering=rendering,
    )
    assert block == f"age_group: 25-34\neducation_level: {UNMAPPED}"


def test_a_value_outside_the_rendering_raises():
    with pytest.raises(ValueError, match="no judge-facing rendering"):
        prompt.render_persona_block(
            {"education_level": "Doctorate"}, ["education_level"],
            rendering={"education_level": {_PHD: "Research degree"}},
        )


# --------------------------------------------------------------------------- #
# the loader fails loudly                                                      #
# --------------------------------------------------------------------------- #


def test_loader_accepts_the_unmodified_copy(tmp_path):
    cfg = JudgeConfig.load(_config_copy(tmp_path, lambda data: None))
    assert cfg.persona_rendering == JudgeConfig.load(_CONFIG_DIR).persona_rendering


def test_loader_raises_on_a_missing_canonical_category(tmp_path):
    def drop(data):
        del data["persona_rendering"]["labels"]["education_level"]["Unknown / Not reported"]
    with pytest.raises(ValueError, match="missing \\['Unknown / Not reported'\\]"):
        JudgeConfig.load(_config_copy(tmp_path, drop))


def test_loader_raises_on_a_non_canonical_key(tmp_path):
    def add(data):
        data["persona_rendering"]["labels"]["education_level"]["Doctorate"] = "Doctorate"
    with pytest.raises(ValueError, match="not canonical \\['Doctorate'\\]"):
        JudgeConfig.load(_config_copy(tmp_path, add))


def test_loader_raises_on_a_shared_label(tmp_path):
    def merge(data):
        labels = data["persona_rendering"]["labels"]["education_level"]
        labels["Post-Secondary 3+ yrs (ISCED 5A)"] = labels[_PHD]
    with pytest.raises(ValueError, match="same label"):
        JudgeConfig.load(_config_copy(tmp_path, merge))


def test_loader_raises_on_an_empty_label(tmp_path):
    def blank(data):
        data["persona_rendering"]["labels"]["education_level"][_PHD] = "  "
    with pytest.raises(ValueError, match="empty label"):
        JudgeConfig.load(_config_copy(tmp_path, blank))


def test_loader_raises_on_an_attribute_the_tier_does_not_declare(tmp_path):
    def foreign(data):
        data["persona_rendering"]["labels"]["shoe_size"] = {"42": "forty-two"}
    with pytest.raises(ValueError, match="shoe_size"):
        JudgeConfig.load(_config_copy(tmp_path, foreign))


def test_loader_raises_when_the_block_is_absent(tmp_path):
    with pytest.raises(ValueError, match="persona_rendering"):
        JudgeConfig.load(_config_copy(tmp_path, lambda data: data.pop("persona_rendering")))


# --------------------------------------------------------------------------- #
# provenance: the map is part of the prompt identity                           #
# --------------------------------------------------------------------------- #


def test_rendering_hash_changes_with_the_map_and_ignores_key_order():
    cfg = JudgeConfig.load(_CONFIG_DIR)
    labels = cfg.persona_rendering["education_level"]
    reordered = {"education_level": dict(reversed(list(labels.items())))}
    assert persona_rendering_sha256(reordered) == persona_rendering_sha256(cfg.persona_rendering)

    edited = dataclasses.replace(
        cfg, persona_rendering={"education_level": {**labels, _PHD: "Doctorate"}},
    )
    before, after = cfg.prompt_identity(), edited.prompt_identity()
    assert set(before) == set(PROMPT_IDENTITY_KEYS)
    assert before["prompt_template_sha256"] == after["prompt_template_sha256"]
    assert before["persona_rendering_sha256"] != after["persona_rendering_sha256"]


class _Client:
    """A judge stub that records the user prompts it was shown."""

    def __init__(self, seen: list[str]) -> None:
        self._seen = seen
        self.last_metadata: dict[str, object] = {}

    def generate_content(self, user: str, *, model: str, system_instruction: str) -> str:
        self._seen.append(user)
        self.last_metadata = {
            "provider": "stub", "model": model, "prompt_tokens": 1, "completion_tokens": 1,
            "total_tokens": 2, "elapsed_ms": 1, "context_isolation": JUDGE_CONTEXT_ISOLATION,
        }
        return json.dumps({"can_exist": True, "typicality": 5, "issues": [], "reasoning": ""})


def _population(attrs: list[str]) -> list[dict]:
    real_values = {
        "age_group": "25-34", "education_level": _PHD, "employment_status": "Employed",
    }
    return [{"id": "persona_00000", **{a: real_values.get(a, f"val_{i}") for i, a in enumerate(attrs)}}]


def test_runner_renders_the_prompt_stores_canonical_values_and_stamps_the_identity(tmp_path):
    cfg = dataclasses.replace(JudgeConfig.load(_CONFIG_DIR), n_rounds=1, workers=1)
    attrs = scheme_attributes("swedish")
    seen: list[str] = []
    run_combo_judgements(_population(attrs), "combo", attrs, tmp_path, cfg,
                         client_factory=lambda: _Client(seen))

    assert cfg.persona_rendering["education_level"][_PHD] in seen[0]
    cache = json.loads((tmp_path / "persona_00000.json").read_text(encoding="utf-8"))
    assert cache["attributes"]["education_level"] == _PHD
    for key, value in cfg.prompt_identity().items():
        assert cache[key] == value


def test_resume_refuses_a_cache_judged_under_another_rendering(tmp_path):
    cfg = dataclasses.replace(JudgeConfig.load(_CONFIG_DIR), n_rounds=1, workers=1)
    attrs = scheme_attributes("swedish")
    population = _population(attrs)
    run_combo_judgements(population, "combo", attrs, tmp_path, cfg, client_factory=lambda: _Client([]))

    labels = cfg.persona_rendering["education_level"]
    edited = dataclasses.replace(
        cfg, n_rounds=2, persona_rendering={"education_level": {**labels, _PHD: "Doctorate"}},
    )
    with pytest.raises(ValueError, match="different prompt"):
        run_combo_judgements(population, "combo", attrs, tmp_path, edited,
                             client_factory=lambda: _Client([]))

    # The same config tops the cache up (round 1 kept, round 2 added) ...
    deeper = dataclasses.replace(cfg, n_rounds=2)
    summary = run_combo_judgements(population, "combo", attrs, tmp_path, deeper,
                                   client_factory=lambda: _Client([]))
    assert summary.topped_up == 1
    # ... and --force re-judges under the new rendering from scratch.
    run_combo_judgements(population, "combo", attrs, tmp_path, edited, force=True,
                         client_factory=lambda: _Client([]))
    cache = json.loads((tmp_path / "persona_00000.json").read_text(encoding="utf-8"))
    assert cache["persona_rendering_sha256"] == edited.prompt_identity()["persona_rendering_sha256"]

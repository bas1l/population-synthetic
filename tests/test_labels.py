"""Tests for the config-driven label resolver.

Two things are asserted here, and they fail for different reasons.

The first is that the *convention* holds over the real config: every model, strategy,
country and attribute the repository declares resolves to a display string, none of
them contains an underscore, and no model's display name carries its serving provider.
Those tests read the checked-in config, so they fail when config drifts -- which is the
point, since the alternative is discovering it on a proof.

The second is that a **miss is loud**. An unknown id, a missing ``display:`` block, an
empty ``label:`` and an underscored label each raise, and the resolve path contains no
``.get(id, id)`` -- the fallback that would turn every one of those failures into a
published figure with a raw id on its axis.

The method-letter tests build a throwaway strategy axis under ``tmp_path`` rather than
asserting against the live one, because the property under test is that the letters are
*derived* from ``_families.yaml`` at call time: proving it requires a family index that
can be reordered, which the checked-in one must not be.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils import labels
from population_synthetic.analysis.utils.labels import (
    METHOD_LETTERS,
    PROVENANCE_COLUMNS,
    UnknownAxisValue,
    attribute_label,
    country_label,
    discover_model_ids,
    method_key_lines,
    method_letters,
    model_label,
    model_provenance_rows,
    strategy_label,
)

MODELS_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "models"
STRATEGIES_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies"
COUNTRIES_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "countries"
MAPPING_DIR = PROJECT_ROOT / "config" / "mapping"

# The serving-layer tokens that must never appear in a display string. `claude_` carries
# its underscore deliberately: "Claude" is also a model *maker*, so the bare word is
# legitimate on a figure and only the identifier form is not.
PROVIDER_TOKENS = ("openrouter", "ollama", "claude_", "gemini_", "openai_compat")


def _selectable(directory: Path) -> list[str]:
    """The axis ids in *directory*, skipping the `_`-prefixed index/scratch files."""
    return sorted(p.stem for p in directory.glob("*.yaml") if not p.name.startswith("_"))


# ------------------------------------------------------------------
# The live config resolves
# ------------------------------------------------------------------


def test_model_label_drops_the_serving_provider() -> None:
    assert model_label("openrouter_kimi_k3") == "Kimi K3"
    assert model_label("ollama_lucie_7b") == "Lucie 7B Instruct"
    assert model_label("claude_sonnet") == "Claude Sonnet"


@pytest.mark.parametrize("model_id", _selectable(MODELS_DIR))
def test_every_model_resolves_to_a_clean_display_name(model_id: str) -> None:
    name = model_label(model_id)
    assert name and name == name.strip()
    assert "_" not in name
    lowered = name.lower()
    assert not any(token in lowered for token in PROVIDER_TOKENS), name


def test_model_display_names_are_unique() -> None:
    names = [model_label(model_id) for model_id in _selectable(MODELS_DIR)]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"two model axes would render identically: {duplicates}"


def test_model_label_and_axis_label_agree() -> None:
    """`display.name` must be `label:` with only the provider dropped."""
    for model_id in _selectable(MODELS_DIR):
        raw = yaml.safe_load((MODELS_DIR / f"{model_id}.yaml").read_text(encoding="utf-8"))
        assert raw["label"].endswith(model_label(model_id))


@pytest.mark.parametrize("strategy_id", _selectable(STRATEGIES_DIR))
def test_every_strategy_resolves(strategy_id: str) -> None:
    label = strategy_label(strategy_id)
    assert label and "_" not in label


@pytest.mark.parametrize("country_id", _selectable(COUNTRIES_DIR))
def test_every_country_resolves(country_id: str) -> None:
    label = country_label(country_id)
    assert label and "_" not in label


def test_attribute_label_is_sentence_case_prose() -> None:
    assert attribute_label("housing_tenure") == "Housing tenure"
    assert attribute_label("age_group") == "Age group"
    assert attribute_label("birth_country_detail") == "Birth country"


def test_every_mapped_attribute_of_every_tier_has_a_label() -> None:
    """No tier may declare an attribute the figures cannot name."""
    indexes = sorted(MAPPING_DIR.glob("*/_index.json"))
    assert indexes, f"no mapping tiers found under {MAPPING_DIR}"
    for index in indexes:
        for attribute in json.loads(index.read_text(encoding="utf-8"))["attributes"]:
            label = attribute_label(attribute)
            assert label and "_" not in label, (index, attribute)


# ------------------------------------------------------------------
# A miss is loud
# ------------------------------------------------------------------


def test_unknown_model_raises_naming_the_id_and_the_file() -> None:
    with pytest.raises(UnknownAxisValue) as excinfo:
        model_label("openrouter_kimi_k9")
    message = str(excinfo.value)
    assert "openrouter_kimi_k9" in message
    assert "openrouter_kimi_k9.yaml" in message


@pytest.mark.parametrize(
    "resolver, bad_id",
    [
        (strategy_label, "all_pick_dag_v9"),
        (country_label, "atlantean"),
        (attribute_label, "favourite_colour"),
    ],
)
def test_unknown_axis_value_raises_for_every_resolver(resolver, bad_id: str) -> None:
    with pytest.raises(UnknownAxisValue) as excinfo:
        resolver(bad_id)
    assert bad_id in str(excinfo.value)


def test_unknown_axis_value_is_a_value_error() -> None:
    """Callers catching the general malformed-config case still catch this one."""
    assert issubclass(UnknownAxisValue, ValueError)


def test_resolve_path_has_no_identity_fallback() -> None:
    """`.get(x, x)` anywhere in this module would silently publish a raw id.

    Parsed rather than grepped, so the module may *name* the banned pattern in its own
    docstring -- which it does, to say why it is banned -- without tripping the check.
    """
    tree = ast.parse(Path(labels.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get" or len(node.args) != 2:
            continue
        first, second = node.args
        identical = (
            isinstance(first, ast.Name) and isinstance(second, ast.Name) and first.id == second.id
        )
        assert not identical, f"identity fallback at {labels.__file__}:{node.lineno}"


def _write_model(directory: Path, model_id: str, body: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{model_id}.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


def test_model_without_display_block_raises(tmp_path: Path) -> None:
    _write_model(tmp_path, "m", {"id": "m", "label": "M", "model_config": {"provider": "claude", "model": "m"}})
    with pytest.raises(ValueError, match="display"):
        model_label("m", models_dir=tmp_path)


def test_model_with_empty_display_name_raises(tmp_path: Path) -> None:
    _write_model(tmp_path, "m", {"id": "m", "label": "M", "display": {"name": "   "}})
    with pytest.raises(ValueError, match="non-empty"):
        model_label("m", models_dir=tmp_path)


def test_model_display_name_disagreeing_with_label_raises(tmp_path: Path) -> None:
    _write_model(tmp_path, "m", {"id": "m", "label": "OpenRouter Kimi K3", "display": {"name": "Kimi K2"}})
    with pytest.raises(ValueError, match="do not agree"):
        model_label("m", models_dir=tmp_path)


def test_empty_strategy_label_raises(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text('id: "s"\nfamily: "f"\nversion: 1\nlabel: ""\n', encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        strategy_label("s", strategies_dir=tmp_path)


def test_underscored_label_raises(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text('id: "s"\nlabel: "all_pick"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="underscore"):
        strategy_label("s", strategies_dir=tmp_path)


def test_empty_attribute_label_raises(tmp_path: Path) -> None:
    path = tmp_path / "attribute_labels.yaml"
    path.write_text(yaml.safe_dump({"labels": {"region": ""}}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        attribute_label("region", labels_path=path)


# ------------------------------------------------------------------
# The method letters
# ------------------------------------------------------------------


def _strategy_axis(directory: Path, families: list[tuple[str, str]], strategies: list[tuple[str, str, int]]) -> Path:
    """Build a throwaway strategy axis: *families* as (id, label), *strategies* as (id, family, version)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "_families.yaml").write_text(
        yaml.safe_dump({"families": [{"id": fid, "label": label} for fid, label in families]}),
        encoding="utf-8",
    )
    for strategy_id, family, version in strategies:
        (directory / f"{strategy_id}.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": strategy_id,
                    "family": family,
                    "version": version,
                    "label": f"{family.replace('_', ' ').title()} v{version}",
                }
            ),
            encoding="utf-8",
        )
    return directory


FAMILIES = [("f_one", "Alpha"), ("f_two", "Beta"), ("f_three", "Gamma")]
STRATEGIES = [("s_one", "f_one", 1), ("s_two", "f_two", 1), ("s_two_v2", "f_two", 2), ("s_three", "f_three", 1)]


def test_letters_follow_the_family_index_order(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    assert method_letters(["s_three", "s_one", "s_two"], strategies_dir=axis) == {
        "s_one": "A",
        "s_two": "B",
        "s_three": "C",
    }


def test_reordering_the_family_index_reorders_the_letters(tmp_path: Path) -> None:
    """The letter is derived from `_families.yaml` at call time, never stored."""
    axis = _strategy_axis(tmp_path / "axis", list(reversed(FAMILIES)), STRATEGIES)
    assert method_letters(["s_one", "s_two", "s_three"], strategies_dir=axis) == {
        "s_three": "A",
        "s_two": "B",
        "s_one": "C",
    }


def test_letters_are_absolute_not_dense(tmp_path: Path) -> None:
    """A figure omitting a family keeps the remaining families on their own letters."""
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    assert method_letters(["s_one", "s_three"], strategies_dir=axis) == {"s_one": "A", "s_three": "C"}


def test_single_version_set_yields_bare_letters(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    assert method_letters(["s_two_v2"], strategies_dir=axis) == {"s_two_v2": "B"}


def test_mixed_version_set_yields_marked_letters(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    letters = method_letters(["s_one", "s_two", "s_two_v2"], strategies_dir=axis)
    assert letters == {"s_one": "A", "s_two": "B1", "s_two_v2": "B2"}


def test_letters_come_back_simplest_first(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    letters = method_letters(["s_three", "s_two_v2", "s_two", "s_one"], strategies_dir=axis)
    assert list(letters.values()) == ["A", "B1", "B2", "C"]


def test_key_lines_pair_each_letter_with_its_family_phrase(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    assert method_key_lines(["s_one", "s_two", "s_two_v2"], strategies_dir=axis) == [
        "A — Alpha",
        "B1 — Beta (v1)",
        "B2 — Beta (v2)",
    ]


def test_key_lines_carry_no_underscore(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    assert all("_" not in line for line in method_key_lines(["s_one", "s_two"], strategies_dir=axis))


def test_unknown_strategy_in_a_method_axis_raises(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", FAMILIES, STRATEGIES)
    with pytest.raises(ValueError, match="s_missing"):
        method_letters(["s_one", "s_missing"], strategies_dir=axis)


def test_empty_family_label_raises(tmp_path: Path) -> None:
    axis = _strategy_axis(tmp_path / "axis", [("f_one", "Alpha"), ("f_two", "")], STRATEGIES[:2])
    with pytest.raises(ValueError, match="non-empty"):
        method_key_lines(["s_one", "s_two"], strategies_dir=axis)


def test_the_live_method_axis_is_a_to_e() -> None:
    live = ["all_pick", "all_pick_dag", "all_generate_pick", "all_generate_evaluate_pick",
            "all_generate_evaluate_random_pick"]
    assert list(method_letters(live).values()) == list(METHOD_LETTERS[:5])


def test_empty_method_axis_is_empty() -> None:
    assert method_letters([]) == {}
    assert method_key_lines([]) == []


# ------------------------------------------------------------------
# The provenance table
# ------------------------------------------------------------------


def test_provenance_has_one_row_per_model_axis() -> None:
    rows = model_provenance_rows()
    assert [row["model_id"] for row in rows] == discover_model_ids()
    assert all(set(row) == set(PROVENANCE_COLUMNS) for row in rows)


def test_provenance_model_column_is_the_figure_name() -> None:
    for row in model_provenance_rows():
        assert row["model"] == model_label(row["model_id"])


def test_provenance_records_the_machine_for_locally_served_models() -> None:
    rows = {row["model_id"]: row for row in model_provenance_rows()}
    local = [row for row in rows.values() if row["provider"] == "ollama"]
    assert local, "expected at least one locally served model axis"
    for row in local:
        assert row["host"] and row["endpoint"] and row["host_label"]


def test_provenance_leaves_the_endpoint_empty_for_remote_providers() -> None:
    """Empty is the documented absent marker: the SDK's own endpoint, unpinned by config."""
    for row in model_provenance_rows():
        if row["provider"] != "ollama":
            assert row["host"] == "" and row["host_label"] == ""


def test_provenance_carries_the_discarded_flag() -> None:
    rows = {row["model_id"]: row for row in model_provenance_rows()}
    assert rows["ollama_qwen3_14b"]["discarded"] is True
    assert rows["claude_sonnet"]["discarded"] is False


def test_provenance_rejects_a_host_the_registry_does_not_declare(tmp_path: Path) -> None:
    _write_model(
        tmp_path,
        "ollama_ghost",
        {
            "id": "ollama_ghost",
            "label": "Ollama Ghost 1B",
            "display": {"name": "Ghost 1B"},
            "model_config": {"provider": "ollama", "model": "ghost:1b"},
            "parameters": {"parallel": {"workers": {"mars_rover": 2}}},
        },
    )
    with pytest.raises(ValueError, match="mars_rover"):
        model_provenance_rows(models_dir=tmp_path)

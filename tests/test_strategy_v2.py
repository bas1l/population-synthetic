"""The v2 strategy arms: category set, birth chain, discoverability, and the country guard.

A v2 strategy is its v1 sibling minus three categories (``birth_location``,
``ethnicity_broad_global_approx``, ``current_environment_type``) with
``birth_country_detail`` rewired onto ``age`` + ``biological_sex``. Everything else --
the per-category ``method``, the ``context`` mode, the remaining edges -- must be
byte-equivalent to v1, or the v1<->v2 contrast stops being a single-factor comparison.
These tests pin that derivation rather than restating the files.

The compatibility guard is exercised at the orchestration edge, where it lives: the
required raw keys are an analysis-layer fact (the country's mapping index minus its
deprecated attributes), the category set is a generator-layer fact, and only the CLI
driver sees both.
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.generators.synthetic.identity_generator_configurable import (
    resolve_category_order,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_STRATEGY_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies"
_FAMILIES = _STRATEGY_DIR / "_families.yaml"
_SIM_CONFIG = (
    PROJECT_ROOT
    / "config"
    / "synthetic"
    / "simulation_configs"
    / "simulation_config_006_swedish_generative_guided.json"
)

# The v2 category set, verbatim from the plan's Definitions section. Written out rather
# than derived so a silent edit to a YAML cannot silently edit the expectation too.
V2_CATEGORIES = {
    "age",
    "biological_sex",
    "region",
    "birth_country_detail",
    "civil_status",
    "household_size",
    "education_level",
    "employment_status",
    "employment_type",
    "industry_sector",
    "socioeconomic_class",
    "income_source",
    "housing_tenure",
    "parental_structure",
}

DROPPED_IN_V2 = {"birth_location", "ethnicity_broad_global_approx", "current_environment_type"}

# (v2 id, its v1 sibling / family id)
V2_FAMILIES = [
    ("all_pick_v2", "all_pick"),
    ("all_pick_dag_v2", "all_pick_dag"),
    ("all_generate_pick_v2", "all_generate_pick"),
    ("all_generate_evaluate_pick_v2", "all_generate_evaluate_pick"),
    ("all_generate_evaluate_random_pick_v2", "all_generate_evaluate_random_pick"),
]
V2_IDS = [v2 for v2, _ in V2_FAMILIES]

_driver: Any = None


def _load_driver() -> Any:
    """Load the CLI driver by file path (``scripts/`` is not an importable package).

    Cached for the same reason as in ``test_ollama_preflight_cli``: the module attaches
    a console handler to the root logger at import.
    """
    global _driver
    if _driver is None:
        path = PROJECT_ROOT / "scripts" / "generate" / "generate_identities_parallel.py"
        spec = importlib.util.spec_from_file_location("generate_identities_parallel", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _driver = module
    return _driver


def _read(strategy_id: str) -> dict:
    with open(_STRATEGY_DIR / f"{strategy_id}.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("v2_id,family", V2_FAMILIES)
def test_v2_axis_metadata(v2_id: str, family: str) -> None:
    data = _read(v2_id)
    # stem == id, because compose_manifest resolves ``strategies/{id}.yaml``.
    assert data["id"] == v2_id
    assert not v2_id.startswith("_")
    assert data["family"] == family
    assert data["version"] == 2
    assert data["label"] and data["description"]

    with open(_FAMILIES, "r", encoding="utf-8") as f:
        declared = {entry["id"] for entry in yaml.safe_load(f)["families"]}
    assert family in declared


@pytest.mark.parametrize("v2_id", V2_IDS)
def test_v2_category_set_is_exactly_the_fourteen(v2_id: str) -> None:
    categories = _read(v2_id)["categories"]
    assert len(categories) == 14
    assert set(categories) == V2_CATEGORIES
    assert not DROPPED_IN_V2 & set(categories)


@pytest.mark.parametrize("v2_id", V2_IDS)
def test_v2_categories_exist_in_the_country_schema(v2_id: str) -> None:
    # ``identity_generator_configurable`` raises on a category absent from the flat
    # schema, so an unknown name would only surface mid-run.
    with open(_SIM_CONFIG, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert set(_read(v2_id)["categories"]) <= set(schema["categories"])


@pytest.mark.parametrize("v2_id,v1_id", V2_FAMILIES)
def test_v2_mirrors_its_v1_sibling(v2_id: str, v1_id: str) -> None:
    """v2 differs from v1 only by the three drops and the birth-chain rewire."""
    v1, v2 = _read(v1_id), _read(v2_id)
    assert v1.get("context", "cumulative") == v2.get("context", "cumulative")

    for name, cfg in v2["categories"].items():
        assert cfg["method"] == v1["categories"][name]["method"], name

    for name, cfg in v2["categories"].items():
        if name == "birth_country_detail":
            continue  # rewired; asserted separately
        # Every surviving edge is its v1 edge minus references to dropped categories.
        expected = [d for d in v1["categories"][name]["depends_on"] if d not in DROPPED_IN_V2]
        assert cfg["depends_on"] == expected, name


def test_v2_birth_chain_is_rewired_onto_age_and_sex() -> None:
    for v2_id, _ in V2_FAMILIES:
        if v2_id == "all_pick_v2":
            continue  # the context-free baseline: the rewire is a deliberate no-op
        deps = _read(v2_id)["categories"]["birth_country_detail"]["depends_on"]
        assert deps == ["age", "biological_sex"], v2_id


def test_all_pick_v2_stays_the_context_free_baseline() -> None:
    data = _read("all_pick_v2")
    assert data["context"] == "none"
    assert all(cfg["depends_on"] == [] for cfg in data["categories"].values())


@pytest.mark.parametrize("v2_id", V2_IDS)
def test_resolved_order_puts_age_and_sex_before_birth_country(v2_id: str) -> None:
    order = resolve_category_order(str(_STRATEGY_DIR / f"{v2_id}.yaml"))
    assert len(order) == 14
    assert set(order) == V2_CATEGORIES
    assert order.index("age") < order.index("birth_country_detail")
    assert order.index("biological_sex") < order.index("birth_country_detail")


def test_v2_ids_are_discoverable_axis_values() -> None:
    ids = [d["id"] for d in discover_axis_values("strategies")]
    assert set(V2_IDS) <= set(ids)
    assert not [i for i in ids if i.startswith("_")]


def test_each_v2_sorts_immediately_after_its_v1_sibling() -> None:
    ids = [d["id"] for d in discover_axis_values("strategies")]
    ordered = strategy_complexity_order(ids)
    for v2_id, v1_id in V2_FAMILIES:
        assert ordered[ordered.index(v1_id) + 1] == v2_id


@pytest.mark.parametrize("v2_id", V2_IDS)
@pytest.mark.parametrize("country_id", ["swedish", "swedish_02"])
def test_guard_accepts_v2_on_sweden(v2_id: str, country_id: str) -> None:
    # Sweden deprecates birth_location, so its 14 required keys are exactly the v2 set.
    _load_driver()._assert_strategy_covers_country(
        _STRATEGY_DIR / f"{v2_id}.yaml", v2_id, country_id
    )


@pytest.mark.parametrize("v2_id", V2_IDS)
def test_guard_rejects_v2_on_italy(v2_id: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        _load_driver()._assert_strategy_covers_country(
            _STRATEGY_DIR / f"{v2_id}.yaml", v2_id, "italian"
        )
    message = str(excinfo.value)
    # Both axis ids and the missing attribute must be named, or the operator has to
    # reverse-engineer which half of the pair was wrong.
    assert "birth_location" in message
    assert v2_id in message
    assert "italian" in message


@pytest.mark.parametrize("v1_id", [v1 for _, v1 in V2_FAMILIES])
@pytest.mark.parametrize("country_id", ["swedish", "swedish_02", "italian"])
def test_guard_leaves_v1_combos_untouched(v1_id: str, country_id: str) -> None:
    _load_driver()._assert_strategy_covers_country(
        _STRATEGY_DIR / f"{v1_id}.yaml", v1_id, country_id
    )

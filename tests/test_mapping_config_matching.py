"""Guard: every engine-read mapping directory declares valid, explicit matching rules.

The matching engine has no in-code defaults: each ``_index.json`` must declare a
``matching`` block for both sides and every attribute file a ``priority`` list
(:func:`mapping_engine.validate_mappings`). These tests load the production config so a
config edit that drops or breaks either fails here, not halfway through a mapping run.

They also pin the **behaviour-preservation contract**: with ``token_mode: substring``,
``negation: null``, ``tie_break: ["priority"]`` and ``priority == values`` the engine is
provably the historic one (first value in declared order, substring tokens), so the
directories and sides that are meant to map exactly as before -- the global ``scb`` tier,
Italy's ``istat`` and every ``real`` side -- are asserted to carry exactly that.
``config/mapping/ssb`` is not read by the engine (legacy label-map format consumed by the
Norway generator) and is out of scope.
"""

from __future__ import annotations

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping import mapping_engine
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings

_ENGINE_DIRS = ("scb_native", "scb", "istat")

#: The options under which the engine reproduces the historic matcher exactly.
_PRESERVING = mapping_engine.Matching(token_mode="substring", negation=None, tie_break=("priority",))

#: (directory, side) pairs that must keep the historic behaviour.
_PRESERVED_SIDES = [("scb", "real"), ("scb", "synthetic"), ("istat", "real"), ("istat", "synthetic"),
                    ("scb_native", "real")]


def _load(tier: str) -> dict:
    return load_mappings(PROJECT_ROOT / "config" / "mapping" / tier)


@pytest.mark.parametrize("tier", _ENGINE_DIRS)
def test_directory_validates(tier):
    compiled = mapping_engine.validate_mappings(_load(tier), tier)
    assert set(compiled) == {"real", "synthetic"}


@pytest.mark.parametrize("tier", _ENGINE_DIRS)
def test_every_attribute_declares_priority(tier):
    mappings = _load(tier)
    for attr, filename in mappings["_index"]["attributes"].items():
        block = mappings[filename[:-5]]
        assert sorted(block["priority"]) == sorted(block["values"]), f"{tier}/{attr}"


@pytest.mark.parametrize("tier, side", _PRESERVED_SIDES)
def test_preserved_sides_keep_historic_matching(tier, side):
    mappings = _load(tier)
    assert mapping_engine.validate_mappings(mappings, tier)[side] == _PRESERVING
    for attr, filename in mappings["_index"]["attributes"].items():
        block = mappings[filename[:-5]]
        assert block["priority"] == block["values"], f"{tier}/{attr}: priority must equal values order"
        rules = block.get(side, {})
        overrides = {"tie_break", "negation", "numeric_facet"} & set(rules)
        assert not overrides, f"{tier}/{attr}.{side} overrides {sorted(overrides)}"
        for value in block["values"]:
            for key in ("contains", "none_of"):
                assert all(isinstance(t, str) for t in rules.get(value, {}).get(key, [])), (
                    f"{tier}/{attr}.{side}.{value}.{key} carries a token-mode override"
                )

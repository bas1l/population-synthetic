"""Fail-fast unit tests for the generic synthetic-mapper engine.

``BaseSyntheticMapper`` discovers its field set at construction by scanning the
loaded mapping tables for blocks that self-declare a ``pipeline_handler`` kind.
These tests drive that engine directly with minimal synthetic ``mappings`` dicts
(rather than via ``get_synthetic_mapper``) so each fail-fast branch and the
non-cascade handler kinds can be triggered in isolation: ``BaseSyntheticMapper``
is concrete (it implements ``map_individual``) and its ``__init__`` consumes only
the ``mappings`` dict, so no country subclass or on-disk config is needed.

Mirrors ``tests/test_reference_mapper_base.py``.
"""

import pytest

from population_synth.comparison.synthetic_mapper import get_synthetic_mapper
from population_synth.comparison.synthetic_mapper.base import BaseSyntheticMapper


def _flat_identity(**overrides) -> dict:
    """A minimal valid flat identity (passes the age gate) with overridable fields."""
    base = {
        "age": 40, "biological_sex": "Female", "education_level": "x",
        "employment_status": "x", "current_environment_type": "Urban",
        "socioeconomic_class": "Middle class", "parental_structure": "x",
        "region": "x", "civil_status": "Married", "household_size": 2,
        "housing_tenure": "x", "industry_sector": "x", "employment_type": "x",
        "income_source": "x", "ethnicity": "x",
        "birth_location": "", "birth_country_detail": "",
    }
    base.update(overrides)
    return base


def test_no_declaring_block_raises():
    # An ``_scheme``-like block and a reference-only block; neither declares
    # ``pipeline_handler``, so the engine finds no pipeline field.
    mappings = {
        "_scheme": {"attributes": ["age_group"], "categories": {}},
        "socioeconomic": {"reference_handler": "decile_coded"},
    }
    with pytest.raises(ValueError, match="no fields declaring"):
        BaseSyntheticMapper(mappings)


def test_unknown_handler_kind_raises():
    mappings = {"mystery": {"pipeline_handler": "bogus_kind"}}
    with pytest.raises(ValueError, match="Unknown pipeline handler kind"):
        BaseSyntheticMapper(mappings)


def test_passthrough_and_numeric_gate_basic():
    # Mirrors the real ``id.json`` (passthrough) / ``age.json`` (numeric_gate) stubs.
    mappings = {
        "id": {"pipeline_handler": "passthrough"},
        "age": {"pipeline_handler": "numeric_gate", "pipeline_gate": True},
    }
    mapper = BaseSyntheticMapper(mappings)

    # Valid age -> mapped; the injected persona id passes through verbatim.
    out = mapper.map_individual({"age": 42}, "persona_x")
    assert out is not None
    assert out["id"] == "persona_x"
    assert out["age"] == 42


def test_numeric_gate_skips_non_integer_age():
    mappings = {"age": {"pipeline_handler": "numeric_gate", "pipeline_gate": True}}
    mapper = BaseSyntheticMapper(mappings)

    # Non-integer age -> the gate sentinel drops the whole persona.
    assert mapper.map_individual({"age": "not-a-number"}, "persona_y") is None


# ---------------------------------------------------------------------------
# cross_field_coded: the Phase-4 Nordic-Country fix (the one intended behaviour
# change). The Swedish synthetic mapper can now emit "Nordic Country" -- a bucket
# the reference mapper already produces -- for Nordic-born personas.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("birth_location,birth_country_detail", [
    ("", "Norway"),          # refined from birth_country_detail
    ("", "Denmark"),
    ("", "Finland"),
    ("Norway", ""),          # refined from primary free-text
    ("nordic region", ""),
    ("scandinavia", ""),
])
def test_swedish_nordic_persona_maps_to_nordic_country(birth_location, birth_country_detail):
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(
        _flat_identity(birth_location=birth_location, birth_country_detail=birth_country_detail), "p")
    assert out is not None
    assert out["birth_location"] == "Nordic Country"


def test_swedish_domestic_override_still_wins():
    # A domestic birth_country_detail forces Sweden, overriding any primary value.
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(
        _flat_identity(birth_location="Norway", birth_country_detail="Sweden"), "p")
    assert out["birth_location"] == "Sweden"


def test_swedish_non_nordic_european_unchanged():
    # Non-Nordic Europe must stay "Europe (Other)" (the fix is Nordic-only).
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(
        _flat_identity(birth_location="Poland", birth_country_detail=""), "p")
    assert out["birth_location"] == "Europe (Other)"


def test_italian_has_no_nordic_bucket():
    # Italy has only Italy / Europe (Other) / Outside Europe -- a Nordic origin
    # collapses to Europe (Other), exactly as before.
    mapper = get_synthetic_mapper("italian")
    out = mapper.map_individual(
        _flat_identity(birth_location="Norway", birth_country_detail=""), "p")
    assert out["birth_location"] == "Europe (Other)"

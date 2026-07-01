"""Unit tests for ``BaseReferenceMapper`` as a thin loader over the shared engine.

The reference mapper no longer holds a handler-kind engine: it reads the per-country
``_index.json`` master plus each per-attribute file's ``database`` block and ``values``
list, and delegates every attribute to :func:`mapping_engine.resolve`. These tests
drive the concrete base class directly with the shared in-memory config from
:mod:`tests._mapping_fixtures` (the new ``values`` / ``database`` / ``synthetic`` shape,
keyed by file stem plus the ``_index`` master), so no country subclass or on-disk
config is needed.

They exercise the two responsibilities the base class still owns -- ``id`` passthrough
and the raw ``age`` passthrough (``age_group`` is derived at scoring time) -- plus the
DB-side algorithms now expressed purely as matchers: composite ``employment_type``
(attachment x hours), decile-as-``equals`` ``socioeconomic``, the ``absent`` directive
for a missing field, and a total miss resolving to ``None``.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.mapping.reference_mapper.base import BaseReferenceMapper

from ._mapping_fixtures import new_shape_mappings


def _ref_record() -> dict:
    """A raw reference record (nested ``RawCategory`` dicts) exercising every branch."""
    return {
        "id": "ref-1",
        "age": 30,
        "biological_sex": {"label": "women"},
        "education_level": {"label": "universitet"},
        "employment_type": {
            "attachment": {"label": "Permanent employees"},
            "hours": {"label": "35+ hours"},
        },
        "socioeconomic_class": {"decile": "Decile 7"},
        # industry_sector omitted -> absent directive.
        "birth_location": {"label": "Norway"},
        "birth_country_detail": {"label": "Norway"},
        "household_size": {"label": "5"},
    }


# --- fail-fast construction ------------------------------------------------

def test_missing_index_raises():
    # A mappings dict with no ``_index`` master cannot declare an attribute axis.
    with pytest.raises(ValueError, match="_index"):
        BaseReferenceMapper({"biological_sex": {"values": ["Male", "Female"]}})


def test_index_without_attributes_raises():
    with pytest.raises(ValueError, match="_index"):
        BaseReferenceMapper({"_index": {"description": "no attributes"}})


def test_missing_config_block_for_attribute_raises():
    # The master references ``age.json`` but no ``age`` block is present.
    mappings = {"_index": {"attributes": {"employment_type": "employment_type.json"}}}
    mapper = BaseReferenceMapper(mappings)
    with pytest.raises(ValueError, match="missing config block"):
        mapper.normalize_individual({"id": "x", "employment_type": {"attachment": {"label": "z"}}})


# --- end-to-end resolution -------------------------------------------------

def test_reference_mapper_delegates_end_to_end():
    mapper = BaseReferenceMapper(new_shape_mappings())
    out = mapper.normalize_individual(_ref_record())

    assert out["id"] == "ref-1"                       # id passthrough
    assert out["age"] == 30                           # raw age passthrough
    assert "age_group" not in out                     # derived at scoring time
    assert out["biological_sex"] == "Female"          # equals "women"
    assert out["education_level"] == "Tertiary"
    assert out["employment_type"] == "Permanent Full-time"   # composite attachment x hours
    assert out["socioeconomic_class"] == "Middle Class"      # decile-as-equals
    assert out["industry_sector"] == "Not Applicable"        # absent directive
    assert out["birth_location"] == "Nordic Country"
    assert out["household_size"] == "4+ persons"


def test_reference_absent_field_uses_absent_directive():
    # A null employment_type record resolves to the ``absent`` literal, not None.
    mapper = BaseReferenceMapper(new_shape_mappings())
    out = mapper.normalize_individual({"id": "r", "age": 50, "employment_type": None})
    assert out["employment_type"] == "Not Applicable"


def test_reference_total_miss_resolves_to_none():
    # An unmatched token with no on_miss -> None.
    mapper = BaseReferenceMapper(new_shape_mappings())
    out = mapper.normalize_individual({"id": "r", "age": 40, "biological_sex": {"label": "unmatched"}})
    assert out["biological_sex"] is None

"""Fail-fast unit tests for the generic reference-mapper engine.

``BaseReferenceMapper`` discovers its field set at construction by scanning the
loaded mapping tables for blocks that self-declare a ``reference_handler`` kind.
These tests drive that engine directly with minimal synthetic ``mappings`` dicts
(rather than via ``get_reference_mapper``) so each fail-fast branch can be
triggered in isolation: ``BaseReferenceMapper`` is concrete (it implements
``normalize_individual``) and its ``__init__`` consumes only the ``mappings``
dict, so no country subclass or on-disk config is needed.
"""

import pytest

from population_synth.comparison.reference_mapper.base import BaseReferenceMapper


def test_no_declaring_block_raises():
    # Only an ``_scheme``-like block and a synthetic-only block; neither declares
    # ``reference_handler``, so the engine finds no reference field.
    mappings = {
        "_scheme": {"attributes": ["age_group"], "categories": {}},
        "ethnicity": {"pipeline_label_mappings": {"swedish": "Swedish"}},
    }
    with pytest.raises(ValueError, match="no fields declaring"):
        BaseReferenceMapper(mappings)


def test_unknown_handler_kind_raises():
    mappings = {"mystery": {"reference_handler": "bogus_kind"}}
    with pytest.raises(ValueError, match="Unknown reference handler kind"):
        BaseReferenceMapper(mappings)


def test_passthrough_handler_emits_raw_value():
    # Mirrors the real ``id.json`` / ``age.json`` passthrough stubs.
    mappings = {
        "id": {"reference_handler": "passthrough"},
        "age": {"reference_handler": "passthrough"},
    }
    mapper = BaseReferenceMapper(mappings)
    out = mapper.normalize_individual({"id": "abc123", "age": 42})
    assert out["id"] == "abc123"
    assert out["age"] == 42

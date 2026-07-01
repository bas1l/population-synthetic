"""Unit tests for the ``_index.json`` reader and the index-sourced comparison scheme.

Production config is still on the legacy ``_scheme.json`` (migrated in a later
phase), so these tests build a small ``_index.json`` + per-attribute ``values``
files under ``tmp_path`` and point ``load_scheme`` / ``load_index`` at them via the
``mappings_path`` / directory argument.
"""

import json

import pytest

from population_synth.comparison.reference_mapper.mappings import load_index
from population_synth.comparison.scheme import ComparisonScheme, load_scheme


def _write_country(directory, attributes, *, joint_pairs, coherence, omit=()):
    """Write a fixture country mapping dir: an ``_index.json`` + one file per attribute."""
    directory.mkdir(parents=True, exist_ok=True)
    index = {
        "description": "fixture",
        "attributes": {attr: f"{attr}.json" for attr in attributes},
        "joint_pairs": joint_pairs,
        "coherence_attributes": coherence,
    }
    (directory / "_index.json").write_text(json.dumps(index), encoding="utf-8")
    for attr, values in attributes.items():
        if attr in omit:
            continue
        (directory / f"{attr}.json").write_text(
            json.dumps({"values": values, "database": {}, "synthetic": {}}), encoding="utf-8"
        )


_AGE_BINS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


# --- _index.json reader ----------------------------------------------------

def test_load_index_returns_ordered_attributes(tmp_path):
    _write_country(
        tmp_path,
        {"age_group": _AGE_BINS, "biological_sex": ["Male", "Female"]},
        joint_pairs=[["age_group", "biological_sex"]],
        coherence=["age_group"],
    )
    index = load_index(tmp_path)
    assert list(index["attributes"]) == ["age_group", "biological_sex"]


def test_load_index_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_index(tmp_path)


def test_load_index_missing_key_raises(tmp_path):
    (tmp_path / "_index.json").write_text(json.dumps({"attributes": {"a": "a.json"}}), encoding="utf-8")
    with pytest.raises(KeyError, match="joint_pairs"):
        load_index(tmp_path)


def test_load_index_empty_attributes_raises(tmp_path):
    (tmp_path / "_index.json").write_text(
        json.dumps({"attributes": {}, "joint_pairs": [], "coherence_attributes": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="non-empty"):
        load_index(tmp_path)


# --- scheme built from master + per-file values ----------------------------

def test_scheme_built_from_index_and_values(tmp_path):
    _write_country(
        tmp_path,
        {
            "age_group": _AGE_BINS,
            "biological_sex": ["Male", "Female"],
            "employment_status": ["Employed", "Unemployed"],
        },
        joint_pairs=[["age_group", "employment_status"]],
        coherence=["age_group", "employment_status"],
    )
    scheme = load_scheme("swedish", mappings_path=tmp_path)
    assert isinstance(scheme, ComparisonScheme)
    # Attribute order follows the _index.json key order.
    assert scheme.attributes == ["age_group", "biological_sex", "employment_status"]
    # age_group categories are the 7 bin labels from age.json's values.
    assert scheme.categories["age_group"] == _AGE_BINS
    assert scheme.categories["employment_status"] == ["Employed", "Unemployed"]
    # joint_pairs are tuples; coherence a tuple.
    assert scheme.joint_pairs == [("age_group", "employment_status")]
    assert scheme.coherence_attributes == ("age_group", "employment_status")


def test_scheme_is_country_driven_by_index_contents(tmp_path):
    # Italy-like fixture: no income_source attribute in the index at all.
    sv_dir = tmp_path / "scb"
    it_dir = tmp_path / "istat"
    _write_country(
        sv_dir,
        {"age_group": _AGE_BINS, "income_source": ["Wage / Business", "Pension"]},
        joint_pairs=[], coherence=[],
    )
    _write_country(
        it_dir,
        {"age_group": _AGE_BINS, "employment_status": ["Employed", "Not Employed"]},
        joint_pairs=[], coherence=[],
    )
    sv = load_scheme("swedish", mappings_path=sv_dir)
    it = load_scheme("italian", mappings_path=it_dir)
    assert "income_source" in sv.attributes
    assert "income_source" not in it.attributes


def test_scheme_missing_values_key_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
    )
    # Corrupt the attribute file: drop its 'values'.
    (tmp_path / "biological_sex.json").write_text(json.dumps({"database": {}}), encoding="utf-8")
    with pytest.raises(KeyError, match="values"):
        load_scheme("swedish", mappings_path=tmp_path)


def test_scheme_missing_referenced_file_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
        omit=("biological_sex",),
    )
    with pytest.raises(FileNotFoundError):
        load_scheme("swedish", mappings_path=tmp_path)


def test_legacy_scheme_json_still_read_when_no_index(tmp_path):
    # A directory with only the legacy _scheme.json is read through the old path.
    legacy = {
        "attributes": ["biological_sex"],
        "categories": {"biological_sex": ["Male", "Female"]},
        "joint_pairs": [],
        "coherence_attributes": [],
    }
    (tmp_path / "_scheme.json").write_text(json.dumps(legacy), encoding="utf-8")
    scheme = load_scheme("swedish", mappings_path=tmp_path)
    assert scheme.attributes == ["biological_sex"]
    assert scheme.categories["biological_sex"] == ["Male", "Female"]

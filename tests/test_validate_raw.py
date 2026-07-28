"""Unit tests for the validate_raw task (analysis-DAG root: raw completeness gate).

``validate_raw_combo`` inspects every ``persona_*`` dir under a combo's raw directory and
records, per persona: whether ``identity.json`` exists and whether every expected category
carries a non-empty value ("complete" = present, whatever the value). The verdict is
written to one CSV per combo (``persona_id,passed,has_identity_json,n_expected_keys,
missing_categories``) that ``population_cap`` later intersects with the mapped verdict.

Correctness of a value is NOT judged here -- only presence. For the combo-level tests the
expected keys are injected directly, so those are independent of the live mapping config;
the config-derived resolver ``expected_raw_keys`` has its own section at the bottom, where
the deprecation mechanism is exercised against fixture indices (mirroring
``tests/test_scheme_index.py``) plus the two live country configs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from population_synthetic.analysis.utils.validity_csv import read_passed_ids
from population_synthetic.analysis.validate_raw import expected_raw_keys, validate_raw_combo
from population_synthetic.analysis.validate_raw import validate as validate_module

_SLUG = "swedish_all_pick_claude_haiku"
_EXPECTED_KEYS = ["age", "biological_sex", "education_level"]


def _read_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return {r["persona_id"]: r for r in rows}


def _make_persona(combo: Path, name: str, identity: dict | None) -> None:
    pdir = combo / name
    pdir.mkdir(parents=True, exist_ok=True)
    if identity is not None:
        (pdir / "identity.json").write_text(json.dumps(identity), encoding="utf-8")


def test_validate_raw_combo_verdicts_and_csv(tmp_path: Path):
    combo = tmp_path / "01_Raw" / _SLUG
    # persona_00001: no identity.json at all -> has_identity_json False, passed False.
    _make_persona(combo, "persona_00001", None)
    # persona_00002: identity present but one category empty -> passed False, listed.
    _make_persona(
        combo,
        "persona_00002",
        {"age": 30, "biological_sex": "male", "education_level": ""},
    )
    # persona_00003: every expected category populated -> passed True.
    _make_persona(
        combo,
        "persona_00003",
        {"age": 44, "biological_sex": "female", "education_level": "upper_secondary"},
    )

    csv_path = tmp_path / "03_Analysis" / "validate_raw" / f"{_SLUG}.csv"
    summary = validate_raw_combo(_SLUG, combo, _EXPECTED_KEYS, csv_path)

    # --- summary counts
    assert summary["slug"] == _SLUG
    assert summary["n"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 2
    assert summary["missing_identity"] == 1
    # The completeness denominator travels with the counts.
    assert summary["n_expected_keys"] == len(_EXPECTED_KEYS)

    # --- CSV header is the stable validity prefix + the raw detail columns
    assert csv_path.is_file()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == [
        "persona_id",
        "passed",
        "has_identity_json",
        "n_expected_keys",
        "missing_categories",
    ]

    rows = _read_rows(csv_path)
    # missing identity.json
    assert rows["persona_00001"]["has_identity_json"] == "False"
    assert rows["persona_00001"]["passed"] == "False"
    # missing (empty) category is named in missing_categories
    assert rows["persona_00002"]["passed"] == "False"
    assert "education_level" in rows["persona_00002"]["missing_categories"]
    # complete persona passes with no missing categories
    assert rows["persona_00003"]["passed"] == "True"
    assert rows["persona_00003"]["missing_categories"] == ""
    # every row carries the denominator its missing list was drawn from
    assert {r["n_expected_keys"] for r in rows.values()} == {str(len(_EXPECTED_KEYS))}

    # --- read_passed_ids returns exactly the passing persona
    assert read_passed_ids(csv_path) == {"persona_00003"}


def test_validate_raw_combo_empty_expected_keys_raises(tmp_path: Path):
    # An empty requirement would pass every persona vacuously -- fail loudly instead of
    # reporting a meaningless 100%.
    combo = tmp_path / "01_Raw" / _SLUG
    _make_persona(combo, "persona_00001", {"age": 30})
    with pytest.raises(ValueError, match="empty expected-key set"):
        validate_raw_combo(_SLUG, combo, [], tmp_path / "out.csv")


# --- expected_raw_keys: config-derived requirement, deprecated axes subtracted ---------


def _write_index(directory: Path, attributes: list[str], deprecated: list[str] | None = None):
    """Write a minimal mapping ``_index.json`` fixture (attribute -> filename map)."""
    directory.mkdir(parents=True, exist_ok=True)
    index: dict = {"attributes": {attr: f"{attr}.json" for attr in attributes}}
    if deprecated is not None:
        index["deprecated_attributes"] = deprecated
    (directory / "_index.json").write_text(json.dumps(index), encoding="utf-8")


@pytest.fixture
def fixture_country(tmp_path: Path, monkeypatch):
    """Point ``expected_raw_keys`` at a fixture mapping dir instead of the live config."""
    monkeypatch.setattr(validate_module, "mappings_for_country", lambda country: tmp_path)
    return tmp_path


def test_expected_raw_keys_excludes_deprecated(fixture_country: Path):
    _write_index(
        fixture_country,
        ["age_group", "biological_sex", "birth_location"],
        deprecated=["birth_location"],
    )
    # age_group -> age alias applied; the deprecated axis is not required.
    assert expected_raw_keys("anything") == ["age", "biological_sex"]


def test_expected_raw_keys_absent_deprecated_key_unchanged_behavior(fixture_country: Path):
    # Regression guard: no deprecated_attributes key -> the full attribute set is required.
    _write_index(fixture_country, ["age_group", "biological_sex", "birth_location"])
    assert expected_raw_keys("anything") == ["age", "biological_sex", "birth_location"]


def test_expected_raw_keys_unknown_deprecated_name_raises(fixture_country: Path):
    # A deprecated name absent from ``attributes`` is a config error -> fail loudly.
    _write_index(fixture_country, ["age_group"], deprecated=["not_an_attribute"])
    with pytest.raises(ValueError, match="deprecated_attributes"):
        expected_raw_keys("anything")


def test_expected_raw_keys_deprecating_everything_raises(fixture_country: Path):
    # Deprecating every attribute would leave the gate with nothing to check.
    _write_index(
        fixture_country, ["age_group", "biological_sex"], deprecated=["age_group", "biological_sex"]
    )
    with pytest.raises(ValueError, match="no non-deprecated attributes"):
        expected_raw_keys("anything")


def test_expected_raw_keys_live_config_is_country_specific():
    """The live configs: Sweden deprecates birth_location, Italy does not.

    This asymmetry is the point of the deprecation subtraction -- the requirement is a
    property of the country's mapping index, not a list in code.
    """
    swedish = expected_raw_keys("swedish")
    italian = expected_raw_keys("italian")
    assert "birth_location" not in swedish
    assert "birth_location" in italian
    assert "age" in swedish and "age_group" not in swedish  # alias applied
    assert len(swedish) == 14
    assert len(italian) == 14

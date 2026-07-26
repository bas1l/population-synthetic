"""Unit tests for the validate_raw task (analysis-DAG root: raw completeness gate).

``validate_raw_combo`` inspects every ``persona_*`` dir under a combo's raw directory and
records, per persona: whether ``identity.json`` exists and whether every expected category
carries a non-empty value ("complete" = present, whatever the value). The verdict is
written to one CSV per combo (``persona_id,passed,has_identity_json,missing_categories``)
that ``population_cap`` later intersects with the mapped verdict.

Correctness of a value is NOT judged here -- only presence. Expected keys are injected
directly (the config-derived resolver ``expected_raw_keys`` is exercised elsewhere), so
these tests are independent of the live mapping config.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from population_synthetic.analysis.utils.validity_csv import read_passed_ids
from population_synthetic.analysis.validate_raw import validate_raw_combo

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

    # --- CSV header is the stable validity prefix + the raw detail columns
    assert csv_path.is_file()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == ["persona_id", "passed", "has_identity_json", "missing_categories"]

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

    # --- read_passed_ids returns exactly the passing persona
    assert read_passed_ids(csv_path) == {"persona_00003"}

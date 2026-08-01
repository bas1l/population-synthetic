"""Unit tests for the validate_mapped task (unmapped-value gate between mapping and cap).

``validate_mapped_combo`` inspects every mapped individual in a combo's mapped population
file and records whether any canonical attribute is left as the ``__UNMAPPED__`` sentinel
(a value the mappers could not resolve). The verdict is written to one CSV per combo
(``persona_id,passed,unmapped_fields``) keyed on the injected ``id``.

The record ``id`` and the numeric ``age`` passthrough are exempt from the check (they are
not sentinel-bearing resolved attributes); so are the country's ``deprecated_attributes``
(excluded from every analysis, so a persona must not be discarded over one). Every other
key is checked.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED
from population_synthetic.analysis.utils.validity_csv import read_passed_ids
from population_synthetic.analysis.validate_mapped import validate_mapped_combo

_SLUG = "swedish_all_pick_claude_haiku"
_COUNTRY = "swedish"


def _write_mapped_file(path: Path, individuals: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"n": len(individuals)}, "individuals": individuals}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["persona_id"]: r for r in rows}


def test_validate_mapped_combo_flags_unmapped_and_exempts_id_age(tmp_path: Path):
    mapped_file = tmp_path / "03_Analysis" / "mapping" / f"{_SLUG}.json"
    _write_mapped_file(
        mapped_file,
        [
            # A resolved attribute left unmapped -> failed, field listed.
            {"id": "persona_00001", "age": 30, "biological_sex": "male",
             "education_level": UNMAPPED},
            # age carries the sentinel but is EXEMPT (numeric passthrough) -> passes.
            {"id": "persona_00002", "age": UNMAPPED, "biological_sex": "female",
             "education_level": "upper_secondary"},
            # Fully mapped -> passes.
            {"id": "persona_00003", "age": 44, "biological_sex": "male",
             "education_level": "lower_secondary"},
        ],
    )

    csv_path = tmp_path / "03_Analysis" / "validate_mapped" / f"{_SLUG}.csv"
    summary = validate_mapped_combo(_SLUG, mapped_file, csv_path, _COUNTRY)

    # --- summary counts
    assert summary["slug"] == _SLUG
    assert summary["n"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1

    # --- CSV header is the stable validity prefix + the mapped detail column
    assert csv_path.is_file()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == ["persona_id", "passed", "unmapped_fields"]

    rows = _read_rows(csv_path)
    # The unmapped resolved attribute is flagged.
    assert rows["persona_00001"]["passed"] == "False"
    assert rows["persona_00001"]["unmapped_fields"] == "education_level"
    # age is exempt: an unmapped age does NOT fail the persona, and is never listed.
    assert rows["persona_00002"]["passed"] == "True"
    assert "age" not in rows["persona_00002"]["unmapped_fields"]
    # id is never treated as a checkable attribute.
    assert "id" not in rows["persona_00002"]["unmapped_fields"]
    assert rows["persona_00003"]["passed"] == "True"
    assert rows["persona_00003"]["unmapped_fields"] == ""

    # --- read_passed_ids returns exactly the passing personas
    assert read_passed_ids(csv_path) == {"persona_00002", "persona_00003"}


# --- deprecated-attribute exemption (config-driven, per country) -----------------------


def test_validate_mapped_combo_exempts_deprecated_attribute_per_country(tmp_path: Path):
    """The same record passes for Sweden and fails for Italy, on config alone.

    Sweden lists ``birth_location`` under the mapping index's ``deprecated_attributes``
    (it is excluded from the scored axis, and its synthetic rules ``refine_from``
    ``birth_country_detail`` -- which cannot yield an answer for the legitimate SCB
    category ``Other``). Italy analyses the axis, so an unmapped value there is a defect.
    """
    individuals = [
        {"id": "persona_00001", "age": 30, "biological_sex": "male",
         "birth_location": UNMAPPED},
    ]

    swedish_file = tmp_path / "mapping" / "swedish.json"
    _write_mapped_file(swedish_file, individuals)
    swedish = validate_mapped_combo(
        _SLUG, swedish_file, tmp_path / "out_swedish.csv", "swedish"
    )
    assert swedish["passed"] == 1
    assert swedish["failed"] == 0

    italian_file = tmp_path / "mapping" / "italian.json"
    _write_mapped_file(italian_file, individuals)
    italian = validate_mapped_combo(
        "italian_all_pick_claude_haiku", italian_file, tmp_path / "out_italian.csv", "italian"
    )
    assert italian["passed"] == 0
    assert italian["failed"] == 1
    assert _read_rows(tmp_path / "out_italian.csv")["persona_00001"][
        "unmapped_fields"
    ] == "birth_location"


def test_validate_mapped_combo_still_fails_non_deprecated_attributes(tmp_path: Path):
    """Regression guard: the exemption is scoped to the deprecated axis, nothing else."""
    mapped_file = tmp_path / "mapping" / f"{_SLUG}.json"
    _write_mapped_file(
        mapped_file,
        [
            {"id": "persona_00001", "age": 30, "birth_location": UNMAPPED,
             "education_level": UNMAPPED},
        ],
    )
    csv_path = tmp_path / "out.csv"
    summary = validate_mapped_combo(_SLUG, mapped_file, csv_path, _COUNTRY)
    assert summary["failed"] == 1
    # Only the non-deprecated miss is reported.
    assert _read_rows(csv_path)["persona_00001"]["unmapped_fields"] == "education_level"

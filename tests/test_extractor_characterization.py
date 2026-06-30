"""Characterization (golden) tests for :func:`extractor.extract_individual`.

The golden snapshot (``tests/data/extractor/expected_extractor.json``) pins the
*entire* attribute dict returned for three representative fixtures covering both
identity formats (batch narrative + flat/configurable) and both countries
(Swedish + Italian).  It is the safety net proving the ``extractor`` ->
``extract`` subpackage split is behaviour-preserving: this test must stay green
and the snapshot must not change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from population_synth.comparison.extractor import extract_individual, extract_population

_FIXTURE_ROOT = Path(__file__).parent / "data" / "extractor"
_EXPECTED_PATH = _FIXTURE_ROOT / "expected_extractor.json"

_CASES = [
    ("persona_batch_se", "swedish"),
    ("persona_flat_se", "swedish"),
    ("persona_flat_it", "italian"),
]


def _expected() -> dict:
    return json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("persona,country", _CASES)
def test_extract_individual_matches_golden(persona: str, country: str):
    expected = _expected()[persona]
    actual = extract_individual(_FIXTURE_ROOT / persona / "identity.json", country=country)
    assert actual == expected


def test_extract_population_swedish_collects_individuals():
    pop = extract_population(_FIXTURE_ROOT, country="swedish")
    ids = {ind["id"] for ind in pop["individuals"]}
    # Both Swedish-format fixtures (batch + flat) extract cleanly under swedish.
    assert {"persona_batch_se", "persona_flat_se"} <= ids
    assert pop["metadata"]["source"] == "pipeline"
    assert pop["metadata"]["n"] == len(pop["individuals"])

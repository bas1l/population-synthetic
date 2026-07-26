"""validate.py -- atomistic per-combo completeness check for raw personas.

For one combo's raw generation directory (``01_Raw/{slug}/``), this inspects every
``persona_*`` directory and records two things per persona: whether its ``identity.json``
exists, and whether every expected category carries a non-empty value. It is deliberately
single-purpose -- it does NOT judge whether a value is *correct* for its field (a city
appearing where a country belongs is out of scope here; that surfaces later as an
``__UNMAPPED__`` value caught by ``validate_mapped``). "Complete" means present, whatever
the value is.

The expected category set is config-driven, never hardcoded: it is the country's mapping
``_index.json`` attribute list (the full set, *including* deprecated attributes, since
those are still mapped and read from raw), with the single mapper alias applied --
``age_group`` is read from the raw ``age`` key. The injected ``id`` key is not part of the
raw file and is not required.

The per-persona verdict is written to one CSV per combo, keyed on the ``persona_XXXXX``
directory name, so ``population_cap`` can intersect it with the mapped verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, TypedDict

from population_synthetic.analysis.mapping.real_mapper.mappings import load_index
from population_synthetic.analysis.utils.country_config import mappings_for_country
from population_synthetic.analysis.utils.validity_csv import (
    PASSED_COLUMN,
    PERSONA_ID_COLUMN,
    write_validity_csv,
)

# The mapper's one raw-key alias: the canonical ``age_group`` axis is read from the raw
# ``age`` key (a structural constant of the mapping layer, not a tunable).
_AGE_GROUP_ATTR = "age_group"
_AGE_KEY = "age"

_IDENTITY_FILENAME = "identity.json"
_PERSONA_GLOB = "persona_*"

# Detail columns appended after the shared persona_id/passed prefix.
_HAS_IDENTITY_COLUMN = "has_identity_json"
_MISSING_CATEGORIES_COLUMN = "missing_categories"

_CSV_HEADER = (
    PERSONA_ID_COLUMN,
    PASSED_COLUMN,
    _HAS_IDENTITY_COLUMN,
    _MISSING_CATEGORIES_COLUMN,
)

# Sentinel written into ``missing_categories`` when identity.json exists but is unreadable
# (malformed JSON / IO error) -- distinct from a value-level completeness miss.
_UNREADABLE_MARKER = "<unreadable>"


class RawPersonaRow(TypedDict):
    """One raw persona's completeness verdict."""

    persona_id: str
    passed: bool
    has_identity_json: bool
    missing_categories: list[str]


class ValidateRawSummary(TypedDict):
    """Per-combo result of :func:`validate_raw_combo`."""

    slug: str
    n: int
    passed: int
    failed: int
    missing_identity: int
    csv_path: str


def expected_raw_keys(country: str) -> list[str]:
    """Return the raw identity.json keys a complete persona must carry, for ``country``.

    Config-driven: the country's mapping ``_index.json`` attribute list (full set,
    including deprecated attributes) with the ``age_group`` -> ``age`` alias applied.
    """
    index = load_index(mappings_for_country(country))
    return [(_AGE_KEY if attr == _AGE_GROUP_ATTR else attr) for attr in index["attributes"]]


def _is_empty(value: Any) -> bool:
    """Return True when a value is absent-in-spirit: None or an empty/whitespace string.

    Any other value -- including ``0``/``False`` or a wrong-for-the-field string -- counts
    as present, matching the "whatever the value is" completeness rule.
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


def _sorted_persona_dirs(raw_slug_dir: Path) -> list[Path]:
    return sorted(
        (p for p in raw_slug_dir.glob(_PERSONA_GLOB) if p.is_dir()),
        key=lambda p: p.name,
    )


def _evaluate_persona(persona_dir: Path, expected_keys: Sequence[str]) -> RawPersonaRow:
    persona_id = persona_dir.name
    identity_file = persona_dir / _IDENTITY_FILENAME
    if not identity_file.is_file():
        return RawPersonaRow(
            persona_id=persona_id, passed=False, has_identity_json=False, missing_categories=[]
        )
    try:
        with open(identity_file, "r", encoding="utf-8") as f:
            identity = json.load(f)
    except (json.JSONDecodeError, OSError):
        return RawPersonaRow(
            persona_id=persona_id,
            passed=False,
            has_identity_json=True,
            missing_categories=[_UNREADABLE_MARKER],
        )
    missing = [key for key in expected_keys if _is_empty(identity.get(key))]
    return RawPersonaRow(
        persona_id=persona_id,
        passed=not missing,
        has_identity_json=True,
        missing_categories=missing,
    )


def validate_raw_combo(
    slug: str,
    raw_slug_dir: Path,
    expected_keys: Sequence[str],
    csv_path: Path,
) -> ValidateRawSummary:
    """Validate one combo's raw personas and write the per-persona CSV.

    Args:
        slug: The combo slug (``{country}_{strategy}_{model}``).
        raw_slug_dir: The combo's raw directory (``01_Raw/{slug}/``).
        expected_keys: The raw keys a complete persona must carry (see
            :func:`expected_raw_keys`).
        csv_path: Destination CSV (``validate_raw/{slug}.csv``).

    Returns:
        A :class:`ValidateRawSummary`.
    """
    rows = [_evaluate_persona(p, expected_keys) for p in _sorted_persona_dirs(raw_slug_dir)]
    write_validity_csv(
        csv_path,
        _CSV_HEADER,
        rows=[
            (
                r["persona_id"],
                r["passed"],
                r["has_identity_json"],
                ";".join(r["missing_categories"]),
            )
            for r in rows
        ],
    )
    n_passed = sum(1 for r in rows if r["passed"])
    return ValidateRawSummary(
        slug=slug,
        n=len(rows),
        passed=n_passed,
        failed=len(rows) - n_passed,
        missing_identity=sum(1 for r in rows if not r["has_identity_json"]),
        csv_path=str(csv_path),
    )


# Folder-level roll-up: one row per combo in ``validate_raw/_summary.csv``. ``has_issues``
# sits right after the slug for an at-a-glance scan of which combos need attention.
SUMMARY_HEADER = (
    "slug",
    "has_issues",
    "n_personas",
    "passed",
    "failed",
    "missing_identity",
    "pass_rate_pct",
)


def summary_row(summary: ValidateRawSummary) -> tuple:
    """Build the folder-level ``_summary.csv`` row for one combo's raw-validation result."""
    n = summary["n"]
    pass_rate_pct = round(100 * summary["passed"] / n, 1) if n else 0.0
    return (
        summary["slug"],
        summary["failed"] > 0 or n == 0,
        n,
        summary["passed"],
        summary["failed"],
        summary["missing_identity"],
        pass_rate_pct,
    )

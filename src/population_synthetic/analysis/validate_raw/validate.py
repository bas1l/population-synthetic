"""validate.py -- atomistic per-combo completeness check for raw personas.

For one combo's raw generation directory (``01_Raw/{slug}/``), this inspects every
``persona_*`` directory and records two things per persona: whether its ``identity.json``
exists, and whether every expected category carries a non-empty value. It is deliberately
single-purpose -- it does NOT judge whether a value is *correct* for its field (a city
appearing where a country belongs is out of scope here; that surfaces later as an
``__UNMAPPED__`` value caught by ``validate_mapped``). "Complete" means present, whatever
the value is.

The expected category set is config-driven, never hardcoded: it is the country's mapping
``_index.json`` attribute list *minus* its ``deprecated_attributes``, with the single
mapper alias applied -- ``age_group`` is read from the raw ``age`` key. The injected ``id``
key is not part of the raw file and is not required.

Deprecated attributes were previously kept in the expected set, on the reasoning that they
are still mapped and read from raw. That reasoning conflated two questions: *is this axis
still mapped* (yes) and *must a generator still produce it* (no -- a deprecated axis is
excluded from every analysis, so requiring it fails personas over a value nothing scores).
A generation strategy that legitimately stops emitting a deprecated attribute would be
failed at 0% by this gate. The gate now asks only what the country genuinely requires, so
it agrees with :func:`~population_synthetic.analysis.fidelity.scheme.load_scheme`, which
reads the same two index keys. The mapper is unaffected -- it still reads a deprecated key
from raw when present.

Because the requirement is per country, completeness rates are not comparable across
countries (or across index revisions) on their own: Sweden requires 14 keys, Italy 14
including ``birth_location``. Every emitted rate therefore carries its expected-key count
``n_expected_keys`` so a 14-key rate is never silently read as a 15-key one.

The per-persona verdict is written to one CSV per combo, keyed on the ``persona_XXXXX``
directory name, so ``population_cap`` can intersect it with the mapped verdict.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence, TypedDict

from population_synthetic.analysis.mapping.real_mapper.mappings import load_index
from population_synthetic.analysis.utils.country_config import (
    deprecated_attributes,
    mappings_for_country,
)
from population_synthetic.analysis.utils.validity_csv import (
    PASSED_COLUMN,
    PERSONA_ID_COLUMN,
    write_validity_csv,
)

logger = logging.getLogger(__name__)

# The mapper's one raw-key alias: the canonical ``age_group`` axis is read from the raw
# ``age`` key (a structural constant of the mapping layer, not a tunable).
_AGE_GROUP_ATTR = "age_group"
_AGE_KEY = "age"

_IDENTITY_FILENAME = "identity.json"
_PERSONA_GLOB = "persona_*"

# Detail columns appended after the shared persona_id/passed prefix.
_HAS_IDENTITY_COLUMN = "has_identity_json"
_MISSING_CATEGORIES_COLUMN = "missing_categories"
# Denominator of the completeness verdict: how many keys this persona was required to
# carry. Sits immediately before the missing list so numerator and denominator are read
# together -- "2 missing" means nothing without the N it was drawn from.
N_EXPECTED_KEYS_COLUMN = "n_expected_keys"

_CSV_HEADER = (
    PERSONA_ID_COLUMN,
    PASSED_COLUMN,
    _HAS_IDENTITY_COLUMN,
    N_EXPECTED_KEYS_COLUMN,
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
    n_expected_keys: int
    csv_path: str


def expected_raw_keys(country: str) -> list[str]:
    """Return the raw identity.json keys a complete persona must carry, for ``country``.

    Config-driven: the country's mapping ``_index.json`` ``attributes``, minus its
    ``deprecated_attributes``, with the ``age_group`` -> ``age`` alias applied. A
    deprecated axis is excluded from every analysis, so requiring a generator to emit it
    would fail personas over a value nothing scores; the requirement is therefore what the
    *country* still analyses, and nothing else -- it does not depend on which strategy,
    version, or category set produced the run.

    This reads the same two index keys as
    :func:`~population_synthetic.analysis.fidelity.scheme.load_scheme`'s
    ``_scheme_from_index`` and mirrors its fail-loud contract, so the gate and the scored
    axis set cannot drift apart. The deprecation set itself comes from
    :func:`~population_synthetic.analysis.utils.country_config.deprecated_attributes`,
    shared with the mapped-value gate.

    Raises:
        ValueError: If ``deprecated_attributes`` names an attribute absent from
            ``attributes`` (a config error), or if deprecating leaves nothing required.
    """
    directory = mappings_for_country(country)
    index = load_index(directory)

    deprecated = deprecated_attributes(index, directory)
    required = [attr for attr in index["attributes"] if attr not in deprecated]
    if not required:
        raise ValueError(
            f"Mapping index {directory} has no non-deprecated attributes left: country "
            f"{country!r} would require nothing, making the raw completeness gate vacuous"
        )
    if deprecated:
        logger.info(
            "validate_raw: country %r requires %d raw key(s); excluded as deprecated: %s",
            country,
            len(required),
            ", ".join(deprecated),
        )
    return [(_AGE_KEY if attr == _AGE_GROUP_ATTR else attr) for attr in required]


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
        A :class:`ValidateRawSummary`, carrying ``n_expected_keys`` so the pass rate is
        never read without the requirement it was measured against.

    Raises:
        ValueError: If ``expected_keys`` is empty -- every persona would trivially pass,
            which is a silently vacuous gate rather than a 100% result.
    """
    n_expected_keys = len(expected_keys)
    if not n_expected_keys:
        raise ValueError(
            f"validate_raw for {slug!r} was given an empty expected-key set; every persona "
            f"would pass vacuously. Check the country's mapping index."
        )
    rows = [_evaluate_persona(p, expected_keys) for p in _sorted_persona_dirs(raw_slug_dir)]
    write_validity_csv(
        csv_path,
        _CSV_HEADER,
        rows=[
            (
                r["persona_id"],
                r["passed"],
                r["has_identity_json"],
                n_expected_keys,
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
        n_expected_keys=n_expected_keys,
        csv_path=str(csv_path),
    )


# Folder-level roll-up: one row per combo in ``validate_raw/_summary.csv``. ``has_issues``
# sits right after the slug for an at-a-glance scan of which combos need attention.
# ``n_expected_keys`` immediately precedes ``pass_rate_pct``: a pass rate measured against
# 14 required keys is a different quantity from one measured against 15, and the summary
# mixes countries and index revisions in one file, so the rate travels with its
# requirement rather than being comparable only by assumption.
SUMMARY_HEADER = (
    "slug",
    "has_issues",
    "n_personas",
    "passed",
    "failed",
    "missing_identity",
    N_EXPECTED_KEYS_COLUMN,
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
        summary["n_expected_keys"],
        pass_rate_pct,
    )

"""validate.py -- atomistic per-combo unmapped-value check for mapped personas.

For one combo's mapped population file (``03_Analysis/mapping/{slug}.json``), this
inspects every mapped individual and records whether any canonical attribute is left as
the ``__UNMAPPED__`` sentinel (a value the mappers could not resolve -- e.g. a city where
a country was expected). It is deliberately single-purpose: it does not judge whether a
resolved value is *plausible*, only whether it is *mapped*. The per-persona verdict is
written to one CSV per combo, keyed on the ``id`` (the source ``persona_XXXXX`` folder
name) that the synthetic mapper injects into every record, so ``population_cap`` can
intersect it with the raw-completeness verdict.

The module is schema-agnostic beyond two structural facts about a mapped individual: the
``id`` key is the record identifier (never an attribute), and ``age`` is a numeric
passthrough behind the mapper's skip gate rather than a resolved attribute. Every other
key is a resolved comparison attribute subject to the sentinel check -- **except** the
country's analysis-deprecated attributes, which are exempt for the same reason
``validate_raw`` does not require them: a deprecated axis is emitted into population data
but excluded from every analysis, so failing a persona over its value would discard a
persona nothing scores. Sweden deprecates ``birth_location``, whose synthetic rules
``refine_from`` ``birth_country_detail`` -- and the SCB categories ``Other`` and
``Yugoslavia`` carry no Sweden/Europe/Outside-Europe answer, so a persona born in a
country outside SCB's named top-21 is *unresolvable by construction* on that axis.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, TypedDict

from population_synthetic.analysis.utils.country_config import (
    deprecated_attributes_for_country,
)
from population_synthetic.analysis.utils.mapping_sentinel import is_unmapped
from population_synthetic.analysis.utils.validity_csv import (
    PASSED_COLUMN,
    PERSONA_ID_COLUMN,
    write_validity_csv,
)

logger = logging.getLogger(__name__)

# Keys on a mapped individual that are NOT resolved attributes and so are exempt from the
# unmapped-value check: the injected record id, and the numeric age passthrough (emitted
# by the mapper's special-cased age handling, not via the sentinel-bearing resolver).
_NON_ATTRIBUTE_KEYS = ("id", "age")

# Detail column appended after the shared persona_id/passed prefix.
_UNMAPPED_FIELDS_COLUMN = "unmapped_fields"

_CSV_HEADER = (PERSONA_ID_COLUMN, PASSED_COLUMN, _UNMAPPED_FIELDS_COLUMN)


class MappedPersonaRow(TypedDict):
    """One mapped persona's validity verdict."""

    persona_id: str
    passed: bool
    unmapped_fields: list[str]


class ValidateMappedSummary(TypedDict):
    """Per-combo result of :func:`validate_mapped_combo`."""

    slug: str
    n: int
    passed: int
    failed: int
    csv_path: str


def unmapped_fields(
    individual: dict[str, Any],
    exempt: Iterable[str] = (),
) -> list[str]:
    """Return the resolved-attribute keys of ``individual`` left unmapped, in record order.

    Args:
        individual: One mapped individual record.
        exempt: Attribute names excluded from the check (the country's
            ``deprecated_attributes``); an unmapped value on these is not a defect.
    """
    exempt_keys = frozenset(exempt)
    return [
        key
        for key, value in individual.items()
        if key not in _NON_ATTRIBUTE_KEYS and key not in exempt_keys and is_unmapped(value)
    ]


def evaluate_individuals(
    individuals: list[dict[str, Any]],
    exempt: Iterable[str] = (),
) -> list[MappedPersonaRow]:
    """Compute the per-persona unmapped-value verdict for a list of mapped individuals."""
    exempt_keys = frozenset(exempt)
    rows: list[MappedPersonaRow] = []
    for indiv in individuals:
        missing = unmapped_fields(indiv, exempt_keys)
        rows.append(
            MappedPersonaRow(
                persona_id=str(indiv.get("id", "?")),
                passed=not missing,
                unmapped_fields=missing,
            )
        )
    return rows


def _load_individuals(mapped_file: Path) -> list[dict[str, Any]]:
    """Load the ``individuals`` list from a mapped population file (fail-fast on malformed)."""
    with open(mapped_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    individuals = data.get("individuals")
    if not isinstance(individuals, list):
        raise ValueError(
            f"Mapped population file {mapped_file} has no 'individuals' list "
            f"(got {type(individuals).__name__})."
        )
    return individuals


def validate_mapped_combo(
    slug: str,
    mapped_file: Path,
    csv_path: Path,
    country: str,
) -> ValidateMappedSummary:
    """Validate one combo's mapped personas and write the per-persona CSV.

    When ``mapped_file`` is absent (mapping legitimately produced no synthetic file for a
    combo with zero mappable personas), an empty CSV is written and a zero-row summary is
    returned -- the same tolerance the cap task applies to an empty combo, rather than
    failing the batch.

    Args:
        slug: The combo slug (``{country}_{strategy}_{model}``).
        mapped_file: The combo's mapped population file (``mapping/{slug}.json``).
        csv_path: Destination CSV (``validate_mapped/{slug}.csv``).
        country: Country axis id, resolving which attributes are analysis-deprecated
            and therefore exempt from the sentinel check.

    Returns:
        A :class:`ValidateMappedSummary`.
    """
    if not mapped_file.is_file():
        write_validity_csv(csv_path, _CSV_HEADER, rows=[])
        return ValidateMappedSummary(
            slug=slug, n=0, passed=0, failed=0, csv_path=str(csv_path)
        )

    exempt = deprecated_attributes_for_country(country)
    if exempt:
        logger.info(
            "validate_mapped: country %r exempts deprecated attribute(s) from the "
            "unmapped-value check: %s",
            country,
            ", ".join(exempt),
        )

    rows = evaluate_individuals(_load_individuals(mapped_file), exempt)
    write_validity_csv(
        csv_path,
        _CSV_HEADER,
        rows=[
            (r["persona_id"], r["passed"], ";".join(r["unmapped_fields"])) for r in rows
        ],
    )
    n_passed = sum(1 for r in rows if r["passed"])
    return ValidateMappedSummary(
        slug=slug,
        n=len(rows),
        passed=n_passed,
        failed=len(rows) - n_passed,
        csv_path=str(csv_path),
    )


# Folder-level roll-up: one row per combo in ``validate_mapped/_summary.csv``. ``has_issues``
# sits right after the slug for an at-a-glance scan of which combos have unmapped values.
SUMMARY_HEADER = (
    "slug",
    "has_issues",
    "n_personas",
    "passed",
    "failed",
    "pass_rate_pct",
)


def summary_row(summary: ValidateMappedSummary) -> tuple:
    """Build the folder-level ``_summary.csv`` row for one combo's mapped-validation result."""
    n = summary["n"]
    pass_rate_pct = round(100 * summary["passed"] / n, 1) if n else 0.0
    return (
        summary["slug"],
        summary["failed"] > 0 or n == 0,
        n,
        summary["passed"],
        summary["failed"],
        pass_rate_pct,
    )

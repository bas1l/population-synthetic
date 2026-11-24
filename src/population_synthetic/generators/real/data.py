"""Shared population distribution data structures.

Defines ``PopulationDistributions``, the frozen dataclass that holds the
per-attribute and conditional probability distributions sampled during
population generation, plus ``RawCategory``, a ``TypedDict`` describing a
raw API category entry. Shared across all country-specific modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class RawCategory(TypedDict, total=False):
    code: str
    label: str
    decile: str


@dataclass(frozen=True)
class PopulationDistributions:
    age_sex: dict[tuple[int, str], float]
    education_by_age: dict[tuple[str, str], dict[str, float]]
    # Country-specific shape (name retained for cross-country stability). Sweden:
    # register labour-market status keyed by (age_group, sex) -> {status: prob}.
    # Norway/Italy may key this field differently (e.g. sex -> edu -> status).
    employment_by_sex_education: dict[tuple[str, str], dict[str, float]]
    birth_location: dict[tuple[str, str], dict[str, float]]
    region: dict[str, float]
    socioeconomic: dict[tuple[str, str], dict[str, float]]
    parental_structure: dict[str, float]
    civil_status_by_age_sex: dict[tuple[str, str], dict[str, float]]
    industry_sector: dict[tuple[str, str], dict[str, float]]
    employment_type_by_age: dict[tuple[str, str], dict[str, float]]
    housing_tenure: dict[tuple[str, str], dict[str, float]]
    household_size: dict[str, float]
    income_source_by_employment_age: dict[tuple[str, str], dict[str, float]]
    birth_country_detail: dict[tuple[str, str], dict[str, float]]
    ethnicity_map: dict[str, str]
    tables_used: tuple[str, ...]
    # Sweden only: county distribution within each (age_group, sex) cell, from the same
    # table as ``region``. When set, the sampler draws a person's county from their own
    # cell (like every other conditioned attribute); ``region`` stays the national
    # marginal. None for Norway/Italy, which keep drawing from ``region``.
    region_by_age_sex: dict[tuple[str, str], dict[str, float]] | None = None

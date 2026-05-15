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
    employment_by_sex_education: dict[str, dict[str, dict[str, float]]]
    birth_location: dict[str, float]
    region: dict[str, float]
    socioeconomic: dict[tuple[str, str], dict[str, float]]
    parental_structure: dict[str, float]
    civil_status_by_age_sex: dict[tuple[str, str], dict[str, float]]
    industry_sector: dict[str, float]
    employment_type_by_age: dict[tuple[str, str], dict[str, float]]
    housing_tenure: dict[str, float]
    household_size: dict[str, float]
    income_source_by_employment_age: dict[tuple[str, str], dict[str, float]]
    birth_country_detail: dict[tuple[str, str], dict[str, float]]
    ethnicity_map: dict[str, str]
    tables_used: tuple[str, ...]

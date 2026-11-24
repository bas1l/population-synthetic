"""Conditionally samples one individual from Swedish distributions.

Draws a single synthetic person from the ``PopulationDistributions``
produced by the Sweden fetch service via a deterministic chained
sampling sequence, where each attribute is conditioned on prior draws
(e.g. education given age and sex, employment given education).

Every conditional lookup is fail-fast: a missing cell raises ``ValueError``
naming the table and the cell. There is no other-sex or other-age-group
fallback -- such a fallback silently substituted another population's
distribution, and the age-group one iterated a ``set``, so its result depended
on ``PYTHONHASHSEED``. The only cross-cell substitutions are the declared AKU
age proxies for employment_type, built once in the fetch layer
(``constants.AKU_ATTACHMENT_AGE_LABEL_MAP`` / ``EMPLOYMENT_TYPE_AGE_PROXIES``)
and recorded in the output provenance, and the declared income_source fallback for
students aged 65 and over (``_INCOME_SOURCE_AGE_FALLBACK``: the income table has no
student cell above 64, so those individuals use the students' 55-64 income-source mix;
documented in ``docs/reference/scb-pxweb-catalog/income-source-student-65plus-fallback.md``).
"""
from __future__ import annotations

import numpy as np
from numpy.random import Generator

from population_synthetic.generators.real.data import PopulationDistributions
from population_synthetic.generators.real.helpers import age_to_group, sample_from

_SEX_CODES: dict[str, str] = {"men": "1", "women": "2"}

# Maps each canonical employment_status label (emitted by the register parser) to
# the income_source table's `Sysselsattning` (employment status) category, so
# Step 10 can look up the age-conditioned income-component mix. Every status must
# resolve (fail-fast on an unmapped one). Sick/Other fold onto "non gainfully
# employed" -- the income table's residual out-of-work category.
_STATUS_TO_INC_EMP: dict[str, str] = {
    "Employed": "gainfully employed",
    "Unemployed": "unemployed",
    "Student": "students",
    "Retired": "retired",
    "Sick Leave": "non gainfully employed",
    "Other": "non gainfully employed",
}

# Pipeline age group -> TabVX13InkStruktN age-band *code* (the parser keys on
# codes; SCB's labels changed typography between fetches). A list for the
# explorer embed script, which resolves the first candidate present.
_AGE_GROUP_TO_INC_AGE: dict[str, list[str]] = {
    "18-24": ["20-29"],
    "25-34": ["20-29"],
    "35-44": ["30-49"],
    "45-54": ["30-49"],
    "55-64": ["50-64"],
    "65-74": ["65-79"],
    "75-85": ["80-"],
}

# Only the register "Employed" status gates industry_sector (Step 6) and
# employment_type (Step 7); the other five statuses are out of employment.
_EMPLOYED_STATUSES: set[str] = {"Employed"}

_SWEDEN_LABELS: set[str] = {
    "Sverige", "Sweden",
    "Born in Sweden", "born in Sweden",
    "Födda i Sverige", "födda i Sverige",
}


# Declared fallback for income_source cells the SCB table (TabVX13InkStruktN) does not
# deliver. The table has no "students" cell for the 65-79 and 80- bands, but the
# register employment_status distribution still gives students aged 65
# and over a small non-zero share (about 0.1% of those ages, i.e. about 10 of 10,000
# individuals). Without a rule the sampler would raise for them. Rule, applied ONLY for
# the (income employment category, pipeline age group) pairs listed here: use the same
# category's mix for the nearest lower pipeline age group that has a cell, here the 55-64
# group (income band 50-64). It is an assumption, not an SCB figure; it is explicit so the
# choice stays visible and testable. Every other missing cell still raises (fail-fast).
# The unemployed 75-85 cell (band 80-) is also absent from the table, but the register
# employment distribution gives unemployed individuals aged 65 and over probability exactly
# 0, so it is never drawn and needs no entry.
_INCOME_SOURCE_AGE_FALLBACK: dict[tuple[str, str], str] = {
    ("students", "65-74"): "55-64",
    ("students", "75-85"): "55-64",
}


def _resolve_inc_age_key(age_group: str, emp_dist: dict) -> str | None:
    candidates = _AGE_GROUP_TO_INC_AGE.get(age_group, [])
    for cand in candidates:
        if cand in emp_dist:
            return cand
    return None


def _require_cell(table: dict, key: tuple, table_name: str) -> dict:
    """Return ``table[key]``; raise if the cell is absent or empty (no fallback)."""
    dist = table.get(key)
    if not dist:
        raise ValueError(f"No {table_name} distribution for cell {key!r}")
    return dist


class SampleService:
    @staticmethod
    def sample_one(
        distributions: PopulationDistributions,
        rng: Generator,
        individual_id: int,
    ) -> dict:
        # Step 1: joint (age, biological_sex)
        age_sex_keys = list(distributions.age_sex.keys())
        age_sex_probs = np.array([distributions.age_sex[k] for k in age_sex_keys], dtype=float)
        age_sex_probs /= age_sex_probs.sum()
        chosen_idx = rng.choice(len(age_sex_keys), p=age_sex_probs)
        age, sex_label = age_sex_keys[chosen_idx]
        age_group = age_to_group(age)
        sex_code = _SEX_CODES.get(sex_label, "")
        cell = (age_group, sex_label)

        # Step 2: education | (age_group, sex_label)
        edu_dist = _require_cell(distributions.education_by_age, cell, "education")
        education_level = sample_from(rng, edu_dist)

        # Step 3: employment_status -- register labour status over the full
        #         spectrum (employed/unemployed/students/retirees/sick/others),
        #         conditioned on (age_group, sex) from the single register table.
        emp_dist = _require_cell(distributions.employment_by_sex_education, cell, "employment_status")
        employment_status_label = sample_from(rng, emp_dist)
        is_employed = employment_status_label in _EMPLOYED_STATUSES

        # Step 4: birth_location -- conditional on (age_group, sex_label);
        #         region conditional on (age_group, sex_label); parental_structure
        #         marginal; socioeconomic conditional
        bl_dist = _require_cell(distributions.birth_location, cell, "birth_location")
        birth_location_label = sample_from(rng, bl_dist)
        region_dist = _require_cell(distributions.region_by_age_sex or {}, cell, "region")
        region_label = sample_from(rng, region_dist)
        parental_structure_label = sample_from(rng, distributions.parental_structure)

        se_dist = _require_cell(distributions.socioeconomic, cell, "socioeconomic")
        socioeconomic_label = sample_from(rng, se_dist)

        # Step 5: civil_status -- conditional on (age_group, sex_label)
        cs_dist = _require_cell(distributions.civil_status_by_age_sex, cell, "civil_status")
        civil_status_label = sample_from(rng, cs_dist)

        # Step 6: industry_sector -- conditional on employment and (age_group, sex)
        industry_sector_raw: dict | None
        if is_employed:
            ind_dist = _require_cell(distributions.industry_sector, cell, "industry_sector")
            industry_sector_label = sample_from(rng, ind_dist)
            industry_sector_raw = {"label": industry_sector_label}
        else:
            industry_sector_raw = None

        # Step 7: employment_type -- conditional on (age_group, sex_label). The
        #         18-24 and 75-85 cells are the declared AKU age proxies built in
        #         the fetch layer (AKU covers ages 15-74 and publishes attachment
        #         at 15-24, not 18-24).
        employment_type_raw: dict | None
        if is_employed:
            emp_type_dist = _require_cell(distributions.employment_type_by_age, cell, "employment_type")
            composite_key = sample_from(rng, emp_type_dist)
            att_label, hrs_label = composite_key.split("|", 1)
            employment_type_raw = {
                "attachment": {"label": att_label},
                "hours": {"label": hrs_label},
            }
        else:
            employment_type_raw = None

        # Step 8: housing_tenure -- conditional on (age_group, sex_label)
        ht_dist = _require_cell(distributions.housing_tenure, cell, "housing_tenure")
        housing_tenure_label = sample_from(rng, ht_dist)

        # Step 9: household_size -- marginal
        household_size_label = sample_from(rng, distributions.household_size)

        # Step 10: income_source -- conditional on (employment_status, age_group)
        inc_emp_key = _STATUS_TO_INC_EMP.get(employment_status_label)
        if inc_emp_key is None:
            raise ValueError(f"No income_source employment mapping for: {employment_status_label!r}")
        matched_emp_dist = {
            age_k: d
            for (emp_k, age_k), d in distributions.income_source_by_employment_age.items()
            if emp_k == inc_emp_key and d
        }
        if not matched_emp_dist:
            raise ValueError(f"No income_source distribution for employment={inc_emp_key!r}")
        inc_age_key = _resolve_inc_age_key(age_group, matched_emp_dist)
        if inc_age_key is None:
            fallback_group = _INCOME_SOURCE_AGE_FALLBACK.get((inc_emp_key, age_group))
            if fallback_group is not None:
                inc_age_key = _resolve_inc_age_key(fallback_group, matched_emp_dist)
        if inc_age_key is None:
            raise ValueError(
                f"No income_source distribution for cell (employment={inc_emp_key!r}, "
                f"age_group={age_group!r}); available age keys: {sorted(matched_emp_dist)}"
            )
        inc_src_dist = matched_emp_dist[inc_age_key]
        income_source_label = sample_from(rng, inc_src_dist)

        # Step 11: birth_country_detail -- conditional on (age_group, sex_label) and birth_location
        birth_country_raw: dict
        if birth_location_label in _SWEDEN_LABELS:
            birth_country_raw = {"label": birth_location_label}
        else:
            bc_dist = _require_cell(distributions.birth_country_detail, cell, "birth_country_detail")
            birth_country_detail_label = sample_from(rng, bc_dist)
            if birth_country_detail_label in _SWEDEN_LABELS:
                non_sweden = {k: v for k, v in bc_dist.items() if k not in _SWEDEN_LABELS}
                if non_sweden:
                    birth_country_detail_label = sample_from(rng, non_sweden)
            birth_country_raw = {"label": birth_country_detail_label}

        return {
            "id": individual_id,
            "age": age,
            "biological_sex": {"code": sex_code, "label": sex_label} if sex_code else {"label": sex_label},
            "education_level": {"label": education_level},
            "employment_status": {"label": employment_status_label},
            "socioeconomic_class": {"label": socioeconomic_label},
            "birth_location": {"label": birth_location_label},
            "region": {"label": region_label},
            "civil_status": {"label": civil_status_label},
            "industry_sector": industry_sector_raw,
            "employment_type": employment_type_raw,
            "housing_tenure": {"label": housing_tenure_label},
            "household_size": {"label": household_size_label},
            "income_source": {"label": income_source_label},
            "birth_country_detail": birth_country_raw,
            "parental_structure": {"label": parental_structure_label},
        }

    @staticmethod
    def sample_population(
        distributions: PopulationDistributions,
        rng: Generator,
        n: int,
    ) -> list[dict]:
        return [
            SampleService.sample_one(distributions, rng, i)
            for i in range(n)
        ]

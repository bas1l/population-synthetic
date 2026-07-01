"""Conditionally samples one individual from Swedish distributions.

Draws a single synthetic person from the ``PopulationDistributions``
produced by the Sweden fetch service via a deterministic chained
sampling sequence, where each attribute is conditioned on prior draws
(e.g. education given age and sex, employment given education).
"""
from __future__ import annotations

import numpy as np
from numpy.random import Generator

from population_synthetic.population.data import PopulationDistributions
from population_synthetic.population.helpers import VALID_AGE_GROUPS, age_to_group, sample_from

_SEX_CODES: dict[str, str] = {"men": "1", "women": "2"}

_SUN2020_TO_AKU_EDU: dict[str, str] = {
    "förgymnasial utbildning kortare än 9 år": "förgymnasial utbildning",
    "förgymnasial utbildning, 9 (10) år": "förgymnasial utbildning",
    "gymnasial utbildning, högst 2 år": "gymnasial utbildning",
    "gymnasial utbildning, 3 år": "gymnasial utbildning",
    "eftergymnasial utbildning, kortare än 3 år": "eftergymnasial utbildning",
    "eftergymnasial utbildning, 3 år eller längre": "eftergymnasial utbildning",
    "forskarutbildning": "eftergymnasial utbildning",
    "uppgift saknas": "förgymnasial utbildning",
    "primary and secondary education less than 9 years (isced97 1)": "primary and lower secondary education",
    "primary and secondary education 9-10 years (isced97 2)": "primary and lower secondary education",
    "upper secondary education, 2 years or less (isced97 3c)": "upper secondary education",
    "upper secondary education 3 years (isced97 3a)": "upper secondary education",
    "post-secondary education, less than 3 years (isced97 4+5b)": "post secondary education",
    "post-secondary education 3 years or more (isced97 5a)": "post secondary education",
    "post-graduate education (isced97 6)": "post secondary education",
    "no information about level of educational attainment": "primary and lower secondary education",
}

_AKU_TO_INC_EMP: dict[str, str] = {
    "sysselsatta": "gainfully employed",
    "employed": "gainfully employed",
    "in employment": "gainfully employed",
    "employed, thousands": "gainfully employed",
    "arbetslösa": "unemployed",
    "unemployed": "unemployed",
    "unemployed, thousands": "unemployed",
    "ej i arbetskraften - studerande": "students",
    "not in labour force - students": "students",
    "ej i arbetskraften - pensionärer": "retired",
    "not in labour force - retired": "retired",
    "ej i arbetskraften": "non gainfully employed",
    "not in the labour force": "non gainfully employed",
    "not in the labour force, thousands": "non gainfully employed",
    "ej i arbetskraften - övriga": "non gainfully employed",
    "not in labour force - other": "non gainfully employed",
}

_AGE_GROUP_TO_INC_AGE: dict[str, list[str]] = {
    "18-24": ["20-29", "20-29 years", "20-29 år"],
    "25-34": ["20-29", "20-29 years", "20-29 år"],
    "35-44": ["30-49", "30-49 years", "30-49 år"],
    "45-54": ["30-49", "30-49 years", "30-49 år"],
    "55-64": ["50-64", "50-64 years", "50-64 år"],
    "65-74": ["65-79", "65-79 years", "65-79 år"],
    "75-85": ["80-", "80- years", "80- år"],
}

_IS_EMPLOYED_AKU: set[str] = {
    "sysselsatta", "employed", "in employment", "employed, thousands",
}

_SWEDEN_LABELS: set[str] = {
    "Sverige", "Sweden",
    "Born in Sweden", "born in Sweden",
    "Födda i Sverige", "födda i Sverige",
}


def _resolve_edu_key(education_level: str, sex_dists: dict) -> str | None:
    if education_level in sex_dists:
        return education_level
    mapped = _SUN2020_TO_AKU_EDU.get(education_level)
    if mapped and mapped in sex_dists:
        return mapped
    edu_lower = education_level.lower()
    mapped = _SUN2020_TO_AKU_EDU.get(edu_lower)
    if mapped and mapped in sex_dists:
        return mapped
    for key in sex_dists:
        if key.lower() == edu_lower:
            return key
    return None


def _resolve_inc_age_key(age_group: str, emp_dist: dict) -> str | None:
    candidates = _AGE_GROUP_TO_INC_AGE.get(age_group, [])
    for cand in candidates:
        if cand in emp_dist:
            return cand
    return None


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

        # Step 2: education | (age_group, sex_label)
        edu_dist = distributions.education_by_age.get((age_group, sex_label))
        if edu_dist is None:
            all_sexes = {s for (_, s) in distributions.education_by_age}
            for fallback_sex in all_sexes:
                edu_dist = distributions.education_by_age.get((age_group, fallback_sex))
                if edu_dist is not None:
                    break
        if edu_dist is None:
            for fallback_ag in reversed(list(VALID_AGE_GROUPS)):
                edu_dist = distributions.education_by_age.get((fallback_ag, sex_label))
                if edu_dist is not None:
                    break
        if edu_dist is None:
            raise ValueError(
                f"No education distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        education_level = sample_from(rng, edu_dist)

        # Step 3: employment | (sex_label, education_level)
        sex_dists = distributions.employment_by_sex_education.get(sex_label, {})
        edu_key = _resolve_edu_key(education_level, sex_dists)
        if edu_key is None:
            for fallback_sex in distributions.employment_by_sex_education:
                if fallback_sex == sex_label:
                    continue
                opp_dists = distributions.employment_by_sex_education[fallback_sex]
                edu_key = _resolve_edu_key(education_level, opp_dists)
                if edu_key is not None:
                    sex_dists = opp_dists
                    break
        if edu_key is None:
            raise ValueError(
                f"No employment distribution for sex={sex_label!r}, "
                f"education={education_level!r}"
            )
        emp_dist = sex_dists[edu_key]
        employment_status_label = sample_from(rng, emp_dist)
        is_employed = employment_status_label in _IS_EMPLOYED_AKU

        # Step 4: remaining marginals (birth_location, region, parental_structure) +
        #         socioeconomic -- conditional on (age_group, sex_label)
        birth_location_label = sample_from(rng, distributions.birth_location)
        region_label = sample_from(rng, distributions.region)
        parental_structure_label = sample_from(rng, distributions.parental_structure)

        se_dist = distributions.socioeconomic.get((age_group, sex_label))
        if se_dist is None:
            for fallback_sex in {s for (_, s) in distributions.socioeconomic}:
                se_dist = distributions.socioeconomic.get((age_group, fallback_sex))
                if se_dist is not None:
                    break
        if se_dist is None:
            raise ValueError(
                f"No socioeconomic distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        socioeconomic_label = sample_from(rng, se_dist)

        # Step 5: civil_status -- conditional on (age_group, sex_label)
        cs_dist = distributions.civil_status_by_age_sex.get((age_group, sex_label), {})
        if not cs_dist:
            for fallback_sex in {s for (_, s) in distributions.civil_status_by_age_sex}:
                cs_dist = distributions.civil_status_by_age_sex.get((age_group, fallback_sex), {})
                if cs_dist:
                    break
        if not cs_dist:
            raise ValueError(f"No civil_status distribution for age_group={age_group}, sex={sex_label}")
        civil_status_label = sample_from(rng, cs_dist)

        # Step 6: industry_sector -- conditional on employment
        industry_sector_raw: dict | None
        if is_employed:
            industry_sector_label = sample_from(rng, distributions.industry_sector)
            industry_sector_raw = {"label": industry_sector_label}
        else:
            industry_sector_raw = None

        # Step 7: employment_type -- conditional on (age_group, sex_label)
        employment_type_raw: dict | None
        if is_employed:
            emp_type_dist = distributions.employment_type_by_age.get((age_group, sex_label), {})
            if not emp_type_dist:
                for fallback_sex in {s for (_, s) in distributions.employment_type_by_age}:
                    emp_type_dist = distributions.employment_type_by_age.get((age_group, fallback_sex), {})
                    if emp_type_dist:
                        break
            if not emp_type_dist:
                for fallback_ag in reversed(list(VALID_AGE_GROUPS)):
                    emp_type_dist = distributions.employment_type_by_age.get((fallback_ag, sex_label), {})
                    if emp_type_dist:
                        break
            if not emp_type_dist:
                raise ValueError(
                    f"No employment_type distribution for age_group={age_group!r}, sex={sex_label!r}"
                )
            composite_key = sample_from(rng, emp_type_dist)
            att_label, hrs_label = composite_key.split("|", 1)
            employment_type_raw = {
                "attachment": {"label": att_label},
                "hours": {"label": hrs_label},
            }
        else:
            employment_type_raw = None

        # Step 8: housing_tenure -- marginal
        housing_tenure_label = sample_from(rng, distributions.housing_tenure)

        # Step 9: household_size -- marginal
        household_size_label = sample_from(rng, distributions.household_size)

        # Step 10: income_source -- conditional on (employment_status, age_group)
        inc_emp_key = _AKU_TO_INC_EMP.get(employment_status_label)
        if inc_emp_key is None:
            raise ValueError(f"No income_source employment mapping for: {employment_status_label!r}")
        inc_age_key: str | None = None
        inc_emp_dist = distributions.income_source_by_employment_age
        matched_emp_dist = {age_k: d for (emp_k, age_k), d in inc_emp_dist.items() if emp_k == inc_emp_key}
        if not matched_emp_dist:
            for (emp_k, age_k), d in inc_emp_dist.items():
                if d:
                    matched_emp_dist = {age_k: d}
                    break
        if not matched_emp_dist:
            raise ValueError(
                f"No income_source distribution for employment={inc_emp_key!r}"
            )
        inc_age_key = _resolve_inc_age_key(age_group, matched_emp_dist)
        if inc_age_key is None:
            inc_age_key = next(iter(matched_emp_dist))
        inc_src_dist = matched_emp_dist[inc_age_key]
        income_source_label = sample_from(rng, inc_src_dist)

        # Step 11: birth_country_detail -- conditional on (age_group, sex_label) and birth_location
        birth_country_raw: dict
        if birth_location_label in _SWEDEN_LABELS:
            birth_country_raw = {"label": birth_location_label}
        else:
            bc_dist = distributions.birth_country_detail.get((age_group, sex_label))
            if bc_dist is None:
                for fallback_sex in {s for (_, s) in distributions.birth_country_detail}:
                    bc_dist = distributions.birth_country_detail.get((age_group, fallback_sex))
                    if bc_dist is not None:
                        break
            if bc_dist is None:
                raise ValueError(
                    f"No birth_country_detail distribution for age_group={age_group!r}, sex={sex_label!r}"
                )
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
        return [SampleService.sample_one(distributions, rng, i) for i in range(n)]

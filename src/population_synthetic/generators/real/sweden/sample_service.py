"""Conditionally samples one individual from Swedish distributions.

Draws a single synthetic person from the ``PopulationDistributions``
produced by the Sweden fetch service via a deterministic chained
sampling sequence, where each attribute is conditioned on prior draws
(e.g. education given age and sex, employment given education).
"""
from __future__ import annotations

import numpy as np
from numpy.random import Generator

from population_synthetic.generators.real.data import PopulationDistributions
from population_synthetic.generators.real.helpers import VALID_AGE_GROUPS, age_to_group, sample_from

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

_AGE_GROUP_TO_INC_AGE: dict[str, list[str]] = {
    "18-24": ["20-29", "20-29 years", "20-29 år"],
    "25-34": ["20-29", "20-29 years", "20-29 år"],
    "35-44": ["30-49", "30-49 years", "30-49 år"],
    "45-54": ["30-49", "30-49 years", "30-49 år"],
    "55-64": ["50-64", "50-64 years", "50-64 år"],
    "65-74": ["65-79", "65-79 years", "65-79 år"],
    "75-85": ["80-", "80- years", "80- år"],
}

# Only the register "Employed" status gates industry_sector (Step 6) and
# employment_type (Step 7); the other five statuses are out of employment.
_EMPLOYED_STATUSES: set[str] = {"Employed"}

_SWEDEN_LABELS: set[str] = {
    "Sverige", "Sweden",
    "Born in Sweden", "born in Sweden",
    "Födda i Sverige", "födda i Sverige",
}


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
        merge_status_education: bool = False,
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

        # Step 3: employment_status -- register labour status over the full
        #         spectrum (employed/unemployed/students/retirees/sick/others).
        #
        # Default (merge OFF): conditioned on (age_group, sex) only -- the Phase-4
        # single-table path. When the opt-in all-register MERGE is on, it is
        # conditioned on (age_group, education, sex): the status<->education link is
        # recovered from a SECOND register table (ArbStatusUtbM) via the documented
        # odds-multiplication derivation. ASSUMPTION (merge only): no status x age x
        # education interaction -- a documented derivation over real register
        # margins, NOT a synthetic distribution (see the merge spec and
        # parse_employment_status_combined). Falls back to the age x sex leg when a
        # given (age, education, sex) cell is unavailable.
        emp_dist = None
        if merge_status_education and distributions.employment_status_by_edu is not None:
            edu_key = education_level.casefold()
            emp_by_edu = distributions.employment_status_by_edu
            emp_dist = emp_by_edu.get((age_group, edu_key, sex_label))
            if emp_dist is None:
                for fallback_sex in {s for (_, _e, s) in emp_by_edu}:
                    emp_dist = emp_by_edu.get((age_group, edu_key, fallback_sex))
                    if emp_dist is not None:
                        break
        if emp_dist is None:
            emp_dist = distributions.employment_by_sex_education.get((age_group, sex_label))
        if emp_dist is None:
            for fallback_sex in {s for (_, s) in distributions.employment_by_sex_education}:
                emp_dist = distributions.employment_by_sex_education.get((age_group, fallback_sex))
                if emp_dist is not None:
                    break
        if emp_dist is None:
            raise ValueError(
                f"No employment_status distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        employment_status_label = sample_from(rng, emp_dist)
        is_employed = employment_status_label in _EMPLOYED_STATUSES

        # Step 4: birth_location -- conditional on (age_group, sex_label);
        #         region + parental_structure marginal; socioeconomic conditional
        bl_dist = distributions.birth_location.get((age_group, sex_label))
        if bl_dist is None:
            for fallback_sex in {s for (_, s) in distributions.birth_location}:
                bl_dist = distributions.birth_location.get((age_group, fallback_sex))
                if bl_dist is not None:
                    break
        if bl_dist is None:
            raise ValueError(
                f"No birth_location distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        birth_location_label = sample_from(rng, bl_dist)
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

        # Step 6: industry_sector -- conditional on employment and (age_group, sex)
        industry_sector_raw: dict | None
        if is_employed:
            ind_dist = distributions.industry_sector.get((age_group, sex_label))
            if ind_dist is None:
                for fallback_sex in {s for (_, s) in distributions.industry_sector}:
                    ind_dist = distributions.industry_sector.get((age_group, fallback_sex))
                    if ind_dist is not None:
                        break
            if ind_dist is None:
                raise ValueError(
                    f"No industry_sector distribution for age_group={age_group!r}, sex={sex_label!r}"
                )
            industry_sector_label = sample_from(rng, ind_dist)
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

        # Step 8: housing_tenure -- conditional on (age_group, sex_label)
        ht_dist = distributions.housing_tenure.get((age_group, sex_label))
        if ht_dist is None:
            for fallback_sex in {s for (_, s) in distributions.housing_tenure}:
                ht_dist = distributions.housing_tenure.get((age_group, fallback_sex))
                if ht_dist is not None:
                    break
        if ht_dist is None:
            raise ValueError(
                f"No housing_tenure distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        housing_tenure_label = sample_from(rng, ht_dist)

        # Step 9: household_size -- marginal
        household_size_label = sample_from(rng, distributions.household_size)

        # Step 10: income_source -- conditional on (employment_status, age_group)
        inc_emp_key = _STATUS_TO_INC_EMP.get(employment_status_label)
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
        merge_status_education: bool = False,
    ) -> list[dict]:
        return [
            SampleService.sample_one(distributions, rng, i, merge_status_education)
            for i in range(n)
        ]

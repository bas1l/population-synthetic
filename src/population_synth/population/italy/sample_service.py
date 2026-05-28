"""
ISTATSampleService — conditionally samples one individual from Italian
``PopulationDistributions`` produced by ``ISTATFetchService``.

Sampling chain (10 steps, deterministic given ``rng``):
  1. Joint (age, sex)                       — from age_sex
  2. Education | (age_group, sex)           — from education_by_age
  3. Employment | (sex, education)          — from employment_by_sex_education
  4. Marginals: birth_location, region,     — independent draws
               parental; socioeconomic | (age_group, sex)
  5. Civil status | (age_group, sex)        — from civil_status_by_age_sex
  6. Industry sector (employed only)        — from industry_sector
  7. Employment type | (age_group, sex)     — from employment_type_by_age (employed only)
  8. Housing tenure                         — marginal
  9. Household size                         — marginal
 10. Birth country detail | (age, sex)      — from birth_country_detail (non-Italy only)
"""

from __future__ import annotations

import numpy as np
from numpy.random import Generator

from population_synth.population.data import PopulationDistributions
from population_synth.population.helpers import VALID_AGE_GROUPS, age_to_group, sample_from

# ---------------------------------------------------------------------------
# Italian sex codes (ISTAT SDMX uses same codes as SSB)
# ---------------------------------------------------------------------------
_ISTAT_SEX_CODES: dict[str, str] = {"Male": "1", "Female": "2"}

# ---------------------------------------------------------------------------
# Education label bridge:
# education_by_age (52_1194) → employment_by_sex_education (150_938)
# Both tables normalise to the same schema labels so the map is identity.
# ---------------------------------------------------------------------------
_ISTAT_EDU_TO_EMP_EDU: dict[str, str] = {
    "No Formal Education": "No Formal Education",
    "High School (Liceo/Professionale)": "High School (Liceo/Professionale)",
    "University Degree": "University Degree",
}

# Employment statuses that are considered "in employment" for ISTAT data
_IS_EMPLOYED_ISTAT: set[str] = {"Employed"}

# Birth location labels that mean "born in Italy" — no foreign-born detail needed
_ITALY_LABELS: set[str] = {"Italy"}


# ---------------------------------------------------------------------------
# Key-resolution helpers
# ---------------------------------------------------------------------------

def _resolve_edu_key(education_level: str, sex_dists: dict) -> str | None:
    """Return the education key present in ``sex_dists`` that corresponds to
    ``education_level``.  Tries direct lookup, then the normalisation map,
    then case-insensitive match.
    """
    if education_level in sex_dists:
        return education_level
    mapped = _ISTAT_EDU_TO_EMP_EDU.get(education_level)
    if mapped and mapped in sex_dists:
        return mapped
    edu_lower = education_level.lower()
    mapped_lower = _ISTAT_EDU_TO_EMP_EDU.get(edu_lower)
    if mapped_lower and mapped_lower in sex_dists:
        return mapped_lower
    for key in sex_dists:
        if key.lower() == edu_lower:
            return key
    return None


# ---------------------------------------------------------------------------
# ISTATSampleService
# ---------------------------------------------------------------------------

class ISTATSampleService:
    """Conditional sampler for Italian ISTAT ``PopulationDistributions``."""

    @staticmethod
    def sample_one(
        distributions: PopulationDistributions,
        rng: Generator,
        individual_id: int,
    ) -> dict:
        # ------------------------------------------------------------------
        # Step 1: joint (age, sex)
        # ------------------------------------------------------------------
        age_sex_keys = list(distributions.age_sex.keys())
        age_sex_probs = np.array(
            [distributions.age_sex[k] for k in age_sex_keys], dtype=float
        )
        age_sex_probs /= age_sex_probs.sum()
        chosen_idx = rng.choice(len(age_sex_keys), p=age_sex_probs)
        age, sex_label = age_sex_keys[chosen_idx]
        age_group = age_to_group(age)
        sex_code = _ISTAT_SEX_CODES.get(sex_label, "")

        # ------------------------------------------------------------------
        # Step 2: education | (age_group, sex)
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Step 3: employment | (sex, education)
        # ------------------------------------------------------------------
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
        is_employed = employment_status_label in _IS_EMPLOYED_ISTAT

        # ------------------------------------------------------------------
        # Step 4: marginals + socioeconomic | (age_group, sex_label)
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Step 5: civil status | (age_group, sex)
        # ------------------------------------------------------------------
        cs_dist = distributions.civil_status_by_age_sex.get((age_group, sex_label), {})
        if not cs_dist:
            for fallback_sex in {s for (_, s) in distributions.civil_status_by_age_sex}:
                cs_dist = distributions.civil_status_by_age_sex.get(
                    (age_group, fallback_sex), {}
                )
                if cs_dist:
                    break
        if not cs_dist:
            raise ValueError(
                f"No civil_status distribution for age_group={age_group!r}, sex={sex_label!r}"
            )
        civil_status_label = sample_from(rng, cs_dist)

        # ------------------------------------------------------------------
        # Step 6: industry sector (employed persons only)
        # ------------------------------------------------------------------
        industry_sector_raw: dict | None
        if is_employed:
            industry_sector_label = sample_from(rng, distributions.industry_sector)
            industry_sector_raw = {"label": industry_sector_label}
        else:
            industry_sector_raw = None

        # ------------------------------------------------------------------
        # Step 7: employment type | (age_group, sex) — employed persons only
        # ------------------------------------------------------------------
        employment_type_raw: dict | None
        if is_employed:
            emp_type_dist = distributions.employment_type_by_age.get(
                (age_group, sex_label), {}
            )
            if not emp_type_dist:
                for fallback_sex in {s for (_, s) in distributions.employment_type_by_age}:
                    emp_type_dist = distributions.employment_type_by_age.get(
                        (age_group, fallback_sex), {}
                    )
                    if emp_type_dist:
                        break
            if not emp_type_dist:
                for fallback_ag in reversed(list(VALID_AGE_GROUPS)):
                    emp_type_dist = distributions.employment_type_by_age.get(
                        (fallback_ag, sex_label), {}
                    )
                    if emp_type_dist:
                        break
            if not emp_type_dist:
                raise ValueError(
                    f"No employment_type distribution for age_group={age_group!r}, "
                    f"sex={sex_label!r}"
                )
            composite_key = sample_from(rng, emp_type_dist)
            contract_label, hours_label = composite_key.split("|", 1)
            employment_type_raw = {
                "attachment": {"label": contract_label},
                "hours": {"label": hours_label},
            }
        else:
            employment_type_raw = None

        # ------------------------------------------------------------------
        # Step 8: housing tenure — marginal
        # ------------------------------------------------------------------
        housing_tenure_label = sample_from(rng, distributions.housing_tenure)

        # ------------------------------------------------------------------
        # Step 9: household size — marginal
        # ------------------------------------------------------------------
        household_size_label = sample_from(rng, distributions.household_size)

        # ------------------------------------------------------------------
        # Step 10: birth country detail | (age_group, sex)
        #          Only sampled for non-Italy-born individuals.
        # ------------------------------------------------------------------
        birth_country_raw: dict
        if birth_location_label in _ITALY_LABELS:
            birth_country_raw = {"label": birth_location_label}
        else:
            bc_dist = distributions.birth_country_detail.get((age_group, sex_label))
            if bc_dist is None:
                for fallback_sex in {s for (_, s) in distributions.birth_country_detail}:
                    bc_dist = distributions.birth_country_detail.get(
                        (age_group, fallback_sex)
                    )
                    if bc_dist is not None:
                        break
            if bc_dist is None:
                raise ValueError(
                    f"No birth_country_detail distribution for "
                    f"age_group={age_group!r}, sex={sex_label!r}"
                )
            birth_country_detail_label = sample_from(rng, bc_dist)
            if birth_country_detail_label in _ITALY_LABELS:
                non_italy = {
                    k: v for k, v in bc_dist.items() if k not in _ITALY_LABELS
                }
                if non_italy:
                    birth_country_detail_label = sample_from(rng, non_italy)
            birth_country_raw = {"label": birth_country_detail_label}

        # ------------------------------------------------------------------
        # Assemble individual record
        # ------------------------------------------------------------------
        return {
            "id": individual_id,
            "age": age,
            "biological_sex": (
                {"code": sex_code, "label": sex_label}
                if sex_code
                else {"label": sex_label}
            ),
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
            "birth_country_detail": birth_country_raw,
            "parental_structure": {"label": parental_structure_label},
        }

    @staticmethod
    def sample_population(
        distributions: PopulationDistributions,
        rng: Generator,
        n: int,
    ) -> list[dict]:
        """Sample ``n`` individuals from ``distributions``.

        Deterministic given the same ``rng`` state.
        """
        return [ISTATSampleService.sample_one(distributions, rng, i) for i in range(n)]

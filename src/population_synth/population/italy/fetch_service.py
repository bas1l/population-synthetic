from __future__ import annotations

import logging

from population_synth.clients.eurostat_client import EurostatClient
from population_synth.clients.istat_client import ISTATSDMXClient
from population_synth.population.data import PopulationDistributions

from .constants import (
    EUROSTAT_AGE_SEX_DATASET,
    EUROSTAT_BIRTH_LOCATION_DATASET,
    EUROSTAT_HOUSING_TENURE_DATASET,
    EUROSTAT_REGION_DATASET,
    ISTAT_CIVIL_STATUS_DATAFLOW,
    ISTAT_EDUCATION_DATAFLOW,
    ISTAT_EMPLOYMENT_DATAFLOW,
    ISTAT_HOUSEHOLD_DATAFLOW,
)
from .parsers import (
    parse_age_sex,
    parse_birth_country_detail,
    parse_birth_location,
    parse_civil_status_by_age_sex,
    parse_education_by_age,
    parse_employment_by_sex_education,
    parse_employment_type_by_age,
    parse_household_size,
    parse_housing_tenure,
    parse_income_source,
    parse_industry_sector,
    parse_region,
    parse_socioeconomic,
)

_ITALY_PARENTAL_STRUCTURE_APPROX: dict[str, float] = {
    "Nuclear Family": 0.28,
    "Single Parent": 0.09,
    "Couple without Children": 0.30,
    "Living Alone": 0.33,
}

logger = logging.getLogger(__name__)


class ISTATFetchService:
    """Fetch service for Italian ISTAT/Eurostat demographic data.

    All methods are static and return ``(distribution_dict, dataset_tag)``.
    """

    @staticmethod
    def fetch_age_sex(eurostat_client: EurostatClient) -> tuple[dict, str]:
        """Fetch population by single-year age and sex from Eurostat ``demo_pjan``."""
        raw = eurostat_client.fetch_dataset(
            EUROSTAT_AGE_SEX_DATASET,
            params={"sinceTimePeriod": "2023"},
        )
        return parse_age_sex(raw), EUROSTAT_AGE_SEX_DATASET

    @staticmethod
    def fetch_region(eurostat_client: EurostatClient) -> tuple[dict, str]:
        """Fetch population by NUTS2 region from Eurostat ``demo_r_pjangrp3``.

        Falls back to ``demo_r_d2jan`` if the primary dataset cannot be parsed
        (e.g., missing Italian NUTS2 codes or API failure), logging a WARNING.
        """
        primary = EUROSTAT_REGION_DATASET
        fallback = "demo_r_d2jan"
        try:
            raw = eurostat_client.fetch_dataset(
                primary,
                params={"sinceTimePeriod": "2022", "precision": "1"},
            )
            result = parse_region(raw)
            return result, primary
        except Exception as exc:
            logger.warning(
                "ISTATFetchService.fetch_region: primary dataset %s failed (%s). "
                "Retrying with fallback dataset %s.",
                primary,
                exc,
                fallback,
            )
            raw = eurostat_client.fetch_dataset(
                fallback,
                params={"sinceTimePeriod": "2022", "precision": "1"},
            )
            result = parse_region(raw)
            return result, fallback

    @staticmethod
    def fetch_housing_tenure(eurostat_client: EurostatClient) -> tuple[dict, str]:
        """Fetch housing tenure distribution from Eurostat ``ilc_lvho02``."""
        raw = eurostat_client.fetch_dataset(
            EUROSTAT_HOUSING_TENURE_DATASET,
            params={"sinceTimePeriod": "2020"},
        )
        return parse_housing_tenure(raw), EUROSTAT_HOUSING_TENURE_DATASET

    # -----------------------------------------------------------------------
    # ISTAT SDMX fetch methods
    # -----------------------------------------------------------------------

    @staticmethod
    def fetch_education_by_age(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch education by age/sex from ISTAT ``52_1194_DF_DCCV_POPTIT1_UNT2020_1``."""
        raw = istat_client.fetch_data(
            ISTAT_EDUCATION_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_education_by_age(raw), ISTAT_EDUCATION_DATAFLOW

    @staticmethod
    def fetch_employment_by_sex_education(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch employment by sex/education from ISTAT ``150_938``."""
        raw = istat_client.fetch_data(
            ISTAT_EMPLOYMENT_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_employment_by_sex_education(raw), ISTAT_EMPLOYMENT_DATAFLOW

    @staticmethod
    def fetch_socioeconomic(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch socioeconomic distribution from ISTAT ``32_292``."""
        raw = istat_client.fetch_data(
            ISTAT_HOUSEHOLD_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_socioeconomic(raw), ISTAT_HOUSEHOLD_DATAFLOW

    @staticmethod
    def fetch_civil_status_by_age_sex(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch civil status by age/sex from ISTAT ``22_289_DF_DCIS_POPRES1_25``.

        Uses a tight key filter to reduce response size and limit timeout risk.
        Raises ``RuntimeError`` on fetch failure — this endpoint is known to be slow.
        """
        try:
            raw = istat_client.fetch_data(
                ISTAT_CIVIL_STATUS_DATAFLOW,
                key_filter="A.IT..........",
                params={"startPeriod": "2022", "endPeriod": "2023"},
            )
            return parse_civil_status_by_age_sex(raw), ISTAT_CIVIL_STATUS_DATAFLOW
        except Exception as exc:
            raise RuntimeError(
                f"ISTAT civil status fetch failed: {exc}. "
                "This endpoint is known to timeout. "
                "Try clearing the cache and re-running, or skip this field."
            ) from exc

    @staticmethod
    def fetch_industry_sector(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch industry sector distribution from ISTAT ``150_938`` OCCUPATION_2011 dimension."""
        raw = istat_client.fetch_data(
            ISTAT_EMPLOYMENT_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_industry_sector(raw), ISTAT_EMPLOYMENT_DATAFLOW + "#industry"

    @staticmethod
    def fetch_employment_type_by_age(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch employment type by age/sex from ISTAT ``150_938`` FULL_PART_TIME × PERM_TEMP dimensions."""
        raw = istat_client.fetch_data(
            ISTAT_EMPLOYMENT_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_employment_type_by_age(raw), ISTAT_EMPLOYMENT_DATAFLOW + "#employment_type"

    @staticmethod
    def fetch_household_size(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch household size distribution from ISTAT ``32_292``."""
        raw = istat_client.fetch_data(
            ISTAT_HOUSEHOLD_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_household_size(raw), ISTAT_HOUSEHOLD_DATAFLOW + "#household_size"

    @staticmethod
    def fetch_income_source_by_employment_age(istat_client: ISTATSDMXClient) -> tuple[dict, str]:
        """Fetch income source by employment status/age from ISTAT ``32_292``."""
        raw = istat_client.fetch_data(
            ISTAT_HOUSEHOLD_DATAFLOW,
            params={"startPeriod": "2021", "endPeriod": "2023"},
        )
        return parse_income_source(raw), ISTAT_HOUSEHOLD_DATAFLOW + "#income_source"

    @staticmethod
    def fetch_birth_location(eurostat_client: EurostatClient) -> tuple[dict, str]:
        """Fetch birth-location proxy from Eurostat ``migr_pop1ctz`` citizenship dimension.

        Derives 3 categories: "Italy", "Europe (Other)", "Outside Europe".
        """
        raw = eurostat_client.fetch_dataset(
            EUROSTAT_BIRTH_LOCATION_DATASET,
            params={"sinceTimePeriod": "2022"},
        )
        return parse_birth_location(raw), EUROSTAT_BIRTH_LOCATION_DATASET

    @staticmethod
    def fetch_birth_country_detail(eurostat_client: EurostatClient) -> tuple[dict, str]:
        """Fetch top origin-country detail from Eurostat ``migr_pop1ctz``.

        Reuses the same dataset as ``fetch_birth_location`` — cache hit on second call.
        Returns marginal distribution expanded to all VALID_AGE_GROUPS × sex.
        """
        raw = eurostat_client.fetch_dataset(
            EUROSTAT_BIRTH_LOCATION_DATASET,
            params={"sinceTimePeriod": "2022"},
        )
        return parse_birth_country_detail(raw), EUROSTAT_BIRTH_LOCATION_DATASET + "#detail"

    @staticmethod
    def fetch_parental_structure(istat_client: ISTATSDMXClient) -> tuple[dict, str]:  # noqa: ARG004
        """Return Italian 2023 family structure approximation.

        No ISTAT dataflow provides household count by family type at national
        level. The approximation is based on ISTAT census data and is logged as
        a WARNING. The ``istat_client`` parameter is accepted for interface
        consistency but not used.
        """
        logger.warning(
            "ISTATFetchService.fetch_parental_structure: No ISTAT dataflow provides "
            "household count by family type at national level. Using Italian 2023 census "
            "approximation. This is intentional."
        )
        return dict(_ITALY_PARENTAL_STRUCTURE_APPROX), "istat_parental_structure#approximate"

    # -----------------------------------------------------------------------
    # Orchestration
    # -----------------------------------------------------------------------

    @staticmethod
    def load_all(
        eurostat_client: EurostatClient,
        istat_client: ISTATSDMXClient,
    ) -> PopulationDistributions:
        """Fetch all dimensions and construct a ``PopulationDistributions`` instance.

        The dual-client signature is an intentional divergence from the
        single-client pattern in Sweden/Norway: Italy requires two incompatible
        API protocols (Eurostat JSON-stat 2.0 + ISTAT SDMX-JSON 2.0).
        """
        logger.info("ISTATFetchService.load_all: starting fetch sequence")

        age_sex, tag_age_sex = ISTATFetchService.fetch_age_sex(eurostat_client)
        logger.info("  age_sex OK  (%d entries)", len(age_sex))

        education_by_age, tag_edu = ISTATFetchService.fetch_education_by_age(istat_client)
        logger.info("  education_by_age OK  (%d keys)", len(education_by_age))

        employment_by_sex_education, tag_emp = ISTATFetchService.fetch_employment_by_sex_education(istat_client)
        logger.info("  employment_by_sex_education OK  (%d sex keys)", len(employment_by_sex_education))

        birth_location, tag_birth = ISTATFetchService.fetch_birth_location(eurostat_client)
        logger.info("  birth_location OK  (%d categories)", len(birth_location))

        region, tag_region = ISTATFetchService.fetch_region(eurostat_client)
        logger.info("  region OK  (%d regions)", len(region))

        socioeconomic, tag_socio = ISTATFetchService.fetch_socioeconomic(istat_client)
        logger.info("  socioeconomic OK  (%d categories)", len(socioeconomic))

        parental_structure, tag_parental = ISTATFetchService.fetch_parental_structure(istat_client)
        logger.info("  parental_structure OK  (%d categories)", len(parental_structure))

        civil_status_by_age_sex, tag_civil = ISTATFetchService.fetch_civil_status_by_age_sex(istat_client)
        logger.info("  civil_status_by_age_sex OK  (%d keys)", len(civil_status_by_age_sex))

        industry_sector, tag_industry = ISTATFetchService.fetch_industry_sector(istat_client)
        logger.info("  industry_sector OK  (%d sectors)", len(industry_sector))

        employment_type_by_age, tag_emp_type = ISTATFetchService.fetch_employment_type_by_age(istat_client)
        logger.info("  employment_type_by_age OK  (%d keys)", len(employment_type_by_age))

        housing_tenure, tag_housing = ISTATFetchService.fetch_housing_tenure(eurostat_client)
        logger.info("  housing_tenure OK  (%d categories)", len(housing_tenure))

        household_size, tag_household = ISTATFetchService.fetch_household_size(istat_client)
        logger.info("  household_size OK  (%d categories)", len(household_size))

        income_source_by_employment_age, tag_income = (
            ISTATFetchService.fetch_income_source_by_employment_age(istat_client)
        )
        logger.info("  income_source_by_employment_age OK  (%d keys)", len(income_source_by_employment_age))

        birth_country_detail, tag_birth_detail = ISTATFetchService.fetch_birth_country_detail(eurostat_client)
        logger.info("  birth_country_detail OK  (%d keys)", len(birth_country_detail))

        tables_used = (
            tag_age_sex, tag_edu, tag_emp, tag_birth, tag_region,
            tag_socio, tag_parental, tag_civil, tag_industry,
            tag_emp_type, tag_housing, tag_household, tag_income,
            tag_birth_detail,
        )

        logger.info("ISTATFetchService.load_all: all dimensions fetched successfully")

        return PopulationDistributions(
            age_sex=age_sex,
            education_by_age=education_by_age,
            employment_by_sex_education=employment_by_sex_education,
            birth_location=birth_location,
            region=region,
            socioeconomic=socioeconomic,
            parental_structure=parental_structure,
            civil_status_by_age_sex=civil_status_by_age_sex,
            industry_sector=industry_sector,
            employment_type_by_age=employment_type_by_age,
            housing_tenure=housing_tenure,
            household_size=household_size,
            income_source_by_employment_age=income_source_by_employment_age,
            birth_country_detail=birth_country_detail,
            ethnicity_map={},
            tables_used=tables_used,
        )

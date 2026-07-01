"""
SSBFetchService — fetches all demographic dimensions from the Norwegian SSB
PxWebApi v2 and returns a fully populated ``PopulationDistributions`` dataclass.

Each ``fetch_*`` method:
1. Builds a flat query-params dict for ``SSBPxWebClient.fetch_table()``.
2. Calls the appropriate parser from ``ssb_population.parsers``.
3. Returns ``(distribution_dict, table_tag_string)``.

``load_all(client)`` orchestrates all fetches and constructs the dataclass.

Failure policy
--------------
* Every fetched dimension **raises** loudly on API error or empty parse — there
  are no synthetic fallback distributions (see the no-synthetic-distributions
  rule in ``CLAUDE.md``).
* ``income_source_by_employment_age`` is **dropped** (returned empty): no SSB
  PxWebApi v2 table provides income-component shares conditioned jointly on
  employment status and age group, so the field is omitted rather than invented
  (matching the Italian generator).
"""

from __future__ import annotations

import logging

from population_synthetic.clients.ssb_client import SSBPxWebClient
from population_synthetic.generators.reference.data import PopulationDistributions

from .constants import (
    AGE_SEX_REGION_WHOLE_COUNTRY,
    AGE_SEX_TABLE,
    ANSETTELSESFORHOLD_CODES,
    ARBEIDSTID_CODES,
    BIRTH_COUNTRY_TABLE,
    BIRTH_COUNTRY_TOP_CODES,
    BRUTTOINN_BRACKETS,
    CIVIL_STATUS_TABLE,
    EDUCATION_TABLE,
    EMPLOYMENT_TABLE,
    EMPLOYMENT_TYPE_TABLE,
    FYLKE_CODES,
    HOUSEHOLD_SIZE_TABLE,
    HOUSING_TENURE_TABLE,
    INDUSTRY_SECTOR_TABLE,
    PARENTAL_STRUCTURE_TABLE,
    REGION_WHOLE_COUNTRY,
    SOCIOECONOMIC_TABLE,
    VALID_AGE_GROUPS,
)
from .parsers import (
    parse_age_sex,
    parse_civil_status_by_age_sex,
    parse_education_by_age,
    parse_employment_by_sex_education,
    parse_household_size,
    parse_housing_tenure,
    parse_industry_sector,
    parse_parental_structure,
    parse_region,
    parse_socioeconomic,
)

logger = logging.getLogger(__name__)


class SSBFetchService:
    """Fetch service for Norwegian SSB demographic data.

    All methods are static and accept an ``SSBPxWebClient`` instance.
    """

    @staticmethod
    def fetch_age_sex(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch population by single-year age and sex (table 07459, national)."""
        # 07459 uses 3-digit zero-padded age codes: "018" through "085"
        ages = [str(i).zfill(3) for i in range(18, 86)]
        query_params = {
            "Region": [AGE_SEX_REGION_WHOLE_COUNTRY],
            "Kjonn": ["1", "2"],
            "Alder": ages,
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        raw = client.fetch_table(AGE_SEX_TABLE, query_params)
        return parse_age_sex(raw), AGE_SEX_TABLE

    @staticmethod
    def fetch_education_by_age(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch education level by age band and sex (table 08921, national)."""
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "Kjonn": ["1", "2"],
            "Alder": ["16-19", "20-24", "25-29", "30-39", "40-49", "50-59", "60-66", "067+"],
            "UtdanNivaa": ["01", "02a", "11", "03a", "04a", "09a"],
            "ContentsCode": ["Personer"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(EDUCATION_TABLE, query_params)
        result = parse_education_by_age(raw)
        return result, EDUCATION_TABLE

    @staticmethod
    def fetch_employment_by_sex_education(
        client: SSBPxWebClient,
    ) -> tuple[dict, str]:
        """Fetch employment status by education level and sex (table 13785)."""
        query_params = {
            "ArbStyrkStatus": ["1", "2", "6"],
            "UtdNivaa": ["1-2", "3-5", "6-8", "0_9"],
            "Kjonn": ["1", "2"],
            "Alder": ["15-74"],
            "ContentsCode": ["Personer"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(EMPLOYMENT_TABLE, query_params)
        result = parse_employment_by_sex_education(raw)
        return result, EMPLOYMENT_TABLE

    @staticmethod
    def fetch_region(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch population by fylke (region), summed over age/sex (table 07459)."""
        fylke_codes = list(FYLKE_CODES.keys())
        ages = [str(i).zfill(3) for i in range(18, 86)]
        query_params = {
            "Region": fylke_codes,
            "Kjonn": ["1", "2"],
            "Alder": ages,
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        raw = client.fetch_table(AGE_SEX_TABLE, query_params)
        result = parse_region(raw)
        return result, AGE_SEX_TABLE + "#region"

    @staticmethod
    def fetch_birth_location(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch birth-location distribution using two API calls.

        1. Total adult population from table 07459.
        2. Immigrants by world-region aggregate (VES=Nordic+Western, IVE=rest)
           from table 09817.
        Norway proportion is computed as (total_pop - VES - IVE) / total_pop.
        """
        ages = [str(i).zfill(3) for i in range(18, 86)]
        pop_params = {
            "Region": [AGE_SEX_REGION_WHOLE_COUNTRY],
            "Kjonn": ["1", "2"],
            "Alder": ages,
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        pop_raw = client.fetch_table(AGE_SEX_TABLE, pop_params)
        total_pop = float(sum(v for v in pop_raw.get("value", []) if v is not None))

        imm_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "InnvandrKat": ["B"],
            "Landbakgrunn": ["VES", "IVE"],
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        imm_raw = client.fetch_table(BIRTH_COUNTRY_TABLE, imm_params)

        imm_dims = imm_raw.get("dimension", {})
        lb_key = next((k for k in imm_dims if "land" in k.lower()), None)
        if not lb_key:
            raise ValueError("Could not find Landbakgrunn dimension in birth_location response")

        lb_entries = list(imm_dims[lb_key]["category"]["label"].items())  # [(code, label), ...]
        imm_values = imm_raw.get("value", [])

        imm_by_category: dict[str, float] = {}
        for i, (code, _label) in enumerate(lb_entries):
            v = float(imm_values[i] or 0) if i < len(imm_values) else 0.0
            category = "Nordic Country" if code == "VES" else "Outside Europe"
            imm_by_category[category] = imm_by_category.get(category, 0.0) + v

        total_immigrants = sum(imm_by_category.values())
        norway_count = max(0.0, total_pop - total_immigrants)

        dist: dict[str, float] = {"Norway": norway_count}
        dist.update(imm_by_category)

        grand_total = sum(dist.values()) or 1.0
        return {k: v / grand_total for k, v in dist.items()}, BIRTH_COUNTRY_TABLE

    @staticmethod
    def fetch_civil_status_by_age_sex(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch civil status distribution by decade age band and sex (table 03031)."""
        query_params = {
            "Region": list(FYLKE_CODES.keys()),
            "Kjonn": ["1", "2"],
            # Alder: decade codes "0"..="9"
            "Alder": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
            "EkteskStatus": ["1", "2", "3", "4", "5", "6"],
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        raw = client.fetch_table(CIVIL_STATUS_TABLE, query_params)
        result = parse_civil_status_by_age_sex(raw)
        return result, CIVIL_STATUS_TABLE + "#civil_status"

    @staticmethod
    def fetch_industry_sector(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch employed persons by NACE2007 industry sector (table 09315)."""
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "NACE2007": [
                "01-03", "05-09", "10-33", "35-39", "41-43",
                "45-47", "49-53", "55-56", "58-63", "64-66",
                "68-75", "77-82", "84", "85", "86-88", "90-99",
            ],
            "Alder": ["15-74"],
            "ContentsCode": ["Sysselsatte"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(INDUSTRY_SECTOR_TABLE, query_params)
        result = parse_industry_sector(raw)
        return result, INDUSTRY_SECTOR_TABLE

    @staticmethod
    def fetch_employment_type_by_age(
        client: SSBPxWebClient,
    ) -> tuple[dict, str]:
        """Fetch employment contract type x working hours (table 13878).

        Table 13878 only provides Alder="15-74" (no per-band breakdown).
        The same marginal distribution (conditioned on sex only) is expanded
        to all VALID_AGE_GROUPS.
        """
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "Ansettelsesforhold": ["F", "M"],
            "NACE2007": ["00-99"],
            "ArbeidsTidRen": ["H", "D"],
            "Alder": ["15-74"],
            "ContentsCode": ["Sysselsatte"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(EMPLOYMENT_TYPE_TABLE, query_params)

        dims = raw.get("dimension", {})
        values = raw.get("value", [])
        id_list = raw.get("id", list(dims.keys()))

        attach_key = next((k for k in dims if "ansett" in k.lower()), None)
        hours_key = next((k for k in dims if "arbeidstid" in k.lower()), None)
        if not attach_key or not hours_key:
            raise ValueError(
                f"Could not find Ansettelsesforhold/ArbeidsTidRen in 13878 response; dims={list(dims.keys())}"
            )

        attach_entries = list(dims[attach_key]["category"]["label"].items())
        hours_entries = list(dims[hours_key]["category"]["label"].items())

        # Compute strides from id_list ordering
        stride_map: dict[str, int] = {}
        s = 1
        for k in reversed(id_list):
            stride_map[k] = s
            s *= len(dims[k]["category"]["label"])

        # Table 13878 has no Kjonn dimension — build a sex-agnostic marginal,
        # then expand to both sexes for the (age_group, sex) key structure.
        marginal: dict[str, float] = {}
        for att_i, (att_code, _) in enumerate(attach_entries):
            norm_att = ANSETTELSESFORHOLD_CODES.get(att_code, att_code)
            for hr_i, (hr_code, _) in enumerate(hours_entries):
                norm_hr = ARBEIDSTID_CODES.get(hr_code, hr_code)
                composite = f"{norm_att}|{norm_hr}"
                idx = att_i * stride_map[attach_key] + hr_i * stride_map[hours_key]
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                marginal[composite] = marginal.get(composite, 0.0) + v

        if not marginal:
            raise ValueError("No employment_type data parsed from SSB 13878 response")
        total = sum(marginal.values()) or 1.0
        norm_dist = {k: v / total for k, v in marginal.items()}

        result: dict[tuple[str, str], dict[str, float]] = {
            (age_group, sex): dict(norm_dist)
            for age_group in VALID_AGE_GROUPS
            for sex in ("Male", "Female")
        }
        return result, EMPLOYMENT_TYPE_TABLE

    @staticmethod
    def fetch_housing_tenure(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch dwelling tenure form by EierStatus (table 11081)."""
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "HusholdType": ["1-2"],
            "BygnType": ["1b"],
            "EierStatus": ["2", "3", "4"],
            "ContentsCode": ["Husholdning"],
            "Tid": ["2021"],
        }
        raw = client.fetch_table(HOUSING_TENURE_TABLE, query_params)
        result = parse_housing_tenure(raw)
        return result, HOUSING_TENURE_TABLE

    @staticmethod
    def fetch_household_size(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch household size distribution (table 06079, national)."""
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "HushStr": ["1", "2", "3", "4", "5"],
            "ContentsCode": ["Husholdniger"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(HOUSEHOLD_SIZE_TABLE, query_params)
        result = parse_household_size(raw)
        return result, HOUSEHOLD_SIZE_TABLE

    @staticmethod
    def fetch_parental_structure(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch family type distribution (table 06083, national).

        Raises loudly on API error or parse failure — no synthetic fallback.
        """
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "FamilieType": ["001", "002", "003", "004", "005", "006", "007", "008", "009"],
            "ContentsCode": ["Familier"],
            "Tid": ["2023"],
        }
        raw = client.fetch_table(PARENTAL_STRUCTURE_TABLE, query_params)
        result = parse_parental_structure(raw)
        return result, PARENTAL_STRUCTURE_TABLE

    @staticmethod
    def fetch_socioeconomic(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch individual gross income by bracket x age x sex (table 06655, national).

        Queries all 9 BruttoInn brackets, all 6 Alder bands (17-24 through 67+),
        both sexes (Kjonn 1 and 2), using ContentsCode="Personar". Latest year used.
        Raises loudly on API error or parse failure — no silent fallback.
        """
        bracket_codes = [code for code, _, _ in BRUTTOINN_BRACKETS]
        query_params = {
            "BruttoInn": bracket_codes,
            "Alder": ["17-24", "25-34", "35-44", "45-54", "55-66", "67+"],
            "Kjonn": ["1", "2"],
            "ContentsCode": ["Personar"],
            "Tid": ["2024"],
        }
        raw = client.fetch_table(SOCIOECONOMIC_TABLE, query_params)
        result = parse_socioeconomic(raw)
        return result, SOCIOECONOMIC_TABLE

    @staticmethod
    def fetch_birth_country_detail(client: SSBPxWebClient) -> tuple[dict, str]:
        """Fetch birth country detail (table 09817, top 20 origin countries).

        Table 09817 has no age/sex breakdown. Returns a marginal distribution
        over origin countries, expanded to all VALID_AGE_GROUPS x sex.
        """
        _CODE_TO_COUNTRY = {
            "131": "Poland", "106": "Sweden", "148": "Ukraine", "136": "Lithuania",
            "564": "Syria", "346": "Somalia", "144": "Germany", "534": "Pakistan",
            "452": "Iraq", "456": "Iran", "444": "India", "103": "Finland",
            "410": "Bangladesh", "424": "Sri Lanka", "575": "Vietnam", "101": "Denmark",
            "159": "Serbia", "241": "Eritrea", "684": "USA", "140": "Russia",
        }
        query_params = {
            "Region": [REGION_WHOLE_COUNTRY],
            "InnvandrKat": ["B"],
            "Landbakgrunn": BIRTH_COUNTRY_TOP_CODES,
            "ContentsCode": ["Personer1"],
            "Tid": ["2024"],
        }
        raw = client.fetch_table(BIRTH_COUNTRY_TABLE, query_params)

        dims = raw.get("dimension", {})
        values = raw.get("value", [])
        lb_key = next((k for k in dims if "land" in k.lower()), None)
        if not lb_key:
            raise ValueError("Could not find Landbakgrunn dimension in birth_country_detail response")

        lb_entries = list(dims[lb_key]["category"]["label"].items())
        marginal: dict[str, float] = {}
        for i, (code, _) in enumerate(lb_entries):
            v = float(values[i] or 0) if i < len(values) else 0.0
            country = _CODE_TO_COUNTRY.get(code, "Other")
            marginal[country] = marginal.get(country, 0.0) + v

        if not marginal:
            raise ValueError("No birth_country_detail data parsed from SSB response")
        total = sum(marginal.values()) or 1.0
        marginal_norm = {k: v / total for k, v in marginal.items()}

        result: dict[tuple[str, str], dict[str, float]] = {
            (age_group, sex): dict(marginal_norm)
            for age_group in VALID_AGE_GROUPS
            for sex in ("Male", "Female")
        }
        return result, BIRTH_COUNTRY_TABLE + "#detail"

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    @staticmethod
    def load_all(client: SSBPxWebClient) -> PopulationDistributions:
        """Fetch all dimensions and construct a ``PopulationDistributions`` instance.

        All dimensions raise loudly on failure except parental structure and
        income source, which log a WARNING and use documented fallback distributions.
        """
        logger.info("SSBFetchService.load_all: starting fetch sequence")

        age_sex, tag_age_sex = SSBFetchService.fetch_age_sex(client)
        logger.info("  age_sex OK  (%d entries)", len(age_sex))

        education_by_age, tag_education = SSBFetchService.fetch_education_by_age(client)
        logger.info("  education_by_age OK  (%d keys)", len(education_by_age))

        employment_by_sex_education, tag_employment = (
            SSBFetchService.fetch_employment_by_sex_education(client)
        )
        logger.info("  employment_by_sex_education OK  (%d sex keys)", len(employment_by_sex_education))

        region, tag_region = SSBFetchService.fetch_region(client)
        logger.info("  region OK  (%d regions)", len(region))

        birth_location, tag_birth_location = SSBFetchService.fetch_birth_location(client)
        logger.info("  birth_location OK  (%d categories)", len(birth_location))

        civil_status_by_age_sex, tag_civil = SSBFetchService.fetch_civil_status_by_age_sex(client)
        logger.info("  civil_status_by_age_sex OK  (%d keys)", len(civil_status_by_age_sex))

        industry_sector, tag_industry = SSBFetchService.fetch_industry_sector(client)
        logger.info("  industry_sector OK  (%d sectors)", len(industry_sector))

        employment_type_by_age, tag_emp_type = SSBFetchService.fetch_employment_type_by_age(client)
        logger.info("  employment_type_by_age OK  (%d keys)", len(employment_type_by_age))

        housing_tenure, tag_housing = SSBFetchService.fetch_housing_tenure(client)
        logger.info("  housing_tenure OK  (%d categories)", len(housing_tenure))

        household_size, tag_household = SSBFetchService.fetch_household_size(client)
        logger.info("  household_size OK  (%d categories)", len(household_size))

        parental_structure, tag_parental = SSBFetchService.fetch_parental_structure(client)
        logger.info("  parental_structure OK  (%d categories)", len(parental_structure))

        socioeconomic, tag_socioeconomic = SSBFetchService.fetch_socioeconomic(client)
        logger.info("  socioeconomic OK  (%d categories)", len(socioeconomic))

        # income_source_by_employment_age is dropped: no SSB PxWebApi v2 table
        # provides income-component shares conditioned jointly on employment
        # status and age group, and the no-synthetic-distributions rule forbids
        # inventing one. (Italy drops this field identically.)

        birth_country_detail, tag_birth_country = SSBFetchService.fetch_birth_country_detail(client)
        logger.info("  birth_country_detail OK  (%d keys)", len(birth_country_detail))

        tables_used = (
            tag_age_sex,
            tag_education,
            tag_employment,
            tag_region,
            tag_birth_location,
            tag_civil,
            tag_industry,
            tag_emp_type,
            tag_housing,
            tag_household,
            tag_parental,
            tag_socioeconomic,
            tag_birth_country,
        )

        logger.info("SSBFetchService.load_all: all dimensions fetched successfully")

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
            income_source_by_employment_age={},
            birth_country_detail=birth_country_detail,
            ethnicity_map={},
            tables_used=tables_used,
        )

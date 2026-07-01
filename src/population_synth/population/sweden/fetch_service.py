"""Fetches Swedish demographic dimensions from the SCB PxWeb API.

Orchestrates calls to ``SCBPxWebClient``, routes each raw table response
through the Sweden parsers, and assembles a fully populated
``PopulationDistributions`` dataclass via ``load_all``. Every dimension
raises loudly on API error or empty parse; there are no synthetic
fallback distributions.
"""
from __future__ import annotations

from population_synth.clients.scb_client import SCBPxWebClient
from population_synth.population.data import PopulationDistributions

from .constants import (
    AGE_SEX_TABLE,
    BIRTH_COUNTRY_DETAIL_TABLE,
    BIRTH_COUNTRY_TOP_CODES,
    CIVIL_STATUS_TABLE,
    COUNTY_CODES,
    EDUCATION_TABLE,
    EMPLOYMENT_ATTACHMENT_TABLE,
    EMPLOYMENT_BY_EDUCATION_TABLE,
    FAMILY_TABLE,
    FOREIGN_BORN_TABLE,
    HOUSEHOLD_SIZE_TABLE,
    HOUSING_TENURE_TABLE,
    INCOME_BRACKET_TABLE,
    INCOME_SOURCE_TABLE,
    INDUSTRY_SECTOR_TABLE,
    SCB_INCOME_BRACKETS,
    WORKING_HOURS_TABLE,
)
from .parsers import (
    parse_age_sex,
    parse_birth_country_detail,
    parse_birth_location,
    parse_civil_status_by_age_sex,
    parse_education_by_age,
    parse_employment_by_sex_education,
    parse_employment_type_combined,
    parse_household_size,
    parse_housing_tenure,
    parse_income_source,
    parse_industry_sector,
    parse_parental_structure,
    parse_region,
    parse_socioeconomic,
)


class FetchService:
    @staticmethod
    def fetch_age_sex(client: SCBPxWebClient) -> tuple[dict, str]:
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["BE0101N1"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(AGE_SEX_TABLE, query)
        return parse_age_sex(raw), AGE_SEX_TABLE

    @staticmethod
    def fetch_education_by_age(client: SCBPxWebClient) -> tuple[dict, str]:
        ages = [str(i) for i in range(18, 75)]
        edu_levels = ["1", "2", "3", "4", "5", "6", "7", "US"]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "UtbildningsNiva", "selection": {"filter": "item", "values": edu_levels}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["UF0506A1"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(EDUCATION_TABLE, query)
        result = parse_education_by_age(raw, age_group_map={})
        return result, EDUCATION_TABLE

    @staticmethod
    def fetch_employment_by_sex_education(
        client: SCBPxWebClient,
    ) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Arbetskraftstillh", "selection": {"filter": "item", "values": ["SYS", "ALÖS"]}},
                {"code": "UtbildningsNiva", "selection": {"filter": "item", "values": ["21", "3+4", "8"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["AM0401VR"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(EMPLOYMENT_BY_EDUCATION_TABLE, query)
        result = parse_employment_by_sex_education(raw)
        return result, EMPLOYMENT_BY_EDUCATION_TABLE

    @staticmethod
    def fetch_birth_location(client: SCBPxWebClient) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Fodelseland", "selection": {"filter": "item", "values": ["FSV", "FEU", "FUEU"]}},
                {"code": "HDI", "selection": {"filter": "item", "values": ["TOT"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1+2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ["TOT1"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000000N6"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(FOREIGN_BORN_TABLE, query)
        result = parse_birth_location(raw)
        return result, FOREIGN_BORN_TABLE

    @staticmethod
    def fetch_region(client: SCBPxWebClient) -> tuple[dict, str]:
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": COUNTY_CODES}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["BE0101N1"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(AGE_SEX_TABLE, query)
        result = parse_region(raw)
        return result, AGE_SEX_TABLE + "#region"

    @staticmethod
    def fetch_socioeconomic(client: SCBPxWebClient) -> tuple[dict, str]:
        age_bands = [
            "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
            "50-54", "55-59", "60-64", "65-69", "70-74", "75-79",
            "80-84", "85+",
        ]
        bracket_codes = [code for code, _, _ in SCB_INCOME_BRACKETS]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": age_bands}},
                {"code": "Inkomstklass", "selection": {"filter": "item", "values": bracket_codes}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["HE0110J9"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(INCOME_BRACKET_TABLE, query)
        result = parse_socioeconomic(raw)
        return result, INCOME_BRACKET_TABLE

    @staticmethod
    def fetch_parental_structure(client: SCBPxWebClient) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Kon", "selection": {"filter": "item", "values": ["5+6"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ["0-17"]}},
                {"code": "UtlBakgrund", "selection": {"filter": "item", "values": ["TotalC"]}},
                {"code": "UtbNivaForalder", "selection": {"filter": "item", "values": ["30"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000000UJ"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(FAMILY_TABLE, query)
        result = parse_parental_structure(raw)
        return result, FAMILY_TABLE

    @staticmethod
    def fetch_civil_status_by_age_sex(client: SCBPxWebClient) -> tuple[dict, str]:
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Civilstand", "selection": {"filter": "item", "values": ["OG", "G", "ÄNKL", "SK"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["BE0101N1"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(CIVIL_STATUS_TABLE, query)
        result = parse_civil_status_by_age_sex(raw, age_group_map={})
        return result, CIVIL_STATUS_TABLE + "#civil_status"

    @staticmethod
    def fetch_industry_sector(client: SCBPxWebClient) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Anknytningsgrad", "selection": {"filter": "item", "values": ["SYSTOT"]}},
                {"code": "SNI2007", "selection": {"filter": "item", "values": [
                    "01-03", "05-33+35-39", "41-43", "45-47", "49-53",
                    "55-56", "58-63", "64-82", "84+99", "85", "86-88", "90-98",
                ]}},
                {"code": "TypData", "selection": {"filter": "item", "values": ["O_DATA"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1+2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ["tot15-74"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000007V8"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(INDUSTRY_SECTOR_TABLE, query)
        result = parse_industry_sector(raw)
        return result, INDUSTRY_SECTOR_TABLE

    @staticmethod
    def fetch_employment_type_by_age(
        client: SCBPxWebClient,
    ) -> tuple[dict, str, str]:
        query_attach = {
            "query": [
                {"code": "Anknytningsgrad", "selection": {"filter": "item", "values": ["FA", "TA", "FÖ+MH"]}},
                {"code": "TypData", "selection": {"filter": "item", "values": ["O_DATA"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": [
                    "15-24", "25-34", "35-44", "45-54", "55-64", "65-74",
                ]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000007V6"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw_attach = client.fetch_table(EMPLOYMENT_ATTACHMENT_TABLE, query_attach)

        query_hours = {
            "query": [
                {"code": "VeckoarbetstidO", "selection": {"filter": "item", "values": ["1-19", "20-34", "35+"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": [
                    "15-19", "20-24", "25-34", "35-44", "45-54", "55-64", "65-74",
                ]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["AM0401JW"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw_hours = client.fetch_table(WORKING_HOURS_TABLE, query_hours)

        result = parse_employment_type_combined(raw_attach, raw_hours, age_group_map={})
        return result, EMPLOYMENT_ATTACHMENT_TABLE, WORKING_HOURS_TABLE

    @staticmethod
    def fetch_housing_tenure(client: SCBPxWebClient) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Hustyp", "selection": {"filter": "item", "values": ["SMÅHUS", "FLERBOST"]}},
                {"code": "Upplatelseform", "selection": {"filter": "item", "values": ["1", "2", "3"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["BO0104AH"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(HOUSING_TENURE_TABLE, query)
        result = parse_housing_tenure(raw)
        return result, HOUSING_TENURE_TABLE

    @staticmethod
    def fetch_household_size(client: SCBPxWebClient) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Hushallsstorlek", "selection": {"filter": "item", "values": [
                    "1P", "2P", "3P", "4P", "5P", "6P", "7+P",
                ]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["BE0101CZ"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(HOUSEHOLD_SIZE_TABLE, query)
        result = parse_household_size(raw)
        return result, HOUSEHOLD_SIZE_TABLE

    @staticmethod
    def fetch_income_source_by_employment_age(
        client: SCBPxWebClient,
    ) -> tuple[dict, str]:
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Inkomstkomponenter", "selection": {"filter": "item", "values": [
                    "300", "305", "310", "315", "320", "335",
                ]}},
                {"code": "Alder", "selection": {"filter": "item", "values": [
                    "20-29", "30-49", "50-64", "65-79", "80-",
                ]}},
                {"code": "Sysselsattning", "selection": {"filter": "item", "values": [
                    "1000", "1700", "1800", "1910", "1930",
                ]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000006SV"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(INCOME_SOURCE_TABLE, query)
        result = parse_income_source(raw)
        return result, INCOME_SOURCE_TABLE

    @staticmethod
    def fetch_birth_country_detail(client: SCBPxWebClient) -> tuple[dict, str]:
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Fodelseland", "selection": {"filter": "item", "values": BIRTH_COUNTRY_TOP_CODES}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000001NR"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(BIRTH_COUNTRY_DETAIL_TABLE, query)
        result = parse_birth_country_detail(raw, age_group_map={})
        return result, BIRTH_COUNTRY_DETAIL_TABLE

    @staticmethod
    def load_all(client: SCBPxWebClient) -> PopulationDistributions:
        age_sex, tag_age_sex = FetchService.fetch_age_sex(client)
        education_by_age, tag_education = FetchService.fetch_education_by_age(client)
        employment_by_sex_education, tag_employment = FetchService.fetch_employment_by_sex_education(client)
        birth_location, tag_birth_location = FetchService.fetch_birth_location(client)
        region, tag_region = FetchService.fetch_region(client)
        socioeconomic, tag_socioeconomic = FetchService.fetch_socioeconomic(client)
        parental_structure, tag_parental = FetchService.fetch_parental_structure(client)
        civil_status_by_age_sex, tag_civil = FetchService.fetch_civil_status_by_age_sex(client)
        industry_sector, tag_industry = FetchService.fetch_industry_sector(client)
        employment_type_by_age, tag_attach, tag_hours = FetchService.fetch_employment_type_by_age(client)
        housing_tenure, tag_housing = FetchService.fetch_housing_tenure(client)
        household_size, tag_household = FetchService.fetch_household_size(client)
        income_source_by_employment_age, tag_income_source = FetchService.fetch_income_source_by_employment_age(client)
        birth_country_detail, tag_birth_country = FetchService.fetch_birth_country_detail(client)

        tables_used = (
            tag_age_sex,
            tag_education,
            tag_employment,
            tag_birth_location,
            tag_region,
            tag_socioeconomic,
            tag_parental,
            tag_civil,
            tag_industry,
            tag_attach,
            tag_hours,
            tag_housing,
            tag_household,
            tag_income_source,
            tag_birth_country,
        )

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

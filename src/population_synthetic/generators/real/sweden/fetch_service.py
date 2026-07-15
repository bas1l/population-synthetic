"""Fetches Swedish demographic dimensions from the SCB PxWeb API.

Orchestrates calls to ``SCBPxWebClient``, routes each raw table response
through the Sweden parsers, and assembles a fully populated
``PopulationDistributions`` dataclass via ``load_all``. Every dimension
raises loudly on API error or empty parse; there are no synthetic
fallback distributions.
"""
from __future__ import annotations

from population_synthetic.clients.scb_client import SCBPxWebClient
from population_synthetic.generators.real.data import PopulationDistributions

from .constants import (
    AGE_SEX_TABLE,
    BIRTH_COUNTRY_DETAIL_TABLE,
    BIRTH_COUNTRY_TOP_CODES,
    CIVIL_STATUS_TABLE,
    COUNTY_CODES,
    EDUCATION_TABLE,
    EMPLOYMENT_ATTACHMENT_TABLE,
    EMPLOYMENT_BY_EDUCATION_TABLE,
    EMPLOYMENT_STATUS_EDU_TABLE,
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
    EMPLOYMENT_STATUS_AGE_BANDS,
    EMPLOYMENT_STATUS_BASELINE_AGE,
    EMPLOYMENT_STATUS_CONTENTS_CODES,
    EMPLOYMENT_STATUS_EDU_AGE,
    EMPLOYMENT_STATUS_EDU_CODES,
    EMPLOYMENT_STATUS_EDU_STATUS_CODES,
    HOUSING_BOENDEFORM_CODES,
    INDUSTRY_AGE_BANDS,
    INDUSTRY_SNI2007_CODES,
    parse_age_sex,
    parse_birth_country_detail,
    parse_birth_location,
    parse_civil_status_by_age_sex,
    parse_education_by_age,
    parse_employment_by_sex_education,
    parse_employment_status_combined,
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
        # UtbBefRegionR carries single-year Alder up to 95+ (vs the old
        # Utbildning table's 16-74 cap plus a synthetic tot16-74 total), so
        # request the full register range and let the parser drop ages that
        # fall outside the pipeline's canonical groups. This closes the 75+
        # education-attainment gap.
        ages = [str(i) for i in range(16, 95)] + ["95+"]
        edu_levels = ["1", "2", "3", "4", "5", "6", "7", "US"]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "UtbildningsNiva", "selection": {"filter": "item", "values": edu_levels}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000000I2"]}},
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
        # Register (ArRegArbStatus): labour-market status by 5-year age band x sex,
        # over the full register spectrum. NOTE: despite the legacy method/field
        # name ("by_sex_education"), this source carries NO education dimension --
        # status is conditioned on age x sex. Each status is a separate ContentsCode
        # measure (employed/unemployed/students/retirees/sick/others). Region="00"
        # (Sweden), Fodelseregion="tot" (Swedish- and foreign-born), Tid="2024". The
        # register's population is capped at age 74; the parser models ages 75+ from
        # the oldest real band (see EMPLOYMENT_STATUS_AGE_BANDS).
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": list(EMPLOYMENT_STATUS_AGE_BANDS)}},
                {"code": "Fodelseregion", "selection": {"filter": "item", "values": ["tot"]}},
                {
                    "code": "ContentsCode",
                    "selection": {"filter": "item", "values": list(EMPLOYMENT_STATUS_CONTENTS_CODES)},
                },
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(EMPLOYMENT_BY_EDUCATION_TABLE, query)
        result = parse_employment_by_sex_education(raw)
        return result, EMPLOYMENT_BY_EDUCATION_TABLE

    @staticmethod
    def fetch_employment_status(
        client: SCBPxWebClient,
    ) -> tuple[dict, str, str]:
        # Phase 6 opt-in MERGE (all-register). Fetches BOTH register tables and
        # derives P(status | age, education, sex) via the documented
        # odds-multiplication (see parse_employment_status_combined and the merge
        # spec). Called ONLY when the merge flag is on; when off, the generator
        # uses the single-table fetch_employment_by_sex_education path unchanged.
        #
        # ASSUMPTION (surfaced here and at the Step 3 call site): no status x age x
        # education interaction -- the two real 2-way register margins are combined
        # into the maximum-entropy joint consistent with them. Both legs use the
        # register "employed" definition; the AKU survey table is never mixed in.

        # Age leg P(S|A,s) over the 5-year bands PLUS the 15-74 all-ages aggregate,
        # which supplies the baseline P(S|s) (same table, same definition).
        status_ages = list(EMPLOYMENT_STATUS_AGE_BANDS) + [EMPLOYMENT_STATUS_BASELINE_AGE]
        query_status = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": status_ages}},
                {"code": "Fodelseregion", "selection": {"filter": "item", "values": ["tot"]}},
                {
                    "code": "ContentsCode",
                    "selection": {"filter": "item", "values": list(EMPLOYMENT_STATUS_CONTENTS_CODES)},
                },
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw_status = client.fetch_table(EMPLOYMENT_BY_EDUCATION_TABLE, query_status)

        # Education leg P(S|E,s): status x education x sex, working-age 20-64 total.
        # Monthly preliminary table -- use a recent full month for the shape.
        query_edu = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": [EMPLOYMENT_STATUS_EDU_AGE]}},
                {
                    "code": "UtbildningsNiva",
                    "selection": {"filter": "item", "values": list(EMPLOYMENT_STATUS_EDU_CODES)},
                },
                {"code": "Fodelseregion", "selection": {"filter": "item", "values": ["tot"]}},
                {
                    "code": "ContentsCode",
                    "selection": {"filter": "item", "values": list(EMPLOYMENT_STATUS_EDU_STATUS_CODES)},
                },
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024M12"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw_edu = client.fetch_table(EMPLOYMENT_STATUS_EDU_TABLE, query_edu)

        result = parse_employment_status_combined(raw_status, raw_edu, age_group_map={})
        return result, EMPLOYMENT_BY_EDUCATION_TABLE, EMPLOYMENT_STATUS_EDU_TABLE

    @staticmethod
    def fetch_birth_location(client: SCBPxWebClient) -> tuple[dict, str]:
        # FolkmFodlandHVD carries the age x sex breakdown behind the three
        # birth-region buckets, so request single-year Alder and both sexes
        # instead of the all-ages / both-sexes aggregate. OKANT ("unknown
        # country of birth") is queried so the counts stay faithful to the
        # true population; the parser drops it explicitly (no canonical target).
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Fodelseland", "selection": {"filter": "item", "values": ["FSV", "FEU", "FUEU", "OKANT"]}},
                {"code": "HDI", "selection": {"filter": "item", "values": ["TOT"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000000N6"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(FOREIGN_BORN_TABLE, query)
        result = parse_birth_location(raw, age_group_map={})
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
        # SamForvInk1a carries single-year Alder (the old SamForvInk1 gave
        # only 5-year bands). Request single years across the pipeline range;
        # the parser folds them into the canonical age groups. This table has
        # no Region dimension. Sparse young x high-bracket cells are legitimately
        # suppressed (null); the parser tolerates those without treating them as
        # zero-with-certainty.
        ages = [str(i) for i in range(18, 86)]
        bracket_codes = [code for code, _, _ in SCB_INCOME_BRACKETS]
        query = {
            "query": [
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Inkomstklass", "selection": {"filter": "item", "values": bracket_codes}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["HE0110AD"]}},
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
        # Register (ArRegSNI2007Riket): employed persons by industry (NACE Rev. 2),
        # keyed by real age band x sex. Units are person counts (not thousands).
        # This is a national ("Riket") table with no Region dimension. The
        # "employed" definition is the register one (annual gainfully employed by
        # region of residence, ContentsCode 0000071V), across all statuses in
        # employment (Yrkesstallning=TOT) and both Swedish- and foreign-born
        # (Fodelseregion=tot). The parser aggregates the fine SNI2007 codes into
        # the 12 canonical sectors and expands the coarse age bands to groups.
        query = {
            "query": [
                {"code": "SNI2007", "selection": {"filter": "item", "values": list(INDUSTRY_SNI2007_CODES)}},
                {"code": "Yrkesstallning", "selection": {"filter": "item", "values": ["TOT"]}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "Alder", "selection": {"filter": "item", "values": list(INDUSTRY_AGE_BANDS)}},
                {"code": "Fodelseregion", "selection": {"filter": "item", "values": ["tot"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["0000071V"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2024"]}},
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
        # Person-level register (HushallT31): number of persons by type of housing
        # x single-year age x sex. Unlike the old dwelling-level table this carries
        # the person's own age/sex, so the result is conditioned on
        # (age_group, sex). Only the mappable Boendeform codes are requested; the
        # parser collapses building-type x tenure onto the three canonical tenures.
        ages = [str(i) for i in range(18, 86)]
        query = {
            "query": [
                {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
                {"code": "Boendeform", "selection": {"filter": "item", "values": list(HOUSING_BOENDEFORM_CODES)}},
                {"code": "Alder", "selection": {"filter": "item", "values": ages}},
                {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": ["0000031S"]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ["2025"]}},
            ],
            "response": {"format": "json-stat2"},
        }
        raw = client.fetch_table(HOUSING_TENURE_TABLE, query)
        result = parse_housing_tenure(raw, age_group_map={})
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
    def load_all(
        client: SCBPxWebClient,
        merge_status_education: bool = False,
    ) -> PopulationDistributions:
        # merge_status_education (default OFF): when False the employment_status
        # attribute is the single-table age x sex register path (Phase 4), byte for
        # byte -- ArbStatusUtbM is NOT fetched. When True, the opt-in all-register
        # two-table MERGE additionally derives P(status | age, education, sex) (see
        # fetch_employment_status). The single-table field is still populated so
        # Step 3 can fall back to it. Assumption: no status x age x education
        # interaction (documented at the call site and in provenance).
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

        employment_status_by_edu: dict | None = None
        merge_tags: tuple[str, ...] = ()
        if merge_status_education:
            employment_status_by_edu, _tag_status, tag_status_edu = FetchService.fetch_employment_status(client)
            # ArRegArbStatus (_tag_status) is already listed via tag_employment;
            # add only the second, merge-specific table for provenance.
            merge_tags = (tag_status_edu,)

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
        ) + merge_tags

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
            employment_status_by_edu=employment_status_by_edu,
        )

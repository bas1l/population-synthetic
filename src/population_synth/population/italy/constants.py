from __future__ import annotations

from population_synth.population.helpers import VALID_AGE_GROUPS as VALID_AGE_GROUPS  # noqa: F401

# ---------------------------------------------------------------------------
# Eurostat dataset IDs (JSON-stat 2.0)
# ---------------------------------------------------------------------------
EUROSTAT_AGE_SEX_DATASET = "demo_pjan"
EUROSTAT_REGION_DATASET = "demo_r_pjangrp3"
EUROSTAT_HOUSING_TENURE_DATASET = "ilc_lvho02"
EUROSTAT_BIRTH_LOCATION_DATASET = "migr_pop1ctz"

# ---------------------------------------------------------------------------
# ISTAT dataflow IDs (SDMX-JSON 2.0)
# ---------------------------------------------------------------------------
ISTAT_EDUCATION_DATAFLOW = "52_1194_DF_DCCV_POPTIT1_UNT2020_1"
ISTAT_EMPLOYMENT_DATAFLOW = "150_938"
ISTAT_HOUSEHOLD_DATAFLOW = "32_292"
ISTAT_CIVIL_STATUS_DATAFLOW = "22_289_DF_DCIS_POPRES1_25"
ISTAT_BIRTH_COUNTRY_DATAFLOW = "29_348"

# ---------------------------------------------------------------------------
# NUTS2 region codes (20 Italian regions)
# ---------------------------------------------------------------------------
NUTS2_REGION_CODES: dict[str, str] = {
    "ITC1": "Piemonte",
    "ITC2": "Valle d'Aosta",
    "ITC3": "Liguria",
    "ITC4": "Lombardia",
    "ITH1": "Trentino-Alto Adige/Südtirol",
    "ITH2": "Veneto",
    "ITH3": "Friuli-Venezia Giulia",
    "ITH4": "Emilia-Romagna",
    "ITH5": "Toscana",
    "ITI1": "Umbria",
    "ITI2": "Marche",
    "ITI3": "Lazio",
    "ITI4": "Abruzzo",
    "ITF1": "Molise",
    "ITF2": "Campania",
    "ITF3": "Puglia",
    "ITF4": "Basilicata",
    "ITF5": "Calabria",
    "ITF6": "Sicilia",
    "ITG2": "Sardegna",
}

# ---------------------------------------------------------------------------
# Sex label map — Eurostat sex codes → schema labels
# ---------------------------------------------------------------------------
SEX_LABEL_MAP: dict[str, str] = {
    "M": "Male",
    "F": "Female",
    "T": "Total",
}

# ---------------------------------------------------------------------------
# ISCED education level map — ISTAT edu codes → schema labels
# ---------------------------------------------------------------------------
ISCED_LABEL_MAP: dict[str, str] = {
    "ED0": "No Formal Education",
    "ED1": "No Formal Education",
    "ED2": "No Formal Education",
    "ED3": "High School (Liceo/Professionale)",
    "ED4": "High School (Liceo/Professionale)",
    "ED5": "University Degree",
    "ED6": "University Degree",
    "ED7": "University Degree",
    "ED8": "University Degree",
    # Also handle numeric ISCED codes that may appear
    "0": "No Formal Education",
    "1": "No Formal Education",
    "2": "No Formal Education",
    "3": "High School (Liceo/Professionale)",
    "4": "High School (Liceo/Professionale)",
    "5": "University Degree",
    "6": "University Degree",
    "7": "University Degree",
    "8": "University Degree",
}

# ---------------------------------------------------------------------------
# ILO employment status map — ISTAT codes → schema labels
# ---------------------------------------------------------------------------
ILO_EMPLOYMENT_MAP: dict[str, str] = {
    "EMP": "Employed",
    "UNE": "Unemployed",
    "INE": "Not in labour force",
    # Numeric variants
    "1": "Employed",
    "2": "Unemployed",
    "3": "Not in labour force",
}

# ---------------------------------------------------------------------------
# Civil status map — ISTAT codes → schema labels
# ---------------------------------------------------------------------------
CIVIL_STATUS_MAP: dict[str, str] = {
    "SINGLE": "Single",
    "MARRIED": "Married",
    "DIVORCED": "Divorced",
    "WIDOWED": "Widowed",
    "SEP": "Separated",
    "PART": "Civil Partnership",
    # ISTAT may use Italian single-letter codes
    "C": "Single",
    "S": "Married",
    "D": "Divorced",
    "V": "Widowed",
    "L": "Separated",
    "P": "Civil Partnership",
}

# ---------------------------------------------------------------------------
# ATECO/NACE industry sector map — ISTAT occupation/industry codes → schema labels
# ---------------------------------------------------------------------------
ATECO_SECTOR_MAP: dict[str, str] = {
    "A": "Agriculture, Forestry and Fishing",
    "B": "Mining and Quarrying",
    "C": "Manufacturing",
    "D": "Electricity, Gas and Water Supply",
    "E": "Waste Management",
    "F": "Construction",
    "G": "Wholesale and Retail Trade",
    "H": "Transport and Storage",
    "I": "Accommodation and Food Services",
    "J": "Information and Communication",
    "K": "Financial and Insurance Activities",
    "L": "Real Estate Activities",
    "M": "Professional and Scientific Activities",
    "N": "Administrative and Support Services",
    "O": "Public Administration and Defence",
    "P": "Education",
    "Q": "Health and Social Work",
    "R": "Arts, Entertainment and Recreation",
    "S": "Other Service Activities",
    "T": "Household Activities",
    "U": "Extra-territorial Activities",
}

# ---------------------------------------------------------------------------
# Income bracket edges in EUR (for income_class.py classification)
# ---------------------------------------------------------------------------
INCOME_BRACKET_EDGES_EUR: list[int] = [0, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000]

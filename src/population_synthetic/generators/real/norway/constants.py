"""
Constants for the Norwegian SSB population generator.

Table IDs and variable codes are verified against the SSB PxWebApi v2 endpoint
https://data.ssb.no/api/pxwebapi/v2/tables/{table_id}/metadata as of 2026-05.
"""

from population_synthetic.generators.real.helpers import AGE_GROUP_BOUNDS, VALID_AGE_GROUPS  # noqa: F401

# ---------------------------------------------------------------------------
# Age-sex (main population table — annual, by single year of age, by fylke)
# Variable codes: Region (fylke), Kjonn (kjonn), Alder (3-digit 0-padded age),
#                 ContentsCode ("Folkemengde"), Tid (year)
# ---------------------------------------------------------------------------
AGE_SEX_TABLE = "07459"
AGE_SEX_KJONN_CODES = {"1": "Male", "2": "Female"}
AGE_SEX_REGION_WHOLE_COUNTRY = "0"

# ---------------------------------------------------------------------------
# Education by fylke, age band, sex
# Variable codes: Region, Kjonn, Alder (band e.g. "20-24"), UtdanNivaa, ContentsCode, Tid
# ---------------------------------------------------------------------------
EDUCATION_TABLE = "08921"
EDUCATION_NIVAA_CODES = {
    "00": "total",
    "01": "No Formal Education",    # Grunnskolenivå
    "02a": "High School (Videregående)",  # Videregående skolenivå
    "11": "Vocational (Fagskole)",  # Fagskolenivå
    "03a": "University Degree",     # Universitets- og høgskolenivå, kort
    "04a": "University Degree",     # Universitets- og høgskolenivå, lang
    "09a": "No Formal Education",   # Uoppgitt eller ingen fullført utdanning
}

# ---------------------------------------------------------------------------
# Labour force status by sex, age band, education level
# Variable codes: ArbStyrkStatus, Kjonn, Alder, UtdNivaa, ContentsCode, Tid
# Note: Alder codes in this table are broad aggregates (e.g. "15-74", "20-66");
#       used for marginal employment_by_sex_education (no per-age-group breakdown)
# ---------------------------------------------------------------------------
EMPLOYMENT_TABLE = "13785"
EMPLOYMENT_STATUS_CODES = {
    "1": "Employed",
    "2": "Unemployed",
    "6": "Retired",     # "Utenfor arbeidsstyrken" (not in labour force)
}
EMPLOYMENT_NIVAA_CODES = {
    "1-2": "No Formal Education",
    "3-5": "High School (Videregående)",
    "11": "Vocational (Fagskole)",
    "6-8": "University Degree",
    "0_9": "No Formal Education",
}

# ---------------------------------------------------------------------------
# Civil status by fylke, decade age band, sex
# Variable codes: Region, Kjonn, Alder (decade code 0-9), EkteskStatus, ContentsCode, Tid
# Alder codes: "0"=0-9, "1"=10-19, "2"=20-29, "3"=30-39, ..., "9"=90+
# ---------------------------------------------------------------------------
CIVIL_STATUS_TABLE = "03031"
CIVIL_STATUS_CODES = {
    "1": "Single/Never Married",    # Ugift
    "2": "Married",                 # Gift
    "3": "Widowed",                 # Enke/enkemann
    "4": "Divorced",                # Skilt
    "5": "Divorced",                # Separert (mapped → Divorced)
    "6": "Single/Never Married",    # Annen sivilstand (mapped → Single)
}

# ---------------------------------------------------------------------------
# Region population distribution (fylke, from AGE_SEX_TABLE)
# Current post-2024 fylke codes (2-char)
# ---------------------------------------------------------------------------
FYLKE_CODES = {
    "31": "Østfold",
    "32": "Akershus",
    "03": "Oslo",
    "34": "Innlandet",
    "33": "Buskerud",
    "39": "Vestfold",
    "40": "Telemark",
    "42": "Agder",
    "11": "Rogaland",
    "46": "Vestland",
    "15": "Møre og Romsdal",
    "50": "Trøndelag",
    "18": "Nordland",
    "55": "Troms",
    "56": "Finnmark",
}

# ---------------------------------------------------------------------------
# Industry sector (employed persons by age band + NACE2007 section)
# Variable codes: Region, Alder, NACE2007, ContentsCode ("Sysselsatte"), Tid
# ---------------------------------------------------------------------------
INDUSTRY_SECTOR_TABLE = "09315"
NACE_SECTION_TO_SCHEMA = {
    "01-03": "Agriculture & Forestry",
    "05-09": "Manufacturing & Industry",
    "10-33": "Manufacturing & Industry",
    "35-39": "Manufacturing & Industry",
    "41-43": "Manufacturing & Industry",
    "45-47": "Retail & Service",
    "49-53": "Retail & Service",
    "55-56": "Retail & Service",
    "58-63": "IT & Technology",
    "64-66": "IT & Technology",
    "68-75": "IT & Technology",
    "77-82": "Retail & Service",
    "84": "Public Administration",
    "85": "Education",
    "86-88": "Healthcare & Social",
    "90-96": "Other",
    "97-99": "Other",
}

# ---------------------------------------------------------------------------
# Employment contract type (Ansettelsesforhold + ArbeidsTidRen)
# Variable codes: Region, Ansettelsesforhold, NACE2007, ArbeidsTidRen, Alder, ContentsCode, Tid
# ---------------------------------------------------------------------------
EMPLOYMENT_TYPE_TABLE = "13878"
ANSETTELSESFORHOLD_CODES = {
    "F": "permanent",
    "M": "temporary",
}
ARBEIDSTID_CODES = {
    "H": "full_time",    # Heltid
    "D": "part_time",    # Deltid
}

# ---------------------------------------------------------------------------
# Housing tenure (Eierstatus by husholdningstype and building type)
# Variable codes: Region, HusholdType, BygnType, EierStatus, ContentsCode, Tid
# ---------------------------------------------------------------------------
HOUSING_TENURE_TABLE = "11081"
EIERSTATUS_CODES = {
    "2": "Owner-occupied (villa/house)",      # Selveier
    "3": "Cooperative apartment (andel/aksje)",  # Andels-/aksjeeier
    "4": "Rental apartment",                  # Leier
}

# ---------------------------------------------------------------------------
# Household size distribution (percent, national)
# Variable codes: Region, HushStr, ContentsCode ("Husholdniger"), Tid
# ---------------------------------------------------------------------------
HOUSEHOLD_SIZE_TABLE = "06079"
HUSHSTR_CODES = {
    "1": "1 person",
    "2": "2 persons",
    "3": "3-4 persons",
    "4": "3-4 persons",
    "5": "5+ persons",
}

# ---------------------------------------------------------------------------
# Immigrants and Norwegian-born to immigrant parents, by country background
# Variable codes: Region, InnvandrKat, Landbakgrunn, ContentsCode, Tid
# InnvandrKat: "B"=Innvandrere, "B-C"=Both, "C"=Norskfødte with immigrant parents
# ---------------------------------------------------------------------------
BIRTH_COUNTRY_TABLE = "09817"
BIRTH_COUNTRY_TOP_CODES = [
    "131",  # Poland
    "106",  # Sweden
    "148",  # Ukraine
    "136",  # Lithuania
    "564",  # Syria
    "346",  # Somalia
    "144",  # Germany
    "534",  # Pakistan
    "452",  # Iraq
    "456",  # Iran
    "444",  # India
    "103",  # Finland
    "410",  # Bangladesh
    "424",  # Sri Lanka
    "575",  # Vietnam
    "101",  # Denmark
    "159",  # Serbia
    "241",  # Eritrea
    "684",  # USA
    "140",  # Russia
]

# ---------------------------------------------------------------------------
# Parental/family structure (FamilieType, national)
# Variable codes: Region, FamilieType, ContentsCode, Tid
# ---------------------------------------------------------------------------
PARENTAL_STRUCTURE_TABLE = "06083"
FAMILIETYPE_CODES = {
    "001": "Living Alone",
    "002": "Nuclear Family",
    "003": "Nuclear Family",
    "004": "Single Parent",
    "005": "Single Parent",
    "006": "Couple without Children",
    "007": "Couple without Children",
    "008": "Single Parent",
    "009": "Living Alone",
}

# ---------------------------------------------------------------------------
# Income brackets table — individual gross income by age × sex
# Variable codes: BruttoInn (bracket code), Alder (age band), Kjonn (sex),
#                 ContentsCode ("Personar"), Tid (year)
# Note: No per-employment-status or per-age cross-tab available in SSB PxWebApi v2.
#       income_source_by_employment_age uses the approximate distributions in
#       config/mapping/ssb/income_source.json.
# ---------------------------------------------------------------------------
SOCIOECONOMIC_TABLE = "06655"

# (bracket_code, low_nok, high_nok) — bracket edges in NOK.
# Top bracket "73" (2 000 000 NOK and over) is open-ended; treated as
# [2_000_000, 3_000_000] by convention (midpoint 2 500 000).
BRUTTOINN_BRACKETS: list[tuple[str, float, float]] = [
    ("60", 0,           100_000),
    ("61", 100_000,     200_000),
    ("62", 200_000,     300_000),
    ("08", 300_000,     400_000),
    ("09", 400_000,     500_000),
    ("70", 500_000,     750_000),
    ("71", 750_000,   1_000_000),
    ("72", 1_000_000, 2_000_000),
    ("73", 2_000_000, 3_000_000),  # open-ended top bracket; upper bound by convention
]

# ---------------------------------------------------------------------------
# Urbanization proxy (tettsted area + population, national)
# Variable codes: TettSted, ContentsCode, Tid
# ---------------------------------------------------------------------------
URBANIZATION_TABLE = "04859"

# Whole-country region code used when querying SSB for national-level results
REGION_WHOLE_COUNTRY = "0"

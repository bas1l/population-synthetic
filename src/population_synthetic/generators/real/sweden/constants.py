"""Static constants for the Swedish (SCB) population layer.

Holds SCB PxWeb table IDs, county and birth-country code lists, and the
income-bracket definitions used by the Sweden fetch service and parsers.
These are structural identifiers only, not probability values.
"""
COUNTY_CODES = [
    "01", "03", "04", "05", "06", "07", "08", "09", "10",
    "12", "13", "14", "17", "18", "19", "20", "21", "22", "23", "24", "25",
]

AGE_SEX_TABLE = "BE/BE0101/BE0101A/BefolkningNy"
FOREIGN_BORN_TABLE = "BE/BE0101/BE0101E/FolkmFodlandHVD"
BIRTH_COUNTRY_DETAIL_TABLE = "BE/BE0101/BE0101E/FodelselandArK"
EDUCATION_TABLE = "UF/UF0506/UF0506B/UtbBefRegionR"
EMPLOYMENT_TABLE = "AM/AM0401/AM0401A/AKURLBefAr"
# NOTE: kept the legacy name `EMPLOYMENT_BY_EDUCATION_TABLE` (and the matching
# fetch/parse/field names) for cross-country stability -- the shared
# `PopulationDistributions.employment_by_sex_education` field is also populated by
# the Norway/Italy generators, so renaming it here would ripple out of Sweden's
# scope. This source is the *register* labour-market status table
# (ArRegArbStatus): it carries NO education dimension. Labour status is conditioned
# on age x sex over the full register spectrum (employed/unemployed/students/
# retirees/sick/others), with each status exposed as its own ContentsCode measure.
EMPLOYMENT_BY_EDUCATION_TABLE = "AM/AM0210/AM0210D/ArRegArbStatus"
# Phase 6 (opt-in) status<->education leg: register labour-market status x level
# of education x sex (working-age total 20-64). Combined with ArRegArbStatus
# under the documented odds-multiplication derivation ONLY when the merge is
# explicitly enabled -- see docs/reference/scb-pxweb-catalog/
# employment-status-merge-derivation.md and parse_employment_status_combined.
# ALL-REGISTER (never the AKU survey table) so "employed" means the same thing
# in both legs. Not fetched at all when the merge flag is off (Phase 4 default).
EMPLOYMENT_STATUS_EDU_TABLE = "AM/AM0210/AM0210A/ArbStatusUtbM"
INCOME_TABLE = "HE/HE0110/HE0110F/TabVX10InkStrukt"
INCOME_SOURCE_TABLE = "HE/HE0110/HE0110F/TabVX13InkStruktN"
FAMILY_TABLE = "LE/LE0102/LE0102B/LE0102T17"
URBANIZATION_TABLE = "MI/MI0810/MI0810A/BefLandInvKvmTO"
CIVIL_STATUS_TABLE = "BE/BE0101/BE0101A/BefolkningNy"
INDUSTRY_SECTOR_TABLE = "AM/AM0210/AM0210F/ArRegSNI2007Riket"
EMPLOYMENT_ATTACHMENT_TABLE = "AM/AM0401/AM0401I/AKURLSysAnkAr"
WORKING_HOURS_TABLE = "AM/AM0401/AM0401S/NAKUSysselOkArbtidAr"
HOUSING_TENURE_TABLE = "HE/HE0111/HE0111A/HushallT31"
HOUSEHOLD_SIZE_TABLE = "BE/BE0101/BE0101S/HushallT03"

BIRTH_COUNTRY_TOP_CODES = [
    "SY", "IQ", "FI", "PL", "IR", "AF", "SO", "YU", "BA", "TR",
    "IN", "DE", "ER", "TH", "CN", "RO", "NO", "DK", "UA", "GB",
]

INCOME_BRACKET_TABLE = "HE/HE0110/HE0110A/SamForvInk1a"

# (bracket_code, low_sek_thousands, high_sek_thousands).
# All monetary values are in SEK thousands (1 unit = 1 000 SEK).
# The top bracket "1000+" is open-ended; [1 000, 1 500] is used as the closed
# approximation for the midpoint — the top bracket holds a small population
# share so this choice has negligible effect on the computed median.
SCB_INCOME_BRACKETS: list[tuple[str, float, float]] = [
    ("0",       0,     1),
    ("1-19",    1,    20),
    ("20-39",  20,    40),
    ("40-59",  40,    60),
    ("60-79",  60,    80),
    ("80-99",  80,   100),
    ("100-119", 100,  120),
    ("120-139", 120,  140),
    ("140-159", 140,  160),
    ("160-179", 160,  180),
    ("180-199", 180,  200),
    ("200-219", 200,  220),
    ("220-239", 220,  240),
    ("240-259", 240,  260),
    ("260-279", 260,  280),
    ("280-299", 280,  300),
    ("300-319", 300,  320),
    ("320-339", 320,  340),
    ("340-359", 340,  360),
    ("360-379", 360,  380),
    ("380-399", 380,  400),
    ("400-499", 400,  500),
    ("500-599", 500,  600),
    ("600-799", 600,  800),
    ("800-999", 800, 1000),
    ("1000+",  1000, 1500),
]

"""
extractor.py -- Extract demographic profiles from pipeline identity.json files.

Supports two identity formats:
- Batch (single "narrative" key with free-text description)
- Flat / configurable (top-level attribute keys)

The public entry point is ``extract_individual(identity_path)`` which auto-detects
the format and returns a flat attribute dict (or None on failure).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from population_synth._paths import PROJECT_ROOT

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline label mappings -- loaded from category_mappings.json so the JSON
# file is the source of truth for free-form label -> schema-label translations.
# ---------------------------------------------------------------------------

_MAPPINGS_PATH = PROJECT_ROOT / "config" / "assets" / "scb_reference" / "category_mappings.json"


def _load_pipeline_mappings() -> dict[str, dict[str, str]]:
    """Return {category: {raw_label_lower: schema_label}} for fast case-insensitive lookup."""
    with open(_MAPPINGS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)
    out: dict[str, dict[str, str]] = {}
    for key in (
        "education", "employment", "civil_status", "industry_sector",
        "employment_type", "income_source", "housing_tenure",
        "parental_structure", "socioeconomic", "region", "birth_country_detail",
    ):
        section = m.get(key, {}) or {}
        plm = section.get("pipeline_label_mappings", {}) or {}
        out[key] = {k.lower(): v for k, v in plm.items()}
    return out


_PIPELINE_MAPPINGS: dict[str, dict[str, str]] = _load_pipeline_mappings()


def _json_lookup(category: str, raw: str) -> str | None:
    """Case-insensitive exact-match lookup against pipeline_label_mappings."""
    if not raw:
        return None
    return _PIPELINE_MAPPINGS.get(category, {}).get(raw.strip().lower())


# ---------------------------------------------------------------------------
# Target schema labels (must match scb_population.json exactly)
# ---------------------------------------------------------------------------

AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]

EDUCATION_LABELS = [
    "Pre-Secondary < 9 yrs (ISCED 1)",
    "Pre-Secondary 9-10 yrs (ISCED 2)",
    "Upper Secondary ≤ 2 yrs (ISCED 3C)",
    "Upper Secondary 3 yrs (ISCED 3A)",
    "Post-Secondary < 3 yrs (ISCED 4+5B)",
    "Post-Secondary 3+ yrs (ISCED 5A)",
    "Post-Graduate (ISCED 6)",
    "Unknown / Not reported",
]

EMPLOYMENT_LABELS = ["Employed", "Unemployed", "Student", "Retired"]

BIRTH_LOCATION_LABELS = ["Sweden", "Nordic Country", "Europe (Other)", "Outside Europe"]

ETHNICITY_LABELS = ["Swedish", "Nordic", "European", "Non-European"]

ENVIRONMENT_LABELS = ["Urban Metropolis", "Suburban", "Rural/Countryside"]

SOCIOECONOMIC_LABELS = ["Poverty", "Working Class", "Middle Class", "Wealthy"]

PARENTAL_STRUCTURE_LABELS = [
    "Nuclear Family",
    "Single Parent",
    "Couple without Children",
    "Living Alone",
]

REGION_LABELS = [
    "Stockholm",
    "Västra Götaland",
    "Skåne",
    "Östergötland",
    "Uppsala",
    "Örebro",
    "Västernorrland",
    "Norrbotten",
    "Dalarna",
    "Gävleborg",
    "Halland",
    "Jönköping",
    "Kronoberg",
    "Kalmar",
    "Gotland",
    "Blekinge",
    "Värmland",
    "Västmanland",
    "Södermanland",
    "Västerbotten",
    "Jämtland",
]

BIRTH_COUNTRY_DETAIL_LABELS = [
    "Sweden",
    "Syria",
    "Iraq",
    "Finland",
    "Poland",
    "Iran",
    "Afghanistan",
    "Somalia",
    "Yugoslavia",
    "Bosnia and Herzegovina",
    "Turkey",
    "India",
    "Germany",
    "Eritrea",
    "Thailand",
    "China",
    "Romania",
    "Norway",
    "Denmark",
    "Ukraine",
    "United Kingdom",
]

CIVIL_STATUS_LABELS = [
    "Single/Never Married",
    "Married/Cohabiting",
    "Divorced/Separated",
    "Widowed",
]

HOUSEHOLD_SIZE_LABELS = ["1 person", "2 persons", "3 persons", "4 persons", "5 persons", "6 persons", "7+ persons"]

HOUSING_TENURE_LABELS = [
    "Owner-occupied (villa/house)",
    "Bostadsrätt (cooperative apartment)",
    "Rental apartment",
    "Other",
]

INDUSTRY_SECTOR_LABELS = [
    "Agriculture/Forestry/Fishing",
    "Manufacturing/Industry",
    "Retail & Service",
    "IT/Technology",
    "Public Administration/Defense",
    "Education",
    "Healthcare/Social Work",
    "Other Services",
    "Not Applicable",
]

EMPLOYMENT_TYPE_LABELS = [
    "Permanent Full-Time",
    "Permanent Part-Time",
    "Temporary Full-Time",
    "Temporary Part-Time",
    "Self-Employed/Freelance",
    "Not Applicable",
]

INCOME_SOURCE_LABELS = [
    "Wage / Business",
    "Capital",
    "Pension",
    "Insurance / Allowance",
    "Social Assistance",
    "Sickness / Activity Compensation",
]


# ---------------------------------------------------------------------------
# Swedish city -> county mapping (for batch narrative Location field)
# ---------------------------------------------------------------------------

_CITY_TO_COUNTY: dict[str, str] = {
    "stockholm": "Stockholm", "solna": "Stockholm", "sundbyberg": "Stockholm",
    "nacka": "Stockholm", "lidingö": "Stockholm", "danderyd": "Stockholm",
    "täby": "Stockholm", "sollentuna": "Stockholm", "huddinge": "Stockholm",
    "botkyrka": "Stockholm", "södertälje": "Stockholm", "haninge": "Stockholm",
    "tumba": "Stockholm", "sigtuna": "Stockholm", "norrtälje": "Stockholm",
    "göteborg": "Västra Götaland", "borås": "Västra Götaland",
    "trollhättan": "Västra Götaland", "skövde": "Västra Götaland",
    "uddevalla": "Västra Götaland", "lidköping": "Västra Götaland",
    "alingsås": "Västra Götaland", "mölndal": "Västra Götaland",
    "kungälv": "Västra Götaland", "partille": "Västra Götaland",
    "mariestad": "Västra Götaland", "vänersborg": "Västra Götaland",
    "malmö": "Skåne", "lund": "Skåne", "helsingborg": "Skåne",
    "kristianstad": "Skåne", "landskrona": "Skåne", "trelleborg": "Skåne",
    "ystad": "Skåne", "ängelholm": "Skåne",
    "linköping": "Östergötland", "norrköping": "Östergötland", "motala": "Östergötland",
    "mjölby": "Östergötland",
    "uppsala": "Uppsala", "enköping": "Uppsala",
    "västerås": "Västmanland",
    "örebro": "Örebro", "kumla": "Örebro", "hallsberg": "Örebro",
    "umeå": "Västerbotten", "skellefteå": "Västerbotten",
    "robertsfors": "Västerbotten", "sorsele": "Västerbotten", "lycksele": "Västerbotten",
    "vilhelmina": "Västerbotten", "storuman": "Västerbotten", "norsjö": "Västerbotten",
    "sundsvall": "Västernorrland", "härnösand": "Västernorrland",
    "örnsköldsvik": "Västernorrland", "kramfors": "Västernorrland",
    "gävle": "Gävleborg", "sandviken": "Gävleborg", "bollnäs": "Gävleborg",
    "hudiksvall": "Gävleborg",
    "halmstad": "Halland", "varberg": "Halland", "falkenberg": "Halland",
    "jönköping": "Jönköping", "värnamo": "Jönköping", "nässjö": "Jönköping",
    "vetlanda": "Jönköping",
    "växjö": "Kronoberg",
    "kalmar": "Kalmar", "västervik": "Kalmar", "oskarshamn": "Kalmar",
    "nybro": "Kalmar", "vimmerby": "Kalmar", "hultsfred": "Kalmar",
    "visby": "Gotland",
    "karlskrona": "Blekinge",
    "karlstad": "Värmland", "arvika": "Värmland",
    "eskilstuna": "Södermanland", "nyköping": "Södermanland",
    "strängnäs": "Södermanland", "katrineholm": "Södermanland",
    "falun": "Dalarna", "borlänge": "Dalarna", "mora": "Dalarna",
    "hedemora": "Dalarna", "avesta": "Dalarna", "ludvika": "Dalarna",
    "malung": "Dalarna", "leksand": "Dalarna", "rättvik": "Dalarna",
    "östersund": "Jämtland",
    "luleå": "Norrbotten", "kiruna": "Norrbotten", "piteå": "Norrbotten",
    "boden": "Norrbotten", "gällivare": "Norrbotten", "kalix": "Norrbotten",
    "haparanda": "Norrbotten", "arvidsjaur": "Norrbotten", "arjeplog": "Norrbotten",
}

_METRO_CITIES = {"stockholm", "göteborg", "malmö"}

_LARGE_CITIES = {
    "linköping", "norrköping", "uppsala", "västerås", "örebro",
    "umeå", "lund", "växjö", "sundsvall", "gävle", "borås",
    "eskilstuna", "halmstad", "jönköping", "karlstad", "kalmar",
    "helsingborg", "kristianstad", "trollhättan", "luleå",
    "nacka", "södertälje", "solna", "huddinge",
}

_OCCUPATION_TO_INDUSTRY: dict[str, str] = {
    "lärare": "Education", "förskollärare": "Education", "grundskollärare": "Education",
    "gymnasielärare": "Education", "teacher": "Education", "rektor": "Education",
    "skolkurator": "Education", "fritidspedagog": "Education",
    "bibliotekarie": "Education", "librarian": "Education",
    "sjuksköterska": "Healthcare/Social Work", "undersköterska": "Healthcare/Social Work",
    "läkare": "Healthcare/Social Work", "nurse": "Healthcare/Social Work",
    "psykolog": "Healthcare/Social Work", "terapeut": "Healthcare/Social Work",
    "tandläkare": "Healthcare/Social Work", "dietist": "Healthcare/Social Work",
    "socialsekreterare": "Healthcare/Social Work", "kurator": "Healthcare/Social Work",
    "social worker": "Healthcare/Social Work", "socionom": "Healthcare/Social Work",
    "handläggare": "Public Administration/Defense",
    "administratör": "Public Administration/Defense",
    "kommunikatör": "Public Administration/Defense",
    "kommunikationsstrateg": "Public Administration/Defense",
    "utredare": "Public Administration/Defense",
    "projektledare": "Public Administration/Defense",
    "systemutvecklare": "IT/Technology", "system developer": "IT/Technology",
    "systems developer": "IT/Technology", "system administrator": "IT/Technology",
    "programmerare": "IT/Technology", "it-konsult": "IT/Technology",
    "it consultant": "IT/Technology", "webbutvecklare": "IT/Technology",
    "tech company": "IT/Technology",
    "kundtjänstmedarbetare": "Retail & Service", "customer service": "Retail & Service",
    "butikssäljare": "Retail & Service", "kassör": "Retail & Service",
    "kock": "Retail & Service", "servitör": "Retail & Service",
    "frisör": "Retail & Service", "barista": "Retail & Service",
    "elektriker": "Manufacturing/Industry", "electrician": "Manufacturing/Industry",
    "ingenjör": "Manufacturing/Industry", "engineer": "Manufacturing/Industry",
    "svetsare": "Manufacturing/Industry", "mekaniker": "Manufacturing/Industry",
    "snickare": "Manufacturing/Industry",
    "lantbrukare": "Agriculture/Forestry/Fishing",
    "skogsarbetare": "Agriculture/Forestry/Fishing",
}

_UNIVERSITY_OCCUPATIONS = {
    "lärare", "förskollärare", "grundskollärare", "gymnasielärare", "teacher",
    "sjuksköterska", "nurse", "läkare", "psykolog", "terapeut", "tandläkare",
    "socialsekreterare", "socionom", "social worker", "dietist",
    "ingenjör", "engineer", "systemutvecklare", "system developer",
    "kommunikatör", "bibliotekarie", "librarian", "arkitekt",
    "projektledare", "project manager", "it-konsult", "it consultant",
    "programmerare", "webbutvecklare", "jurist", "advokat", "ekonom",
    "civilekonom", "revisor", "forskare", "professor", "rektor",
}


# ---------------------------------------------------------------------------
# Age bucketing
# ---------------------------------------------------------------------------

def _age_to_group(age: int) -> str:
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    if age < 65:
        return "55-64"
    if age < 75:
        return "65-74"
    return "75-85"


# ---------------------------------------------------------------------------
# Fuzzy normalization helpers
# ---------------------------------------------------------------------------

def _fuzzy_match(raw: str, labels: list[str]) -> str | None:
    """Return the first label whose lowercased form is a substring of raw (or vice versa)."""
    raw_lower = raw.lower().strip()
    for label in labels:
        if label.lower() in raw_lower or raw_lower in label.lower():
            return label
    return None


def _normalize_education(raw: str) -> str | None:
    raw_lower = raw.lower()
    if raw in EDUCATION_LABELS:
        return raw
    js = _json_lookup("education", raw)
    if js is not None:
        return js
    _POSTGRAD = ("post-graduate", "postgraduate", "phd", "doctoral", "doktors", "research degree",
                  "isced 6", "isced97 6")
    if any(k in raw_lower for k in _POSTGRAD):
        return "Post-Graduate (ISCED 6)"
    _POSTSEC3 = ("post-secondary 3", "isced 5a", "isced97 5a", "university", "degree", "bachelor",
                  "master", "kandidat", "magister", "högskolex", "högskole", "hogskola", "akademisk")
    if any(k in raw_lower for k in _POSTSEC3):
        return "Post-Secondary 3+ yrs (ISCED 5A)"
    _POSTSEC_LT3 = ("post-secondary <", "isced 4", "isced 5b", "isced97 4", "isced97 5b",
                     "vocational", "yrkeshogskola", "yrkeshögskola", "yrkes", "higher vocational",
                     "yh-")
    if any(k in raw_lower for k in _POSTSEC_LT3):
        return "Post-Secondary < 3 yrs (ISCED 4+5B)"
    _UPPER_SEC3 = ("upper secondary 3", "isced 3a", "isced97 3a", "gymnasium", "high school",
                    "gymnasieskola", "gymnasie", "gymnasial")
    if any(k in raw_lower for k in _UPPER_SEC3):
        return "Upper Secondary 3 yrs (ISCED 3A)"
    if any(k in raw_lower for k in ("upper secondary", "isced 3c", "isced97 3c")):
        return "Upper Secondary ≤ 2 yrs (ISCED 3C)"
    _PRESEC9 = ("pre-secondary 9", "isced 2", "isced97 2", "grundskola", "compulsory",
                 "elementary", "primary school", "folkskola")
    if any(k in raw_lower for k in _PRESEC9):
        return "Pre-Secondary 9-10 yrs (ISCED 2)"
    _PRESEC_LT9 = ("pre-secondary <", "isced 1", "isced97 1", "no formal", "primary",
                    "ingen utbildning", "lägre grundskola")
    if any(k in raw_lower for k in _PRESEC_LT9):
        return "Pre-Secondary < 9 yrs (ISCED 1)"
    if any(k in raw_lower for k in ("unknown", "not reported", "uppgift saknas")):
        return "Unknown / Not reported"
    return _fuzzy_match(raw, EDUCATION_LABELS)


def _normalize_employment(raw: str) -> str | None:
    raw_lower = raw.lower()
    js = _json_lookup("employment", raw)
    if js is not None:
        return js
    if any(k in raw_lower for k in ("parental leave", "föräldraledig", "mammaledig", "pappaledig")):
        return "Employed"
    _SICK = ("sick leave", "sjukskriven", "sjukskrivning", "disability benefit",
             "long-term sick", "long term sick")
    if any(k in raw_lower for k in _SICK):
        return "Unemployed"
    if any(k in raw_lower for k in ("military", "värnplikt", "armed forces")):
        return "Employed"
    _EMPLOYED = ("employ", "working", "worker", "job", "anställd", "heltid",
                  "deltid", "tillsvidare")
    if any(k in raw_lower for k in _EMPLOYED):
        return "Employed"
    _UNEMPLOYED = ("unemploy", "jobless", "seeking", "arbetssökande", "arbetslos",
                    "arbetslös")
    if any(k in raw_lower for k in _UNEMPLOYED):
        return "Unemployed"
    if any(k in raw_lower for k in ("student", "study", "school", "studying", "studerande")):
        return "Student"
    if any(k in raw_lower for k in ("retire", "pension")):
        return "Retired"
    return _fuzzy_match(raw, EMPLOYMENT_LABELS)


def _normalize_birth_location(raw: str) -> str | None:
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("native", "born in sweden", "sweden", "domestic migrant")):
        return "Sweden"
    if any(k in raw_lower for k in ("nordic", "scandinav", "norway", "denmark", "finland", "iceland")):
        return "Europe (Other)"
    if any(k in raw_lower for k in ("eu/europe", "european", "europe", "immigrant")):
        return "Europe (Other)"
    if any(k in raw_lower for k in ("non-eu", "outside europe", "refugee", "displaced", "international")):
        return "Outside Europe"
    return _fuzzy_match(raw, BIRTH_LOCATION_LABELS)


def _normalize_ethnicity(raw: str) -> str | None:
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("caucasian", "white", "swedish")):
        return "Swedish"
    if any(k in raw_lower for k in ("nordic", "scandina", "finnish", "finsk", "dansk", "norsk", "isländsk")):
        return "European"
    if any(k in raw_lower for k in ("european", "southern european", "eastern european", "östeuropeisk")):
        return "European"
    _NON_EU = ("middle eastern", "african", "asian", "hispanic", "latino",
                "non-european", "mixed", "indigenous", "chaldean", "assyrisk", "syriansk")
    if any(k in raw_lower for k in _NON_EU):
        return "Non-European"
    return _fuzzy_match(raw, ETHNICITY_LABELS)


def _normalize_environment(raw: str) -> str | None:
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("suburban", "suburb", "förort", "stadsnära")):
        return "Suburban"
    _RURAL = ("rural", "countryside", "village", "nomadic", "landsbygd", "glesbygd")
    if any(k in raw_lower for k in _RURAL) or raw_lower in ("by", "landsby"):
        return "Rural/Countryside"
    if any(k in raw_lower for k in ("small town", "smaller town", "town", "tätort", "mindre stad")):
        return "Suburban"
    _METRO = ("urban metropolis", "metropolis", "city center", "inner city",
               "major city", "storstad", "innerstad")
    if any(k in raw_lower for k in _METRO):
        return "Urban Metropolis"
    if any(k in raw_lower for k in ("urban", " city", "/city")):
        return "Urban Metropolis"
    if raw_lower in ("city", "urban"):
        return "Urban Metropolis"
    return _fuzzy_match(raw, ENVIRONMENT_LABELS)


def _normalize_socioeconomic(raw: str) -> str | None:
    raw_lower = raw.lower()
    js = _json_lookup("socioeconomic", raw)
    if js is not None:
        return js
    if any(k in raw_lower for k in ("poverty", "poor", "destitute", "fattigdom")):
        return "Poverty"
    _WORKING = ("working class", "lower class", "blue collar", "arbetarklass",
                 "lägre medelklass")
    if any(k in raw_lower for k in _WORKING):
        return "Working Class"
    _MIDDLE = ("middle class", "middle-class", "medelklass", "övre medelklass",
                "högre medelklass", "akademiker", "god ekonomi", "pensionär")
    if any(k in raw_lower for k in _MIDDLE):
        return "Middle Class"
    if any(k in raw_lower for k in ("wealthy", "rich", "affluent", "upper class", "välbärgad", "överklass")):
        return "Wealthy"
    return _fuzzy_match(raw, SOCIOECONOMIC_LABELS)


def _normalize_civil_status(raw: str) -> str:
    raw_lower = raw.lower()
    js = _json_lookup("civil_status", raw)
    if js is not None:
        return js
    if any(k in raw_lower for k in ("skild", "frånskild", "separated", "divorced")):
        return "Divorced"
    if any(k in raw_lower for k in ("singel", "ogift", "single", "never married")):
        return "Single/Never Married"
    if any(k in raw_lower for k in ("gift", "cohabiting", "sambo", "married")):
        return "Married"
    if any(k in raw_lower for k in ("änka", "änkling", "widow")):
        return "Widowed"
    return raw


def _normalize_industry_sector(raw: str) -> str:
    _EXACT = {
        "Agriculture/Forestry/Fishing": "Agriculture & Forestry",
        "Manufacturing/Industry": "Manufacturing & Industry",
        "Retail & Service": "Retail & Service",
        "IT/Technology": "IT & Technology",
        "Public Administration/Defense": "Public Administration",
        "Education": "Education",
        "Healthcare/Social Work": "Healthcare & Social",
        "Other Services": "Other",
        "Not Applicable": "Not Applicable",
    }
    if raw in _EXACT:
        return _EXACT[raw]
    if not raw:
        return "Not Applicable"
    js = _json_lookup("industry_sector", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if raw_lower in ("not applicable", "ej tillämpbart", "n/a"):
        return "Not Applicable"
    _HEALTH = ("healthcare", "health care", "vård", "omsorg", "medical", "social work",
                "socialtjänst", "social care", "nursing", "pharmacy", "life science",
                "pharmaceutical", "biotech")
    if any(k in raw_lower for k in _HEALTH):
        return "Healthcare & Social"
    if any(k in raw_lower for k in ("education", "utbildning", "school", "university",
                                     "teaching", "academic")):
        return "Education"
    _IT = ("information technology", "information and communication technology", "ict",
           "software", "it ", "it&", "it/", "tech", "data")
    if any(k in raw_lower for k in _IT):
        return "IT & Technology"
    _PUB_ADM = ("public administration", "offentlig förvaltning", "offentlig", "defence",
                "defense", "compulsory social security", "government", "municipality",
                "kommunal")
    if any(k in raw_lower for k in _PUB_ADM):
        return "Public Administration"
    _MANUF = ("manufacturing", "tillverkning", "tillverknings", "industri", "industry",
              "engineering services", "construction", "bygg")
    if any(k in raw_lower for k in _MANUF):
        return "Manufacturing & Industry"
    if any(k in raw_lower for k in ("retail", "handel", "wholesale", "trade", "butik", "detaljhandel", "partihandel")):
        return "Retail & Service"
    if any(k in raw_lower for k in ("agriculture", "forestry", "fishing", "lantbruk", "jordbruk", "skogsbruk")):
        return "Agriculture & Forestry"
    return "Other"


def _normalize_employment_type(raw: str) -> str:
    _EXACT = {
        "Permanent Full-Time": "Permanent Full-time",
        "Permanent Part-Time": "Permanent Part-time",
        "Temporary Full-Time": "Temporary Full-time",
        "Temporary Part-Time": "Temporary Part-time",
        "Self-Employed/Freelance": "Self-Employed",
        "Not Applicable": "Not Applicable",
    }
    if raw in _EXACT:
        return _EXACT[raw]
    js = _json_lookup("employment_type", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if raw_lower in ("not applicable", "ej tillämpbart", "n/a"):
        return "Not Applicable"
    is_temp = any(k in raw_lower for k in ("temp", "fixed", "visstid", "project", "probation", "allmän visstid"))
    is_full = any(k in raw_lower for k in ("full", "heltid", "100%"))
    is_part = any(k in raw_lower for k in ("part", "deltid", "50%", "75%"))
    if any(k in raw_lower for k in ("self-employ", "self employ", "freelan", "egenföretagare", "konsult")):
        return "Self-Employed"
    if is_temp and is_full:
        return "Temporary Full-time"
    if is_temp and is_part:
        return "Temporary Part-time"
    if is_temp:
        return "Temporary Full-time"
    if is_part:
        return "Permanent Part-time"
    if any(k in raw_lower for k in ("permanent", "tillsvidare", "fast", "open-ended")):
        return "Permanent Full-time"
    return raw


def _normalize_income_source(raw: str) -> str:
    if raw in INCOME_SOURCE_LABELS:
        return raw
    js = _json_lookup("income_source", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("sickness", "activity compensation", "sjukersättning", "aktivitetsersättning")):
        return "Sickness / Activity Compensation"
    if any(k in raw_lower for k in ("social assistance", "försörjningsstöd", "socialbidrag")):
        return "Social Assistance"
    _INSURANCE = ("insurance", "allowance", "a-kassa", "sjukpenning",
                   "föräldrapenning", "allowan", "ersättning", "transfer", "benefit")
    if any(k in raw_lower for k in _INSURANCE):
        return "Insurance / Allowance"
    if any(k in raw_lower for k in ("pension",)):
        return "Pension"
    if any(k in raw_lower for k in ("capital", "kapital", "dividend", "interest", "ränta", "aktieutdelning")):
        return "Capital"
    _WAGE = ("wage", "business", "employment", "self-employ", "lön", "företag",
             "egenföretagare", "freelan", "frilans", "work")
    if any(k in raw_lower for k in _WAGE):
        return "Wage / Business"
    return raw


def _normalize_housing_tenure(raw: str) -> str:
    if raw == "Bostadsrätt (cooperative apartment)":
        return "Tenant-owned apartment (bostadsrätt)"
    js = _json_lookup("housing_tenure", raw)
    if js is not None:
        return js
    return raw


def _normalize_birth_country_detail(raw: str) -> str:
    js = _json_lookup("birth_country_detail", raw)
    if js is not None:
        return js
    return raw


def _normalize_parental_structure(raw: str) -> str | None:
    raw_lower = raw.lower()
    js = _json_lookup("parental_structure", raw)
    if js is not None:
        return js
    _SINGLE_PARENT = (
        "single parent", "single mother", "single father", "ensamstående",
        "single biological parent", "single-mother", "single-father",
        "mother only", "father only", "biological mother only",
        "biological father only", "grandparent", "farfar", "farmor",
        "morfar", "mormor", "other relative", "residential care", "guardian",
    )
    if any(k in raw_lower for k in _SINGLE_PARENT):
        return "Single Parent"
    _NUCLEAR = (
        "two parents", "two-parent", "intact", "nuclear", "biological parents",
        "biological mother", "biological father", "mother and father", "blended",
        "stepparent", "stepfamily", "stepmother", "stepfather", "step-parent",
        "two mothers", "two fathers", "same-sex parent",
    )
    if any(k in raw_lower for k in _NUCLEAR):
        return "Nuclear Family"
    if any(k in raw_lower for k in ("divorced", "split", "adoptive", "foster", "orphan", "ward")):
        return "Single Parent"
    if any(k in raw_lower for k in ("couple without", "no children", "childless couple")):
        return "Couple without Children"
    if any(k in raw_lower for k in ("living alone", "alone", "solo")):
        return "Living Alone"
    return _fuzzy_match(raw, PARENTAL_STRUCTURE_LABELS)


# ---------------------------------------------------------------------------
# Batch template parsing helpers
# ---------------------------------------------------------------------------

_BULLET_LINE_RE = re.compile(
    r"^[ \t]*[•\-\*][ \t]*(?P<label>[^:\n]+?)[ \t]*:[ \t]*(?P<value>[^\n]+)$",
    re.MULTILINE,
)

_TEMPLATE_LABEL_ALIASES: dict[str, str] = {
    "age": "age", "ålder": "age",
    "gender": "gender", "kön": "gender", "sex": "gender",
    "location": "location", "plats": "location", "ort": "location",
    "occupation": "occupation", "yrke": "occupation", "sysselsättning": "occupation",
    "region": "region",
    "birth location": "birth_location",
    "birth country detail": "birth_country_detail", "birth country": "birth_country_detail",
    "civil status": "civil_status",
    "household size": "household_size",
    "housing tenure": "housing_tenure",
    "parental structure": "parental_structure",
    "education level": "education_level", "education": "education_level",
    "employment status": "employment_status",
    "industry sector": "industry_sector",
    "employment type": "employment_type",
    "income source": "income_source",
    "socioeconomic class": "socioeconomic_class",
    "current environment type": "current_environment_type",
    "environment": "current_environment_type",
    "ethnicity": "ethnicity",
}


def _parse_template_fields(text: str) -> dict[str, str]:
    """Parse bullet lines ``- Label: value`` into a dict keyed by canonical attribute name."""
    fields: dict[str, str] = {}
    for m in _BULLET_LINE_RE.finditer(text):
        label_raw = m.group("label").strip().lower()
        value = m.group("value").strip()
        if not value:
            continue
        if value.startswith("(Paragraph") or value.startswith("(paragraph"):
            continue
        key = _TEMPLATE_LABEL_ALIASES.get(label_raw)
        if key and key not in fields:
            fields[key] = value
    return fields


def _extract_city_from_location(location_raw: str) -> str | None:
    if not location_raw:
        return None
    city = location_raw.split(",")[0].strip()
    return city if city else None


def _industry_from_occupation(occupation_raw: str) -> str | None:
    occ_lower = occupation_raw.lower()
    for keyword, industry in _OCCUPATION_TO_INDUSTRY.items():
        if keyword in occ_lower:
            return industry
    return None


def _education_from_occupation(occupation_raw: str) -> str | None:
    occ_lower = occupation_raw.lower()
    for keyword in _UNIVERSITY_OCCUPATIONS:
        if keyword in occ_lower:
            return "Post-Secondary 3+ yrs (ISCED 5A)"
    return None


def _employment_type_from_prose(text_lower: str, employment_status: str) -> str:
    if employment_status in ("Unemployed", "Student", "Retired"):
        return "Not Applicable"
    if any(k in text_lower for k in ("self-employed", "egenföretagare", "freelance", "frilans", "egen firma")):
        return "Self-Employed/Freelance"
    if any(k in text_lower for k in ("part-time", "deltid", "halvtid")):
        if any(k in text_lower for k in ("temporary", "tillfällig", "vikariat", "visstid")):
            return "Temporary Part-Time"
        return "Permanent Part-Time"
    if any(k in text_lower for k in ("temporary", "tillfällig", "vikariat", "visstid")):
        return "Temporary Full-Time"
    if employment_status == "Employed":
        return "Permanent Full-Time"
    return "Not Applicable"


def _income_source_from_context(employment_status: str, text_lower: str) -> str:
    if employment_status == "Retired":
        return "Pension"
    _SICK_BENEFIT = ("sjukersättning", "aktivitetsersättning",
                      "sickness benefit", "activity compensation")
    if any(k in text_lower for k in _SICK_BENEFIT):
        return "Sickness / Activity Compensation"
    if employment_status == "Unemployed":
        if any(k in text_lower for k in ("socialbidrag", "försörjningsstöd", "social assistance")):
            return "Social Assistance"
        return "Insurance / Allowance"
    if employment_status == "Student":
        return "Insurance / Allowance"
    if any(k in text_lower for k in ("egenföretagare", "self-employed", "egen firma", "freelance", "frilans")):
        return "Wage / Business"
    return "Wage / Business"


# ---------------------------------------------------------------------------
# Batch format extractor (narrative text)
# ---------------------------------------------------------------------------

_AGE_RE = re.compile(
    r"\b(\d{1,3})[- ]?year[s]?[- ]?old\b"
    r"|\bage[d]?\s+(\d{1,3})\b"
    r"|\b(\d{1,3})-årig\b",
    re.IGNORECASE,
)


def _extract_batch(identity: dict, persona_id: str) -> dict[str, Any] | None:
    """Extract attributes from the batch identity.json format (free-text narrative)."""
    text = identity.get("narrative", "")
    if not text:
        logger.warning("%s: batch identity has empty narrative -- skipping", persona_id)
        return None

    text_lower = text.lower()
    unmapped: list[str] = []
    template = _parse_template_fields(text)

    tpl: dict[str, str] = {}

    def _accept(attr: str, value: Any, valid: set[str] | None) -> None:
        if value is None:
            return
        sv = str(value).strip()
        if not sv:
            return
        if valid is None or sv in valid:
            tpl[attr] = sv

    _civil_valid = {"Single/Never Married", "Married", "Divorced", "Widowed"}
    _housing_valid = set(HOUSING_TENURE_LABELS)
    _household_valid = set(HOUSEHOLD_SIZE_LABELS)
    _parental_valid = set(PARENTAL_STRUCTURE_LABELS)
    _education_valid = set(EDUCATION_LABELS)
    _employment_status_valid = set(EMPLOYMENT_LABELS)
    _birth_location_valid = set(BIRTH_LOCATION_LABELS)
    _ethnicity_valid = set(ETHNICITY_LABELS)
    _environment_valid = set(ENVIRONMENT_LABELS)
    _socio_valid = set(SOCIOECONOMIC_LABELS)
    _region_valid = set(REGION_LABELS)

    if (r := template.get("civil_status")):
        _accept("civil_status", _normalize_civil_status(r), _civil_valid)
    if (r := template.get("housing_tenure")):
        _accept("housing_tenure", _fuzzy_match(r, HOUSING_TENURE_LABELS), _housing_valid)
    if (r := template.get("household_size")):
        _accept("household_size", _fuzzy_match(r, HOUSEHOLD_SIZE_LABELS), _household_valid)
    if (r := template.get("parental_structure")):
        _accept("parental_structure", _normalize_parental_structure(r), _parental_valid)
    if (r := template.get("education_level")):
        _accept("education_level", _normalize_education(r), _education_valid)
    if (r := template.get("employment_status")):
        _accept("employment_status", _normalize_employment(r), _employment_status_valid)
    if (r := template.get("birth_location")):
        _accept("birth_location", _normalize_birth_location(r), _birth_location_valid)
    if (r := template.get("birth_country_detail")):
        _accept("birth_country_detail", _normalize_birth_country_detail(r),
                set(BIRTH_COUNTRY_DETAIL_LABELS))
    if (r := template.get("ethnicity")):
        _accept("ethnicity", _normalize_ethnicity(r), _ethnicity_valid)
    if (r := template.get("current_environment_type")):
        _accept("current_environment_type", _normalize_environment(r), _environment_valid)
    if (r := template.get("socioeconomic_class")):
        _accept("socioeconomic_class", _normalize_socioeconomic(r), _socio_valid)
    if (r := template.get("industry_sector")):
        _accept("industry_sector", _normalize_industry_sector(r), None)
    if (r := template.get("employment_type")):
        _accept("employment_type", _normalize_employment_type(r), None)
    if (r := template.get("income_source")):
        _accept("income_source", _normalize_income_source(r), None)
    if (r := template.get("region")):
        if r in REGION_LABELS:
            _accept("region", r, _region_valid)
        else:
            _accept("region", _fuzzy_match(r, REGION_LABELS), _region_valid)

    # --- Age ---
    age_group = "Non-standard label"
    if "age" in template:
        try:
            age_group = _age_to_group(int(template["age"]))
        except ValueError:
            pass
    if age_group == "Non-standard label":
        m = _AGE_RE.search(text)
        if m:
            raw_age = int(next(g for g in m.groups() if g is not None))
            age_group = _age_to_group(raw_age)
    if age_group == "Non-standard label":
        unmapped.append("age=<not found>")

    # --- Biological sex ---
    biological_sex = "Non-standard label"
    if "gender" in template:
        g = template["gender"].strip().lower()
        if g in ("kvinna", "female", "flicka", "tjej", "f"):
            biological_sex = "Female"
        elif g in ("man", "male", "pojke", "kille", "m"):
            biological_sex = "Male"
    if biological_sex == "Non-standard label":
        if any(k in text_lower for k in ("female", "woman", "she/her", "kvinna", " hon ", "flicka")):
            biological_sex = "Female"
        elif any(k in text_lower for k in (" male", " man ", "he/him", " han ", "pojke")):
            biological_sex = "Male"
    if biological_sex == "Non-standard label":
        unmapped.append("biological_sex=<not found>")

    # --- Region ---
    region = tpl.get("region", "Non-standard label")
    city_name: str | None = None
    if region != "Non-standard label":
        pass
    elif "location" in template:
        city_name = _extract_city_from_location(template["location"])
        if city_name:
            region = _CITY_TO_COUNTY.get(city_name.lower(), "Non-standard label")
        if region == "Non-standard label":
            loc_lower = template["location"].lower()
            for county in REGION_LABELS:
                if county.lower() in loc_lower:
                    region = county
                    break
    if region == "Non-standard label":
        for candidate in REGION_LABELS:
            if candidate.lower() in text_lower:
                region = candidate
                break
    if region == "Non-standard label":
        for c_name, county in _CITY_TO_COUNTY.items():
            if c_name in text_lower:
                region = county
                city_name = city_name or c_name
                break
    if region == "Non-standard label":
        unmapped.append("region=<not found>")

    # --- Current environment type ---
    current_environment_type = tpl.get("current_environment_type", "Non-standard label")
    if current_environment_type != "Non-standard label":
        pass
    elif city_name:
        cl = city_name.lower()
        if cl in _METRO_CITIES:
            current_environment_type = "Urban Metropolis"
        elif cl in _LARGE_CITIES:
            current_environment_type = "Suburban"
        elif cl in _CITY_TO_COUNTY:
            current_environment_type = "Rural/Countryside"
    if current_environment_type == "Non-standard label":
        current_environment_type = _normalize_environment(text) or "Non-standard label"
    if current_environment_type == "Non-standard label":
        unmapped.append("current_environment_type=<not found>")

    # --- Employment status ---
    employment_status = tpl.get("employment_status", "Non-standard label")
    if employment_status != "Non-standard label":
        pass
    elif "occupation" in template:
        occ_lower = template["occupation"].lower()
        if any(k in occ_lower for k in ("student", "studerande")):
            employment_status = "Student"
        elif any(k in occ_lower for k in ("pensionär", "pensionerad", "retired")):
            employment_status = "Retired"
        elif any(k in occ_lower for k in ("arbetslös", "unemployed", "arbetssökande")):
            employment_status = "Unemployed"
        else:
            employment_status = "Employed"
    if employment_status == "Non-standard label":
        employment_status = _normalize_employment(text) or "Non-standard label"
    if employment_status == "Non-standard label":
        if any(k in text_lower for k in ("arbetar", "anställd", "anställning", "tjänst")):
            employment_status = "Employed"
        elif any(k in text_lower for k in ("arbetslös", "arbetssökande")):
            employment_status = "Unemployed"
        elif any(k in text_lower for k in ("studerande", "studerar")):
            employment_status = "Student"
        elif any(k in text_lower for k in ("pensionär", "pensionerad")):
            employment_status = "Retired"
    if employment_status == "Non-standard label":
        unmapped.append("employment_status=<not found>")

    # --- Education level ---
    education_level = tpl.get("education_level", "Non-standard label")
    if education_level != "Non-standard label":
        pass
    elif "occupation" in template:
        education_level = _education_from_occupation(template["occupation"]) or "Non-standard label"
    if education_level == "Non-standard label":
        if any(k in text_lower for k in ("doktorsexamen", "ph.d", "phd", "doctoral degree", "research degree")):
            education_level = "Post-Graduate (ISCED 6)"
        elif any(k in text_lower for k in (
            "university", "universitet", "högskola", "hogskola",
            "bachelor", "master", "kandidatexamen", "magisterexamen",
            "masterexamen", "universitetsutbildning", "högskoleutbildning", "akademisk",
        )):
            education_level = "Post-Secondary 3+ yrs (ISCED 5A)"
        elif any(k in text_lower for k in ("vocational", "yrkeshögskola", "yrkeshogskola", "yrkes", "yh-")):
            education_level = "Post-Secondary < 3 yrs (ISCED 4+5B)"
        elif any(k in text_lower for k in ("gymnasium", "gymnasieskola", "high school", "gymnasie")):
            education_level = "Upper Secondary 3 yrs (ISCED 3A)"
        elif any(k in text_lower for k in ("grundskola", "folkskola", "primary school", "compulsory school")):
            education_level = "Pre-Secondary 9-10 yrs (ISCED 2)"
        elif any(k in text_lower for k in ("no formal", "ingen utbildning")):
            education_level = "Pre-Secondary < 9 yrs (ISCED 1)"
    if education_level == "Non-standard label":
        education_level = _normalize_education(text) or "Non-standard label"
    if education_level == "Non-standard label":
        unmapped.append("education_level=<not found>")

    # --- Industry sector ---
    industry_sector = tpl.get("industry_sector", "Non-standard label")
    if industry_sector != "Non-standard label":
        pass
    elif "occupation" in template:
        raw_industry = _industry_from_occupation(template["occupation"])
        if raw_industry:
            industry_sector = _normalize_industry_sector(raw_industry)
    if industry_sector == "Non-standard label":
        for candidate in INDUSTRY_SECTOR_LABELS:
            if candidate.lower() in text_lower:
                industry_sector = _normalize_industry_sector(candidate)
                break
    if industry_sector == "Non-standard label" and employment_status in ("Student", "Retired", "Unemployed"):
        industry_sector = "Not Applicable"
    if industry_sector == "Non-standard label":
        unmapped.append("industry_sector=<not found>")

    # --- Shared indicators ---
    has_children = any(k in text_lower for k in ("children", "barn", " son ", " sons ", "daughter", "dotter"))
    lives_alone = any(k in text_lower for k in ("lives alone", "bor ensam", "bor själv"))
    has_partner = any(k in text_lower for k in (
        "sambo", "partner", "wife", "husband", "fru", " make ", " makes ",
    ))

    # --- Civil status ---
    civil_status = tpl.get("civil_status", "Non-standard label")
    if civil_status != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("divorced", "divorce", "skild", "frånskild", "separated", "separerad")):
        civil_status = "Divorced"
    elif any(k in text_lower for k in (" gift ", " gift,", " gift.", "married")):
        civil_status = "Married"
    elif any(k in text_lower for k in ("sambo", "cohabiting", "live-in partner", "sammanboende", "särbo")):
        civil_status = "Married"
    elif any(k in text_lower for k in ("änka", "änkling", "widow")):
        civil_status = "Widowed"
    elif any(k in text_lower for k in ("singel", "single", "ogift", "ensamstående", "unmarried",
                                        "ended a relationship", "ended her relationship",
                                        "ended his relationship", "ended a cohabitation")):
        civil_status = "Single/Never Married"
    elif lives_alone and not has_children and not has_partner:
        civil_status = "Single/Never Married"
    if civil_status == "Non-standard label":
        for candidate in CIVIL_STATUS_LABELS:
            if candidate.lower() in text_lower:
                civil_status = _normalize_civil_status(candidate)
                break
    if civil_status == "Non-standard label":
        unmapped.append("civil_status=<not found>")

    # --- Housing tenure ---
    housing_tenure = tpl.get("housing_tenure", "Non-standard label")
    if housing_tenure != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("hyresrätt", "hyreslägenhet", "rental apartment", "rented apartment", "rented")):
        housing_tenure = "Rental apartment"
    elif any(k in text_lower for k in ("bostadsrätt", "bostadsrätts", "condominium", "tenant-owned")):
        housing_tenure = "Tenant-owned apartment (bostadsrätt)"
    elif any(k in text_lower for k in ("villa", "radhus", "house", "detached", "owner-occupied", "owns a home")):
        housing_tenure = "Owner-occupied (villa/house)"
    if housing_tenure == "Non-standard label":
        for candidate in HOUSING_TENURE_LABELS:
            if candidate.lower() in text_lower:
                housing_tenure = _normalize_housing_tenure(candidate)
                break
    if housing_tenure == "Non-standard label":
        unmapped.append("housing_tenure=<not found>")

    # --- Birth location ---
    birth_location = tpl.get("birth_location", "Non-standard label")
    if birth_location != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("born in sweden", "född i sverige")):
        birth_location = "Sweden"
    elif any(k in text_lower for k in ("immigrant", "invandrat", "flykting", "refugee",
                                        "moved to sweden", "flyttade till sverige",
                                        "bakgrund från", "ursprung")):
        birth_location = _normalize_birth_location(text) or "Non-standard label"
    else:
        birth_location = "Sweden"
    if birth_location == "Non-standard label":
        unmapped.append("birth_location=<not found>")

    # --- Birth country detail ---
    birth_country_detail = tpl.get("birth_country_detail", "Non-standard label")
    if birth_country_detail != "Non-standard label":
        pass
    elif birth_location == "Sweden":
        birth_country_detail = "Sweden"
    else:
        for candidate in BIRTH_COUNTRY_DETAIL_LABELS:
            if candidate.lower() in text_lower:
                birth_country_detail = _normalize_birth_country_detail(candidate)
                break
    if birth_country_detail == "Non-standard label":
        unmapped.append("birth_country_detail=<not found>")

    # --- Ethnicity ---
    ethnicity = tpl.get("ethnicity") or _normalize_ethnicity(text)
    if ethnicity is None:
        eth_from_birth = {
            "Sweden": "Swedish",
            "Nordic Country": "European",
            "Europe (Other)": "European",
            "Outside Europe": "Non-European",
        }
        ethnicity = eth_from_birth.get(birth_location, "Non-standard label")
    if ethnicity == "Non-standard label":
        unmapped.append("ethnicity=<not found>")

    # --- Household size ---
    household_size = tpl.get("household_size", "Non-standard label")
    if civil_status == "Married":
        has_partner = True

    child_count = 0
    for pat, n in [("four children", 4), ("fyra barn", 4), ("4 children", 4),
                   ("three children", 3), ("tre barn", 3), ("3 children", 3),
                   ("two children", 2), ("två barn", 2), ("2 children", 2),
                   ("one child", 1), ("ett barn", 1), ("a child", 1), ("1 child", 1)]:
        if pat in text_lower:
            child_count = max(child_count, n)
            break

    if household_size != "Non-standard label":
        pass
    elif lives_alone and not has_children:
        household_size = "1 person"
    elif has_partner and has_children:
        total = 2 + max(child_count, 1)
        if total >= 7:
            household_size = "7+ persons"
        elif total == 6:
            household_size = "6 persons"
        elif total == 5:
            household_size = "5 persons"
        elif total == 4:
            household_size = "4 persons"
        else:
            household_size = "3 persons"
    elif has_partner and not has_children:
        household_size = "2 persons"
    elif has_children and not has_partner:
        total = 1 + max(child_count, 1)
        if total >= 7:
            household_size = "7+ persons"
        elif total == 6:
            household_size = "6 persons"
        elif total == 5:
            household_size = "5 persons"
        elif total == 4:
            household_size = "4 persons"
        elif total == 3:
            household_size = "3 persons"
        else:
            household_size = "2 persons"
    elif lives_alone or civil_status == "Single/Never Married":
        household_size = "1 person"
    if household_size == "Non-standard label":
        unmapped.append("household_size=<not found>")

    # --- Socioeconomic class ---
    socioeconomic_class = tpl.get("socioeconomic_class", "Non-standard label")
    if socioeconomic_class != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("financial strain", "ekonomiska svårigheter", "economic hardship",
                                      "tight budget", "skulder", "debt")):
        socioeconomic_class = "Working Class"
    elif education_level in ("Post-Secondary 3+ yrs (ISCED 5A)", "Post-Graduate (ISCED 6)"):
        socioeconomic_class = "Middle Class"
    elif education_level in ("Pre-Secondary < 9 yrs (ISCED 1)", "Pre-Secondary 9-10 yrs (ISCED 2)",
                             "Upper Secondary ≤ 2 yrs (ISCED 3C)", "Upper Secondary 3 yrs (ISCED 3A)",
                             "Post-Secondary < 3 yrs (ISCED 4+5B)"):
        socioeconomic_class = "Working Class"
    elif employment_status == "Retired":
        socioeconomic_class = "Middle Class"
    elif employment_status == "Employed":
        socioeconomic_class = "Middle Class"
    else:
        socioeconomic_class = _normalize_socioeconomic(text) or "Working Class"
    if socioeconomic_class == "Non-standard label":
        unmapped.append("socioeconomic_class=<not found>")

    # --- Parental structure ---
    parental_structure = tpl.get("parental_structure", "Non-standard label")
    if parental_structure != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("single mother", "single father", "ensamstående med barn",
                                      "ensamstående mamma", "ensamstående pappa",
                                      "solo parent", "ensam vårdnad")):
        parental_structure = "Single Parent"
    elif civil_status == "Divorced" and has_children:
        parental_structure = "Single Parent"
    elif civil_status == "Married" and has_children:
        parental_structure = "Nuclear Family"
    elif civil_status == "Married" and not has_children:
        parental_structure = "Couple without Children"
    elif has_children:
        parental_structure = "Single Parent"
    elif lives_alone or civil_status == "Single/Never Married":
        parental_structure = "Living Alone"
    if parental_structure == "Non-standard label":
        parental_structure = _normalize_parental_structure(text) or "Non-standard label"
    if parental_structure == "Non-standard label":
        unmapped.append("parental_structure=<not found>")

    # --- Employment type ---
    employment_type = tpl.get("employment_type") or _normalize_employment_type(
        _employment_type_from_prose(text_lower, employment_status)
    )

    # --- Income source ---
    income_source = tpl.get("income_source") or _normalize_income_source(
        _income_source_from_context(employment_status, text_lower)
    )

    if unmapped:
        logger.warning("%s: unmapped values (batch): %s", persona_id, ", ".join(unmapped))

    return {
        "age_group": age_group,
        "biological_sex": biological_sex,
        "education_level": education_level,
        "employment_status": employment_status,
        "birth_location": birth_location,
        "ethnicity": ethnicity,
        "current_environment_type": current_environment_type,
        "socioeconomic_class": socioeconomic_class,
        "parental_structure": parental_structure,
        "region": region,
        "birth_country_detail": birth_country_detail,
        "civil_status": civil_status,
        "household_size": household_size,
        "housing_tenure": housing_tenure,
        "industry_sector": industry_sector,
        "employment_type": employment_type,
        "income_source": income_source,
    }


# ---------------------------------------------------------------------------
# Flat / configurable format extractor
# ---------------------------------------------------------------------------

_EUROPEAN_COUNTRIES = {
    "finland", "finl", "norge", "norway", "danmark", "denmark", "island", "iceland",
    "polen", "poland", "tyskland", "germany", "frankrike", "france", "italien", "italy",
    "spanien", "spain", "rumänien", "romania", "ungern", "hungary", "tjeckien", "czech",
    "greece", "grekland", "portugal", "österrike", "austria", "belgien", "belgium",
    "nederländerna", "netherlands", "holland", "ukraine", "ukraina", "serbien", "serbia",
    "kroatien", "croatia", "bosnien", "bosnia", "albanien", "albania", "bulgarien", "bulgaria",
    "slovakien", "slovakia", "litauen", "lithuania", "lettland", "latvia", "estland", "estonia",
    "kosovo", "nordmakedon", "monteneg", "moldov", "vitryssland", "belarus",
    "united kingdom", "uk", "england", "scotland", "wales", "ireland", "irland",
    "schweiz", "switzerland", "slovenien", "slovenia",
}

_NON_EUROPEAN_COUNTRIES = {
    "irak", "iraq", "syrien", "syria", "somalia", "iran", "afghanistan",
    "bagdad", "damaskus", "teheran", "kabul", "mogadishu", "eritrea",
    "etiopien", "ethiopia", "kina", "china", "indien", "india", "pakistan",
    "turkiet", "turkey", "libanon", "lebanon", "palestina", "palestine",
    "marocko", "morocco", "tunisien", "tunisia", "algeriet", "algeria",
    "nigeria", "kenya", "tanzania", "usa", "united states", "brasil", "brazil",
    "mexiko", "mexico", "chile", "colombia", "argentina", "vietnam", "thailand",
    "filippinerna", "philippines", "japan", "sydkorea", "south korea",
    "middle east", "mellanöstern", "north africa", "nordafrika", "sub-saharan",
    "yemen", "jemen", "libyen", "libya", "egypten", "egypt", "jordanien", "jordan",
}


def _birth_location_from_flat(raw: str) -> str:
    """Map flat birth_location (city name or country) to schema category."""
    raw_lower = raw.lower().strip()
    stripped = raw_lower.removesuffix(" kommun").removesuffix(" stad").strip()
    if (stripped in _CITY_TO_COUNTY
            or raw_lower in _CITY_TO_COUNTY
            or any(c.lower() == raw_lower for c in REGION_LABELS)):
        return "Sweden"
    if any(c.lower() in raw_lower for c in REGION_LABELS) or stripped in _CITY_TO_COUNTY:
        return "Sweden"
    if any(k in raw_lower for k in _NON_EUROPEAN_COUNTRIES):
        return "Outside Europe"
    if any(k in raw_lower for k in _EUROPEAN_COUNTRIES):
        return "Europe (Other)"
    result = _normalize_birth_location(raw)
    if result:
        return result
    if "sweden" in raw_lower or "sverige" in raw_lower:
        return "Sweden"
    return "Non-standard label"


def _extract_flat(identity: dict, persona_id: str) -> dict[str, Any] | None:
    """Extract attributes from the flat configurable identity.json format."""
    unmapped: list[str] = []

    raw_age = identity.get("age")
    if raw_age is None:
        logger.warning("%s: missing age -- skipping persona", persona_id)
        return None
    try:
        age_group = _age_to_group(int(raw_age))
    except (ValueError, TypeError):
        logger.warning("%s: non-integer age %r -- skipping persona", persona_id, raw_age)
        return None

    raw_sex = str(identity.get("biological_sex") or "")
    sex_lower = raw_sex.lower().strip()
    if "female" in sex_lower or "kvinna" in sex_lower or sex_lower == "xx":
        biological_sex = "Female"
    elif "male" in sex_lower or sex_lower == "man" or "xy" in sex_lower:
        biological_sex = "Male"
    else:
        biological_sex = None
    if biological_sex is None:
        unmapped.append(f"biological_sex={raw_sex!r}")
        biological_sex = "Non-standard label"

    raw_edu = str(identity.get("education_level") or "")
    education_level = _normalize_education(raw_edu) or "Non-standard label"
    if education_level == "Non-standard label":
        unmapped.append(f"education_level={raw_edu!r}")

    raw_emp = str(identity.get("employment_status") or "")
    employment_status = _normalize_employment(raw_emp) or "Non-standard label"
    if employment_status == "Non-standard label":
        unmapped.append(f"employment_status={raw_emp!r}")

    raw_birth = str(identity.get("birth_location") or "")
    birth_location = _birth_location_from_flat(raw_birth) if raw_birth else "Non-standard label"
    raw_bcd_for_loc = str(identity.get("birth_country_detail") or "")
    bcd_normalized = _normalize_birth_country_detail(raw_bcd_for_loc) if raw_bcd_for_loc else ""
    if bcd_normalized == "Sweden":
        birth_location = "Sweden"
    elif birth_location == "Non-standard label" and bcd_normalized:
        nordic = {"Norway", "Denmark", "Finland"}
        european = {"Poland", "Germany", "United Kingdom", "Ukraine", "Romania",
                    "Bosnia and Herzegovina", "Yugoslavia"}
        if bcd_normalized in nordic:
            birth_location = "Europe (Other)"
        elif bcd_normalized in european:
            birth_location = "Europe (Other)"
        else:
            birth_location = "Outside Europe"
    if birth_location == "Non-standard label":
        unmapped.append(f"birth_location={raw_birth!r}")

    raw_eth = str(identity.get("ethnicity_broad_global_approx") or "")
    ethnicity = _normalize_ethnicity(raw_eth) or "Non-standard label"
    if ethnicity == "Non-standard label":
        unmapped.append(f"ethnicity={raw_eth!r}")

    raw_env = str(identity.get("current_environment_type") or "")
    current_environment_type = _normalize_environment(raw_env) or "Non-standard label"
    if current_environment_type == "Non-standard label":
        unmapped.append(f"current_environment_type={raw_env!r}")

    raw_sec = str(identity.get("socioeconomic_class") or "")
    socioeconomic_class = _normalize_socioeconomic(raw_sec) or "Non-standard label"
    if socioeconomic_class == "Non-standard label":
        unmapped.append(f"socioeconomic_class={raw_sec!r}")

    raw_par = str(identity.get("parental_structure") or "")
    parental_structure = _normalize_parental_structure(raw_par) or "Non-standard label"
    if parental_structure == "Non-standard label":
        unmapped.append(f"parental_structure={raw_par!r}")

    region = str(identity.get("region") or "Non-standard label")
    if region not in REGION_LABELS:
        region = _fuzzy_match(region, REGION_LABELS) or "Non-standard label"

    raw_bcd = str(identity.get("birth_country_detail") or "")
    birth_country_detail = _normalize_birth_country_detail(raw_bcd) if raw_bcd else "Non-standard label"

    raw_cs = str(identity.get("civil_status") or "")
    civil_status = _normalize_civil_status(raw_cs)

    raw_hs = identity.get("household_size")
    if isinstance(raw_hs, int):
        if raw_hs == 1:
            household_size = "1 person"
        elif raw_hs == 2:
            household_size = "2 persons"
        elif raw_hs == 3:
            household_size = "3 persons"
        elif raw_hs == 4:
            household_size = "4 persons"
        elif raw_hs == 5:
            household_size = "5 persons"
        elif raw_hs == 6:
            household_size = "6 persons"
        else:
            household_size = "7+ persons"
    else:
        household_size = _fuzzy_match(str(raw_hs or ""), HOUSEHOLD_SIZE_LABELS) or "Non-standard label"

    raw_ht = str(identity.get("housing_tenure") or "")
    js_ht = _json_lookup("housing_tenure", raw_ht)
    if js_ht is not None:
        housing_tenure = js_ht
    else:
        ht_lower = raw_ht.lower()
        if any(k in ht_lower for k in ("bostadsrätt", "bostadsratt", "cooperative apartment", "tenant-owned")):
            housing_tenure = "Tenant-owned apartment (bostadsrätt)"
        elif any(k in ht_lower for k in ("villa", "radhus", "friköpt", "äganderätt", "owner", "house", "detached")):
            housing_tenure = "Owner-occupied (villa/house)"
        elif any(k in ht_lower for k in ("rental", "rent", "hyresrätt", "hyra", "studentbostad")):
            housing_tenure = "Rental apartment"
        else:
            housing_tenure = _fuzzy_match(raw_ht, HOUSING_TENURE_LABELS) or "Non-standard label"

    raw_ind = str(identity.get("industry_sector") or "")
    js_ind = _json_lookup("industry_sector", raw_ind)
    if js_ind is not None:
        industry_sector = js_ind
    else:
        ind_lower = raw_ind.lower()
        if any(k in ind_lower for k in ("vård", "sjukvård", "omsorg", "healthcare")):
            industry_sector = _normalize_industry_sector("Healthcare/Social Work")
        elif any(k in ind_lower for k in ("finansiell", "bank", "finans")):
            industry_sector = _normalize_industry_sector("IT/Technology")
        elif any(k in ind_lower for k in ("detaljhandel", "handel")):
            industry_sector = _normalize_industry_sector("Retail & Service")
        elif any(k in ind_lower for k in ("utbildning", "forskning")):
            industry_sector = _normalize_industry_sector("Education")
        elif "offentlig förvaltning" in ind_lower:
            industry_sector = _normalize_industry_sector("Public Administration/Defense")
        elif any(k in ind_lower for k in ("teknik", " it", "information")):
            industry_sector = _normalize_industry_sector("IT/Technology")
        elif any(k in ind_lower for k in ("kultur", "kreativ")):
            industry_sector = _normalize_industry_sector("Other Services")
        elif any(k in ind_lower for k in ("bygg", "construction", "tillverkning", "industri")):
            industry_sector = _normalize_industry_sector("Manufacturing/Industry")
        elif raw_ind in INDUSTRY_SECTOR_LABELS:
            industry_sector = _normalize_industry_sector(raw_ind)
        else:
            industry_sector = _normalize_industry_sector(
                _fuzzy_match(raw_ind, INDUSTRY_SECTOR_LABELS) or "Non-standard label"
            )

    raw_et = str(identity.get("employment_type") or "")
    js_et = _json_lookup("employment_type", raw_et)
    if js_et is not None:
        employment_type = js_et
    else:
        et_lower = raw_et.lower()
        _NA = ("not applicable", "n/a", "ej tillämpligt",
               "ej relevant", "ingen anställning")
        _SELF = ("self-employed", "freelance", "egenföretagare",
                 "enskild firma", "konsultanställning")
        _TEMP_MISC = ("projektanställning", "visstidsanställning",
                      "provanställning", "praktik")
        _PERM = ("permanent", "tillsvidare")
        _TEMP = ("temporary", "tillfällig", "visstid")
        if any(k in et_lower for k in _NA):
            employment_type = "Not Applicable"
        elif any(k in et_lower for k in _SELF):
            employment_type = "Self-Employed"
        elif any(k in et_lower for k in _TEMP_MISC):
            employment_type = "Temporary Full-time"
        elif (any(k in et_lower for k in _PERM)
              and any(k in et_lower for k in ("full", "heltid"))):
            employment_type = "Permanent Full-time"
        elif (any(k in et_lower for k in _PERM)
              and any(k in et_lower for k in ("part", "deltid"))):
            employment_type = "Permanent Part-time"
        elif (any(k in et_lower for k in _TEMP)
              and any(k in et_lower for k in ("full", "heltid"))):
            employment_type = "Temporary Full-time"
        elif (any(k in et_lower for k in _TEMP)
              and any(k in et_lower for k in ("part", "deltid"))):
            employment_type = "Temporary Part-time"
        elif "tillsvidareanställning" in et_lower or "heltidsanställning" in et_lower:
            employment_type = "Permanent Full-time"
        else:
            employment_type = _normalize_employment_type(raw_et)

    raw_inc = str(identity.get("income_source") or "")
    income_source = _normalize_income_source(raw_inc) if raw_inc else "Wage / Business"
    if income_source not in INCOME_SOURCE_LABELS:
        income_source = _normalize_income_source(
            _fuzzy_match(raw_inc, INCOME_SOURCE_LABELS) or "Wage / Business"
        )

    if unmapped:
        logger.warning("%s: unmapped flat fields: %s", persona_id, "; ".join(unmapped))

    return {
        "age_group": age_group,
        "biological_sex": biological_sex,
        "education_level": education_level,
        "employment_status": employment_status,
        "birth_location": birth_location,
        "ethnicity": ethnicity,
        "current_environment_type": current_environment_type,
        "socioeconomic_class": socioeconomic_class,
        "parental_structure": parental_structure,
        "region": region,
        "birth_country_detail": birth_country_detail,
        "civil_status": civil_status,
        "household_size": household_size,
        "housing_tenure": housing_tenure,
        "industry_sector": industry_sector,
        "employment_type": employment_type,
        "income_source": income_source,
    }


# ---------------------------------------------------------------------------
# Format detection helpers
# ---------------------------------------------------------------------------

def _is_flat(identity: dict) -> bool:
    return "age" in identity and not any(k.startswith("level_") for k in identity) and "narrative" not in identity


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_individual(identity_path: Path) -> dict[str, Any] | None:
    """Read an identity.json file, auto-detect format, and return a flat attribute dict.

    Returns None if the file cannot be read or the persona is critically incomplete.
    """
    persona_id = identity_path.parent.name
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s: could not read identity.json: %s", persona_id, exc)
        return None

    if "narrative" in identity:
        attrs = _extract_batch(identity, persona_id)
    elif _is_flat(identity):
        attrs = _extract_flat(identity, persona_id)
    else:
        logger.warning("%s: unrecognised identity format (keys: %s) -- skipping", persona_id, list(identity))
        return None

    if attrs is None:
        return None

    return {"id": persona_id, **attrs}

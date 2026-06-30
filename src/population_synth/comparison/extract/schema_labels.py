"""Target-schema label constants and lookup maps for demographic extraction.

These constants define the canonical category labels (matching
``scb_population.json`` / ISTAT references) plus the static lookup maps used by
the normalizers and prose-inference helpers: city -> county/region tables,
occupation -> industry / education tables, and the batch-template label aliases.

All values here are *structural* (code-to-label maps, query category labels),
not probability tables, so they fall outside the no-synthetic-distributions
rule.
"""

from __future__ import annotations

import json
import re

from population_synth._paths import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Target schema labels (must match scb_population.json exactly)
#
# Where the SCB category-mapping JSON already declares a canonical category list
# (``output_categories`` / ``age_groups.groups``), that file is the single
# source of truth and the constant below is *loaded* from it rather than
# re-declared -- the JSON files under config/mapping/scb/
# own the values. Constants without a config counterpart (input-side label
# lists, lists absent from config) remain declared here.
# ---------------------------------------------------------------------------

_SCB_MAPPINGS_DIR = PROJECT_ROOT / "config" / "mapping" / "scb"


def _load_output_categories(filename: str, key: str = "output_categories") -> list[str]:
    """Return the canonical category list declared in an SCB mapping JSON.

    Fail-fast: a missing file, missing key, or non-list/empty value raises
    rather than silently falling back to a hardcoded list.
    """
    path = _SCB_MAPPINGS_DIR / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    if key not in data:
        raise KeyError(f"{path}: expected '{key}' to define the canonical category list")
    categories = data[key]
    if not isinstance(categories, list) or not categories:
        raise ValueError(f"{path}: '{key}' must be a non-empty list")
    return categories


AGE_GROUPS = [group["label"] for group in _load_output_categories("age_groups.json", "groups")]

EDUCATION_LABELS = _load_output_categories("education.json")

EMPLOYMENT_LABELS = ["Employed", "Unemployed", "Student", "Retired"]

BIRTH_LOCATION_LABELS = ["Sweden", "Nordic Country", "Europe (Other)", "Outside Europe"]

ETHNICITY_LABELS = _load_output_categories("ethnicity.json")

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

BIRTH_COUNTRY_DETAIL_LABELS = _load_output_categories("birth_country_detail.json")

CIVIL_STATUS_LABELS = [
    "Single/Never Married",
    "Married/Cohabiting",
    "Divorced/Separated",
    "Widowed",
]

HOUSEHOLD_SIZE_LABELS = _load_output_categories("household_size.json")

HOUSING_TENURE_LABELS = _load_output_categories("housing_tenure.json")

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

INCOME_SOURCE_LABELS = _load_output_categories("income_source.json")

# Canonical OUTPUT values the Swedish normalizers actually emit (NOT the *_LABELS
# input constants above, whose casing / slash-forms differ from real output).
# employment_type and civil_status historically returned the raw string on
# no-match instead of "Non-standard label", letting unmapped values masquerade
# as real categories; the membership checks below restore consistent accounting.
_EMPLOYMENT_TYPE_OUTPUT = frozenset({
    "Permanent Full-time", "Permanent Part-time", "Temporary Full-time",
    "Temporary Part-time", "Self-Employed", "Not Applicable",
})
_CIVIL_STATUS_OUTPUT = frozenset({
    "Single/Never Married", "Married", "Divorced", "Widowed",
})


# ---------------------------------------------------------------------------
# Italian label constants
# ---------------------------------------------------------------------------

EDUCATION_LABELS_IT = [
    "No Formal Education",
    "High School (Liceo/Professionale)",
    "University Degree",
]

EMPLOYMENT_LABELS_IT = ["Employed", "Not Employed"]

BIRTH_LOCATION_LABELS_IT = ["Italy", "Europe (Other)", "Outside Europe"]

REGION_LABELS_IT = [
    "Piemonte", "Valle d'Aosta", "Liguria", "Lombardia",
    "Trentino-Alto Adige/Südtirol", "Veneto", "Friuli-Venezia Giulia",
    "Emilia-Romagna", "Toscana", "Umbria", "Marche", "Lazio",
    "Abruzzo", "Molise", "Campania", "Puglia", "Basilicata",
    "Calabria", "Sicilia", "Sardegna",
]

CIVIL_STATUS_LABELS_IT = [
    "Single", "Married", "Divorced", "Widowed", "Separated", "Civil Partnership",
]

HOUSING_TENURE_LABELS_IT = ["Owner-occupied", "Rental"]

INDUSTRY_SECTOR_LABELS_IT = [
    "Professional & Managerial",
    "Clerical & Administrative",
    "Craft & Technical",
    "Elementary Occupations",
    "Not Applicable",
]

EMPLOYMENT_TYPE_LABELS_IT = [
    "Permanent|Full-time", "Permanent|Part-time",
    "Temporary|Full-time", "Temporary|Part-time",
    "Unspecified|Full-time", "Unspecified|Part-time",
    "Not Applicable",
]

BIRTH_COUNTRY_DETAIL_LABELS_IT = [
    "Italy", "Romania", "Albania", "Morocco", "China", "Ukraine",
    "Philippines", "Moldova", "India", "Bangladesh", "Pakistan",
    "Nigeria", "Egypt", "Senegal", "Tunisia", "Serbia",
    "North Macedonia", "Germany", "France", "Spain", "Poland",
    "Russia", "Turkey", "Other",
]

HOUSEHOLD_SIZE_LABELS_IT = ["1", "2", "3", "4", "5", "GE6"]

PARENTAL_STRUCTURE_LABELS_IT = [
    "Living Alone", "Single Parent", "Couple without Children",
    "Nuclear Family", "Extended Family",
]

SOCIOECONOMIC_LABELS_IT = ["Poverty", "Working Class", "Middle Class", "Wealthy"]

_CITY_TO_REGION_IT: dict[str, str] = {
    "roma": "Lazio", "milano": "Lombardia", "napoli": "Campania",
    "torino": "Piemonte", "palermo": "Sicilia", "genova": "Liguria",
    "bologna": "Emilia-Romagna", "firenze": "Toscana", "bari": "Puglia",
    "catania": "Sicilia", "venezia": "Veneto", "verona": "Veneto",
    "messina": "Sicilia", "padova": "Veneto", "trieste": "Friuli-Venezia Giulia",
    "brescia": "Lombardia", "taranto": "Puglia", "reggio calabria": "Calabria",
    "reggio emilia": "Emilia-Romagna", "modena": "Emilia-Romagna",
    "perugia": "Umbria", "cagliari": "Sardegna", "parma": "Emilia-Romagna",
    "livorno": "Toscana", "foggia": "Puglia", "l'aquila": "Abruzzo",
    "pescara": "Abruzzo", "ancona": "Marche", "potenza": "Basilicata",
    "campobasso": "Molise", "aosta": "Valle d'Aosta",
    "trento": "Trentino-Alto Adige/Südtirol", "bolzano": "Trentino-Alto Adige/Südtirol",
    "rome": "Lazio", "milan": "Lombardia", "naples": "Campania",
    "turin": "Piemonte", "florence": "Toscana", "venice": "Veneto",
    "genoa": "Liguria",
}


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
# Batch template parsing constants
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

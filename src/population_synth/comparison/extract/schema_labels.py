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

INCOME_SOURCE_LABELS = _load_output_categories("income_source.json")


# ---------------------------------------------------------------------------
# Italian label constants
# ---------------------------------------------------------------------------

EDUCATION_LABELS_IT = [
    "No Formal Education",
    "High School (Liceo/Professionale)",
    "University Degree",
]


# ---------------------------------------------------------------------------
# Occupation -> industry / education inference tables (prose inference)
# ---------------------------------------------------------------------------

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

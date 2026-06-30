"""Swedish (SCB) free-text -> schema-label normalizers.

Each ``_normalize_*`` maps a raw free-form value (LLM output or narrative
fragment) to a canonical Swedish schema label, trying the JSON
``pipeline_label_mappings`` first and then keyword heuristics, falling back to
substring fuzzy matching.  Also holds the shared ``_age_to_group`` bucketing and
``_fuzzy_match`` helper used across both extractors.
"""

from __future__ import annotations

from population_synth.comparison.extract.mappings import _json_lookup
from population_synth.comparison.extract.schema_labels import (
    BIRTH_LOCATION_LABELS,
    EDUCATION_LABELS,
    EMPLOYMENT_LABELS,
    ENVIRONMENT_LABELS,
    ETHNICITY_LABELS,
    INCOME_SOURCE_LABELS,
    PARENTAL_STRUCTURE_LABELS,
    SOCIOECONOMIC_LABELS,
)

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
    raw_lower = raw.lower().replace("_", " ")
    if raw in EDUCATION_LABELS:
        return raw
    js = _json_lookup("education", raw)
    if js is not None:
        return js
    _POSTGRAD = ("post-graduate", "postgraduate", "phd", "doctoral", "doktors", "research degree",
                  "licentiate", "isced 6", "isced97 6")
    if any(k in raw_lower for k in _POSTGRAD):
        return "Post-Graduate (ISCED 6)"
    _POSTSEC3 = ("post-secondary 3", "isced 5a", "isced97 5a", "university", "degree", "bachelor",
                  "master", "kandidat", "magister", "högskolex", "högskole", "hogskola", "akademisk",
                  "universitet", "tertiary", "undergraduate", "baccalaure", "first cycle",
                  "higher education")
    if any(k in raw_lower for k in _POSTSEC3):
        return "Post-Secondary 3+ yrs (ISCED 5A)"
    _POSTSEC_LT3 = ("post-secondary <", "isced 4", "isced 5b", "isced97 4", "isced97 5b",
                     "vocational", "yrkeshogskola", "yrkeshögskola", "yrkes", "higher vocational",
                     "yh-")
    if any(k in raw_lower for k in _POSTSEC_LT3):
        return "Post-Secondary < 3 yrs (ISCED 4+5B)"
    # Lower secondary maps to ISCED 2 -- guard before the generic "secondary education"
    # keyword below would otherwise sweep it into upper secondary.
    if "lower secondary" in raw_lower:
        return "Pre-Secondary 9-10 yrs (ISCED 2)"
    _UPPER_SEC3 = ("upper secondary 3", "upper-secondary", "isced 3a", "isced97 3a", "gymnasium",
                    "high school", "gymnasieskola", "gymnasie", "gymnasial", "secondary education",
                    "secondary school", "higher secondary")
    if any(k in raw_lower for k in _UPPER_SEC3):
        return "Upper Secondary 3 yrs (ISCED 3A)"
    if any(k in raw_lower for k in ("upper secondary", "isced 3c", "isced97 3c")):
        return "Upper Secondary ≤ 2 yrs (ISCED 3C)"
    _PRESEC9 = ("pre-secondary 9", "isced 2", "isced97 2", "grundskola", "compulsory",
                 "elementary", "primary school", "folkskola", "realskoleexamen")
    if any(k in raw_lower for k in _PRESEC9):
        return "Pre-Secondary 9-10 yrs (ISCED 2)"
    _PRESEC_LT9 = ("pre-secondary <", "isced 1", "isced97 1", "no formal", "primary",
                    "ingen utbildning", "ingen formell", "lägre grundskola")
    if any(k in raw_lower for k in _PRESEC_LT9):
        return "Pre-Secondary < 9 yrs (ISCED 1)"
    if any(k in raw_lower for k in ("unknown", "not reported", "uppgift saknas")):
        return "Unknown / Not reported"
    return _fuzzy_match(raw, EDUCATION_LABELS)


def _normalize_employment(raw: str) -> str | None:
    raw_lower = raw.lower().replace("_", " ")
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
                  "deltid", "tillsvidare", "sysselsatt", "förvärvsarbetande",
                  "yrkesverksam", "arbetar", "full time", "part time", "selvständig",
                  "self-employ", "freelanc", "egenföretag", "företagare", "frilans",
                  "eget företag", "näringsidkare", "konstnär", "projektledare",
                  "forskare", "tjänsteman", "lönearbetande", "kok",
                  "praktikant", "uppdragstagare")
    if any(k in raw_lower for k in _EMPLOYED):
        return "Employed"
    _UNEMPLOYED = ("unemploy", "jobless", "seeking", "arbetssökande", "arbetslos",
                    "arbetslös", "arbetsträning", "arbetstränade",
                    "a-kassa", "försörjning", "hemmafru", "hemvårdare")
    if any(k in raw_lower for k in _UNEMPLOYED):
        return "Unemployed"
    if any(k in raw_lower for k in ("student", "study", "school", "studying", "studerande",
                                     "studierande")):
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
    js = _json_lookup("ethnicity", raw)
    if js is not None:
        return js
    if any(k in raw_lower for k in ("caucasian", "white", "swedish", "svensk")):
        return "Swedish"
    if any(k in raw_lower for k in ("nordic", "scandina", "finnish", "finsk", "dansk", "norsk", "isländsk", "nordisk", "skandinavisk")):
        return "Nordic"
    if any(k in raw_lower for k in ("european", "southern european", "eastern european", "östeuropeisk", "europeisk")):
        return "European"
    _NON_EU = ("middle eastern", "african", "asian", "hispanic", "latino",
                "non-european", "mixed", "indigenous", "chaldean", "assyrisk", "syriansk",
                "utomeuropeisk", "mellanöstern", "afrikansk", "asiatisk")
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
    raw_lower = raw.lower().replace("_", " ")
    js = _json_lookup("socioeconomic", raw)
    if js is not None:
        return js
    _POVERTY = ("poverty", "poor", "destitute", "fattigdom", "låginkomsttagare",
                "low income", "low-income", "lower income", "lower-income",
                "economic precariat", "precariat",
                "povertà", "basso reddito", "classe bassa", "marginalizzat")
    if any(k in raw_lower for k in _POVERTY):
        return "Poverty"
    _WORKING = ("working class", "lower class", "blue collar", "blue-collar", "arbetarklass",
                 "arbetar", "lägre medelklass", "nedre mellanklass", "skilled worker",
                 "service worker", "semi-skilled", "semi skilled",
                 "classe operaia", "classe lavoratrice", "operaio", "ceto popolare",
                 "lavorante", "medio-bass", "medio bass", "media bass",
                 "classe media bass", "ceto medio-bass", "ceto medio bass",
                 "classe subaltern", "student", "studerande")
    if any(k in raw_lower for k in _WORKING):
        return "Working Class"
    _MIDDLE = ("middle class", "middle-class", "medelklass", "mellanklass", "övre medelklass",
                "högre medelklass", "akademiker", "akademi", "god ekonomi", "pensionär",
                "mellanstora tjänstemän", "mellan-tjänstemän", "kvalificerad tjänsteman",
                "professional", "upper middle", "upper-middle", "lower middle", "lower-middle",
                "middle income", "middle-income", "white collar", "white-collar",
                "managerial", "administrative", "median income", "above median",
                "classe media", "ceto medio", "medio-alt", "medio alt",
                "media-alt", "media alt", "borghes", "classe media alt",
                "classe media elevat", "classe dirigent", "classe dirigenz",
                "mellanskikt", "medelinkomst", "giovane professionista",
                "giovani professionisti", "mediano", "mediocre",
                "högskoleutbildad", "tjänsteman", "tjänstemän", "it-", "konsult",
                "företagare", "egenföretagare", "professionell", "urban",
                "mittenklass", "mittelsocial", "middelklass", "mellanposition",
                "mellanliggande", "intellektuell")
    if any(k in raw_lower for k in _MIDDLE):
        return "Middle Class"
    _WEALTHY = ("wealthy", "rich", "affluent", "upper class", "välbärgad",
                 "överklass", "högre tjänstemän", "high income", "high-income",
                 "higher income", "higher-income", "high socioeconomic", "corporate class",
                 "elite",
                 "alta borghesia", "alta buona", "classe elevat", "classe emergente",
                 "kapitalist", "hög inkomst", "höginkomst",
                 "comfortable income", "high-earning", "high earning")
    if any(k in raw_lower for k in _WEALTHY):
        return "Wealthy"
    return _fuzzy_match(raw, SOCIOECONOMIC_LABELS)


def _normalize_civil_status(raw: str) -> str:
    raw_lower = raw.lower()
    js = _json_lookup("civil_status", raw)
    if js is not None:
        return js
    if any(k in raw_lower for k in ("skild", "frånskild", "separated", "divorced")):
        return "Divorced"
    if any(k in raw_lower for k in ("singel", "ogift", "single", "never married", "ensamstående", "ensam")):
        return "Single/Never Married"
    # Cohabiting / partnered descriptors collapse to the Married/Cohabiting bucket,
    # consistent with the existing "sambo"/"cohabiting" handling.
    if any(k in raw_lower for k in (
        "gift", "cohabiting", "cohabit", "habiting", "habitant", "sambo", "samboende",
        "särbo", "married", "partner", "relation", "förhållande", "registrerad partner",
    )):
        return "Married"
    if any(k in raw_lower for k in ("änka", "änkling", "änklig", "änkeman", "widow")):
        return "Widowed"
    return raw


def _normalize_industry_sector(raw: str) -> str:
    # Exact category-label translations (the labels the LLM is handed) live in
    # the JSON pipeline_label_mappings; only morphological generalization remains
    # here.
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
    # Exact category-label translations (the labels the LLM is handed) live in
    # the JSON pipeline_label_mappings; only morphological generalization remains
    # here.
    js = _json_lookup("employment_type", raw)
    if js is not None:
        return js
    raw_lower = raw.lower().replace("_", " ")
    if raw_lower in ("not applicable", "ej tillämpbart", "n/a"):
        return "Not Applicable"
    is_temp = any(k in raw_lower for k in ("temp", "fixed", "visstid", "project", "probation",
                                           "allmän visstid", "tidkontrakt", "tidsbegräns",
                                           "timanställ", "internship", "seasonal"))
    is_full = any(k in raw_lower for k in ("full", "heltid", "100%"))
    is_part = any(k in raw_lower for k in ("part", "deltid", "50%", "75%"))
    if any(k in raw_lower for k in ("self-employ", "self employ", "freelan", "egenföretagare", "konsult",
                                    "egenanställd", "aktiebolag")):
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
    if "vikarie" in raw_lower:
        return "Temporary Full-time"
    if any(k in raw_lower for k in ("volontär", "arbetsträning")):
        return "Not Applicable"
    if "pensionsåldern" in raw_lower:
        return "Temporary Full-time"
    # A (full-time) student is not employed; a job-bearing student term (studentjobb,
    # student assistant) is left to fall through since its contract type is unknown.
    if "student" in raw_lower and not any(
        k in raw_lower for k in ("jobb", "job", "arbet", "assistant", "anställ", "worker", "intern")
    ):
        return "Not Applicable"
    if any(k in raw_lower for k in ("pension", "pensionär", "pensioner")):
        return "Not Applicable"
    # Explicit full-time descriptor with no temp/part/self signal -> permanent full-time,
    # matching the existing default that bare "permanent"/"tillsvidare" maps to full-time.
    if is_full:
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
    raw_lower = raw.lower().replace("_", " ")
    js = _json_lookup("parental_structure", raw)
    if js is not None:
        return js
    _SINGLE_PARENT = (
        "single parent", "single-parent", "single mother", "single father", "ensamstående",
        "single biological parent", "single-mother", "single-father",
        "mother only", "father only", "biological mother only",
        "biological father only", "grandparent", "farfar", "farmor",
        "morfar", "mormor", "other relative", "residential care", "guardian",
        "shared custody", "shared residency", "separated parents",
        "skilda föräldrar", "växelvis boende", "one biological parent",
        "widowed mother", "widowed father", "unwed",
        "genitore solo", "genitore singolo", "madre sola", "padre solo",
        "monogenitor", "famiglia monogenitorial", "genitore unico",
        "enskild mor", "enskild far", "enskild föräld", "enkel föräld",
        "monofamilj", "monoparental",
    )
    if any(k in raw_lower for k in _SINGLE_PARENT):
        return "Single Parent"
    _NUCLEAR = (
        "two parents", "two-parent", "two parent", "intact", "nuclear", "biological parents",
        "biological mother", "biological father", "mother and father", "blended",
        "stepparent", "stepfamily", "step-family", "stepchild", "stepmother", "stepfather",
        "step-parent", "two mothers", "two fathers", "same-sex parent", "same-sex couple",
        "same sex couple", "same sex", "heterosexual parents", "married parents",
        "two married parents", "cohabit", "traditional", "unmarried cohabiting",
        "both parents", "gift par", "gifta",
        "tvåförälder", "tvåföräldra", "två föräldrar", "båda föräldra",
        "båda biologiska föräldra", "biologiska föräldra", "heterosexuella föräldra",
        "föräldrar tillsammans", "nukleär", "borgerlig famil", "borgerlig hushåll",
        "ombildad famil", "närståendefamilj", "sambo",
        "father and mother", "mother and father", "mother-father", "mother father",
        "due genitori", "entrambi i genitori", "coppia coniugat", "coppia sposat",
        "married couple", "madre e padre", "madre, padre", "genitori biologici",
        "famiglia nucleare", "nucleo familiar", "con figli",
    )
    if any(k in raw_lower for k in _NUCLEAR):
        return "Nuclear Family"
    if any(k in raw_lower for k in ("famiglia estesa", "famiglia allargata", "extended",
                                     "multigenerational")):
        return "Extended Family"
    if any(k in raw_lower for k in ("divorced", "split", "adoptive", "foster", "orphan", "ward")):
        return "Single Parent"
    if any(k in raw_lower for k in ("couple without", "no children", "childless couple",
                                     "coppia senza figli", "senza figli", "dink", "childless")):
        return "Couple without Children"
    if any(k in raw_lower for k in ("living alone", "alone", "solo",
                                     "vive da sol", "vivo da sol", "single person",
                                     "single-person", "enkelhushåll", "enskilt hushåll",
                                     "enskild hushåll")):
        return "Living Alone"
    return _fuzzy_match(raw, PARENTAL_STRUCTURE_LABELS)

"""Italian (ISTAT) free-text -> schema-label normalizers.

Each ``_normalize_*_it`` maps a raw free-form value to a canonical Italian
schema label, trying the Italian JSON ``pipeline_label_mappings`` first and then
Italian/English keyword heuristics.
"""

from __future__ import annotations

from population_synth.comparison.extract.mappings import _json_lookup_it
from population_synth.comparison.extract.schema_labels import EDUCATION_LABELS_IT


def _normalize_education_it(raw: str) -> str | None:
    if raw in EDUCATION_LABELS_IT:
        return raw
    js = _json_lookup_it("education", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("laurea", "university", "degree", "dottorato", "master",
                                      "formazione professionale avanzata", "post-graduate", "postgraduate")):
        return "University Degree"
    if any(k in raw_lower for k in ("liceo", "diploma", "maturità", "istituto", "secondary",
                                     "high school", "scuola superiore", "professionale", "tecnico",
                                     "formazione")):
        return "High School (Liceo/Professionale)"
    if any(k in raw_lower for k in ("elementare", "media", "obbligo", "primary", "no formal",
                                     "nessun", "analfabet", "alfabetizzazione", "scuola primaria")):
        return "No Formal Education"
    return None


def _normalize_employment_it(raw: str) -> str | None:
    js = _json_lookup_it("employment", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("not employed", "disoccupat", "pensionat", "pensione",
                                     "ritirat", "student", "casaling", "inattiv", "inoccupat",
                                     "unemploy", "retire", "neo-laureat", "neolaureato",
                                     "neolaureata", "in cerca", "cerca lavoro",
                                     "senza occupazione", "job search", "recently graduated",
                                     "stagista", "tirocinante", "apprendista", "borsista",
                                     "stage", "homemaker", "casalinga", "stay-at-home",
                                     "materne", "nessun impiego")):
        return "Not Employed"
    if any(k in raw_lower for k in ("employ", "occupat", "lavora", "impiegat", "dipendente",
                                     "manager", "dirigent", "responsabil", "docente",
                                     "professore", "professionista", "imprendit", "artigian",
                                     "tecnic", "ingegner", "commerc", "consulen",
                                     "amministrat", "autonomo", "freelance", "libero",
                                     "fulltime", "part-time", "parttime", "a tempo",
                                     "in carriera", "in occupazione", "titolar", "costrutt")):
        return "Employed"
    return None


def _normalize_birth_location_it(raw: str) -> str | None:
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("domestic", "italy", "italia", "nato in italia", "italian")):
        return "Italy"
    if any(k in raw_lower for k in ("europe", "europa", "eu ", "european")):
        return "Europe (Other)"
    if any(k in raw_lower for k in ("outside", "non-eu", "extra", "abroad", "estero", "fuori")):
        return "Outside Europe"
    return None


def _normalize_civil_status_it(raw: str) -> str:
    js = _json_lookup_it("civil_status", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("single", "celibe", "nubile", "unmarried")):
        return "Single"
    if any(k in raw_lower for k in ("married", "coniugat", "sposat")):
        return "Married"
    if any(k in raw_lower for k in ("divorced", "divorziat")):
        return "Divorced"
    if any(k in raw_lower for k in ("widowed", "vedov")):
        return "Widowed"
    if any(k in raw_lower for k in ("separated", "separat")):
        return "Separated"
    if any(k in raw_lower for k in ("civil partnership", "unione civile", "convivente")):
        return "Civil Partnership"
    return raw


def _normalize_housing_tenure_it(raw: str) -> str:
    js = _json_lookup_it("housing_tenure", raw)
    if js is not None:
        return js
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ("owner", "owned", "proprietar", "proprietà", "mortgage",
                                     "mutuo", "acquistato", "casa", "villa",
                                     "appartamento proprio", "condominio", "ipoteca")):
        return "Owner-occupied"
    if any(k in raw_lower for k in ("rental", "rent", "affitto", "locatar", "inquilin", "tenant",
                                     "locazione", "canone")):
        return "Rental"
    return raw

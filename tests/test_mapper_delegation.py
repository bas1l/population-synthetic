"""End-to-end checks that the thinned mappers delegate to the shared resolver.

Phase 2 gutted ``real_mapper/base.py`` and ``synthetic_mapper/base.py`` into
thin loaders over :mod:`population_synthetic.analysis.mapping.mapping_engine`, driven by the
new symmetric per-attribute config (``values`` / ``real`` / ``synthetic``) plus
an ``_index.json`` master. Production config is not migrated until Phase 3, so these
tests build small in-memory ``mappings`` dicts in the *new* shape (mirroring what
``load_mappings`` produces: one entry per file stem, plus the ``_index`` master) and
drive the concrete base classes directly.

They exercise the behaviours the base classes must preserve: the ``id`` passthrough,
the raw ``age`` passthrough / persona-skip gate, composite (``employment_type``)
extraction, ``refine_from`` cross-field resolution, ``absent`` directives, and the
narrative-format skip.
"""

from __future__ import annotations

from population_synthetic.analysis.mapping.real_mapper.base import BaseRealMapper
from population_synthetic.analysis.mapping.synthetic_mapper.base import BaseSyntheticMapper
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED

# ---------------------------------------------------------------------------
# Shared new-shape config, keyed by file stem (as load_mappings would return),
# plus the ``_index`` master listing the comparison attributes in axis order.
# ---------------------------------------------------------------------------

_INDEX = {
    "attributes": {
        "age_group": "age.json",
        "biological_sex": "biological_sex.json",
        "education_level": "education.json",
        "employment_type": "employment_type.json",
        "socioeconomic_class": "socioeconomic.json",
        "industry_sector": "industry_sector.json",
        "birth_location": "birth_location.json",
        "birth_country_detail": "birth_country_detail.json",
        "household_size": "household_size.json",
    },
}

_MAPPINGS = {
    "_index": _INDEX,
    "age": {"values": ["18-24", "25-44", "45-64", "65+"]},
    "biological_sex": {
        "values": ["Male", "Female"],
        "real": {"Male": {"equals": ["men", "1"]}, "Female": {"equals": ["women", "2"]}},
        "synthetic": {
            "Male": {"contains": ["male", "pojke"], "equals": ["man", "m"]},
            "Female": {"contains": ["female", "kvinna"], "equals": ["f"]},        },
    },
    "education": {
        "values": ["Primary", "Secondary", "Tertiary"],
        "real": {
            "Primary": {"equals": ["grundskola"]},
            "Secondary": {"equals": ["gymnasium"]},
            "Tertiary": {"equals": ["universitet"]},        },
        "synthetic": {
            "Primary": {"contains": ["primary", "grundskola"]},
            "Secondary": {"contains": ["secondary", "gymnasium", "high school"]},
            "Tertiary": {"contains": ["tertiary", "university", "bachelor", "master"]},
        },
    },
    "employment_type": {
        "values": ["Permanent Full-time", "Permanent Part-time", "Not Applicable"],
        "real": {
            "Permanent Full-time": {
                "attachment": {"contains": ["permanent employees"]},
                "hours": {"contains": ["35+ hours"]},
            },
            "Permanent Part-time": {
                "attachment": {"contains": ["permanent employees"]},
                "hours": {"contains": ["1-19 hours", "20-34 hours"]},
            },
            "absent": "Not Applicable",        },
        "synthetic": {
            "Permanent Full-time": {"all_of": [["permanent", "fast"], ["full", "heltid"]]},
            "Permanent Part-time": {"all_of": [["permanent", "fast"], ["part", "deltid"]]},
            "Not Applicable": {"contains": ["student", "pensionär"]},
            "on_miss": "Not Applicable",        },
    },
    "socioeconomic": {
        "values": ["Poverty", "Working Class", "Middle Class", "Upper Class"],
        "real": {
            "Poverty": {"equals": ["Decile 1", "Decile 2"]},
            "Working Class": {"equals": ["Decile 3", "Decile 4", "Decile 5"]},
            "Middle Class": {"equals": ["Decile 6", "Decile 7", "Decile 8"]},
            "Upper Class": {"equals": ["Decile 9", "Decile 10"]},        },
        "synthetic": {
            "Poverty": {"contains": ["poverty", "poor"]},
            "Working Class": {"contains": ["working class"]},
            "Middle Class": {"contains": ["middle class"]},
            "Upper Class": {"contains": ["upper class", "wealthy"]},
        },
    },
    "industry_sector": {
        "values": ["Health", "Education", "Other"],
        "real": {
            "Health": {"equals": ["q"]},
            "Education": {"equals": ["p"]},
            "absent": "Not Applicable",        },
        "synthetic": {
            "Health": {"contains": ["health", "nurse", "hospital"]},
            "Education": {"contains": ["teacher", "school", "education"]},
            "on_miss": "Other",
        },
    },
    "birth_location": {
        "values": ["Sweden", "Nordic Country", "Europe (Other)", "Outside Europe"],
        "real": {
            "Sweden": {"equals": ["sweden", "sverige"]},
            "Nordic Country": {"equals": ["norway", "denmark"]},        },
        "synthetic": {
            "Sweden": {"contains": ["stockholm", "sweden", "sverige"]},
            "Nordic Country": {"contains": ["norway", "denmark", "finland"]},
            "Europe (Other)": {"contains": ["germany", "poland"]},
            "Outside Europe": {"contains": ["syria", "somalia"]},
            "refine_from": "birth_country_detail",        },
    },
    "birth_country_detail": {
        "values": ["Sweden", "Norway", "Germany", "Syria"],
        "real": {
            "Sweden": {"equals": ["sweden"]},
            "Norway": {"equals": ["norway"]},
            "Germany": {"equals": ["germany"]},
            "Syria": {"equals": ["syria"]},        },
        "synthetic": {
            "Sweden": {"contains": ["sweden", "stockholm"]},
            "Norway": {"contains": ["norway", "oslo"]},
            "Germany": {"contains": ["germany", "berlin"]},
            "Syria": {"contains": ["syria", "damascus"]},
        },
    },
    "household_size": {
        "values": ["1 person", "2 persons", "3 persons", "4+ persons"],
        "real": {
            "1 person": {"equals": ["1"]},
            "2 persons": {"equals": ["2"]},
            "3 persons": {"equals": ["3"]},
            "4+ persons": {"equals": ["4", "5", "6"]},        },
        "synthetic": {
            "1 person": {"int": [1]},
            "2 persons": {"int": [2]},
            "3 persons": {"int": [3]},
            "4+ persons": {"int_gte": 4},        },
    },
}


# ---------------------------------------------------------------------------
# Real mapper
# ---------------------------------------------------------------------------

def _real_record() -> dict:
    return {
        "id": "real-1",
        "age": 30,
        "biological_sex": {"label": "women"},
        "education_level": {"label": "universitet"},
        "employment_type": {
            "attachment": {"label": "Permanent employees"},
            "hours": {"label": "35+ hours"},
        },
        "socioeconomic_class": {"decile": "Decile 7"},
        # industry_sector omitted -> absent directive.
        "birth_location": {"label": "Norway"},
        "birth_country_detail": {"label": "Norway"},
        "household_size": {"label": "5"},
    }


def test_real_mapper_delegates_end_to_end():
    mapper = BaseRealMapper(_MAPPINGS)
    out = mapper.normalize_individual(_real_record())

    assert out["id"] == "real-1"
    assert out["age"] == 30  # raw passthrough, not an age_group label
    assert "age_group" not in out
    assert out["biological_sex"] == "Female"  # equals "women"
    assert out["education_level"] == "Tertiary"
    assert out["employment_type"] == "Permanent Full-time"  # composite attachment x hours
    assert out["socioeconomic_class"] == "Middle Class"  # decile-as-equals
    assert out["industry_sector"] == "Not Applicable"  # absent directive
    assert out["birth_location"] == "Nordic Country"
    assert out["household_size"] == "4+ persons"


def test_real_missing_field_resolves_to_unmapped():
    mapper = BaseRealMapper(_MAPPINGS)
    record = {"id": "real-2", "age": 40, "biological_sex": {"label": "unmatched-token"}}
    out = mapper.normalize_individual(record)
    assert out["biological_sex"] == UNMAPPED  # miss, no fuzzy, no on_miss


# ---------------------------------------------------------------------------
# Synthetic mapper
# ---------------------------------------------------------------------------

def _synth_mapper() -> BaseSyntheticMapper:
    return BaseSyntheticMapper(_MAPPINGS)


def test_synthetic_mapper_delegates_end_to_end():
    identity = {
        "age": 30,
        "biological_sex": "kvinna",
        "education_level": "Master of Science",
        "employment_type": "fast anställning, heltid",
        "socioeconomic_class": "middle class",
        "industry_sector": "software developer",  # miss -> on_miss "Other"
        "birth_location": "unknown-place",  # primary miss -> refine from detail
        "birth_country_detail": "Born in Oslo, Norway",
        "household_size": 3,
    }
    out = _synth_mapper().map_individual(identity, "persona_1")

    assert out["id"] == "persona_1"
    assert out["age"] == 30
    assert out["biological_sex"] == "Female"
    assert out["education_level"] == "Tertiary"
    assert out["employment_type"] == "Permanent Full-time"  # all_of co-occurrence
    assert out["socioeconomic_class"] == "Middle Class"
    assert out["industry_sector"] == "Other"  # on_miss default
    assert out["birth_country_detail"] == "Norway"
    assert out["birth_location"] == "Nordic Country"  # refined from detail
    assert out["household_size"] == "3 persons"  # numeric matcher


def test_synthetic_age_gate_skips_persona():
    mapper = _synth_mapper()
    assert mapper.map_individual({"age": "not-a-number", "biological_sex": "man"}, "p") is None
    assert mapper.map_individual({"age": None, "biological_sex": "man"}, "p") is None


def test_synthetic_narrative_format_skipped():
    mapper = _synth_mapper()
    assert mapper.map_individual({"narrative": "a life story"}, "p") is None


def test_synthetic_utf8_repair_applied():
    # Double-encoded "kvinna" variant repaired before matching.
    mapper = _synth_mapper()
    out = mapper.map_individual({"age": 22, "biological_sex": "kvinna"}, "p")
    assert out["biological_sex"] == "Female"

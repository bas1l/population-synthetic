"""Shared in-memory mapping config for the mapper base-class tests.

Both ``BaseRealMapper`` and ``BaseSyntheticMapper`` are now thin loaders over
the shared :mod:`population_synthetic.analysis.mapping.mapping_engine`, driven by the unified
symmetric per-attribute config (``values`` / ``real`` / ``synthetic``) plus an
``_index.json`` master. :func:`new_shape_mappings` returns a small, self-contained
config in exactly the shape :func:`load_mappings` produces (one entry per file stem,
keyed by stem, plus the ``_index`` master) so the concrete base classes can be driven
directly -- no country subclass or on-disk config needed.

The fixture is deliberately compact but exercises every branch the base classes and
the shared engine must preserve: ``id`` passthrough, the raw ``age`` passthrough /
persona-skip gate, ``equals`` / ``contains`` matchers, composite (``employment_type``)
resolution, decile-as-``equals`` (``socioeconomic``), numeric (``household_size``),
the ``absent`` / ``on_miss`` directives, and ``refine_from`` cross-field resolution
(``birth_location`` refined from ``birth_country_detail``).
"""

from __future__ import annotations

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


def new_shape_mappings() -> dict:
    """Return a fresh unified-symmetric mappings dict (keyed by file stem)."""
    return {
        "_index": {
            "attributes": dict(_INDEX["attributes"]),
        },
        "age": {"values": ["18-24", "25-44", "45-64", "65+"]},
        "biological_sex": {
            "values": ["Male", "Female"],
            "real": {"Male": {"equals": ["men", "1"]}, "Female": {"equals": ["women", "2"]}},
            "synthetic": {
                "Male": {"contains": ["male", "pojke"], "equals": ["man", "m"]},
                "Female": {"contains": ["female", "kvinna"], "equals": ["f"]},            },
        },
        "education": {
            "values": ["Primary", "Secondary", "Tertiary"],
            "real": {
                "Primary": {"equals": ["grundskola"]},
                "Secondary": {"equals": ["gymnasium"]},
                "Tertiary": {"equals": ["universitet"]},            },
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
                "absent": "Not Applicable",            },
            "synthetic": {
                "Permanent Full-time": {"all_of": [["permanent", "fast"], ["full", "heltid"]]},
                "Permanent Part-time": {"all_of": [["permanent", "fast"], ["part", "deltid"]]},
                "Not Applicable": {"none_of": ["job", "arbet"], "contains": ["student", "pensionär"]},
                "on_miss": "Not Applicable",            },
        },
        "socioeconomic": {
            "values": ["Poverty", "Working Class", "Middle Class", "Upper Class"],
            "real": {
                "Poverty": {"equals": ["Decile 1", "Decile 2"]},
                "Working Class": {"equals": ["Decile 3", "Decile 4", "Decile 5"]},
                "Middle Class": {"equals": ["Decile 6", "Decile 7", "Decile 8"]},
                "Upper Class": {"equals": ["Decile 9", "Decile 10"]},            },
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
                "absent": "Not Applicable",            },
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
                "Nordic Country": {"equals": ["norway", "denmark"]},            },
            "synthetic": {
                "Sweden": {"contains": ["stockholm", "sweden", "sverige"]},
                "Nordic Country": {"contains": ["norway", "denmark", "finland"]},
                "Europe (Other)": {"contains": ["germany", "poland"]},
                "Outside Europe": {"contains": ["syria", "somalia"]},
                "refine_from": "birth_country_detail",            },
        },
        "birth_country_detail": {
            "values": ["Sweden", "Norway", "Germany", "Syria"],
            "real": {
                "Sweden": {"equals": ["sweden"]},
                "Norway": {"equals": ["norway"]},
                "Germany": {"equals": ["germany"]},
                "Syria": {"equals": ["syria"]},            },
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
                "4+ persons": {"equals": ["4", "5", "6"]},            },
            "synthetic": {
                "1 person": {"int": [1]},
                "2 persons": {"int": [2]},
                "3 persons": {"int": [3]},
                "4+ persons": {"int_gte": 4},            },
        },
    }

"""Unit tests for ``BaseSyntheticMapper`` as a thin loader over the shared engine.

The synthetic mapper no longer holds a handler-kind engine: it reads the per-country
``_index.json`` master plus each per-attribute file's ``synthetic`` block and ``values``
list, and delegates every attribute to :func:`mapping_engine.resolve`. These tests drive
the concrete base class directly with the shared in-memory config from
:mod:`tests._mapping_fixtures` (mirroring ``test_real_mapper_base.py``), and add a
couple of real-config integration checks through ``get_synthetic_mapper``.

They exercise the three responsibilities the base class still owns -- the format gate
(narrative blobs skipped), record-level UTF-8 repair, and the persona-skip ``age`` gate
-- plus the synthetic-side algorithms now expressed as matchers/directives: ``equals`` /
``contains``, ``all_of`` co-occurrence with a ``none_of`` veto (``employment_type``),
numeric (``household_size``), the ``on_miss`` default, and ``refine_from`` cross-field
resolution (``birth_location`` refined from ``birth_country_detail``).
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.mapping.synthetic_mapper import get_synthetic_mapper
from population_synthetic.analysis.mapping.synthetic_mapper.base import BaseSyntheticMapper

from ._mapping_fixtures import new_shape_mappings, with_matching


def _synth_mapper() -> BaseSyntheticMapper:
    return BaseSyntheticMapper(new_shape_mappings())


# --- fail-fast construction ------------------------------------------------

def test_missing_index_raises():
    with pytest.raises(ValueError, match="_index"):
        BaseSyntheticMapper({"biological_sex": {"values": ["Male", "Female"]}})


def test_index_without_attributes_raises():
    with pytest.raises(ValueError, match="_index"):
        BaseSyntheticMapper({"_index": {"description": "no attributes"}})


# --- format gate + persona-skip age gate -----------------------------------

def test_narrative_format_skipped():
    assert _synth_mapper().map_individual({"narrative": "a life story"}, "p") is None


def test_age_gate_skips_non_integer_and_missing_age():
    mapper = _synth_mapper()
    assert mapper.map_individual({"age": "not-a-number", "biological_sex": "man"}, "p") is None
    assert mapper.map_individual({"age": None, "biological_sex": "man"}, "p") is None


def test_utf8_repair_applied_before_matching():
    # Double-encoded "kvinna" variant repaired record-level before matching.
    out = _synth_mapper().map_individual({"age": 22, "biological_sex": "kvinna"}, "p")
    assert out is not None
    assert out["biological_sex"] == "Female"


# --- end-to-end resolution -------------------------------------------------

def test_synthetic_mapper_delegates_end_to_end():
    identity = {
        "age": 30,
        "biological_sex": "kvinna",
        "education_level": "Master of Science",
        "employment_type": "fast anställning, heltid",   # all_of co-occurrence
        "socioeconomic_class": "middle class",
        "industry_sector": "software developer",          # miss -> on_miss "Other"
        "birth_location": "unknown-place",                # primary miss -> refine from detail
        "birth_country_detail": "Born in Oslo, Norway",
        "household_size": 3,                              # numeric matcher
    }
    out = _synth_mapper().map_individual(identity, "persona_1")

    assert out["id"] == "persona_1"           # injected persona id
    assert out["age"] == 30                    # raw age passthrough
    assert out["biological_sex"] == "Female"
    assert out["education_level"] == "Tertiary"
    assert out["employment_type"] == "Permanent Full-time"
    assert out["socioeconomic_class"] == "Middle Class"
    assert out["industry_sector"] == "Other"          # on_miss default
    assert out["birth_country_detail"] == "Norway"
    assert out["birth_location"] == "Nordic Country"  # refined from detail
    assert out["household_size"] == "3 persons"


def test_none_of_veto_blocks_employment_type():
    # "student job" carries the Not-Applicable ``contains`` token "student" but is
    # vetoed by the ``none_of`` token "job", so it does not resolve to Not Applicable.
    out = _synth_mapper().map_individual(
        {"age": 20, "employment_type": "student job at cafe"}, "p")
    # Vetoed positive + no other value hits -> on_miss default ("Not Applicable").
    # The veto proves the positive contains-tier did not fire on its own.
    assert out["employment_type"] == "Not Applicable"


# --- miss log ---------------------------------------------------------------

def test_misses_record_raw_value_and_flag_on_miss_masking():
    mapper = _synth_mapper()
    mapper.map_individual(
        {"age": 30, "biological_sex": "kvinna", "industry_sector": "software developer"}, "persona_1")

    by_attr = {m["attribute"]: m for m in mapper.misses}
    # ``industry_sector`` misses but its ``on_miss`` literal hides that in the mapped
    # record -- the log is the only place the offending raw string survives.
    assert by_attr["industry_sector"]["raw_value"] == "software developer"
    assert by_attr["industry_sector"]["mapped_to"] == "Other"
    assert by_attr["industry_sector"]["masked_by_on_miss"] is True
    # A plain sentinel miss (absent raw, no ``on_miss``) is logged as unmasked.
    assert by_attr["socioeconomic_class"]["masked_by_on_miss"] is False
    # A resolved attribute is never logged.
    assert "biological_sex" not in by_attr
    assert all(m["persona_id"] == "persona_1" for m in mapper.misses)


def test_misses_accumulate_across_personas_and_skip_refine_duplicates():
    mapper = _synth_mapper()
    assert mapper.misses == []
    for i in range(3):
        mapper.map_individual({"age": 30, "biological_sex": "kvinna"}, f"persona_{i}")
    assert len({m["persona_id"] for m in mapper.misses}) == 3
    # ``birth_location`` declares ``refine_from: birth_country_detail``, which pulls the
    # sibling in early. Memoisation must keep that from logging the sibling twice.
    per_persona = [m for m in mapper.misses if m["persona_id"] == "persona_0"]
    attrs = [m["attribute"] for m in per_persona]
    assert len(attrs) == len(set(attrs))


# --- tie log (the {slug}.ties.csv sidecar) -----------------------------------

def test_ties_record_candidates_winner_and_criterion():
    mappings = with_matching(
        new_shape_mappings(),
        synthetic={"token_mode": "substring", "negation": None, "tie_break": ["longest", "priority"]},
    )
    mapper = BaseSyntheticMapper(mappings)
    # Both Secondary ("secondary") and Tertiary ("tertiary") hit in the contains tier;
    # "secondary" is longer, so ``longest`` decides against the declared order.
    out = mapper.map_individual({"age": 30, "education_level": "post-secondary or tertiary"}, "persona_7")
    assert out["education_level"] == "Secondary"
    ties = [t for t in mapper.ties if t["attribute"] == "education_level"]
    assert len(ties) == 1
    tie = ties[0]
    assert tie["persona_id"] == "persona_7"
    assert tie["raw_value"] == "post-secondary or tertiary"
    assert tie["tier"] == "contains"
    assert tie["winner"] == "Secondary"
    assert tie["criterion"] == "longest"
    assert "Secondary:9:secondary" in tie["candidates"]
    assert "Tertiary:8:tertiary" in tie["candidates"]


def test_single_hit_is_not_a_tie():
    mapper = _synth_mapper()
    mapper.map_individual({"age": 30, "education_level": "university"}, "p")
    assert mapper.ties == []


def test_ambiguous_numeric_facet_is_logged_as_tie_row():
    mappings = new_shape_mappings()
    et = mappings["employment_type"]
    et["synthetic"]["numeric_facet"] = {
        "extract": [{"pattern": r"(\d+)(?:\s*-\s*(\d+))?\s*(?:h\b|timmar\b)", "scale": 1.0}],
        "ambiguous_if_preceded_by": ["över"],
        "bands": [{"name": "part", "gte": 1, "lt": 35}, {"name": "full", "gte": 35}],
        "remap": {
            "Permanent Full-time": {"part": "Permanent Part-time", "full": "Permanent Full-time"},
            "Permanent Part-time": {"part": "Permanent Part-time", "full": "Permanent Full-time"},
        },
    }
    mapper = BaseSyntheticMapper(mappings)
    out = mapper.map_individual({"age": 30, "employment_type": "fast heltid, 20 h"}, "p1")
    assert out["employment_type"] == "Permanent Part-time"           # re-banded from stated hours
    assert mapper.ties == []
    out = mapper.map_individual({"age": 30, "employment_type": "fast heltid, 30-40 timmar"}, "p2")
    assert out["employment_type"] == "__UNMAPPED__"                  # straddle: band undetermined
    (row,) = mapper.ties
    assert (row["persona_id"], row["criterion"], row["tier"]) == ("p2", "facet_ambiguous", "numeric_facet")
    assert row["candidates"] == "full | part"
    assert row["winner"] == "__UNMAPPED__"
    assert not [m for m in mapper.misses if m["attribute"] == "employment_type"]  # walk hit: no miss


def test_invalid_config_raises_at_construction():
    mappings = new_shape_mappings()
    mappings["education"]["synthetic"]["Primary"] = {"contain": ["primary"]}
    with pytest.raises(ValueError, match="unknown matcher key 'contain'"):
        BaseSyntheticMapper(mappings)


# --- real-config integration: the Sweden Nordic-fold reconciliation ---------

def test_swedish_norway_born_is_outside_the_eu():
    # FolkmFodlandHVD splits Sweden / other EU / outside the EU, so a Norway-born
    # persona is "Born outside the EU" and a Germany-born one "Born in another EU country".
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(_swedish_identity(birth_country_detail="Norway"), "p")
    assert out["birth_location"] == "Born outside the EU"
    out = mapper.map_individual(_swedish_identity(birth_country_detail="Germany"), "p")
    assert out["birth_location"] == "Born in another EU country"


def test_swedish_domestic_maps_to_sweden():
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(_swedish_identity(birth_location="Stockholm"), "p")
    assert out["birth_location"] == "Sweden"


def test_italian_nordic_born_folds_into_europe_other():
    # Italy has no "Nordic Country" bucket either: a Norway free-text birthplace
    # collapses to "Europe (Other)".
    mapper = get_synthetic_mapper("italian")
    out = mapper.map_individual(_swedish_identity(birth_location="Norway"), "p")
    assert out["birth_location"] == "Europe (Other)"


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("Full-time student", "Student"),   # was a null-source miss -> None
        ("Student", "Student"),
        ("studerande", "Student"),
        ("Retired", "Retired"),
        ("Pensionär", "Retired"),
        ("Employed", "Employed"),           # regression: unchanged
        ("Anställd heltid", "Employed"),     # regression: unchanged
        ("Arbetslös", "Unemployed"),         # regression: unchanged
    ],
)
def test_swedish_employment_status_student_and_retired_matchers(raw_status, expected):
    # employment.json gained Student/Retired synthetic blocks (previously latent None);
    # "Full-time student" must route to Student, not Employed (Employed's "full time"
    # space-token cannot substring-match the hyphenated "full-time").
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(_swedish_identity(employment_status=raw_status), "p")
    assert out["employment_status"] == expected


def test_swedish_natural_parents_mother_and_father_phrasing():
    # parental_structure.json Natural Parents gained "mother and father" so the common
    # LLM phrasing "Mother and father (married)" no longer resolves to None.
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(
        _swedish_identity(parental_structure="Mother and father (married)"), "p")
    assert out["parental_structure"] == "Natural Parents"


def _swedish_identity(**overrides) -> dict:
    """A minimal valid flat identity (passes the age gate) with overridable fields."""
    base = {
        "age": 40, "biological_sex": "Female", "education_level": "x",
        "employment_status": "x", "current_environment_type": "Urban",
        "socioeconomic_class": "Middle class", "parental_structure": "x",
        "region": "x", "civil_status": "Married", "household_size": 2,
        "housing_tenure": "x", "industry_sector": "x", "employment_type": "x",
        "income_source": "x", "birth_location": "", "birth_country_detail": "",
    }
    base.update(overrides)
    return base


# --- real-config integration: scb_native matching rules (SCB-checked audit) ---

@pytest.mark.parametrize("attr, raw, expected", [
    # prefix boundary: no left-embedded hit
    ("education_level", "Eftergymnasial utbildning, 3 år eller längre", "Post-Secondary 3+ yrs (ISCED 5A)"),
    ("education_level", "Eftergymnasial utbildning, kortare än 3 år", "Post-Secondary < 3 yrs (ISCED 4+5B)"),
    ("education_level", "Masterexamen (2-årig på högskola)", "Post-Secondary 3+ yrs (ISCED 5A)"),
    ("biological_sex", "Female (kvinna)", "Female"),
    # substring overrides for compound heads
    ("income_source", "Månadslön", "Wage / Business"),
    ("employment_status", "Heltidsanställd", "Employed"),
    # longest beats axis order; it-konsult
    ("industry_sector", "IT-konsulting", "Information & Communication"),
    # negation: a cue before the token discards it (Married); a cue-initial token still hits
    ("civil_status", "Inte gift", "Single/Never Married"),
    ("civil_status", "Never married", "Single/Never Married"),
    # hours facet: stated hours re-band the attachment (AKU 1-19 / 20-34 / 35+)
    ("employment_type", "Tillsvidareanställning, 15 timmar/vecka", "Permanent Short Part-time"),
    ("employment_type", "Tillsvidareanställning, 30 timmar/vecka", "Permanent Part-time"),
    ("employment_type", "Tillsvidareanställning, 40 timmar/vecka", "Permanent Full-time"),
])
def test_swedish_scb_native_matching_rules(attr, raw, expected):
    mapper = get_synthetic_mapper("swedish")
    out = mapper.map_individual(_swedish_identity(**{attr: raw}), "p")
    assert out[attr] == expected

"""Unit tests for the shared symmetric resolver ``comparison.mapping_engine``.

These drive :func:`resolve` directly with small in-test rules blocks (the same
shape the migrated ``config/mapping/{scb,istat}/*.json`` files will carry) so each
matcher tier, directive, and precedence rule can be exercised in isolation --
before any production config is rewritten.
"""

import pytest

from population_synthetic.analysis.mapping import mapping_engine
from population_synthetic.analysis.mapping.mapping_engine import (
    MappingConfigError,
    compile_matching,
    normalize,
    resolve_traced,
    validate_mappings,
    validate_priority,
    validate_rules,
)
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED, is_unmapped

from ._mapping_fixtures import SUBSTRING_MATCHING, with_matching


# The tests in this module pin the historic behaviour: they declare the
# behaviour-preserving matching options explicitly (substring tokens, no negation,
# ties broken by a ``priority`` list equal to the declared ``values`` order).
def resolve(raw, block, values, **kwargs):
    return mapping_engine.resolve(raw, block, values, matching=SUBSTRING_MATCHING, priority=list(values), **kwargs)


def resolve_detailed(raw, block, values, **kwargs):
    return mapping_engine.resolve_detailed(
        raw, block, values, matching=SUBSTRING_MATCHING, priority=list(values), **kwargs
    )


# --- equals / contains precedence and first-match-by-order -----------------

def test_equals_exact_match():
    values = ["Male", "Female"]
    block = {"Male": {"equals": ["men", "1"]}, "Female": {"equals": ["women", "2"]}}
    assert resolve("men", block, values) == "Male"
    assert resolve("2", block, values) == "Female"


def test_equals_is_not_substring():
    # ``equals`` must be exact: "women" must not match the "men" token.
    block = {"Male": {"equals": ["men"]}}
    assert resolve("women", block, ["Male"]) == UNMAPPED


def test_contains_substring_match():
    values = ["Male", "Female"]
    block = {
        "Male": {"contains": ["pojke", "manlig"]},
        "Female": {"contains": ["kvinn", "flicka"]},
    }
    assert resolve("en liten pojke", block, values) == "Male"
    assert resolve("kvinnlig", block, values) == "Female"


def test_first_matching_value_wins_by_declared_order():
    # Both values would match "ab"; declaration order (values) decides.
    block = {"First": {"contains": ["a"]}, "Second": {"contains": ["b"]}}
    assert resolve("ab", block, ["First", "Second"]) == "First"
    assert resolve("ab", block, ["Second", "First"]) == "Second"


def test_unmatched_returns_unmapped():
    block = {"Male": {"equals": ["men"]}}
    assert resolve("zzz", block, ["Male"]) == UNMAPPED


def test_case_and_underscore_and_hyphen_normalization():
    block = {"TwoParents": {"equals": ["two biological parents"]}}
    # snake_case / mixed case resolves to the space-form token.
    assert resolve("Two_Biological_Parents", block, ["TwoParents"]) == "TwoParents"
    # Hyphen is preserved (not collapsed), so upper-secondary != upper secondary.
    block2 = {"C": {"equals": ["upper-secondary"]}, "A": {"equals": ["upper secondary"]}}
    assert resolve("Upper Secondary", block2, ["C", "A"]) == "A"


def test_double_encoded_utf8_repaired():
    block = {"Female": {"equals": ["män"]}}  # Swedish men/male token, but as an example label
    assert resolve("M√§n", block, ["Female"]) == "Female"


def test_typographic_punctuation_folds_to_ascii():
    # LLM output uses U+2011 / en dash / typographic apostrophe interchangeably with
    # their ASCII forms; a config token written with a plain hyphen must still match.
    block = {"ICT": {"equals": ["it-tjänster"]}}
    assert resolve("IT‑tjänster", block, ["ICT"]) == "ICT"   # non-breaking hyphen
    assert resolve("IT–tjänster", block, ["ICT"]) == "ICT"   # en dash
    assert resolve("IT-tjänster", block, ["ICT"]) == "ICT"        # ASCII, unchanged
    # The fold is symmetric: a fancy-punctuation *token* matches an ASCII raw.
    block2 = {"MSc": {"equals": ["master’s degree"]}}
    assert resolve("Master's degree", block2, ["MSc"]) == "MSc"


def test_punctuation_fold_runs_after_utf8_repair():
    # The cp1252 mojibake keys ("Ã–", "Ã…") embed U+2013 / U+2026. Folding punctuation
    # first would rewrite them out of existence and break the repair, so order matters.
    block = {"Oe": {"equals": ["över"]}}
    assert resolve("Ã–ver", block, ["Oe"]) == "Oe"


# --- all_of / none_of ------------------------------------------------------

def test_all_of_requires_one_token_from_every_group():
    block = {
        "PermanentFull": {"all_of": [["permanent", "tillsvidare"], ["full", "heltid"]]},
    }
    assert resolve("permanent heltid contract", block, ["PermanentFull"]) == "PermanentFull"
    # Missing the hours group -> no match.
    assert resolve("permanent contract", block, ["PermanentFull"]) == UNMAPPED


def test_none_of_veto_blocks_otherwise_matching_value():
    # "Employed" would match on "work" but the student veto blocks it.
    block = {
        "NotApplicable": {"contains": ["student"]},
        "Employed": {"contains": ["work"], "none_of": ["student"]},
    }
    assert resolve("part-time work", block, ["NotApplicable", "Employed"]) == "Employed"
    # A student who also mentions work is vetoed out of Employed -> NotApplicable.
    assert resolve("student with work placement", block, ["NotApplicable", "Employed"]) == "NotApplicable"


# --- numeric (int / int_gte) ----------------------------------------------

def test_int_and_int_gte_bucketing_with_overflow():
    values = ["1 person", "2 persons", "3 persons", "6 persons or more"]
    block = {
        "1 person": {"int": [1]},
        "2 persons": {"int": [2]},
        "3 persons": {"int": [3]},
        "6 persons or more": {"int_gte": 6},
    }
    assert resolve(1, block, values) == "1 person"
    assert resolve(3, block, values) == "3 persons"
    assert resolve(6, block, values) == "6 persons or more"
    assert resolve(9, block, values) == "6 persons or more"  # overflow
    # A size with no bucket and no overflow rule -> UNMAPPED.
    assert resolve(4, block, values) == UNMAPPED


def test_int_accepts_integer_valued_string():
    block = {"3 persons": {"int": [3]}}
    assert resolve("3", block, ["3 persons"]) == "3 persons"


# --- composite two-field matcher ------------------------------------------

def test_composite_attachment_hours_all_subfields_must_hit():
    values = ["Permanent Full-time", "Permanent Part-time"]
    block = {
        "Permanent Full-time": {
            "attachment": {"contains": ["permanent employees"]},
            "hours": {"contains": ["35+ hours"]},
        },
        "Permanent Part-time": {
            "attachment": {"contains": ["permanent employees"]},
            "hours": {"contains": ["under 35 hours"]},
        },
    }
    rec_full = {"attachment": "permanent employees", "hours": "35+ hours worked"}
    rec_part = {"attachment": "permanent employees", "hours": "under 35 hours worked"}
    assert resolve(rec_full, block, values) == "Permanent Full-time"
    assert resolve(rec_part, block, values) == "Permanent Part-time"
    # One sub-field mismatched -> no composite hit.
    rec_bad = {"attachment": "temporary staff", "hours": "35+ hours"}
    assert resolve(rec_bad, block, values) == UNMAPPED
    # A non-dict raw can never satisfy a composite matcher.
    assert resolve("permanent full time", block, values) == UNMAPPED


# --- refine_from cross-field ----------------------------------------------

def test_refine_from_resolves_from_sibling_when_primary_misses():
    values = ["Sweden", "Europe (Other)", "Outside Europe"]
    block = {
        "refine_from": "birth_country_detail",
        "Sweden": {"contains": ["sweden", "sverige"]},
        "Europe (Other)": {"contains": ["germany", "poland", "norway"]},
        "Outside Europe": {"contains": ["syria", "somalia"]},
    }
    # Primary free-text empty; refine from the resolved detail "Germany".
    assert resolve("", block, values, refine_value="Germany") == "Europe (Other)"
    # Primary hits directly -> refine not needed.
    assert resolve("born in Sweden", block, values, refine_value="Germany") == "Sweden"
    # No refine value and primary misses -> UNMAPPED.
    assert resolve("", block, values) == UNMAPPED


# --- absent / on_miss ------------------------------------------------------

def test_absent_literal_for_missing_raw():
    block = {"absent": "Not Applicable", "Manufacturing": {"contains": ["factory"]}}
    values = ["Manufacturing"]
    assert resolve(None, block, values) == "Not Applicable"
    assert resolve("   ", block, values) == "Not Applicable"
    assert resolve("factory worker", block, values) == "Manufacturing"


def test_on_miss_default_unmapped_vs_literal():
    values = ["Wage / Business", "Pension"]
    matchers = {
        "Wage / Business": {"contains": ["salary"]},
        "Pension": {"contains": ["pension"]},
    }
    # No declared on_miss -> the UNMAPPED sentinel (not a bare None).
    assert resolve("lottery winnings", matchers, values) == UNMAPPED
    # A declared literal on_miss is unaffected.
    block_default = {"on_miss": "Wage / Business", **matchers}
    assert resolve("lottery winnings", block_default, values) == "Wage / Business"


def test_resolve_detailed_reports_miss_even_when_on_miss_masks_it():
    values = ["Wage / Business", "Pension"]
    matchers = {
        "Wage / Business": {"contains": ["salary"]},
        "Pension": {"contains": ["pension"]},
    }
    # A hit is never a miss.
    assert resolve_detailed("monthly salary", matchers, values) == ("Wage / Business", False)
    # A total miss without on_miss: sentinel + missed.
    assert resolve_detailed("lottery winnings", matchers, values) == (UNMAPPED, True)
    # A total miss *with* on_miss returns a real category -- indistinguishable from a
    # genuine hit by value alone, which is exactly why the flag exists.
    block_default = {"on_miss": "Wage / Business", **matchers}
    assert resolve_detailed("lottery winnings", block_default, values) == ("Wage / Business", True)


def test_resolve_detailed_absent_literal_is_not_a_miss():
    values = ["Employed"]
    block = {"absent": "Not Applicable", "Employed": {"contains": ["employ"]}}
    assert resolve_detailed(None, block, values) == ("Not Applicable", False)


def test_unmatched_raw_returns_unmapped_without_fuzzy_fallback():
    # There is no fuzzy tier: a raw that substring-matches a value *label* but hits
    # no declared matcher must miss.
    values = ["Middle Class", "Working Class"]
    block = {"Middle Class": {"equals": ["mc"]}, "Working Class": {"equals": ["wc"]}}
    assert resolve("solidly middle class household", block, values) == UNMAPPED


# --- global tiered precedence (equals -> all_of -> contains -> numeric) -----

def test_equals_beats_contains_across_values_globally():
    # Regression for the biological_sex bug: raw "female" must NOT resolve to Male via
    # Male's contains ["male"] (substring of "female"); Female's exact equals wins first.
    values = ["Male", "Female"]
    block = {
        "Male": {"equals": ["male", "man"], "contains": ["male", "pojke"]},
        "Female": {"equals": ["female"], "contains": ["female", "kvinna"]},
    }
    assert resolve("female", block, values) == "Female"
    # And an unambiguous raw still resolves to Male.
    assert resolve("male", block, values) == "Male"


def test_equals_on_later_value_beats_contains_on_earlier_value():
    # Earlier value would match by contains, later value by equals -> equals wins.
    values = ["First", "Second"]
    block = {"First": {"contains": ["abc"]}, "Second": {"equals": ["abcd"]}}
    assert resolve("abcd", block, values) == "Second"


def test_all_of_beats_contains_across_values_globally():
    values = ["Broad", "Specific"]
    block = {
        "Broad": {"contains": ["permanent"]},
        "Specific": {"all_of": [["permanent"], ["full"]]},
    }
    # Both could match, but all_of is a higher tier -> Specific wins.
    assert resolve("permanent full-time", block, values) == "Specific"
    # Only the contains token present -> falls to Broad.
    assert resolve("permanent contract", block, values) == "Broad"


# --- all_of_rules: self-contained conjunctive exceptions --------------------

_RULE_VALUES = ["Job", "NotApplicable"]
_RULE_BLOCK = {
    "Job": {
        "contains": ["employed"],
        "none_of": ["pension"],
        "all_of_rules": [{"all_of": [["pension"], ["hours", "employed"]], "none_of": ["former"]}],
    },
    "NotApplicable": {"contains": ["pension"]},
}


def test_all_of_rule_reaches_a_value_past_its_own_veto():
    # The value-level veto blocks "pension" texts, but the rule states the exception.
    assert resolve("pensioner, 15 hours a week", _RULE_BLOCK, _RULE_VALUES) == "Job"
    assert resolve("pensioner, employed", _RULE_BLOCK, _RULE_VALUES) == "Job"
    # No work cue: the rule misses and the veto still holds.
    assert resolve("pensioner", _RULE_BLOCK, _RULE_VALUES) == "NotApplicable"
    # The value's own contains is untouched.
    assert resolve("employed", _RULE_BLOCK, _RULE_VALUES) == "Job"


def test_all_of_rule_honours_only_its_own_none_of():
    assert resolve("pensioner, former employed", _RULE_BLOCK, _RULE_VALUES) == "NotApplicable"
    # The rule's veto does not reach the value's own contains tier.
    assert resolve("former employed", _RULE_BLOCK, _RULE_VALUES) == "Job"


def test_all_of_rule_competes_in_the_all_of_tier():
    res = mapping_engine.resolve_traced(
        "pensioner, 15 hours", _RULE_BLOCK, _RULE_VALUES, matching=SUBSTRING_MATCHING, priority=_RULE_VALUES
    )
    assert (res.tier, res.value, res.token) == ("all_of", "Job", "rule:pension+hours")
    # An equals hit on another value still wins (earlier tier).
    block = {**_RULE_BLOCK, "NotApplicable": {"equals": ["pension 15 hours"], "contains": ["pension"]}}
    assert resolve("pension 15 hours", block, _RULE_VALUES) == "NotApplicable"


def test_all_of_rules_validation():
    validate_rules(_RULE_BLOCK, _RULE_VALUES, "t")
    with pytest.raises(MappingConfigError, match="must declare 'all_of'"):
        validate_rules({"Job": {"all_of_rules": [{"none_of": ["x"]}]}}, ["Job"], "t")
    with pytest.raises(MappingConfigError, match="must declare 'all_of'"):
        validate_rules({"Job": {"all_of_rules": [{"all_of": [["a"]], "contains": ["x"]}]}}, ["Job"], "t")
    with pytest.raises(MappingConfigError, match="non-empty list"):
        validate_rules({"Job": {"all_of_rules": []}}, ["Job"], "t")
    with pytest.raises(MappingConfigError, match="non-empty list"):
        validate_rules({"Job": {"all_of_rules": [{"all_of": [[]]}]}}, ["Job"], "t")


# --- normalization primitive ----------------------------------------------

def test_normalize_lowercases_and_collapses_underscores_but_keeps_hyphens():
    assert normalize("Upper_Secondary") == "upper secondary"
    assert normalize("upper-secondary") == "upper-secondary"
    assert normalize(None) == ""
    assert normalize(42) == "42"


# --- UNMAPPED sentinel predicate ------------------------------------------

def test_is_unmapped_recognizes_sentinel_and_legacy_none():
    # The explicit sentinel and legacy None (pre-sentinel data/caches) are both
    # "no canonical equivalent".
    assert is_unmapped(UNMAPPED) is True
    assert is_unmapped(None) is True
    # A real mapped value (or any other string/number) is not unmapped.
    assert is_unmapped("Male") is False
    assert is_unmapped("") is False
    assert is_unmapped(0) is False
    assert is_unmapped("Not Applicable") is False


# ===========================================================================
# Matching options: token boundaries, negation, tie-break, numeric facet and
# config validation (the ``_index.json`` ``matching`` block)
# ===========================================================================

_NEG = {
    "cues": ["not", "no", "inte", "ej", "ingen", "never", "non"],
    "window": 2,
    "clause_breaks": [",", ";", ":", "(", ")", "/", ".", " - ", "but", "men", "och", "and"],
}


def _m(token_mode="prefix", negation=None, tie_break=("longest", "priority")):
    return {"token_mode": token_mode, "negation": negation, "tie_break": list(tie_break)}


def _r(raw, block, values, matching, priority=None, **kwargs):
    return mapping_engine.resolve(raw, block, values, matching=matching, priority=priority or list(values), **kwargs)


# --- token boundaries ------------------------------------------------------

def test_prefix_rejects_left_embedded_token():
    values = ["3A", "Male", "Rental", "Short"]
    block = {
        "3A": {"contains": ["gymnasial"]},
        "Male": {"contains": ["male"]},
        "Rental": {"contains": ["rent"]},
        "Short": {"contains": ["0 timmar"]},
    }
    prefix, substring = _m("prefix"), _m("substring")
    for raw in ("Eftergymnasial utbildning", "female", "living with parents", "40 timmar i veckan"):
        assert _r(raw, block, values, prefix) == UNMAPPED, raw
        assert _r(raw, block, values, substring) != UNMAPPED, raw
    # The unembedded forms still hit under prefix.
    assert _r("Gymnasial utbildning", block, values, prefix) == "3A"
    assert _r("0 timmar", block, values, prefix) == "Short"
    assert _r("(0 timmar)", block, values, prefix) == "Short"


def test_number_boundary_digit_counts_as_alphanumeric():
    block = {"Zero": {"contains": ["0 timmar"]}, "Forty": {"contains": ["40 timmar"]}}
    values = ["Zero", "Forty"]
    assert _r("arbetar 40 timmar", block, values, _m("prefix")) == "Forty"
    assert _r("arbetar 0 timmar", block, values, _m("prefix")) == "Zero"


def test_prefix_accepts_compound_modifier():
    block = {"5A": {"contains": ["högskole"]}}
    assert _r("Högskoleexamen", block, ["5A"], _m("prefix")) == "5A"


def test_substring_override_matches_compound_head():
    values = ["Wage"]
    plain = {"Wage": {"contains": ["lön"]}}
    override = {"Wage": {"contains": [{"token": "lön", "mode": "substring"}]}}
    assert _r("Månadslön", plain, values, _m("prefix")) == UNMAPPED
    assert _r("Månadslön", override, values, _m("prefix")) == "Wage"


def test_word_mode_requires_both_boundaries():
    block = {"Gift": {"contains": ["gift"]}}
    assert _r("gift", block, ["Gift"], _m("word")) == "Gift"
    assert _r("gifta sig", block, ["Gift"], _m("word")) == UNMAPPED
    assert _r("gifta sig", block, ["Gift"], _m("prefix")) == "Gift"
    # A per-token word override inside a prefix side.
    block_w = {"Gift": {"contains": [{"token": "gift", "mode": "word"}]}}
    assert _r("gifta sig", block_w, ["Gift"], _m("prefix")) == UNMAPPED


def test_token_mode_applies_to_all_of_and_none_of():
    values = ["PermFull", "Other"]
    block = {
        "PermFull": {"all_of": [["fast"], ["heltid"]], "none_of": ["deltid"]},
        "Other": {"contains": ["anställ"]},
    }
    # all_of member "fast" embedded in "Bofast" does not count under prefix.
    assert _r("Bofast anställd heltid", block, values, _m("prefix")) == "Other"
    assert _r("Bofast anställd heltid", block, values, _m("substring")) == "PermFull"
    # none_of "deltid" embedded in "xdeltid" does not veto under prefix.
    assert _r("fast heltid, anställd xdeltid", block, values, _m("prefix")) == "PermFull"
    assert _r("fast heltid, anställd xdeltid", block, values, _m("substring")) == "Other"


# --- negation ---------------------------------------------------------------

def test_negation_cue_suppresses_following_token():
    values = ["Married", "Employed"]
    block = {"Married": {"contains": ["gift"]}, "Employed": {"contains": ["employed"]}}
    neg = _m("prefix", _NEG)
    assert _r("inte gift", block, values, neg) == UNMAPPED
    assert _r("not employed", block, values, neg) == UNMAPPED
    assert _r("gift", block, values, neg) == "Married"
    # Without negation the historic engine hits.
    assert _r("inte gift", block, values, _m("prefix")) == "Married"


def test_negation_window_counts_words():
    block = {"Employed": {"contains": ["employed"]}}
    neg = _m("prefix", _NEG)
    assert _r("not currently employed", block, ["Employed"], neg) == UNMAPPED   # cue 2 words back
    assert _r("not at all currently employed", block, ["Employed"], neg) == "Employed"  # outside window


def test_negation_stops_at_clause_break():
    values = ["NA", "Retired"]
    block = {"NA": {"contains": ["anställning"]}, "Retired": {"contains": ["pensionär"]}}
    neg = _m("prefix", _NEG)
    # "Ingen" negates "anställning" but the clause break ends its scope, so "pensionär" stands.
    assert _r("Ingen anställning - pensionär", block, values, neg) == "Retired"
    assert _r("Ingen anställning, pensionär", block, values, neg) == "Retired"
    # Past tense is not negation.
    assert _r("tidigare anställning", block, values, neg) == "NA"


def test_token_starting_with_cue_not_negated():
    values = ["Single", "Married"]
    block = {"Single": {"contains": ["never married"]}, "Married": {"contains": ["married"]}}
    neg = _m("prefix", _NEG, tie_break=["priority"])
    # "married" inside "never married" is negated; the Single token itself is not.
    assert _r("never married", block, values, neg, priority=["Married", "Single"]) == "Single"
    assert _r("never married", block, values, _m("prefix", tie_break=["priority"]),
              priority=["Married", "Single"]) == "Married"
    assert _r("married", block, values, neg) == "Married"


def test_negated_veto_does_not_veto():
    block = {"Employed": {"contains": ["arbetar"], "none_of": ["student"]}}
    neg = _m("prefix", _NEG)
    assert _r("arbetar, student", block, ["Employed"], neg) == UNMAPPED
    assert _r("arbetar, inte student", block, ["Employed"], neg) == "Employed"


def test_attribute_negation_opt_out():
    block = {"Outside EU": {"contains": ["eu"]}}
    neg = _m("prefix", _NEG)
    assert _r("non eu", block, ["Outside EU"], neg) == UNMAPPED
    opted = {"negation": None, **block}
    assert _r("non eu", opted, ["Outside EU"], neg) == "Outside EU"


def test_equals_is_not_subject_to_negation():
    block = {"NA": {"equals": ["ej anställd"]}}
    assert _r("Ej anställd", block, ["NA"], _m("prefix", _NEG)) == "NA"


# --- tie-break --------------------------------------------------------------

def test_tie_break_longest_beats_values_order():
    values = ["Owner", "Tenant-owned"]
    block = {"Owner": {"contains": ["äg"]}, "Tenant-owned": {"contains": ["bostadsrätt"]}}
    raw = "äger en bostadsrätt"
    assert _r(raw, block, values, _m("substring", tie_break=["priority"])) == "Owner"
    assert _r(raw, block, values, _m("substring")) == "Tenant-owned"


def test_tie_break_longest_scores_all_of_by_summed_groups():
    values = ["A", "B"]
    block = {"A": {"all_of": [["ab"], ["cd"]]}, "B": {"all_of": [["abc"]]}}
    assert _r("abc cd", block, values, _m("substring"), priority=["B", "A"]) == "A"  # 2 + 2 > 3


def test_tie_break_priority_uses_priority_list_not_values():
    values = ["Student", "Employed"]
    block = {"Student": {"contains": ["studerar"]}, "Employed": {"contains": ["arbetar"]}}
    raw = "studerar och arbetar"
    m = _m("substring", tie_break=["priority"])
    assert _r(raw, block, values, m, priority=["Student", "Employed"]) == "Student"
    assert _r(raw, block, values, m, priority=["Employed", "Student"]) == "Employed"
    # An attribute-level tie_break override replaces the side default.
    override = {"tie_break": ["priority"], **block}
    longest = _m("substring")
    assert _r(raw, block, values, longest, priority=["Employed", "Student"]) == "Student"
    assert _r(raw, override, values, longest, priority=["Employed", "Student"]) == "Employed"


def test_equal_length_tie_falls_to_priority_and_is_reported():
    values = ["A", "B"]
    block = {"A": {"contains": ["xyz"]}, "B": {"contains": ["abc"]}}
    res = resolve_traced("abc xyz", block, values, matching=_m("substring"), priority=["B", "A"])
    assert res.value == "B"
    assert res.criterion == "priority"
    assert {c.value for c in res.candidates} == {"A", "B"}
    res2 = resolve_traced("abcd xyz", {"A": {"contains": ["xyz"]}, "B": {"contains": ["abcd"]}},
                          values, matching=_m("substring"), priority=["A", "B"])
    assert (res2.value, res2.criterion) == ("B", "longest")
    single = resolve_traced("xyz", block, values, matching=_m("substring"), priority=values)
    assert (single.criterion, len(single.candidates)) == (None, 1)


def test_tier_precedence_unchanged_by_longest():
    values = ["Broad", "Exact"]
    block = {"Broad": {"contains": ["a very long token"]}, "Exact": {"equals": ["x a very long token"]}}
    assert _r("x a very long token", block, values, _m("substring")) == "Exact"


# --- numeric facet -----------------------------------------------------------

_HOURS = r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(?:h\b|hours?\b|timmar\b)"
_PCT = r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*%"
_FACET_VALUES = ["Perm Full", "Perm Part", "Perm Short", "NA"]


def _facet_block():
    return {
        "numeric_facet": {
            "extract": [{"pattern": _HOURS, "scale": 1.0}, {"pattern": _PCT, "scale": 0.4}],
            "ambiguous_if_preceded_by": ["över", "under", "<", ">", "more than", "up to"],
            "bands": [{"name": "short", "gte": 1, "lt": 20}, {"name": "part", "gte": 20, "lt": 35},
                      {"name": "full", "gte": 35}],
            "remap": {v: {"short": "Perm Short", "part": "Perm Part", "full": "Perm Full"}
                      for v in ("Perm Full", "Perm Part", "Perm Short")},
        },
        "Perm Full": {"contains": ["fast"]},
        "NA": {"contains": ["pension"]},
    }


@pytest.mark.parametrize("raw, expected", [
    ("fast, 1 h", "Perm Short"),
    ("fast, 15 h", "Perm Short"),
    ("fast, 19 h", "Perm Short"),
    ("fast, 20 h", "Perm Part"),
    ("fast, 34.5 h", "Perm Part"),
    ("fast, 34,5 timmar", "Perm Part"),
    ("fast, 35 h", "Perm Full"),
    ("fast, 40 timmar i veckan", "Perm Full"),
    ("fast, 80%", "Perm Part"),
    ("fast, 90 %", "Perm Full"),
    ("fast, 20-34 timmar", "Perm Part"),
    ("fast tjänst", "Perm Full"),        # no hours stated: walked value kept
    ("fast, 0 timmar", "Perm Full"),     # 0 is in no band: never overrides
    ("pension 10 h", "NA"),              # walked value not in remap
])
def test_numeric_facet_rebands(raw, expected):
    assert _r(raw, _facet_block(), _FACET_VALUES, _m("prefix")) == expected


@pytest.mark.parametrize("raw, bands", [
    ("fast, 15-25 timmar", ("part", "short")),
    ("fast, 10 h eller 40 h", ("full", "short")),
    ("fast, 1-35 timmar", ("full", "short")),
    ("fast, 30-40 timmar", ("full", "part")),
])
def test_numeric_facet_straddle_is_unmapped_not_the_walked_band(raw, bands):
    # Stated hours across two or more bands leave the band undetermined: the walked
    # "Perm Full" must not survive, and no band is picked either.
    res = resolve_traced(raw, _facet_block(), _FACET_VALUES, matching=_m("prefix"), priority=_FACET_VALUES)
    assert res.value == UNMAPPED
    assert (res.facet, res.facet_bands, res.walked_value) == ("ambiguous", bands, "Perm Full")
    assert res.missed is False                      # the walk hit; the facet withheld the band


def test_numeric_facet_comparator_keeps_walked_value():
    res = resolve_traced("fast, över 30 timmar", _facet_block(), _FACET_VALUES, matching=_m("prefix"),
                         priority=_FACET_VALUES)
    assert (res.value, res.facet) == ("Perm Full", "ambiguous")


@pytest.mark.parametrize("raw", ["fast, 15 h", "fast, 25-30 timmar", "fast, 80%", "fast, 10-15 h"])
def test_numeric_facet_sub_35_hours_never_keep_full_time(raw):
    assert _r(raw, _facet_block(), _FACET_VALUES, _m("prefix")) in ("Perm Part", "Perm Short")


# --- config validation -------------------------------------------------------

def _dir(**index_extra):
    return {
        "_index": {"attributes": {"sex": "sex.json"}, **index_extra},
        "sex": {"values": ["M", "F"], "priority": ["M", "F"],
                "real": {"M": {"equals": ["1"]}}, "synthetic": {"M": {"contains": ["man"]}}},
    }


def test_valid_directory_compiles_both_sides():
    out = validate_mappings(with_matching(_dir()))
    assert set(out) == {"real", "synthetic"}


def test_missing_matching_block_raises():
    with pytest.raises(MappingConfigError, match="'matching' block is required"):
        validate_mappings(_dir())


def test_matching_block_missing_a_side_raises():
    with pytest.raises(MappingConfigError, match="must declare exactly"):
        validate_mappings(_dir(matching={"real": _m("substring")}))


def test_matching_block_missing_a_key_raises():
    with pytest.raises(MappingConfigError, match="must declare exactly"):
        compile_matching({"token_mode": "prefix", "tie_break": ["priority"]})


def test_unknown_token_mode_raises():
    with pytest.raises(MappingConfigError, match="unknown token_mode"):
        compile_matching(_m("fuzzy"))
    with pytest.raises(MappingConfigError, match="unknown token mode"):
        validate_rules({"M": {"contains": [{"token": "man", "mode": "fuzzy"}]}}, ["M"], "t")


def test_unknown_matcher_key_raises():
    # "contain" is a typo: it must raise, not be read as a composite sub-field.
    with pytest.raises(MappingConfigError, match="unknown matcher key 'contain'"):
        validate_rules({"M": {"contain": ["man"]}}, ["M"], "t")
    # A declared sub-field is fine.
    validate_rules({"subfields": ["hours"], "M": {"hours": {"contains": ["35+"]}}}, ["M"], "t")


def test_unknown_block_key_raises():
    with pytest.raises(MappingConfigError, match="unknown key 'Mle'"):
        validate_rules({"Mle": {"contains": ["man"]}}, ["M"], "t")


def test_priority_must_be_permutation_of_values():
    with pytest.raises(MappingConfigError, match="permutation"):
        validate_priority({"values": ["M", "F"], "priority": ["M"]}, "t")
    with pytest.raises(MappingConfigError, match="permutation"):
        validate_priority({"values": ["M", "F"], "priority": ["M", "X"]}, "t")
    with pytest.raises(MappingConfigError, match="'priority' list is required"):
        validate_priority({"values": ["M", "F"]}, "t")


@pytest.mark.parametrize("window", [0, -1, 1.5, True, "2"])
def test_negation_window_positive_int(window):
    with pytest.raises(MappingConfigError, match="window"):
        compile_matching(_m(negation={**_NEG, "window": window}))


def test_negation_cue_must_be_single_word():
    with pytest.raises(MappingConfigError, match="single word"):
        compile_matching(_m(negation={**_NEG, "cues": ["not at all"]}))


def test_attribute_negation_may_only_opt_out():
    with pytest.raises(MappingConfigError, match="opt out"):
        validate_rules({"negation": {"cues": ["x"]}, "M": {"contains": ["m"]}}, ["M"], "t")


def test_tie_break_must_end_with_priority():
    with pytest.raises(MappingConfigError, match="end with 'priority'"):
        compile_matching(_m(tie_break=["longest"]))
    with pytest.raises(MappingConfigError, match="unknown tie_break"):
        compile_matching(_m(tie_break=["shortest", "priority"]))
    with pytest.raises(MappingConfigError, match="end with 'priority'"):
        validate_rules({"tie_break": ["longest"], "M": {"contains": ["m"]}}, ["M"], "t")


def test_facet_remap_target_must_be_value():
    block = _facet_block()
    block["numeric_facet"]["remap"]["Perm Full"]["short"] = "Perm Tiny"
    with pytest.raises(MappingConfigError, match="not one of values"):
        validate_rules(block, _FACET_VALUES, "t")


def test_facet_bands_must_not_overlap():
    block = _facet_block()
    block["numeric_facet"]["bands"][1]["gte"] = 15
    with pytest.raises(MappingConfigError, match="overlap"):
        validate_rules(block, _FACET_VALUES, "t")


def test_empty_token_raises():
    with pytest.raises(MappingConfigError, match="empty token"):
        validate_rules({"M": {"contains": [""]}}, ["M"], "t")


def test_equals_rejects_token_objects():
    with pytest.raises(MappingConfigError, match="token must be a string"):
        validate_rules({"M": {"equals": [{"token": "m", "mode": "prefix"}]}}, ["M"], "t")

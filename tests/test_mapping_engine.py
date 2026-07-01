"""Unit tests for the shared symmetric resolver ``comparison.mapping_engine``.

These drive :func:`resolve` directly with small in-test rules blocks (the same
shape the migrated ``config/mapping/{scb,istat}/*.json`` files will carry) so each
matcher tier, directive, and precedence rule can be exercised in isolation --
before any production config is rewritten.
"""

from population_synth.comparison.mapping_engine import normalize, resolve

# --- equals / contains precedence and first-match-by-order -----------------

def test_equals_exact_match():
    values = ["Male", "Female"]
    block = {"Male": {"equals": ["men", "1"]}, "Female": {"equals": ["women", "2"]}}
    assert resolve("men", block, values) == "Male"
    assert resolve("2", block, values) == "Female"


def test_equals_is_not_substring():
    # ``equals`` must be exact: "women" must not match the "men" token.
    block = {"Male": {"equals": ["men"]}}
    assert resolve("women", block, ["Male"]) is None


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


def test_unmatched_returns_none():
    block = {"Male": {"equals": ["men"]}}
    assert resolve("zzz", block, ["Male"]) is None


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


# --- all_of / none_of ------------------------------------------------------

def test_all_of_requires_one_token_from_every_group():
    block = {
        "PermanentFull": {"all_of": [["permanent", "tillsvidare"], ["full", "heltid"]]},
    }
    assert resolve("permanent heltid contract", block, ["PermanentFull"]) == "PermanentFull"
    # Missing the hours group -> no match.
    assert resolve("permanent contract", block, ["PermanentFull"]) is None


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
    # A size with no bucket and no overflow rule -> None.
    assert resolve(4, block, values) is None


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
    assert resolve(rec_bad, block, values) is None
    # A non-dict raw can never satisfy a composite matcher.
    assert resolve("permanent full time", block, values) is None


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
    # No refine value and primary misses -> None.
    assert resolve("", block, values) is None


# --- absent / on_miss ------------------------------------------------------

def test_absent_literal_for_missing_raw():
    block = {"absent": "Not Applicable", "Manufacturing": {"contains": ["factory"]}}
    values = ["Manufacturing"]
    assert resolve(None, block, values) == "Not Applicable"
    assert resolve("   ", block, values) == "Not Applicable"
    assert resolve("factory worker", block, values) == "Manufacturing"


def test_on_miss_default_none_vs_literal():
    values = ["Wage / Business", "Pension"]
    matchers = {
        "Wage / Business": {"contains": ["salary"]},
        "Pension": {"contains": ["pension"]},
    }
    # Default on_miss -> None.
    assert resolve("lottery winnings", matchers, values) is None
    # Literal on_miss default.
    block_default = {"on_miss": "Wage / Business", **matchers}
    assert resolve("lottery winnings", block_default, values) == "Wage / Business"


def test_unmatched_raw_returns_none_without_fuzzy_fallback():
    # There is no fuzzy tier: a raw that substring-matches a value *label* but hits
    # no declared matcher must miss.
    values = ["Middle Class", "Working Class"]
    block = {"Middle Class": {"equals": ["mc"]}, "Working Class": {"equals": ["wc"]}}
    assert resolve("solidly middle class household", block, values) is None


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


# --- normalization primitive ----------------------------------------------

def test_normalize_lowercases_and_collapses_underscores_but_keeps_hyphens():
    assert normalize("Upper_Secondary") == "upper secondary"
    assert normalize("upper-secondary") == "upper-secondary"
    assert normalize(None) == ""
    assert normalize(42) == "42"

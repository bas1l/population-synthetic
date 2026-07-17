"""Unit tests for analysis.consistency -- the config-driven consistency-scan rules
(load + evaluate) and the scan/report builder.

Covers: :func:`load_rules` failing loudly on a missing config file, an unknown
attribute, a malformed predicate, and an empty ``rules`` list; :func:`evaluate` /
:func:`is_violation` on equality, membership, and numeric-range predicates (using
the real seed rules from ``config/analysis/consistency/scb.yaml`` where useful, and
hand-built rules for the membership/range cases the seed rules don't exercise); and
:func:`scan_population`'s counts/rates/capped-examples on a hand-built mini-population.
"""

from __future__ import annotations

import math

import pytest
import yaml

from population_synthetic.analysis.consistency.builder import scan_population
from population_synthetic.analysis.consistency.rules import (
    Predicate,
    Rule,
    evaluate,
    is_violation,
    load_rules,
)

# ---------------------------------------------------------------------------
# load_rules -- fail-fast config loading
# ---------------------------------------------------------------------------


def test_load_rules_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_rules("swedish", config_path=tmp_path / "does_not_exist.yaml")


def test_load_rules_empty_rules_raises(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text(yaml.safe_dump({"rules": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_rules("swedish", config_path=path)


def test_load_rules_missing_rules_key_raises(tmp_path):
    path = tmp_path / "no_rules_key.yaml"
    path.write_text(yaml.safe_dump({"description": "no rules here"}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_rules("swedish", config_path=path)


def test_load_rules_unknown_attribute_raises(tmp_path):
    path = tmp_path / "unknown_attr.yaml"
    path.write_text(
        yaml.safe_dump({
            "rules": [{
                "id": "bogus",
                "description": "references an attribute that does not exist",
                "severity": "hard",
                "when": {"not_a_real_attribute": "x"},
                "require": {"age": {"min": 1}},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown attribute"):
        load_rules("swedish", config_path=path)


@pytest.mark.parametrize(
    "when_block",
    [
        {"employment_status": 123},  # not a string / list of strings
        {"age": "not a mapping"},  # age must be a {min,max} mapping
        {"age": {}},  # empty age mapping
        {"age": {"min": 1, "bogus": 2}},  # unknown key inside age mapping
        {"civil_status": []},  # empty membership list
        {"civil_status": ["Married", 5]},  # non-string entry in membership list
    ],
)
def test_load_rules_malformed_predicate_raises(tmp_path, when_block):
    path = tmp_path / "malformed.yaml"
    path.write_text(
        yaml.safe_dump({
            "rules": [{
                "id": "malformed",
                "description": "malformed predicate",
                "severity": "hard",
                "when": when_block,
                "require": {"age": {"min": 1}},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_rules("swedish", config_path=path)


def test_load_rules_invalid_severity_raises(tmp_path):
    path = tmp_path / "bad_severity.yaml"
    path.write_text(
        yaml.safe_dump({
            "rules": [{
                "id": "bad_severity",
                "description": "severity is not hard/soft",
                "severity": "critical",
                "when": {"age": {"min": 1}},
                "require": {"age": {"min": 1}},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="severity"):
        load_rules("swedish", config_path=path)


def test_load_rules_duplicate_id_raises(tmp_path):
    rule = {
        "id": "dup",
        "description": "duplicate id",
        "severity": "hard",
        "when": {"age": {"min": 1}},
        "require": {"age": {"min": 1}},
    }
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump({"rules": [rule, dict(rule)]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_rules("swedish", config_path=path)


def test_load_rules_seed_config_loads_expected_rules():
    rules = load_rules("swedish")
    ids = {rule.id for rule in rules}
    assert ids == {"young_retiree", "minor_married"}
    for rule in rules:
        assert rule.severity == "hard"


# ---------------------------------------------------------------------------
# evaluate / is_violation -- predicate matching
# ---------------------------------------------------------------------------


def _rule_by_id(rules, rule_id):
    return next(r for r in rules if r.id == rule_id)


def test_young_retiree_trips_on_young_retired_individual():
    rules = load_rules("swedish")
    young_retiree = _rule_by_id(rules, "young_retiree")

    assert is_violation({"age": 25, "employment_status": "Retired"}, young_retiree) is True
    assert is_violation({"age": 60, "employment_status": "Retired"}, young_retiree) is False
    # Doesn't match `when` at all -> never a violation of this rule.
    assert is_violation({"age": 25, "employment_status": "Employed"}, young_retiree) is False


def test_minor_married_trips_on_underage_married_individual():
    rules = load_rules("swedish")
    minor_married = _rule_by_id(rules, "minor_married")

    assert is_violation({"age": 15, "civil_status": "Married"}, minor_married) is True
    assert is_violation({"age": 20, "civil_status": "Married"}, minor_married) is False
    assert is_violation({"age": 15, "civil_status": "Divorced"}, minor_married) is False


def test_evaluate_equality_predicate():
    predicate = Predicate(attr="civil_status", equals="Married")
    assert evaluate({"civil_status": "Married"}, predicate) is True
    assert evaluate({"civil_status": "Divorced"}, predicate) is False
    assert evaluate({"civil_status": None}, predicate) is False


def test_evaluate_membership_predicate():
    predicate = Predicate(attr="civil_status", isin=("Married", "Divorced"))
    assert evaluate({"civil_status": "Married"}, predicate) is True
    assert evaluate({"civil_status": "Divorced"}, predicate) is True
    assert evaluate({"civil_status": "Widowed"}, predicate) is False


def test_evaluate_age_range_predicate_min_and_max():
    predicate = Predicate(attr="age", age_min=18.0, age_max=64.0)
    assert evaluate({"age": 18}, predicate) is True
    assert evaluate({"age": 64}, predicate) is True
    assert evaluate({"age": 17}, predicate) is False
    assert evaluate({"age": 65}, predicate) is False
    assert evaluate({"age": None}, predicate) is False


def test_evaluate_age_range_predicate_min_only():
    predicate = Predicate(attr="age", age_min=55.0)
    assert evaluate({"age": 55}, predicate) is True
    assert evaluate({"age": 200}, predicate) is True
    assert evaluate({"age": 54}, predicate) is False


def test_is_violation_multi_predicate_when_and_require():
    # Multiple keys inside a single when/require block are ANDed together.
    rule = Rule(
        id="multi",
        description="employed AND married adults should be at least 18",
        severity="soft",
        when=(
            Predicate(attr="employment_status", equals="Employed"),
            Predicate(attr="civil_status", equals="Married"),
        ),
        require=(Predicate(attr="age", age_min=18.0),),
    )
    # Matches both `when` predicates, fails `require` -> violation.
    assert is_violation({"age": 16, "employment_status": "Employed", "civil_status": "Married"}, rule) is True
    # Matches `when`, satisfies `require` -> no violation.
    assert is_violation({"age": 30, "employment_status": "Employed", "civil_status": "Married"}, rule) is False
    # Only one `when` predicate matches -> rule does not apply at all.
    assert is_violation({"age": 16, "employment_status": "Unemployed", "civil_status": "Married"}, rule) is False


# ---------------------------------------------------------------------------
# scan_population -- counts, rates, capped examples
# ---------------------------------------------------------------------------


def _young_retiree_rule():
    return Rule(
        id="young_retiree",
        description="Retired individuals should not be younger than 55.",
        severity="hard",
        when=(Predicate(attr="employment_status", equals="retired"),),
        require=(Predicate(attr="age", age_min=55.0),),
    )


def test_scan_population_counts_and_rates():
    individuals = [
        {"id": 0, "age": 25, "employment_status": "retired"},   # violation
        {"id": 1, "age": 60, "employment_status": "retired"},   # ok
        {"id": 2, "age": 30, "employment_status": "Employed"},  # rule doesn't apply
        {"id": 3, "age": 40, "employment_status": "retired"},   # violation
    ]
    rules = (_young_retiree_rule(),)

    report = scan_population(individuals, rules, population="mini", country="swedish")

    assert report.n_individuals == 4
    assert len(report.results) == 1
    result = report.results[0]
    assert result.rule_id == "young_retiree"
    assert result.n_violations == 2
    assert math.isclose(result.violation_rate, 0.5)
    assert len(result.examples) == 2
    assert {ex["id"] for ex in result.examples} == {0, 3}


def test_scan_population_caps_examples():
    individuals = [{"id": i, "age": 20, "employment_status": "retired"} for i in range(10)]
    rules = (_young_retiree_rule(),)

    report = scan_population(individuals, rules, population="mini", country="swedish", max_examples=3)

    result = report.results[0]
    assert result.n_violations == 10
    assert math.isclose(result.violation_rate, 1.0)
    assert len(result.examples) == 3


def test_scan_population_empty_population_yields_nan_rate():
    report = scan_population([], (_young_retiree_rule(),), population="empty", country="swedish")

    assert report.n_individuals == 0
    result = report.results[0]
    assert result.n_violations == 0
    assert math.isnan(result.violation_rate)
    assert result.examples == ()


def test_scan_population_never_mutates_input():
    individuals = [{"id": 0, "age": 25, "employment_status": "retired"}]
    snapshot = [dict(ind) for ind in individuals]

    scan_population(individuals, (_young_retiree_rule(),), population="mini", country="swedish")

    assert individuals == snapshot

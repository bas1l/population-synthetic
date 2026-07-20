"""rules.py -- Config-driven consistency rules: fail-fast loader + predicate matcher.

A rule is a **guarded requirement**: ``when`` (a predicate over canonical attributes)
implies ``require`` (another predicate). An individual matching every predicate in
``when`` but failing at least one predicate in ``require`` is a violation of that
rule. The rule list lives in ``config/analysis/consistency/{country}.yaml`` (country
keyed by the real mapper's ``MAPPINGS_SUBDIR`` stem, the same convention as
``config/analysis/fidelity/{country}.json``) -- see that file for the exact grammar
and the current seed rules.

:func:`load_rules` is deliberately strict (fail-fast convention): a missing config
file, an empty ``rules`` list, a rule referencing an attribute unknown to the
country's :class:`~population_synthetic.analysis.fidelity.scheme.ComparisonScheme`
(plus the raw ``age`` field, which individuals carry but which is not itself a scored
comparison attribute), or any predicate shape outside the small grammar below all
raise loudly rather than silently dropping or defaulting a rule.

Predicate grammar (one attribute per key inside a ``when``/``require`` mapping;
multiple keys are ANDed together):

- ``{attr: "label"}``        -- categorical equality against the canonical mapped value.
- ``{attr: [l1, l2]}``       -- categorical membership.
- ``{age: {min: N, max: M}}`` -- numeric range on the raw integer ``age`` (``min``/``max``
  both optional, at least one required).

Individuals are canonical *mapped* records (from the analysis-stage mapping folder), where
every scored attribute is a plain string value (e.g. ``{"employment_status": "Employed"}``)
-- not a nested ``{"label": ...}`` dict; that nested shape belongs to the raw,
pre-mapping record produced by the generator. :func:`evaluate` reads values through
:func:`~population_synthetic.analysis.fidelity.evaluator.attr_value`, which also
derives ``age_group`` from the raw integer ``age`` on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.fidelity.evaluator import attr_value
from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.mapping.real_mapper.factory import _mapper_class

_CONFIG_ROOT = PROJECT_ROOT / "config" / "analysis" / "consistency"

#: Raw fields accepted in a predicate in addition to the country's scored
#: ComparisonScheme attributes. ``age`` is not itself a scored comparison attribute
#: (``age_group`` is, derived from it), but individuals carry the raw integer and
#: rules commonly need a numeric range on it.
_EXTRA_ATTRS: tuple[str, ...] = ("age",)

_VALID_SEVERITIES: tuple[str, ...] = ("hard", "soft")


@dataclass(frozen=True)
class Predicate:
    """One attribute-level condition inside a rule's ``when`` or ``require`` block.

    Exactly one of ``equals``/``isin``/(``age_min`` or ``age_max``) is populated,
    matching the three predicate shapes in the module grammar.
    """

    attr: str
    equals: str | None = None
    isin: tuple[str, ...] | None = None
    age_min: float | None = None
    age_max: float | None = None


@dataclass(frozen=True)
class Rule:
    """One guarded-requirement consistency rule: ``when`` implies ``require``."""

    id: str
    description: str
    severity: str
    when: tuple[Predicate, ...]
    require: tuple[Predicate, ...]


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _config_path(country: str) -> Path:
    """Rule-config path for *country*: ``config/analysis/consistency/{MAPPINGS_SUBDIR}.yaml``."""
    subdir = _mapper_class(country).MAPPINGS_SUBDIR
    return _CONFIG_ROOT / f"{subdir}.yaml"


def _parse_age_condition(condition: Any, *, rule_id: str, field_name: str) -> Predicate:
    if not isinstance(condition, dict) or not condition:
        raise ValueError(
            f"Consistency rule {rule_id!r}: 'age' condition in '{field_name}' must be a "
            f"non-empty mapping with 'min' and/or 'max', got {condition!r}"
        )
    unknown_keys = set(condition) - {"min", "max"}
    if unknown_keys:
        raise ValueError(
            f"Consistency rule {rule_id!r}: 'age' condition in '{field_name}' has unknown "
            f"keys {sorted(unknown_keys)} (only 'min'/'max' allowed)"
        )
    age_min, age_max = condition.get("min"), condition.get("max")
    if age_min is None and age_max is None:
        raise ValueError(
            f"Consistency rule {rule_id!r}: 'age' condition in '{field_name}' must declare "
            "at least one of 'min'/'max'"
        )
    for bound_name, bound_value in (("min", age_min), ("max", age_max)):
        if bound_value is not None and (isinstance(bound_value, bool) or not isinstance(bound_value, (int, float))):
            raise ValueError(
                f"Consistency rule {rule_id!r}: 'age' {bound_name!r} in '{field_name}' must "
                f"be a number, got {bound_value!r}"
            )
    return Predicate(
        attr="age",
        age_min=float(age_min) if age_min is not None else None,
        age_max=float(age_max) if age_max is not None else None,
    )


def _parse_condition(attr: str, condition: Any, *, rule_id: str, field_name: str) -> Predicate:
    if attr == "age":
        return _parse_age_condition(condition, rule_id=rule_id, field_name=field_name)
    if isinstance(condition, str):
        if not condition:
            raise ValueError(f"Consistency rule {rule_id!r}: {attr!r} equality label in '{field_name}' is empty")
        return Predicate(attr=attr, equals=condition)
    if isinstance(condition, list):
        if not condition or not all(isinstance(v, str) and v for v in condition):
            raise ValueError(
                f"Consistency rule {rule_id!r}: {attr!r} membership list in '{field_name}' must "
                f"be a non-empty list of non-empty strings, got {condition!r}"
            )
        return Predicate(attr=attr, isin=tuple(condition))
    raise ValueError(
        f"Consistency rule {rule_id!r}: malformed predicate for {attr!r} in '{field_name}': "
        f"{condition!r} (expected a string, a list of strings, or -- for 'age' -- a "
        "{min, max} mapping)"
    )


def _parse_predicate_block(
    block: Any, *, rule_id: str, field_name: str, valid_attrs: set[str]
) -> tuple[Predicate, ...]:
    if not isinstance(block, dict) or not block:
        raise ValueError(
            f"Consistency rule {rule_id!r}: '{field_name}' must be a non-empty mapping of "
            f"attribute -> condition, got {block!r}"
        )
    predicates: list[Predicate] = []
    for attr, condition in block.items():
        if attr not in valid_attrs:
            raise ValueError(
                f"Consistency rule {rule_id!r}: unknown attribute {attr!r} in '{field_name}' "
                f"(known attributes: {sorted(valid_attrs)})"
            )
        predicates.append(_parse_condition(attr, condition, rule_id=rule_id, field_name=field_name))
    return tuple(predicates)


def load_rules(country: str, *, config_path: Path | None = None) -> tuple[Rule, ...]:
    """Load the consistency rule list for *country* (fail-fast).

    Raises on: a missing config file, a config without a non-empty ``rules`` list, a
    rule entry missing a required key (``id``/``description``/``severity``/``when``/
    ``require``), a duplicate ``id``, an invalid ``severity`` (must be ``hard`` or
    ``soft``), a predicate referencing an attribute unknown to the country's
    :class:`~population_synthetic.analysis.fidelity.scheme.ComparisonScheme`
    (plus the raw ``age`` field), or any predicate whose shape does not match the
    module grammar. *config_path* overrides the default
    ``config/analysis/consistency/{MAPPINGS_SUBDIR}.yaml`` location (for tests).
    """
    path = config_path if config_path is not None else _config_path(country)
    if not path.is_file():
        raise FileNotFoundError(f"No consistency rule config for country {country!r}: {path} not found")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or "rules" not in raw:
        raise KeyError(f"Consistency rule config {path} is missing required key 'rules'")

    entries = raw["rules"]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Consistency rule config {path}: 'rules' must be a non-empty list")

    scheme = load_scheme(country)
    valid_attrs = set(scheme.attributes) | set(_EXTRA_ATTRS)

    seen_ids: set[str] = set()
    parsed: list[Rule] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Consistency rule config {path}: each rule entry must be a mapping, got {entry!r}")

        missing = [key for key in ("id", "description", "severity", "when", "require") if key not in entry]
        if missing:
            raise KeyError(f"Consistency rule config {path}: rule entry {entry!r} missing key(s) {missing}")

        rule_id = entry["id"]
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError(f"Consistency rule config {path}: rule 'id' must be a non-empty string, got {rule_id!r}")
        if rule_id in seen_ids:
            raise ValueError(f"Consistency rule config {path}: duplicate rule id {rule_id!r}")
        seen_ids.add(rule_id)

        description = entry["description"]
        if not isinstance(description, str) or not description:
            raise ValueError(f"Consistency rule {rule_id!r}: 'description' must be a non-empty string")

        severity = entry["severity"]
        if severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"Consistency rule {rule_id!r}: 'severity' must be one of {_VALID_SEVERITIES}, got {severity!r}"
            )

        when = _parse_predicate_block(
            entry["when"], rule_id=rule_id, field_name="when", valid_attrs=valid_attrs
        )
        require = _parse_predicate_block(
            entry["require"], rule_id=rule_id, field_name="require", valid_attrs=valid_attrs
        )

        parsed.append(Rule(id=rule_id, description=description, severity=severity, when=when, require=require))

    return tuple(parsed)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def evaluate(individual: dict, predicate: Predicate) -> bool:
    """Return whether *individual* satisfies one *predicate*.

    Reads the individual's value through
    :func:`~population_synthetic.analysis.fidelity.evaluator.attr_value` (which also
    derives ``age_group`` from the raw ``age`` on demand) for every attribute except
    the raw ``age`` field itself, which is read directly. A ``None``/non-numeric raw
    ``age`` never satisfies an age-range predicate (missing data is not "in range").
    """
    value = individual.get("age") if predicate.attr == "age" else attr_value(individual, predicate.attr)

    if predicate.equals is not None:
        return value == predicate.equals

    if predicate.isin is not None:
        return value in predicate.isin

    # Numeric range predicate (age_min / age_max).
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if predicate.age_min is not None and numeric < predicate.age_min:
        return False
    if predicate.age_max is not None and numeric > predicate.age_max:
        return False
    return True


def _matches_all(individual: dict, predicates: tuple[Predicate, ...]) -> bool:
    return all(evaluate(individual, predicate) for predicate in predicates)


def is_violation(individual: dict, rule: Rule) -> bool:
    """True when *individual* matches every ``when`` predicate but fails ``require``."""
    if not _matches_all(individual, rule.when):
        return False
    return not _matches_all(individual, rule.require)

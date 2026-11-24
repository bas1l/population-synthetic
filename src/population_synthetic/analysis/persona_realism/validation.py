"""validation.py -- the hard-rules can_exist validation subset (the validity anchor).

The reliability metric in :mod:`stats` measures the judge's self-consistency, not
its correctness. This module supplies the *only* validity signal: a small set of
**config-driven, deterministic** structural-impossibility rules
(``config/analysis/persona_realism/hard_rules.yaml``) evaluated over a sampled
subset of personas, whose verdicts are compared to the judge's majority
``can_exist``. A rule firing means the persona is structurally IMPOSSIBLE, so the
judge should have said ``can_exist=false``; the agreement (and specifically the
recall on rule-detected impossibilities) is the QC number the report surfaces.

Rules live only in config -- **no rule is hardcoded here**. The engine dispatches
on a rule ``type`` (``incompatible_pair`` is the one type implemented in v1) so
more types can be added in config + a matching ``_fires_*`` handler without
touching callers. It is pure apart from :func:`load_hard_rules`, a thin config
parse (mirroring ``prompt.load_prompt_template``); it must NOT know about paths
beyond the one it is handed, the registry, the LLM, or rendering.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from population_synthetic.analysis.persona_realism.reduce import LoadedPersona, reduce_persona

__all__ = [
    "HardRule",
    "HardRulesValidation",
    "load_hard_rules",
    "rule_fires",
    "rules_verdict",
    "validate_against_hard_rules",
]

# The rule types the engine can evaluate. v1 grounds only ``incompatible_pair``;
# adding a type means adding a config entry + a ``_fires_<type>`` handler here.
_SUPPORTED_TYPES: frozenset[str] = frozenset({"incompatible_pair"})


@dataclass(frozen=True)
class HardRule:
    """One deterministic structural-impossibility rule from ``hard_rules.yaml``.

    ``type`` selects the firing predicate. For ``incompatible_pair`` the rule fires
    when the persona's ``when_attribute`` value is in ``when_equals`` AND its
    ``forbid_attribute`` value is in ``forbid_equals`` -- an impossible co-occurrence
    (``severity`` ``S3``). ``when_equals``/``forbid_equals`` are frozensets for
    O(1), order-independent membership.
    """

    id: str
    description: str
    type: str
    when_attribute: str
    when_equals: frozenset[str]
    forbid_attribute: str
    forbid_equals: frozenset[str]
    severity: str


@dataclass(frozen=True)
class HardRulesValidation:
    """Result of comparing the deterministic rules to the judge over a subset.

    ``n_sampled`` personas were checked; ``n_rule_impossible`` were flagged
    impossible by at least one rule. The 2x2 confusion of rule-impossibility vs the
    judge's majority ``can_exist``:

    * ``both_impossible`` -- rule fired AND judge said impossible (agreement on the
      contradiction);
    * ``rule_impossible_judge_possible`` -- rule fired but the judge said possible
      (the judge *missed* a structural impossibility -- the failure this anchor
      exists to catch);
    * ``both_possible`` -- no rule fired AND judge possible;
    * ``rule_possible_judge_impossible`` -- no rule fired but the judge said
      impossible (NOT a judge error: the rules cover only a subset of all
      impossibilities, so the judge legitimately finds contradictions the rules do
      not encode).

    ``agreement`` is ``(both_possible + both_impossible) / n_sampled``.
    ``recall_on_rule_impossibilities`` is ``both_impossible / n_rule_impossible`` --
    the share of *known* structural impossibilities the judge caught (``None`` when
    no rule fired in the subset). ``fired_rule_counts`` maps each rule id to the
    number of sampled personas it fired on. All ratios are ``None`` (not ``NaN``)
    when their denominator is zero.
    """

    n_sampled: int
    n_rule_impossible: int
    both_impossible: int
    rule_impossible_judge_possible: int
    both_possible: int
    rule_possible_judge_impossible: int
    agreement: float | None
    recall_on_rule_impossibilities: float | None
    fired_rule_counts: dict[str, int] = field(default_factory=dict)


def load_hard_rules(path: str | Path) -> tuple[HardRule, ...]:
    """Parse ``hard_rules.yaml`` into validated :class:`HardRule`s (fail-fast).

    Raises ``ValueError`` on a missing ``rules`` list, an unsupported rule
    ``type``, or a malformed rule (missing ``id``/``when``/``forbid``/``equals``) --
    a validity anchor built on a silently-defaulted rule is worse than none.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"hard-rules config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"hard-rules config {path} must be a mapping with a 'rules' list")
    raw_rules = data["rules"]
    if not isinstance(raw_rules, list):
        raise ValueError(f"hard-rules config {path} 'rules' must be a list, got {type(raw_rules).__name__}")

    rules: list[HardRule] = []
    for i, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"hard-rules config {path} rule[{i}] must be a mapping")
        try:
            rule_type = raw["type"]
            if rule_type not in _SUPPORTED_TYPES:
                raise ValueError(
                    f"rule[{i}] has unsupported type {rule_type!r}; "
                    f"implemented types: {sorted(_SUPPORTED_TYPES)}"
                )
            when = raw["when"]
            forbid = raw["forbid"]
            rules.append(
                HardRule(
                    id=str(raw["id"]),
                    description=str(raw.get("description", "")),
                    type=str(rule_type),
                    when_attribute=str(when["attribute"]),
                    when_equals=frozenset(str(v) for v in when["equals"]),
                    forbid_attribute=str(forbid["attribute"]),
                    forbid_equals=frozenset(str(v) for v in forbid["equals"]),
                    severity=str(raw.get("severity", "S3")),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"hard-rules config {path} rule[{i}] is malformed: {exc}") from exc

    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise ValueError(f"hard-rules config {path} has duplicate rule ids: {ids}")
    return tuple(rules)


def _fires_incompatible_pair(rule: HardRule, attributes: dict[str, Any]) -> bool:
    """Firing predicate for an ``incompatible_pair`` rule (fail-fast on absent axis)."""
    for attr in (rule.when_attribute, rule.forbid_attribute):
        if attr not in attributes:
            raise KeyError(
                f"hard rule {rule.id!r} references attribute {attr!r} absent from the "
                f"persona (present axes: {sorted(attributes)})"
            )
    return (
        str(attributes[rule.when_attribute]) in rule.when_equals
        and str(attributes[rule.forbid_attribute]) in rule.forbid_equals
    )


def rule_fires(rule: HardRule, attributes: dict[str, Any]) -> bool:
    """Return whether *rule* fires (declares impossible) on a persona's attributes."""
    if rule.type == "incompatible_pair":
        return _fires_incompatible_pair(rule, attributes)
    raise ValueError(f"unsupported hard-rule type {rule.type!r}")


def rules_verdict(
    rules: tuple[HardRule, ...] | list[HardRule],
    attributes: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate all rules on one persona: ``(is_impossible, fired_rule_ids)``.

    A persona is rule-impossible if ANY rule fires; the fired ids are returned so
    the caller can attribute impossibilities per rule.
    """
    fired = tuple(r.id for r in rules if rule_fires(r, attributes))
    return (len(fired) > 0, fired)


def _sample_personas(
    personas: list[LoadedPersona],
    sample_size: int | None,
    seed: Any,
) -> list[LoadedPersona]:
    """Seeded subsample of *personas* (all when unbounded / larger than the set).

    Sorted by persona id before sampling and the result re-sorted, so the subset is
    deterministic in *seed* and stable across runs.
    """
    ordered = sorted(personas, key=lambda p: p.persona_id)
    if sample_size is None or sample_size >= len(ordered):
        return ordered
    rng = random.Random(seed)
    chosen = rng.sample(ordered, sample_size)
    return sorted(chosen, key=lambda p: p.persona_id)


def validate_against_hard_rules(
    personas: list[LoadedPersona],
    rules: tuple[HardRule, ...] | list[HardRule],
    *,
    sample_size: int | None = None,
    seed: Any = None,
) -> HardRulesValidation:
    """Run the deterministic rules over a sampled subset and score judge agreement.

    For each sampled persona: the judge's majority ``can_exist`` (from
    :func:`reduce.reduce_persona` over its cached rounds) is compared to the
    deterministic ``rules_verdict``. See :class:`HardRulesValidation` for the
    confusion cells and the recall/agreement definitions.
    """
    subset = _sample_personas(personas, sample_size, seed)
    n_sampled = len(subset)

    both_impossible = 0
    rule_impossible_judge_possible = 0
    both_possible = 0
    rule_possible_judge_impossible = 0
    n_rule_impossible = 0
    fired_rule_counts: dict[str, int] = {}

    for persona in subset:
        judge_possible = reduce_persona(persona.rounds, persona_id=persona.persona_id).possible_majority
        rule_impossible, fired = rules_verdict(rules, persona.attributes)
        for rule_id in fired:
            fired_rule_counts[rule_id] = fired_rule_counts.get(rule_id, 0) + 1
        if rule_impossible:
            n_rule_impossible += 1
            if judge_possible:
                rule_impossible_judge_possible += 1
            else:
                both_impossible += 1
        else:
            if judge_possible:
                both_possible += 1
            else:
                rule_possible_judge_impossible += 1

    agreement = (both_possible + both_impossible) / n_sampled if n_sampled else None
    recall = both_impossible / n_rule_impossible if n_rule_impossible else None

    return HardRulesValidation(
        n_sampled=n_sampled,
        n_rule_impossible=n_rule_impossible,
        both_impossible=both_impossible,
        rule_impossible_judge_possible=rule_impossible_judge_possible,
        both_possible=both_possible,
        rule_possible_judge_impossible=rule_possible_judge_impossible,
        agreement=agreement,
        recall_on_rule_impossibilities=recall,
        fired_rule_counts=fired_rule_counts,
    )

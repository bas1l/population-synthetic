"""Shared, symmetric mapping resolver for the comparison pipeline.

This is the single engine both the *real* mapper and the
*synthetic* (pipeline) mapper delegate to. It replaces the two parallel
5-handler factory stacks (``real_mapper.base`` / ``synthetic_mapper.base``)
with one ordered value-walk driven by the symmetric per-attribute config.

Config shape (per attribute file, e.g. ``biological_sex.json``)::

    {
      "values": ["Male", "Female"],          # unified value set + axis order
      "real":      {"Male": {"equals": ["men","1"]}, "Female": {...}},
      "synthetic": {"Male": {"contains": ["male"]}, "Female": {...}}
    }

The ``real`` block resolves a raw national-statistics value; the
``synthetic`` block resolves a raw LLM ``identity.json`` value. Both are keyed by
unified value → matcher, so the two sides are symmetric and the scored comparison
axis simply *is* the ``values`` list.

Resolution model
----------------
:func:`resolve` matches ``values`` with a **global tiered sweep** and returns the
first value that hits; a total miss yields the ``UNMAPPED`` sentinel (or the
attribute-level ``on_miss`` literal, when one is declared). Each tier is swept
across *all* values before the next tier is tried, so
a later value's ``equals`` beats an earlier value's ``contains``. Within a single
tier, ``values`` declared order breaks ties.

Tier order (first hit wins; ``none_of`` vetoes its value in every tier):

1. ``equals`` — exact match: the normalized+stripped raw equals a normalized token.
2. ``all_of`` — AND-of-ORs: the raw contains at least one token from *every* group.
3. ``contains`` — substring: the raw contains any token.
4. ``int`` / ``int_gte`` — numeric: ``int(raw)`` is in the list / ``>=`` the bound.

``none_of`` is a veto, not a tier: if any token is present in the (normalized) raw,
that value is rejected in every tier regardless of its positive matchers.

A **composite** matcher (used by ``employment_type`` real, whose raw record has
``attachment`` + ``hours`` sub-fields) keys sub-fields of a dict raw value instead
of the reserved matcher keys above; every sub-field matcher must hit::

    "Permanent Full-time": {
      "attachment": {"contains": ["permanent employees"]},
      "hours":      {"contains": ["35+ hours"]}
    }

Composite values are swept in their own pass after the scalar tiers (composite and
scalar values never coexist within one attribute side, so the pass order is moot).

Attribute-level directives (reserved keys on the ``real`` / ``synthetic`` block,
never confused with value keys because the walk is driven by ``values``):

- ``absent`` — literal value emitted when the raw input is missing/empty
  (e.g. ``"Not Applicable"``); replaces the old ``reference_none_default``.
- ``refine_from`` — cross-field: when the primary raw walk misses, re-run the walk
  against a second attribute's already-resolved value (passed as ``refine_value``);
  replaces the old ``cross_field_coded`` handler.
- ``on_miss`` — literal default when everything misses; e.g. synthetic
  ``industry_sector`` → ``"Other"``. When omitted, a total miss defaults to the
  explicit ``UNMAPPED`` sentinel (``"__UNMAPPED__"``), not a bare ``None``.
"""

from __future__ import annotations

import re
from typing import Any

from population_synthetic.analysis.mapping.synthetic_mapper._text_helpers import (
    _repair_utf8_double_encoding,
)
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED, is_unmapped

# ---------------------------------------------------------------------------
# Reserved keys
# ---------------------------------------------------------------------------

#: Matcher keys recognised inside a per-value matcher block. A value block whose
#: keys are *all* drawn from this set is a scalar matcher; a block carrying any
#: other key is a composite matcher (its extra keys naming raw sub-fields).
_MATCHER_KEYS: frozenset[str] = frozenset(
    {"equals", "contains", "all_of", "none_of", "int", "int_gte"}
)

#: Attribute-level directive keys on a ``real`` / ``synthetic`` rules block.
#: These are never treated as values (the value-walk is driven by ``values``).
_DIRECTIVE_KEYS: frozenset[str] = frozenset({"absent", "refine_from", "on_miss"})

#: Scalar matcher tiers, swept in this order globally across all values.
_SCALAR_TIERS: tuple[str, ...] = ("equals", "all_of", "contains", "numeric")

_UNDERSCORE_RE = re.compile(r"_")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize(value: Any) -> str:
    """Normalize a raw value to the canonical matching form.

    Repairs double-encoded UTF-8 (mirroring the synthetic mapper's record-level
    repair), lowercases, and collapses underscores to spaces. Hyphens are
    **preserved** and the result is **not** stripped -- matching the behaviour of
    the retired ``_kw_norm`` keyword-rule normaliser, so order-sensitive
    distinctions (``upper-secondary`` vs ``upper secondary``) and leading-space
    tokens (``" city"``) survive substring tests. ``equals`` comparisons strip
    both sides separately (see :func:`_match_scalar`).
    """
    text = "" if value is None else str(value)
    text = _repair_utf8_double_encoding(text)
    return _UNDERSCORE_RE.sub(" ", text.lower())


_LEADING_INT_RE = re.compile(r"-?\d+")


def _to_int(value: Any) -> int | None:
    """Return *value* as an int, else None.

    Accepts a real int, a pure-integer string, or a string that *begins* with an
    integer -- so LLM household-size answers like ``"2 people"``,
    ``"1 person (living alone)"``, ``"2.0"`` (leading ``2``) or ``"10+"`` resolve
    to their leading count. Strings with no leading digit (``"Three"``,
    ``"Nuclear family"``) still yield None. Only the ``int`` / ``int_gte`` matchers
    consume this (household_size on the synthetic side), so widening it here does
    not affect any other attribute.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        m = _LEADING_INT_RE.match(value.strip())
        if m is not None:
            return int(m.group())
    return None


def _is_absent(raw: Any) -> bool:
    """True when the raw input carries no value (None, or blank/whitespace string)."""
    if raw is None:
        return True
    if isinstance(raw, str) and raw.strip() == "":
        return True
    return False


# ---------------------------------------------------------------------------
# Matcher evaluators
# ---------------------------------------------------------------------------

def _is_composite(matcher: dict) -> bool:
    """A matcher is composite iff it declares at least one non-reserved (sub-field) key."""
    return any(key not in _MATCHER_KEYS for key in matcher)


def _vetoed(raw: Any, matcher: dict) -> bool:
    """True when the matcher's ``none_of`` veto is triggered by *raw*."""
    none_of = matcher.get("none_of")
    if none_of:
        norm = normalize(raw)
        return any(normalize(tok) in norm for tok in none_of)
    return False


def _match_tier(raw: Any, matcher: dict, tier: str) -> bool:
    """Evaluate a single scalar matcher *tier* against *raw* (no ``none_of`` veto).

    The veto is applied separately by the caller so it can gate every tier. Tier
    keys: ``equals`` (exact on stripped/normalized forms), ``all_of`` (AND-of-ORs),
    ``contains`` (substring), ``numeric`` (``int`` / ``int_gte``).
    """
    if tier == "equals":
        equals = matcher.get("equals")
        if equals is not None:
            norm_stripped = normalize(raw).strip()
            return any(norm_stripped == normalize(tok).strip() for tok in equals)
        return False

    if tier == "all_of":
        all_of = matcher.get("all_of")
        if all_of is not None:
            norm = normalize(raw)
            return all(any(normalize(tok) in norm for tok in group) for group in all_of)
        return False

    if tier == "contains":
        contains = matcher.get("contains")
        if contains is not None:
            norm = normalize(raw)
            return any(normalize(tok) in norm for tok in contains)
        return False

    if tier == "numeric":
        raw_int = _to_int(raw)
        if raw_int is not None:
            int_list = matcher.get("int")
            if int_list is not None and raw_int in int_list:
                return True
            int_gte = matcher.get("int_gte")
            if int_gte is not None and raw_int >= int_gte:
                return True
        return False

    return False


def _match_scalar(raw: Any, matcher: dict) -> bool:
    """Evaluate a scalar matcher as a whole (all tiers, first hit), honouring ``none_of``.

    Used for composite sub-field matchers, where the sub-field is a single matcher
    resolved in isolation. The top-level value-walk instead sweeps tiers globally.
    """
    if _vetoed(raw, matcher):
        return False
    return any(_match_tier(raw, matcher, tier) for tier in _SCALAR_TIERS)


def _match_composite(raw: Any, matcher: dict) -> bool:
    """Evaluate a composite matcher: every sub-field's own matcher must hit.

    *raw* must be a dict of raw sub-fields (e.g. ``{"attachment": ..., "hours": ...}``);
    a non-dict raw can never satisfy a composite matcher.
    """
    if not isinstance(raw, dict):
        return False
    for subfield, sub_matcher in matcher.items():
        if not isinstance(sub_matcher, dict):
            return False
        if not _match_value(raw.get(subfield), sub_matcher):
            return False
    return True


def _match_value(raw: Any, matcher: dict) -> bool:
    """Dispatch to the composite or scalar evaluator for one value's matcher block."""
    if _is_composite(matcher):
        return _match_composite(raw, matcher)
    return _match_scalar(raw, matcher)


def _walk(raw: Any, rules_block: dict, values: list[str]) -> str | None:
    """Return the matching value via a global tiered sweep, else None.

    Each scalar tier (``equals`` → ``all_of`` → ``contains`` → ``numeric``) is swept
    across *all* values before the next tier is tried, so a later value's ``equals``
    beats an earlier value's ``contains``. Within a tier, declared ``values`` order
    breaks ties. Composite values are swept in a final pass (they never coexist with
    scalar values on one attribute side). ``none_of`` vetoes its value in every tier.
    """
    for tier in _SCALAR_TIERS:
        for value in values:
            matcher = rules_block.get(value)
            if matcher is None or _is_composite(matcher):
                continue
            if _vetoed(raw, matcher):
                continue
            if _match_tier(raw, matcher, tier):
                return value

    for value in values:
        matcher = rules_block.get(value)
        if matcher is None or not _is_composite(matcher):
            continue
        if _match_composite(raw, matcher):
            return value

    return None


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def resolve(
    raw_value: Any,
    rules_block: dict,
    values: list[str],
    *,
    refine_value: str | None = None,
) -> str | None:
    """Resolve one raw input to a unified value using *rules_block*.

    Parameters
    ----------
    raw_value:
        The raw input for this attribute. A scalar (str/int/None) for simple and
        numeric attributes, or a dict of sub-fields for composite attributes
        (whose value matchers key those sub-fields).
    rules_block:
        The per-attribute ``real`` or ``synthetic`` block: unified value →
        matcher entries plus the optional attribute-level directives ``absent`` /
        ``refine_from`` / ``on_miss``.
    values:
        The unified value set in declared (priority) order. The walk only ever
        considers keys present in this list, so directive keys never collide with
        value keys.
    refine_value:
        The already-resolved value of the ``refine_from`` attribute, supplied by
        the caller. Only consulted when ``rules_block`` declares ``refine_from``
        and the primary walk misses.

    Returns
    -------
    The first matching unified value, the ``absent`` literal (missing raw), or the
    total-miss default: the attribute's ``on_miss`` literal when declared, else the
    ``UNMAPPED`` sentinel (``"__UNMAPPED__"``).
    """
    absent = rules_block.get("absent")
    # Default a total miss to the explicit UNMAPPED sentinel (not a bare None), so a
    # "mapped, but nothing matched" outcome is legible downstream. Attributes that
    # declare their own ``on_miss`` literal are unaffected.
    on_miss = rules_block.get("on_miss", UNMAPPED)
    refine_from = rules_block.get("refine_from")

    # Absent input -> the declared literal (e.g. "Not Applicable"). When no
    # ``absent`` is declared, an empty primary still falls through so a
    # ``refine_from`` attribute can resolve from its sibling field.
    if _is_absent(raw_value) and absent is not None:
        return absent

    # 1. Primary ordered value-walk against the raw input.
    hit = _walk(raw_value, rules_block, values)
    if hit is not None:
        return hit

    # 2. refine_from: re-run the same walk against the sibling's resolved value.
    #    An unmapped sibling (UNMAPPED sentinel or legacy None) carries no canonical
    #    value to refine from, so it is skipped exactly as a bare None was.
    if refine_from and not is_unmapped(refine_value) and not _is_absent(refine_value):
        hit = _walk(refine_value, rules_block, values)
        if hit is not None:
            return hit

    # 3. Total miss -> the on_miss literal (default: the UNMAPPED sentinel).
    return on_miss

"""Shared, symmetric mapping resolver for the comparison pipeline.

This is the single engine both the *real* mapper and the
*synthetic* (pipeline) mapper delegate to. It replaces the two parallel
5-handler factory stacks (``real_mapper.base`` / ``synthetic_mapper.base``)
with one ordered value-walk driven by the symmetric per-attribute config.

Config shape (per attribute file, e.g. ``biological_sex.json``)::

    {
      "values":   ["Male", "Female"],         # unified value set + axis order
      "priority": ["Male", "Female"],         # tie-break order (permutation of values)
      "real":      {"Male": {"equals": ["men","1"]}, "Female": {...}},
      "synthetic": {"Male": {"contains": ["male"]}, "Female": {...}}
    }

The ``real`` block resolves a raw national-statistics value; the
``synthetic`` block resolves a raw LLM ``identity.json`` value. Both are keyed by
unified value → matcher, so the two sides are symmetric and the scored comparison
axis simply *is* the ``values`` list. ``priority`` is the explicit rule priority
used to break ties; it is deliberately separate from ``values`` (which is also the
chart / axis order) so the two jobs never share one list.

Matching options (``_index.json`` ``matching`` block)
-----------------------------------------------------
Every mapping directory's ``_index.json`` declares, for each side, how tokens
match. There is no in-code default: a missing or malformed block raises
(:func:`validate_mappings`)::

    "matching": {
      "synthetic": {"token_mode": "prefix",
                    "negation": {"cues": ["not", "inte", ...], "window": 2,
                                 "clause_breaks": [",", ";", "but", "men", ...]},
                    "tie_break": ["longest", "priority"]},
      "real":      {"token_mode": "substring", "negation": null, "tie_break": ["priority"]}
    }

- ``token_mode`` -- how a ``contains`` / ``all_of`` / ``none_of`` token must sit in
  the raw text:

  * ``substring``: anywhere (the historic behaviour);
  * ``prefix``: the character before the match must not be alphanumeric
    (``str.isalnum``, so Unicode letters and digits both count). This blocks
    left-embedding -- ``gymnasial`` in ``eftergymnasial``, ``male`` in ``female``,
    ``0 timmar`` in ``40 timmar`` -- while keeping compound *modifiers*
    (``högskole`` in ``högskoleexamen``);
  * ``word``: ``prefix`` plus the character after the match must not be
    alphanumeric.

  The boundary is only checked on a side of the token that is itself alphanumeric,
  so a token written with a leading space or punctuation keeps its literal meaning.
  A single token may override the side's mode by being written as an object,
  ``{"token": "lön", "mode": "substring"}`` -- the opt-in for compound *heads*
  (``månadslön``), which are legitimately matched mid-word.
- ``negation`` -- ``null`` (off) or a cue window. A token occurrence is discarded
  when one of ``cues`` is among the ``window`` words immediately before it inside
  the same clause (clauses split on ``clause_breaks``: punctuation literally, word
  entries on word boundaries). Only the text *before* an occurrence is examined, so
  a token that itself begins with a cue (``never married``) still hits. Negation
  applies to ``contains``, every ``all_of`` member and ``none_of`` (a negated veto
  does not veto); it does not apply to ``equals``, which compares whole strings.
- ``tie_break`` -- an ordered list of criteria resolving several values that hit in
  the same tier: ``longest`` (longest matched token; for ``all_of`` the summed
  length of every group's best token) and ``priority`` (position in the
  attribute's ``priority`` list). The list must end with ``priority``, the only
  total order, so every tie resolves deterministically.

Resolution model
----------------
:func:`resolve` matches ``values`` with a **global tiered sweep**: one tier is swept
across *all* values before the next is tried, so a later value's ``equals`` beats an
earlier value's ``contains``. Within the winning tier every hitting value is
collected and ``tie_break`` picks one; :func:`resolve_traced` reports the
candidates and the deciding criterion (the synthetic mapper writes every multi-hit
to the ``{slug}.ties.csv`` sidecar). A total miss yields the ``UNMAPPED`` sentinel
(or the attribute-level ``on_miss`` literal, when one is declared).

Tier order (``none_of`` vetoes its value in every tier, except the value's
self-contained ``all_of_rules``, which carry their own ``none_of``):

1. ``equals`` — exact match: the normalized+stripped raw equals a normalized token.
2. ``all_of`` — AND-of-ORs: the raw contains at least one token from *every* group.
   ``all_of_rules`` hit in this same tier (see below).
3. ``contains`` — the raw contains any token.
4. ``int`` / ``int_gte`` — numeric: ``int(raw)`` is in the list / ``>=`` the bound.

``all_of_rules`` -- a list of **self-contained** conjunctive rules on one value,
each ``{"all_of": [[...], ...], "none_of": [...]}`` (``none_of`` optional). A rule
hits when every one of its groups hits and none of *its own* ``none_of`` tokens
does; the value-level ``none_of`` does **not** apply to it, so a rule is the one
place a value can be reached past its own veto. It exists for a narrow exception
that a value-wide veto cannot express ("a status word normally vetoes this value,
except when the same text also states current paid work, unless that work is
said to be over"): the rule states the exception and every veto it still needs,
in full, in one place. Its score is the summed length of its groups' best tokens,
exactly like ``all_of``, and it competes in the ``all_of`` tier::

    "Permanent Full-time": {
      "none_of": ["pension", ...],
      "all_of_rules": [{"all_of": [["pension"], ["timmar", "anställ"]],
                        "none_of": ["tidigare", "deltid", ...]}]
    }

A **composite** matcher (used by ``employment_type`` real, whose raw record has
``attachment`` + ``hours`` sub-fields) keys sub-fields of a dict raw value instead
of the reserved matcher keys above; every sub-field matcher must hit. Sub-field
names must be declared in the side's ``subfields`` directive -- any other
non-matcher key raises, so a typo (``"contain"``) can never be read as a sub-field::

    "subfields": ["attachment", "hours"],
    "Permanent Full-time": {
      "attachment": {"contains": ["permanent employees"]},
      "hours":      {"contains": ["35+ hours"]}
    }

Composite values are swept in their own pass after the scalar tiers, in
``priority`` order (composite and scalar values never coexist within one attribute
side, so the pass order is moot).

Attribute-level directives (reserved keys on the ``real`` / ``synthetic`` block,
never confused with value keys because the walk is driven by ``values``):

- ``absent`` — literal value emitted when the raw input is missing/empty
  (e.g. ``"Not Applicable"``); replaces the old ``reference_none_default``.
- ``refine_from`` — cross-field: when the primary raw walk misses, re-run the walk
  against a second attribute's already-resolved value (passed as ``refine_value``);
  replaces the old ``cross_field_coded`` handler.
- ``on_miss`` — literal default when everything misses. When omitted, a total miss
  defaults to the explicit ``UNMAPPED`` sentinel (``"__UNMAPPED__"``), not a bare
  ``None``.
- ``subfields`` — the composite sub-field names this side's matchers may key.
- ``tie_break`` — per-attribute override of the side's ``tie_break`` (e.g. the
  SCB BAS hierarchy for ``employment_status`` is ``["priority"]`` only).
- ``negation`` — ``null`` opts this attribute out of the side's negation
  (e.g. ``non-binary``, ``non-EU``); no other value is accepted.
- ``numeric_facet`` — a post-walk re-banding of the walked value from a number
  stated in the raw text (synthetic ``employment_type``: weekly hours or a
  percentage of a full-time week re-banded to the AKU agreed-hours bands)::

      "numeric_facet": {
        "extract": [{"pattern": "<regex, group 1 = number, optional group 2 = range end>",
                     "scale": 1.0}, ...],
        "ambiguous_if_preceded_by": ["över", "under", "<", ...],
        "bands": [{"name": "short", "gte": 1, "lt": 20}, {"name": "full", "gte": 35}],
        "remap": {"Permanent Full-time": {"short": "Permanent Short Part-time", ...}}
      }

  The facet runs after the primary walk. When the walked value is a ``remap`` key
  and every extracted number (both ends of a range) falls in one band, the value
  becomes ``remap[value][band]``. A number preceded by a comparator, or numbers
  spanning several bands, leave the walked value unchanged and are reported as
  ``facet_ambiguous``. A number in no band (``0 timmar``) never overrides.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

from population_synthetic.analysis.mapping.synthetic_mapper._text_helpers import (
    _fold_unicode_punctuation,
    _repair_utf8_double_encoding,
)
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED, is_unmapped

# ---------------------------------------------------------------------------
# Reserved keys and vocabularies
# ---------------------------------------------------------------------------

#: Matcher keys recognised inside a per-value matcher block. Any other key must be
#: a sub-field declared in the side's ``subfields`` directive (composite matcher).
_MATCHER_KEYS: frozenset[str] = frozenset(
    {"equals", "contains", "all_of", "all_of_rules", "none_of", "int", "int_gte"}
)

#: Attribute-level directive keys on a ``real`` / ``synthetic`` rules block.
#: These are never treated as values (the value-walk is driven by ``values``).
_DIRECTIVE_KEYS: frozenset[str] = frozenset(
    {"absent", "refine_from", "on_miss", "subfields", "tie_break", "negation", "numeric_facet"}
)

#: Scalar matcher tiers, swept in this order globally across all values.
_SCALAR_TIERS: tuple[str, ...] = ("equals", "all_of", "contains", "numeric")

#: Token boundary modes (see the module docstring).
TOKEN_MODES: frozenset[str] = frozenset({"substring", "prefix", "word"})

#: Tie-break criteria; a ``tie_break`` list must end with ``"priority"``.
TIE_CRITERIA: frozenset[str] = frozenset({"longest", "priority"})

#: The two rule sides every ``matching`` block declares.
SIDES: tuple[str, ...] = ("real", "synthetic")

#: Keys of one side's ``matching`` block, all required.
_MATCHING_KEYS: frozenset[str] = frozenset({"token_mode", "negation", "tie_break"})
_NEGATION_KEYS: frozenset[str] = frozenset({"cues", "window", "clause_breaks"})
_TOKEN_OBJECT_KEYS: frozenset[str] = frozenset({"token", "mode"})
_FACET_KEYS: frozenset[str] = frozenset({"extract", "ambiguous_if_preceded_by", "bands", "remap"})
_RULE_KEYS: frozenset[str] = frozenset({"all_of", "none_of"})

_UNDERSCORE_RE = re.compile(r"_")
_WORD_RE = re.compile(r"\w+")


class MappingConfigError(ValueError):
    """Raised for a missing or malformed mapping config (fail-fast, never defaulted)."""


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize(value: Any) -> str:
    """Normalize a raw value to the canonical matching form.

    Repairs double-encoded UTF-8 (mirroring the synthetic mapper's record-level
    repair), folds typographic punctuation to ASCII, lowercases, and collapses
    underscores to spaces. Hyphens are **preserved** and the result is **not**
    stripped -- matching the behaviour of the retired ``_kw_norm`` keyword-rule
    normaliser, so order-sensitive distinctions (``upper-secondary`` vs
    ``upper secondary``) and leading-space tokens (``" city"``) survive substring
    tests. ``equals`` comparisons strip both sides separately.

    Both the raw value and every config token pass through here, so the punctuation
    fold is symmetric: a token written with an ASCII hyphen matches raw output using
    a non-breaking hyphen (U+2011) or an en dash, and vice versa. The fold runs
    *after* the UTF-8 repair by construction -- see ``_UNICODE_PUNCTUATION_FOLDS``.
    """
    text = "" if value is None else str(value)
    text = _fold_unicode_punctuation(_repair_utf8_double_encoding(text))
    return _UNDERSCORE_RE.sub(" ", text.lower())


@lru_cache(maxsize=65536)
def _norm_token(token: str) -> str:
    """Cached :func:`normalize` for config tokens (the same few thousand strings recur)."""
    return normalize(token)


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
# Compiled matching options
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Negation:
    """A compiled negation cue window (see the module docstring)."""

    cues: frozenset[str]
    window: int
    clause_re: re.Pattern


@dataclass(frozen=True)
class Matching:
    """Compiled matching options for one side (``_index.json`` ``matching.<side>``)."""

    token_mode: str
    negation: Negation | None
    tie_break: tuple[str, ...]


@dataclass(frozen=True)
class _Band:
    name: str
    gte: float
    lt: float


@dataclass(frozen=True)
class NumericFacet:
    """A compiled ``numeric_facet`` directive."""

    extract: tuple[tuple[re.Pattern, float], ...]
    ambiguous_re: re.Pattern | None
    bands: tuple[_Band, ...]
    remap: dict[str, dict[str, str]]


def _fail(where: str, message: str) -> None:
    raise MappingConfigError(f"{where}: {message}")


def _compile_negation(spec: Any, where: str) -> Negation | None:
    if spec is None:
        return None
    if not isinstance(spec, dict):
        _fail(where, f"'negation' must be null or an object, got {type(spec).__name__}")
    keys = set(spec)
    if keys != _NEGATION_KEYS:
        _fail(where, f"'negation' must declare exactly {sorted(_NEGATION_KEYS)}, got {sorted(keys)}")
    cues = spec["cues"]
    if not isinstance(cues, list) or not cues:
        _fail(where, "'negation.cues' must be a non-empty list")
    norm_cues = []
    for cue in cues:
        if not isinstance(cue, str) or not _WORD_RE.fullmatch(normalize(cue)):
            _fail(where, f"negation cue {cue!r} must be a single word")
        norm_cues.append(normalize(cue))
    window = spec["window"]
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        _fail(where, f"'negation.window' must be a positive integer, got {window!r}")
    breaks = spec["clause_breaks"]
    if not isinstance(breaks, list) or not breaks:
        _fail(where, "'negation.clause_breaks' must be a non-empty list")
    parts = []
    for brk in breaks:
        if not isinstance(brk, str) or brk == "":
            _fail(where, f"clause break {brk!r} must be a non-empty string")
        nb = normalize(brk)
        parts.append(rf"\b{re.escape(nb)}\b" if _WORD_RE.fullmatch(nb) else re.escape(nb))
    return Negation(frozenset(norm_cues), window, re.compile("|".join(parts)))


def _validate_tie_break(spec: Any, where: str) -> tuple[str, ...]:
    if not isinstance(spec, list) or not spec:
        _fail(where, f"'tie_break' must be a non-empty list, got {spec!r}")
    for crit in spec:
        if crit not in TIE_CRITERIA:
            _fail(where, f"unknown tie_break criterion {crit!r} (allowed: {sorted(TIE_CRITERIA)})")
    if len(set(spec)) != len(spec):
        _fail(where, f"'tie_break' repeats a criterion: {spec!r}")
    if spec[-1] != "priority":
        _fail(where, f"'tie_break' must end with 'priority' (the only total order), got {spec!r}")
    return tuple(spec)


def compile_matching(spec: Any, where: str = "matching") -> Matching:
    """Validate and compile one side's ``matching`` block. Raises on any defect."""
    if not isinstance(spec, dict):
        _fail(where, f"matching block must be an object, got {type(spec).__name__}")
    keys = set(spec)
    if keys != _MATCHING_KEYS:
        _fail(where, f"matching block must declare exactly {sorted(_MATCHING_KEYS)}, got {sorted(keys)}")
    mode = spec["token_mode"]
    if mode not in TOKEN_MODES:
        _fail(where, f"unknown token_mode {mode!r} (allowed: {sorted(TOKEN_MODES)})")
    return Matching(
        token_mode=mode,
        negation=_compile_negation(spec["negation"], where),
        tie_break=_validate_tie_break(spec["tie_break"], where),
    )


def _as_matching(matching: Matching | dict) -> Matching:
    return matching if isinstance(matching, Matching) else compile_matching(matching)


def _effective_matching(matching: Matching, rules_block: dict) -> Matching:
    """Apply the attribute-level ``tie_break`` / ``negation`` overrides to *matching*."""
    eff = matching
    if "tie_break" in rules_block:
        eff = replace(eff, tie_break=tuple(rules_block["tie_break"]))
    if "negation" in rules_block:
        eff = replace(eff, negation=None)
    return eff


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def _validate_token(tok: Any, where: str, *, allow_object: bool) -> None:
    if isinstance(tok, str):
        if normalize(tok) == "":
            _fail(where, "empty token")
        return
    if allow_object and isinstance(tok, dict):
        if set(tok) != _TOKEN_OBJECT_KEYS:
            _fail(where, f"token object must declare exactly {sorted(_TOKEN_OBJECT_KEYS)}, got {sorted(tok)}")
        if not isinstance(tok["token"], str) or normalize(tok["token"]) == "":
            _fail(where, f"token object needs a non-empty string 'token', got {tok['token']!r}")
        if tok["mode"] not in TOKEN_MODES:
            _fail(where, f"unknown token mode {tok['mode']!r} (allowed: {sorted(TOKEN_MODES)})")
        return
    kind = "a string or a {token, mode} object" if allow_object else "a string"
    _fail(where, f"token must be {kind}, got {tok!r}")


def _validate_token_list(value: Any, where: str, *, allow_object: bool) -> None:
    if not isinstance(value, list):
        _fail(where, f"must be a list, got {type(value).__name__}")
    for tok in value:
        _validate_token(tok, where, allow_object=allow_object)


def _validate_all_of(spec: Any, where: str) -> None:
    if not isinstance(spec, list) or not spec:
        _fail(where, "must be a non-empty list of token groups")
    for group in spec:
        if not isinstance(group, list) or not group:
            _fail(where, "every all_of group must be a non-empty list")
        _validate_token_list(group, where, allow_object=True)


def _validate_matcher(matcher: Any, where: str, subfields: frozenset[str]) -> None:
    if not isinstance(matcher, dict) or not matcher:
        _fail(where, "matcher must be a non-empty object")
    for key, spec in matcher.items():
        kwhere = f"{where}.{key}"
        if key in ("equals",):
            _validate_token_list(spec, kwhere, allow_object=False)
        elif key in ("contains", "none_of"):
            _validate_token_list(spec, kwhere, allow_object=True)
        elif key == "all_of":
            _validate_all_of(spec, kwhere)
        elif key == "all_of_rules":
            if not isinstance(spec, list) or not spec:
                _fail(kwhere, "must be a non-empty list of {all_of, none_of} rules")
            for i, rule in enumerate(spec):
                rwhere = f"{kwhere}[{i}]"
                if not isinstance(rule, dict) or "all_of" not in rule or not set(rule) <= _RULE_KEYS:
                    _fail(rwhere, f"a rule must declare 'all_of' and optionally 'none_of', got {rule!r}")
                _validate_all_of(rule["all_of"], f"{rwhere}.all_of")
                if "none_of" in rule:
                    _validate_token_list(rule["none_of"], f"{rwhere}.none_of", allow_object=True)
        elif key == "int":
            if not isinstance(spec, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in spec):
                _fail(kwhere, "must be a list of integers")
        elif key == "int_gte":
            if isinstance(spec, bool) or not isinstance(spec, int):
                _fail(kwhere, "must be an integer")
        elif key in subfields:
            if not isinstance(spec, dict):
                _fail(kwhere, "sub-field matcher must be an object")
            _validate_matcher(spec, kwhere, frozenset())
        else:
            _fail(kwhere, f"unknown matcher key {key!r} (allowed: {sorted(_MATCHER_KEYS)}"
                          f"{' + subfields ' + str(sorted(subfields)) if subfields else ''})")


def _compile_facet(spec: Any, where: str, values: list[str]) -> NumericFacet:
    if not isinstance(spec, dict) or set(spec) != _FACET_KEYS:
        _fail(where, f"numeric_facet must declare exactly {sorted(_FACET_KEYS)}")
    extract = spec["extract"]
    if not isinstance(extract, list) or not extract:
        _fail(where, "numeric_facet.extract must be a non-empty list")
    compiled_extract = []
    for ex in extract:
        if not isinstance(ex, dict) or set(ex) != {"pattern", "scale"}:
            _fail(where, "every numeric_facet.extract entry must declare exactly ['pattern', 'scale']")
        try:
            pat = re.compile(ex["pattern"])
        except (re.error, TypeError) as exc:
            _fail(where, f"numeric_facet pattern {ex['pattern']!r} does not compile: {exc}")
        if pat.groups < 1:
            _fail(where, f"numeric_facet pattern {ex['pattern']!r} needs a capture group for the number")
        scale = ex["scale"]
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale <= 0:
            _fail(where, f"numeric_facet scale must be a positive number, got {scale!r}")
        compiled_extract.append((pat, float(scale)))
    amb = spec["ambiguous_if_preceded_by"]
    if not isinstance(amb, list) or not all(isinstance(a, str) and a for a in amb):
        _fail(where, "numeric_facet.ambiguous_if_preceded_by must be a list of non-empty strings")
    amb_re = re.compile("(?:" + "|".join(re.escape(normalize(a)) for a in amb) + r")\s*$") if amb else None
    bands_spec = spec["bands"]
    if not isinstance(bands_spec, list) or not bands_spec:
        _fail(where, "numeric_facet.bands must be a non-empty list")
    bands = []
    for b in bands_spec:
        if not isinstance(b, dict) or not {"name", "gte"} <= set(b) or not set(b) <= {"name", "gte", "lt"}:
            _fail(where, f"band {b!r} must declare 'name', 'gte' and optionally 'lt'")
        lo, hi = b["gte"], b.get("lt", math.inf)
        if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)) or lo >= hi:
            _fail(where, f"band {b['name']!r} needs numeric gte < lt")
        bands.append(_Band(str(b["name"]), float(lo), float(hi)))
    names = [b.name for b in bands]
    if len(set(names)) != len(names):
        _fail(where, f"numeric_facet band names repeat: {names}")
    ordered = sorted(bands, key=lambda b: b.gte)
    for left, right in zip(ordered, ordered[1:]):
        if left.lt > right.gte:
            _fail(where, f"numeric_facet bands {left.name!r} and {right.name!r} overlap")
    remap = spec["remap"]
    if not isinstance(remap, dict) or not remap:
        _fail(where, "numeric_facet.remap must be a non-empty object")
    for src, targets in remap.items():
        if src not in values:
            _fail(where, f"numeric_facet.remap key {src!r} is not one of values")
        if not isinstance(targets, dict) or set(targets) != set(names):
            _fail(where, f"numeric_facet.remap[{src!r}] must map every band {names} to a value")
        for band, target in targets.items():
            if target not in values:
                _fail(where, f"numeric_facet.remap[{src!r}][{band!r}] target {target!r} is not one of values")
    return NumericFacet(tuple(compiled_extract), amb_re, tuple(bands), {k: dict(v) for k, v in remap.items()})


def validate_rules(rules_block: Any, values: list[str], where: str) -> None:
    """Validate one ``real`` / ``synthetic`` rules block against its ``values``. Raises on any defect."""
    if not isinstance(rules_block, dict):
        _fail(where, "rules block must be an object")
    subfields_spec = rules_block.get("subfields", [])
    if not isinstance(subfields_spec, list) or not all(isinstance(s, str) and s for s in subfields_spec):
        _fail(where, "'subfields' must be a list of sub-field names")
    subfields = frozenset(subfields_spec)
    clash = subfields & _MATCHER_KEYS
    if clash:
        _fail(where, f"'subfields' may not reuse matcher keys {sorted(clash)}")
    for key, spec in rules_block.items():
        kwhere = f"{where}.{key}"
        if key in values:
            _validate_matcher(spec, kwhere, subfields)
        elif key in ("absent", "on_miss"):
            if not isinstance(spec, str):
                _fail(kwhere, "must be a string literal")
        elif key == "refine_from":
            if not isinstance(spec, str) or not spec:
                _fail(kwhere, "must name a sibling attribute")
        elif key == "subfields":
            continue
        elif key == "tie_break":
            _validate_tie_break(spec, kwhere)
        elif key == "negation":
            if spec is not None:
                _fail(kwhere, "an attribute may only opt out of negation (null); cues live in _index.json")
        elif key == "numeric_facet":
            _compile_facet(spec, kwhere, values)
        else:
            _fail(kwhere, f"unknown key {key!r}: neither one of values nor a directive {sorted(_DIRECTIVE_KEYS)}")


def validate_priority(block: dict, where: str) -> list[str]:
    """Return the attribute file's ``priority`` list, raising unless it permutes ``values``."""
    values = block.get("values")
    if not isinstance(values, list) or not values:
        _fail(where, "'values' must be a non-empty list")
    if len(set(values)) != len(values):
        _fail(where, "'values' repeats an entry")
    priority = block.get("priority")
    if not isinstance(priority, list):
        _fail(where, "'priority' list is required (a permutation of 'values')")
    if len(priority) != len(values) or set(priority) != set(values):
        _fail(where, f"'priority' must be a permutation of 'values'; got {priority!r} for {values!r}")
    return priority


def validate_mappings(mappings: dict, where: str = "mapping config") -> dict[str, Matching]:
    """Validate a merged mapping directory and return its compiled ``matching`` per side.

    Checks the ``_index.json`` ``matching`` block (both sides required), every
    attribute file the index lists (``values`` + ``priority``), and every rules
    block those files carry. Raises :class:`MappingConfigError` on the first defect.
    """
    index = mappings.get("_index")
    if not isinstance(index, dict) or not isinstance(index.get("attributes"), dict):
        _fail(where, "'_index' block declaring 'attributes' is required")
    matching_spec = index.get("matching")
    if not isinstance(matching_spec, dict):
        _fail(f"{where} _index", "'matching' block is required (no in-code default)")
    if set(matching_spec) != set(SIDES):
        _fail(f"{where} _index.matching", f"must declare exactly {list(SIDES)}, got {sorted(matching_spec)}")
    compiled = {side: compile_matching(matching_spec[side], f"{where} _index.matching.{side}") for side in SIDES}
    for attr, filename in index["attributes"].items():
        stem = filename[:-5] if filename.endswith(".json") else filename
        block = mappings.get(stem)
        fwhere = f"{where} {stem} ({attr})"
        if not isinstance(block, dict):
            _fail(fwhere, "attribute config file is missing")
        validate_priority(block, fwhere)
        for side in SIDES:
            if side in block:
                validate_rules(block[side], block["values"], f"{fwhere}.{side}")
    return compiled


# ---------------------------------------------------------------------------
# Token matching primitives
# ---------------------------------------------------------------------------

def _occurrences(text: str, tok: str, mode: str):
    """Yield start offsets of *tok* in *text* satisfying the boundary *mode*."""
    start = 0
    check_left = mode != "substring" and tok[0].isalnum()
    check_right = mode == "word" and tok[-1].isalnum()
    while True:
        i = text.find(tok, start)
        if i < 0:
            return
        start = i + 1
        if check_left and i > 0 and text[i - 1].isalnum():
            continue
        if check_right:
            j = i + len(tok)
            if j < len(text) and text[j].isalnum():
                continue
        yield i


def _negated(text: str, i: int, negation: Negation | None) -> bool:
    """True when a negation cue sits in the ``window`` words before offset *i*, same clause."""
    if negation is None:
        return False
    before = text[:i]
    last = None
    for last in negation.clause_re.finditer(before):
        pass
    if last is not None:
        before = before[last.end():]
    words = _WORD_RE.findall(before)
    return any(w in negation.cues for w in words[-negation.window:])


def _token_hit(text: str, tok: Any, matching: Matching) -> int:
    """Matched length (> 0) of *tok* in normalized *text* under *matching*, else 0."""
    if isinstance(tok, dict):
        t, mode = _norm_token(tok["token"]), tok["mode"]
    else:
        t, mode = _norm_token(tok), matching.token_mode
    if not t:
        return 0
    score = len(t.strip()) or len(t)
    if mode == "substring" and matching.negation is None:
        return score if t in text else 0
    for i in _occurrences(text, t, mode):
        if not _negated(text, i, matching.negation):
            return score
    return 0


def _token_label(tok: Any) -> str:
    return tok["token"] if isinstance(tok, dict) else str(tok)


def _best_token(text: str, tokens: list, matching: Matching) -> tuple[int, str]:
    """(length, token) of the longest-hitting token in *tokens* (first on equal length)."""
    best_len, best_tok = 0, ""
    for tok in tokens:
        n = _token_hit(text, tok, matching)
        if n > best_len:
            best_len, best_tok = n, _token_label(tok)
    return best_len, best_tok


# ---------------------------------------------------------------------------
# Matcher evaluators
# ---------------------------------------------------------------------------

def _is_composite(matcher: dict) -> bool:
    """A matcher is composite iff it declares a (validated) sub-field key."""
    return any(key not in _MATCHER_KEYS for key in matcher)


def _vetoed(text: str, matcher: dict, matching: Matching) -> bool:
    """True when the matcher's ``none_of`` veto is triggered (a negated veto token does not veto)."""
    none_of = matcher.get("none_of")
    if none_of:
        return any(_token_hit(text, tok, matching) for tok in none_of)
    return False


def _all_of_hit(text: str, groups: list, matching: Matching) -> tuple[int, str] | None:
    """``(summed length, joined tokens)`` when every group hits, else None."""
    total, toks = 0, []
    for group in groups:
        n, tok = _best_token(text, group, matching)
        if n == 0:
            return None
        total += n
        toks.append(tok)
    return total, "+".join(toks)


def _rules_hit(text: str, matcher: dict, matching: Matching) -> tuple[int, str] | None:
    """Best-scoring hit among *matcher*'s self-contained ``all_of_rules`` (own ``none_of`` only)."""
    best = None
    for rule in matcher.get("all_of_rules") or ():
        none_of = rule.get("none_of")
        if none_of and any(_token_hit(text, tok, matching) for tok in none_of):
            continue
        hit = _all_of_hit(text, rule["all_of"], matching)
        if hit is not None and (best is None or hit[0] > best[0]):
            best = (hit[0], "rule:" + hit[1])
    return best


def _tier_hit(raw: Any, text: str, matcher: dict, tier: str, matching: Matching) -> tuple[int, str] | None:
    """Evaluate one scalar *tier* of *matcher*: ``(score, token)`` on a hit, else None."""
    if tier == "equals":
        equals = matcher.get("equals")
        if equals is not None:
            stripped = text.strip()
            for tok in equals:
                if stripped == _norm_token(tok).strip():
                    return len(stripped), tok
        return None

    if tier == "all_of":
        all_of = matcher.get("all_of")
        if all_of is not None:
            return _all_of_hit(text, all_of, matching)
        return None

    if tier == "contains":
        contains = matcher.get("contains")
        if contains is not None:
            n, tok = _best_token(text, contains, matching)
            if n:
                return n, tok
        return None

    if tier == "numeric":
        raw_int = _to_int(raw)
        if raw_int is not None:
            int_list = matcher.get("int")
            if int_list is not None and raw_int in int_list:
                return 1, f"int:{raw_int}"
            int_gte = matcher.get("int_gte")
            if int_gte is not None and raw_int >= int_gte:
                return 1, f"int_gte:{int_gte}"
        return None

    return None


def _match_scalar(raw: Any, matcher: dict, matching: Matching) -> bool:
    """Evaluate a scalar matcher as a whole (any tier), honouring ``none_of``.

    Used for composite sub-field matchers, where the sub-field is a single matcher
    resolved in isolation. The top-level value-walk instead sweeps tiers globally.
    """
    text = normalize(raw)
    if _rules_hit(text, matcher, matching) is not None:
        return True
    if _vetoed(text, matcher, matching):
        return False
    return any(_tier_hit(raw, text, matcher, tier, matching) for tier in _SCALAR_TIERS)


def _match_composite(raw: Any, matcher: dict, matching: Matching) -> bool:
    """Evaluate a composite matcher: every sub-field's own matcher must hit.

    *raw* must be a dict of raw sub-fields (e.g. ``{"attachment": ..., "hours": ...}``);
    a non-dict raw can never satisfy a composite matcher.
    """
    if not isinstance(raw, dict):
        return False
    for subfield, sub_matcher in matcher.items():
        if not isinstance(sub_matcher, dict):
            return False
        if not _match_scalar(raw.get(subfield), sub_matcher, matching):
            return False
    return True


# ---------------------------------------------------------------------------
# Walk, tie-break and facet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    """One value that hit in the winning tier."""

    value: str
    score: int
    token: str


@dataclass(frozen=True)
class Resolution:
    """Full trace of one resolution (see :func:`resolve_traced`).

    ``tier`` is ``equals`` / ``all_of`` / ``contains`` / ``numeric`` / ``composite``
    (prefixed ``refine:`` when the hit came from the ``refine_from`` sibling),
    ``absent`` or ``miss``. ``candidates`` lists every value that hit in that tier
    (more than one = a tie) and ``criterion`` names the ``tie_break`` criterion
    that decided it (None without a tie). ``facet`` is None when no numeric facet
    applies, else ``"applied"`` / ``"ambiguous"`` / ``"none"`` with the bands seen.
    """

    value: str | None
    missed: bool
    tier: str
    token: str | None = None
    candidates: tuple[Candidate, ...] = ()
    criterion: str | None = None
    walked_value: str | None = None
    facet: str | None = None
    facet_bands: tuple[str, ...] = field(default=())


def _pick(cands: list[Candidate], tie_break: tuple[str, ...], rank: dict[str, int]) -> tuple[Candidate, str | None]:
    """Resolve *cands* by the ordered *tie_break* criteria; return (winner, deciding criterion)."""
    if len(cands) == 1:
        return cands[0], None

    def key(crit: str, c: Candidate) -> int:
        return -c.score if crit == "longest" else rank[c.value]

    remaining = cands
    for crit in tie_break:
        best = min(key(crit, c) for c in remaining)
        remaining = [c for c in remaining if key(crit, c) == best]
        if len(remaining) == 1:
            return remaining[0], crit
    raise AssertionError("tie_break ends with 'priority', which is a total order")  # pragma: no cover


def _walk(
    raw: Any, rules_block: dict, values: list[str], priority: list[str], matching: Matching
) -> tuple[str, Candidate, tuple[Candidate, ...], str | None] | None:
    """Global tiered sweep; returns ``(tier, winner, candidates, criterion)`` or None on a miss."""
    rank = {v: i for i, v in enumerate(priority)}
    text = normalize(raw)
    scalar = [(v, rules_block[v]) for v in values if isinstance(rules_block.get(v), dict)]
    scalar = [(v, m) for v, m in scalar if not _is_composite(m)]
    live = {v for v, m in scalar if not _vetoed(text, m, matching)}
    for tier in _SCALAR_TIERS:
        cands = []
        for value, matcher in scalar:
            hit = _tier_hit(raw, text, matcher, tier, matching) if value in live else None
            if tier == "all_of":
                rule = _rules_hit(text, matcher, matching)
                if rule is not None and (hit is None or rule[0] > hit[0]):
                    hit = rule
            if hit is not None:
                cands.append(Candidate(value, hit[0], hit[1]))
        if cands:
            winner, criterion = _pick(cands, matching.tie_break, rank)
            return tier, winner, tuple(cands), criterion

    for value in sorted(values, key=lambda v: rank[v]):
        matcher = rules_block.get(value)
        if not isinstance(matcher, dict) or not _is_composite(matcher):
            continue
        if _match_composite(raw, matcher, matching):
            cand = Candidate(value, 0, "composite")
            return "composite", cand, (cand,), None

    return None


_FACET_CACHE: dict[int, tuple[dict, NumericFacet]] = {}


def _compiled_facet(spec: dict, values: list[str]) -> NumericFacet:
    """Compile a facet spec once per spec object (config dicts live for the run)."""
    hit = _FACET_CACHE.get(id(spec))
    if hit is not None and hit[0] is spec:
        return hit[1]
    facet = _compile_facet(spec, "numeric_facet", values)
    _FACET_CACHE[id(spec)] = (spec, facet)
    return facet


def _facet_bands(text: str, facet: NumericFacet) -> tuple[set[str], bool]:
    """Bands of every stated number in *text*, and whether a comparator made it ambiguous."""
    bands: set[str] = set()
    ambiguous = False
    for pattern, scale in facet.extract:
        for m in pattern.finditer(text):
            if facet.ambiguous_re is not None and facet.ambiguous_re.search(text[: m.start()]):
                ambiguous = True
                continue
            for g in range(1, min(pattern.groups, 2) + 1):
                num = m.group(g)
                if not num:
                    continue
                h = float(num.replace(",", ".")) * scale
                for band in facet.bands:
                    if band.gte <= h < band.lt:
                        bands.add(band.name)
    return bands, ambiguous


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def resolve(
    raw_value: Any,
    rules_block: dict,
    values: list[str],
    *,
    matching: Matching | dict,
    priority: list[str],
    refine_value: str | None = None,
) -> str | None:
    """Resolve one raw input to a unified value using *rules_block*.

    Thin wrapper over :func:`resolve_traced` that returns the value only.

    Parameters
    ----------
    raw_value:
        The raw input for this attribute. A scalar (str/int/None) for simple and
        numeric attributes, or a dict of sub-fields for composite attributes
        (whose value matchers key those sub-fields).
    rules_block:
        The per-attribute ``real`` or ``synthetic`` block: unified value →
        matcher entries plus the optional attribute-level directives.
    values:
        The unified value set. The walk only ever considers keys present in this
        list, so directive keys never collide with value keys.
    matching:
        The side's compiled :class:`Matching` (or the raw ``_index.json``
        ``matching.<side>`` dict, compiled and validated on the fly).
    priority:
        The attribute's ``priority`` list (a permutation of *values*) consulted by
        the ``priority`` tie-break criterion.
    refine_value:
        The already-resolved value of the ``refine_from`` attribute, supplied by
        the caller. Only consulted when ``rules_block`` declares ``refine_from``
        and the primary walk misses.

    Returns
    -------
    The winning unified value, the ``absent`` literal (missing raw), or the
    total-miss default: the attribute's ``on_miss`` literal when declared, else the
    ``UNMAPPED`` sentinel (``"__UNMAPPED__"``).
    """
    return resolve_traced(
        raw_value, rules_block, values, matching=matching, priority=priority, refine_value=refine_value
    ).value


def resolve_detailed(
    raw_value: Any,
    rules_block: dict,
    values: list[str],
    *,
    matching: Matching | dict,
    priority: list[str],
    refine_value: str | None = None,
) -> tuple[str | None, bool]:
    """Resolve as :func:`resolve` does, and report whether it was a total miss.

    Returns ``(value, missed)``. ``missed`` is True exactly when the primary walk
    and the optional ``refine_from`` walk both failed -- i.e. when the returned
    value is the total-miss default rather than a matched one.

    The flag exists because ``missed`` is **not** recoverable from the value alone:
    an attribute declaring ``on_miss`` returns a legitimate-looking category on a
    total miss, so miss-mass would otherwise be silently folded into that category
    and be invisible to ``validate_mapped``. A raw value satisfying a declared
    ``absent`` directive is a declared outcome, not a miss, and reports ``False``.
    """
    res = resolve_traced(
        raw_value, rules_block, values, matching=matching, priority=priority, refine_value=refine_value
    )
    return res.value, res.missed


def resolve_traced(
    raw_value: Any,
    rules_block: dict,
    values: list[str],
    *,
    matching: Matching | dict,
    priority: list[str],
    refine_value: str | None = None,
) -> Resolution:
    """Resolve and return the full :class:`Resolution` trace (tier, candidates, tie criterion, facet)."""
    eff = _effective_matching(_as_matching(matching), rules_block)
    absent = rules_block.get("absent")
    # Default a total miss to the explicit UNMAPPED sentinel (not a bare None), so a
    # "mapped, but nothing matched" outcome is legible downstream.
    on_miss = rules_block.get("on_miss", UNMAPPED)
    refine_from = rules_block.get("refine_from")

    # Absent input -> the declared literal. When no ``absent`` is declared, an empty
    # primary still falls through so a ``refine_from`` attribute can resolve from
    # its sibling field.
    if _is_absent(raw_value) and absent is not None:
        return Resolution(absent, False, "absent")

    # 1. Primary walk against the raw input, then the optional numeric facet.
    hit = _walk(raw_value, rules_block, values, priority, eff)
    if hit is not None:
        tier, winner, cands, criterion = hit
        value, facet_state, bands = winner.value, None, ()
        facet_spec = rules_block.get("numeric_facet")
        if facet_spec is not None and winner.value in facet_spec["remap"]:
            facet = _compiled_facet(facet_spec, values)
            seen, ambiguous = _facet_bands(normalize(raw_value), facet)
            bands = tuple(sorted(seen))
            if ambiguous or len(seen) > 1:
                facet_state = "ambiguous"
            elif len(seen) == 1:
                facet_state = "applied"
                value = facet.remap[winner.value][bands[0]]
            else:
                facet_state = "none"
        return Resolution(value, False, tier, winner.token, cands, criterion, winner.value, facet_state, bands)

    # 2. refine_from: re-run the same walk against the sibling's resolved value. An
    #    unmapped sibling carries no canonical value to refine from, so it is skipped.
    if refine_from and not is_unmapped(refine_value) and not _is_absent(refine_value):
        hit = _walk(refine_value, rules_block, values, priority, eff)
        if hit is not None:
            tier, winner, cands, criterion = hit
            return Resolution(winner.value, False, f"refine:{tier}", winner.token, cands, criterion, winner.value)

    # 3. Total miss -> the on_miss literal (default: the UNMAPPED sentinel).
    return Resolution(on_miss, True, "miss")

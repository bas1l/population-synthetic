"""Abstract and base synthetic-population mappers.

The *synthetic mapper* turns one raw pipeline ``identity.json`` record (free-text
attribute values produced by an LLM) into the canonical schema dict the
``StatisticalEvaluator`` consumes.

``AbstractSyntheticMapper`` is a pure contract: it declares the per-country class
attribute (``MAPPINGS_SUBDIR``) and the ``map_individual`` method, and knows
nothing about which demographic fields exist or how any of them is coded.

``BaseSyntheticMapper`` is a **generic handler-kind engine**, the synthetic-side
mirror of ``reference_mapper/base.py``.  It discovers its field set at
construction by scanning the loaded mapping tables for blocks that self-declare a
``pipeline_handler`` key; the handler kind names a generic algorithm (never a
field), and the binding of field -> algorithm lives in the country mapping JSON
under ``config/mapping/{scb,istat}/``.  A block declaring a ``pipeline_attr``
emits under that schema key (resolving file-stem != schema-attribute, e.g.
``education`` -> ``education_level``).  Blocks without a ``pipeline_handler`` key
are ignored.  The engine fails fast: an unknown kind, or no field declaring a
handler at all, raises ``ValueError``.

The five handler kinds are:

- ``passthrough`` -- emit ``identity.get(attr)`` verbatim (e.g. ``id``).
- ``numeric_gate`` -- ``int(raw)`` or the private ``_SKIP`` sentinel on a
  missing/non-integer value, which makes ``map_individual`` return ``None``
  (the persona-skip gate, e.g. ``age``).
- ``text_coded`` -- ordered free-text -> canonical resolver.
- ``numeric_bucket`` -- int/str -> bucket label.
- ``cross_field_coded`` -- resolve a primary field via ``text_coded``, then
  refine it from a second field (e.g. ``birth_location`` refined by
  ``birth_country_detail``).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.normalizer import load_mappings
from population_synth.comparison.synthetic_mapper._text_helpers import (
    _fuzzy_match,
    _repair_utf8_double_encoding,
    _sep_norm,
)

logger = logging.getLogger(__name__)

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

#: Private sentinel returned by a gate handler to signal "skip this persona".
_SKIP = object()


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def is_flat_identity(identity: dict) -> bool:
    """Return True for the flat / configurable identity.json format."""
    return "age" in identity and not any(k.startswith("level_") for k in identity) and "narrative" not in identity


# ---------------------------------------------------------------------------
# Handler-kind factories
#
# Each factory shares the ``(attr, block, engine) -> Callable[[identity, unmapped], value]``
# signature.  It closes over the output schema attribute (``attr``) and that
# attribute's own mapping block (``block``); the produced handler reads the raw
# value from the identity and resolves it.  No factory names a field -- the
# algorithm name is the only identity it carries.
# ---------------------------------------------------------------------------

def _passthrough_handler(attr: str, block: dict, engine: BaseSyntheticMapper) -> Callable[[dict, list], Any]:
    """Emit the raw identity value for *attr* verbatim (e.g. ``id``)."""
    return lambda identity, unmapped: identity.get(attr)


def _numeric_gate_handler(attr: str, block: dict, engine: BaseSyntheticMapper) -> Callable[[dict, list], Any]:
    """``int(raw)`` or the ``_SKIP`` sentinel on a missing/non-integer value.

    A ``_SKIP`` return makes the orchestrator drop the whole persona, preserving
    the validity gate that skips personas with missing/non-integer age.
    """
    def handler(identity: dict, unmapped: list[str]) -> Any:
        raw = identity.get(attr)
        if raw is None:
            logger.warning("%s: missing %s -- skipping persona", engine._persona_id, attr)
            return _SKIP
        try:
            return int(raw)
        except (ValueError, TypeError):
            logger.warning("%s: non-integer %s %r -- skipping persona", engine._persona_id, attr, raw)
            return _SKIP

    return handler


def _kw_norm(text: str) -> str:
    """Lowercase + underscore->space, the form the legacy ``contains`` cascades match on.

    Mirrors the ``raw.lower().replace("_", " ")`` normalisation the ``_normalize_*``
    functions apply for substring tests.  Crucially it does **not** collapse
    hyphens to spaces (unlike the separator-normalised label lookup) -- so
    order-sensitive distinctions such as ``upper-secondary`` (ISCED 3A) vs ``upper
    secondary`` (ISCED 3C) survive -- and does **not** strip, so tokens that rely
    on a leading space (e.g. ``" city"``) keep it.
    """
    return text.lower().replace("_", " ")


def _compile_keyword_rules(block: dict) -> list[tuple]:
    """Pre-compile ``pipeline_keyword_rules`` to ``(kind, tokens, label)`` tuples.

    Each rule is one of: ``equals`` (the stripped, normalised raw equals any token
    -- mirroring ``match_common_sex``'s ``raw.lower().strip()``), ``contains`` (raw
    contains any token), or ``contains`` with ``all_of`` (raw contains at least one
    token from each inner group -- AND-of-ORs co-occurrence).  ``contains`` tokens
    keep leading/trailing spaces; ``equals`` tokens are stripped.
    """
    compiled: list[tuple] = []
    for rule in block.get("pipeline_keyword_rules", []) or []:
        label = rule["label"]
        none_of = [_kw_norm(t) for t in rule.get("none_of", [])]
        if "all_of" in rule:
            groups = [[_kw_norm(t) for t in grp] for grp in rule["all_of"]]
            compiled.append(("all_of", groups, none_of, label))
        elif rule["match"] == "equals":
            tokens = [_kw_norm(t).strip() for t in rule["any_of"]]
            compiled.append(("equals", tokens, none_of, label))
        else:
            tokens = [_kw_norm(t) for t in rule["any_of"]]
            compiled.append(("contains", tokens, none_of, label))
    return compiled


def _apply_keyword_rules(rules: list[tuple], norm_raw: str) -> str | None:
    """Return the label of the first matching rule (top-to-bottom), else ``None``.

    *norm_raw* is :func:`_kw_norm` of the raw value (not stripped); the ``equals``
    tier strips it before comparing so trailing/leading whitespace is ignored there.
    An optional ``none_of`` veto blocks a rule if any of its tokens is present
    (mirroring the guarded ``student`` -> Not Applicable test in employment_type).
    """
    norm_equals = norm_raw.strip()
    for kind, tokens, none_of, label in rules:
        if none_of and any(tok in norm_raw for tok in none_of):
            continue
        if kind == "equals":
            if norm_equals in tokens:
                return label
        elif kind == "contains":
            if any(tok in norm_raw for tok in tokens):
                return label
        elif kind == "all_of":
            if all(any(tok in norm_raw for tok in grp) for grp in tokens):
                return label
    return None


def _text_coded_handler(attr: str, block: dict, engine: BaseSyntheticMapper) -> Callable[[dict, list], Any]:
    """Ordered free-text -> canonical resolver.

    Resolution order: (1) exact membership in ``output_categories``
    (already-canonical passthrough, no double-mapping); (2) optional
    ``pipeline_passthrough_on_separator``; (3) ``pipeline_label_mappings`` lookup
    (separator-insensitive); (4) ordered ``pipeline_keyword_rules``; (5) substring
    ``_fuzzy_match`` against ``output_categories`` (gated by ``pipeline_fuzzy``,
    default true); (6) ``pipeline_on_miss`` policy -- ``"non_standard"`` (emit
    ``"Non-standard label"`` + record unmapped), ``"passthrough"`` (raw verbatim),
    ``"passthrough_or_nonstandard"`` (raw if non-empty else ``"Non-standard
    label"``), or any literal default string.
    """
    source_key: str = block.get("pipeline_source_key", attr)
    output_categories: list[str] = block.get("output_categories", []) or []
    separator: str | None = block.get("pipeline_passthrough_on_separator")
    empty_raw: str | None = block.get("pipeline_empty_raw")
    # Most attributes pass an already-canonical value through verbatim; SE
    # industry_sector is the exception -- its ampersand output forms are not keys
    # in its label map and don't fuzzy-match its slash aliases, so the legacy code
    # routes them to ``Other``.  Disabling membership reproduces that.
    use_membership: bool = block.get("pipeline_membership", True)
    label_lookup = {_sep_norm(k.lower()): v
                    for k, v in (block.get("pipeline_label_mappings", {}) or {}).items()}
    rules = _compile_keyword_rules(block)
    use_fuzzy: bool = block.get("pipeline_fuzzy", True)
    # The substring-fuzzy tier can target a list distinct from ``output_categories``
    # (e.g. the shared base parental resolver fuzzed against the 4 Swedish labels,
    # not Italy's 5-category output); defaults to ``output_categories``.
    fuzzy_categories: list[str] = block.get("pipeline_fuzzy_categories") or output_categories
    # When the fuzzy list holds non-canonical aliases (e.g. industry's slash forms),
    # re-map a fuzzy hit through ``pipeline_label_mappings`` to its canonical label,
    # mirroring the legacy ``_normalize_industry_sector(_fuzzy_match(...))`` two-step.
    fuzzy_relabel: bool = block.get("pipeline_fuzzy_relabel", False)
    on_miss: str = block.get("pipeline_on_miss", "non_standard")
    silent: bool = block.get("pipeline_silent_unmapped", False)

    def handler(identity: dict, unmapped: list[str]) -> Any:
        value = identity.get(source_key)
        raw = "" if value is None else str(value)
        if raw == "" and empty_raw is not None:
            # Mirror the legacy ``identity.get(attr) or "<default>"`` substitution
            # (e.g. region), so the absent-field placeholder flows through the
            # resolver instead of fuzzy-matching the empty string to a category.
            raw = empty_raw
        if use_membership and raw in output_categories:
            return raw
        if separator and separator in raw:
            return raw
        if raw:
            hit = label_lookup.get(_sep_norm(raw.lower()))
            if hit is not None:
                return hit
        rule_hit = _apply_keyword_rules(rules, _kw_norm(raw))
        if rule_hit is not None:
            return rule_hit
        if use_fuzzy:
            fuzzy = _fuzzy_match(raw, fuzzy_categories)
            if fuzzy is not None:
                if fuzzy_relabel:
                    return label_lookup.get(_sep_norm(fuzzy.lower()), fuzzy)
                return fuzzy
        if on_miss == "non_standard":
            if not silent:
                unmapped.append(f"{attr}={raw!r}")
            return "Non-standard label"
        if on_miss == "passthrough":
            return raw
        if on_miss == "passthrough_or_nonstandard":
            return raw if raw else "Non-standard label"
        return on_miss  # literal default label

    return handler


def _cross_field_coded_handler(attr: str, block: dict, engine: BaseSyntheticMapper) -> Callable[[dict, list], Any]:
    """Resolve a primary free-text field, then refine it from a second field.

    Two-field resolver (the synthetic-side counterpart of the reference
    ``composite`` handler) used by ``birth_location``:

    1. Run the standard ``text_coded`` resolution on ``pipeline_primary_field``
       (the block's own ``output_categories`` / ``pipeline_keyword_rules`` /
       fuzzy chain).  An empty primary value short-circuits to the miss sentinel
       (mirroring the legacy ``... if raw_birth else "Non-standard label"``), so
       it never fuzzy-matches the empty string to a category.
    2. Resolve ``pipeline_refine_from`` through *its own* registered handler
       (e.g. the ``birth_country_detail`` resolver).
    3. If the resolved detail equals ``pipeline_domestic_label`` -> force the
       primary to the domestic label (overrides any primary resolution).
    4. Else, when the primary resolution missed, map the detail through the
       ordered ``pipeline_refine_buckets`` keyword rules -- against the resolved
       label (``pipeline_refine_source: "resolved"``, the default) or the raw
       refine-from value (``"raw"``) -- falling back to ``pipeline_refine_default``
       when set, otherwise leaving the miss sentinel.

    All canonical labels (including ``"Nordic Country"``) come from config: the
    refinement buckets live in ``birth_location.json``'s ``pipeline_refine_buckets``,
    so the handler can emit every label the reference side produces.
    """
    primary_field: str = block["pipeline_primary_field"]
    refine_from: str = block["pipeline_refine_from"]
    domestic_label: str = block["pipeline_domestic_label"]
    refine_source: str = block.get("pipeline_refine_source", "resolved")
    refine_default: str | None = block.get("pipeline_refine_default")
    silent: bool = block.get("pipeline_silent_unmapped", False)
    miss = "Non-standard label"
    # The primary resolver is a native, silent ``text_coded`` over this very
    # block -- it consumes the same ``output_categories`` / keyword rules / fuzzy
    # config; the cross-field handler owns the unmapped accounting instead.
    primary_block = {
        **block,
        "pipeline_handler": "text_coded",
        "pipeline_attr": primary_field,
        "pipeline_source_key": primary_field,
        "pipeline_silent_unmapped": True,
        "pipeline_on_miss": "non_standard",
    }
    primary_resolver = _text_coded_handler(primary_field, primary_block, engine)
    # ``pipeline_refine_buckets`` is either a dict (exact, case-sensitive label
    # lookup -- mirrors the legacy ``if bcd in {<canonical labels>}`` membership)
    # or an ordered keyword-rule list (case-insensitive substring/equals -- mirrors
    # the legacy ``any(tok in raw.lower())`` token-set scan).
    buckets_cfg = block.get("pipeline_refine_buckets")
    refine_dict: dict | None = buckets_cfg if isinstance(buckets_cfg, dict) else None
    refine_rules = None if refine_dict is not None else _compile_keyword_rules(
        {"pipeline_keyword_rules": buckets_cfg or []})

    def handler(identity: dict, unmapped: list[str]) -> Any:
        raw_primary = identity.get(primary_field)
        raw_primary_str = "" if raw_primary is None else str(raw_primary)
        primary = miss if raw_primary_str == "" else primary_resolver(identity, [])

        detail_handler = engine._handlers.get(refine_from)
        detail = detail_handler(identity, []) if detail_handler is not None else None

        # Domestic override: an unambiguously-domestic detail wins over the
        # primary resolution (mirrors the legacy ``if bcd == <domestic>`` branch).
        if detail == domestic_label:
            return domestic_label
        if primary != miss:
            return primary

        # Primary missed -> refine from the detail field.
        refine_input = detail if refine_source == "resolved" else identity.get(refine_from)
        if refine_input not in (None, "", miss):
            if refine_dict is not None:
                refined = refine_dict.get(str(refine_input))
            else:
                refined = _apply_keyword_rules(refine_rules, str(refine_input).lower())
            if refined is not None:
                return refined
            if refine_default is not None:
                return refine_default

        if not silent:
            unmapped.append(f"{attr}={raw_primary_str!r}")
        return miss

    return handler


def _numeric_bucket_handler(attr: str, block: dict, engine: BaseSyntheticMapper) -> Callable[[dict, list], Any]:
    """int/str -> bucket label.

    When the block declares ``pipeline_numeric_buckets`` the bucketing is config-
    driven: an integer maps through ``pipeline_numeric_buckets`` (keyed by the
    decimal string), with ``pipeline_bucket_overflow`` (``{threshold, label}``)
    catching values at/above the threshold; an integer below every bucket falls
    back to the overflow label when ``pipeline_bucket_default == "overflow"`` and
    otherwise to its own decimal string.  A non-integer resolves by membership /
    ``_fuzzy_match`` against ``output_categories``.
    """
    buckets: dict[str, str] = block.get("pipeline_numeric_buckets", {}) or {}
    overflow: dict | None = block.get("pipeline_bucket_overflow")
    bucket_default: str | None = block.get("pipeline_bucket_default")
    output_categories: list[str] = block.get("output_categories", []) or []

    def handler(identity: dict, unmapped: list[str]) -> Any:
        raw = identity.get(attr)
        if isinstance(raw, int):
            key = str(raw)
            if key in buckets:
                return buckets[key]
            if overflow and raw >= overflow["threshold"]:
                return overflow["label"]
            if bucket_default == "overflow" and overflow:
                return overflow["label"]
            return key
        raw_str = str(raw or "")
        if raw_str in output_categories:
            return raw_str
        return _fuzzy_match(raw_str, output_categories) or "Non-standard label"

    return handler


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class AbstractSyntheticMapper(ABC):
    """Per-country contract for mapping a raw pipeline population to schema.

    A subclass supplies :data:`MAPPINGS_SUBDIR` (the mapping directory that drives
    the whole engine); the per-record orchestration lives entirely in
    :class:`BaseSyntheticMapper`.
    """

    #: Category-mappings sub-directory under ``config/mapping/`` (e.g. ``"scb"``).
    MAPPINGS_SUBDIR: ClassVar[str]

    @abstractmethod
    def map_individual(self, identity: dict[str, Any], persona_id: str) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Base implementation: generic handler-kind engine
# ---------------------------------------------------------------------------

class BaseSyntheticMapper(AbstractSyntheticMapper):
    """Shared, field-literal-free engine driven by the mapping tables.

    A country subclass supplies :data:`MAPPINGS_SUBDIR`; the field set is
    discovered at construction by scanning the loaded mappings for blocks that
    declare a ``pipeline_handler`` kind.
    """

    #: Library of generic handler kinds, keyed by algorithm name (never by field).
    #: Each value is a factory ``(attr, block, engine) -> Callable[[identity, unmapped], value]``.
    _HANDLER_KINDS: ClassVar[dict[str, Callable]] = {
        "passthrough": _passthrough_handler,
        "numeric_gate": _numeric_gate_handler,
        "text_coded": _text_coded_handler,
        "numeric_bucket": _numeric_bucket_handler,
        "cross_field_coded": _cross_field_coded_handler,
    }

    def __init__(self, mappings: dict | None = None) -> None:
        """Build the handler registry by scanning *mappings* for declared fields.

        Every block carrying a ``pipeline_handler`` key contributes one handler,
        bound to ``pipeline_attr`` (defaulting to the file stem).  Blocks without
        the key are skipped.  Fail fast on an unknown kind or a mapping set that
        declares no pipeline field at all.  When *mappings* is omitted the
        country's default ``config/mapping/{MAPPINGS_SUBDIR}`` directory is read.
        """
        if mappings is None:
            mappings = load_mappings(_MAPPINGS_ROOT / self.MAPPINGS_SUBDIR)
        self.mappings = mappings
        self._persona_id: str = "?"

        self._handlers: dict[str, Callable[[dict, list], Any]] = {}
        for stem, block in mappings.items():
            if not isinstance(block, dict) or "pipeline_handler" not in block:
                continue
            kind = block["pipeline_handler"]
            factory = self._HANDLER_KINDS.get(kind)
            if factory is None:
                raise ValueError(f"Unknown pipeline handler kind {kind!r} in {stem!r}")
            attr = block.get("pipeline_attr", stem)
            self._handlers[attr] = factory(attr, block, self)
        if not self._handlers:
            raise ValueError("synthetic mapper found no fields declaring 'pipeline_handler'")

    # -- orchestrator -------------------------------------------------------

    def map_individual(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        """Map a single raw identity dict to the canonical schema dict.

        Returns ``None`` for unrecognised formats or critically-incomplete
        personas.  Only the flat configurable identity format is supported;
        unrecognised formats (including legacy narrative dicts) are logged as a
        warning and skipped.
        """
        if not is_flat_identity(identity):
            logger.warning("%s: unrecognised identity format (keys: %s) -- skipping", persona_id, list(identity))
            return None
        return self._map_flat(identity, persona_id)

    def _map_flat(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        identity = {k: _repair_utf8_double_encoding(str(v)) if isinstance(v, str) else v
                    for k, v in identity.items()}
        # Inject the authoritative persona id so the ``passthrough`` id handler
        # emits it (the canonical schema carries ``id`` like the reference side).
        identity["id"] = persona_id
        self._persona_id = persona_id
        unmapped: list[str] = []

        result: dict[str, Any] = {}
        for attr, handler in self._handlers.items():
            value = handler(identity, unmapped)
            if value is _SKIP:
                return None
            result[attr] = value

        if unmapped:
            logger.warning("%s: unmapped flat fields: %s", persona_id, "; ".join(unmapped))
        return result

"""Abstract and base synthetic-population mappers.

The *synthetic mapper* turns one raw pipeline ``identity.json`` record (free-text
attribute values produced by an LLM) into the canonical schema dict the
``StatisticalEvaluator`` consumes.

``AbstractSyntheticMapper`` is a pure contract: it declares the per-country class
attribute (``MAPPINGS_SUBDIR``) and the ``map_individual`` method, and knows
nothing about which demographic fields exist or how any of them is coded.

``BaseSyntheticMapper`` is a **thin loader** over the shared symmetric resolver
(:mod:`population_synth.comparison.mapping_engine`), the synthetic-side mirror of
``reference_mapper/base.py``. It reads the per-country ``_index.json`` master
(``attribute -> config filename``, in axis order) plus each per-attribute config
file, and for every attribute delegates to :func:`mapping_engine.resolve`, passing
that file's ``synthetic`` rules block and ``values`` list. The old 5 handler-kind
factories are gone: every algorithm the pipeline side used (label lookup, ordered
keyword rules, numeric buckets, cross-field refinement) is now expressed as
matchers/directives in the ``synthetic`` block and evaluated by the shared engine.

Three responsibilities remain in the mapper itself:

- **Format gate** -- only the flat/configurable ``identity.json`` shape is
  supported; unrecognised formats (e.g. a legacy ``{"narrative": ...}`` blob) are
  logged as a warning and skipped (``map_individual`` returns ``None``).
- **UTF-8 repair** -- every string field has its double-encoded UTF-8 repaired
  once, record-level, before resolution.
- **Persona-skip age gate** -- a missing / non-integer ``age`` skips the whole
  persona; otherwise the raw integer ``age`` is emitted under the ``age`` key (the
  ``age_group`` comparison attribute is *derived* from it by
  ``evaluator.attr_value`` at scoring time). ``id`` is the injected persona id.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison import mapping_engine
from population_synth.comparison.reference_mapper.mappings import load_mappings
from population_synth.comparison.synthetic_mapper._text_helpers import _repair_utf8_double_encoding

logger = logging.getLogger(__name__)

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

#: Comparison attribute derived from the raw integer ``age`` at scoring time; the
#: mapper passes ``age`` through (behind the persona-skip gate) instead of resolving.
_AGE_GROUP_ATTR = "age_group"

#: Output / raw-identity key carrying the integer age.
_AGE_KEY = "age"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def is_flat_identity(identity: dict) -> bool:
    """Return True for the flat / configurable identity.json format."""
    return "age" in identity and not any(k.startswith("level_") for k in identity) and "narrative" not in identity


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
# Base implementation: thin loader over the shared resolver
# ---------------------------------------------------------------------------

class BaseSyntheticMapper(AbstractSyntheticMapper):
    """Shared, field-literal-free loader driven by the symmetric mapping config.

    A country subclass supplies :data:`MAPPINGS_SUBDIR`. The comparison attributes
    (in axis order) come from the ``_index.json`` master; each attribute's
    ``synthetic`` rules block and ``values`` list drive :func:`mapping_engine.resolve`.
    """

    def __init__(self, mappings: dict | None = None) -> None:
        """Bind the merged *mappings* dict and read its ``_index`` master.

        When *mappings* is omitted the country's default
        ``config/mapping/{MAPPINGS_SUBDIR}`` directory is read. Fails fast when no
        ``_index`` block with an ``attributes`` map is present.
        """
        if mappings is None:
            mappings = load_mappings(_MAPPINGS_ROOT / self.MAPPINGS_SUBDIR)
        self.mappings = mappings
        index = mappings.get("_index")
        if not isinstance(index, dict) or not isinstance(index.get("attributes"), dict):
            raise ValueError("synthetic mapper requires an '_index' block declaring 'attributes'")
        #: Ordered ``attribute -> config filename`` map (key order = axis order).
        self._attributes: dict[str, str] = index["attributes"]

    # -- config access ------------------------------------------------------

    def _block_for(self, attr: str) -> dict:
        """Return the per-attribute config block for *attr* (keyed by file stem)."""
        filename = self._attributes[attr]
        stem = filename[:-5] if filename.endswith(".json") else filename
        block = self.mappings.get(stem)
        if not isinstance(block, dict):
            raise ValueError(f"synthetic mapper: missing config block {stem!r} for attribute {attr!r}")
        return block

    # -- resolution ---------------------------------------------------------

    def _resolve_attr(self, attr: str, identity: dict, resolved: dict[str, Any]) -> Any:
        """Resolve one attribute against *identity*, memoising into *resolved*.

        Delegates to :func:`mapping_engine.resolve` with the attribute's
        ``synthetic`` block, resolving a ``refine_from`` sibling first when declared
        (e.g. ``birth_location`` refined from ``birth_country_detail``).
        """
        if attr in resolved:
            return resolved[attr]
        block = self._block_for(attr)
        rules_block = block["synthetic"]
        values = block["values"]
        raw = identity.get(attr)

        refine_value: str | None = None
        refine_from = rules_block.get("refine_from")
        if refine_from is not None:
            refine_value = self._resolve_attr(refine_from, identity, resolved)

        value = mapping_engine.resolve(raw, rules_block, values, refine_value=refine_value)
        resolved[attr] = value
        return value

    # -- orchestrator -------------------------------------------------------

    def map_individual(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        """Map a single raw identity dict to the canonical schema dict.

        Returns ``None`` for unrecognised formats (including legacy narrative dicts)
        and for critically-incomplete personas (missing/non-integer ``age``).
        """
        if not is_flat_identity(identity):
            logger.warning("%s: unrecognised identity format (keys: %s) -- skipping", persona_id, list(identity))
            return None
        return self._map_flat(identity, persona_id)

    def _map_flat(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        identity = {k: _repair_utf8_double_encoding(str(v)) if isinstance(v, str) else v
                    for k, v in identity.items()}

        # Persona-skip gate: a missing / non-integer age drops the whole persona.
        raw_age = identity.get(_AGE_KEY)
        try:
            age_int = int(raw_age)
        except (ValueError, TypeError):
            logger.warning("%s: missing/non-integer age %r -- skipping persona", persona_id, raw_age)
            return None

        resolved: dict[str, Any] = {}
        result: dict[str, Any] = {"id": persona_id}
        for attr in self._attributes:
            if attr == _AGE_GROUP_ATTR:
                result[_AGE_KEY] = age_int
                resolved[attr] = age_int
                continue
            result[attr] = self._resolve_attr(attr, identity, resolved)
        return result

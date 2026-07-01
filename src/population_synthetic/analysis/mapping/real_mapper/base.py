"""Abstract and base real-population mappers.

The *real mapper* turns one raw-format real record (nested
``RawCategory`` dicts produced by a national statistics API, e.g. SCB/ISTAT)
into the flat canonical schema dict the ``StatisticalEvaluator`` consumes.

``AbstractRealMapper`` is a pure contract: it declares the single per-country
class attribute (``MAPPINGS_SUBDIR``) and the ``normalize_individual`` method, and
knows nothing about which demographic fields exist or how any of them is coded.

``BaseRealMapper`` is a **thin loader** over the shared symmetric resolver
(:mod:`population_synthetic.analysis.mapping.mapping_engine`). It reads the per-country
``_index.json`` master (``attribute -> config filename``, in axis order) plus each
per-attribute config file, and for every attribute delegates to
:func:`mapping_engine.resolve`, passing that file's ``real`` rules block and
``values`` list. The old 5 handler-kind factories are gone: every algorithm the DB
side used (label lookup, composite attachment/hours, decile/substring codes) is now
expressed as matchers in the ``real`` block and evaluated by the shared engine.

Two responsibilities remain in the mapper itself:

- ``id`` passthrough -- ``id`` is not a comparison attribute (absent from the
  master), so it is copied straight from the record.
- ``age`` passthrough -- the ``age_group`` comparison attribute is *derived* from
  the raw integer ``age`` by ``evaluator.attr_value`` at scoring time, so the mapper
  emits the raw ``age`` under the ``age`` key rather than resolving it.

The mapper also flattens the raw record's nested ``RawCategory`` dicts to the
scalar (or, for the composite ``employment_type``, sub-field dict) the engine
consumes, and wires ``refine_from`` by resolving the named sibling attribute first
and passing its value as ``refine_value``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from population_synthetic.analysis.mapping import mapping_engine

#: Comparison attribute whose value is derived from the raw integer ``age`` at
#: scoring time; the mapper passes ``age`` through instead of resolving it.
_AGE_GROUP_ATTR = "age_group"

#: Output key carrying the raw integer age (what ``evaluator.attr_value`` bins).
_AGE_KEY = "age"

#: Keys that mark a raw dict as a single ``RawCategory`` (a coded value) rather than
#: a composite of sub-fields (e.g. ``employment_type``'s attachment/hours).
_RAW_CATEGORY_KEYS = ("label", "code", "decile")


# ---------------------------------------------------------------------------
# Raw-record extraction primitives
# ---------------------------------------------------------------------------

def _label(value: Any) -> Any:
    """Flatten a single ``RawCategory`` dict to its scalar label/code/decile.

    A plain scalar (or ``None``) passes through unchanged; a dict is read through
    its ``label`` -> ``code`` -> ``decile`` keys.
    """
    if isinstance(value, dict):
        return value.get("label") or value.get("code") or value.get("decile")
    return value


def _extract(raw: Any) -> Any:
    """Extract the engine-ready raw for one attribute from its record value.

    Scalars pass through. A single ``RawCategory`` dict (one carrying a
    ``label``/``code``/``decile`` key) is flattened to that scalar. Any other dict
    is treated as a **composite** raw (e.g. ``employment_type``'s
    ``{"attachment": ..., "hours": ...}``) and each sub-field is flattened to its
    label, yielding the sub-field dict the engine's composite matcher consumes.
    """
    if isinstance(raw, dict):
        if any(key in raw for key in _RAW_CATEGORY_KEYS):
            return _label(raw)
        return {subfield: _label(value) for subfield, value in raw.items()}
    return raw


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class AbstractRealMapper(ABC):
    """Per-country contract for normalizing a raw real population to schema.

    A subclass supplies only :data:`MAPPINGS_SUBDIR`; the per-record behaviour lives
    in :class:`BaseRealMapper`, and every label it emits comes from that
    directory's mapping config.
    """

    #: Default category-mappings sub-directory under ``config/mapping/``.
    MAPPINGS_SUBDIR: ClassVar[str]

    @abstractmethod
    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Base implementation: thin loader over the shared resolver
# ---------------------------------------------------------------------------

class BaseRealMapper(AbstractRealMapper):
    """Shared, field-literal-free loader driven by the symmetric mapping config.

    Not instantiated directly -- a country subclass supplies :data:`MAPPINGS_SUBDIR`.
    The comparison attributes (in axis order) come from the ``_index.json`` master;
    each attribute's ``real`` rules block and ``values`` list drive
    :func:`mapping_engine.resolve`.
    """

    def __init__(self, mappings: dict) -> None:
        """Bind the merged *mappings* dict and read its ``_index`` master.

        *mappings* is the per-country config merged by ``load_mappings`` (one entry
        per file, keyed by file stem, including the ``_index`` master). Fails fast
        when no ``_index`` block with an ``attributes`` map is present.
        """
        self.mappings = mappings
        index = mappings.get("_index")
        if not isinstance(index, dict) or not isinstance(index.get("attributes"), dict):
            raise ValueError("real mapper requires an '_index' block declaring 'attributes'")
        #: Ordered ``attribute -> config filename`` map (key order = axis order).
        self._attributes: dict[str, str] = index["attributes"]

    # -- config access ------------------------------------------------------

    def _block_for(self, attr: str) -> dict:
        """Return the per-attribute config block for *attr* (keyed by file stem)."""
        filename = self._attributes[attr]
        stem = filename[:-5] if filename.endswith(".json") else filename
        block = self.mappings.get(stem)
        if not isinstance(block, dict):
            raise ValueError(f"real mapper: missing config block {stem!r} for attribute {attr!r}")
        return block

    # -- resolution ---------------------------------------------------------

    def _resolve_attr(self, attr: str, record: dict, resolved: dict[str, Any]) -> Any:
        """Resolve one attribute against *record*, memoising into *resolved*.

        ``age_group`` short-circuits to the raw integer age (the evaluator bins it);
        every other attribute delegates to :func:`mapping_engine.resolve` with its
        ``real`` block, resolving a ``refine_from`` sibling first when declared.
        """
        if attr in resolved:
            return resolved[attr]
        if attr == _AGE_GROUP_ATTR:
            value = record.get(_AGE_KEY)
            resolved[attr] = value
            return value

        block = self._block_for(attr)
        rules_block = block["real"]
        values = block["values"]
        raw = _extract(record.get(attr))

        refine_value: str | None = None
        refine_from = rules_block.get("refine_from")
        if refine_from is not None:
            refine_value = self._resolve_attr(refine_from, record, resolved)

        value = mapping_engine.resolve(raw, rules_block, values, refine_value=refine_value)
        resolved[attr] = value
        return value

    # -- orchestrator -------------------------------------------------------

    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert one raw-format record (nested RawCategory dicts) to flat schema strings."""
        resolved: dict[str, Any] = {}
        result: dict[str, Any] = {"id": record.get("id")}
        for attr in self._attributes:
            value = self._resolve_attr(attr, record, resolved)
            out_key = _AGE_KEY if attr == _AGE_GROUP_ATTR else attr
            result[out_key] = value
        return result

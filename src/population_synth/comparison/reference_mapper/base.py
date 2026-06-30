"""Abstract and base reference-population mappers.

The *reference mapper* turns one raw-format reference record (nested
``RawCategory`` dicts produced by a national statistics API, e.g. SCB/ISTAT)
into the flat canonical schema dict the ``StatisticalEvaluator`` consumes.

``AbstractReferenceMapper`` is a pure contract: it declares the single per-country
class attribute (``MAPPINGS_SUBDIR``) and the ``normalize_individual`` method, and
knows nothing about which demographic fields exist or how any of them is coded.

``BaseReferenceMapper`` is a **generic handler-kind engine**. It holds no field-name
literal whatsoever: it discovers its field set at construction by scanning the loaded
mapping tables for blocks that self-declare a ``reference_handler`` key. The handler
kind names a generic algorithm (never a field); the binding of field -> algorithm, and
every label the algorithm emits, lives in the country mapping JSON under
``config/mapping/{scb,istat}/``.

There are five handler kinds, each a factory ``(attr, block) -> handler`` that closes
over the output schema attribute and that attribute's own mapping block:

- ``passthrough`` -- emit the raw record value verbatim (e.g. ``id``, ``age``).
- ``label`` -- case-insensitive lookup through ``reference_label_mappings`` with a
  ``reference_none_default`` fallback when the field is absent.
- ``composite`` -- combine attachment/hours sub-labels into one composite schema label;
  an already-composite reference value passes through unchanged.
- ``decile_coded`` -- decile/income-bracket codes -> class label (CI decile map, numeric
  ``Decile N`` fallback, ``mappings[*].reference_codes``, raw passthrough).
- ``substring_coded`` -- substring match of a raw code against ``mappings[*].reference_codes``.

A block declaring a ``reference_attr`` emits under that schema key while reading its
tables from the file's own block (resolving file-stem != schema-attribute). Blocks
without a ``reference_handler`` key (``_scheme`` and the synthetic-only files) are
ignored. The engine fails fast: an unknown handler kind, or no field declaring a
handler at all, raises ``ValueError``. An unrecognised raw value passes through
unchanged for every kind.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Role-based config sub-keys and structural tokens (never field names)
# ---------------------------------------------------------------------------

#: Role-based sub-key holding a one-to-one ``reference label -> schema label`` table.
_LABEL_KEY = "reference_label_mappings"

#: Role-based sub-key holding the schema label to emit when the record omits the field.
_NONE_DEFAULT_KEY = "reference_none_default"

#: Separator joining the attachment/hours schema tokens into a composite key, and the
#: marker for an already-composite reference value that passes through.
_COMPOSITE_SEP = "|"


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _ci_map(d: dict[str, str]) -> dict[str, str]:
    """Build a case-insensitive lookup dict (lowercased keys, original values)."""
    return {k.lower(): v for k, v in d.items()}


def _label(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get("label") or v.get("code") or v.get("decile")
    return str(v)


def _ci_get(ci_dict: dict[str, str], raw: str, default: str | None = None) -> str | None:
    return ci_dict.get(raw.lower(), default if default is not None else raw)


# ---------------------------------------------------------------------------
# Handler-kind factories
#
# Each factory shares the ``(attr, block) -> Callable[[record], value]`` signature.
# It closes over the output schema attribute (``attr``) and that attribute's own
# mapping block (``block``); the produced handler reads the record value via
# ``record.get(attr)`` while pulling every table from ``block``. No factory names a
# field -- the algorithm name is the only identity it carries.
# ---------------------------------------------------------------------------

def _passthrough_handler(attr: str, block: dict) -> Callable[[dict], Any]:
    """Emit the raw record value for *attr* verbatim."""
    return lambda record: record.get(attr)


def _label_handler(attr: str, block: dict) -> Callable[[dict], str | None]:
    """Single-label attribute resolved through ``_LABEL_KEY`` + ``_NONE_DEFAULT_KEY``."""
    none_default = block.get(_NONE_DEFAULT_KEY)
    label_map = _ci_map(block.get(_LABEL_KEY, {}))

    def handler(record: dict) -> str | None:
        raw = _label(record.get(attr))
        if not raw:
            return none_default
        return _ci_get(label_map, raw)

    return handler


def _composite_handler(attr: str, block: dict) -> Callable[[dict], str | None]:
    """Two composite sub-tables + a combination table, joined by ``_COMPOSITE_SEP``."""
    att_map = _ci_map(block.get("reference_attachment_mappings", {}))
    hrs_map = _ci_map(block.get("reference_hours_mappings", {}))
    composite_map: dict[str, str] = block.get("reference_composite_mappings", {})
    none_default: str | None = block.get(_NONE_DEFAULT_KEY)

    def handler(record: dict) -> str | None:
        raw = record.get(attr)
        if isinstance(raw, dict) and "attachment" in raw:
            att_label = _label(raw.get("attachment")) or ""
            hrs_label = _label(raw.get("hours")) or ""
            att = att_map.get(att_label.lower(), att_label)
            hrs = hrs_map.get(hrs_label.lower(), hrs_label)
            composite = (composite_map.get(f"{att}{_COMPOSITE_SEP}{hrs}")
                         or composite_map.get(att))
            return composite if composite is not None else f"{att}/{hrs}"
        if isinstance(raw, str) and _COMPOSITE_SEP in raw:
            # Already-composite reference value (e.g. "Permanent|Full-time").
            return raw
        if raw is None:
            return none_default
        return _label(raw)

    return handler


def _decile_coded_handler(attr: str, block: dict) -> Callable[[dict], str | None]:
    """Decile/income-bracket codes -> class label, with raw passthrough fallback."""
    code_to_schema: dict[str, str] = {}
    for entry in block.get("mappings", {}).values():
        schema_label = entry.get("schema_label", "")
        for code in entry.get("reference_codes", []):
            code_to_schema[str(code)] = schema_label
    # Decile labels (legacy SCB-format populations like scb02) -> 4-class schema.
    decile_map: dict[str, str] = block.get("reference_decile_mappings", {})
    decile_ci: dict[str, str] = {k.lower(): v for k, v in decile_map.items()}
    decile_num: dict[str, str] = {}
    for k, v in decile_map.items():
        if k.lower().startswith("decile "):
            decile_num[k.split()[-1]] = v

    def handler(record: dict) -> str | None:
        raw = record.get(attr)
        if isinstance(raw, dict):
            raw_val = str(raw.get("label") or raw.get("decile", ""))
            raw_val_l = raw_val.lower()
            if raw_val_l in decile_ci:
                return decile_ci[raw_val_l]
            if raw_val_l.startswith("decile "):
                token = raw_val.split()[-1]
                return (decile_num.get(token)
                        or code_to_schema.get(token) or raw_val)
            return code_to_schema.get(raw_val) or (raw_val if raw_val else None)
        if raw is not None:
            return code_to_schema.get(str(raw), str(raw))
        return None

    return handler


def _substring_coded_handler(attr: str, block: dict) -> Callable[[dict], str | None]:
    """Reference codes -> schema label, matched exactly then by substring."""
    raw_to_schema: dict[str, str] = {}
    for entry in block.get("mappings", {}).values():
        schema_label = entry.get("schema_label", "")
        for code in entry.get("reference_codes", []):
            raw_to_schema[code.lower()] = schema_label

    def match(raw_lower: str) -> str | None:
        exact = raw_to_schema.get(raw_lower)
        if exact is not None:
            return exact
        for code, schema_label in raw_to_schema.items():
            if code in raw_lower:
                return schema_label
        return None

    def handler(record: dict) -> str | None:
        raw = _label(record.get(attr))
        if raw is not None:
            return match(raw.lower()) or raw
        return None

    return handler


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class AbstractReferenceMapper(ABC):
    """Per-country contract for normalizing a raw reference population to schema.

    A subclass supplies only :data:`MAPPINGS_SUBDIR`; the per-record behaviour lives
    in :class:`BaseReferenceMapper`, and every label it emits comes from that
    directory's mapping tables.
    """

    #: Default category-mappings sub-directory under ``config/mapping/``.
    MAPPINGS_SUBDIR: ClassVar[str]

    @abstractmethod
    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Base implementation: generic handler-kind engine
# ---------------------------------------------------------------------------

class BaseReferenceMapper(AbstractReferenceMapper):
    """Shared, field-literal-free engine driven entirely by the mapping tables.

    Not instantiated directly -- a country subclass supplies :data:`MAPPINGS_SUBDIR`.
    The field set is discovered at construction by scanning the loaded mappings for
    blocks that declare a ``reference_handler`` kind.
    """

    #: Library of generic handler kinds, keyed by algorithm name (never by field).
    #: Each value is a factory ``(attr, block) -> Callable[[record], value]``.
    _HANDLER_KINDS: ClassVar[dict[str, Callable]] = {
        "passthrough": _passthrough_handler,
        "label": _label_handler,
        "composite": _composite_handler,
        "decile_coded": _decile_coded_handler,
        "substring_coded": _substring_coded_handler,
    }

    def __init__(self, mappings: dict) -> None:
        """Build the handler registry by scanning *mappings* for declared fields.

        Every block carrying a ``reference_handler`` key contributes one handler,
        bound to ``reference_attr`` (defaulting to the file stem). Blocks without the
        key (``_scheme`` and the synthetic-only files) are skipped. Fail fast on an
        unknown kind or a mapping set that declares no reference field at all.
        """
        self.mappings = mappings

        self._handlers: dict[str, Callable[[dict], Any]] = {}
        for stem, block in mappings.items():
            if not isinstance(block, dict) or "reference_handler" not in block:
                continue
            kind = block["reference_handler"]
            factory = self._HANDLER_KINDS.get(kind)
            if factory is None:
                raise ValueError(f"Unknown reference handler kind {kind!r} in {stem!r}")
            attr = block.get("reference_attr", stem)
            self._handlers[attr] = factory(attr, block)
        if not self._handlers:
            raise ValueError("reference mapper found no fields declaring 'reference_handler'")

    # -- orchestrator -------------------------------------------------------

    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert one raw-format record (nested RawCategory dicts) to flat schema strings."""
        return {attr: handler(record) for attr, handler in self._handlers.items()}

"""mapping_sentinel.py -- the "no canonical equivalent" sentinel for mapped values.

Single source of truth for the explicit token the mapping engine emits when an
attribute is mapped but has no canonical equivalent (a total value-walk miss with
no configured ``on_miss`` literal). Before this sentinel the mapper emitted a bare
``None`` on such a miss, which was indistinguishable from a genuinely absent field
and silently readable as "no data". The explicit :data:`UNMAPPED` token makes the
"mapped, but nothing matched" outcome legible in the persona payloads the judge
reads while remaining statistically inert.

Two consumers depend on this:

* the LLM-as-judge (``persona_realism``) **tolerates and renders** the token so an
  unmapped axis shows up verbatim in the persona block instead of hard-failing;
* the statistical evaluators (fidelity marginals / joint / coherence, and the
  shared ``marginals`` helper) treat the token **exactly** as they already treat
  ``None`` -- excluded from proportion bases, joint tables, and coherence support --
  so fidelity outputs are numerically unchanged.

:func:`is_unmapped` is the predicate both sides use. It recognises the explicit
sentinel **and** legacy ``None`` so pre-sentinel on-disk data and caches keep
behaving identically until they are re-mapped.

No heavy dependencies: importable from any layer (pure stdlib types only).
"""

from __future__ import annotations

from typing import Any

__all__ = ["UNMAPPED", "is_unmapped"]

#: The explicit "mapped attribute with no canonical equivalent" token. Emitted by
#: the mapping engine on a total miss when the attribute declares no ``on_miss``.
UNMAPPED = "__UNMAPPED__"


def is_unmapped(value: Any) -> bool:
    """Return whether *value* is a mapped attribute with no canonical equivalent.

    Recognises both the explicit :data:`UNMAPPED` sentinel and legacy ``None``
    (pre-sentinel data/caches), so the two are handled identically everywhere the
    pipeline previously special-cased ``None``.
    """
    return value is None or value == UNMAPPED

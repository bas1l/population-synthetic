"""Guard: Sweden's mapping tiers declare no ``on_miss`` sink, and no orphan values.

``on_miss`` names a literal the engine returns when the whole value-walk misses. On a
*scored* axis that is a silent failure: the mapped record carries a real-looking category,
so ``validate_mapped`` (which only ever sees the ``__UNMAPPED__`` sentinel) cannot tell the
miss from a hit, and the miss mass lands in that category's marginal -- the exact quantity
the fidelity score measures. Both former Swedish sinks behaved this way
(``industry_sector -> "Other"``, ``income_source -> "Wage / Business"``); removing them was
a deliberate correctness change, and re-adding one is a regression a config edit could
reintroduce without any test noticing.

The orphan check is the second half of the same rule. Dropping a sink can leave the value it
pointed at unreachable from *both* the ``real`` and ``synthetic`` blocks -- as it did for
``industry_sector``'s ``Other`` -- and a declared-but-unproducible value becomes a zero-mass
phantom category on the comparison axis.

Italy (``config/mapping/istat/``) is deliberately not covered: it still declares ``on_miss``
on two attributes, and removing it there invalidates every Italian mapped artefact, so it is
its own change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from population_synthetic._paths import PROJECT_ROOT

#: Mapping tiers Sweden can select via a country axis YAML's ``parameters.mappings``.
_SWEDEN_TIERS = ("scb", "scb_native")

#: ``age_group`` is special-cased to an int passthrough by ``map_individual`` and its
#: matchers are never consumed, so its values are unreachable by construction.
_UNMAPPED_BY_DESIGN = frozenset({"age_group"})

_RULE_BLOCKS = ("real", "synthetic")


def _attribute_files(tier: str) -> list[tuple[str, Path]]:
    """Return ``(attribute, path)`` for every attribute the tier's ``_index`` declares."""
    root = PROJECT_ROOT / "config" / "mapping" / tier
    index = json.loads((root / "_index.json").read_text(encoding="utf-8"))
    return [
        (attr, root / filename)
        for attr, filename in index["attributes"].items()
        if attr not in _UNMAPPED_BY_DESIGN
    ]


_CASES = [
    pytest.param(tier, attr, path, id=f"{tier}/{attr}")
    for tier in _SWEDEN_TIERS
    for attr, path in _attribute_files(tier)
]


@pytest.mark.parametrize(("tier", "attr", "path"), _CASES)
def test_no_on_miss_sink_declared(tier: str, attr: str, path: Path) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    for block in _RULE_BLOCKS:
        assert "on_miss" not in config.get(block, {}), (
            f"{tier}/{attr} declares an 'on_miss' sink in its {block!r} block. A sink returns a "
            f"real-looking category on a total miss, so validate_mapped cannot see the failure "
            f"and the miss mass corrupts that category's marginal. Add a matcher token for the "
            f"variant instead, or let the value stay __UNMAPPED__."
        )


@pytest.mark.parametrize(("tier", "attr", "path"), _CASES)
def test_every_declared_value_is_reachable(tier: str, attr: str, path: Path) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    values = config.get("values", [])
    if not values:
        pytest.skip(f"{tier}/{attr} declares no unified value set")

    for block in _RULE_BLOCKS:
        rules = config.get(block, {})
        if not rules:
            continue
        # A value is reachable if it has a matcher entry, or is the block's ``absent``
        # literal (produced when the raw field is missing rather than by a matcher).
        unreachable = [v for v in values if v not in rules and v != rules.get("absent")]
        assert not unreachable, (
            f"{tier}/{attr} declares value(s) {unreachable} that no {block!r} matcher can "
            f"produce. An unproducible value is a zero-mass phantom category on the comparison "
            f"axis -- drop it from 'values', or give it a matcher."
        )

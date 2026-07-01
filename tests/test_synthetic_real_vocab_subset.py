"""Config-integrity guard over the unified symmetric mapping files.

The old dual-vocabulary drift guard (synthetic emittable vocab subseteq real
vocab) is obsolete: both mapper sides now emit *only* the labels declared in each
attribute file's single ``values`` list, so the two vocabularies are the same set by
construction. What remains worth locking down is that the config actually upholds that
invariant on disk -- i.e. neither the ``real`` nor the ``synthetic`` rules block
can key a label outside ``values`` (which would be an unscored, never-matched entry),
and the ``_index.json`` master points only at files that exist.

For every comparison attribute file in each country dir this test asserts:

1. the ``_index.json`` master's referenced file exists;
2. every non-directive key of the ``real`` block is a declared ``value``;
3. every non-directive key of the ``synthetic`` block is a declared ``value``;
4. any ``refine_from`` directive names an attribute present in the master.

Directive keys (``absent`` / ``refine_from`` / ``on_miss``) are the only
non-value keys permitted on a rules block. ``age.json`` is values-only (``age_group``
is derived at scoring time), so its missing ``real`` / ``synthetic`` blocks are
skipped. The check reads the real ``config/mapping/{scb,istat}`` files (no mapper run),
so any future config edit that re-introduces drift fails loudly, naming the offender.
"""

from __future__ import annotations

import json

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper.mappings import load_index

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

#: The only non-``value`` keys a ``real`` / ``synthetic`` rules block may carry.
_DIRECTIVE_KEYS = {"absent", "refine_from", "on_miss"}

_COUNTRY_DIRS = {"swedish": "scb", "italian": "istat"}


def _country_attribute_files(subdir: str):
    """Yield ``(attr, path, block)`` for every attribute the country's master declares."""
    directory = _MAPPINGS_ROOT / subdir
    index = load_index(directory)
    for attr, filename in index["attributes"].items():
        path = directory / filename
        assert path.is_file(), f"[{subdir}] _index references missing file {path}"
        block = json.loads(path.read_text(encoding="utf-8"))
        yield attr, path, block, index["attributes"]


@pytest.mark.parametrize("country,subdir", sorted(_COUNTRY_DIRS.items()))
def test_rules_blocks_key_only_declared_values(country: str, subdir: str) -> None:
    """Both rules blocks key only labels present in the file's ``values`` (+ directives)."""
    checked: list[str] = []
    offenders: dict[str, dict[str, list[str]]] = {}

    for attr, path, block, all_attrs in _country_attribute_files(subdir):
        assert "values" in block, f"[{subdir}] {path.name} is missing 'values'"
        values = set(block["values"])
        checked.append(attr)

        for side in ("real", "synthetic"):
            rules = block.get(side)
            if rules is None:  # e.g. age.json is values-only.
                continue
            stray = sorted(
                key for key in rules
                if key not in _DIRECTIVE_KEYS and key not in values
            )
            if stray:
                offenders.setdefault(attr, {})[side] = stray

            refine_from = rules.get("refine_from")
            if refine_from is not None:
                assert refine_from in all_attrs, (
                    f"[{subdir}] {path.name} [{side}] refine_from -> {refine_from!r} "
                    f"is not a declared comparison attribute"
                )

    assert checked, f"no attributes discovered for {country!r}"
    assert not offenders, (
        f"[{country}] rules blocks key labels outside the declared 'values' axis "
        f"(would be unscored, never-matched entries):\n"
        + "\n".join(f"  {attr}: {sides}" for attr, sides in sorted(offenders.items()))
    )

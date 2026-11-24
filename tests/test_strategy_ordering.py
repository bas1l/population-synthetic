"""Tests for the config-derived strategy ordering accessor (``analysis/utils/axes.py``).

The strategy axis used to be a hardcoded Python list; it is now derived from
``config/synthetic/axes/strategies/_families.yaml`` (family rank) plus each
strategy YAML's ``family`` / ``version``. Three properties are load-bearing:

* **the legacy sequence is preserved** -- with only the five v1 ids present the
  order must equal the old constant exactly, or the manuscript's global-best-strategy
  tie-break (ties prefer the *simpler* strategy) silently moves a published result;
* **the order is total** -- every pair compares, so the tie-break is decidable;
* **the resolution fails loudly** -- an unknown id or family raises rather than
  "sorting last", which would hide axis drift behind a plausible-looking chart.
"""

from __future__ import annotations

from itertools import combinations

import pytest
import yaml

from population_synthetic.analysis.utils.axes import (
    FAMILIES_FILENAME,
    STRATEGIES_DIR,
    load_family_order,
    strategy_complexity_order,
    strategy_versions,
)
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

# The order the removed ``STRATEGY_COMPLEXITY_ORDER`` constant declared. Frozen here
# on purpose: this literal is the regression anchor, not a second source of truth.
LEGACY_ORDER = [
    "all_pick",
    "all_pick_dag",
    "all_generate_pick",
    "all_generate_evaluate_pick",
    "all_generate_evaluate_random_pick",
]


# --------------------------------------------------------------------------- #
# Regression: the v1-only order is byte-identical to the legacy constant        #
# --------------------------------------------------------------------------- #


def test_v1_only_order_equals_the_legacy_sequence():
    assert strategy_complexity_order(LEGACY_ORDER) == LEGACY_ORDER


def test_v1_only_order_is_independent_of_input_order():
    """Input permutation must not survive into the output (it is a sort, not a filter)."""
    assert strategy_complexity_order(list(reversed(LEGACY_ORDER))) == LEGACY_ORDER
    assert strategy_complexity_order(sorted(LEGACY_ORDER)) == LEGACY_ORDER


def test_discovered_strategy_axis_orders_to_the_legacy_sequence():
    """Whatever the axis currently declares, the v1 families keep the locked order."""
    discovered = [d["id"] for d in discover_axis_values("strategies")]
    ordered = strategy_complexity_order(discovered)
    assert [s for s in ordered if s in LEGACY_ORDER] == LEGACY_ORDER


# --------------------------------------------------------------------------- #
# Totality                                                                     #
# --------------------------------------------------------------------------- #


def test_order_is_total_over_the_declared_axis():
    """Every pair compares strictly one way: no two ids share a sort position."""
    discovered = [d["id"] for d in discover_axis_values("strategies")]
    ordered = strategy_complexity_order(discovered)

    assert len(ordered) == len(set(ordered)) == len(set(discovered))
    position = {s: i for i, s in enumerate(ordered)}
    for a, b in combinations(ordered, 2):
        assert (position[a] < position[b]) != (position[b] < position[a])


def test_duplicate_ids_are_collapsed():
    assert strategy_complexity_order(["all_pick_dag", "all_pick", "all_pick"]) == [
        "all_pick",
        "all_pick_dag",
    ]


# --------------------------------------------------------------------------- #
# Family / version keys                                                        #
# --------------------------------------------------------------------------- #


def test_family_index_declares_the_five_v1_families_simplest_first():
    assert load_family_order() == LEGACY_ORDER


def test_v1_strategies_declare_version_one():
    assert strategy_versions(LEGACY_ORDER) == dict.fromkeys(LEGACY_ORDER, 1)


def _fixture_dir(tmp_path, families, strategies):
    """Write a self-contained strategies directory (family index + strategy YAMLs)."""
    (tmp_path / FAMILIES_FILENAME).write_text(
        yaml.safe_dump({"families": [{"id": f} for f in families]}), encoding="utf-8"
    )
    for strategy_id, doc in strategies.items():
        (tmp_path / f"{strategy_id}.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return tmp_path


def test_version_sorts_after_family_rank(tmp_path):
    """A later version of a simpler family still precedes a more complex family."""
    directory = _fixture_dir(
        tmp_path,
        ["simple", "complex"],
        {
            "simple_v1": {"family": "simple", "version": 1},
            "simple_v2": {"family": "simple", "version": 2},
            "complex_v1": {"family": "complex", "version": 1},
        },
    )
    assert strategy_complexity_order(
        ["complex_v1", "simple_v2", "simple_v1"], strategies_dir=directory
    ) == ["simple_v1", "simple_v2", "complex_v1"]


def test_version_ten_sorts_after_version_two(tmp_path):
    """Versions compare as integers, not as strings (v10 must not precede v2)."""
    directory = _fixture_dir(
        tmp_path,
        ["fam"],
        {
            "fam_v2": {"family": "fam", "version": 2},
            "fam_v10": {"family": "fam", "version": 10},
        },
    )
    assert strategy_complexity_order(["fam_v10", "fam_v2"], strategies_dir=directory) == [
        "fam_v2",
        "fam_v10",
    ]


# --------------------------------------------------------------------------- #
# Fail-fast                                                                    #
# --------------------------------------------------------------------------- #


def test_unknown_strategy_id_raises():
    with pytest.raises(ValueError, match="Unknown strategy id"):
        strategy_complexity_order(["all_pick", "not_a_strategy"])


def test_unknown_family_raises(tmp_path):
    directory = _fixture_dir(
        tmp_path, ["fam"], {"stray": {"family": "unlisted", "version": 1}}
    )
    with pytest.raises(ValueError, match="not in the family index"):
        strategy_complexity_order(["stray"], strategies_dir=directory)


@pytest.mark.parametrize(
    "doc",
    [
        {"version": 1},                       # family absent
        {"family": "", "version": 1},         # family empty
        {"family": "fam"},                    # version absent
        {"family": "fam", "version": 0},      # version below 1
        {"family": "fam", "version": "1"},    # version not an int
        {"family": "fam", "version": True},   # bool is not a version
    ],
)
def test_malformed_axis_metadata_raises(tmp_path, doc):
    directory = _fixture_dir(tmp_path, ["fam"], {"broken": doc})
    with pytest.raises(ValueError, match="family|version"):
        strategy_complexity_order(["broken"], strategies_dir=directory)


def test_missing_family_index_raises(tmp_path):
    (tmp_path / "lonely.yaml").write_text(
        yaml.safe_dump({"family": "fam", "version": 1}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="family index"):
        strategy_complexity_order(["lonely"], strategies_dir=tmp_path)


@pytest.mark.parametrize(
    "raw",
    [
        {},                                              # no 'families' key
        {"families": []},                                # empty
        {"families": ["all_pick"]},                      # entries not mappings
        {"families": [{"label": "no id"}]},              # entry without an id
        {"families": [{"id": "a"}, {"id": "a"}]},        # duplicate rank
    ],
)
def test_malformed_family_index_raises(tmp_path, raw):
    (tmp_path / FAMILIES_FILENAME).write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_family_order(tmp_path)


# --------------------------------------------------------------------------- #
# The family index must never be discovered as a strategy                      #
# --------------------------------------------------------------------------- #


def test_family_index_is_not_a_discoverable_strategy():
    """The ``_`` prefix is what keeps the index out of the selectable axis."""
    assert FAMILIES_FILENAME.startswith("_")
    assert (STRATEGIES_DIR / FAMILIES_FILENAME).is_file()

    ids = [d["id"] for d in discover_axis_values("strategies")]
    assert "_families" not in ids
    assert "families" not in ids
    assert not any(i.startswith("_") for i in ids)

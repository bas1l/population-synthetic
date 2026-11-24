"""Tests for the config-derived strategy ordering accessor (``analysis/utils/axes.py``).

The strategy axis used to be a hardcoded Python list; it is now derived from
``config/synthetic/axes/strategies/_families.yaml`` (family rank) plus each
strategy YAML's ``family`` / ``version``. Three properties are load-bearing:

* **the sequence is preserved** -- with the five strategy ids present the
  order must equal the family sequence exactly, or the manuscript's global-best-strategy
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

# The five families, simplest first. Frozen here on purpose: this literal is the
# regression anchor, not a second source of truth. STRATEGY_ORDER is the same order as
# the selectable strategy ids.
FAMILY_ORDER = [
    "all_pick",
    "all_pick_dag",
    "all_generate_pick",
    "all_generate_evaluate_pick",
    "all_generate_evaluate_random_pick",
]
STRATEGY_ORDER = [f"{family}_v2" for family in FAMILY_ORDER]


# --------------------------------------------------------------------------- #
# Regression: the strategy order follows the family sequence                   #
# --------------------------------------------------------------------------- #


def test_strategy_order_equals_the_family_sequence():
    assert strategy_complexity_order(STRATEGY_ORDER) == STRATEGY_ORDER


def test_strategy_order_is_independent_of_input_order():
    """Input permutation must not survive into the output (it is a sort, not a filter)."""
    assert strategy_complexity_order(list(reversed(STRATEGY_ORDER))) == STRATEGY_ORDER
    assert strategy_complexity_order(sorted(STRATEGY_ORDER)) == STRATEGY_ORDER


def test_discovered_strategy_axis_orders_to_the_family_sequence():
    """Whatever the axis currently declares, the families keep the locked order."""
    discovered = [d["id"] for d in discover_axis_values("strategies")]
    ordered = strategy_complexity_order(discovered)
    assert ordered == STRATEGY_ORDER


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
    assert strategy_complexity_order(["all_pick_dag_v2", "all_pick_v2", "all_pick_v2"]) == [
        "all_pick_v2",
        "all_pick_dag_v2",
    ]


# --------------------------------------------------------------------------- #
# Family / version keys                                                        #
# --------------------------------------------------------------------------- #


def test_family_index_declares_the_five_families_simplest_first():
    assert load_family_order() == FAMILY_ORDER


def test_strategies_declare_version_two():
    assert strategy_versions(STRATEGY_ORDER) == dict.fromkeys(STRATEGY_ORDER, 2)


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
            "simple_first": {"family": "simple", "version": 1},
            "simple_second": {"family": "simple", "version": 2},
            "complex_first": {"family": "complex", "version": 1},
        },
    )
    assert strategy_complexity_order(
        ["complex_first", "simple_second", "simple_first"], strategies_dir=directory
    ) == ["simple_first", "simple_second", "complex_first"]


def test_version_ten_sorts_after_version_two(tmp_path):
    """Versions compare as integers, not as strings (ten must not precede two)."""
    directory = _fixture_dir(
        tmp_path,
        ["fam"],
        {
            "fam_two": {"family": "fam", "version": 2},
            "fam_ten": {"family": "fam", "version": 10},
        },
    )
    assert strategy_complexity_order(["fam_ten", "fam_two"], strategies_dir=directory) == [
        "fam_two",
        "fam_ten",
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

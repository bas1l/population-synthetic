"""Unit tests for the ``cost_efficiency`` builder: one derived quantity, no composite.

Three properties:

* ``cost_per_usable_persona`` is denominated on ``clean`` and is ``None`` -- never
  ``0.0``, never infinite -- wherever the quotient is undefined. A measured ``0.0``
  occurs only for an unmetered model, and it must survive as ``0.0``.
* **No composite score exists.** Not as a CSV column, not as a JSON key. The document
  declares ``non_composite`` so the omission is a stated property rather than an
  oversight, and this file asserts that no accuracy-per-dollar field ever creeps back in.
* Withdrawn combinations are carried in the document with the money they cost, so the
  artifact reports what the figure cannot draw.

Rates are compared with ``pytest.approx``; nothing here asserts exact float equality.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.cost_efficiency.builder import (
    PROCESS_ID,
    build_document,
    build_rows,
    cost_per_usable_persona,
)
from population_synthetic.analysis.cost_efficiency.loader import load_cost_records
from population_synthetic.analysis.utils.cost_csv import FIELDNAMES
from tests._cost_efficiency_fixtures import (
    COMPLEX_STRATEGY,
    COUNTRY,
    METERED_MODEL,
    SIMPLE_STRATEGY,
    UNMETERED_MODEL,
    build_base,
    make_pricing,
    slug_for,
)

_PRICING = make_pricing()


def _result(tmp_path, **kwargs):
    base = build_base(tmp_path, **kwargs)
    return load_cost_records(base, COUNTRY, pricing=_PRICING)


# ---------------------------------------------------------------------------
# The one derived quantity
# ---------------------------------------------------------------------------

def test_cost_per_usable_persona_is_cost_over_clean() -> None:
    assert cost_per_usable_persona(0.21, 8) == pytest.approx(0.02625)


def test_cost_per_usable_persona_is_none_when_the_cost_is_absent() -> None:
    value = cost_per_usable_persona(None, 8)
    assert value is None
    assert value != 0.0


def test_cost_per_usable_persona_is_none_not_infinite_at_zero_clean() -> None:
    value = cost_per_usable_persona(0.21, 0)
    assert value is None


def test_unmetered_cost_per_usable_persona_is_a_measured_zero() -> None:
    value = cost_per_usable_persona(0.0, 8)
    assert value == 0.0
    assert value is not None


def test_row_denominates_on_clean_not_selected(tmp_path) -> None:
    # generated=10, clean=8, cost 0.21 -> 0.02625. Denominating on selected would be a
    # different number the moment the cap is not the clean pool.
    result = _result(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),),
                     generated=10, clean=8)
    row = build_rows(result)[0]
    assert row.clean == 8
    assert row.total_cost_usd == pytest.approx(0.21)
    assert row.cost_per_usable_persona == pytest.approx(0.21 / 8)


def test_generation_multiplier_is_read_from_attrition_not_recomputed(tmp_path) -> None:
    result = _result(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),),
                     generated=10, clean=8)
    row = build_rows(result)[0]
    assert row.generation_multiplier == pytest.approx(result.records[0].attrition.generation_multiplier)


# ---------------------------------------------------------------------------
# No composite score
# ---------------------------------------------------------------------------

_FORBIDDEN = ("per_dollar", "value_score", "efficiency_score", "accuracy_per", "score_rank")


def test_no_composite_column_exists() -> None:
    for column in FIELDNAMES:
        assert not any(token in column for token in _FORBIDDEN), column


def test_document_declares_non_composite(tmp_path) -> None:
    document = build_document(_result(tmp_path))
    assert document["non_composite"] is True
    assert document["non_composite_reason"]


def test_no_composite_key_anywhere_in_the_document(tmp_path) -> None:
    document = build_document(_result(tmp_path))

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not any(token in key for token in _FORBIDDEN), f"{path}.{key}"
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(document)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def test_document_carries_the_cost_basis_and_the_unmetered_note(tmp_path) -> None:
    document = build_document(_result(tmp_path))
    assert document["cost_basis"] == "generated_pool_01_raw"
    assert "not free" in document["unmetered_note"]
    assert document["process"] == PROCESS_ID


def test_document_states_the_membership_rule_and_the_join_key(tmp_path) -> None:
    document = build_document(
        _result(tmp_path,
                joined=((METERED_MODEL, SIMPLE_STRATEGY),),
                withdrawn=((UNMETERED_MODEL, COMPLEX_STRATEGY),))
    )
    membership = document["membership"]
    assert membership["attrition_rows"] == 2
    assert membership["attrition_withdrawn"] == 1
    assert membership["joined_rows"] == 1
    assert "axis_slug" in membership["join_key"]
    assert "withdraw" in membership["rule"].lower()


def test_withdrawn_combination_is_in_the_document_with_its_spend(tmp_path) -> None:
    document = build_document(
        _result(tmp_path,
                joined=((UNMETERED_MODEL, SIMPLE_STRATEGY),),
                withdrawn=((METERED_MODEL, COMPLEX_STRATEGY),),
                generated=10)
    )
    assert document["n_combinations"] == 1
    entry = document["withdrawn_combinations"][0]
    assert entry["slug"] == slug_for(METERED_MODEL, COMPLEX_STRATEGY)
    assert entry["total_cost_usd"] == pytest.approx(0.21)
    assert entry["reason"]
    assert document["withdrawn_totals"]["metered_total_cost_usd"] == pytest.approx(0.21)


def test_totals_separate_the_metered_subset_from_the_unmetered_rows(tmp_path) -> None:
    document = build_document(
        _result(tmp_path,
                joined=((METERED_MODEL, SIMPLE_STRATEGY), (UNMETERED_MODEL, SIMPLE_STRATEGY)),
                generated=10, clean=8)
    )
    totals = document["totals"]
    assert totals["n_combinations"] == 2
    assert totals["n_unmetered_combinations"] == 1
    # Pooling the unmetered zero into the dollar total would claim that run was free.
    assert totals["metered"]["n_combinations"] == 1
    assert totals["metered"]["clean"] == 8
    assert totals["metered"]["total_cost_usd"] == pytest.approx(0.21)


def test_pricing_provenance_covers_the_withdrawn_models_too(tmp_path) -> None:
    document = build_document(
        _result(tmp_path,
                joined=((UNMETERED_MODEL, SIMPLE_STRATEGY),),
                withdrawn=((METERED_MODEL, COMPLEX_STRATEGY),))
    )
    assert set(document["pricing"]["models"]) == {UNMETERED_MODEL, METERED_MODEL}
    assert document["pricing"]["models"][UNMETERED_MODEL]["unmetered"] is True


def test_document_carries_no_timestamp_so_it_is_byte_reproducible(tmp_path) -> None:
    import json

    result = _result(tmp_path)
    first = json.dumps(build_document(result), indent=2, sort_keys=False)
    second = json.dumps(build_document(result), indent=2, sort_keys=False)
    assert first == second
    assert "generated_at" not in first


def test_rows_are_sorted_by_slug(tmp_path) -> None:
    result = _result(
        tmp_path,
        joined=((UNMETERED_MODEL, SIMPLE_STRATEGY), (METERED_MODEL, SIMPLE_STRATEGY)),
    )
    slugs = [row.slug for row in build_rows(result)]
    assert slugs == sorted(slugs)

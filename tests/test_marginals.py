"""Unit tests for the shared per-category proportion helper.

Covers the contract of ``analysis/utils/marginals.py::compute_proportions``:
normal proportions, an absent-in-data category as an explicit ``0.0``, an
all-null attribute, extra (unmapped) categories surfaced rather than dropped,
the fail-loud on a missing axis, and the ``age_group`` derivation from raw age.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED
from population_synthetic.analysis.utils.marginals import compute_proportions


def _inds(attr: str, values: list) -> list[dict]:
    return [{attr: v} for v in values]


def test_normal_proportions_sum_to_one_over_present_categories():
    inds = _inds("biological_sex", ["male", "male", "female", "female"])
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    assert props == {"male": 0.5, "female": 0.5}
    assert extra == []
    assert sum(props.values()) == pytest.approx(1.0)


def test_absent_in_data_category_is_explicit_zero():
    inds = _inds("biological_sex", ["male", "male", "male"])
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    assert props["male"] == pytest.approx(1.0)
    # 'female' is requested but never occurs -> a real 0.0, not missing.
    assert props["female"] == 0.0
    assert "female" in props
    assert extra == []


def test_all_null_attribute_yields_all_zero():
    inds = [{"biological_sex": None} for _ in range(3)]
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    assert props == {"male": 0.0, "female": 0.0}
    assert extra == []


def test_unmapped_sentinel_excluded_exactly_like_none():
    # The UNMAPPED sentinel must drop out of the proportion base identically to None:
    # here 2 real values + 1 None + 1 sentinel -> divisor is 2, not 4.
    inds_none = _inds("biological_sex", ["male", "female", None, None])
    inds_sentinel = _inds("biological_sex", ["male", "female", UNMAPPED, UNMAPPED])
    props_none, extra_none = compute_proportions(inds_none, "biological_sex", ["male", "female"])
    props_sentinel, extra_sentinel = compute_proportions(inds_sentinel, "biological_sex", ["male", "female"])
    # Numerically identical to the None case (proves no change to the base).
    assert props_sentinel == props_none == {"male": pytest.approx(0.5), "female": pytest.approx(0.5)}
    # The sentinel is not surfaced as an extra category (excluded, like None).
    assert extra_sentinel == extra_none == []


def test_all_unmapped_attribute_yields_all_zero():
    inds = [{"biological_sex": UNMAPPED} for _ in range(3)]
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    assert props == {"male": 0.0, "female": 0.0}
    assert extra == []


def test_absent_attribute_key_treated_as_null():
    # No 'biological_sex' key at all -> attr_value returns None for each.
    inds = [{} for _ in range(3)]
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    assert props == {"male": 0.0, "female": 0.0}
    assert extra == []


def test_extra_category_surfaced_not_dropped():
    inds = _inds("biological_sex", ["male", "female", "other", "other"])
    props, extra = compute_proportions(inds, "biological_sex", ["male", "female"])
    # 'other' is in the data but not in the requested axis: surfaced, not dropped.
    assert "other" not in props
    assert extra == ["other"]
    # Divisor is total_non_null (4), so requested categories reflect the full count.
    assert props["male"] == pytest.approx(0.25)
    assert props["female"] == pytest.approx(0.25)


def test_multiple_extra_categories_in_first_seen_order():
    inds = _inds("region", ["z", "a", "a", "m"])
    props, extra = compute_proportions(inds, "region", ["a"])
    assert props == {"a": pytest.approx(0.5)}
    assert extra == ["z", "m"]  # first-seen order, not sorted


def test_none_axis_raises():
    inds = _inds("biological_sex", ["male"])
    with pytest.raises(TypeError):
        compute_proportions(inds, "biological_sex", None)


def test_empty_axis_returns_empty_proportions_and_all_extras():
    inds = _inds("biological_sex", ["male", "female"])
    props, extra = compute_proportions(inds, "biological_sex", [])
    assert props == {}
    assert set(extra) == {"male", "female"}


def test_age_group_derived_from_raw_age():
    # attr_value derives the canonical age_group bin from raw integer age.
    inds = [{"age": 20}, {"age": 21}, {"age": 30}]
    props, extra = compute_proportions(inds, "age_group", ["18-24", "25-34"])
    assert props["18-24"] == pytest.approx(2 / 3)
    assert props["25-34"] == pytest.approx(1 / 3)
    assert extra == []

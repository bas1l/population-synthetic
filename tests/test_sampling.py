"""Unit tests for analysis.utils.sampling.subsample_population.

Cover the seeded, size-equalising cap: no-op paths (``n=None``, ``n == len``),
the undersize warning (``n > len``), the real cap (``n < len`` -> exactly n rows in
original relative order with ``metadata['n']`` corrected), seed reproducibility,
the positive-n guard, and non-mutation of the caller's dict.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.utils.sampling import subsample_population


def _population(size: int) -> dict:
    """A minimal mapped-population dict with `size` uniquely tagged individuals."""
    return {
        "individuals": [{"id": i, "value": i * 10} for i in range(size)],
        "metadata": {"n": size, "country": "test"},
    }


def test_n_none_returns_unchanged():
    pop = _population(20)
    result = subsample_population(pop, None)
    # Same object identity is fine (early-return path reproduces current behaviour).
    assert result is pop
    assert result["individuals"] == pop["individuals"]
    assert result["metadata"]["n"] == 20


def test_cap_smaller_than_len_exact_count_and_order():
    pop = _population(50)
    result = subsample_population(pop, 10, seed=0)

    assert len(result["individuals"]) == 10
    assert result["metadata"]["n"] == 10

    # Original relative order preserved: the drawn ids appear in ascending order
    # (records tagged 0..49 in order, sorted indices retain that order).
    ids = [ind["id"] for ind in result["individuals"]]
    assert ids == sorted(ids)
    # Every retained row is a genuine member of the source population.
    assert set(ids) <= {ind["id"] for ind in pop["individuals"]}


def test_cap_equal_to_len_returns_full(capsys):
    pop = _population(15)
    result = subsample_population(pop, 15, seed=0)
    # The requested size is met exactly -- nothing to draw, and nothing to warn
    # about: the shortfall warning belongs to available < n alone.
    assert "WARNING" not in capsys.readouterr().out
    assert len(result["individuals"]) == 15
    assert result["metadata"]["n"] == 15
    assert [i["id"] for i in result["individuals"]] == list(range(15))


def test_cap_larger_than_len_warns_and_returns_full(capsys):
    pop = _population(8)
    result = subsample_population(pop, 100, seed=0)
    captured = capsys.readouterr()

    assert "WARNING" in captured.out
    assert result is pop
    assert len(result["individuals"]) == 8
    assert result["metadata"]["n"] == 8


def test_same_seed_same_subset():
    pop = _population(60)
    a = subsample_population(pop, 12, seed=7)
    b = subsample_population(pop, 12, seed=7)
    assert [i["id"] for i in a["individuals"]] == [i["id"] for i in b["individuals"]]


def test_different_seed_generally_different_subset():
    pop = _population(60)
    a = subsample_population(pop, 12, seed=0)
    b = subsample_population(pop, 12, seed=999)
    # Not guaranteed for every seed pair, but overwhelmingly likely for 12-of-60.
    assert [i["id"] for i in a["individuals"]] != [i["id"] for i in b["individuals"]]


@pytest.mark.parametrize("bad_n", [0, -1, -100])
def test_non_positive_n_raises(bad_n):
    pop = _population(20)
    with pytest.raises(ValueError):
        subsample_population(pop, bad_n)


def test_does_not_mutate_caller():
    pop = _population(40)
    original_individuals = pop["individuals"]
    subsample_population(pop, 5, seed=3)

    # Caller's metadata['n'] and individuals list are untouched.
    assert pop["metadata"]["n"] == 40
    assert pop["individuals"] is original_individuals
    assert len(pop["individuals"]) == 40


def test_retained_records_are_referenced_not_copied():
    pop = _population(30)
    result = subsample_population(pop, 6, seed=1)
    source_by_id = {ind["id"]: ind for ind in pop["individuals"]}
    for ind in result["individuals"]:
        assert ind is source_by_id[ind["id"]]

"""Unit tests for the ``cost_efficiency`` loader: the reconstructed-key join.

The loader's whole job is to refuse the inputs that would otherwise produce a plausible
but wrong cost figure, so most of these tests are about what it *rejects*.

Three properties carry the weight:

* **The key is reconstructed, and the reconstruction is checked.** The
  ``generation_metadata`` summary has no slug column, so its key is rebuilt through
  ``manifest_loader.axis_slug``. The same rebuild is applied to the ``model_ranking`` CSV,
  which *does* publish a slug, and a disagreement raises -- that comparison is the live
  proof, on this very data, that the rule reproduces the producer's own slug.
* **The three inputs legitimately disagree on membership.** The attrition CSV holds every
  combination the gate recorded, withdrawals included; the other two hold only the
  survivors. A withdrawal is reported, never inner-joined away; any other difference
  raises naming the key and both files.
* **An empty join is never valid.** Zero matched rows would publish an empty cost figure
  that looks like a measured absence of cost.

Fixtures build the four-part workspace on ``tmp_path`` (see
``tests/_cost_efficiency_fixtures.py``); the pricing table is in memory, so a change to
the repository's real prices cannot move an expected cost.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.cost_efficiency.loader import (
    available_countries,
    load_cost_records,
    resolve_sources,
)
from tests._cost_efficiency_fixtures import (
    COMPLEX_STRATEGY,
    COUNTRY,
    METERED_MODEL,
    SIMPLE_STRATEGY,
    UNMETERED_MODEL,
    build_base,
    make_attrition_row,
    make_pricing,
    slug_for,
    write_attrition,
    write_performance,
    write_raw_pool,
    write_telemetry,
)

_PRICING = make_pricing()


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_joins_every_surviving_combination(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY), (UNMETERED_MODEL, SIMPLE_STRATEGY)),
    )
    result = load_cost_records(base, COUNTRY, pricing=_PRICING)

    assert [r.slug for r in result.records] == sorted(
        [slug_for(METERED_MODEL, SIMPLE_STRATEGY), slug_for(UNMETERED_MODEL, SIMPLE_STRATEGY)]
    )
    assert result.membership["joined_rows"] == 2
    assert result.membership["attrition_withdrawn"] == 0


def test_cost_is_totalled_over_the_whole_generated_pool_not_the_cap(tmp_path) -> None:
    # 10 personas x (1000 in @ 1.0/M + 2000 out @ 10.0/M) = 10 * 0.021 = 0.21 USD.
    # Only 8 of them are clean, so a capped measurement would report 8/10 of this.
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),),
                      generated=10, clean=8)
    record = load_cost_records(base, COUNTRY, pricing=_PRICING).records[0]

    assert record.cost.n_personas == 10
    assert record.cost.total_cost_usd == pytest.approx(0.21)
    assert record.cost.cost_basis == "generated_pool_01_raw"


def test_unmetered_model_reports_measured_zero_and_the_flag(tmp_path) -> None:
    base = build_base(tmp_path, joined=((UNMETERED_MODEL, SIMPLE_STRATEGY),))
    record = load_cost_records(base, COUNTRY, pricing=_PRICING).records[0]

    assert record.cost.unmetered is True
    assert record.cost.total_cost_usd == 0.0
    assert record.cost.total_cost_usd is not None


def test_absent_pricing_entry_raises(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    thin = make_pricing({UNMETERED_MODEL: (0.0, 0.0)})
    with pytest.raises(KeyError, match=METERED_MODEL):
        load_cost_records(base, COUNTRY, pricing=thin)


def test_available_countries_reads_the_attrition_folder(tmp_path) -> None:
    assert available_countries(tmp_path) == []
    base = build_base(tmp_path)
    assert available_countries(base) == [COUNTRY]


def test_resolve_sources_uses_the_registry_folders(tmp_path) -> None:
    sources = resolve_sources(tmp_path, COUNTRY)
    assert sources.performance.name == f"{COUNTRY}_performance.csv"
    assert sources.attrition.name == f"{COUNTRY}_attrition.csv"
    assert sources.telemetry.name == f"{COUNTRY}_summary.csv"
    assert sources.performance.parent.name == "model_ranking"
    assert sources.attrition.parent.name == "validation_attrition"
    assert sources.telemetry.parent.name == "generation_metadata"


# ---------------------------------------------------------------------------
# Withdrawals: reported, never inner-joined away
# ---------------------------------------------------------------------------

def test_withdrawn_combination_is_reported_not_dropped(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY),),
        withdrawn=((UNMETERED_MODEL, COMPLEX_STRATEGY),),
    )
    result = load_cost_records(base, COUNTRY, pricing=_PRICING)

    assert [r.slug for r in result.records] == [slug_for(METERED_MODEL, SIMPLE_STRATEGY)]
    assert [w.slug for w in result.withdrawn] == [slug_for(UNMETERED_MODEL, COMPLEX_STRATEGY)]
    assert result.membership["attrition_rows"] == 2
    assert result.membership["attrition_withdrawn"] == 1
    assert result.withdrawn[0].reason


def test_withdrawn_combination_still_carries_its_measured_spend(tmp_path) -> None:
    # The money is the point: a withdrawn combination generated a pool and yielded
    # nothing, and this is the only artifact that can say what it cost.
    base = build_base(
        tmp_path,
        joined=((UNMETERED_MODEL, SIMPLE_STRATEGY),),
        withdrawn=((METERED_MODEL, COMPLEX_STRATEGY),),
        generated=10,
    )
    withdrawn = load_cost_records(base, COUNTRY, pricing=_PRICING).withdrawn[0]
    assert withdrawn.cost.total_cost_usd == pytest.approx(0.21)
    assert withdrawn.clean == 1


# ---------------------------------------------------------------------------
# The one-to-one assertion
# ---------------------------------------------------------------------------

def test_accuracy_row_missing_for_a_survivor_raises_naming_key_and_both_files(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY), (UNMETERED_MODEL, SIMPLE_STRATEGY)),
    )
    # Rewrite the ranking CSV without one of the two survivors.
    write_performance(base, [(METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8)])

    with pytest.raises(ValueError) as excinfo:
        load_cost_records(base, COUNTRY, pricing=_PRICING)
    message = str(excinfo.value)
    assert slug_for(UNMETERED_MODEL, SIMPLE_STRATEGY) in message
    assert "_attrition.csv" in message
    assert "_performance.csv" in message


def test_telemetry_row_missing_for_a_survivor_raises_naming_key_and_both_files(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY), (UNMETERED_MODEL, SIMPLE_STRATEGY)),
    )
    write_telemetry(base, [(METERED_MODEL, SIMPLE_STRATEGY)])

    with pytest.raises(ValueError) as excinfo:
        load_cost_records(base, COUNTRY, pricing=_PRICING)
    message = str(excinfo.value)
    assert slug_for(UNMETERED_MODEL, SIMPLE_STRATEGY) in message
    assert "_attrition.csv" in message
    assert "_summary.csv" in message


def test_accuracy_row_for_a_withdrawn_combination_raises(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY),),
        withdrawn=((UNMETERED_MODEL, COMPLEX_STRATEGY),),
    )
    write_performance(base, [
        (METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8),
        (UNMETERED_MODEL, COMPLEX_STRATEGY, 0.7, 8),
    ])

    with pytest.raises(ValueError, match="WITHDRAWN"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_accuracy_row_absent_from_attrition_entirely_raises(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    write_performance(base, [
        (METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8),
        (METERED_MODEL, COMPLEX_STRATEGY, 0.7, 8),
    ])

    with pytest.raises(ValueError) as excinfo:
        load_cost_records(base, COUNTRY, pricing=_PRICING)
    message = str(excinfo.value)
    assert slug_for(METERED_MODEL, COMPLEX_STRATEGY) in message
    assert "no row at all" in message


def test_published_slug_disagreeing_with_the_rebuild_raises(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    write_performance(
        base,
        [(METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8)],
        slug_override={(METERED_MODEL, SIMPLE_STRATEGY): "swedish_02_something_else"},
    )
    with pytest.raises(ValueError, match="axis_slug"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_duplicate_accuracy_row_raises(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    write_performance(base, [
        (METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8),
        (METERED_MODEL, SIMPLE_STRATEGY, 0.7, 8),
    ])
    with pytest.raises(ValueError, match="appears twice"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_telemetry_has_token_data_true_over_an_untelemetered_pool_raises(tmp_path) -> None:
    # The capped mirror is copied out of the generated pool, so it cannot hold telemetry
    # the pool does not.
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),), with_tokens=False)
    with pytest.raises(ValueError, match="has_token_data"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_foreign_country_row_in_the_attrition_csv_raises(tmp_path) -> None:
    build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    write_attrition(tmp_path, [
        make_attrition_row(METERED_MODEL, SIMPLE_STRATEGY),
        make_attrition_row(METERED_MODEL, SIMPLE_STRATEGY, country="italian"),
    ])
    with pytest.raises(ValueError, match="italian"):
        load_cost_records(tmp_path, COUNTRY, pricing=_PRICING)


# ---------------------------------------------------------------------------
# The empty join
# ---------------------------------------------------------------------------

def test_all_combinations_withdrawn_raises_rather_than_returning_nothing(tmp_path) -> None:
    base = build_base(tmp_path, joined=(), withdrawn=((METERED_MODEL, SIMPLE_STRATEGY),))
    with pytest.raises(ValueError, match="empty join is never a valid result"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_filter_matching_nothing_raises_rather_than_writing_an_empty_result(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    with pytest.raises(ValueError, match="empty join is never a valid result"):
        load_cost_records(base, COUNTRY, pricing=_PRICING, models=["no_such_model"])


def test_missing_input_file_raises_naming_the_producer(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    resolve_sources(base, COUNTRY).telemetry.unlink()
    with pytest.raises(FileNotFoundError, match="summarize_generation_metadata.py"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


def test_missing_raw_pool_raises(tmp_path) -> None:
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    pool = base / "01_Raw" / slug_for(METERED_MODEL, SIMPLE_STRATEGY)
    for persona in pool.glob("persona_*"):
        for child in persona.iterdir():
            child.unlink()
        persona.rmdir()
    pool.rmdir()
    with pytest.raises(FileNotFoundError, match="No raw generation pool"):
        load_cost_records(base, COUNTRY, pricing=_PRICING)


# ---------------------------------------------------------------------------
# Filtering is selection, not a verdict
# ---------------------------------------------------------------------------

def test_filter_narrows_all_three_sides_symmetrically(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY), (UNMETERED_MODEL, SIMPLE_STRATEGY)),
    )
    result = load_cost_records(base, COUNTRY, pricing=_PRICING, models=[METERED_MODEL])
    assert [r.slug for r in result.records] == [slug_for(METERED_MODEL, SIMPLE_STRATEGY)]
    assert result.membership["accuracy_rows"] == 1
    assert result.membership["telemetry_rows"] == 1


def test_slug_filter_selects_one_combination(tmp_path) -> None:
    base = build_base(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY), (METERED_MODEL, COMPLEX_STRATEGY)),
    )
    wanted = slug_for(METERED_MODEL, COMPLEX_STRATEGY)
    result = load_cost_records(base, COUNTRY, pricing=_PRICING, slugs=[wanted])
    assert [r.slug for r in result.records] == [wanted]


def test_extra_raw_pool_does_not_enter_the_join(tmp_path) -> None:
    # A pool on disk is not a combination: only the gate's record makes one.
    base = build_base(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),))
    write_raw_pool(base, slug_for(METERED_MODEL, COMPLEX_STRATEGY), n_personas=3)
    result = load_cost_records(base, COUNTRY, pricing=_PRICING)
    assert len(result.records) == 1

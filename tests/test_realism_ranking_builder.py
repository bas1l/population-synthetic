"""Unit tests for the ``realism_ranking`` builder: both axes, the tests, and the honesty block.

The load-bearing assertions here are the two directional ones -- the real population is
an ordinary ranked competitor on Axis A, and the *target* on Axis B -- because getting
either backwards silently inverts what the whole task claims. The rest pin hand-computed
rates against known fixtures, the seeded-bootstrap reproducibility, and the rule that a
test which cannot run leaves a recorded reason rather than nothing.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic.analysis.realism_ranking.builder import (  # noqa: E402
    CAVEATS,
    build_ranking,
    scb_contrast_rows,
    summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_headline_map,
    plot_impossibility_forest,
)
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord  # noqa: E402
from population_synthetic.analysis.utils.realism_csv import RealismPersonaRow  # noqa: E402

_BOOT = {"iterations": 200, "seed": 20260723, "ci_level": 0.95}
_COUNTRY = "swedish"
_PROVENANCE = {"judge_model": "claude-sonnet-5", "prompt_template_sha256": "abc", "n_rounds": 2}


def _row(pid, slug, *, impossible, typicality, model, strategy, is_real=False):
    return RealismPersonaRow(
        persona_id=pid, slug=slug, country=_COUNTRY, model=model, strategy=strategy,
        is_real_reference=is_real, n_rounds_attempted=2, n_rounds_successful=2,
        can_exist_true_votes=0 if impossible else 2, can_exist_majority=not impossible,
        typicality_mean=typicality, typicality_sd=None,
        typicality_rounds=() if typicality is None else (int(typicality),) * 2,
        max_severity="S3" if impossible else "", clash_count=1 if impossible else 0,
    )


def _record(slug, *, n_impossible, typicalities, model="claude_haiku", strategy="all_pick",
            is_real=False, dispersion=None):
    rows = [
        _row(f"persona_{i:05d}", slug, impossible=True, typicality=None,
             model=model, strategy=strategy, is_real=is_real)
        for i in range(n_impossible)
    ] + [
        _row(f"persona_{n_impossible + i:05d}", slug, impossible=False, typicality=t,
             model=model, strategy=strategy, is_real=is_real)
        for i, t in enumerate(typicalities)
    ]
    n = len(rows)
    return CompetitorRecord(
        slug=slug, country=_COUNTRY, model=model, strategy=strategy,
        is_real_reference=is_real, n_personas=n, n_failed=0, personas=tuple(rows),
        impossibility={"rate": n_impossible / n if n else None},
        dispersion=dispersion or {"variance": 4.0, "entropy": 1.5, "tail_coverage": 0.1},
        reliability={}, provenance=dict(_PROVENANCE),
        report_path=f"/fake/{slug}.json", personas_csv_path=f"/fake/{slug}_personas.csv",
    )


def _build(records, **kwargs):
    return build_ranking(records, _COUNTRY, bootstrap=_BOOT, variance_center="median", **kwargs)


# --------------------------------------------------------------------------- #
# Axis A -- the real population is an ordinary ranked competitor               #
# --------------------------------------------------------------------------- #


def test_impossibility_rate_and_denominator_are_hand_computable():
    record = _record("s1", n_impossible=2, typicalities=[5.0, 6.0, 7.0, 8.0])  # 2 of 6
    ranking = _build([record, _record("s2", n_impossible=0, typicalities=[5.0, 5.0])])
    entry = next(e for e in ranking["axis_a"]["ranking"] if e["slug"] == "s1")
    assert entry["rate"] == pytest.approx(2 / 6)
    assert entry["impossible_count"] == 2
    assert entry["denominator"] == 6


def test_real_population_is_ranked_like_any_other_competitor():
    """It appears in the ranking, and it can place anywhere -- including last."""
    worst_real = _record("real_swedish", n_impossible=4, typicalities=[5.0],
                         model="", strategy="", is_real=True)
    clean = _record("s1", n_impossible=0, typicalities=[5.0, 6.0])
    ranking = _build([clean, worst_real])

    ranked = ranking["axis_a"]["ranking"]
    assert {e["slug"] for e in ranked} == {"s1", "real_swedish"}
    # Ordered by rate ascending -- the real population placing LAST must be expressible.
    assert [e["slug"] for e in ranked] == ["s1", "real_swedish"]
    assert ranked[-1]["is_real_reference"] is True
    assert ranked[-1]["rate"] == pytest.approx(0.8)


def test_real_population_placing_first_is_equally_expressible():
    best_real = _record("real_swedish", n_impossible=0, typicalities=[5.0, 5.0],
                        model="", strategy="", is_real=True)
    dirty = _record("s1", n_impossible=3, typicalities=[5.0])
    ranking = _build([dirty, best_real])
    assert [e["slug"] for e in ranking["axis_a"]["ranking"]] == ["real_swedish", "s1"]


def test_tied_rates_share_a_rank_rather_than_being_broken_arbitrarily():
    a = _record("s1", n_impossible=1, typicalities=[5.0, 6.0, 7.0])
    b = _record("s2", n_impossible=1, typicalities=[5.0, 6.0, 7.0], model="claude_sonnet")
    ranking = _build([a, b])
    ranks = {e["slug"]: e["rank"] for e in ranking["axis_a"]["ranking"]}
    assert ranks["s1"] == ranks["s2"] == 1


def test_bootstrap_ci_is_reproducible_across_calls_with_the_same_seed():
    records = [_record("s1", n_impossible=2, typicalities=[5.0, 6.0, 7.0])]
    first = _build(records)["axis_a"]["ranking"][0]
    second = _build(records)["axis_a"]["ranking"][0]
    assert (first["ci_lo"], first["ci_hi"]) == (second["ci_lo"], second["ci_hi"])


# --------------------------------------------------------------------------- #
# Axis A -- contrasts against the real population                             #
# --------------------------------------------------------------------------- #


def test_scb_contrast_is_holm_corrected_and_carries_an_effect_size():
    real = _record("real_swedish", n_impossible=1, typicalities=[5.0] * 9,
                   model="", strategy="", is_real=True)
    a = _record("s1", n_impossible=5, typicalities=[5.0] * 5)
    b = _record("s2", n_impossible=0, typicalities=[5.0] * 10, model="claude_sonnet")
    ranking = _build([a, b, real])

    contrasts = {c["slug"]: c for c in ranking["axis_a"]["scb_contrast"]}
    assert set(contrasts) == {"s1", "s2"}          # the real competitor is not contrasted with itself
    for contrast in contrasts.values():
        assert contrast["correction"] == "holm"
        assert contrast["p_holm"] is not None
        assert contrast["p_holm"] >= contrast["p_raw"]   # Holm never shrinks a p-value
        assert contrast["effect_h"] is not None          # every p-value has an effect beside it
        assert contrast["effect_magnitude"] in {"negligible", "small", "medium", "large"}
    # diff > 0 == less coherent than the real population.
    assert contrasts["s1"]["diff"] > 0
    assert contrasts["s2"]["diff"] < 0


# --------------------------------------------------------------------------- #
# Axis B -- the real population is the TARGET (direction must not invert)      #
# --------------------------------------------------------------------------- #


def test_axis_b_distance_is_absolute_so_mode_collapse_scores_badly():
    """A collapsed spread must read as a LARGE distance, not as a good score.

    This is the assertion that guards the axis's direction: if the distance were signed
    (or if the axis were "more spread is better"), a mode-collapsed combination -- the
    documented LLM failure mode -- would look like a success.
    """
    real = _record("real_swedish", n_impossible=0, typicalities=[5.0, 5.0],
                   model="", strategy="", is_real=True,
                   dispersion={"variance": 6.0, "entropy": 2.0, "tail_coverage": 0.2})
    collapsed = _record("collapsed", n_impossible=0, typicalities=[5.0, 5.0],
                        dispersion={"variance": 0.0, "entropy": 0.0, "tail_coverage": 0.0})
    over_spread = _record("over", n_impossible=0, typicalities=[1.0, 9.0],
                          model="claude_sonnet",
                          dispersion={"variance": 12.0, "entropy": 4.0, "tail_coverage": 0.4})
    ranking = _build([collapsed, over_spread, real])

    rows = {r["slug"]: r for r in ranking["axis_b"]["dispersion_contrast"]}
    assert rows["collapsed"]["distance_to_scb"]["variance"] == pytest.approx(6.0)
    assert rows["over"]["distance_to_scb"]["variance"] == pytest.approx(6.0)
    # Symmetric: collapsing is penalised exactly as much as over-spreading.
    assert (rows["collapsed"]["distance_to_scb"]["variance"]
            == rows["over"]["distance_to_scb"]["variance"])
    assert ranking["axis_definitions"]["B"]["real_population_role"].startswith("the target")


def test_axis_b_variance_equality_test_is_present_per_competitor():
    real = _record("real_swedish", n_impossible=0, typicalities=[5.0, 5.0, 6.0],
                   model="", strategy="", is_real=True)
    syn = _record("s1", n_impossible=0, typicalities=[1.0, 9.0, 4.0])
    ranking = _build([syn, real])
    row = ranking["axis_b"]["dispersion_contrast"][0]
    assert row["variance_equality"]["center"] == "median"
    assert "statistic" in row["variance_equality"]


# --------------------------------------------------------------------------- #
# factor significance                                                          #
# --------------------------------------------------------------------------- #


def _factor_fixture():
    """Two models x two methods, plus the real competitor."""
    records = []
    for model, base in (("claude_haiku", 3.0), ("claude_sonnet", 7.0)):
        for strategy in ("all_pick", "all_pick_dag"):
            records.append(_record(
                f"swedish_{strategy}_{model}", n_impossible=1,
                typicalities=[base, base + 1, base + 2, base - 1],
                model=model, strategy=strategy,
            ))
    records.append(_record("real_swedish", n_impossible=0, typicalities=[5.0, 5.0, 6.0],
                           model="", strategy="", is_real=True))
    return records


def test_real_competitor_is_held_out_of_the_factor_tests():
    ranking = _build(_factor_fixture())
    groups = ranking["factor_significance"]["by_model"]["groups"]
    assert set(groups) == {"claude_haiku", "claude_sonnet"}   # no "" level from the real one
    assert ranking["factor_significance"]["real_competitor_held_out"] is True
    # ... while it IS present in the Axis A ranking.
    assert any(e["is_real_reference"] for e in ranking["axis_a"]["ranking"])


def test_kruskal_and_dunn_are_holm_corrected():
    ranking = _build(_factor_fixture())
    block = ranking["factor_significance"]["by_model"]
    assert block["kruskal"]["p"] is not None
    assert block["correction"] == "holm"
    assert all("p_holm" in pair for pair in block["dunn"])


def test_single_factor_level_is_skipped_with_a_reason_not_a_nan():
    records = [
        _record("s1", n_impossible=1, typicalities=[5.0, 6.0]),
        _record("s2", n_impossible=1, typicalities=[5.0, 6.0], strategy="all_pick_dag"),
    ]  # one model level only
    ranking = _build(records)
    assert ranking["factor_significance"]["by_model"]["kruskal"] is None
    reasons = {s["test"]: s["reason"] for s in ranking["skipped_tests"]}
    assert "kruskal_by_model" in reasons
    assert "levels" in reasons["kruskal_by_model"]


def test_mixed_logit_degenerate_design_is_skipped_with_a_reason():
    records = [_record("s1", n_impossible=1, typicalities=[5.0, 6.0])]  # 1 model, 1 method
    ranking = _build(records)
    reasons = {s["test"]: s["reason"] for s in ranking["skipped_tests"]}
    assert "mixed_logit_can_exist" in reasons
    assert ranking["factor_significance"]["mixed_logit_can_exist"] is None


def test_mixed_logit_fits_on_a_full_design_or_records_why_not():
    """On a 2x2 design the mixed model either fits or leaves an explicit reason."""
    ranking = _build(_factor_fixture())
    fitted = ranking["factor_significance"]["mixed_logit_can_exist"]
    skipped = {s["test"] for s in ranking["skipped_tests"]}
    assert (fitted is not None) ^ ("mixed_logit_can_exist" in skipped)
    if fitted is not None:
        assert "logit" in fitted["method"].lower()
        assert fitted["n_combinations"] == 4


# --------------------------------------------------------------------------- #
# honesty block + degenerate inputs                                            #
# --------------------------------------------------------------------------- #


def test_ranking_records_every_mandatory_honesty_field():
    ranking = _build(_factor_fixture(), skipped_combinations=[("swedish_x_y", "no report")])
    assert ranking["axis_a"]["correction"] == "holm"
    assert [c["id"] for c in ranking["caveats"]] == [c["id"] for c in CAVEATS]
    assert {c["id"] for c in ranking["caveats"]} == {
        "pseudo_replication", "single_run_per_combination"
    }
    assert ranking["skipped_combinations"] == [{"slug": "swedish_x_y", "reason": "no report"}]
    prov = ranking["provenance"]
    assert prov["bootstrap_seed"] == _BOOT["seed"]
    assert set(prov["library_versions"]) == {"numpy", "scipy", "statsmodels", "scikit_posthocs"}
    assert prov["judge_model"] == "claude-sonnet-5"
    assert len(prov["consumed_artifacts"]) == ranking["n_competitors"]
    # Every rate carries its denominator.
    assert all("denominator" in e for e in ranking["axis_a"]["ranking"])


def test_absent_real_competitor_skips_both_contrasts_with_a_reason_but_still_ranks():
    records = [
        _record("s1", n_impossible=1, typicalities=[5.0, 6.0]),
        _record("s2", n_impossible=0, typicalities=[5.0, 6.0], model="claude_sonnet"),
    ]
    ranking = _build(records)
    assert len(ranking["axis_a"]["ranking"]) == 2       # Axis A still runs
    assert ranking["axis_a"]["scb_contrast"] == []
    reasons = {s["test"] for s in ranking["skipped_tests"]}
    assert {"axis_a_scb_contrast", "axis_b_dispersion_contrast"} <= reasons
    assert ranking["real_competitor"] is None


def test_every_competitor_impossible_free_still_ranks_without_dividing_by_zero():
    records = [
        _record("s1", n_impossible=0, typicalities=[5.0, 6.0]),
        _record("s2", n_impossible=0, typicalities=[5.0, 6.0], model="claude_sonnet"),
    ]
    ranking = _build(records)
    assert all(e["rate"] == pytest.approx(0.0) for e in ranking["axis_a"]["ranking"])
    assert all(e["rank"] == 1 for e in ranking["axis_a"]["ranking"])  # explicit tie


def test_combination_with_no_successful_persona_has_no_rate_and_ranks_last():
    empty = CompetitorRecord(
        slug="dead", country=_COUNTRY, model="claude_haiku", strategy="all_pick",
        is_real_reference=False, n_personas=0, n_failed=7, personas=(),
        impossibility={"rate": None}, dispersion={}, reliability={},
        provenance=dict(_PROVENANCE), report_path="/fake/dead.json",
        personas_csv_path="/fake/dead_personas.csv",
    )
    ranking = _build([empty, _record("s1", n_impossible=1, typicalities=[5.0, 6.0])])
    last = ranking["axis_a"]["ranking"][-1]
    assert last["slug"] == "dead"
    assert last["rate"] is None          # not an imputed 0.0
    assert last["denominator"] == 0
    assert last["n_failed"] == 7


# --------------------------------------------------------------------------- #
# CSV rows + charts                                                            #
# --------------------------------------------------------------------------- #


def test_summary_and_contrast_rows_are_flat_and_complete():
    ranking = _build(_factor_fixture())
    summary = summary_rows(ranking)
    assert len(summary) == ranking["n_competitors"]
    assert summary[0]["rank"] == 1
    assert all("denominator" in row for row in summary)

    contrast = scb_contrast_rows(ranking)
    assert len(contrast) == ranking["n_synthetic"]
    assert all(row["correction"] == "holm" for row in contrast)
    assert all("effect_h" in row and "p_holm" in row for row in contrast)


def test_charts_render_from_a_built_ranking():
    ranking = _build(_factor_fixture())
    assert plot_headline_map(ranking) is not None
    assert plot_impossibility_forest(ranking) is not None


def test_charts_raise_rather_than_emitting_an_empty_figure():
    empty = CompetitorRecord(
        slug="dead", country=_COUNTRY, model="m", strategy="s", is_real_reference=False,
        n_personas=0, n_failed=1, personas=(), impossibility={"rate": None},
        dispersion={}, reliability={}, provenance=dict(_PROVENANCE),
        report_path="/fake/dead.json", personas_csv_path="/fake/dead_personas.csv",
    )
    ranking = _build([empty])
    with pytest.raises(ValueError):
        plot_headline_map(ranking)
    with pytest.raises(ValueError):
        plot_impossibility_forest(ranking)

"""Unit tests for the ``realism_ranking`` builder: both axes, the tests, and the honesty block.

The load-bearing assertions here are the two directional ones -- the real population is
an ordinary ranked competitor on Axis A, and the *target* on Axis B -- because getting
either backwards silently inverts what the whole task claims. The rest pin hand-computed
rates against known fixtures, the seeded-bootstrap reproducibility, and the rule that a
test which cannot run leaves a recorded reason rather than nothing.
"""

from __future__ import annotations

import dataclasses

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic.analysis.realism_ranking.builder import (  # noqa: E402
    CAVEATS,
    build_ranking,
    scb_contrast_rows,
    severity_driver_rows,
    severity_driver_value_rows,
    summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_headline_map,
    plot_impossibility_forest,
    plot_impossibility_heatmap,
    plot_severity_heatmap,
)
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord  # noqa: E402
from population_synthetic.analysis.utils.realism_clash_csv import RealismClashRow  # noqa: E402
from population_synthetic.analysis.utils.realism_csv import (  # noqa: E402
    SEVERITY_LEVELS,
    SEVERITY_RANK,
    RealismPersonaRow,
)

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
    # The driver bounds are required arguments (the builder reads no config), so the
    # helper pins permissive ones; the tests that are *about* them pass their own.
    kwargs.setdefault("driver_top_n", 3)
    kwargs.setdefault("driver_min_count", 1)
    return build_ranking(records, _COUNTRY, bootstrap=_BOOT, variance_center="median", **kwargs)


# --------------------------------------------------------------------------- #
# Axis A -- the real population is an ordinary ranked competitor               #
# --------------------------------------------------------------------------- #


def test_impossibility_rate_and_denominator_are_hand_computable():
    record = _record("s1", n_impossible=2, typicalities=[5.0, 6.0, 7.0, 8.0])  # 2 of 6
    ranking = _build([
        record,
        # A distinct model: two competitors may not share one model x method cell.
        _record("s2", n_impossible=0, typicalities=[5.0, 5.0], model="claude_sonnet"),
    ])
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
    ranking = _build([
        empty,
        _record("s1", n_impossible=1, typicalities=[5.0, 6.0], model="claude_sonnet"),
    ])
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
    assert plot_impossibility_heatmap(ranking) is not None


# --------------------------------------------------------------------------- #
# Axis A grid (model x method heatmap input)                                   #
# --------------------------------------------------------------------------- #


def test_grid_places_each_combination_at_its_model_method_coordinate():
    ranking = _build(_factor_fixture())
    grid = ranking["axis_a"]["grid"]
    assert grid["models"] == ["claude_haiku", "claude_sonnet"]
    assert grid["methods"] == ["all_pick", "all_pick_dag"]
    for model in grid["models"]:
        for method in grid["methods"]:
            cell = grid["cells"][model][method]
            assert cell is not None, (model, method)
            assert cell["slug"] == f"swedish_{method}_{model}"
            assert cell["denominator"] == 5          # 1 impossible + 4 possible
            assert cell["rate"] == pytest.approx(1 / 5)


def test_grid_rates_equal_the_ranking_rates():
    """The heatmap and the forest plot can never disagree: one source, not two."""
    ranking = _build(_factor_fixture())
    grid = ranking["axis_a"]["grid"]
    by_slug = {e["slug"]: e for e in ranking["axis_a"]["ranking"]}
    for model in grid["models"]:
        for method in grid["methods"]:
            cell = grid["cells"][model][method]
            entry = by_slug[cell["slug"]]
            assert cell["rate"] == entry["rate"]
            assert (cell["ci_lo"], cell["ci_hi"]) == (entry["ci_lo"], entry["ci_hi"])
            assert cell["denominator"] == entry["denominator"]


def test_unjudged_pair_is_none_not_zero():
    """The load-bearing guard: an absent cell must never read as a perfect score.

    A rate of 0.0 is the BEST possible result. Rendering an unjudged combination at
    zero would report a combination nobody judged as the most coherent in the sweep.
    """
    records = [
        _record("swedish_all_pick_claude_haiku", n_impossible=1, typicalities=[5.0, 6.0],
                model="claude_haiku", strategy="all_pick"),
        _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0, typicalities=[5.0, 6.0],
                model="claude_sonnet", strategy="all_pick_dag"),
    ]  # the other two corners of the 2x2 were never judged
    grid = _build(records)["axis_a"]["grid"]

    assert grid["cells"]["claude_haiku"]["all_pick_dag"] is None
    assert grid["cells"]["claude_sonnet"]["all_pick"] is None
    # ... and the judged corners are present, one of them with a genuine 0.0.
    assert grid["cells"]["claude_haiku"]["all_pick"]["rate"] == pytest.approx(1 / 3)
    assert grid["cells"]["claude_sonnet"]["all_pick_dag"]["rate"] == pytest.approx(0.0)
    assert "NOT an impossibility rate of zero" in grid["note"]


def test_real_population_is_carried_separately_and_is_not_a_grid_cell():
    ranking = _build(_factor_fixture())
    grid = ranking["axis_a"]["grid"]
    assert grid["real"]["slug"] == "real_swedish"
    assert grid["real"]["rate"] == pytest.approx(0.0)
    assert grid["real"]["denominator"] == 3
    # It has no model/method, so it must not appear anywhere in the grid proper.
    assert "" not in grid["models"] and "" not in grid["methods"]
    assert "real_swedish" not in grid["models"]
    slugs = {
        cell["slug"]
        for row in grid["cells"].values() for cell in row.values() if cell is not None
    }
    assert "real_swedish" not in slugs


def test_grid_real_is_none_without_a_real_competitor_and_the_heatmap_still_renders():
    records = [r for r in _factor_fixture() if not r.is_real_reference]
    ranking = _build(records)
    assert ranking["axis_a"]["grid"]["real"] is None
    assert plot_impossibility_heatmap(ranking) is not None


def test_heatmap_raises_rather_than_emitting_an_empty_figure():
    empty = CompetitorRecord(
        slug="dead", country=_COUNTRY, model="m", strategy="s", is_real_reference=False,
        n_personas=0, n_failed=1, personas=(), impossibility={"rate": None},
        dispersion={}, reliability={}, provenance=dict(_PROVENANCE),
        report_path="/fake/dead.json", personas_csv_path="/fake/dead_personas.csv",
    )
    with pytest.raises(ValueError):
        plot_impossibility_heatmap(_build([empty]))


def test_duplicate_grid_coordinate_raises_naming_both_slugs():
    """Slugs are unique by construction, so a duplicate cell means a corrupt input."""
    a = _record("swedish_all_pick_claude_haiku", n_impossible=1, typicalities=[5.0])
    b = _record("swedish_all_pick_claude_haiku_copy", n_impossible=0, typicalities=[5.0])
    with pytest.raises(ValueError, match="same grid cell"):
        _build([a, b])


def test_synthetic_competitor_without_a_coordinate_raises():
    orphan = _record("swedish_orphan", n_impossible=1, typicalities=[5.0],
                     model="", strategy="")
    with pytest.raises(ValueError, match="missing its model/method coordinate"):
        _build([orphan])


# --------------------------------------------------------------------------- #
# severity dimension (reporting only, one grid per level)                      #
# --------------------------------------------------------------------------- #


def _with_severities(record, per_persona):
    """Stamp per-persona (s1, s2, s3) distinct-clash counts onto a fixture record."""
    rows = tuple(
        dataclasses.replace(row, clash_count_s1=s1, clash_count_s2=s2, clash_count_s3=s3,
                            clash_count=s1 + s2 + s3)
        for row, (s1, s2, s3) in zip(record.personas, per_persona)
    )
    return dataclasses.replace(record, personas=rows)


def _severity_fixture():
    """Four personas per combination, with a deliberate S3+S2 double-carrier."""
    a = _record("swedish_all_pick_claude_haiku", n_impossible=1, typicalities=[5.0] * 3,
                model="claude_haiku", strategy="all_pick")
    # persona 0 carries an S3 AND an S2; persona 1 carries an S1; personas 2-3 are clean.
    a = _with_severities(a, [(0, 1, 1), (1, 0, 0), (0, 0, 0), (0, 0, 0)])
    b = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0, typicalities=[5.0] * 4,
                model="claude_sonnet", strategy="all_pick_dag")
    b = _with_severities(b, [(0, 0, 0)] * 4)
    real = _record("real_swedish", n_impossible=0, typicalities=[5.0] * 4,
                   model="", strategy="", is_real=True)
    real = _with_severities(real, [(1, 0, 0), (0, 1, 0), (0, 0, 0), (0, 0, 0)])
    return [a, b, real]


def test_severity_levels_are_counted_independently_not_as_a_partition():
    """The load-bearing property: a persona with both an S3 and an S2 is in BOTH grids.

    A ``max_severity``-based implementation would file that persona under S3 alone, so
    the S2 grid would report 0.0 -- indistinguishable from a combination with no
    near-impossible pairings at all.
    """
    ranking = _build(_severity_fixture())
    levels = ranking["severity"]["levels"]

    s3 = levels["S3"]["grid"]["cells"]["claude_haiku"]["all_pick"]
    s2 = levels["S2"]["grid"]["cells"]["claude_haiku"]["all_pick"]
    # One of four personas carries an S3; the SAME persona also carries an S2.
    assert s3["affected"] == 1 and s3["rate"] == pytest.approx(0.25) and s3["denominator"] == 4
    assert s2["affected"] == 1 and s2["rate"] == pytest.approx(0.25) and s2["denominator"] == 4

    s1 = levels["S1"]["grid"]["cells"]["claude_haiku"]["all_pick"]
    assert s1["affected"] == 1 and s1["rate"] == pytest.approx(0.25)


def test_persona_with_no_clash_appears_in_no_severity_grid():
    ranking = _build(_severity_fixture())
    for level in ("S1", "S2", "S3"):
        cell = ranking["severity"]["levels"][level]["grid"]["cells"]["claude_sonnet"]["all_pick_dag"]
        assert cell["affected"] == 0
        assert cell["rate"] == pytest.approx(0.0)   # a real, measured zero
        assert cell["denominator"] == 4


def test_severity_grid_unjudged_pair_is_none_not_zero():
    ranking = _build(_severity_fixture())
    for level in ("S1", "S2", "S3"):
        cells = ranking["severity"]["levels"][level]["grid"]["cells"]
        assert cells["claude_haiku"]["all_pick_dag"] is None
        assert cells["claude_sonnet"]["all_pick"] is None
        assert f"NOT an {level} prevalence of zero" in \
            ranking["severity"]["levels"][level]["grid"]["note"]


def test_severity_real_population_is_a_separate_entry_not_a_grid_cell():
    ranking = _build(_severity_fixture())
    for level, expected in (("S1", 0.25), ("S2", 0.25), ("S3", 0.0)):
        grid = ranking["severity"]["levels"][level]["grid"]
        assert grid["real"]["slug"] == "real_swedish"
        assert grid["real"]["rate"] == pytest.approx(expected)
        assert "real_swedish" not in grid["models"]


def test_s1_is_declared_not_penalised_while_s2_and_s3_are():
    """Direction is per level. Colouring S1 as a defect would assert unusual == wrong."""
    levels = _build(_severity_fixture())["severity"]["levels"]
    assert levels["S1"]["penalised"] is False
    assert "never penalised" in levels["S1"]["direction"]
    for level in ("S2", "S3"):
        assert levels[level]["penalised"] is True
        assert "lower is better" in levels[level]["direction"]


def test_severity_block_declares_itself_reporting_only():
    ranking = _build(_severity_fixture())
    block = ranking["severity"]
    assert "no ranking" in block["reporting_only"]
    assert "independently" in block["independent_levels"]
    # It must not have leaked into the ranking, the contrasts or the factor tests.
    assert "severity" not in ranking["axis_a"]
    assert all("severity" not in entry for entry in ranking["axis_a"]["ranking"])


def test_severity_charts_render_and_raise_on_an_empty_ranking():
    ranking = _build(_severity_fixture())
    for level in ("S1", "S2", "S3"):
        assert plot_severity_heatmap(ranking, level) is not None
    with pytest.raises(KeyError, match="Unknown severity level"):
        plot_severity_heatmap(ranking, "S9")

    empty = CompetitorRecord(
        slug="dead", country=_COUNTRY, model="m", strategy="s", is_real_reference=False,
        n_personas=0, n_failed=1, personas=(), impossibility={"rate": None},
        dispersion={}, reliability={}, provenance=dict(_PROVENANCE),
        report_path="/fake/dead.json", personas_csv_path="/fake/dead_personas.csv",
    )
    dead = _build([empty])
    for level in ("S1", "S2", "S3"):
        with pytest.raises(ValueError):
            plot_severity_heatmap(dead, level)


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


# --------------------------------------------------------------------------- #
# severity drivers (what clashed -- reporting only, one grid per level)         #
# --------------------------------------------------------------------------- #


def _clash(record, persona_index, pair, values, severity, *, round_index=0, unresolved=False):
    """One per-clash contract row for *record*'s persona at *persona_index*."""
    persona = record.personas[persona_index]
    return RealismClashRow(
        persona_id=persona.persona_id, slug=record.slug, country=_COUNTRY,
        model=record.model, strategy=record.strategy,
        is_real_reference=record.is_real_reference, round_index=round_index,
        attr_a=pair[0], attr_b=pair[1],
        value_a="" if unresolved else values[0], value_b="" if unresolved else values[1],
        severity=severity, unresolved=unresolved,
    )


def _with_clashes(record, clashes):
    """Attach clash rows and derive the per-persona counts they imply.

    Mirrors the loader's reconciliation invariant inside the fixture: the per-persona
    ``clash_count_s{L}`` columns are the count of *distinct* ``(pair, severity)``
    clashes per persona, so a fixture that set them independently could assert a
    denominator agreement that only holds because both sides were hand-written.
    """
    distinct = {}
    for row in clashes:
        distinct.setdefault(row.persona_id, set()).add((row.attr_a, row.attr_b, row.severity))
    personas = []
    for persona in record.personas:
        seen = distinct.get(persona.persona_id, set())
        counts = {level: sum(1 for *_, s in seen if s == level) for level in ("S1", "S2", "S3")}
        personas.append(dataclasses.replace(
            persona, clash_count_s1=counts["S1"], clash_count_s2=counts["S2"],
            clash_count_s3=counts["S3"], clash_count=sum(counts.values()),
        ))
    return dataclasses.replace(record, personas=tuple(personas), clashes=tuple(clashes))


_AGE_EDU = ("age_group", "education_level")
_CIVIL_HOUSEHOLD = ("civil_status", "household_size")
_EMPLOYMENT = ("employment_status", "employment_type")


def _driver_fixture():
    """Four personas per competitor, with a hand-computable S3 driver ranking.

    Competitor A's S3 clashes: ``age_group x education_level`` in personas 0, 1 and 2
    (persona 0 in two rounds -- the round collapse), and ``civil_status x
    household_size`` in persona 0 alone. Its S2 clash sits on persona 3, so the two
    levels do not partition the personas.
    """
    a = _record("swedish_all_pick_claude_haiku", n_impossible=1, typicalities=[5.0] * 3,
                model="claude_haiku", strategy="all_pick")
    a = _with_clashes(a, [
        _clash(a, 0, _AGE_EDU, ("16-19", "Doctorate"), "S3"),
        _clash(a, 0, _AGE_EDU, ("16-19", "Doctorate"), "S3", round_index=1),
        _clash(a, 1, _AGE_EDU, ("16-19", "Doctorate"), "S3"),
        _clash(a, 2, _AGE_EDU, ("20-24", "Doctorate"), "S3"),
        _clash(a, 0, _CIVIL_HOUSEHOLD, ("Married", "1"), "S3"),
        _clash(a, 3, _EMPLOYMENT, ("Student", "Permanent Full-time"), "S2"),
    ])
    b = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0, typicalities=[5.0] * 4,
                model="claude_sonnet", strategy="all_pick_dag")
    b = _with_clashes(b, [])
    real = _record("real_swedish", n_impossible=0, typicalities=[5.0] * 4,
                   model="", strategy="", is_real=True)
    real = _with_clashes(real, [
        _clash(real, 0, ("civil_status", "housing_tenure"), ("Married", "Rented"), "S1"),
        _clash(real, 1, ("civil_status", "housing_tenure"), ("Married", "Rented"), "S1"),
    ])
    return [a, b, real]


def _cell(ranking, level, model="claude_haiku", method="all_pick"):
    return ranking["severity_drivers"]["levels"][level]["grid"]["cells"][model][method]


def test_drivers_rank_attribute_pairs_by_the_personas_that_exhibit_them():
    cell = _cell(_build(_driver_fixture()), "S3")
    assert cell["denominator"] == 4
    assert [(d["rank"], d["attr_a"], d["attr_b"], d["n_personas"]) for d in cell["drivers"]] == [
        (1, "age_group", "education_level", 3),
        (2, "civil_status", "household_size", 1),
    ]
    assert cell["drivers"][0]["prevalence"] == pytest.approx(3 / 4)
    assert cell["drivers"][1]["prevalence"] == pytest.approx(1 / 4)


def test_a_clash_repeated_across_rounds_counts_its_persona_once():
    """The counting unit is the persona; persona 0 raised the same pair in two rounds."""
    cell = _cell(_build(_driver_fixture()), "S3")
    top = cell["drivers"][0]
    assert top["n_personas"] == 3          # not 4, which is the row count
    assert cell["affected"] == 3


def test_nested_category_pairs_are_ranked_under_their_attribute_pair():
    top = _cell(_build(_driver_fixture()), "S3")["drivers"][0]
    assert [(v["rank"], v["value_a"], v["value_b"], v["n_personas"]) for v in top["values"]] == [
        (1, "16-19", "Doctorate", 2),
        (2, "20-24", "Doctorate", 1),
    ]
    # Value prevalences share the cell's denominator, so they read against the heatmap.
    assert top["values"][0]["prevalence"] == pytest.approx(2 / 4)


def test_driver_denominators_equal_the_severity_grid_cell_denominators():
    """The load-bearing agreement: a driver prevalence is readable against its heatmap.

    If these two denominators could differ, a cell could report a driver prevalence
    above its own severity rate -- arithmetically impossible for a subset, and a sure
    sign the numerator and denominator came from different persona sets.
    """
    ranking = _build(_driver_fixture())
    for level in ("S1", "S2", "S3"):
        prevalence_grid = ranking["severity"]["levels"][level]["grid"]
        driver_grid = ranking["severity_drivers"]["levels"][level]["grid"]
        assert driver_grid["models"] == prevalence_grid["models"]
        assert driver_grid["methods"] == prevalence_grid["methods"]
        for model in driver_grid["models"]:
            for method in driver_grid["methods"]:
                left = prevalence_grid["cells"][model][method]
                right = driver_grid["cells"][model][method]
                assert (left is None) == (right is None), (level, model, method)
                if left is None:
                    continue
                assert right["denominator"] == left["denominator"]
                assert right["affected"] == left["affected"]
        assert driver_grid["real"]["denominator"] == prevalence_grid["real"]["denominator"]
        assert driver_grid["real"]["affected"] == prevalence_grid["real"]["affected"]


def test_tie_break_is_total_so_equal_counts_always_rank_in_the_same_order():
    """Two pairs at the same count must not swap between runs, or ranks are noise."""
    record = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[5.0] * 2)
    rows = [
        _clash(record, 0, ("zebra_axis", "zulu_axis"), ("x", "y"), "S3"),
        _clash(record, 1, ("zebra_axis", "zulu_axis"), ("x", "y"), "S3"),
        _clash(record, 0, ("alpha_axis", "beta_axis"), ("p", "q"), "S3"),
        _clash(record, 1, ("alpha_axis", "beta_axis"), ("p", "q"), "S3"),
    ]
    forward = _build([_with_clashes(record, rows)])
    reverse = _build([_with_clashes(record, list(reversed(rows)))])

    ranked = [(d["attr_a"], d["n_personas"]) for d in _cell(forward, "S3")["drivers"]]
    assert ranked == [("alpha_axis", 2), ("zebra_axis", 2)]   # equal counts, name order
    assert _cell(forward, "S3") == _cell(reverse, "S3")       # and order-independent


def test_min_count_suppression_is_counted_rather_than_silently_dropped():
    ranking = _build(_driver_fixture(), driver_min_count=2)
    cell = _cell(ranking, "S3")
    assert [d["attr_a"] for d in cell["drivers"]] == ["age_group"]   # the n=1 pair is gone
    assert cell["n_distinct_pairs"] == 2
    assert cell["n_suppressed"] == 1
    assert ranking["severity_drivers"]["excluded"]["drivers_below_min_count"] >= 1
    assert ranking["severity_drivers"]["min_count"] == 2


def test_top_n_truncation_is_counted_separately_from_suppression():
    ranking = _build(_driver_fixture(), driver_top_n=1, driver_min_count=1)
    cell = _cell(ranking, "S3")
    assert len(cell["drivers"]) == 1
    assert cell["n_truncated"] == 1
    assert cell["n_suppressed"] == 0
    assert ranking["severity_drivers"]["excluded"]["drivers_below_top_n"] >= 1


@pytest.mark.parametrize("kwargs", [{"driver_top_n": 0}, {"driver_min_count": 0}])
def test_degenerate_driver_bounds_raise_rather_than_emitting_an_empty_table(kwargs):
    with pytest.raises(ValueError):
        _build(_driver_fixture(), **kwargs)


def test_a_cell_every_persona_shares_a_clash_in_reaches_prevalence_one():
    record = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[5.0] * 3)
    record = _with_clashes(record, [
        _clash(record, i, _EMPLOYMENT, ("Student", "Permanent Full-time"), "S3")
        for i in range(3)
    ])
    cell = _cell(_build([record]), "S3")
    assert cell["drivers"][0]["prevalence"] == pytest.approx(1.0)
    assert cell["drivers"][0]["values"][0]["prevalence"] == pytest.approx(1.0)


def test_a_clash_free_cell_has_an_empty_driver_list_and_no_skip():
    ranking = _build(_driver_fixture())
    cell = _cell(ranking, "S3", model="claude_sonnet", method="all_pick_dag")
    assert cell["drivers"] == []
    assert cell["affected"] == 0 and cell["denominator"] == 4
    assert not [s for s in ranking["skipped_tests"] if s["test"].startswith("severity_drivers")]


def test_unjudged_pair_is_none_in_the_driver_grid_not_an_empty_driver_list():
    """An empty list means "judged, nothing drove it"; None means "never judged"."""
    ranking = _build(_driver_fixture())
    cells = ranking["severity_drivers"]["levels"]["S3"]["grid"]["cells"]
    assert cells["claude_haiku"]["all_pick_dag"] is None
    assert cells["claude_sonnet"]["all_pick"] is None


def test_a_cell_whose_clash_rows_are_missing_records_a_skip_not_a_silent_zero():
    """Personas declaring a clash with no per-clash row cannot be attributed."""
    record = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[5.0] * 2)
    record = _with_severities(record, [(0, 0, 1), (0, 0, 0)])   # counts, but no clash rows
    ranking = _build([record])
    cell = _cell(ranking, "S3")
    assert cell["affected"] == 1 and cell["drivers"] == []
    reasons = {s["test"]: s["reason"] for s in ranking["skipped_tests"]}
    assert "severity_drivers[S3][swedish_all_pick_claude_haiku]" in reasons
    assert "--rewrite-artifacts" in reasons["severity_drivers[S3][swedish_all_pick_claude_haiku]"]


def test_unresolved_clashes_count_at_the_pair_grain_and_are_absent_from_the_values():
    """The pair is known and the clash is real; only its category values are not."""
    record = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[5.0] * 2)
    record = _with_clashes(record, [
        _clash(record, 0, _AGE_EDU, ("", ""), "S3", unresolved=True),
        _clash(record, 1, _AGE_EDU, ("16-19", "Doctorate"), "S3"),
    ])
    ranking = _build([record], driver_min_count=1)
    driver = _cell(ranking, "S3")["drivers"][0]
    assert driver["n_personas"] == 2               # both personas exhibit the pair
    assert driver["n_personas_unresolved"] == 1
    assert [v["n_personas"] for v in driver["values"]] == [1]   # only the resolved one
    assert ranking["severity_drivers"]["n_unresolved"] == 1
    assert ranking["severity_drivers"]["excluded"]["clashes_unresolved"] == 1


def test_driver_block_declares_itself_reporting_only_and_does_not_leak():
    ranking = _build(_driver_fixture())
    block = ranking["severity_drivers"]
    assert "no ranking" in block["reporting_only"]
    assert "not shares of a whole" in block["non_additive"]
    assert "personas, not clashes" in block["counting_unit"]
    # It must not have reached the ranking, the contrasts or the factor tests.
    assert "severity_drivers" not in ranking["axis_a"]
    assert all("severity_drivers" not in entry for entry in ranking["axis_a"]["ranking"])
    assert all("severity_drivers" not in row for row in ranking["axis_a"]["scb_contrast"])
    assert all("severity_drivers" not in row for row in ranking["axis_b"]["dispersion_contrast"])
    assert "severity_drivers" not in ranking["factor_significance"]
    assert all("severity_drivers" not in row for row in summary_rows(ranking))
    assert all("severity_drivers" not in row for row in scb_contrast_rows(ranking))


def test_drivers_change_no_number_the_ranking_already_published():
    """Same records, tighter driver bounds: every published number must be identical."""
    records = _driver_fixture()
    loose = _build(records, driver_top_n=3, driver_min_count=1)
    tight = _build(records, driver_top_n=1, driver_min_count=3)
    for key in ("axis_a", "axis_b", "severity"):
        assert loose[key] == tight[key], key
    # The mixed model is excluded: its variational fit is not bit-reproducible between
    # two calls, which is a property of the fitter and would mask, not reveal, a leak.
    for factor in ("by_model", "by_method"):
        assert loose["factor_significance"][factor] == tight["factor_significance"][factor]


# --------------------------------------------------------------------------- #
# severity driver CSV rows                                                     #
# --------------------------------------------------------------------------- #


def test_driver_rows_carry_the_denominator_the_penalised_flag_and_the_counting_unit():
    ranking = _build(_driver_fixture())
    rows = [row for row in severity_driver_rows(ranking) if row["severity"] == "S3"]
    assert rows, "the fixture has S3 drivers"
    for row in rows:
        assert row["penalised"] is True
        assert row["denominator"] == 4
        assert "personas, not clashes" in row["counting_unit"]
        assert "do not sum" in row["non_additive"]
    top = rows[0]
    assert (top["slug"], top["rank"], top["attr_a"]) == (
        "swedish_all_pick_claude_haiku", 1, "age_group")
    assert top["prevalence"] == pytest.approx(3 / 4)


def test_driver_value_rows_carry_their_parent_pair():
    rows = [row for row in severity_driver_value_rows(_build(_driver_fixture()))
            if row["severity"] == "S3"]
    top = rows[0]
    assert (top["attr_a"], top["attr_b"]) == _AGE_EDU
    assert (top["pair_rank"], top["pair_n_personas"]) == (1, 3)
    assert (top["value_a"], top["value_b"], top["n_personas"]) == ("16-19", "Doctorate", 2)
    assert top["penalised"] is True


def test_s1_driver_rows_declare_themselves_not_penalised():
    """An S1 row read alone must not look like a defect row.

    Load-bearing in the merged table: S1 rows sit beside S3 rows in the same file, and
    ``penalised`` is the only column that tells a defect from an unusual-but-possible
    pairing.
    """
    rows = severity_driver_rows(_build(_driver_fixture()))
    s1 = [row for row in rows if row["severity"] == "S1"]
    assert s1, "the real competitor carries an S1 clash"
    assert all(row["penalised"] is False for row in s1)
    assert all(row["penalised"] is True for row in rows if row["severity"] in ("S2", "S3"))


def test_driver_tables_hold_every_level_in_one_file_with_severity_as_a_column():
    """One table per grain, not one per level: all three levels are present, in rank order."""
    ranking = _build(_driver_fixture())
    for rows in (severity_driver_rows(ranking), severity_driver_value_rows(ranking)):
        assert {row["severity"] for row in rows} == set(SEVERITY_LEVELS)
        # `severity` is an identity column: it precedes every number on the row.
        keys = list(rows[0])
        assert keys[:6] == [
            "slug", "model", "strategy", "is_real_reference", "severity", "penalised"]
        # Every row carries the same columns, so the merged file is a rectangle.
        assert all(list(row) == keys for row in rows)


def test_driver_row_order_is_total_and_deterministic():
    """Byte-stability: the same ranking flattens to the same row sequence, twice."""
    ranking = _build(_driver_fixture())
    for flatten, key in (
        (severity_driver_rows, lambda r: (r["slug"], SEVERITY_RANK[r["severity"]], r["rank"])),
        (severity_driver_value_rows,
         lambda r: (r["slug"], SEVERITY_RANK[r["severity"]], r["pair_rank"], r["rank"])),
    ):
        rows = flatten(ranking)
        assert flatten(ranking) == rows
        keys = [key(row) for row in rows]
        assert keys == sorted(keys), "rows must be sorted by (slug, severity rank, rank)"
        assert len(set(keys)) == len(keys), "the sort key must leave no residual tie"


def test_driver_ranks_stay_within_their_level_and_are_not_renumbered():
    """A rank-1 S2 driver and a rank-1 S3 driver are both rank 1 in the merged table."""
    rows = severity_driver_rows(_build(_driver_fixture()))
    haiku = [row for row in rows if row["slug"] == "swedish_all_pick_claude_haiku"]
    by_level = {}
    for row in haiku:
        by_level.setdefault(row["severity"], []).append(row["rank"])
    assert by_level == {"S3": [1, 2], "S2": [1]}


def test_the_real_population_appears_in_the_driver_tables_as_an_ordinary_competitor():
    ranking = _build(_driver_fixture())
    pair_rows = severity_driver_rows(ranking)
    value_rows = severity_driver_value_rows(ranking)
    real_pairs = [row for row in pair_rows if row["is_real_reference"]]
    assert [(row["slug"], row["severity"]) for row in real_pairs] == [("real_swedish", "S1")]
    assert real_pairs[0]["n_personas"] == 2 and real_pairs[0]["denominator"] == 4
    assert real_pairs[0]["model"] == "" and real_pairs[0]["strategy"] == ""
    assert any(row["is_real_reference"] and row["value_b"] == "Rented" for row in value_rows)


def test_driver_rows_are_empty_rather_than_wrong_when_no_level_has_a_driver():
    ranking = _build(_driver_fixture(), driver_min_count=5)
    assert severity_driver_rows(ranking) == []
    assert severity_driver_value_rows(ranking) == []


def test_driver_flatteners_raise_when_the_block_is_missing_a_level():
    """A block built without one of the levels is malformed, not a table with a gap."""
    ranking = _build(_driver_fixture())
    del ranking["severity_drivers"]["levels"]["S1"]
    for flatten in (severity_driver_rows, severity_driver_value_rows):
        with pytest.raises(KeyError, match="Unknown severity level"):
            flatten(ranking)

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
    severity_pair_summary,
    summary_rows,
    typicality_histogram_rows,
    typicality_summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_headline_map,
    plot_impossibility_forest,
    plot_impossibility_heatmap,
    plot_severity_heatmap,
    plot_severity_pair_summary,
    plot_typicality_by_method,
    plot_typicality_heatmap,
)
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord  # noqa: E402
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.palette import HEATMAP_CMAP  # noqa: E402
from population_synthetic.analysis.utils.realism_clash_csv import RealismClashRow  # noqa: E402
from population_synthetic.analysis.utils.realism_csv import (  # noqa: E402
    SEVERITY_LEVELS,
    SEVERITY_RANK,
    RealismPersonaRow,
)

_BOOT = {"iterations": 200, "seed": 20260723, "ci_level": 0.95}
_COUNTRY = "swedish"
_PROVENANCE = {"judge_model": "claude-sonnet-5", "prompt_template_sha256": "abc", "n_rounds": 2}
#: The typicality axis's tunables, which the builder requires and never defaults. The
#: floor is 1 rather than the CLI's production 30: these fixtures hold a handful of
#: personas, so the shipped floor would flag every cell and the gate's own tests would be
#: the only ones exercising an ordinary cell.
_TYPICALITY = {"statistic": "iov", "n_levels": 11, "min_n": 1, "tail_threshold": 5}


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
    # The driver bounds and the typicality options are required arguments (the builder
    # reads no config), so the helper pins permissive ones; the tests that are *about*
    # them pass their own.
    kwargs.setdefault("driver_top_n", 3)
    kwargs.setdefault("driver_min_count", 1)
    kwargs.setdefault("typicality", dict(_TYPICALITY))
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


def _complexity_fixture():
    """Three methods whose complexity order and alphabetical order genuinely differ."""
    return [
        _record(f"swedish_{strategy}_claude_haiku", n_impossible=1,
                typicalities=[5.0, 6.0, 7.0, 8.0], model="claude_haiku", strategy=strategy)
        for strategy in ("all_pick", "all_generate_pick", "all_pick_dag")
    ]


def test_method_axis_is_ordered_by_complexity_not_alphabetically():
    """Every grid this task emits reads simplest-method-first, like the rest of the layer.

    Alphabetical is not a harmless second convention on this axis: `all_generate_*` sorts
    ahead of `all_pick*`, so it very nearly inverts the complexity order and puts the most
    elaborate method leftmost -- while the fidelity, model-ranking and method-significance
    figures beside it put the simplest one there.
    """
    expected = ["all_pick", "all_pick_dag", "all_generate_pick"]
    ranking = _build(_complexity_fixture())

    assert ranking["axis_a"]["grid"]["methods"] == expected
    assert expected != sorted(expected), "the fixture must discriminate the two orders"
    # One reshape serves every grid, so the severity and driver grids inherit it.
    for level in SEVERITY_LEVELS:
        assert ranking["severity"]["levels"][level]["grid"]["methods"] == expected
        assert ranking["severity_drivers"]["levels"][level]["grid"]["methods"] == expected


def test_method_factor_lists_its_levels_in_complexity_order():
    """The factor block's group listing follows the same axis its heatmaps do."""
    ranking = _build(_complexity_fixture())
    assert list(ranking["factor_significance"]["by_method"]["groups"]) == [
        "all_pick", "all_pick_dag", "all_generate_pick"]
    # The model factor has no declared order and stays alphabetical.
    by_model = _build(_factor_fixture())["factor_significance"]["by_model"]["groups"]
    assert list(by_model) == sorted(by_model)


def test_an_unknown_method_raises_rather_than_sorting_last():
    """An axis-naming drift must not hide behind a plausible-looking chart."""
    records = [
        _record("swedish_all_pick_claude_haiku", n_impossible=1, typicalities=[5.0, 6.0]),
        _record("swedish_not_a_strategy_claude_haiku", n_impossible=1, typicalities=[5.0, 6.0],
                strategy="not_a_strategy"),
    ]
    with pytest.raises(ValueError, match="not_a_strategy"):
        _build(records)


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
        # A real strategy id: the method axis is resolved through the strategy config, so
        # an invented one would raise in the builder and this test would pass on the wrong
        # exception -- it is about the *chart* refusing to draw an empty grid.
        slug="dead", country=_COUNTRY, model="m", strategy="all_pick", is_real_reference=False,
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
        # A real strategy id: the method axis is resolved through the strategy config, so
        # an invented one would raise in the builder and this test would pass on the wrong
        # exception -- it is about the *chart* refusing to draw an empty grid.
        slug="dead", country=_COUNTRY, model="m", strategy="all_pick", is_real_reference=False,
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
        # A real strategy id: the method axis is resolved through the strategy config, so
        # an invented one would raise in the builder and this test would pass on the wrong
        # exception -- it is about the *chart* refusing to draw an empty grid.
        slug="dead", country=_COUNTRY, model="m", strategy="all_pick", is_real_reference=False,
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
    method_rank = {
        method: rank for rank, method in enumerate(strategy_complexity_order(sorted(
            {row["strategy"] for row in severity_driver_rows(ranking)
             if not row["is_real_reference"]}
        )))
    }

    def competitor(row):
        # Method axis first, then model -- NOT the slug, which walks the methods
        # alphabetically. The real population has no coordinate and sorts last.
        if row["is_real_reference"]:
            return (1, 0, row["slug"])
        return (0, method_rank[row["strategy"]], row["model"])

    for flatten, key in (
        (severity_driver_rows,
         lambda r: (*competitor(r), SEVERITY_RANK[r["severity"]], r["rank"])),
        (severity_driver_value_rows,
         lambda r: (*competitor(r), SEVERITY_RANK[r["severity"]], r["pair_rank"], r["rank"])),
    ):
        rows = flatten(ranking)
        assert flatten(ranking) == rows
        keys = [key(row) for row in rows]
        assert keys == sorted(keys), "rows must be sorted by (method, model, severity, rank)"
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


# --------------------------------------------------------------------------- #
# severity pair summary (what clashed country-wide -- reporting only)           #
# --------------------------------------------------------------------------- #


def _summary(records, level, **kwargs):
    kwargs.setdefault("top_n", 10)
    return severity_pair_summary(records, level, **kwargs)


def test_pair_summary_counts_personas_not_clash_rows_and_pools_the_denominator():
    """Hand-computed: the round-duplicated clash counts its persona once.

    Competitor A raises ``age_group x education_level`` in personas 0 (twice -- two
    rounds), 1 and 2: four clash rows, three affected personas. The denominator is the
    two synthetic competitors' personas summed (4 + 4), which is exactly what the S3
    heatmap divides each of its two cells by.
    """
    summary = _summary(_driver_fixture(), "S3")

    assert summary["denominator"] == 8
    assert summary["n_synthetic_competitors"] == 2
    assert summary["real_slug"] == "real_swedish" and summary["real_denominator"] == 4
    assert [(p["attr_a"], p["attr_b"], p["n_personas"]) for p in summary["pairs"]] == [
        ("age_group", "education_level", 3),
        ("civil_status", "household_size", 1),
    ]
    assert summary["pairs"][0]["prevalence"] == pytest.approx(3 / 8)
    assert summary["pairs"][1]["prevalence"] == pytest.approx(1 / 8)
    # Reporting-only, and the level's direction travels with the numbers.
    assert summary["penalised"] is True and summary["severity"] == "S3"


def test_pair_summary_keeps_the_real_population_out_of_the_bars():
    """The real population is a separate series with its own denominator, never pooled."""
    summary = _summary(_driver_fixture(), "S3")
    # It raises no S3 clash at all: zero is a measurement, not an absent series.
    assert all(p["real_n_personas"] == 0 and p["real_prevalence"] == 0.0
               for p in summary["pairs"])

    s1 = _summary(_driver_fixture(), "S1")
    pair = s1["pairs"][0]
    assert (pair["attr_a"], pair["attr_b"]) == ("civil_status", "housing_tenure")
    # Two of the real competitor's four personas -- and none of the eight synthetic ones.
    assert pair["n_personas"] == 0 and pair["prevalence"] == 0.0
    assert pair["real_n_personas"] == 2 and pair["real_prevalence"] == pytest.approx(0.5)
    assert s1["n_pairs_real_only"] == 1


def test_pair_summary_denominator_is_the_population_the_heatmap_divides_by():
    """The pooled base equals the summed synthetic cell denominators, cell for cell."""
    records = _driver_fixture()
    grid = _build(records)["severity"]["levels"]["S3"]["grid"]
    cells = [grid["cells"][model][method]
             for model in grid["models"] for method in grid["methods"]
             if grid["cells"][model][method] is not None]

    summary = _summary(records, "S3")
    assert summary["denominator"] == sum(cell["denominator"] for cell in cells)
    assert summary["real_denominator"] == grid["real"]["denominator"]


def _tied_fixture():
    """Two synthetic competitors whose S2 pairs tie at one persona each.

    A tie is what makes the declared tie-break observable: without one the order is a
    function of the counts alone and the name ordering is never exercised.
    """
    a = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[5.0] * 3,
                model="claude_haiku", strategy="all_pick")
    a = _with_clashes(a, [
        _clash(a, 0, ("civil_status", "household_size"), ("Married", "1"), "S2"),
        _clash(a, 1, ("age_group", "housing_tenure"), ("16-19", "Owned"), "S2"),
        _clash(a, 2, ("age_group", "education_level"), ("16-19", "Doctorate"), "S2"),
    ])
    b = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0, typicalities=[5.0] * 3,
                model="claude_sonnet", strategy="all_pick_dag")
    b = _with_clashes(b, [
        _clash(b, 0, ("age_group", "employment_status"), ("16-19", "Retired"), "S2"),
    ])
    return [a, b]


def test_pair_summary_order_is_total_with_no_residual_tie():
    """Four pairs, all tied at one persona: the order is name order, and it is stable."""
    records = _tied_fixture()
    summary = _summary(records, "S2")

    assert all(pair["n_personas"] == 1 for pair in summary["pairs"])
    assert [(p["attr_a"], p["attr_b"]) for p in summary["pairs"]] == [
        ("age_group", "education_level"),
        ("age_group", "employment_status"),
        ("age_group", "housing_tenure"),
        ("civil_status", "household_size"),
    ]
    assert [p["rank"] for p in summary["pairs"]] == [1, 2, 3, 4]
    # The emitted order is a function of the counts and names alone: reversing the record
    # order (and with it every dict insertion order upstream) changes nothing.
    assert _summary(list(reversed(records)), "S2")["pairs"] == summary["pairs"]
    assert _summary(records, "S2") == summary


def test_pair_summary_counts_what_top_n_cut_rather_than_truncating_silently():
    summary = _summary(_driver_fixture(), "S3", top_n=1)
    assert summary["n_pairs_total"] == 2
    assert summary["n_pairs_shown"] == 1
    assert summary["n_pairs_hidden"] == 1
    assert summary["top_n"] == 1


def test_pair_summary_of_a_level_with_no_clash_is_empty_rather_than_absent():
    records = _driver_fixture()
    records[-1] = _with_clashes(records[-1], [])   # drop the real competitor's S1 clash
    summary = _summary(records, "S1")
    assert summary["pairs"] == []
    assert summary["n_pairs_total"] == 0 and summary["n_pairs_hidden"] == 0
    # The denominators are still reported: "nobody clashed" is a rate over a real base.
    assert summary["denominator"] == 8 and summary["real_denominator"] == 4


def test_pair_summary_raises_on_input_that_would_make_its_denominator_a_lie():
    records = _driver_fixture()
    with pytest.raises(KeyError, match="Unknown severity level"):
        _summary(records, "S9")
    with pytest.raises(ValueError, match="top_n must be >= 1"):
        _summary(records, "S3", top_n=0)
    with pytest.raises(ValueError, match="at least one competitor"):
        _summary([], "S3")
    with pytest.raises(ValueError, match="one country"):
        _summary([records[0], dataclasses.replace(records[1], country="italian")], "S3")
    with pytest.raises(ValueError, match="More than one competitor is flagged"):
        _summary([records[-1], dataclasses.replace(records[0], is_real_reference=True)], "S3")


def test_pair_summary_changes_no_number_in_the_ranking_document():
    """Reporting-only, and computed off to the side: the document must not notice it."""
    records = _driver_fixture()
    before = _build(records)
    for level in SEVERITY_LEVELS:
        _summary(records, level)
    after = _build(records)
    for block in ("axis_a", "axis_b", "severity"):
        assert after[block] == before[block]
    assert after["factor_significance"]["by_model"] == before["factor_significance"]["by_model"]
    assert after["factor_significance"]["by_method"] == before["factor_significance"]["by_method"]
    assert "severity_pair_summary" not in after


def test_pair_summary_figures_render_for_every_level():
    records = _driver_fixture()
    for level in SEVERITY_LEVELS:
        fig = plot_severity_pair_summary(_summary(records, level))
        assert fig.axes, level
        texts = " ".join(t.get_text() for t in fig.texts)
        # The caveats travel on the figure, not only in the docs.
        assert "Never render these as a pie" in texts, level
        assert "not from the per-cell severity_drivers tables" in texts, level
        assert (f"{level} is neither better nor worse" in texts) is (level == "S1"), level


def test_pair_summary_figure_of_an_empty_level_explains_itself():
    """No bars anywhere, and a stated reason -- never blank axes and never a crash."""
    records = _driver_fixture()
    records[-1] = _with_clashes(records[-1], [])
    fig = plot_severity_pair_summary(_summary(records, "S1"))
    ax = fig.axes[0]
    assert not ax.patches, "an empty level must draw no bar"
    assert "measured absence" in " ".join(t.get_text() for t in ax.texts)


# --------------------------------------------------------------------------- #
# typicality axis (self-contained per competitor -- reporting only)             #
# --------------------------------------------------------------------------- #


def _typicality_fixture():
    """Two competitors whose typicality bases differ from their persona counts.

    Competitor A: two impossible personas plus four scored ``{9, 9, 10, 10}`` -- the
    collapse pattern, IOV 0.1 by hand (only ``F_9 = 0.5`` is interior-non-degenerate, so
    ``4 * 0.25 / 10``). Competitor B: four scored ``{0, 0, 10, 10}`` -- every interior
    cutpoint at 0.5, so IOV 1.0. The pair is exactly the separation the statistic was
    chosen for: a location or order-blind summary scores the two splits identically.
    """
    a = _record("swedish_all_pick_claude_haiku", n_impossible=2,
                typicalities=[9.0, 9.0, 10.0, 10.0],
                model="claude_haiku", strategy="all_pick")
    b = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0,
                typicalities=[0.0, 0.0, 10.0, 10.0],
                model="claude_sonnet", strategy="all_pick_dag")
    return [a, b]


def _real_record(typicalities):
    return _record("real_swedish", n_impossible=0, typicalities=typicalities,
                   model="", strategy="", is_real=True)


def _typ(ranking, model="claude_haiku", method="all_pick"):
    return ranking["typicality"]["grid"]["cells"][model][method]


def test_typicality_denominator_is_the_typicality_base_not_the_persona_count():
    """The two bases differ by construction, and both travel on the cell.

    Competitor A's impossibility rate is over six personas; its typicality is over the
    four that carry one. Reading the second against the first would understate every
    spread in the sweep by the impossibility rate.
    """
    ranking = _build(_typicality_fixture())
    a, b = _typ(ranking), _typ(ranking, "claude_sonnet", "all_pick_dag")

    assert a["value"] == pytest.approx(0.1)
    assert a["denominator"] == 4 and a["n_personas"] == 6
    assert b["value"] == pytest.approx(1.0)
    assert b["denominator"] == b["n_personas"] == 4
    # ... while Axis A ranks A over all six personas, which is the point of the two names.
    assert ranking["axis_a"]["grid"]["cells"]["claude_haiku"]["all_pick"]["denominator"] == 6
    # {9,10} vs {0,10}: the collapse distinction an order-blind summary cannot draw.
    assert a["value"] < b["value"]
    # The base is the one the factor tests consume -- one source, so they cannot disagree.
    groups = ranking["factor_significance"]["by_model"]["groups"]
    assert sum(group["n"] for group in groups.values()) == a["denominator"] + b["denominator"]


def test_a_fully_collapsed_competitor_is_zero_with_a_flagged_boundary_interval():
    """The honest ``[0, 0]`` is published *with* its flag, never bare and never patched.

    At a parameter-space boundary the percentile bootstrap is inconsistent rather than
    merely inaccurate, so the interval is reported as degenerate instead of being
    smoothed into one that looks trustworthy.
    """
    collapsed = _record("swedish_all_pick_claude_haiku", n_impossible=0,
                        typicalities=[9.0] * 5)
    spread = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0,
                     typicalities=[2.0, 4.0, 6.0, 8.0, 9.0],
                     model="claude_sonnet", strategy="all_pick_dag")
    ranking = _build([collapsed, spread])

    cell = _typ(ranking)
    assert cell["value"] == 0.0
    assert (cell["ci_lo"], cell["ci_hi"]) == (0.0, 0.0)
    assert cell["boundary"] is True
    assert cell["status"] == "ok"          # measured, and measurable -- merely collapsed
    assert "inconsistent" in ranking["typicality"]["boundary_note"]

    # An interior cell with a genuine interval must not inherit the flag.
    interior = _typ(ranking, "claude_sonnet", "all_pick_dag")
    assert interior["boundary"] is False
    assert interior["ci_lo"] < interior["value"] < interior["ci_hi"]


def _powered_fixture():
    """One competitor below a floor of three typicality-bearing personas, one above."""
    small = _record("swedish_all_pick_claude_haiku", n_impossible=1,
                    typicalities=[3.0, 7.0], model="claude_haiku", strategy="all_pick")
    large = _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0,
                    typicalities=[3.0] * 3 + [7.0] * 3,
                    model="claude_sonnet", strategy="all_pick_dag")
    return [small, large]


def test_under_powered_cell_is_flagged_and_counted_rather_than_silently_dropped():
    """Three states, never two: a value, an under-powered value, and an unjudged null."""
    ranking = _build(_powered_fixture(), typicality={**_TYPICALITY, "min_n": 3})
    block = ranking["typicality"]
    small = _typ(ranking)
    large = _typ(ranking, "claude_sonnet", "all_pick_dag")

    assert small["under_powered"] is True and small["status"] == "under_powered"
    assert small["value"] is not None, "an under-powered cell is published, not dropped"
    assert small["denominator"] == 2
    assert large["under_powered"] is False and large["status"] == "ok"
    assert block["min_n"] == 3
    assert block["excluded"]["competitors_under_powered"] == 1
    assert "too few personas" in block["under_powered_policy"]

    # Distinct from an unjudged pair, which claims nothing was measured at all.
    assert block["grid"]["cells"]["claude_haiku"]["all_pick_dag"] is None
    assert block["grid"]["cells"]["claude_sonnet"]["all_pick"] is None
    assert block["excluded"]["cells_unjudged"] == 2
    assert "NOT a value of zero" in block["grid"]["note"]


def test_a_competitor_with_no_typicality_is_null_and_never_zero():
    """Every persona judged impossible: nothing was measured, and 0.0 is a measurement."""
    dead = _record("swedish_all_pick_claude_haiku", n_impossible=3, typicalities=[])
    ranking = _build([dead])
    cell = _typ(ranking)

    assert cell["value"] is None and cell["status"] == "no_typicality"
    assert cell["denominator"] == 0 and cell["n_personas"] == 3
    # Not "measured on too few personas" -- a different claim, and this is not it.
    assert cell["under_powered"] is False
    assert cell["histogram"] is None and cell["tail_proportion"] is None
    reasons = {s["test"]: s["reason"] for s in ranking["skipped_tests"]}
    assert "typicality[swedish_all_pick_claude_haiku]" in reasons
    assert "undefined" in reasons["typicality[swedish_all_pick_claude_haiku]"]
    excluded = ranking["typicality"]["excluded"]
    assert excluded["competitors_without_typicality"] == 1
    assert excluded["personas_without_a_typicality"] == 3


def test_a_single_persona_competitor_is_defined_with_a_degenerate_interval():
    """n = 1 must produce a number and an honest zero-width interval, not a crash."""
    lone = _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[7.0])
    cell = _typ(_build([lone]))
    assert cell["denominator"] == 1
    assert cell["value"] == 0.0            # one persona cannot be dispersed
    assert cell["ci_lo"] == cell["ci_hi"] == 0.0
    assert cell["boundary"] is True


def test_histogram_bins_sum_to_the_typicality_denominator():
    ranking = _build(_typicality_fixture())
    a = _typ(ranking)
    assert len(a["histogram"]) == _TYPICALITY["n_levels"]
    assert a["histogram"][9] == 2 and a["histogram"][10] == 2
    assert sum(a["histogram"]) == a["denominator"]

    rows = typicality_histogram_rows(ranking)
    by_slug: dict[str, list] = {}
    for row in rows:
        by_slug.setdefault(row["slug"], []).append(row)
    assert set(by_slug) == {"swedish_all_pick_claude_haiku", "swedish_all_pick_dag_claude_sonnet"}
    for group in by_slug.values():
        # The full scale, including the levels nobody scored -- a gap would read as absent.
        assert [row["level"] for row in group] == list(range(_TYPICALITY["n_levels"]))
        assert sum(row["n_personas_at_level"] for row in group) == group[0]["denominator"]
        assert sum(row["proportion"] for row in group) == pytest.approx(1.0)
        # Both bases on every row, under distinct names.
        assert group[0]["denominator"] <= group[0]["n_personas"]


def test_tail_column_is_a_proportion_with_a_wilson_interval_over_the_same_base():
    ranking = _build(_typicality_fixture(), typicality={**_TYPICALITY, "tail_threshold": 5})
    block = ranking["typicality"]
    assert block["tail_threshold"] == 5

    spread = _typ(ranking, "claude_sonnet", "all_pick_dag")      # {0, 0, 10, 10}
    assert spread["tail_count"] == 2 and spread["tail_proportion"] == pytest.approx(0.5)
    assert 0.0 < spread["tail_ci_lo"] < 0.5 < spread["tail_ci_hi"] < 1.0

    collapsed = _typ(ranking)                                    # {9, 9, 10, 10}
    assert collapsed["tail_count"] == 0 and collapsed["tail_proportion"] == 0.0
    # A proportion at its boundary keeps a width -- which is why it is not bootstrapped.
    assert collapsed["tail_ci_lo"] == 0.0 and collapsed["tail_ci_hi"] > 0.0


def test_reference_value_is_the_real_populations_own_statistic_or_null_with_a_reason():
    """The reference is read from the document, never assumed and never a literal."""
    records = _typicality_fixture() + [_real_record([9.0, 9.0, 10.0, 10.0])]
    block = _build(records)["typicality"]
    assert block["reference_slug"] == "real_swedish"
    assert block["reference_value"] == pytest.approx(0.1)
    assert block["reference_value"] == block["grid"]["real"]["value"]
    assert "colourbar rule" in block["reference_note"]
    # It is an ordinary competitor: no grid coordinate, no privilege in any cell.
    assert "real_swedish" not in block["grid"]["models"]

    without = _build(_typicality_fixture())["typicality"]
    assert without["reference_slug"] is None and without["reference_value"] is None
    assert "nothing to measure a distance against" in without["reference_note"]


def test_typicality_block_publishes_its_orientation_and_no_direction():
    """Direction is the render's job; the statistic states its endpoints and stops."""
    from population_synthetic.analysis.utils.ordinal import STATISTIC_LABELS

    block = _build(_typicality_fixture())["typicality"]
    assert block["direction"] is None
    assert "no monotone better direction" in block["direction_reason"]
    assert block["orientation"] == "dispersion"
    # Sourced from the definition rather than re-worded here, so the two cannot drift.
    assert block["statistic_label"] == STATISTIC_LABELS["iov"]
    assert "maximally dispersed" in block["statistic_label"]
    assert block["statistic_caveat"] is None
    assert "no ranking" in block["reporting_only"]
    assert "personas, not judge rounds" in block["counting_unit"]
    assert "factor_significance" in block["cross_reference"]
    assert "never averaged" in block["non_composite"]


def test_the_mean_option_carries_its_interval_assumption_on_every_row():
    """A caveat that lives only in the docs is one the table travels without."""
    ranking = _build(_typicality_fixture(),
                     typicality={**_TYPICALITY, "statistic": "mean_level"})
    block = ranking["typicality"]
    assert block["orientation"] == "location"
    assert "equally spaced" in block["statistic_caveat"]
    assert _typ(ranking)["value"] == pytest.approx(9.5)

    rows = typicality_summary_rows(ranking)
    assert rows and all("equally spaced" in row["statistic_caveat"] for row in rows)
    # ... and the default statistic makes no such claim, so it carries no such caveat.
    default_rows = typicality_summary_rows(_build(_typicality_fixture()))
    assert all(row["statistic_caveat"] is None for row in default_rows)


def test_typicality_changes_no_number_the_ranking_already_published():
    """Reporting-only, in the tested sense: loose vs tight bounds, byte for byte."""
    records = _driver_fixture()
    loose = _build(records, typicality={"statistic": "iov", "n_levels": 11,
                                        "min_n": 1, "tail_threshold": 3})
    tight = _build(records, typicality={"statistic": "mean_level", "n_levels": 11,
                                        "min_n": 50, "tail_threshold": 8})
    for key in ("axis_a", "axis_b", "severity", "severity_drivers"):
        assert loose[key] == tight[key], key
    # The mixed model is excluded: its variational fit is not bit-reproducible between
    # two calls, which is a property of the fitter and would mask, not reveal, a leak.
    for factor in ("by_model", "by_method"):
        assert loose["factor_significance"][factor] == tight["factor_significance"][factor]
    assert loose["typicality"] != tight["typicality"], "the fixture must discriminate"

    # It has not leaked into the ranking, the contrasts, the factor tests or their tables.
    assert "typicality" not in loose["axis_a"]
    assert all("typicality" not in entry for entry in loose["axis_a"]["ranking"])
    assert all("typicality" not in row for row in loose["axis_b"]["dispersion_contrast"])
    assert "typicality" not in loose["factor_significance"]
    assert all("typicality" not in row for row in summary_rows(loose))
    assert all("typicality" not in row for row in scb_contrast_rows(loose))
    assert all("typicality" not in row for row in severity_driver_rows(loose))


@pytest.mark.parametrize("options", [
    {"min_n": 0}, {"min_n": -1}, {"n_levels": 1}, {"tail_threshold": 11},
    {"tail_threshold": -1}, {"statistic": "not_a_statistic"},
])
def test_degenerate_typicality_options_raise_rather_than_emitting_an_empty_table(options):
    with pytest.raises(ValueError):
        _build(_typicality_fixture(), typicality={**_TYPICALITY, **options})


@pytest.mark.parametrize("options", [
    {key: value for key, value in _TYPICALITY.items() if key != "min_n"},   # incomplete
    {**_TYPICALITY, "typicality_min_n": 30},                                # a typo'd key
])
def test_malformed_typicality_options_raise_rather_than_being_defaulted(options):
    with pytest.raises(ValueError, match="Malformed typicality options"):
        _build(_typicality_fixture(), typicality=options)


def test_omitting_the_options_leaves_a_null_block_a_recorded_reason_and_no_table():
    """Absent because nobody asked is a fact worth recording, not a silent default."""
    ranking = build_ranking(
        _typicality_fixture(), _COUNTRY, bootstrap=_BOOT, variance_center="median",
        driver_top_n=3, driver_min_count=1,
    )
    assert ranking["typicality"] is None
    assert "typicality_axis" in {skip["test"] for skip in ranking["skipped_tests"]}
    for flatten in (typicality_summary_rows, typicality_histogram_rows):
        with pytest.raises(ValueError, match="no typicality axis"):
            flatten(ranking)


def test_typicality_rows_are_ordered_by_method_then_model_with_the_real_population_last():
    """The tables read simplest-method-first, exactly as their heatmap does."""
    records = _complexity_fixture() + [_real_record([5.0, 6.0, 7.0])]
    ranking = _build(records)
    rows = typicality_summary_rows(ranking)

    assert [row["strategy"] for row in rows] == [
        "all_pick", "all_pick_dag", "all_generate_pick", ""]
    assert rows[-1]["is_real_reference"] is True
    assert rows[-1]["slug"] == "real_swedish"
    # Every row carries the same columns, so the file is a rectangle.
    keys = list(rows[0])
    assert keys[:4] == ["slug", "model", "strategy", "is_real_reference"]
    assert all(list(row) == keys for row in rows)
    # Both persona counts, under distinct names, on every row.
    assert all({"denominator", "n_personas"} <= set(row) for row in rows)

    histogram = typicality_histogram_rows(ranking)
    assert [row["slug"] for row in rows] == list(dict.fromkeys(
        row["slug"] for row in histogram))
    # Byte-stable: the same ranking flattens to the same row sequence, twice.
    assert typicality_summary_rows(ranking) == rows
    assert typicality_histogram_rows(ranking) == histogram


def test_competitor_order_changes_no_emitted_typicality_byte():
    records = _typicality_fixture()
    forward = _build(records)
    reverse = _build(list(reversed(records)))
    assert forward["typicality"] == reverse["typicality"]
    assert typicality_summary_rows(forward) == typicality_summary_rows(reverse)
    assert typicality_histogram_rows(forward) == typicality_histogram_rows(reverse)


# --------------------------------------------------------------------------- #
# typicality figures -- the reference lives in the rendering, not in the cells  #
# --------------------------------------------------------------------------- #


def _four_state_fixture():
    """One grid carrying all four states the typicality heatmap must tell apart.

    ``claude_haiku x all_pick`` has four typicality-bearing personas (under-powered at a
    floor of five), ``claude_sonnet x all_pick_dag`` five (powered), ``claude_haiku x
    all_pick_dag`` was judged but every persona is impossible (no typicality), and
    ``claude_sonnet x all_pick`` is unjudged -- it exists only as the rectangle's hole.
    """
    return [
        _record("swedish_all_pick_claude_haiku", n_impossible=2,
                typicalities=[9.0, 9.0, 10.0, 10.0],
                model="claude_haiku", strategy="all_pick"),
        _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0,
                typicalities=[0.0, 0.0, 10.0, 10.0, 10.0],
                model="claude_sonnet", strategy="all_pick_dag"),
        _record("swedish_all_pick_dag_claude_haiku", n_impossible=3, typicalities=[],
                model="claude_haiku", strategy="all_pick_dag"),
        _real_record([4.0, 4.0, 5.0, 6.0, 7.0]),
    ]


def _four_state_ranking(**options):
    return _build(_four_state_fixture(), typicality={**_TYPICALITY, "min_n": 5, **options})


def _figure_text(fig) -> str:
    """Every string on a figure: the axes' annotations and the footnote block."""
    return " ".join(
        [t.get_text() for ax in fig.axes for t in ax.texts] + [t.get_text() for t in fig.texts]
    )


def test_typicality_heatmap_renders_a_populated_cell_as_a_value_not_as_missing():
    """The guard against Constraint 1's silent-wrong-output path.

    ``_render_grid_heatmap`` reads ``cell["rate"]`` by literal key, and this block's value
    key is ``value``: pointing the old renderer at this grid paints every cell grey and
    labels it ``n/a`` **without raising**. Nothing else in the suite would notice, because
    the figure is produced, is the right size and carries the right labels -- so the
    populated cells are asserted to carry their numbers.
    """
    ranking = _four_state_ranking()
    fig = plot_typicality_heatmap(ranking)
    text = _figure_text(fig)

    assert "0.100" in text and "n=4" in text   # haiku x all_pick, hand-computed in Phase 2
    assert "n/a" not in text
    # The four states are four different marks, and each says which it is.
    assert text.count("not judged") == 1               # sonnet x all_pick
    assert "no typicality\nof 3 personas" in text      # haiku x all_pick_dag
    assert "real population" in text


def test_typicality_heatmap_anchors_the_house_ramp_at_the_statistics_true_zero():
    """Same ramp and same anchoring as every sibling grid: zero is a real measurement."""
    ranking = _four_state_ranking()
    reference = ranking["typicality"]["reference_value"]
    image = plot_typicality_heatmap(ranking).axes[0].images[0]

    assert image.cmap.name == HEATMAP_CMAP
    vmin, vmax = image.get_clim()
    assert vmin == 0.0, "a cell at the floor must mean 'no variety', not 'least here'"
    # Wide enough to hold every drawn value, the real population's own included.
    values = [
        cell["value"]
        for model in ranking["typicality"]["grid"]["models"]
        for cell in ranking["typicality"]["grid"]["cells"][model].values()
        if cell is not None and cell["value"] is not None
    ] + [reference]
    assert max(values) <= vmax


def test_typicality_heatmap_carries_the_reference_as_a_rule_and_a_signed_delta():
    """The ramp is sequential, so the *side* of the reference lives in the annotations.

    This is the guard on the one thing the diverging ramp used to do for free. A cell
    above the reference and a cell below it are drawn by magnitude alone; if the signed
    delta or the colourbar rule went missing, the figure would still look complete while
    having quietly dropped the reading the whole axis exists to give.
    """
    ranking = _four_state_ranking()
    reference = float(ranking["typicality"]["reference_value"])
    fig = plot_typicality_heatmap(ranking)

    values = [
        cell["value"]
        for model in ranking["typicality"]["grid"]["models"]
        for cell in ranking["typicality"]["grid"]["cells"][model].values()
        if cell is not None and cell["value"] is not None
    ]
    text = _figure_text(fig)
    for value in values:
        assert f"({value - reference:+.3f})" in text

    # The rule sits on the colourbar axes, at the reference's own value.
    colorbar_ax = fig.axes[-1]
    assert [line.get_ydata()[0] for line in colorbar_ax.lines] == [pytest.approx(reference)]


def test_typicality_heatmap_drops_the_reference_marking_when_there_is_no_reference():
    """No real population -> no rule, no delta, and never a literal one in their place."""
    records = [r for r in _four_state_fixture() if not r.is_real_reference]
    ranking = _build(records, typicality={**_TYPICALITY, "min_n": 5})
    assert ranking["typicality"]["reference_value"] is None

    fig = plot_typicality_heatmap(ranking)
    image = fig.axes[0].images[0]
    assert image.cmap.name == HEATMAP_CMAP
    assert image.get_clim()[0] == 0.0
    text = _figure_text(fig)
    assert "nothing to measure a distance against" in text   # the block's recorded reason
    assert "Parenthesised in each cell" not in text          # no delta to explain
    assert "Colourbar rule" not in text
    assert len(fig.axes[-1].lines) == 0


def test_typicality_heatmap_survives_a_zero_width_range():
    """Every competitor at the statistic's floor: a ramp, not a division by zero."""
    identical = [
        _record("swedish_all_pick_claude_haiku", n_impossible=0, typicalities=[3.0, 3.0]),
        _record("swedish_all_pick_dag_claude_sonnet", n_impossible=0,
                typicalities=[3.0, 3.0], model="claude_sonnet", strategy="all_pick_dag"),
        _real_record([3.0, 3.0]),
    ]
    ranking = _build(identical)
    assert ranking["typicality"]["reference_value"] == 0.0

    fig = plot_typicality_heatmap(ranking)
    vmin, vmax = fig.axes[0].images[0].get_clim()
    assert vmin < vmax, "a zero-width range must still yield valid limits"
    assert "no measured range" in _figure_text(fig)


def test_typicality_heatmap_method_axis_is_the_complexity_order():
    """The figure takes its axis from the grid verbatim, never re-sorting it."""
    records = _complexity_fixture() + [_real_record([5.0, 6.0, 7.0])]
    ranking = _build(records)
    methods = ranking["typicality"]["grid"]["methods"]
    assert methods == strategy_complexity_order(methods) != sorted(methods)

    ax = plot_typicality_heatmap(ranking).axes[0]
    assert [label.get_text() for label in ax.get_xticklabels()] == methods


def test_typicality_figures_carry_their_direction_refusal_and_the_min_n_gate():
    """The caveats travel on the figures: they outlive this docstring and the code."""
    ranking = _four_state_ranking()
    block = ranking["typicality"]
    for fig in (plot_typicality_heatmap(ranking), plot_typicality_by_method(ranking)):
        # Whitespace-normalised: the footnote block is hard-wrapped for reading, so the
        # payload's sentences arrive on the figure broken across lines.
        text = " ".join(_figure_text(fig).split())
        assert "Not a score:" in text
        # Worded by the block, not by the chart, so the two cannot drift.
        assert " ".join(block["direction_reason"].split()) in text
        assert " ".join(block["under_powered_policy"].split()) in text
        assert "min_n = 5" in text
        assert block["reference_slug"] in text


def test_typicality_by_method_draws_the_real_population_as_a_reference_line():
    """The one place in this task the real population is a reference rather than a series.

    Legitimate only because this axis ranks nothing: on Axis A a reference line would
    encode "closer to it is better" into a figure built to leave that question open.
    """
    ranking = _four_state_ranking()
    reference = ranking["typicality"]["reference_value"]
    ax = plot_typicality_by_method(ranking).axes[0]

    horizontal = [line for line in ax.lines
                  if len(set(line.get_ydata())) == 1
                  and list(set(line.get_ydata())) == [pytest.approx(reference)]]
    assert horizontal, "the reference line is missing"
    inline = " ".join(t.get_text() for t in ax.texts)
    assert f"{reference:.3f}" in inline and "not a target" in inline
    # Methods on x, in the grid's own order; nothing is drawn for the unjudged pair.
    assert [label.get_text() for label in ax.get_xticklabels()] == \
        ranking["typicality"]["grid"]["methods"]


def test_typicality_by_method_marks_an_under_powered_competitor_without_dropping_it():
    ranking = _four_state_ranking()
    assert _typ(ranking)["under_powered"] is True
    fig = plot_typicality_by_method(ranking)
    ax = fig.axes[0]

    drawn = [value for collection in ax.collections
             for _x, value in collection.get_offsets()]
    assert pytest.approx(_typ(ranking)["value"]) in drawn, "an under-powered mark is drawn"
    labels = [handle.get_label() for handle in ax.get_legend().legend_handles]
    assert any("hollow = under-powered" in label for label in labels)
    assert "under-powered competitor(s) are drawn hollow" in " ".join(_figure_text(fig).split())


def test_typicality_figures_raise_rather_than_emitting_an_empty_one():
    """Nothing measurable is a raise, matching every sibling chart in this module."""
    dead = _build([_record("swedish_all_pick_claude_haiku", n_impossible=3, typicalities=[])])
    for plot in (plot_typicality_heatmap, plot_typicality_by_method):
        with pytest.raises(ValueError, match="defined typicality statistic"):
            plot(dead)

    # ... and so is a document built without the axis at all, whose absence is a decision
    # rather than a measurement.
    without = build_ranking(
        _typicality_fixture(), _COUNTRY, bootstrap=_BOOT, variance_center="median",
        driver_top_n=3, driver_min_count=1,
    )
    for plot in (plot_typicality_heatmap, plot_typicality_by_method):
        with pytest.raises(ValueError, match="typicality: null"):
            plot(without)


def test_a_grid_of_nothing_but_under_powered_cells_still_renders():
    """Every cell below the floor is still a measurement, and still gets drawn.

    The degenerate neighbour of the raise above: nothing here clears ``min_n``, but
    something *was* measured everywhere, so suppressing the figure would report a sweep of
    small samples as a sweep of no data.
    """
    ranking = _build(_four_state_fixture(), typicality={**_TYPICALITY, "min_n": 50})
    grid = ranking["typicality"]["grid"]
    cells = [_typ(ranking), _typ(ranking, "claude_sonnet", "all_pick_dag"), grid["real"]]
    assert all(cell["under_powered"] for cell in cells)

    fig = plot_typicality_heatmap(ranking)
    # The real population's band is marked on the same terms as the cells: every cell's
    # delta is measured against it, so a thin reference drawn as a firm one is the worse
    # error.
    assert [patch.get_hatch() for patch in fig.axes[0].patches].count("//") == len(cells)
    assert "0.100" in _figure_text(fig) and "n=4" in _figure_text(fig)
    assert plot_typicality_by_method(ranking).axes[0].collections


def test_a_single_competitor_renders_on_both_figures():
    """n = 1 competitor: a degenerate CI, and ramp limits that are still valid."""
    lone = _build([_record("swedish_all_pick_claude_haiku", n_impossible=0,
                           typicalities=[2.0, 4.0, 6.0])])
    vmin, vmax = plot_typicality_heatmap(lone).axes[0].images[0].get_clim()
    assert vmin < vmax
    assert plot_typicality_by_method(lone).axes[0].collections

"""Unit tests for the realism ranking's typicality distribution, effects and closeness blocks.

Three blocks beside ``typicality``: the round-weighted score distribution per competitor
on the model x strategy grid (``typicality_distribution``), the effect sizes of the
typicality factor tests plus the location contrast against the reference
(``typicality_effects``), and the combination-level closeness to the reference with its
model + strategy decomposition (``typicality_closeness``).

The load-bearing checks are hand-computed values (the round-weighted weights, the band
shares), the orientation and family rules of the effect tables, the four distinct cell
states, and the reproduction of the prototype's golden first-round closeness numbers --
the manuscript's ``--rounds 1`` run -- through the builder's own round-weighted basis.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from pathlib import Path

import numpy as np
import pytest

from population_synthetic.analysis.realism_ranking.builder import (
    _typicality_closeness,
    build_ranking,
    typicality_band_rows,
    typicality_closeness_decomposition_rows,
    typicality_closeness_pair_rows,
    typicality_closeness_rows,
    typicality_closeness_test_rows,
    typicality_distribution_rows,
    typicality_effect_model_pair_rows,
    typicality_effect_omnibus_rows,
    typicality_effect_vs_reference_rows,
    typicality_histogram_rows,
    validate_typicality_bands,
)
from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord
from population_synthetic.analysis.utils.realism_csv import RealismPersonaRow
from population_synthetic.analysis.utils.stats_tests import holm_adjust
from tests import _closeness_fixtures as golden

_COUNTRY = "swedish"
_BOOT = {"iterations": 200, "seed": 20260723, "ci_level": 0.95}
_PROVENANCE = {"judge_model": "claude-sonnet-5", "prompt_template_sha256": "abc", "n_rounds": 3}
_TYPICALITY = {"statistic": "iov", "n_levels": 11, "min_n": 1, "tail_threshold": 5}
_CLOSENESS = {
    "ci_level": 0.95, "bootstrap_iterations": 200, "bootstrap_seed": 20260921,
    "permutation_iterations": 199, "permutation_seed": 20260928,
    "noise_iterations": 400, "noise_seed": 20261020, "noise_quantile": 0.95,
}
_PROTOTYPE = Path(__file__).resolve().parents[1] / (
    "docs/development/plans/active/typicality-distribution-grid"
)


def _persona(pid, slug, rounds, *, model, strategy, is_real=False, possible=True):
    scored = [t for t in rounds if t is not None]
    return RealismPersonaRow(
        persona_id=pid, slug=slug, country=_COUNTRY, model=model, strategy=strategy,
        is_real_reference=is_real, n_rounds_attempted=len(rounds), n_rounds_successful=len(rounds),
        can_exist_true_votes=len(rounds) if possible else 0, can_exist_majority=possible,
        typicality_mean=statistics.mean(scored) if scored else None, typicality_sd=None,
        typicality_rounds=tuple(rounds), max_severity="", clash_count=0,
    )


def _record(slug, rounds_per_persona, *, model="", strategy="", is_real=False, impossible=0):
    rows = [
        _persona(f"persona_{i:05d}", slug, rounds, model=model, strategy=strategy, is_real=is_real)
        for i, rounds in enumerate(rounds_per_persona)
    ] + [
        _persona(f"persona_x{i:05d}", slug, (None, None), model=model, strategy=strategy,
                 is_real=is_real, possible=False)
        for i in range(impossible)
    ]
    return CompetitorRecord(
        slug=slug, country=_COUNTRY, model=model, strategy=strategy, is_real_reference=is_real,
        n_personas=len(rows), n_failed=0, personas=tuple(rows),
        impossibility={"rate": impossible / len(rows) if rows else None},
        dispersion={"variance": 4.0, "entropy": 1.5, "tail_coverage": 0.1},
        reliability={}, provenance=dict(_PROVENANCE),
        report_path=Path(f"/fake/{slug}.json"), personas_csv_path=Path(f"/fake/{slug}_personas.csv"),
    )


def _synthetic(model, strategy, scores):
    """A one-round-per-persona synthetic competitor with the given scores."""
    return _record(f"{_COUNTRY}_{strategy}_{model}", [(s,) for s in scores], model=model, strategy=strategy)


def _real(scores):
    return _record(f"real_{_COUNTRY}", [(s,) for s in scores], is_real=True)


def _build(records, *, country=_COUNTRY, **kwargs):
    kwargs.setdefault("typicality", dict(_TYPICALITY))
    kwargs.setdefault("typicality_bands", (4, 7))
    kwargs.setdefault("withdrawn", ())
    kwargs.setdefault("closeness", dict(_CLOSENESS))
    return build_ranking(
        records, country, bootstrap=_BOOT, variance_center="median",
        driver_top_n=3, driver_min_count=1, **kwargs,
    )


def _grid_fixture():
    """Two models x two strategies with the fourth cell left to the caller, plus the reference."""
    return [
        _synthetic("claude_haiku", "all_pick", [8, 9, 9, 7, 10, 8, 9]),
        _synthetic("claude_haiku", "all_pick_dag", [6, 7, 8, 9, 9, 5, 7]),
        _synthetic("claude_sonnet", "all_pick", [9, 9, 10, 8, 9, 9, 7]),
        _real([3, 4, 5, 6, 4, 2, 5, 7, 4, 3]),
    ]


# --------------------------------------------------------------------------- #
# typicality_distribution                                                      #
# --------------------------------------------------------------------------- #


def test_round_weighted_distribution_is_hand_computable():
    """Rounds (8, 9), (9), (10, None, 10) and a non-survivor: 8 -> .5, 9 -> 1.5, 10 -> 1."""
    record = _record(
        f"{_COUNTRY}_all_pick_claude_haiku", [(8, 9), (9,), (10, None, 10)],
        model="claude_haiku", strategy="all_pick", impossible=1,
    )
    block = _build([record, _real([4, 5, 6])])["typicality_distribution"]
    cell = block["grid"]["cells"]["claude_haiku"]["all_pick"]
    expected = [0.0] * 11
    expected[8], expected[9], expected[10] = 0.5, 1.5, 1.0
    assert cell["weights"] == expected
    assert sum(cell["weights"]) == cell["denominator"] == 3
    assert cell["n_personas"] == 4 and cell["n_multi_round"] == 2
    assert cell["mean"] == pytest.approx(statistics.mean(record.typicality_means), abs=1e-12)
    assert cell["mean"] == pytest.approx((8.5 + 9 + 10) / 3, abs=1e-12)


def test_one_round_per_survivor_reduces_to_the_integer_histogram():
    records = _grid_fixture()
    ranking = _build(records)
    block = ranking["typicality_distribution"]
    for record in records:
        cell = (block["grid"]["real"] if record.is_real_reference
                else block["grid"]["cells"][record.model][record.strategy])
        scores = [s for (s,) in record.typicality_round_scores]
        assert cell["weights"] == np.bincount(scores, minlength=11).astype(float).tolist()
    # ... and equal to the existing (rounded-mean) histogram, which coincides at one round.
    histogram = {(row["slug"], row["level"]): row["n_personas_at_level"]
                 for row in typicality_histogram_rows(ranking)}
    for row in typicality_distribution_rows(ranking):
        assert row["weight"] == histogram[(row["slug"], row["level"])]


def test_band_shares_are_known_and_sum_to_one():
    record = _synthetic("claude_haiku", "all_pick", [0, 4, 5, 7, 8, 10, 10, 2])
    block = _build([record, _real([4, 5, 6])])["typicality_distribution"]
    cell = block["grid"]["cells"]["claude_haiku"]["all_pick"]
    assert cell["band_shares"] == pytest.approx([3 / 8, 2 / 8, 3 / 8], abs=1e-15)
    assert sum(cell["band_shares"]) == pytest.approx(1.0, abs=1e-12)
    assert block["bands"] == {"edges": [4, 7], "labels": ["0–4", "5–7", "8–10"]}
    (row,) = [r for r in typicality_band_rows(_build([record, _real([4])])) if not r["is_real_reference"]]
    assert (row["share_low"], row["share_mid"], row["share_high"]) == pytest.approx((3 / 8, 2 / 8, 3 / 8))


@pytest.mark.parametrize("bands", [(7, 4), (-1, 4), (4, 10), (4, 4), (4,)])
def test_malformed_bands_raise(bands):
    with pytest.raises(ValueError, match="bands"):
        validate_typicality_bands(bands, 11)
    with pytest.raises(ValueError, match="bands"):
        _build(_grid_fixture(), typicality_bands=bands)


def test_score_outside_the_scale_raises():
    record = _synthetic("claude_haiku", "all_pick", [11])
    with pytest.raises(ValueError, match="outside"):
        _build([record, _real([4])])


def test_withdrawn_unjudged_and_no_typicality_are_three_distinct_states():
    no_typicality = _record(
        f"{_COUNTRY}_all_pick_dag_claude_sonnet", [], model="claude_sonnet",
        strategy="all_pick_dag", impossible=3,
    )
    records = [
        _synthetic("claude_haiku", "all_pick", [8, 9]),
        _synthetic("claude_sonnet", "all_pick", [9, 9]),
        no_typicality,
        _synthetic("gpt", "all_pick_dag", [7, 8]),
        _real([4, 5]),
    ]
    withdrawn = [f"{_COUNTRY}_all_pick_dag_claude_haiku"]
    block = _build(records, withdrawn=withdrawn)["typicality_distribution"]
    states = block["grid"]["states"]
    assert states["claude_haiku"]["all_pick_dag"] == "withdrawn"
    assert states["gpt"]["all_pick"] == "unjudged"
    assert states["claude_sonnet"]["all_pick_dag"] == "no_typicality"
    assert states["claude_haiku"]["all_pick"] == "ok"
    assert block["withdrawn"] == withdrawn
    assert block["unjudged"] == [f"{_COUNTRY}_all_pick_gpt"]
    assert block["grid"]["cells"]["claude_haiku"]["all_pick_dag"] is None
    assert block["grid"]["cells"]["claude_sonnet"]["all_pick_dag"]["distribution"] is None
    # A no-typicality competitor is in the bands table, but has no distribution rows.
    ranking = _build(records, withdrawn=withdrawn)
    assert no_typicality.slug in {row["slug"] for row in typicality_band_rows(ranking)}
    assert no_typicality.slug not in {row["slug"] for row in typicality_distribution_rows(ranking)}


def test_a_withdrawn_slug_that_was_consumed_raises():
    records = _grid_fixture()
    with pytest.raises(ValueError, match="withdrawn by the population gate"):
        _build(records, withdrawn=[records[0].slug])


# --------------------------------------------------------------------------- #
# typicality_effects                                                           #
# --------------------------------------------------------------------------- #


def _effects_fixture():
    rng = random.Random(7)
    records = []
    for m_index, model in enumerate(("claude_haiku", "claude_sonnet", "gpt")):
        for s_index, strategy in enumerate(("all_pick", "all_pick_dag")):
            centre = 5 + m_index + s_index
            scores = [min(10, max(0, centre + rng.choice((-2, -1, 0, 1, 2)))) for _ in range(12)]
            records.append(_synthetic(model, strategy, scores))
    records.append(_real([rng.choice(range(2, 8)) for _ in range(15)]))
    return records


def test_epsilon_squared_is_h_over_n_minus_one_of_the_published_kruskal():
    ranking = _build(_effects_fixture())
    omnibus = {row["factor"]: row for row in typicality_effect_omnibus_rows(ranking)}
    for factor, key in (("model", "by_model"), ("strategy", "by_method")):
        kruskal = ranking["factor_significance"][key]["kruskal"]
        assert omnibus[factor]["epsilon_squared"] == kruskal["H"] / (kruskal["n"] - 1)
        assert omnibus[factor]["H"] == kruskal["H"]


def test_model_pair_delta_follows_the_dunn_orientation():
    ranking = _build(_effects_fixture())
    dunn = {(d["a"], d["b"]): d for d in ranking["factor_significance"]["by_model"]["dunn"]}
    rows = typicality_effect_model_pair_rows(ranking)
    assert [(row["a"], row["b"]) for row in rows] == list(dunn)
    for row in rows:
        d = dunn[(row["a"], row["b"])]
        assert row["p_holm"] == d["p_holm"] and row["dunn_z"] == d["z"]
        if row["cliffs_delta"] != 0 and d["z"] != 0:
            assert np.sign(row["cliffs_delta"]) == np.sign(d["z"])
        assert row["ci_lo"] <= row["cliffs_delta"] <= row["ci_hi"]


def test_vs_reference_holm_families_are_exactly_their_rows():
    records = _effects_fixture()
    no_typicality = _record(f"{_COUNTRY}_all_pick_zeta", [], model="zeta", strategy="all_pick", impossible=2)
    ranking = _build([*records, no_typicality])
    families = ranking["typicality_effects"]["vs_reference"]
    combos = families["combination_vs_reference"]
    synthetic = [r for r in records if not r.is_real_reference]
    assert {row["slug"] for row in combos} == {r.slug for r in synthetic}
    assert len(families["model_vs_reference"]) == 3
    for rows in families.values():
        assert [row["p_holm"] for row in rows] == holm_adjust([row["p_raw"] for row in rows])
        assert all(row["correction"] == "holm" and row["reference"] == f"real_{_COUNTRY}" for row in rows)
    assert any(skip["test"] == f"typicality_effects.combination_vs_reference[{no_typicality.slug}]"
               for skip in ranking["skipped_tests"])
    assert len(typicality_effect_vs_reference_rows(ranking)) == len(combos) + 3


def test_missing_reference_leaves_empty_families_and_no_closeness_with_reasons():
    records = [r for r in _effects_fixture() if not r.is_real_reference]
    ranking = _build(records)
    assert ranking["typicality_effects"]["vs_reference"] == {
        "combination_vs_reference": [], "model_vs_reference": []}
    assert typicality_effect_vs_reference_rows(ranking) == []
    tests = {skip["test"] for skip in ranking["skipped_tests"]}
    assert {"typicality_effects.combination_vs_reference", "typicality_effects.model_vs_reference",
            "typicality_closeness"} <= tests
    assert ranking["typicality_closeness"] is None
    with pytest.raises(ValueError, match="no typicality_closeness block"):
        typicality_closeness_rows(ranking)


# --------------------------------------------------------------------------- #
# typicality_closeness                                                          #
# --------------------------------------------------------------------------- #


def test_closeness_options_are_required_and_exact():
    with pytest.raises(ValueError, match="Malformed closeness options"):
        _build(_grid_fixture(), closeness={k: v for k, v in _CLOSENESS.items() if k != "noise_seed"})
    with pytest.raises(ValueError, match="Malformed closeness options"):
        _build(_grid_fixture(), closeness={**_CLOSENESS, "seed": 1})


def test_closeness_on_a_degenerate_design_records_skips_rather_than_raising():
    ranking = _build(_grid_fixture())
    block = ranking["typicality_closeness"]
    assert block["n_combinations"] == 3
    tv = block["by_outcome"]["tv_similarity"]
    assert tv["decomposition"]["anova"]["df_residual"] == 0
    assert tv["decomposition"]["intervals"] is None
    assert any(skip["test"].startswith("typicality_closeness[") for skip in ranking["skipped_tests"])
    for flatten in (typicality_closeness_rows, typicality_closeness_decomposition_rows,
                    typicality_closeness_test_rows, typicality_closeness_pair_rows):
        flatten(ranking)   # every table still flattens


def test_new_blocks_and_tables_do_not_depend_on_record_order():
    records = _effects_fixture()
    shuffled = list(records)
    random.Random(3).shuffle(shuffled)
    forward, reverse = _build(records), _build(shuffled)
    for key in ("typicality_distribution", "typicality_effects", "typicality_closeness"):
        assert json.dumps(forward[key], sort_keys=False) == json.dumps(reverse[key], sort_keys=False), key
    for flatten in (typicality_distribution_rows, typicality_band_rows, typicality_effect_omnibus_rows,
                    typicality_effect_model_pair_rows, typicality_effect_vs_reference_rows,
                    typicality_closeness_rows, typicality_closeness_decomposition_rows,
                    typicality_closeness_test_rows, typicality_closeness_pair_rows):
        assert flatten(forward) == flatten(reverse), flatten.__name__


# --------------------------------------------------------------------------- #
# Golden reproduction: the prototype's first-round closeness numbers           #
# --------------------------------------------------------------------------- #


def _golden_records():
    """The 58 swedish_02 combinations and the reference, one scored round per survivor."""
    keys, counts, reference = golden.first_round_histograms()

    def scores_of(row):
        return [(int(level),) for level in np.repeat(np.arange(11), row.astype(int))]

    records = [
        _record(f"swedish_02_{strategy}_{model}", scores_of(row), model=model, strategy=strategy)
        for (model, strategy), row in zip(keys, counts)
    ]
    records.append(_record("real_swedish_02", scores_of(reference), is_real=True))
    return records


@pytest.fixture(scope="module")
def golden_closeness():
    records = _golden_records()
    skips: list = []
    options = {**_CLOSENESS, "bootstrap_iterations": 300, "noise_iterations": 20000}
    block = _typicality_closeness(
        [r for r in records if not r.is_real_reference], records[-1],
        n_levels=11, options=options, skips=skips,
    )
    return block, skips


def _csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_golden_first_round_distributions_are_reproduced():
    """The --rounds 1 grid equals distribution_first_round_by_combo.csv to 1e-12."""
    records = _golden_records()
    block = _build(records, country="swedish_02", withdrawn=[
        "swedish_02_all_generate_evaluate_random_pick_v2_ollama_deepseek_r1_14b",
        "swedish_02_all_generate_evaluate_random_pick_v2_ollama_gemma4_e4b",
    ])["typicality_distribution"]
    rows = _csv(_PROTOTYPE / "golden" / "distribution_first_round_by_combo.csv")
    assert len(rows) == 60
    for row in rows:
        state = block["grid"]["states"][row["model"]][row["strategy"]]
        if row["withdrawn"] == "True":
            assert state == "withdrawn"
            continue
        cell = block["grid"]["cells"][row["model"]][row["strategy"]]
        assert cell["denominator"] == int(float(row["n"]))
        assert cell["distribution"] == pytest.approx([float(row[f"p{k}"]) for k in range(11)], abs=1e-12)


def test_golden_closeness_outcomes_per_combination(golden_closeness):
    block, _ = golden_closeness
    expected = {(row["model"], row["strategy"]): row for row in golden.combination_outcomes()}
    assert block["n_combinations"] == 58 and block["reference_n"] == 100
    for row in block["combinations"]:
        gold = expected[(row["model"], row["strategy"])]
        assert row["n"] == gold["n"]
        assert row["tv_similarity"]["value"] == pytest.approx(1.0 - gold["tv"], abs=1e-12)
        assert row["cliffs_delta"]["value"] == pytest.approx(gold["delta"], abs=1e-12)
        assert row["cramer_distance"]["value"] == pytest.approx(gold["cramer"], abs=1e-12)
        for outcome in ("tv_similarity", "cliffs_delta", "cramer_distance"):
            assert row[outcome]["ci_lo"] <= row[outcome]["value"] <= row[outcome]["ci_hi"]


def test_golden_noise_baseline_matches_the_prototype_floor(golden_closeness):
    """100 vs 100: prototype mean TV 0.172 (q95 0.240) -> similarity 0.828, 5th pct 0.760."""
    block, _ = golden_closeness
    meta = json.loads((_PROTOTYPE / "closeness_shape" / "shape_meta.json").read_text(encoding="utf-8"))
    floor = meta["null_floor"]["100_vs_100"]
    headline = next(e for e in block["noise_baseline"]["by_n"] if e["n"] == 100)
    assert headline["tv_similarity"]["mean"] == pytest.approx(1.0 - floor["tv"]["mean"], abs=0.003)
    assert headline["tv_similarity"]["bound"] == pytest.approx(1.0 - floor["tv"]["q95"], abs=0.01)
    assert headline["cramer_distance"]["mean"] == pytest.approx(floor["cramer"]["mean"], abs=0.005)
    assert headline["cliffs_delta"]["mean_abs"] == pytest.approx(floor["delta"]["mean_abs"], abs=0.003)


_OUTCOME_OF = {"tv_similarity": "tv", "cramer_distance": "cramer", "cliffs_delta": "delta"}


def test_golden_decomposition_point_values(golden_closeness):
    """Shares, F and partial eta^2 / omega^2 equal closeness_shape/decomposition.csv (TV via 1 - TV)."""
    block, _ = golden_closeness
    gold = {(r["outcome"], r["stat"]): float(r["estimate"])
            for r in _csv(_PROTOTYPE / "closeness_shape" / "decomposition.csv")}
    for outcome, key in _OUTCOME_OF.items():
        decomposition = block["by_outcome"][outcome]["decomposition"]
        anova = decomposition["anova"]
        assert anova["df_residual"] == 42
        for factor in ("strategy", "model"):
            f = anova["factors"][factor]
            assert f["share"] == pytest.approx(gold[(key, f"share_{factor}")], abs=1e-9)
            assert f["F"] == pytest.approx(gold[(key, f"F_{factor}")], abs=1e-9)
            assert f["partial_eta_sq"] == pytest.approx(gold[(key, f"peta2_{factor}")], abs=1e-9)
            assert f["partial_omega_sq"] == pytest.approx(gold[(key, f"pomega2_{factor}")], abs=1e-9)
        assert anova["share_residual"] == pytest.approx(gold[(key, "share_resid")], abs=1e-9)
        assert anova["share_overlap"] == pytest.approx(gold[(key, "share_overlap")], abs=1e-9)
        derived = decomposition["derived"]
        assert derived["ss_ratio_strategy_over_model"]["point"] == pytest.approx(
            gold[(key, "ratio_ss_strategy_over_model")], abs=1e-9)
        assert derived["partial_omega_sq_strategy_minus_model"]["point"] == pytest.approx(
            gold[(key, "pomega2_diff_strategy_minus_model")], abs=1e-9)
        assert decomposition["intervals"] is not None
        assert decomposition["residual_normality"]["n"] == 58


def test_golden_complete_block_tests_and_post_hocs(golden_closeness):
    block, _ = golden_closeness
    tests = json.loads((_PROTOTYPE / "closeness_shape" / "complete_block_tests.json").read_text(encoding="utf-8"))
    pairs = _csv(_PROTOTYPE / "closeness_shape" / "posthoc_pairs.csv")
    letters = dict(zip(golden.LETTERS, golden.STRATEGIES))
    for outcome, key in _OUTCOME_OF.items():
        complete = block["by_outcome"][outcome]["complete_blocks"]
        assert len(complete["complete_models"]) == 10
        assert sorted(complete["dropped_models"]) == ["ollama_deepseek_r1_14b", "ollama_gemma4_e4b"]
        for direction in ("strategy", "model"):
            friedman = complete[direction]["friedman"]
            gold = tests[key][f"friedman_{direction}"]
            assert friedman["chi2"] == pytest.approx(gold["chi2"], abs=1e-9)
            assert friedman["kendalls_w"] == pytest.approx(gold["kendalls_w"], abs=1e-9)
            w_ci = complete[direction]["kendalls_w_ci"]
            assert w_ci["lo"] <= w_ci["hi"]
        paired = complete["strategy_pairs"]["paired_t"]["pairs"]
        conover = complete["strategy_pairs"]["conover"]["pairs"]
        # A similarity runs opposite to the prototype's TV distance: every paired
        # difference and d_z flips sign, and every p is unchanged.
        sign = -1.0 if outcome == "tv_similarity" else 1.0
        for row in (r for r in pairs if r["outcome"] == key):
            pair = f"{letters[row['a']]}|{letters[row['b']]}"
            assert paired[pair]["mean_diff"] == pytest.approx(sign * float(row["mean_b_minus_a"]), abs=1e-12)
            assert paired[pair]["dz"] == pytest.approx(sign * float(row["dz"]), abs=1e-9)
            assert paired[pair]["p_holm"] == pytest.approx(float(row["p_paired_t_holm"]), abs=1e-9)
            assert conover[pair]["p_holm"] == pytest.approx(float(row["p_conover_holm"]), abs=1e-9)


def test_golden_permutation_tests_reject_at_the_floor(golden_closeness):
    """The prototype saw 0 of 10,000 permuted F at least as large; here 0 of 199 -> p = 1/200."""
    block, _ = golden_closeness
    for outcome in _OUTCOME_OF:
        for factor in ("strategy", "model"):
            perm = block["by_outcome"][outcome]["permutation"][factor]
            assert perm["n_at_least_as_extreme"] == 0
            assert perm["p"] == pytest.approx(1 / 200)

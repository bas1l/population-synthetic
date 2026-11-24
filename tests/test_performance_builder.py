"""Tests for the performance builder: matrix, ranking, stats wiring, serialisation.

Pins the overall-mean derivation, the rank order (TV-mean descending, coherence
tie-break), the factor-group sample shapes fed to Kruskal-Wallis / Dunn, and the
JSON/CSV writers' documented shapes.
"""

from __future__ import annotations

import json

import pytest

from population_synthetic.analysis.model_ranking.builder import (
    build_performance_comparison,
    write_performance_csv,
    write_performance_json,
)
from tests._performance_fixtures import ATTRIBUTES, make_combo


def _grid():
    """2 models x 2 strategies; haiku strictly better than flash on every attribute."""
    return [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": 0.1, "education_level": 0.1},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={"age_group": 0.3, "biological_sex": 0.3, "education_level": 0.3},
        ),
        make_combo(
            slug="swedish_all_generate_pick_claude_haiku", strategy="all_generate_pick",
            model="claude_haiku",
            tv_by_attr={"age_group": 0.2, "biological_sex": 0.2, "education_level": 0.2},
        ),
        make_combo(
            slug="swedish_all_generate_pick_gemini_flash", strategy="all_generate_pick",
            model="gemini_flash",
            tv_by_attr={"age_group": 0.4, "biological_sex": 0.4, "education_level": 0.4},
        ),
    ]


def test_overall_mean_and_ranking():
    result = build_performance_comparison(_grid(), ATTRIBUTES)
    assert result["ranking"] == [
        "swedish_all_pick_claude_haiku",           # mean tv-sim 0.9
        "swedish_all_generate_pick_claude_haiku",  # 0.8
        "swedish_all_pick_gemini_flash",           # 0.7
        "swedish_all_generate_pick_gemini_flash",  # 0.6
    ]
    best = result["combos"]["swedish_all_pick_claude_haiku"]
    assert best["overall"]["tv_similarity_mean"] == pytest.approx(0.9)
    assert best["overall"]["rank"] == 1
    assert best["per_attribute"]["age_group"]["tv_similarity"] == pytest.approx(0.9)
    assert best["per_attribute"]["age_group"]["tv_distance"] == pytest.approx(0.1)
    assert best["nan_attributes"] == []


def test_coherence_tie_break():
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={a: 0.2 for a in ATTRIBUTES}, coherence_score=0.99,
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={a: 0.2 for a in ATTRIBUTES}, coherence_score=0.50,
        ),
    ]
    result = build_performance_comparison(combos, ATTRIBUTES)
    assert result["ranking"] == [
        "swedish_all_pick_claude_haiku",
        "swedish_all_pick_gemini_flash",
    ]


def test_nan_attributes_recorded_and_excluded_from_mean():
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": float("nan"), "education_level": 0.3},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={a: 0.2 for a in ATTRIBUTES},
        ),
    ]
    result = build_performance_comparison(combos, ATTRIBUTES)
    combo = result["combos"]["swedish_all_pick_claude_haiku"]
    assert combo["nan_attributes"] == ["biological_sex"]
    # Mean over the two scorable attributes only: (0.9 + 0.7) / 2.
    assert combo["overall"]["tv_similarity_mean"] == pytest.approx(0.8)


def test_stats_group_shapes():
    result = build_performance_comparison(_grid(), ATTRIBUTES)
    by_model = result["stats"]["by_model"]
    # Each model pools 3 attributes x 2 strategies = 6 samples.
    assert by_model["groups"]["claude_haiku"]["n"] == 6
    assert by_model["groups"]["gemini_flash"]["n"] == 6
    assert by_model["n_combos_per_group"] == {"claude_haiku": 2, "gemini_flash": 2}
    # haiku is uniformly better -> ordered first.
    assert by_model["order"] == ["claude_haiku", "gemini_flash"]
    assert set(by_model["kruskal"]) >= {"H", "p"}
    assert len(by_model["dunn"]) == 1  # C(2, 2)
    assert set(by_model["dunn"][0]) == {"a", "b", "z", "p_raw", "p_holm"}

    by_strategy = result["stats"]["by_strategy"]
    assert by_strategy["groups"]["all_pick"]["n"] == 6
    assert by_strategy["n_combos_per_group"] == {"all_pick": 2, "all_generate_pick": 2}


def test_fewer_than_two_combos_raises():
    with pytest.raises(ValueError, match="at least 2"):
        build_performance_comparison(_grid()[:1], ATTRIBUTES)


def test_mixed_countries_raise():
    combos = _grid()[:2]
    combos.append(
        make_combo(
            slug="italian_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={a: 0.2 for a in ATTRIBUTES}, country="italian",
        )
    )
    with pytest.raises(ValueError, match="one country"):
        build_performance_comparison(combos, ATTRIBUTES)


def test_skipped_recorded_in_metadata():
    result = build_performance_comparison(
        _grid()[:2], ATTRIBUTES, skipped=[("swedish_all_pick_x", "no comparison report")]
    )
    assert result["metadata"]["skipped"] == [
        {"slug": "swedish_all_pick_x", "reason": "no comparison report"}
    ]


def test_methods_matrix_means_and_order():
    result = build_performance_comparison(_grid(), ATTRIBUTES)
    matrix = result["methods_matrix"]
    # Ordered by STRATEGY_COMPLEXITY_ORDER (all_pick before all_generate_pick).
    assert matrix["strategies"] == ["all_pick", "all_generate_pick"]
    assert matrix["attributes"] == ATTRIBUTES

    # all_pick: mean over models per attribute = (0.9 + 0.7) / 2 = 0.8 for each attr.
    all_pick = matrix["cells"]["all_pick"]
    for attr in ATTRIBUTES:
        assert all_pick[attr] == pytest.approx(0.8)
    assert all_pick["overall"] == pytest.approx(0.8)

    # all_generate_pick: (0.8 + 0.6) / 2 = 0.7 for each attr.
    all_gen = matrix["cells"]["all_generate_pick"]
    for attr in ATTRIBUTES:
        assert all_gen[attr] == pytest.approx(0.7)
    assert all_gen["overall"] == pytest.approx(0.7)


def test_methods_matrix_excludes_nan_attributes():
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": float("nan"), "education_level": 0.3},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={"age_group": 0.3, "biological_sex": 0.5, "education_level": 0.1},
        ),
    ]
    matrix = build_performance_comparison(combos, ATTRIBUTES)["methods_matrix"]
    cell = matrix["cells"]["all_pick"]
    # age_group: mean(0.9, 0.7) = 0.8; biological_sex: only flash scorable -> 0.5;
    # education_level: mean(0.7, 0.9) = 0.8.
    assert cell["age_group"] == pytest.approx(0.8)
    assert cell["biological_sex"] == pytest.approx(0.5)
    assert cell["education_level"] == pytest.approx(0.8)
    # Overall = mean of the three per-attribute means.
    assert cell["overall"] == pytest.approx((0.8 + 0.5 + 0.8) / 3)


def test_methods_matrix_all_nan_attribute_column():
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": float("nan"), "education_level": 0.3},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={"age_group": 0.3, "biological_sex": float("nan"), "education_level": 0.1},
        ),
    ]
    cell = build_performance_comparison(combos, ATTRIBUTES)["methods_matrix"]["cells"]["all_pick"]
    # biological_sex NaN for every model -> NaN cell, excluded from the overall.
    assert cell["biological_sex"] != cell["biological_sex"]
    assert cell["overall"] == pytest.approx((0.8 + 0.8) / 2)


def test_model_hosting_embedded_when_supplied():
    hosting = {"claude_haiku": "hosted", "gemini_flash": "hosted"}
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=hosting)
    assert result["metadata"]["model_hosting"] == hosting


def test_model_hosting_defaults_to_empty():
    result = build_performance_comparison(_grid(), ATTRIBUTES)
    assert result["metadata"]["model_hosting"] == {}


def test_writers(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES)

    json_path = write_performance_json(result, tmp_path / "swedish_performance.json")
    with open(json_path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert set(loaded) == {"metadata", "combos", "ranking", "methods_matrix", "stats"}
    assert loaded["stats"]["metric"] == "tv_similarity"
    assert loaded["stats"]["caveats"]

    csv_path = write_performance_csv(result, tmp_path / "swedish_performance.csv")
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].split(",")
    assert header[:9] == [
        "rank", "model", "strategy", "slug", "n", "overall_tv_similarity", "coherence_score",
        "c2st_auc", "mean_delta_v",
    ]
    assert header[9:] == [f"tv_similarity__{a}" for a in ATTRIBUTES]
    assert len(lines) == 1 + 4  # header + one row per combo
    assert lines[1].startswith("1,claude_haiku,all_pick,swedish_all_pick_claude_haiku")

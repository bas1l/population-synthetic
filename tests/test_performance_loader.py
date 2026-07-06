"""Tests for the performance loader: report extraction and filesystem discovery.

``extract_combo_performance`` is pinned against the comparison-report schema
(TV-similarity derivation, NaN omission, carried metrics, fail-fast on drift);
``load_combo_performances`` is exercised on a materialised ``tmp_path``
workspace with injected axis registries and attribute axis.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.model_ranking.loader import (
    extract_combo_performance,
    load_combo_performances,
)
from tests._performance_fixtures import (
    ATTRIBUTES,
    AXIS_IDS,
    build_workspace,
    make_multivariate,
    make_report,
)


def _attrs(country: str) -> list[str]:
    assert country == "swedish"
    return ATTRIBUTES


# --- extract_combo_performance ------------------------------------------------

def test_extract_happy_path():
    report = make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        coherence_score=0.95,
        n_synth=80,
    )
    combo = extract_combo_performance(
        "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku", report, ATTRIBUTES
    )
    assert combo.tv_similarity == pytest.approx(
        {"age_group": 0.9, "biological_sex": 0.8, "education_level": 0.7}
    )
    assert combo.n_synthetic == 80
    assert combo.coherence["score"] == 0.95
    # The other marginal metrics are carried through untouched.
    assert combo.marginals["age_group"]["kl_divergence"] == 0.1
    assert combo.marginals["age_group"]["chi_sq_p"] == 0.5
    assert combo.marginals["age_group"]["max_diff"] == 0.05


def test_extract_nan_tv_distance_omitted():
    report = make_report(
        {"age_group": 0.1, "biological_sex": float("nan"), "education_level": 0.3}
    )
    combo = extract_combo_performance(
        "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku", report, ATTRIBUTES
    )
    assert "biological_sex" not in combo.tv_similarity
    assert set(combo.tv_similarity) == {"age_group", "education_level"}


def test_extract_missing_tv_distance_raises():
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    del report["marginals"]["age_group"]["tv_distance"]
    with pytest.raises(KeyError, match="tv_distance"):
        extract_combo_performance(
            "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku",
            report, ATTRIBUTES,
        )


def test_extract_attribute_drift_raises():
    # Missing attribute.
    report = make_report({"age_group": 0.1, "biological_sex": 0.2})
    with pytest.raises(KeyError, match="education_level"):
        extract_combo_performance(
            "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku",
            report, ATTRIBUTES,
        )
    # Unknown extra attribute.
    report = make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3, "bogus": 0.4}
    )
    with pytest.raises(KeyError, match="bogus"):
        extract_combo_performance(
            "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku",
            report, ATTRIBUTES,
        )


def test_extract_old_report_without_multivariate_block():
    # Pre-change reports have no 'multivariate' key: the optional fields stay None,
    # and nothing about the existing extraction regresses.
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert "multivariate" not in report
    combo = extract_combo_performance(
        "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku", report, ATTRIBUTES
    )
    assert combo.c2st_auc is None
    assert combo.mean_delta_v is None
    assert combo.tv_similarity["age_group"] == pytest.approx(0.9)


def test_extract_new_report_populates_multivariate():
    report = make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        multivariate=make_multivariate(c2st_auc=0.73, mean_delta_v=0.12),
    )
    combo = extract_combo_performance(
        "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku", report, ATTRIBUTES
    )
    assert combo.c2st_auc == pytest.approx(0.73)
    assert combo.mean_delta_v == pytest.approx(0.12)


def test_extract_multivariate_nan_auc_tolerated():
    # A present-but-degenerate block (NaN AUC) is carried through as NaN, not None.
    report = make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        multivariate=make_multivariate(c2st_auc=float("nan")),
    )
    combo = extract_combo_performance(
        "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku", report, ATTRIBUTES
    )
    assert combo.c2st_auc != combo.c2st_auc  # NaN


def test_extract_missing_toplevel_key_raises():
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    del report["coherence"]
    with pytest.raises(KeyError, match="coherence"):
        extract_combo_performance(
            "swedish_all_pick_claude_haiku", "swedish", "all_pick", "claude_haiku",
            report, ATTRIBUTES,
        )


# --- load_combo_performances ---------------------------------------------------

_TV = {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3}


def test_load_missing_index_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="map_populations"):
        load_combo_performances(tmp_path, axis_ids=AXIS_IDS, attributes_for_country=_attrs)


def test_load_records_and_skips(tmp_path):
    base = build_workspace(
        tmp_path,
        [
            {"slug": "swedish_all_pick_claude_haiku", "country": "swedish", "report": make_report(_TV)},
            {"slug": "swedish_all_pick_gemini_flash", "country": "swedish", "report": make_report(_TV)},
            # Mapped but never compared -> missing-report skip.
            {"slug": "swedish_all_generate_pick_claude_haiku", "country": "swedish", "report": None},
            # Skipped during mapping.
            {"slug": "swedish_all_generate_pick_gemini_flash", "country": "swedish",
             "report": None, "skipped": True},
            # Legacy slug that does not decompose.
            {"slug": "seed_022_all_pick_sonnet", "country": "swedish", "report": None},
        ],
    )
    records, skipped = load_combo_performances(
        base, axis_ids=AXIS_IDS, attributes_for_country=_attrs
    )
    assert sorted(r.slug for r in records) == [
        "swedish_all_pick_claude_haiku",
        "swedish_all_pick_gemini_flash",
    ]
    assert records[0].model in {"claude_haiku", "gemini_flash"}
    assert records[0].strategy == "all_pick"
    reasons = dict(skipped)
    assert "no comparison report" in reasons["swedish_all_generate_pick_claude_haiku"]
    assert "skipped during mapping" in reasons["swedish_all_generate_pick_gemini_flash"]
    assert "not decomposable" in reasons["seed_022_all_pick_sonnet"]


def test_load_strict_missing_report_raises(tmp_path):
    base = build_workspace(
        tmp_path,
        [
            {"slug": "swedish_all_pick_claude_haiku", "country": "swedish", "report": make_report(_TV)},
            {"slug": "swedish_all_pick_gemini_flash", "country": "swedish", "report": None},
        ],
    )
    with pytest.raises(RuntimeError, match="swedish_all_pick_gemini_flash"):
        load_combo_performances(
            base, strict=True, axis_ids=AXIS_IDS, attributes_for_country=_attrs
        )


def test_load_filters_narrow_selection(tmp_path):
    base = build_workspace(
        tmp_path,
        [
            {"slug": "swedish_all_pick_claude_haiku", "country": "swedish", "report": make_report(_TV)},
            {"slug": "swedish_all_pick_gemini_flash", "country": "swedish", "report": make_report(_TV)},
        ],
    )
    records, skipped = load_combo_performances(
        base, models=["claude_haiku"], axis_ids=AXIS_IDS, attributes_for_country=_attrs
    )
    assert [r.slug for r in records] == ["swedish_all_pick_claude_haiku"]
    assert skipped == []  # filtered-out combos are not skips

    records, _ = load_combo_performances(
        base, slugs=["swedish_all_pick_gemini_flash"],
        axis_ids=AXIS_IDS, attributes_for_country=_attrs,
    )
    assert [r.slug for r in records] == ["swedish_all_pick_gemini_flash"]

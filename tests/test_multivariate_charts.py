"""Smoke tests for the Phase-4 multivariate figures.

These do not assert on pixels: they confirm the two new chart functions produce a
PNG from a tiny fixture, degrade to ``None`` on absent data, and that the builder
surfaces the optional multivariate columns without disturbing the ranking.
"""

from __future__ import annotations

import csv

from population_synthetic.analysis.comparison.charts import plot_association_heatmap
from population_synthetic.analysis.performance.builder import (
    build_performance_comparison,
    write_performance_csv,
)
from population_synthetic.analysis.performance.charts import plot_c2st_vs_tv
from tests._performance_fixtures import ATTRIBUTES, make_combo, make_multivariate, make_report

# --- association heatmap (comparison level) -----------------------------------

def test_association_heatmap_renders(tmp_path):
    report = make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        multivariate=make_multivariate(),
    )
    out = plot_association_heatmap(report, tmp_path, prefix="swedish_all_pick_x", attributes=ATTRIBUTES)
    assert out is not None
    assert out.is_file()
    assert out.name == "swedish_all_pick_x_association_heatmap.png"


def test_association_heatmap_none_without_block(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert plot_association_heatmap(report, tmp_path) is None


# --- C2ST-vs-TV scatter (performance level) -----------------------------------

def _built(with_multivariate: bool):
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": 0.1, "education_level": 0.1},
            c2st_auc=0.60 if with_multivariate else None,
            mean_delta_v=0.08 if with_multivariate else None,
        ),
        make_combo(
            slug="swedish_all_generate_pick_gemini_flash", strategy="all_generate_pick",
            model="gemini_flash",
            tv_by_attr={"age_group": 0.3, "biological_sex": 0.3, "education_level": 0.3},
            c2st_auc=0.85 if with_multivariate else None,
            mean_delta_v=0.20 if with_multivariate else None,
        ),
    ]
    return build_performance_comparison(combos, ATTRIBUTES)


def test_c2st_scatter_renders(tmp_path):
    result = _built(with_multivariate=True)
    out = plot_c2st_vs_tv(result, tmp_path / "swedish_c2st_vs_tv.png")
    assert out is not None
    assert out.is_file()


def test_c2st_scatter_none_when_no_auc(tmp_path):
    result = _built(with_multivariate=False)
    assert plot_c2st_vs_tv(result, tmp_path / "swedish_c2st_vs_tv.png") is None


# --- builder surfaces the optional columns; ranking unchanged -----------------

def test_builder_csv_carries_multivariate_columns(tmp_path):
    result = _built(with_multivariate=True)
    # Ranking is still TV-driven: haiku (better marginals) ranks first.
    assert result["ranking"][0] == "swedish_all_pick_claude_haiku"
    assert result["combos"]["swedish_all_pick_claude_haiku"]["multivariate"] == {
        "c2st_auc": 0.60,
        "mean_delta_v": 0.08,
    }

    csv_path = write_performance_csv(result, tmp_path / "swedish_performance.csv")
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert "c2st_auc" in rows[0]
    assert "mean_delta_v" in rows[0]
    top = next(r for r in rows if r["slug"] == "swedish_all_pick_claude_haiku")
    assert float(top["c2st_auc"]) == 0.60
    assert float(top["mean_delta_v"]) == 0.08


def test_builder_csv_blank_when_multivariate_absent(tmp_path):
    result = _built(with_multivariate=False)
    csv_path = write_performance_csv(result, tmp_path / "swedish_performance.csv")
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # None -> empty CSV cell, no crash.
    assert rows[0]["c2st_auc"] == ""
    assert rows[0]["mean_delta_v"] == ""

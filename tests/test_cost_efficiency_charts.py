"""Tests for the cost-vs-fidelity scatter and the CLI that saves it.

The renderer is a pure consumer of the built document, so every assertion here is a
structural property of the artists it actually drew -- the marker offsets, the axis
scale, the shaded band, the printed text -- never a byte comparison of the PNG, whose
bytes move with matplotlib metadata and font hinting without anything about the figure
having changed.

Two regressions this file pins:

* **A drawn point is never silently lost.** The renderer reads ``cost`` and ``accuracy``
  out of nested document blocks; a renderer keyed to the wrong literal draws an empty
  axes without raising (ADR 2026-08-12). ``test_every_combination_is_drawn`` counts the
  markers against the document.
* **The unmetered band is labelled, and its label says unmetered is not free.** Drawing a
  local model at zero dollars without that sentence publishes a claim the pricing config
  cannot support.

The last tests drive the real CLI edge by subprocess against a ``tmp_path`` workspace,
because the flags and the argument resolution there are what a unit test of the renderer
cannot reach. They use real model and strategy axis ids, so the pricing config and the
strategy-complexity order resolve exactly as they do in production.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # noqa: E402 -- before any package import that may touch pyplot

import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.cost_efficiency.builder import build_document  # noqa: E402
from population_synthetic.analysis.cost_efficiency.charts import (  # noqa: E402
    HOST_MARKERS,
    plot_cost_vs_accuracy,
)
from population_synthetic.analysis.cost_efficiency.loader import load_cost_records  # noqa: E402
from population_synthetic.analysis.utils.cost_csv import read_cost_csv  # noqa: E402
from population_synthetic.analysis.utils.registry import analysis_output_dir  # noqa: E402
from tests._cost_efficiency_fixtures import (  # noqa: E402
    COMPLEX_STRATEGY,
    COUNTRY,
    METERED_MODEL,
    SIMPLE_STRATEGY,
    UNMETERED_MODEL,
    build_base,
    make_pricing,
)

_SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "analyze_cost_efficiency.py"
_PRICING = make_pricing()

_MIXED = (
    (METERED_MODEL, SIMPLE_STRATEGY),
    (METERED_MODEL, COMPLEX_STRATEGY),
    (UNMETERED_MODEL, SIMPLE_STRATEGY),
    (UNMETERED_MODEL, COMPLEX_STRATEGY),
)


def _document(tmp_path, **kwargs):
    base = build_base(tmp_path, **kwargs)
    return build_document(load_cost_records(base, COUNTRY, pricing=_PRICING))


def _all_text(fig) -> str:
    """Every string the figure draws, with the caption's line wrapping undone.

    The caption is ``textwrap.fill``-ed to the figure width, so a sentence read out of
    the document arrives split across lines; collapsing whitespace lets a test assert the
    sentence rather than the layout it happened to be wrapped into.
    """
    joined = " ".join(t.get_text() for t in fig.findobj(match=matplotlib.text.Text))
    return " ".join(joined.split())


# ---------------------------------------------------------------------------
# The renderer
# ---------------------------------------------------------------------------

def test_returns_an_unsaved_figure(tmp_path) -> None:
    fig = plot_cost_vs_accuracy(_document(tmp_path, joined=_MIXED))
    assert isinstance(fig, matplotlib.figure.Figure)
    matplotlib.pyplot.close(fig)


def test_every_combination_is_drawn(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    ax = fig.axes[0]
    # One PathCollection per point (each scatter call draws one).
    assert len(ax.collections) == document["n_combinations"] == 4
    matplotlib.pyplot.close(fig)


def test_metered_points_carry_their_measured_cost_and_accuracy(tmp_path) -> None:
    document = _document(tmp_path, joined=((METERED_MODEL, SIMPLE_STRATEGY),),
                         generated=10, clean=8, accuracy=0.77)
    entry = document["combinations"][0]
    fig = plot_cost_vs_accuracy(document)
    offsets = fig.axes[0].collections[0].get_offsets().tolist()
    assert len(offsets) == 1
    x, y = offsets[0]
    assert x == pytest.approx(entry["cost"]["cost_per_usable_persona"])
    assert y == pytest.approx(entry["accuracy"]["overall_tv_similarity"])
    matplotlib.pyplot.close(fig)


def test_unmetered_points_sit_inside_the_band_and_metered_ones_outside(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    ax = fig.axes[0]
    linthresh = ax.xaxis.get_transform().linthresh

    unmetered = {e["slug"] for e in document["combinations"] if e["cost"]["unmetered"]}
    xs = [c.get_offsets().tolist()[0][0] for c in ax.collections]
    inside = [x for x in xs if abs(x) < linthresh]
    outside = [x for x in xs if abs(x) >= linthresh]
    assert len(inside) == len(unmetered) == 2
    assert len(outside) == 2
    assert all(x > 0 for x in outside)
    matplotlib.pyplot.close(fig)


def test_x_axis_is_symlog_so_a_measured_zero_is_placeable(tmp_path) -> None:
    fig = plot_cost_vs_accuracy(_document(tmp_path, joined=_MIXED))
    assert fig.axes[0].get_xscale() == "symlog"
    matplotlib.pyplot.close(fig)


def test_left_limit_stops_at_the_band_edge_so_no_negative_cost_is_shown(tmp_path) -> None:
    fig = plot_cost_vs_accuracy(_document(tmp_path, joined=_MIXED))
    ax = fig.axes[0]
    linthresh = ax.xaxis.get_transform().linthresh
    assert ax.get_xlim()[0] == pytest.approx(-linthresh)
    # No tick may label a position inside the band: it holds one value, zero.
    assert all(abs(t) >= linthresh for t in ax.get_xticks())
    matplotlib.pyplot.close(fig)


def test_band_label_says_unmetered_is_not_free(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    text = _all_text(fig)
    assert "unmetered" in text
    assert "not free" in text
    assert " ".join(document["unmetered_note"].split()) in text
    matplotlib.pyplot.close(fig)


def test_cost_basis_is_printed_on_the_figure(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    assert document["cost_basis"] in _all_text(fig)
    matplotlib.pyplot.close(fig)


def test_withdrawn_combinations_are_counted_on_the_figure_not_omitted(tmp_path) -> None:
    document = _document(
        tmp_path,
        joined=((METERED_MODEL, SIMPLE_STRATEGY),),
        withdrawn=((UNMETERED_MODEL, COMPLEX_STRATEGY),),
    )
    fig = plot_cost_vs_accuracy(document)
    text = _all_text(fig)
    assert "WITHDRAWN" in text
    assert "1 combination(s) were WITHDRAWN by the full-N rule and are not drawn" in text
    matplotlib.pyplot.close(fig)


def test_non_composite_reason_travels_onto_the_figure(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    assert "No accuracy-per-dollar" in _all_text(fig)
    matplotlib.pyplot.close(fig)


def test_hosting_changes_the_marker_shape(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    hosting = {METERED_MODEL: "hosted", UNMETERED_MODEL: "local"}
    fig = plot_cost_vs_accuracy(document, hosting=hosting)
    labels = {t.get_text() for t in fig.legends[1].get_texts()}
    assert "local (Ollama)" in labels
    assert "hosted (API)" in labels
    assert set(HOST_MARKERS) == {"hosted", "local"}
    matplotlib.pyplot.close(fig)


def test_method_legend_is_in_complexity_order(tmp_path) -> None:
    document = _document(tmp_path, joined=_MIXED)
    fig = plot_cost_vs_accuracy(document)
    labels = [t.get_text() for t in fig.legends[0].get_texts()]
    assert labels == [SIMPLE_STRATEGY, COMPLEX_STRATEGY]
    matplotlib.pyplot.close(fig)


def test_empty_document_raises_rather_than_drawing_empty_axes() -> None:
    with pytest.raises(ValueError, match="no combination"):
        plot_cost_vs_accuracy({"combinations": [], "country": "x"})


# ---------------------------------------------------------------------------
# The CLI edge
# ---------------------------------------------------------------------------

def _run(base: Path, *extra: str) -> Path:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--country", COUNTRY,
         "--output-base", str(base), "--force", *extra],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return analysis_output_dir("cost_efficiency", base)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_base(
        tmp_path_factory.mktemp("cost_efficiency_cli"),
        joined=_MIXED,
        withdrawn=((UNMETERED_MODEL, "all_generate_evaluate_pick_v2"),),
    )


def test_no_charts_leaves_no_png_and_no_svg(workspace) -> None:
    out_dir = _run(workspace, "--no-charts")
    assert (out_dir / f"{COUNTRY}_cost_efficiency.csv").is_file()
    assert (out_dir / f"{COUNTRY}_cost_efficiency.json").is_file()
    assert list(out_dir.glob("*.png")) == []
    assert list(out_dir.glob("*.svg")) == []


def test_a_normal_run_emits_both_formats(workspace) -> None:
    out_dir = _run(workspace)
    assert (out_dir / f"{COUNTRY}_cost_vs_fidelity.png").is_file()
    assert (out_dir / f"{COUNTRY}_cost_vs_fidelity.svg").is_file()


def test_the_csv_carries_one_row_per_joined_combination(workspace) -> None:
    out_dir = _run(workspace, "--no-charts")
    rows = read_cost_csv(out_dir / f"{COUNTRY}_cost_efficiency.csv")
    assert len(rows) == len(_MIXED)
    assert {row.cost_basis for row in rows} == {"generated_pool_01_raw"}
    assert any(row.unmetered for row in rows)
    assert any(not row.unmetered for row in rows)


def test_the_csv_and_json_are_byte_reproducible(workspace) -> None:
    out_dir = _run(workspace, "--no-charts")
    csv_first = (out_dir / f"{COUNTRY}_cost_efficiency.csv").read_bytes()
    json_first = (out_dir / f"{COUNTRY}_cost_efficiency.json").read_bytes()
    _run(workspace, "--no-charts")
    assert (out_dir / f"{COUNTRY}_cost_efficiency.csv").read_bytes() == csv_first
    assert (out_dir / f"{COUNTRY}_cost_efficiency.json").read_bytes() == json_first


def test_the_driver_reports_the_withdrawn_combination(workspace) -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--country", COUNTRY,
         "--output-base", str(workspace), "--force", "--no-charts"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WITHDRAWN and therefore NOT plotted (1)" in result.stdout


def test_an_unmatched_key_fails_the_cli_loudly(workspace, tmp_path) -> None:
    import shutil

    from tests._cost_efficiency_fixtures import write_performance

    broken = tmp_path / "broken"
    shutil.copytree(workspace, broken)
    write_performance(broken, [(METERED_MODEL, SIMPLE_STRATEGY, 0.8, 8)])

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--country", COUNTRY,
         "--output-base", str(broken), "--force", "--no-charts"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 1
    assert "not one-to-one" in result.stderr

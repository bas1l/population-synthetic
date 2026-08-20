"""Tests for the two ``validation_attrition`` figures and the CLI that saves them.

The renderers are pure consumers of the built document, so every fixture here is an
in-memory dict and every assertion is a structural property of the artists the renderer
actually drew -- the imshow array, the tick labels, the in-cell annotations and the
overlay patches -- never a byte comparison of the PNG, whose bytes move with matplotlib
metadata and font hinting without anything about the figure having changed.

The regression this file exists to pin is the one ADR 2026-08-12 records: a renderer that
reads a value by a key the document does not carry paints every cell grey and labels it
absent **without raising**, producing a plausible figure that has silently dropped its
content. ``test_populated_cell_is_not_rendered_as_missing`` and its siblings assert the
four cell states are drawn distinctly and that a measured cell is never one of the two
grey ones.

The last three tests drive the real CLI edge by subprocess against a ``tmp_path``
workspace holding the gate's three records, because the flags and the argument resolution
at that edge are exactly what a unit test of the renderers cannot reach.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # noqa: E402 -- before any package import that may touch pyplot

import csv  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Mapping, Sequence  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.cap_index import INDEX_FILENAME  # noqa: E402
from population_synthetic.analysis.utils.palette import MISSING_COLOR  # noqa: E402
from population_synthetic.analysis.utils.registry import analysis_output_dir  # noqa: E402
from population_synthetic.analysis.validation_attrition.charts import (  # noqa: E402
    CELL_STATES,
    _cell_state,
    _segment_counts,
    plot_attrition_funnel,
    plot_mapped_validity_grid,
)
from population_synthetic.analysis.validation_attrition.loader import (  # noqa: E402
    MAPPED_SUMMARY_PROCESS_ID,
    RAW_SUMMARY_PROCESS_ID,
    SUMMARY_FILENAME,
)

_COUNTRY = "swedish"
_SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "analyze_validation_attrition.py"

# Two real strategy ids, in the config-derived order the columns must follow.
_METHODS = strategy_complexity_order(["all_pick", "all_generate_pick"])
_SIMPLE, _COMPLEX = _METHODS

_RAW_HEADER = (
    "slug", "has_issues", "n_personas", "passed", "failed",
    "missing_identity", "n_expected_keys", "pass_rate_pct",
)
_MAPPED_HEADER = ("slug", "has_issues", "n_personas", "passed", "failed", "pass_rate_pct")


# --------------------------------------------------------------------------- #
# in-memory document fixtures                                                   #
# --------------------------------------------------------------------------- #


def _entry(
    model: str,
    strategy: str,
    *,
    generated: int = 150,
    raw_valid: int | None = None,
    clean: int = 120,
    selected: int = 100,
    excluded: bool = False,
) -> dict[str, Any]:
    """One combination entry shaped exactly as ``builder.build_document`` emits it."""
    raw_valid = generated if raw_valid is None else raw_valid
    return {
        "slug": f"{_COUNTRY}_{strategy}_{model}",
        "country": _COUNTRY,
        "model": model,
        "strategy": strategy,
        "requested_n": 100,
        "funnel": {
            "generated": generated,
            "raw_valid": raw_valid,
            "mapped_valid": clean,
            "clean": clean,
            "selected": selected,
        },
        "retention_rate": None if generated == 0 else clean / generated,
        "generation_multiplier": None if clean == 0 else generated / clean,
        "excluded": excluded,
        "exclusion_reason": "fewer clean personas than the requested n=100" if excluded else "",
        "had_surplus": clean > 100,
    }


def _document(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    generated = sum(e["funnel"]["generated"] for e in entries)
    clean = sum(e["funnel"]["clean"] for e in entries)
    return {
        "process": "validation_attrition",
        "country": _COUNTRY,
        "schema_version": 1,
        "n_combinations": len(entries),
        "n_excluded": sum(1 for e in entries if e["excluded"]),
        "totals": {
            "generated": generated,
            "raw_valid": sum(e["funnel"]["raw_valid"] for e in entries),
            "mapped_valid": sum(e["funnel"]["mapped_valid"] for e in entries),
            "clean": clean,
            "selected": sum(e["funnel"]["selected"] for e in entries),
            "retention_rate": None if generated == 0 else clean / generated,
            "generation_multiplier": None if clean == 0 else generated / clean,
        },
        "combinations": list(entries),
        "excluded_combinations": [
            {
                "slug": e["slug"], "requested_n": e["requested_n"],
                "generated": e["funnel"]["generated"], "clean": e["funnel"]["clean"],
                "reason": e["exclusion_reason"],
            }
            for e in entries if e["excluded"]
        ],
        "skipped_combinations": [],
        "provenance": {"consumed_artifacts": []},
    }


def _annotations(ax) -> list[str]:
    return [t.get_text() for t in ax.texts]


def _annotation_at(ax, x: float, y: float) -> str:
    """The in-cell annotation drawn at data coordinates (*x*, *y*)."""
    for text in ax.texts:
        tx, ty = text.get_position()
        if abs(tx - x) < 1e-6 and abs(ty - y) < 1e-6:
            return text.get_text()
    raise AssertionError(f"no annotation drawn at cell ({x}, {y})")


def _hatched_cells(ax) -> set[tuple[int, int]]:
    """``(row, column)`` of every cell carrying the withdrawal hatch."""
    cells = set()
    for patch in ax.patches:
        if patch.get_hatch():
            x, y = patch.get_xy()
            cells.add((round(y + 0.5), round(x + 0.5)))
    return cells


def _dotted_cells(ax) -> set[tuple[int, int]]:
    """``(row, column)`` of every cell carrying the undefined-rate dotted border."""
    cells = set()
    for patch in ax.patches:
        if patch.get_hatch():
            continue
        style = patch.get_linestyle()
        if isinstance(style, tuple) and style[1] is not None and patch.get_linewidth() > 1.0:
            x, y = patch.get_xy()
            cells.add((round(y + 0.5), round(x + 0.5)))
    return cells


# --------------------------------------------------------------------------- #
# the cell-state classifier                                                     #
# --------------------------------------------------------------------------- #


def test_cell_states_are_exactly_four_and_mutually_exclusive() -> None:
    assert CELL_STATES == ("absent", "undefined", "withdrawn", "measured")
    assert _cell_state(None) == "absent"
    assert _cell_state(_entry("claude_haiku", _SIMPLE)) == "measured"
    assert _cell_state(_entry("claude_haiku", _SIMPLE, clean=9, selected=0, excluded=True)) == (
        "withdrawn"
    )
    # An empty pool outranks the withdrawal for the FILL: there is no rate to paint.
    assert _cell_state(
        _entry("claude_haiku", _SIMPLE, generated=0, raw_valid=0, clean=0, selected=0,
               excluded=True)
    ) == "undefined"


# --------------------------------------------------------------------------- #
# the model x method grid                                                       #
# --------------------------------------------------------------------------- #


def test_populated_cell_is_not_rendered_as_missing() -> None:
    """The ADR 2026-08-12 regression: a measured cell must never come out grey.

    A renderer reading its value by a key the document does not carry masks every cell
    and labels it absent without raising, so the assertion has to be on the drawn array
    and the drawn text, not on the absence of an exception.
    """
    fig = plot_mapped_validity_grid(_document([_entry("claude_haiku", _SIMPLE, clean=120)]))
    ax = fig.axes[0]
    array = ax.get_images()[0].get_array()

    assert not np.ma.getmaskarray(array)[0, 0], "a measured cell was masked -> painted grey"
    assert array[0, 0] == pytest.approx(0.8)
    assert _annotation_at(ax, 0, 0) == "80.0\n120/150"
    assert "not\ngenerated" not in _annotations(ax)
    assert "no rate\nN=0" not in _annotations(ax)

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_grid_draws_all_four_states_distinguishably() -> None:
    """Measured, withdrawn, undefined and absent must each be separable on the figure."""
    document = _document([
        _entry("claude_haiku", _SIMPLE, clean=120),                                  # measured
        _entry("claude_haiku", _COMPLEX, clean=9, selected=0, excluded=True),        # withdrawn
        _entry("gemini_flash", _SIMPLE, generated=0, raw_valid=0, clean=0,
               selected=0, excluded=True),                                            # undefined
        # gemini_flash x _COMPLEX is deliberately absent from the document.
    ])
    fig = plot_mapped_validity_grid(document)
    ax = fig.axes[0]
    array = ax.get_images()[0].get_array()
    mask = np.ma.getmaskarray(array)
    models = [label.get_text() for label in ax.get_yticklabels()]
    haiku, gemini = models.index("claude_haiku"), models.index("gemini_flash")

    # measured and withdrawn both carry a painted value; the two grey states do not.
    assert not mask[haiku, 0] and not mask[haiku, 1]
    assert mask[gemini, 0] and mask[gemini, 1]

    # ... and the withdrawn cell is its measured rate, emphatically not zero.
    assert array[haiku, 1] == pytest.approx(9 / 150)
    assert _annotation_at(ax, 1, haiku) == "6.0\n9/150"

    # The two grey states are separated by their label and their border.
    assert _annotation_at(ax, 0, gemini) == "no rate\nN=0"
    assert _annotation_at(ax, 1, gemini) == "not\ngenerated"
    assert (gemini, 0) in _dotted_cells(ax)
    assert (gemini, 1) not in _dotted_cells(ax)

    # The withdrawal marking is independent of the fill: it is drawn on the withdrawn
    # cell AND on the withdrawn cell whose pool was empty.
    assert _hatched_cells(ax) == {(haiku, 1), (gemini, 0)}

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_grid_columns_follow_the_config_complexity_order() -> None:
    """Column order is a config fact, so the reversed input must not reorder them."""
    document = _document([
        _entry("claude_haiku", _COMPLEX),
        _entry("claude_haiku", _SIMPLE),
    ])
    fig = plot_mapped_validity_grid(document)
    ax = fig.axes[0]

    assert [label.get_text() for label in ax.get_xticklabels()] == list(_METHODS)

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_grid_rows_cover_every_model_including_a_fully_withdrawn_one() -> None:
    """A model withdrawn under every method still gets a row -- this is the one figure
    that reports withdrawal, so dropping it would erase the finding."""
    document = _document([
        _entry("claude_haiku", _SIMPLE),
        _entry("gemini_flash", _SIMPLE, clean=11, selected=0, excluded=True),
        _entry("gemini_flash", _COMPLEX, clean=7, selected=0, excluded=True),
    ])
    fig = plot_mapped_validity_grid(document)
    ax = fig.axes[0]

    assert sorted(label.get_text() for label in ax.get_yticklabels()) == [
        "claude_haiku", "gemini_flash",
    ]
    # Worst pooled survival last.
    assert [label.get_text() for label in ax.get_yticklabels()][-1] == "gemini_flash"

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_grid_cell_prints_the_denominator_behind_its_rate() -> None:
    fig = plot_mapped_validity_grid(
        _document([_entry("claude_haiku", _SIMPLE, generated=549, clean=132)])
    )
    ax = fig.axes[0]

    assert _annotation_at(ax, 0, 0).endswith("132/549")

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_grid_raises_on_an_empty_document() -> None:
    with pytest.raises(ValueError, match="no combination"):
        plot_mapped_validity_grid(_document([]))


def test_missing_colour_is_the_shared_one_not_a_local_literal() -> None:
    """Pins that the grey the grid uses is the layer's, so a palette change moves it."""
    fig = plot_mapped_validity_grid(_document([_entry("claude_haiku", _SIMPLE)]))
    ax = fig.axes[0]
    bad = ax.get_images()[0].cmap.get_bad()

    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    assert tuple(bad)[:3] == pytest.approx(mcolors.to_rgb(MISSING_COLOR))
    plt.close(fig)


# --------------------------------------------------------------------------- #
# the funnel                                                                    #
# --------------------------------------------------------------------------- #


def test_funnel_segments_partition_the_generated_pool() -> None:
    """The four slices are a partition, so they sum to the pool exactly."""
    entry = _entry("claude_haiku", _SIMPLE, generated=150, raw_valid=140, clean=120, selected=100)
    slices = _segment_counts(entry)

    assert slices == {
        "failed_raw": 10, "failed_mapped": 20, "clean_unselected": 20, "selected": 100,
    }
    assert sum(slices.values()) == 150


def test_funnel_segments_of_a_withdrawn_combination_never_go_negative() -> None:
    entry = _entry("claude_haiku", _SIMPLE, generated=150, clean=9, selected=0, excluded=True)
    slices = _segment_counts(entry)

    assert slices["selected"] == 0
    assert slices["clean_unselected"] == 9
    assert sum(slices.values()) == 150


def test_funnel_segments_raise_when_the_counts_do_not_partition() -> None:
    entry = _entry("claude_haiku", _SIMPLE, generated=150, raw_valid=100, clean=120)
    with pytest.raises(ValueError, match="do not partition"):
        _segment_counts(entry)


def test_funnel_prints_the_denominator_on_every_bar() -> None:
    document = _document([
        _entry("claude_haiku", _SIMPLE, generated=150, clean=120),
        _entry("gemini_flash", _SIMPLE, generated=549, clean=132),
    ])
    fig = plot_attrition_funnel(document)
    ax = fig.axes[0]
    texts = _annotations(ax)

    assert any(t.startswith("N=150") for t in texts)
    assert any(t.startswith("N=549") for t in texts)
    # And the rate beside it is the document's own, not a recomputation.
    assert any("retained 80.0%" in t for t in texts)
    assert any("retained 24.0%" in t for t in texts)

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_funnel_draws_an_empty_pool_as_a_stated_band_not_an_absent_row() -> None:
    document = _document([
        _entry("claude_haiku", _SIMPLE, generated=0, raw_valid=0, clean=0, selected=0),
    ])
    fig = plot_attrition_funnel(document)
    ax = fig.axes[0]

    assert any("generated = 0" in t for t in _annotations(ax))
    assert any(t == "N=0" for t in _annotations(ax))

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_funnel_marks_a_withdrawn_combination_in_its_row_label() -> None:
    document = _document([
        _entry("claude_haiku", _SIMPLE, clean=120),
        _entry("gemini_flash", _SIMPLE, clean=9, selected=0, excluded=True),
    ])
    fig = plot_attrition_funnel(document)
    ax = fig.axes[0]

    labels = [label.get_text() for label in ax.get_yticklabels()]
    assert any(label.endswith("[withdrawn]") for label in labels)
    assert sum(label.endswith("[withdrawn]") for label in labels) == 1

    import matplotlib.pyplot as plt
    plt.close(fig)


def test_funnel_raises_on_an_empty_document() -> None:
    with pytest.raises(ValueError, match="no combination"):
        plot_attrition_funnel(_document([]))


# --------------------------------------------------------------------------- #
# the CLI edge                                                                  #
# --------------------------------------------------------------------------- #


def _cap_entry(
    model: str,
    strategy: str,
    *,
    raw_total: int = 150,
    raw_passed: int = 150,
    mapped_passed: int = 120,
    selected: int = 100,
    excluded: bool = False,
) -> dict[str, Any]:
    slug = f"{_COUNTRY}_{strategy}_{model}"
    return {
        "slug": slug,
        "country": _COUNTRY,
        "requested_n": 100,
        "raw_total": raw_total,
        "raw_passed": raw_passed,
        "mapped_passed": mapped_passed,
        "clean_available": mapped_passed,
        "selected": selected,
        "seed": 0,
        "selected_ids": [f"persona_{i:05d}" for i in range(selected)],
        "truncated": mapped_passed > 100,
        "synthetic_file": None if excluded else f"{slug}.json",
        "real_file": None if excluded else f"real_{_COUNTRY}.json",
        "mapped_n": selected,
        "excluded": excluded,
        "exclusion_reason": (
            f"only {mapped_passed} clean persona(s) pass both validity gates, fewer than "
            "the requested n=100" if excluded else None
        ),
    }


def _build_workspace(tmp_path: Path, entries: Sequence[Mapping[str, Any]]) -> Path:
    """Materialise the gate's three records under *tmp_path*; return the output base."""
    cap_dir = analysis_output_dir("population_cap", tmp_path)
    cap_dir.mkdir(parents=True, exist_ok=True)
    (cap_dir / INDEX_FILENAME).write_text(json.dumps(list(entries), indent=2), encoding="utf-8")

    raw_rows, mapped_rows = [], []
    for entry in entries:
        slug, raw_n, raw_passed = entry["slug"], entry["raw_total"], entry["raw_passed"]
        mapped_n, mapped_passed = raw_passed, entry["mapped_passed"]
        raw_rows.append(
            [slug, raw_passed < raw_n, raw_n, raw_passed, raw_n - raw_passed, 0, 14, 0.0]
        )
        mapped_rows.append(
            [slug, mapped_passed < mapped_n, mapped_n, mapped_passed,
             mapped_n - mapped_passed, 0.0]
        )

    for process_id, header, rows in (
        (RAW_SUMMARY_PROCESS_ID, _RAW_HEADER, raw_rows),
        (MAPPED_SUMMARY_PROCESS_ID, _MAPPED_HEADER, mapped_rows),
    ):
        path = analysis_output_dir(process_id, tmp_path) / SUMMARY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(list(header))
            writer.writerows(rows)
    return tmp_path


def _run_cli(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--output-base", str(tmp_path), "--dpi", "60", *extra],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return _build_workspace(tmp_path, [
        _cap_entry("claude_haiku", _SIMPLE),
        _cap_entry("claude_haiku", _COMPLEX, mapped_passed=9, selected=0, excluded=True),
        _cap_entry("gemini_flash", _SIMPLE, raw_total=190, raw_passed=180, mapped_passed=140),
    ])


def test_cli_writes_both_tables_and_both_figures(workspace: Path) -> None:
    result = _run_cli(workspace)
    assert result.returncode == 0, result.stderr
    out_dir = analysis_output_dir("validation_attrition", workspace)

    assert (out_dir / f"{_COUNTRY}_attrition.json").is_file()
    with open(out_dir / f"{_COUNTRY}_attrition.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 3
    withdrawn = [r for r in rows if r["excluded"] == "true"]
    assert len(withdrawn) == 1
    assert withdrawn[0]["selected"] == "0"
    assert withdrawn[0]["retention_rate"] == str(9 / 150)
    assert withdrawn[0]["generation_multiplier"] == str(150 / 9)

    for stem in (f"{_COUNTRY}_attrition_funnel", f"{_COUNTRY}_mapped_validity_grid"):
        assert (out_dir / f"{stem}.png").is_file()
        assert (out_dir / f"{stem}.svg").is_file()


def test_cli_no_charts_writes_no_png_and_no_svg(workspace: Path) -> None:
    result = _run_cli(workspace, "--no-charts")
    assert result.returncode == 0, result.stderr
    out_dir = analysis_output_dir("validation_attrition", workspace)

    assert (out_dir / f"{_COUNTRY}_attrition.csv").is_file()
    assert list(out_dir.glob("*.png")) == []
    assert list(out_dir.glob("*.svg")) == []

    # ... and a second, ordinary run then produces both formats for both figures.
    assert _run_cli(workspace, "--force").returncode == 0
    assert len(list(out_dir.glob("*.png"))) == 2
    assert len(list(out_dir.glob("*.svg"))) == 2


def test_cli_is_idempotent_and_skips_without_force(workspace: Path) -> None:
    assert _run_cli(workspace, "--no-charts").returncode == 0
    out_dir = analysis_output_dir("validation_attrition", workspace)
    first_csv = (out_dir / f"{_COUNTRY}_attrition.csv").read_bytes()
    first_json = (out_dir / f"{_COUNTRY}_attrition.json").read_bytes()

    skipped = _run_cli(workspace, "--no-charts")
    assert skipped.returncode == 0
    assert "SKIP (exists)" in skipped.stdout

    forced = _run_cli(workspace, "--no-charts", "--force")
    assert forced.returncode == 0
    # JSON and CSV only: matplotlib stamps every SVG with a creation date, so no figure
    # in this repository is byte-stable and none is claimed to be.
    assert (out_dir / f"{_COUNTRY}_attrition.csv").read_bytes() == first_csv
    assert (out_dir / f"{_COUNTRY}_attrition.json").read_bytes() == first_json


def test_cli_exits_nonzero_when_the_gate_has_recorded_nothing(tmp_path: Path) -> None:
    _build_workspace(tmp_path, [])
    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "cap_populations.py" in result.stderr

"""Smoke tests for the per-slug figures added for the JSON-only comparison metrics.

Like ``test_multivariate_charts.py`` these do not assert on pixels: each confirms
the figure produces a PNG with the expected filename from a tiny fixture, and
degrades to ``None`` on an absent block or all-NaN data. Also asserts the shared
``write_comparison_artifacts`` orchestrator lays down the full artifact set.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from population_synthetic.analysis.fidelity import charts
from population_synthetic.analysis.fidelity.charts import (
    plot_c2st,
    plot_coherence,
    plot_combination_plausibility,
    plot_joint_chi_sq,
    plot_joint_fidelity,
)
from population_synthetic.analysis.utils.style import MAX_HEIGHT, MAX_WIDTH
from tests._performance_fixtures import ATTRIBUTES, make_multivariate, make_report

_PREFIX = "swedish_02_all_pick_v2_x"

_JF_PAIRS = [
    {"attr_x": "age_group", "attr_y": "biological_sex",
     "joint_tv": 0.12, "grounded": True, "basis": "audit"},
    {"attr_x": "age_group", "attr_y": "education_level",
     "joint_tv": 0.20, "grounded": False, "basis": "reference"},
]

_CHECKS = [
    {"attributes": ["age_group", "education_level", "employment_status"], "k": 3,
     "threshold": 0.001, "n_total": 100, "n_impossible": 2, "n_rare": 3,
     "n_plausible": 95, "fraction_impossible": 0.02, "fraction_rare": 0.03},
]


def _report(**mv_kwargs):
    return make_report(
        {"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
        multivariate=make_multivariate(**mv_kwargs),
    )


# --- C2ST ---------------------------------------------------------------------

def test_c2st_renders(tmp_path):
    out = plot_c2st(_report(), tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_c2st.png"


def test_c2st_none_without_block(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert plot_c2st(report, tmp_path, prefix=_PREFIX) is None


def test_c2st_none_when_auc_nan(tmp_path):
    assert plot_c2st(_report(c2st_auc=math.nan), tmp_path, prefix=_PREFIX) is None


# --- grounded joint TV --------------------------------------------------------

def test_joint_fidelity_renders(tmp_path):
    out = plot_joint_fidelity(_report(joint_fidelity_pairs=_JF_PAIRS), tmp_path,
                              prefix=_PREFIX, attributes=ATTRIBUTES)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_joint_fidelity.png"


def test_joint_fidelity_none_without_pairs(tmp_path):
    assert plot_joint_fidelity(_report(), tmp_path, prefix=_PREFIX) is None


def test_joint_fidelity_none_when_all_nan(tmp_path):
    nan_pairs = [{**p, "joint_tv": math.nan} for p in _JF_PAIRS]
    assert plot_joint_fidelity(_report(joint_fidelity_pairs=nan_pairs), tmp_path, prefix=_PREFIX) is None


# --- k-way combination plausibility -------------------------------------------

def test_combination_plausibility_renders(tmp_path):
    out = plot_combination_plausibility(_report(combination_checks=_CHECKS), tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_combination_plausibility.png"


def test_combination_plausibility_none_without_checks(tmp_path):
    assert plot_combination_plausibility(_report(), tmp_path, prefix=_PREFIX) is None


def test_combination_plausibility_none_when_n_total_zero(tmp_path):
    empty_b = [{**_CHECKS[0], "n_total": 0, "fraction_impossible": math.nan, "fraction_rare": math.nan}]
    assert plot_combination_plausibility(_report(combination_checks=empty_b), tmp_path, prefix=_PREFIX) is None


# --- legacy: joint chi-squared ------------------------------------------------

def test_joint_chi_sq_renders(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
                         joint_chi_sq={"age_group_x_education_level": 0.3, "age_group_x_biological_sex": 0.01})
    out = plot_joint_chi_sq(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_joint_chi_sq.png"


def test_joint_chi_sq_none_when_empty(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    assert plot_joint_chi_sq(report, tmp_path, prefix=_PREFIX) is None


# --- legacy: coherence --------------------------------------------------------

def test_coherence_renders_with_flagged(tmp_path):
    flagged = [
        {"id": 0, "age_group": "75-85", "education_level": "No Formal Education",
         "employment_status": "Employed", "probability": 0.0},
        {"id": 1, "age_group": "18-24", "education_level": "University Degree",
         "employment_status": "Retired", "probability": 0.0005},
    ]
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3},
                         flagged=flagged)
    out = plot_coherence(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()
    assert out.name == f"{_PREFIX}_coherence.png"


def test_coherence_renders_without_flagged(tmp_path):
    report = make_report({"age_group": 0.1, "biological_sex": 0.2, "education_level": 0.3})
    out = plot_coherence(report, tmp_path, prefix=_PREFIX)
    assert out is not None and out.is_file()


def test_coherence_none_without_block(tmp_path):
    assert plot_coherence({}, tmp_path, prefix=_PREFIX) is None


# --- radar grid: the printable-page budget at production scale -----------------

#: The shape of the live Swedish sweep -- 12 model arms across the five generation
#: methods -- and the smallest grid this regression is allowed to shrink to. The other
#: fixtures in this module are three-category reports for a single combination, which
#: never reach the state the defect needed: a canvas already clamped to the printable
#: page by `grow_height`, with the figure-level title and method key drawn against its
#: edges. The row and column ids are real ones from the axis config, because the
#: labelling layer resolves every one of them and raises on an id it does not know.
_PRODUCTION_ROWS = 12
_PRODUCTION_COLUMNS = 5


def _production_grid() -> tuple[list[str], list[str], list[str]]:
    """A ``(models, methods, attributes)`` triple the size of the live sweep."""
    import yaml

    from population_synthetic.analysis.utils.axes import strategy_complexity_order
    from population_synthetic.analysis.utils.labels import (
        ATTRIBUTE_LABELS_PATH,
        discover_model_ids,
        discover_strategy_ids,
    )

    models = discover_model_ids()[:_PRODUCTION_ROWS]
    methods = strategy_complexity_order(discover_strategy_ids())[:_PRODUCTION_COLUMNS]
    attributes = sorted(yaml.safe_load(ATTRIBUTE_LABELS_PATH.read_text(encoding="utf-8"))["labels"])
    assert len(models) == _PRODUCTION_ROWS and len(methods) == _PRODUCTION_COLUMNS
    return models, methods, attributes


def test_radar_grid_fits_the_printable_page_at_production_scale():
    """The written canvas stays inside the printable page on a full-size grid.

    Asserted on the ``Figure`` rather than on an exported file, for the reason
    ``test_figure_compliance`` gives for the same choice: the quantity the export budget
    checks is the *tight bounding box*, which is what ``bbox_inches="tight"`` writes at
    and which this reads directly -- so the defect is caught without paying to serialise
    sixty polar panels into three formats, and a failure names the geometry rather than
    a byte count.

    Both halves matter. The tight box must fit the page, and the figure itself must still
    be the full page: this grid is tall enough that ``grow_height`` clamps it, and the
    overhang must not be resolved by shrinking a canvas the size vocabulary chose.
    """
    import matplotlib.pyplot as plt

    models, methods, attributes = _production_grid()
    results = {
        (model, method): {attr: {"tv_distance": 0.1} for attr in attributes}
        for model in models
        for method in methods
    }

    measured: dict[str, tuple[float, float]] = {}

    def measure(fig, path, **kwargs):
        fig.canvas.draw()
        box = fig.get_tightbbox(fig.canvas.get_renderer())
        measured["figure_in"] = tuple(float(v) for v in fig.get_size_inches())
        measured["written_in"] = (float(box.width), float(box.height))
        plt.close(fig)
        return path

    original = charts.save_figure
    charts.save_figure = measure
    try:
        charts.plot_radar_grid(results, Path("."), prefix="swedish_02", attributes=attributes)
    finally:
        charts.save_figure = original

    written_width, written_height = measured["written_in"]
    assert written_width <= MAX_WIDTH and written_height <= MAX_HEIGHT
    assert measured["figure_in"] == pytest.approx((MAX_WIDTH, MAX_HEIGHT))


# --- the per-combination family: the printable-page budget at production scale -

#: A slug from the live Swedish sweep, and the label of the mapped real population it is
#: scored against. Both reach the canvas verbatim -- the bar charts print the pair in the
#: axes title and in the legend, and every report figure prefixes its title with the slug
#: -- so the length of a real run slug is part of the geometry under test. The tiny
#: ``_PREFIX`` above is not: it is short enough that no title on this family ever reaches
#: a page edge, which is exactly why the smoke tests above never saw the defect.
_PRODUCTION_SLUG = "swedish_02_all_generate_evaluate_pick_v2_claude_haiku"
_PRODUCTION_REAL_LABEL = "real_swedish_02"


def _production_scheme():
    """The live Swedish comparison axis: every analysed attribute and its categories.

    Read through the same loader the drivers use, so the axis under test is the config's
    and not a list restated here -- the fixtures elsewhere in this module carry three
    attributes, and the widest bar charts in the family are the ones the full axis has.
    """
    from population_synthetic.analysis.fidelity.scheme import load_scheme
    from population_synthetic.analysis.utils.country_config import mappings_for_country

    return load_scheme("swedish_02", mappings_path=mappings_for_country("swedish_02"))


def _population(scheme, *, n: int = 40) -> dict:
    """A population occupying every category of every attribute on *scheme*.

    Every category has to be occupied, because an attribute's chart is drawn over the
    categories the scheme declares and the axis is at its production width only when none
    of them is empty in both populations.
    """
    individuals = []
    for i in range(n):
        individual: dict = {"age": 18 + (i % 60)}
        for attr, categories in scheme.categories.items():
            if attr == "age_group":
                continue
            individual[attr] = categories[i % len(categories)]
        individuals.append(individual)
    return {"individuals": individuals, "metadata": {"n": len(individuals)}}


def _capture_figures(call) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    """Run *call*, returning ``(name, figure_inches, written_inches)`` per saved figure.

    Measures the **tight** bounding box, which is the quantity the export budget checks
    and the one ``bbox_inches="tight"`` writes at, for the reason
    ``test_radar_grid_fits_the_printable_page_at_production_scale`` gives: the geometry is
    the defect, and reading it off the figure names it without serialising three formats.
    """
    import matplotlib.pyplot as plt

    measured: list[tuple[str, tuple[float, float], tuple[float, float]]] = []

    def measure(fig, path, **kwargs):
        fig.canvas.draw()
        box = fig.get_tightbbox(fig.canvas.get_renderer())
        measured.append((
            Path(path).name,
            tuple(float(v) for v in fig.get_size_inches()),
            (float(box.width), float(box.height)),
        ))
        plt.close(fig)
        return path

    original = charts.save_figure
    charts.save_figure = measure
    try:
        call()
    finally:
        charts.save_figure = original
    assert measured, "the chart function did not produce a figure"
    return measured


def _fits(written: tuple[float, float]) -> bool:
    return written[0] <= MAX_WIDTH and written[1] <= MAX_HEIGHT


def test_comparison_charts_fit_the_printable_page_at_production_scale():
    """Every per-attribute bar chart stays inside the page with real labels on it.

    This family is drawn at the printable width **exactly**, so it has no headroom at
    all: the axes title is centred on the axes rather than on the paper, and with two run
    slugs interpolated into it it reached past the page edge, where the exporter's tight
    box grew to contain it. Both halves are asserted -- the written box fits, and the
    canvas is still the full page, because the overhang has to be re-flowed and never
    resolved by shrinking a figure the size vocabulary sized.
    """
    scheme = _production_scheme()
    population = _population(scheme)

    measured = _capture_figures(lambda: charts.plot_comparison_charts(
        population, population, Path("unused"),
        pop_a_label=_PRODUCTION_REAL_LABEL, pop_b_label=_PRODUCTION_SLUG,
        prefix=_PRODUCTION_SLUG, attributes=scheme.attributes, categories=scheme.categories,
    ))

    assert len(measured) == len(scheme.attributes)
    over = [name for name, _figure, written in measured if not _fits(written)]
    assert not over, f"written past the printable page: {over}"
    for name, figure_in, _written in measured:
        assert figure_in[0] == pytest.approx(MAX_WIDTH), f"{name}: the canvas was shrunk"


def _report_figure_calls(scheme):
    """The report figures whose title carries the run slug, as ``(name, call)`` builders.

    The association heatmap and the two legacy figures join the three multivariate ones
    because they share the property under test: a title prefixed with a run slug, on a
    canvas the size vocabulary has already clamped to the page.
    """
    report = make_report(
        {attr: 0.1 for attr in scheme.attributes[:3]},
        multivariate=make_multivariate(
            joint_fidelity_pairs=_JF_PAIRS, combination_checks=_CHECKS,
        ),
        joint_chi_sq={"age_group_x_education_level": 0.3, "age_group_x_biological_sex": 0.01},
    )
    report["multivariate"]["association"] = {
        "pairs": [
            {"attr_x": x, "attr_y": y, "abs_delta_v": 0.1}
            for i, x in enumerate(scheme.attributes)
            for y in scheme.attributes[i + 1:]
        ]
    }
    return [
        ("association_heatmap", lambda: charts.plot_association_heatmap(
            report, Path("unused"), prefix=_PRODUCTION_SLUG, attributes=scheme.attributes)),
        ("c2st", lambda: charts.plot_c2st(report, Path("unused"), prefix=_PRODUCTION_SLUG)),
        ("joint_fidelity", lambda: charts.plot_joint_fidelity(
            report, Path("unused"), prefix=_PRODUCTION_SLUG, attributes=scheme.attributes)),
        ("combination_plausibility", lambda: charts.plot_combination_plausibility(
            report, Path("unused"), prefix=_PRODUCTION_SLUG)),
        ("joint_chi_sq", lambda: charts.plot_joint_chi_sq(
            report, Path("unused"), prefix=_PRODUCTION_SLUG)),
        ("coherence", lambda: charts.plot_coherence(
            report, Path("unused"), prefix=_PRODUCTION_SLUG)),
    ]


@pytest.mark.parametrize("index", range(6))
def test_report_figures_fit_the_printable_page_with_a_run_slug_in_the_title(index):
    """A slug-prefixed title is re-flowed onto the page, not resolved by resizing.

    The canvas half is asserted against the *same figure drawn with the fit disabled*
    rather than against a literal, because these six size themselves differently -- one
    grows with the pair count, one with the attribute count, one is a fixed small panel.
    What has to hold for all of them is that fitting the title changed the layout inside
    the canvas and left the canvas itself alone.
    """
    scheme = _production_scheme()
    name, call = _report_figure_calls(scheme)[index]

    real_fit_to_page = charts.fit_to_page
    charts.fit_to_page = lambda fig: None
    try:
        unfitted = _capture_figures(call)
    finally:
        charts.fit_to_page = real_fit_to_page
    fitted = _capture_figures(call)

    assert _fits(fitted[0][2]), f"{name}: written {fitted[0][2]} past the printable page"
    assert fitted[0][1] == pytest.approx(unfitted[0][1]), f"{name}: the canvas was shrunk"


def test_3way_radar_fits_the_printable_page_at_production_scale():
    """The three-way radar keeps its spoke labels and its legend inside the page.

    Drawn at both caps at once, so -- like the two-way radar it mirrors -- its polar box
    has to stop short of the paper: a polar axes fills its subplot box, the spoke labels
    are drawn outside the frame, and the legend sits below it.
    """
    scheme = _production_scheme()
    pairwise = {
        f"{a}_vs_{b}": {attr: {"tv_distance": 0.1} for attr in scheme.attributes}
        for a, b in (("real", "x"), ("real", "y"), ("x", "y"))
    }

    measured = _capture_figures(lambda: charts.plot_3way_radar(
        pairwise, (_PRODUCTION_REAL_LABEL, _PRODUCTION_SLUG, _PRODUCTION_SLUG),
        Path("unused"), attributes=scheme.attributes, prefix="swedish_02",
    ))

    name, figure_in, written = measured[0]
    assert _fits(written), f"{name}: written {written} past the printable page"
    assert figure_in == pytest.approx((MAX_WIDTH, MAX_HEIGHT)), f"{name}: the canvas was shrunk"

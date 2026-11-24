"""Camera-ready compliance, asserted over figures the layer actually draws.

The plan this layer was built for defines a *camera-ready* figure as one whose every
text element is the house font at 8-12 pt, whose strokes exceed 0.25 pt, whose colours
are RGB, whose canvas is within the printable page, and **none of whose displayed
strings contains an underscore or an API-provider token** -- and it says explicitly that
this is "testable by inspecting the figure object before export, not by eye".

That is what this module does, and it is the reason it exists beside the per-process
chart tests rather than inside them. Those tests each assert what one figure *shows*.
This one asserts the property that has to hold across all of them at once, and that no
single chart module is in a position to check: that no id, no provider prefix and no
sub-floor type reached the canvas anywhere. A rule enforced in fifteen places is a rule
that holds in fourteen.

**Why the assertion is on the ``Figure`` and not on the written file.** Two reasons.
Inspecting the figure catches the defect on every figure, including the ones a size
budget currently rejects at export -- which are exactly the figures a
file-based check would silently skip. And it names the offending artist, where a file
check could only say that some pixel somewhere was wrong.

The three-format guarantee is the one property that genuinely lives in the file system,
so it is asserted there, on a figure small enough to be about the writer rather than
about any chart's layout.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pytest  # noqa: E402

from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES, save_figure  # noqa: E402
from population_synthetic.analysis.utils.style import (  # noqa: E402
    FONT_CEILING_PT,
    FONT_FLOOR_PT,
    apply_house_style,
)

# --------------------------------------------------------------------------- #
# what "camera-ready" forbids                                                   #
# --------------------------------------------------------------------------- #

#: Tokens naming a *serving layer* rather than a model. The labelling convention drops
#: them from every axis -- LMArena, the Kimi K2 report and the HuggingFace leaderboard
#: all name the model's creator, not who is hosting it -- and keeps them in the
#: generated provenance table instead. Lower-cased before matching, so a display label
#: that legitimately contains "Ollama" as a proper noun would still be caught; none
#: does, and if one ever should, this is where the exception gets argued for.
PROVIDER_TOKENS = ("openrouter", "ollama", "claude_")

#: Characters no *labelling* string may contain. The underscore is a code-identifier
#: convention that no journal guideline sanctions, and on a tick, an axis label, a legend
#: entry or a title there is nothing it could be but an id.
FORBIDDEN_CHARACTERS = ("_",)


def axis_vocabulary() -> frozenset[str]:
    """Every model, strategy and country id the axis config declares.

    Read from config rather than listed here, so a new arm is policed the day it is added
    and this test can never drift from the vocabulary it exists to keep off the canvas.
    """
    from population_synthetic.analysis.utils.labels import (
        COUNTRIES_DIR,
        STRATEGIES_DIR,
        discover_model_ids,
    )

    ids = set(discover_model_ids())
    for directory in (STRATEGIES_DIR, COUNTRIES_DIR):
        ids |= {
            path.stem for path in directory.glob("*.yaml") if not path.stem.startswith("_")
        }
    return frozenset(ids)


def _tokens(text: str) -> set[str]:
    """The identifier-shaped runs in *text*, which is the shape an id would arrive in."""
    import re

    return set(re.findall(r"[A-Za-z0-9_]+", text))


#: Text that is drawn but is not *displayed* -- matplotlib fills the offsetText and the
#: axis label of every axes whether or not anything uses them, and an empty or
#: whitespace-only string shows nothing. Matched exactly, never stripped-and-guessed.
_EMPTY = ("", " ")


def _displayed_texts(fig):
    """Every ``Text`` artist on *fig* that a reader would actually see.

    Walks the whole artist tree rather than the handful of accessors a chart module
    happens to use, because the leak this guards against is precisely the string nobody
    remembered was drawn: a legend entry, a colourbar label, an offset text, an
    annotation inside a heatmap cell.
    """
    from matplotlib.text import Text

    for artist in fig.findobj(Text):
        if not artist.get_visible():
            continue
        text = artist.get_text()
        if text in _EMPTY or not text.strip():
            continue
        yield artist, text


def _labelling_texts(fig):
    """The subset that *names* something: ticks, axis labels, titles, legend entries.

    Separated from the rest because the two carry different rules. A tick or a legend
    entry has no business containing an underscore at all -- there is nothing it could be
    but an id. A caption is prose, and this layer's captions deliberately cite the CSV
    column a number was read from ("the document's retention_rate"), which is the join
    from the figure back to the data and is worth more than the character it costs.
    Caption text is held to the narrower, stricter rule instead: no *id*, ever, matched
    against the vocabulary the axis config actually declares.
    """
    from matplotlib.legend import Legend

    for axes in fig.axes:
        yield from axes.get_xticklabels()
        yield from axes.get_yticklabels()
        yield axes.xaxis.label
        yield axes.yaxis.label
        yield axes.title
    for artist in fig.findobj(Legend):
        yield from artist.get_texts()
        title = artist.get_title()
        if title is not None:
            yield title


def assert_camera_ready(fig, label: str) -> None:
    """Raise unless every displayed string and size on *fig* satisfies the definition.

    Collects **all** violations before failing rather than stopping at the first: a
    figure that leaks one id usually leaks a family of them, and a test that reports
    them one render at a time turns a five-minute fix into an afternoon.
    """
    vocabulary = axis_vocabulary()
    labelling = {id(artist) for artist in _labelling_texts(fig)}
    violations: list[str] = []
    for artist, text in _displayed_texts(fig):
        flat = text.replace("\n", " ")
        if id(artist) in labelling:
            for character in FORBIDDEN_CHARACTERS:
                if character in text:
                    violations.append(f"{label}: {character!r} in the label {flat!r}")
        leaked = sorted(_tokens(text) & vocabulary)
        if leaked:
            violations.append(f"{label}: config id(s) {leaked} printed in {flat!r}")
        lowered = text.lower()
        for token in PROVIDER_TOKENS:
            if token in lowered:
                violations.append(f"{label}: provider token {token!r} in {flat!r}")
        size = artist.get_fontsize()
        if size < FONT_FLOOR_PT:
            violations.append(
                f"{label}: {size} pt is below the {FONT_FLOOR_PT} pt floor, on {flat!r}"
            )
        if size > FONT_CEILING_PT:
            violations.append(
                f"{label}: {size} pt is above the {FONT_CEILING_PT} pt ceiling, on {flat!r}"
            )
    assert not violations, "\n".join(violations)


# --------------------------------------------------------------------------- #
# the figures under test                                                        #
# --------------------------------------------------------------------------- #

def _capture(module, call):
    """Run *call* and return the ``Figure`` it handed to ``save_figure``.

    Several chart entry points save internally and return a path. Intercepting the
    writer is what lets this module inspect those figures too -- including the ones the
    writer currently rejects on a size budget, which are the figures a
    file-based check would quietly never see.
    """
    captured: list = []
    original = module.save_figure

    def spy(fig, path, **kwargs):
        captured.append(fig)
        return path

    module.save_figure = spy
    try:
        call()
    finally:
        module.save_figure = original
    assert captured, "the chart function did not produce a figure"
    return captured[-1]


def _validity_grids():
    from population_synthetic.analysis.validation_attrition.charts import (
        GRID_VARIANTS,
        plot_attrition_funnel,
        plot_mapped_validity_grid,
    )
    from tests.test_validation_attrition_charts import _COMPLEX, _SIMPLE, _document, _entry

    document = _document([
        _entry("claude_haiku", _SIMPLE, clean=120),
        _entry("claude_haiku", _COMPLEX, clean=9, selected=0, excluded=True),
        _entry("openrouter_kimi_k3", _SIMPLE, clean=118),
        _entry("openrouter_kimi_k3", _COMPLEX, generated=0, raw_valid=0, clean=0, selected=0,
               excluded=True),
    ])
    yield "validation_attrition::plot_attrition_funnel", plot_attrition_funnel(document)
    for name, variant in GRID_VARIANTS.items():
        yield (
            f"validation_attrition::plot_mapped_validity_grid[{name}]",
            plot_mapped_validity_grid(document, variant=variant),
        )


def _model_ranking_figures():
    from pathlib import Path

    import population_synthetic.analysis.model_ranking.charts as mod
    from tests.test_model_ranking_charts import _result

    # (model, strategy, overall TV-similarity, n). Two real models on two real methods,
    # so the rows carry a combination label and the columns a method letter -- the two
    # places an id used to reach the canvas.
    result = _result([
        ("claude_haiku", "all_pick_v2", 0.90, 100),
        ("claude_haiku", "all_generate_pick_v2", 0.80, 100),
        ("openrouter_kimi_k3", "all_pick_v2", 0.85, 100),
        ("openrouter_kimi_k3", "all_generate_pick_v2", 0.95, 100),
    ])
    for fn_name in ("plot_performance_heatmap", "plot_performance_leaderboard"):
        fn = getattr(mod, fn_name)
        yield (
            f"model_ranking::{fn_name}",
            _capture(mod, lambda f=fn: f(result, Path("unused.png"))),
        )


def _generation_metadata_figures():
    """The cross-factor comparison family: two model x method grids and eight panels.

    The object these charts draw is rebuilt from the raw telemetry on every run and is
    never persisted, so it is assembled here from the same ``ComboSummary`` fixture the
    comparison unit tests use -- with **real** axis ids, which is the whole point: this
    family carries the layer's densest model and method axes.
    """
    from pathlib import Path

    import population_synthetic.analysis.generation_metadata.charts as mod
    from population_synthetic.analysis.generation_metadata.comparison import (
        build_summary_comparison,
    )
    from tests.test_gm_comparison import _combo

    def samples(calls, tokens):
        return {
            "calls": [calls, calls + 1.0, calls + 2.0],
            "total_tokens": [tokens, tokens + 10.0, tokens + 20.0],
            "wall_clock_s": [calls * 2, calls * 2 + 1, calls * 2 + 2],
        }

    comparison = build_summary_comparison([
        _combo("claude_haiku", "all_pick_v2", samples(3.0, 100.0)),
        _combo("claude_haiku", "all_generate_pick_v2", samples(5.0, 200.0)),
        _combo("openrouter_kimi_k3", "all_pick_v2", samples(4.0, 150.0)),
        _combo("openrouter_kimi_k3", "all_generate_pick_v2", samples(6.0, 250.0)),
    ])

    captured: list = []
    original = mod.save_figure

    def spy(fig, path, **kwargs):
        captured.append((path, fig))
        return path

    mod.save_figure = spy
    try:
        mod.plot_run_comparison(comparison, Path("unused"))
    finally:
        mod.save_figure = original
    for path, fig in captured:
        yield f"generation_metadata::{Path(path).stem}", fig


def _realism_ranking_figures():
    """The typicality distribution grid: a point-laid-out glyph grid on real axis ids.

    The fixture holds the live twelve models and five strategies, with one cell in each
    non-histogram state, so every label, legend entry and mark the figure can print is on
    the canvas under test.
    """
    from population_synthetic.analysis.realism_ranking.charts import (
        plot_typicality_distribution_grid,
    )
    from tests.test_realism_distribution_grid import HOSTING, MODELS, STRATEGIES, _ranking

    ranking = _ranking(states={
        ("ollama_gemma4_e4b", STRATEGIES[-1]): "withdrawn",
        ("claude_haiku", STRATEGIES[0]): "unjudged",
        ("claude_sonnet", STRATEGIES[1]): "no_typicality",
    })
    yield (
        "realism_ranking::plot_typicality_distribution_grid",
        plot_typicality_distribution_grid(ranking, model_order=list(MODELS), hosting=HOSTING),
    )


def _figures():
    """Every figure this module inspects, as ``(label, Figure)``.

    Built inside the house style, because a figure drawn outside it carries matplotlib's
    default sizes and would be tested against a scale it was never drawn to.
    """
    with apply_house_style():
        for label, fig in _validity_grids():
            yield label, fig
        for label, fig in _model_ranking_figures():
            yield label, fig
        for label, fig in _generation_metadata_figures():
            yield label, fig
        for label, fig in _realism_ranking_figures():
            yield label, fig


@pytest.fixture(scope="module")
def drawn_figures():
    import matplotlib.pyplot as plt

    figures = list(_figures())
    yield figures
    for _label, fig in figures:
        plt.close(fig)


def test_the_figure_set_is_not_empty(drawn_figures):
    """A vacuous sweep passes every rule it checks; this is what stops that."""
    assert len(drawn_figures) >= 5


def test_no_displayed_string_carries_an_id_or_a_provider(drawn_figures):
    """The plan's criterion: no underscore, no serving-layer token, anywhere on a canvas."""
    for label, fig in drawn_figures:
        assert_camera_ready(fig, label)


def test_the_compliance_check_catches_what_it_claims_to():
    """The guard on the guard: a deliberately non-compliant figure must fail it.

    Without this the suite could not tell "every figure is compliant" from "the walk
    finds no text at all", which is the failure mode a tree-walking assertion has.
    """
    import matplotlib.pyplot as plt

    with apply_house_style():
        fig, ax = plt.subplots()
        ax.set_title("openrouter_kimi_k3", fontsize=FONT_FLOOR_PT - 1.0)
    with pytest.raises(AssertionError) as excinfo:
        assert_camera_ready(fig, "deliberate")
    message = str(excinfo.value)
    assert "'_'" in message
    assert "openrouter_kimi_k3" in message
    assert f"below the {FONT_FLOOR_PT} pt floor" in message
    plt.close(fig)


#: The presentation layer: the modules every ``charts.py`` draws through. Named here, not
#: discovered, because membership is a claim about what a module *may* do -- receive finished
#: numbers and draw them -- and the test below checks the half of that claim a syntax tree
#: can check. Eight modules since ``glyph_grid`` joined for the point-laid-out glyph grids.
PRESENTATION_MODULES = (
    "palette",
    "style",
    "labels",
    "figures",
    "grids",
    "grid_annotations",
    "table_style",
    "glyph_grid",
)


def _imported_modules(path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            if node.module == "population_synthetic.analysis":
                names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("module", PRESENTATION_MODULES)
def test_a_presentation_module_imports_no_analysis_subpackage(module):
    """The membership test for the layer: nothing from any analysis subpackage.

    ``analysis/utils`` is shared infrastructure, not a process, so an import from it is
    allowed; an import from ``analysis/<process>/`` would let a statistic or a process's
    vocabulary leak behind the boundary.
    """
    from pathlib import Path

    import population_synthetic.analysis.utils as utils

    path = Path(utils.__file__).resolve().parent / f"{module}.py"
    assert path.exists(), f"presentation module {module} is missing"
    prefix = "population_synthetic.analysis."
    offenders = sorted(
        name for name in _imported_modules(path)
        if name.startswith(prefix) and name[len(prefix):].split(".")[0] != "utils"
    )
    assert offenders == [], f"{module} imports {offenders}"


def test_the_presentation_layer_has_eight_modules():
    assert len(set(PRESENTATION_MODULES)) == 8


def test_every_written_figure_appears_in_all_three_formats(tmp_path):
    """PNG to read a draft in, SVG to edit for the deck, EPS to submit.

    Asserted against ``OUTPUT_SUFFIXES`` rather than a literal list, so adding a format
    to the writer cannot leave this test asserting the old set.
    """
    import matplotlib.pyplot as plt

    with apply_house_style():
        fig, ax = plt.subplots(figsize=(3.0, 2.0))
        ax.plot([0, 1], [0, 1])
        written = save_figure(fig, tmp_path / "figure.png")

    assert written.suffix == ".png"
    for suffix in OUTPUT_SUFFIXES:
        sibling = written.with_suffix(suffix)
        assert sibling.exists(), f"{suffix} was not written"
        assert sibling.stat().st_size > 0, f"{suffix} is empty"
    plt.close(fig)

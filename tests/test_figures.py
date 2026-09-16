"""Tests for the figure export layer.

Compliance tests, like ``test_style.py`` and for the same reason.
``figure-preparation-standards.docx`` states what a submitted figure must be -- vector
EPS with the font embedded, RGB, a canvas of at most 19.05 x 22.23 cm and a file of at
most 10 MB -- and :mod:`population_synthetic.analysis.utils.figures` is the one place
those are enforced. A suite that only checked "three files appeared" would let every
one of the constraints drift while staying green, so each test below asserts a
constraint on the *written bytes*.

Two of them are drift guards over the source tree rather than over an artifact: that
no chart module writes a figure behind the export helper's back, and that no driver
restates a raster resolution the helper already owns. Both are properties the export
policy cannot enforce from inside itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from population_synthetic.analysis.utils import figures, style  # noqa: E402

SRC_ROOT = Path(figures.__file__).resolve().parents[3]
ANALYSIS_ROOT = Path(figures.__file__).resolve().parents[1]
SCRIPTS_ROOT = SRC_ROOT.parent / "scripts" / "analyze"

#: The first bytes of each format, so "it is a PNG" is asserted on content and not on
#: the suffix the helper itself chose.
MAGIC = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".svg": b"<?xml",
    ".eps": b"%!PS-Adobe-3.0 EPSF-3.0",
}

#: The five analysis drivers carrying a ``--dpi`` flag.
DPI_DRIVERS = (
    "analyze_cost_efficiency.py",
    "analyze_persona_realism.py",
    "analyze_real_population_stats.py",
    "analyze_validation_attrition.py",
    "rank_persona_realism.py",
)


def _figure(width_in: float, height_in: float):
    """A minimal drawn figure of an exact nominal size, in the house style."""
    with style.apply_house_style():
        fig, ax = plt.subplots(figsize=(width_in, height_in))
        ax.bar([0, 1, 2], [1.0, 2.0, 1.5])
        ax.set_title("Export test")
    return fig


def _canvas_cm(eps_path: Path) -> tuple[float, float]:
    """The written canvas of an EPS on disk, in centimetres."""
    width_in, height_in = figures._canvas_inches(eps_path.read_bytes())
    return (width_in * style.CM_PER_INCH, height_in * style.CM_PER_INCH)


@pytest.fixture(autouse=True)
def _no_leaked_figures():
    """Every test starts and ends with no open figures, so closure is observable."""
    plt.close("all")
    yield
    plt.close("all")


# ------------------------------------------------------------------
# Every required format, on every save
# ------------------------------------------------------------------

def test_save_figure_writes_the_png_svg_and_eps_trio(tmp_path):
    """One save produces all three formats, sharing one stem and directory.

    EPS is the format all four target venues accept; the SVG is the editable sibling
    and the PNG the readable one. A save emitting fewer than three is the half-vector
    state this module was written to end.
    """
    png_path = figures.save_figure(_figure(4.0, 3.0), tmp_path / "chart.png", dpi=100)

    assert png_path == tmp_path / "chart.png"
    for suffix, magic in MAGIC.items():
        sibling = png_path.with_suffix(suffix)
        assert sibling.exists(), f"{suffix} was not written"
        assert sibling.read_bytes().startswith(magic), f"{sibling.name} is not a {suffix}"


def test_the_written_trio_is_within_both_budgets(tmp_path):
    """Each written file satisfies the canvas budget and the file-size ceiling."""
    png_path = figures.save_figure(_figure(style.DOUBLE, 4.0), tmp_path / "chart.png", dpi=100)

    width_cm, height_cm = _canvas_cm(png_path.with_suffix(".eps"))
    assert width_cm <= style.MAX_WIDTH * style.CM_PER_INCH
    assert height_cm <= style.MAX_HEIGHT * style.CM_PER_INCH
    for suffix in MAGIC:
        written = png_path.with_suffix(suffix).stat().st_size
        assert written <= figures.MAX_FILE_BYTES, f"{suffix} is {written} bytes"


def test_the_figure_is_closed_after_a_successful_save(tmp_path):
    """The helper owns the figure lifecycle; a caller never has to close."""
    figures.save_figure(_figure(4.0, 3.0), tmp_path / "chart.png", dpi=100)
    assert plt.get_fignums() == []


# ------------------------------------------------------------------
# Vector text is embedded, not requested from the reader's machine
# ------------------------------------------------------------------

def test_the_eps_embeds_the_house_font_even_when_saved_outside_the_style(tmp_path):
    """A figure saved outside ``apply_house_style`` still embeds a TrueType face.

    This is the driver path: several chart modules return an unsaved ``Figure`` and
    their driver writes it, so the ambient ``rcParams`` at write time are matplotlib's
    defaults -- under which ``ps.fonttype`` is 3 and the face is *not* embedded. The
    export helper therefore installs the save-time subset itself.
    """
    with style.apply_house_style():
        fig, ax = plt.subplots(figsize=(4.0, 3.0))
        ax.set_title("Embedding")

    # matplotlib's own default, pinned so the test states the condition it guards
    # against rather than trusting whatever this host's matplotlibrc happens to say.
    with plt.rc_context({"ps.fonttype": 3}):
        eps = figures.save_figure(fig, tmp_path / "chart.png", dpi=100).with_suffix(".eps")
    text = eps.read_bytes()
    assert b"/FontType 42 def" in text, "vector text was not written as embedded TrueType"
    assert b"/sfnts" in text, "the font program itself was not embedded"


def test_the_svg_keeps_its_text_as_text_even_when_saved_outside_the_style(tmp_path):
    """The SVG carries real ``<text>`` nodes, not glyph outlines.

    The SVG is the format a figure is *edited* in, and matplotlib's default
    ``svg.fonttype = 'path'`` converts every glyph to a shape -- which turned a
    heatmap's labels into ~1700 anonymous paths an illustration tool cannot retype.
    Guarded on the driver path (saved outside ``apply_house_style``) and against the
    pinned default, for the same reason as the EPS test above.
    """
    with style.apply_house_style():
        fig, ax = plt.subplots(figsize=(4.0, 3.0))
        ax.set_title("Retypeable")

    with plt.rc_context({"svg.fonttype": "path"}):
        svg = figures.save_figure(fig, tmp_path / "chart.png", dpi=100).with_suffix(".svg")
    markup = svg.read_text(encoding="utf-8")
    assert "<text" in markup, "the SVG carries no text node; its glyphs were written as outlines"
    assert "Retypeable" in markup, "the title is not present as editable text"
    assert f"font-family: '{style.house_font()}'" in markup, "the text node names no font family"


# ------------------------------------------------------------------
# The budgets are enforced, and enforcement writes nothing
# ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("width_in", "height_in", "expected"),
    [
        (style.MAX_WIDTH + 4.0, 3.0, "width"),
        (4.0, style.MAX_HEIGHT + 4.0, "height"),
    ],
)
def test_a_canvas_over_the_printable_area_raises(tmp_path, width_in, height_in, expected):
    """An oversized canvas fails the run rather than being silently shrunk.

    Clamping would publish a figure other than the one that was drawn -- text
    below the 8 pt floor, or a grid with its outer column cropped -- while every
    caller still believed it had emitted a compliant figure.
    """
    with pytest.raises(figures.FigureBudgetExceeded) as excinfo:
        figures.save_figure(_figure(width_in, height_in), tmp_path / "wide.png", dpi=100)

    assert expected in str(excinfo.value)
    assert list(tmp_path.iterdir()) == [], "a rejected figure must leave nothing on disk"


def test_a_file_over_the_size_ceiling_raises(tmp_path, monkeypatch):
    """The 10 MB ceiling is enforced on the rendered bytes, before anything is written."""
    monkeypatch.setattr(figures, "MAX_FILE_BYTES", 1024)

    with pytest.raises(figures.FigureBudgetExceeded) as excinfo:
        figures.save_figure(_figure(4.0, 3.0), tmp_path / "chart.png", dpi=100)

    assert "ceiling" in str(excinfo.value)
    assert list(tmp_path.iterdir()) == [], "a rejected figure must leave nothing on disk"


def test_the_figure_is_closed_even_when_a_budget_is_broken(tmp_path):
    """A rejected save still releases the figure; a failing run must not leak memory."""
    with pytest.raises(figures.FigureBudgetExceeded):
        figures.save_figure(
            _figure(style.MAX_WIDTH + 4.0, 3.0), tmp_path / "wide.png", dpi=100
        )
    assert plt.get_fignums() == []


def test_an_eps_without_a_bounding_box_cannot_pass_unmeasured():
    """An unmeasurable EPS raises rather than skipping the canvas check."""
    with pytest.raises(figures.EPSBoundingBoxMissing):
        figures._canvas_inches(b"%!PS-Adobe-3.0 EPSF-3.0\n%%EndComments\n")


# ------------------------------------------------------------------
# Drift guards over the source tree
# ------------------------------------------------------------------

def test_only_the_export_helper_writes_a_figure():
    """No module in ``src/`` may call ``savefig`` behind the export helper's back.

    A second write path is how half the layer came to emit PNG only: the format set,
    the tight bbox and both budgets live in one function precisely so that a chart
    module cannot opt out of them.
    """
    offenders = [
        path.relative_to(SRC_ROOT)
        for path in (p.resolve() for p in SRC_ROOT.rglob("*.py"))
        if path != Path(figures.__file__).resolve()
        and ".savefig(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"figures are written outside the export helper: {offenders}"


def test_no_driver_restates_a_raster_resolution():
    """The ``--dpi`` flags default to :data:`figures.RASTER_DPI`, never to a literal.

    Three regimes (150, 180 and 200) preceded this constant, under which the same
    figure family exported at a different resolution depending on which process drew
    it. A numeric default here would re-open that split.
    """
    pattern = re.compile(r'"--dpi".*?default=(?P<default>[^,)]+)', re.DOTALL)
    for name in DPI_DRIVERS:
        source = (SCRIPTS_ROOT / name).read_text(encoding="utf-8")
        match = pattern.search(source)
        assert match is not None, f"{name} no longer declares a --dpi flag"
        assert match.group("default").strip() == "RASTER_DPI", (
            f"{name} restates a raster resolution instead of reading figures.RASTER_DPI"
        )


def test_the_analysis_layer_names_no_resolution_of_its_own():
    """No chart module carries a ``dpi=<number>`` literal.

    The resolution is an export decision, and export has one home. A module-private
    ``_DPI`` was how the previous split survived a first round of consolidation.
    """
    literal = re.compile(r"dpi\s*=\s*\d")
    offenders = [
        path.relative_to(ANALYSIS_ROOT)
        for path in ANALYSIS_ROOT.rglob("*.py")
        if literal.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"a raster resolution is named outside figures.py: {offenders}"

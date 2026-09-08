"""Tests for the shared heatmap draw loop and its annotation policies.

Two properties are pinned here, and they are the two the presentation boundary exists
for.

**Substitutability.** Two annotation policies over one input must produce the same
figure in everything except the cell text: the same dimensions, the same extent, the same
colour scale, the same painted array. That is what makes "publish this grid clean" a
change of policy rather than a second renderer, and it is asserted both on
:func:`render_grid` directly and on the two published variants of the validation-survival
grid, because the guarantee is worthless if the caller re-derives its limits per variant.

**Fail-fast on a contract mismatch.** ADR ``2026-08-12-self-contained-typicality-axis.md``
records a renderer that read a cell value by literal key, was handed a differently shaped
block, and painted every cell grey and labelled it unavailable *without raising* -- "a
silent-wrong-output path that produces a plausible figure". Each policy therefore declares
the keys it reads and the renderer validates every record against that declaration. The
assertion has to be that a mismatch **raises**, since the failure mode being guarded
against is precisely one that produced a figure instead of an exception.
"""

from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")  # noqa: E402 -- before any package import that may touch pyplot

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from population_synthetic.analysis.utils.grid_annotations import (  # noqa: E402
    CellAnnotationPolicy,
    MissingCellValue,
    NoAnnotationPolicy,
    RateOnlyPolicy,
    RateWithCountsPolicy,
    SignedValuePolicy,
    SignedValueWithStarsPolicy,
)
from population_synthetic.analysis.utils.grids import (  # noqa: E402
    CELL_STROKE_WIDTH,
    CellRecordMismatch,
    GridShapeMismatch,
    render_grid,
)
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    CELL_STROKE,
    MISSING_COLOR,
    heatmap_cmap,
)
from population_synthetic.analysis.utils.style import MIN_STROKE_PT  # noqa: E402

_ALL_POLICIES = (
    RateWithCountsPolicy(),
    RateOnlyPolicy(),
    SignedValuePolicy(),
    SignedValueWithStarsPolicy(),
    SignedValueWithStarsPolicy(count_key="n"),
    NoAnnotationPolicy(),
)


def _matrix() -> np.ndarray:
    """A 2x3 grid with one unmeasured cell, so the missing branch is always exercised."""
    return np.array(
        [[0.80, 0.06, np.nan],
         [0.41, 0.99, 0.13]],
        dtype=float,
    )


def _cells() -> list[list[dict | None]]:
    """Records matching :func:`_matrix`; the unmeasured cell carries none."""
    matrix = _matrix()
    rows: list[list[dict | None]] = []
    for i in range(matrix.shape[0]):
        row: list[dict | None] = []
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            if np.isnan(value):
                row.append(None)
            else:
                row.append(
                    {"rate": float(value), "numerator": 10 + j, "denominator": 100 + i}
                )
        rows.append(row)
    return rows


def _draw(policy: CellAnnotationPolicy):
    """Render the shared fixture through *policy*; returns ``(fig, ax, im)``."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.0, 3.0))
    im = render_grid(
        ax, _matrix(), _cells(),
        policy=policy,
        cmap=heatmap_cmap(),
        norm=mcolors.Normalize(vmin=0.0, vmax=1.0),
        extent=(-0.5, 2.5, 1.5, -0.5),
    )
    return fig, ax, im


def _annotations(ax) -> dict[tuple[float, float], str]:
    return {tuple(text.get_position()): text.get_text() for text in ax.texts}


# --------------------------------------------------------------------------- #
# the policies                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("policy", _ALL_POLICIES, ids=lambda p: type(p).__name__)
def test_every_policy_declares_the_keys_it_reads(policy: CellAnnotationPolicy) -> None:
    """``required_keys`` is the renderer's validation input, so it must exist and be a set."""
    assert isinstance(policy.required_keys, frozenset)
    assert all(isinstance(key, str) for key in policy.required_keys)


def test_policies_read_only_the_keys_they_declared() -> None:
    """A record holding exactly the declared keys must be enough to produce the text."""
    assert RateWithCountsPolicy().text(
        {"rate": 0.8, "numerator": 120, "denominator": 150}
    ) == "80.0\n120/150"
    assert RateOnlyPolicy().text({"rate": 0.8}) == "80.0"
    assert SignedValuePolicy().text({"value": 0.031}) == "+0.031"
    assert SignedValuePolicy().text({"value": -0.031}) == "-0.031"
    assert NoAnnotationPolicy().text({"anything": 1}) is None


def test_counts_line_names_the_base_the_caller_declared() -> None:
    """With a numerator the value is a quotient; without one it rests on a single count."""
    quotient = RateWithCountsPolicy(numerator_key="numerator")
    rests_on = RateWithCountsPolicy(numerator_key=None, value_key="value", scale=1.0)

    assert quotient.text({"rate": 0.5, "numerator": 5, "denominator": 10}) == "50.0\n5/10"
    assert rests_on.required_keys == frozenset({"value", "denominator"})
    assert rests_on.text({"value": 1.25, "denominator": 40}) == "1.2\nn=40"


def test_a_value_less_record_raises_unless_the_wording_was_declared() -> None:
    """Silence about a supplied record would read as 'not measured', so it is an error."""
    with pytest.raises(MissingCellValue, match="absent_text"):
        RateWithCountsPolicy().text({"rate": None, "numerator": 0, "denominator": 12})

    declared = RateWithCountsPolicy(numerator_key=None, absent_text="--")
    assert declared.text({"rate": None, "denominator": 12}) == "--\nn=12"


def test_qualifier_is_read_from_the_record_never_derived() -> None:
    """A signed distance needs a second unit's value, so the chart formats it, not the policy."""
    policy = RateWithCountsPolicy(
        value_key="value", numerator_key=None, scale=1.0, number_format=".3f",
        qualifier_key="delta",
    )
    assert policy.required_keys == frozenset({"value", "denominator", "delta"})
    assert policy.text(
        {"value": 0.328, "denominator": 42, "delta": "  (-0.071)"}
    ) == "0.328  (-0.071)\nn=42"


def test_the_star_policy_declares_the_count_only_when_the_caller_asked_for_it() -> None:
    """The clean variant and its counted sibling differ by exactly one declared key."""
    clean = SignedValueWithStarsPolicy()
    counted = SignedValueWithStarsPolicy(count_key="n")

    assert clean.required_keys == frozenset({"value", "stars"})
    assert counted.required_keys == frozenset({"value", "stars", "n"})


def test_the_star_policy_always_prints_the_sign() -> None:
    """The fill is symmetric across the diagonal, so only the sign says which way it ran.

    A square of pairwise comparisons paints ``(i, j)`` and ``(j, i)`` the same colour --
    the tier is a property of the pair, not of its order. Dropping the sign would leave
    the two cells indistinguishable while the figure claims to show a direction.
    """
    policy = SignedValueWithStarsPolicy()

    assert policy.text({"value": 0.031, "stars": "***"}) == "+0.031\n***"
    assert policy.text({"value": -0.031, "stars": "ns"}) == "-0.031\nns"
    assert policy.text({"value": 0.0, "stars": "ns"}) == "+0.000\nns"


def test_the_star_policy_prints_the_count_beneath_the_symbol() -> None:
    counted = SignedValueWithStarsPolicy(count_key="n")
    assert counted.text({"value": 0.031, "stars": "**", "n": 12}) == "+0.031\n**\nn=12"


def test_an_untested_pair_is_marked_rather_than_starred() -> None:
    """"Not tested" and "tested, not significant" are different findings.

    Both cells would be handed to the same policy, and the untested one is unpainted, so
    the fill cannot separate them either. The mark on its own line -- with neither symbol
    nor count beneath it, which would each imply a test that never ran -- is the only
    thing that does.
    """
    clean = SignedValueWithStarsPolicy()
    counted = SignedValueWithStarsPolicy(count_key="n")

    assert clean.text({"value": None, "stars": None}) == "—"
    assert counted.text({"value": None, "stars": None, "n": None}) == "—"
    assert clean.text({"value": 0.004, "stars": "ns"}) == "+0.004\nns"


def test_the_star_policy_can_be_asked_to_treat_an_absent_value_as_an_error() -> None:
    """The default marks the cell; a caller with no wording for it declares ``None``."""
    with pytest.raises(MissingCellValue, match="absent_text"):
        SignedValueWithStarsPolicy(absent_text=None).text({"value": None, "stars": "ns"})


def test_a_measured_cell_missing_its_symbol_raises_rather_than_printing_none() -> None:
    """A record claiming a value while withholding what is printed beside it is broken."""
    with pytest.raises(MissingCellValue, match="'stars' = None"):
        SignedValueWithStarsPolicy().text({"value": 0.031, "stars": None})

    with pytest.raises(MissingCellValue, match="'n' = None"):
        SignedValueWithStarsPolicy(count_key="n").text(
            {"value": 0.031, "stars": "**", "n": None}
        )


# --------------------------------------------------------------------------- #
# the contract the renderer enforces                                            #
# --------------------------------------------------------------------------- #


def test_a_mismatched_cell_record_raises_rather_than_rendering_blank() -> None:
    """The ADR 2026-08-12 regression, at the renderer boundary.

    A block whose value key is ``value`` handed to a policy reading ``rate`` must fail
    loudly. Rendering it leniently paints every cell as unmeasured and produces a
    plausible, silently wrong figure -- so the assertion is on the raise, and on the
    exception naming both what was required and what the record actually carries.
    """
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    cells = [[{"value": 0.8, "denominator": 100}]]
    with pytest.raises(CellRecordMismatch) as excinfo:
        render_grid(
            ax, np.array([[0.8]]), cells,
            policy=RateWithCountsPolicy(),
            cmap=heatmap_cmap(),
            norm=mcolors.Normalize(vmin=0.0, vmax=1.0),
        )
    message = str(excinfo.value)
    assert "'rate'" in message and "'numerator'" in message
    assert "'value'" in message
    plt.close(fig)


def test_a_star_record_without_its_symbol_is_caught_at_the_renderer_boundary() -> None:
    """The declaration is enforced for the star policy too, naming policy and cell.

    A pairwise square whose builder stopped emitting the symbol would otherwise render
    with the fill intact and the text silently reduced to bare differences -- a figure
    that looks finished while having dropped the channel it was drawn for.
    """
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    cells = [[{"value": 0.03, "n": 12}]]
    with pytest.raises(CellRecordMismatch) as excinfo:
        render_grid(
            ax, np.array([[0.03]]), cells,
            policy=SignedValueWithStarsPolicy(count_key="n"),
            cmap=heatmap_cmap(),
            norm=mcolors.Normalize(vmin=0.0, vmax=1.0),
        )
    message = str(excinfo.value)
    assert "SignedValueWithStarsPolicy" in message
    assert "row 0, column 0" in message
    assert "'stars'" in message
    plt.close(fig)


def test_the_mismatch_is_caught_below_the_first_row_too() -> None:
    """Validation covers every record: a ragged block's bad cell is rarely the first."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    cells = [[{"rate": 0.8}], [{"proportion": 0.2}]]
    with pytest.raises(CellRecordMismatch, match="row 1"):
        render_grid(
            ax, np.array([[0.8], [0.2]]), cells,
            policy=RateOnlyPolicy(), cmap=heatmap_cmap(),
        )
    plt.close(fig)


def test_cells_must_describe_the_same_grid_as_the_matrix() -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    with pytest.raises(GridShapeMismatch):
        render_grid(
            ax, np.array([[0.1, 0.2]]), [[{"rate": 0.1}]],
            policy=RateOnlyPolicy(), cmap=heatmap_cmap(),
        )
    plt.close(fig)


def test_a_cell_without_a_record_is_drawn_but_not_annotated() -> None:
    """No record means the renderer has nothing to say -- not that nothing was measured."""
    import matplotlib.pyplot as plt

    fig, ax, im = _draw(RateOnlyPolicy())
    array = im.get_array()

    assert np.ma.getmaskarray(array)[0, 2], "the NaN cell should take the set_bad fill"
    assert (2.0, 0.0) not in _annotations(ax)
    assert len(ax.texts) == 5
    plt.close(fig)


# --------------------------------------------------------------------------- #
# substitutability                                                              #
# --------------------------------------------------------------------------- #


def test_two_policies_differ_in_cell_text_and_in_nothing_else() -> None:
    """The property the clean figure variant rests on, asserted on the renderer itself."""
    import matplotlib.pyplot as plt

    annotated_fig, annotated_ax, annotated_im = _draw(RateWithCountsPolicy())
    clean_fig, clean_ax, clean_im = _draw(RateOnlyPolicy())

    # Same painted array, mask included.
    np.testing.assert_array_equal(
        np.ma.getmaskarray(annotated_im.get_array()),
        np.ma.getmaskarray(clean_im.get_array()),
    )
    np.testing.assert_allclose(
        annotated_im.get_array().filled(np.nan),
        clean_im.get_array().filled(np.nan),
    )
    # Same colour scale and same extent.
    assert (annotated_im.norm.vmin, annotated_im.norm.vmax) == (
        clean_im.norm.vmin, clean_im.norm.vmax,
    )
    assert annotated_im.get_extent() == clean_im.get_extent()
    assert annotated_im.cmap.name == clean_im.cmap.name
    assert annotated_fig.get_size_inches().tolist() == clean_fig.get_size_inches().tolist()

    # Same cells annotated, at the same positions and in the same colours ...
    annotated = _annotations(annotated_ax)
    clean = _annotations(clean_ax)
    assert set(annotated) == set(clean)
    assert [t.get_color() for t in annotated_ax.texts] == [
        t.get_color() for t in clean_ax.texts
    ]
    # ... and the text is the only difference: the clean variant is the annotated one
    # with its second line dropped.
    for position, text in annotated.items():
        assert text.splitlines()[0] == clean[position]
        assert "\n" in text and "\n" not in clean[position]

    plt.close(annotated_fig)
    plt.close(clean_fig)


def _stroke_segments(ax) -> list:
    """Every line segment the separators drew, in data coordinates."""
    import matplotlib.colors as mcolors

    stroke_rgba = mcolors.to_rgba(CELL_STROKE)
    segments = []
    for collection in ax.collections:
        colors = collection.get_colors()
        if len(colors) and tuple(colors[0]) == stroke_rgba:
            segments.extend(collection.get_segments())
    return segments


def test_abutting_cells_are_separated_by_a_stroke_on_every_interior_boundary() -> None:
    """Simultaneous contrast: touching tiles shift each other's apparent value.

    The 2x3 fixture has two interior column boundaries and one interior row boundary,
    and the separators are read back by their colour rather than by their index in
    ``ax.collections``, so a caller adding furniture of its own does not move them.
    """
    import matplotlib.pyplot as plt

    fig, ax, im = _draw(RateOnlyPolicy())
    left, right, bottom, top = im.get_extent()

    verticals = sorted(
        seg[0][0] for seg in _stroke_segments(ax) if seg[0][0] == seg[1][0]
    )
    horizontals = sorted(
        seg[0][1] for seg in _stroke_segments(ax) if seg[0][1] == seg[1][1]
    )
    # Interior only: two of the four column boundaries, one of the three row boundaries.
    assert verticals == pytest.approx([left + 1.0, left + 2.0])
    assert horizontals == pytest.approx([(bottom + top) / 2.0])
    plt.close(fig)


def test_the_grid_perimeter_is_left_to_the_caller() -> None:
    """A second outline under a frame or a tier divider reads as a doubled rule."""
    import matplotlib.pyplot as plt

    fig, ax, im = _draw(RateOnlyPolicy())
    left, right, bottom, top = im.get_extent()
    verticals = {seg[0][0] for seg in _stroke_segments(ax) if seg[0][0] == seg[1][0]}
    horizontals = {seg[0][1] for seg in _stroke_segments(ax) if seg[0][1] == seg[1][1]}

    assert verticals.isdisjoint({left, right})
    assert horizontals.isdisjoint({bottom, top})
    plt.close(fig)


def test_a_degenerate_grid_has_no_interior_boundary_to_separate() -> None:
    """One cell, no neighbours: nothing to contrast against, so nothing is drawn."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(2.0, 2.0))
    render_grid(
        ax, np.array([[0.5]]), [[{"rate": 0.5}]],
        policy=RateOnlyPolicy(),
        cmap=heatmap_cmap(),
        norm=mcolors.Normalize(vmin=0.0, vmax=1.0),
    )
    assert _stroke_segments(ax) == []
    plt.close(fig)


def test_the_cell_stroke_clears_the_publisher_floor() -> None:
    assert CELL_STROKE_WIDTH > MIN_STROKE_PT


def test_the_separators_sit_above_the_fill_and_below_the_annotations() -> None:
    """A stroke over the fill it divides, under every marking a caller puts on a cell."""
    import matplotlib.pyplot as plt

    fig, ax, im = _draw(RateOnlyPolicy())
    stroke_zorders = {
        collection.get_zorder()
        for collection in ax.collections
        if _stroke_segments(ax) and collection.get_segments()
    }
    assert stroke_zorders
    for zorder in stroke_zorders:
        assert im.get_zorder() < zorder
        assert all(zorder < text.get_zorder() for text in ax.texts)
    plt.close(fig)


def test_no_annotation_policy_draws_the_same_grid_with_no_text() -> None:
    import matplotlib.pyplot as plt

    fig, ax, im = _draw(NoAnnotationPolicy())
    reference_fig, _reference_ax, reference_im = _draw(RateOnlyPolicy())

    assert list(ax.texts) == []
    assert im.get_extent() == reference_im.get_extent()
    np.testing.assert_allclose(
        im.get_array().filled(np.nan), reference_im.get_array().filled(np.nan)
    )
    plt.close(fig)
    plt.close(reference_fig)


def test_annotation_colour_is_derived_from_what_the_ramp_painted() -> None:
    """White on the dark low end, black on the bright high end -- read off the mappable."""
    import matplotlib.pyplot as plt

    fig, ax, _im = _draw(RateOnlyPolicy())
    annotations = {position: text for position, text in _annotations(ax).items()}
    colors = {tuple(t.get_position()): t.get_color() for t in ax.texts}

    # 0.06 sits at the near-black end of inferno; 0.99 at the bright-yellow end.
    low = next(pos for pos, text in annotations.items() if text == "6.0")
    high = next(pos for pos, text in annotations.items() if text == "99.0")
    assert colors[low] == "white"
    assert colors[high] == "black"
    plt.close(fig)


def test_an_annotated_unpainted_cell_takes_its_colour_from_the_set_bad_grey() -> None:
    """The renderer names no grey: the missing-cell text colour comes from the cmap."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    from population_synthetic.analysis.utils.palette import text_color_for_rgb

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    render_grid(
        ax, np.array([[np.nan]]), [[{"rate": None, "denominator": 0}]],
        policy=RateWithCountsPolicy(numerator_key=None, absent_text="--"),
        cmap=heatmap_cmap(), norm=mcolors.Normalize(vmin=0.0, vmax=1.0),
    )

    assert [t.get_text() for t in ax.texts] == ["--\nn=0"]
    assert ax.texts[0].get_color() == text_color_for_rgb(mcolors.to_rgb(MISSING_COLOR))
    plt.close(fig)


def test_a_transparent_missing_colour_raises_instead_of_guessing() -> None:
    """Without a ``set_bad`` the annotation would sit on a ground this module cannot see."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    with pytest.raises(ValueError, match="transparent"):
        render_grid(
            ax, np.array([[np.nan]]), [[{"rate": None}]],
            policy=RateOnlyPolicy(absent_text="n/a"),
            cmap=plt.get_cmap("inferno").copy(),
        )
    plt.close(fig)


# --------------------------------------------------------------------------- #
# the two published variants of the validation-survival grid                     #
# --------------------------------------------------------------------------- #


def test_the_two_f05_variants_are_the_same_figure_with_different_cell_text() -> None:
    """End-to-end substitutability, on the figure the clean variant was introduced for."""
    import matplotlib.pyplot as plt

    from population_synthetic.analysis.validation_attrition.charts import (
        GRID_VARIANT_CLEAN,
        GRID_VARIANT_WITH_COUNTS,
        plot_mapped_validity_grid,
    )
    from tests.test_validation_attrition_charts import _COMPLEX, _SIMPLE, _document, _entry

    document = _document([
        _entry("claude_haiku", _SIMPLE, clean=120),
        _entry("claude_haiku", _COMPLEX, clean=9, selected=0, excluded=True),
        _entry("gemini_flash", _SIMPLE, generated=0, raw_valid=0, clean=0, selected=0,
               excluded=True),
    ])

    annotated = plot_mapped_validity_grid(document, variant=GRID_VARIANT_WITH_COUNTS)
    clean = plot_mapped_validity_grid(document, variant=GRID_VARIANT_CLEAN)
    annotated_ax, clean_ax = annotated.axes[0], clean.axes[0]
    annotated_im, clean_im = annotated_ax.get_images()[0], clean_ax.get_images()[0]

    assert annotated.get_size_inches().tolist() == clean.get_size_inches().tolist()
    assert annotated_im.get_extent() == clean_im.get_extent()
    assert (annotated_im.norm.vmin, annotated_im.norm.vmax) == (
        clean_im.norm.vmin, clean_im.norm.vmax,
    )
    np.testing.assert_allclose(
        annotated_im.get_array().filled(np.nan), clean_im.get_array().filled(np.nan)
    )
    assert annotated_ax.get_xlim() == clean_ax.get_xlim()
    assert annotated_ax.get_ylim() == clean_ax.get_ylim()
    assert [t.get_text() for t in annotated_ax.get_yticklabels()] == [
        t.get_text() for t in clean_ax.get_yticklabels()
    ]
    # The withdrawn hatch, the dotted undefined border and the best-in-column box are
    # markings, not annotations, so both variants carry all of them.
    assert len(annotated_ax.patches) == len(clean_ax.patches)

    # The measured cell prints its counts on one variant and not on the other.
    annotated_cell = _annotations(annotated_ax)[(0.0, 0.0)]
    clean_cell = _annotations(clean_ax)[(0.0, 0.0)]
    assert annotated_cell == "80.0\n120/150"
    assert clean_cell == "80.0"

    plt.close(annotated)
    plt.close(clean)


def test_the_clean_variant_prints_at_or_above_the_publisher_font_floor() -> None:
    """The reason the variant exists: 7 pt annotations were below the 8 pt floor."""
    from population_synthetic.analysis.utils.style import FONT_FLOOR_PT
    from population_synthetic.analysis.validation_attrition.charts import (
        GRID_VARIANT_CLEAN,
        GRID_VARIANT_WITH_COUNTS,
    )

    assert GRID_VARIANT_CLEAN.fontsize >= FONT_FLOOR_PT
    assert GRID_VARIANT_WITH_COUNTS.fontsize >= FONT_FLOOR_PT
    # The clean variant spends the room the dropped count line frees.
    assert GRID_VARIANT_CLEAN.fontsize > GRID_VARIANT_WITH_COUNTS.fontsize


# --------------------------------------------------------------------------- #
# the layer-wide variant rule, over every grid family that publishes variants     #
# --------------------------------------------------------------------------- #


def _assert_substitutable(counted, clean, label: str) -> None:
    """The two publications of one grid differ in cell text and in nothing else.

    Asserted on the *drawn* figures rather than on the records they were built from,
    because the property that matters is what a reader receives: two figures that can be
    swapped in a manuscript without moving a row, a column, a tick or a colour. Anything
    the caller re-derives per variant -- a norm taken over the annotated values, a canvas
    grown to fit a longer string -- would break exactly here.
    """
    assert counted.get_size_inches().tolist() == clean.get_size_inches().tolist(), label
    counted_ax, clean_ax = counted.axes[0], clean.axes[0]
    counted_images, clean_images = counted_ax.get_images(), clean_ax.get_images()
    assert len(counted_images) == len(clean_images), label
    for counted_im, clean_im in zip(counted_images, clean_images):
        assert counted_im.get_extent() == clean_im.get_extent(), label
        assert (counted_im.norm.vmin, counted_im.norm.vmax) == (
            clean_im.norm.vmin, clean_im.norm.vmax,
        ), label
        assert counted_im.cmap.name == clean_im.cmap.name, label
        np.testing.assert_allclose(
            counted_im.get_array().filled(np.nan),
            clean_im.get_array().filled(np.nan),
            err_msg=label,
        )
    assert counted_ax.get_xlim() == clean_ax.get_xlim(), label
    assert counted_ax.get_ylim() == clean_ax.get_ylim(), label
    assert [t.get_text() for t in counted_ax.get_yticklabels()] == [
        t.get_text() for t in clean_ax.get_yticklabels()
    ], label
    assert [t.get_text() for t in counted_ax.get_xticklabels()] == [
        t.get_text() for t in clean_ax.get_xticklabels()
    ], label
    # Markings -- hatches, best-cell boxes, tier rules -- qualify cells, not text, so
    # both variants carry every one of them.
    assert len(counted_ax.patches) == len(clean_ax.patches), label


#: The second form a count line takes: the two counts a printed quotient rests on.
_COUNT_QUOTIENT = re.compile(r"\d+/\d+")


def _assert_clean_drops_only_the_count_line(counted, clean, label: str) -> None:
    """Every clean cell is its counted twin with the count line removed, and nothing else.

    The point of the revision: what leaves the camera-ready figure is one line of one
    cell's text, never a qualifier, a marking or a value.
    """
    counted_texts = _annotations(counted.axes[0])
    clean_texts = _annotations(clean.axes[0])
    assert set(counted_texts) == set(clean_texts), label
    dropped = 0
    for position, text in counted_texts.items():
        # The count is the LAST line of a cell, whatever precedes it: one family prints
        # it under a bare value, another under a value and the symbol qualifying it.
        head, _, tail = text.rpartition("\n")
        if clean_texts[position] == text:
            # A cell the caller wrote rather than the policy -- "not generated", the real
            # population's own band -- reads the same on both, which is the point: only
            # the policy's own second line goes.
            continue
        assert clean_texts[position] == head, f"{label} at {position}"
        # What went is a count line and nothing else: `n=267`, or the `110/267` form the
        # validity grid uses because its value IS a quotient of two printed counts.
        assert tail.startswith("n=") or _COUNT_QUOTIENT.fullmatch(tail), (
            f"{label} at {position}: dropped {tail!r}, which is not a count line"
        )
        dropped += 1
    assert dropped, f"{label}: no counted cell to drop a line from -- vacuous fixture"


def _capture_saved(module, call):
    """Run *call* with *module*'s writer intercepted, and return the figures it produced.

    Several grid entry points save internally and return only a path. Intercepting the
    writer is what lets a substitutability assertion reach those figures -- including the
    ones the writer would reject on a size budget, which are exactly the figures a
    file-based check would never see.
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
    assert captured, "the chart function produced no figure"
    return captured


def _gm_summary(model: str, strategy: str, scale: float):
    """One ``ComboSummary`` carrying a defined mean and count for every metric.

    The metric grids read ``metrics[name]["mean"]`` and ``["n"]`` and skip a metric that
    is undefined everywhere, so a fixture with empty metrics would yield no figure at all
    and the assertions below would pass vacuously.
    """
    from population_synthetic.analysis.generation_metadata.combo_aggregator import (
        METRIC_NAMES,
        ComboSummary,
    )

    return ComboSummary(
        country="swedish",
        model=model,
        strategy=strategy,
        n_personas=100,
        has_token_data=True,
        metrics={
            name: {"mean": (index + 1) * scale, "std": 0.5, "median": (index + 1) * scale,
                   "q1": 0.0, "q3": 1.0, "n": 100}
            for index, name in enumerate(METRIC_NAMES)
        },
        skipped=[],
    )


def _variant_pairs():
    """``(label, counted_figure, clean_figure)`` for every varianted grid in the layer.

    Built from each family's own fixtures rather than from a synthetic grid, because the
    substitutability claim is about the *published* figures: a family that re-derives a
    limit from the annotated values, or grows its canvas around a longer string, fails
    here and nowhere else.
    """
    from population_synthetic.analysis.utils.style import apply_house_style

    with apply_house_style():
        # F05 -- the validation-survival grid the variant mechanism was introduced for.
        import population_synthetic.analysis.validation_attrition.charts as attrition_mod
        from tests.test_validation_attrition_charts import (
            _COMPLEX,
            _SIMPLE,
            _document,
            _entry,
        )

        document = _document([
            _entry("claude_haiku", _SIMPLE, clean=120),
            _entry("claude_haiku", _COMPLEX, clean=9, selected=0, excluded=True),
            _entry("gemini_flash", _SIMPLE, generated=0, raw_valid=0, clean=0, selected=0,
                   excluded=True),
        ])
        yield (
            "validation_attrition::plot_mapped_validity_grid",
            attrition_mod.plot_mapped_validity_grid(
                document, variant=attrition_mod.GRID_VARIANT_WITH_COUNTS,
            ),
            attrition_mod.plot_mapped_validity_grid(
                document, variant=attrition_mod.GRID_VARIANT_CLEAN,
            ),
        )

        # The manuscript's model x method fidelity grid.
        import population_synthetic.analysis.model_ranking.charts as ranking_mod
        from tests.test_model_ranking_charts import REQUESTED_N, _cap, _result

        cells = [
            ("claude_haiku", "all_pick", 0.90, REQUESTED_N),
            ("claude_haiku", "all_generate_pick", 0.80, REQUESTED_N),
            ("openrouter_kimi_k3", "all_pick", 0.85, REQUESTED_N),
            ("openrouter_kimi_k3", "all_generate_pick", 0.95, REQUESTED_N),
        ]
        result, cap = _result(cells), _cap(cells)
        drawn = {
            variant.name: _capture_saved(
                ranking_mod,
                lambda v=variant: ranking_mod.plot_model_method_heatmap(
                    result, cap, "unused.png", variant=v,
                ),
            )[-1]
            for variant in ranking_mod.GRID_VARIANTS.values()
        }
        yield (
            "model_ranking::plot_model_method_heatmap",
            drawn[ranking_mod.GRID_VARIANT_WITH_COUNTS.name],
            drawn[ranking_mod.GRID_VARIANT_CLEAN.name],
        )

        # The two realism grids: the impossibility/severity rate family and typicality.
        import population_synthetic.analysis.realism_ranking.charts as realism_mod
        from tests.test_realism_ranking_builder import _build, _record

        ranking = _build([
            _record("s1", n_impossible=2, typicalities=[5.0, 6.0, 7.0, 8.0]),
            _record("s2", n_impossible=1, typicalities=[4.0, 5.0, 9.0],
                    model="claude_sonnet"),
        ])
        yield (
            "realism_ranking::plot_impossibility_heatmap",
            realism_mod.plot_impossibility_heatmap(
                ranking, variant=realism_mod.RATE_VARIANT_WITH_COUNTS,
            ),
            realism_mod.plot_impossibility_heatmap(
                ranking, variant=realism_mod.RATE_VARIANT_CLEAN,
            ),
        )
        yield (
            "realism_ranking::plot_typicality_heatmap",
            realism_mod.plot_typicality_heatmap(
                ranking, variant=realism_mod.TYPICALITY_VARIANT_WITH_COUNTS,
            ),
            realism_mod.plot_typicality_heatmap(
                ranking, variant=realism_mod.TYPICALITY_VARIANT_CLEAN,
            ),
        )

        # The generation-cost metric grids.
        import population_synthetic.analysis.generation_metadata.charts as gm_mod

        summaries = [
            _gm_summary("claude_haiku", "all_pick", 1.0),
            _gm_summary("openrouter_kimi_k3", "all_generate_pick", 2.0),
        ]
        gm_figures = _capture_saved(
            gm_mod, lambda: gm_mod.render_metric_heatmaps("swedish", summaries, "unused"),
        )
        # One figure per metric per variant, emitted in the variant map's own order.
        names = list(gm_mod.GRID_VARIANTS)
        by_variant = {
            name: gm_figures[index::len(names)] for index, name in enumerate(names)
        }
        for index, (counted, clean) in enumerate(zip(
            by_variant[gm_mod.GRID_VARIANT_WITH_COUNTS.name],
            by_variant[gm_mod.GRID_VARIANT_CLEAN.name],
        )):
            yield f"generation_metadata::metric_heatmap[{index}]", counted, clean

        # The method x method pairwise-significance square. Built from the serialised
        # block rather than from a fitted grid: the renderer is a pure consumer of it,
        # and that block is the only place a test can state which pairs were never
        # tested -- the cell state this family exists to keep distinct.
        import population_synthetic.analysis.method_significance.charts as pair_mod
        from tests import _method_significance_fixtures as ms_fixtures

        pair_methods = ms_fixtures.FIVE_METHODS
        pair_result = ms_fixtures.result(pair_methods, {
            "overall": ms_fixtures.panel(
                pair_methods, ms_fixtures.significant_pairs(pair_methods),
            ),
        })
        pair_figures = _capture_saved(
            pair_mod,
            lambda: pair_mod.plot_method_pair_significance(pair_result, "unused"),
        )
        pair_by_variant = dict(zip(pair_mod.GRID_VARIANTS, pair_figures))
        yield (
            "method_significance::plot_method_pair_significance",
            pair_by_variant[pair_mod.GRID_VARIANT_WITH_COUNTS.name],
            pair_by_variant[pair_mod.GRID_VARIANT_CLEAN.name],
        )


@pytest.fixture(scope="module")
def variant_pairs():
    import matplotlib.pyplot as plt

    pairs = list(_variant_pairs())
    yield pairs
    for _label, counted, clean in pairs:
        plt.close(counted)
        plt.close(clean)


def test_every_grid_family_publishes_a_variant_pair(variant_pairs) -> None:
    """A vacuous sweep passes every rule it checks; this is what stops that."""
    families = {label.split("::")[0] for label, _counted, _clean in variant_pairs}
    assert families == {
        "validation_attrition", "model_ranking", "realism_ranking", "generation_metadata",
        "method_significance",
    }


def test_the_two_variants_of_every_grid_are_the_same_figure(variant_pairs) -> None:
    """Substitutability, on every published pair rather than on F05 alone."""
    for label, counted, clean in variant_pairs:
        _assert_substitutable(counted, clean, label)


def test_the_clean_variant_of_every_grid_drops_only_the_count_line(variant_pairs) -> None:
    """The canonical figure loses the count line and keeps everything else."""
    for label, counted, clean in variant_pairs:
        _assert_clean_drops_only_the_count_line(counted, clean, label)


def _variant_maps():
    """Every family's variant map, as ``(label, map)``."""
    import population_synthetic.analysis.generation_metadata.charts as gm_mod
    import population_synthetic.analysis.method_significance.charts as pair_mod
    import population_synthetic.analysis.model_ranking.charts as ranking_mod
    import population_synthetic.analysis.realism_ranking.charts as realism_mod
    import population_synthetic.analysis.validation_attrition.charts as attrition_mod

    return [
        ("validation_attrition", attrition_mod.GRID_VARIANTS),
        ("model_ranking", ranking_mod.GRID_VARIANTS),
        ("realism_ranking::rate", realism_mod.RATE_GRID_VARIANTS),
        ("realism_ranking::typicality", realism_mod.TYPICALITY_GRID_VARIANTS),
        ("generation_metadata", gm_mod.GRID_VARIANTS),
        ("method_significance", pair_mod.GRID_VARIANTS),
    ]


def test_every_family_names_the_canonical_variant_the_same_way() -> None:
    """One naming rule across every family, so no driver invents one of its own."""
    from population_synthetic.analysis.utils.grid_variants import (
        CANONICAL_VARIANT,
        COUNTED_VARIANT,
        variant_suffixes,
    )

    for label, variants in _variant_maps():
        assert set(variants) == {CANONICAL_VARIANT, COUNTED_VARIANT}, label
        suffixes = {
            variant.name: suffix for suffix, variant in variant_suffixes(variants)
        }
        # The camera-ready figure takes the bare filename; the counted one is suffixed.
        assert suffixes[CANONICAL_VARIANT] == "", label
        assert suffixes[COUNTED_VARIANT] == f"_{COUNTED_VARIANT}", label


def test_no_variant_prints_below_the_publisher_font_floor() -> None:
    """Dropping a line may buy type size; it may never cost any."""
    from population_synthetic.analysis.utils.grid_variants import (
        CANONICAL_VARIANT,
        COUNTED_VARIANT,
    )
    from population_synthetic.analysis.utils.style import FONT_FLOOR_PT

    for label, variants in _variant_maps():
        for name, variant in variants.items():
            assert variant.fontsize >= FONT_FLOOR_PT, f"{label}::{name}"
        assert (
            variants[CANONICAL_VARIANT].fontsize >= variants[COUNTED_VARIANT].fontsize
        ), label


def test_a_family_without_a_canonical_variant_raises_rather_than_promoting_one() -> None:
    """The unsuffixed filename is the manuscript's; nothing may take it by accident."""
    from population_synthetic.analysis.utils.grid_variants import (
        COUNTED_VARIANT,
        GridVariant,
        variant_map,
        variant_suffixes,
    )

    counted = GridVariant(
        name=COUNTED_VARIANT, policy=RateOnlyPolicy(), cell_clause="", fontsize=8.0,
        linespacing=None,
    )
    with pytest.raises(ValueError, match="clean"):
        variant_map(counted)
    with pytest.raises(ValueError, match="clean"):
        variant_suffixes({counted.name: counted})


def test_two_variants_may_not_share_a_name() -> None:
    """A name is a filename suffix, so a duplicate would silently drop a publication."""
    from population_synthetic.analysis.utils.grid_variants import (
        CANONICAL_VARIANT,
        GridVariant,
        variant_map,
    )

    clean = GridVariant(
        name=CANONICAL_VARIANT, policy=RateOnlyPolicy(), cell_clause="", fontsize=8.0,
        linespacing=None,
    )
    with pytest.raises(ValueError, match="share the name"):
        variant_map(clean, clean)

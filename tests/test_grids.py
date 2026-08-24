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
)
from population_synthetic.analysis.utils.grids import (  # noqa: E402
    CellRecordMismatch,
    GridShapeMismatch,
    render_grid,
)
from population_synthetic.analysis.utils.palette import MISSING_COLOR, heatmap_cmap  # noqa: E402

_ALL_POLICIES = (
    RateWithCountsPolicy(),
    RateOnlyPolicy(),
    SignedValuePolicy(),
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
        GRID_VARIANT_ANNOTATED,
        GRID_VARIANT_CLEAN,
        plot_mapped_validity_grid,
    )

    from tests.test_validation_attrition_charts import _COMPLEX, _SIMPLE, _document, _entry

    document = _document([
        _entry("claude_haiku", _SIMPLE, clean=120),
        _entry("claude_haiku", _COMPLEX, clean=9, selected=0, excluded=True),
        _entry("gemini_flash", _SIMPLE, generated=0, raw_valid=0, clean=0, selected=0,
               excluded=True),
    ])

    annotated = plot_mapped_validity_grid(document, variant=GRID_VARIANT_ANNOTATED)
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
        GRID_VARIANT_ANNOTATED,
        GRID_VARIANT_CLEAN,
    )

    assert GRID_VARIANT_CLEAN.fontsize >= FONT_FLOOR_PT
    assert GRID_VARIANT_ANNOTATED.fontsize >= FONT_FLOOR_PT
    # The clean variant spends the room the dropped count line frees.
    assert GRID_VARIANT_CLEAN.fontsize > GRID_VARIANT_ANNOTATED.fontsize

"""Tests for the shared analysis-layer heatmap palette.

Three properties, each one a bug that has a silent failure mode: the ramp is shared
by every sequential grid, ``heatmap_cmap`` never hands back the registry's own object,
and annotation colour is derived from the painted colour rather than from a threshold
tuned to one ramp.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from population_synthetic.analysis.utils.palette import (  # noqa: E402
    HEATMAP_CMAP,
    MISSING_COLOR,
    heatmap_cmap,
    text_color_for_rgb,
    text_color_on,
)


def test_heatmap_cmap_is_a_copy_not_the_registry_object():
    """``set_bad`` mutates; matplotlib hands every caller the same registry instance.

    Without the copy, one chart setting its missing-cell colour would repaint the
    missing cells of every other figure drawn in the same process -- a cross-figure
    effect with no error and no local symptom.
    """
    mine = heatmap_cmap(missing="#FF0000")
    registry = plt.get_cmap(HEATMAP_CMAP)

    assert mine is not registry
    assert mine.get_bad()[:3] == pytest.approx((1.0, 0.0, 0.0))
    # The registry copy is untouched: its bad colour is still fully transparent.
    assert registry(np.ma.masked_invalid([np.nan]))[0][3] == pytest.approx(0.0)


def test_missing_colour_defaults_to_the_off_ramp_grey():
    cmap = heatmap_cmap()
    assert matplotlib.colors.to_hex(cmap.get_bad()).upper() == MISSING_COLOR.upper()


@pytest.mark.parametrize(
    "rgb, expected",
    [
        ((0.0, 0.0, 0.0), "white"),        # inferno's low end: near-black
        ((0.99, 0.99, 0.75), "black"),     # inferno's high end: bright yellow
        ((0.0, 0.0, 1.0), "white"),        # saturated blue is dark to the eye ...
        ((1.0, 1.0, 0.0), "black"),        # ... and saturated yellow is light
    ],
)
def test_text_colour_follows_luminance_not_raw_value(rgb, expected):
    """An unweighted mean would call blue light and yellow dark -- backwards for both."""
    assert text_color_for_rgb(rgb) == expected


def test_text_colour_on_a_sequential_ramp_flips_across_the_range():
    """The house ramp is dark at its floor and bright at its ceiling."""
    fig, ax = plt.subplots()
    im = ax.imshow(np.array([[0.0, 1.0]]), cmap=heatmap_cmap(), vmin=0.0, vmax=1.0)

    assert text_color_on(im, 0.0) == "white"
    assert text_color_on(im, 1.0) == "black"
    plt.close(fig)


def test_text_colour_on_a_diverging_ramp_needs_no_special_case():
    """Diverging ramps are dark at *both* ends and pale in the middle.

    No chart in the layer uses one today -- they were all unified onto the house
    sequential ramp -- but the helper is the reason a future one could be reintroduced
    without touching annotation code: a "dark above a threshold" rule needs an explicit
    second branch for the two-ended shape, and luminance needs none.
    """
    fig, ax = plt.subplots()
    im = ax.imshow(np.array([[-1.0, 1.0]]), cmap=heatmap_cmap("PuOr"), vmin=-1.0, vmax=1.0)

    assert text_color_on(im, -1.0) == "white"
    assert text_color_on(im, 1.0) == "white"
    assert text_color_on(im, 0.0) == "black"
    plt.close(fig)

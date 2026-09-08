"""Tests for the shared analysis-layer colour vocabulary.

Every property here has a silent failure mode: the ramp is shared by every sequential
grid, ``heatmap_cmap`` never hands back the registry's own object, the categorical series
are stable (chart modules cycle them *positionally* and hold no copy of their own, so
reordering or shortening one silently recolours every figure that uses it) and internally
distinct, and annotation colour is derived from the painted colour by a contrast model
rather than by a threshold tuned to one ramp.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from population_synthetic.analysis.utils import palette  # noqa: E402
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    ACCENT_PAIR,
    CATEGORICAL_SERIES,
    HEATMAP_CMAP,
    HOST_COLORS,
    MISSING_COLOR,
    ORDERED_QUALITATIVE_SERIES,
    SEVERITY_SERIES,
    STAGE_SERIES,
    SURFACE,
    heatmap_cmap,
    heatmap_levels,
    opaque,
    relative_luminance,
    text_color_for_rgb,
    text_color_on,
)

#: The categorical roles, as ``(name, expected length, values)``. Listed rather than
#: discovered so that *removing* one is a failure too.
_CATEGORICAL_ROLES = [
    ("CATEGORICAL_SERIES", 7, CATEGORICAL_SERIES),
    ("ACCENT_PAIR", 2, ACCENT_PAIR),
    ("ORDERED_QUALITATIVE_SERIES", 5, ORDERED_QUALITATIVE_SERIES),
    ("STAGE_SERIES", 4, STAGE_SERIES),
    ("SEVERITY_SERIES", 3, SEVERITY_SERIES),
    ("HOST_COLORS", 2, tuple(HOST_COLORS.values())),
]

_ROLE_IDS = [role[0] for role in _CATEGORICAL_ROLES]


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


def test_heatmap_levels_bins_the_house_ramp_into_the_requested_steps():
    """A tiered quantity is drawn on *n* steps, sampled from the one house ramp."""
    levels = heatmap_levels(5)

    assert isinstance(levels, matplotlib.colors.ListedColormap)
    assert levels.N == 5
    # Sampled from the same ramp, not a second one: the extreme steps sit at the
    # continuous ramp's own ends.
    continuous = heatmap_cmap()
    assert levels(0)[:3] == pytest.approx(continuous(0.0)[:3], abs=0.02)
    assert levels(4)[:3] == pytest.approx(continuous(1.0)[:3], abs=0.02)


def test_heatmap_levels_keeps_an_opaque_missing_colour():
    """``render_grid`` derives the unpainted cell's text colour from ``set_bad``.

    It raises outright on a fully transparent bad colour, so a discrete ramp that lost
    the entry on the way through ``resampled`` would take every grid drawn on it down --
    or, worse, take down only the grids that happen to have an unmeasured cell.
    """
    levels = heatmap_levels(5)

    assert matplotlib.colors.to_hex(levels.get_bad()).upper() == MISSING_COLOR.upper()
    assert levels.get_bad()[3] == pytest.approx(1.0)


def test_heatmap_levels_is_a_copy_and_honours_a_declared_missing_colour():
    levels = heatmap_levels(3, missing="#FF0000")
    registry = plt.get_cmap(HEATMAP_CMAP)

    assert levels is not registry
    assert levels.get_bad()[:3] == pytest.approx((1.0, 0.0, 0.0))
    assert registry(np.ma.masked_invalid([np.nan]))[0][3] == pytest.approx(0.0)


@pytest.mark.parametrize("bad_n", [0, -1, 2.5, True, "5"])
def test_heatmap_levels_rejects_a_step_count_that_is_not_a_positive_integer(bad_n):
    """Matplotlib would answer these with an empty or silently rounded colormap."""
    with pytest.raises(ValueError, match="positive integer"):
        heatmap_levels(bad_n)


def test_every_public_name_is_exported():
    """``__all__`` is listed by hand, so it can only stay complete if that is asserted.

    A colour role added without an entry is half-exported: present on the module,
    absent from its declared surface, and invisible to anything reading the latter.
    """
    public = {
        name for name in vars(palette)
        if not name.startswith("_") and name not in {"annotations"}
    }
    assert public == set(palette.__all__)


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


# ------------------------------------------------------------------
# The categorical roles
# ------------------------------------------------------------------

@pytest.mark.parametrize("name, length, values", _CATEGORICAL_ROLES, ids=_ROLE_IDS)
def test_categorical_role_is_non_empty_and_the_expected_length(name, length, values):
    """A cycled series is indexed by position, so its length is part of its contract.

    A series that quietly shrinks does not raise: the caller's ``i % len(...)`` simply
    wraps sooner, and two categories that were distinct start sharing a colour.
    """
    assert values, f"{name} is empty"
    assert len(values) == length


@pytest.mark.parametrize("name, length, values", _CATEGORICAL_ROLES, ids=_ROLE_IDS)
def test_categorical_role_entries_are_distinct(name, length, values):
    """Two equal entries make two categories indistinguishable, with no error anywhere."""
    normalised = [matplotlib.colors.to_hex(v).lower() for v in values]
    assert len(set(normalised)) == len(normalised), f"{name} repeats a colour: {normalised}"


@pytest.mark.parametrize("name, length, values", _CATEGORICAL_ROLES, ids=_ROLE_IDS)
def test_categorical_role_entries_are_parseable_colours(name, length, values):
    """Every entry resolves through matplotlib, so a mistyped hex fails here, not on a canvas."""
    for value in values:
        assert len(matplotlib.colors.to_rgb(value)) == 3


def test_the_house_categorical_series_is_stable():
    """Pinned literally: chart modules index it positionally and hold no copy of their own.

    Reordering or retuning it is a deliberate, layer-wide restyle -- which is exactly the
    change this assertion exists to make visible rather than silent.
    """
    assert CATEGORICAL_SERIES == (
        "#4878CF", "#D65F5F", "#6AB187", "#E8935A", "#E9C46A", "#8172B2", "#64B5CD",
    )


def test_host_colours_are_slots_of_the_house_series():
    """The provenance split is a categorical role, not a colour vocabulary of its own."""
    assert set(HOST_COLORS) == {"hosted", "local"}
    assert HOST_COLORS["hosted"] == CATEGORICAL_SERIES[0]
    assert HOST_COLORS["local"] == CATEGORICAL_SERIES[3]


def test_the_sequential_ramp_is_the_only_ramp():
    """Settled by ADR 2026-08-12: one house ramp, off-ramp grey for the unmeasured cells."""
    assert HEATMAP_CMAP == "inferno"
    assert MISSING_COLOR == "#DDDDDD"


# ------------------------------------------------------------------
# The WCAG relative-luminance model
# ------------------------------------------------------------------

def test_relative_luminance_matches_the_reference_points():
    """Black is 0, white is 1, and each primary carries its BT.709 weight exactly."""
    assert relative_luminance((0.0, 0.0, 0.0)) == pytest.approx(0.0)
    assert relative_luminance((1.0, 1.0, 1.0)) == pytest.approx(1.0)
    assert relative_luminance((1.0, 0.0, 0.0)) == pytest.approx(0.2126)
    assert relative_luminance((0.0, 1.0, 0.0)) == pytest.approx(0.7152)
    assert relative_luminance((0.0, 0.0, 1.0)) == pytest.approx(0.0722)


def test_relative_luminance_linearises_rather_than_weighting_gamma_encoded_values():
    """Mid-grey is ~0.214 in linear light, not the 0.5 its encoded value suggests.

    This is the whole of the corrected bug: weighting gamma-encoded sRGB overstates the
    luminance of dark fills, which is how the previous rule came to hand white text to
    fills that black reads on considerably better.
    """
    assert relative_luminance((0.5, 0.5, 0.5)) == pytest.approx(0.2140, abs=5e-4)


def test_relative_luminance_rejects_an_out_of_range_channel():
    """0-255 input is the plausible mistake, and it must fail rather than be clamped."""
    with pytest.raises(ValueError, match="out of range"):
        relative_luminance((255, 255, 255))


def _grey_with_luminance(luminance: float) -> tuple[float, float, float]:
    """The neutral grey whose relative luminance is *luminance* (inverse sRGB transfer)."""
    if luminance <= 0.0031308:
        channel = luminance * 12.92
    else:
        channel = 1.055 * luminance ** (1 / 2.4) - 0.055
    return (channel, channel, channel)


def _contrast_ratio(luminance: float, text: str) -> float:
    """WCAG contrast ratio between a fill of *luminance* and white or black *text*."""
    text_luminance = 1.0 if text == "white" else 0.0
    lighter, darker = max(luminance, text_luminance), min(luminance, text_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_crossover_is_the_equal_contrast_luminance():
    """Solving ``(L + 0.05) ** 2 == 1.05 * 0.05`` -- the L at which the two options tie."""
    crossover = palette._TEXT_CONTRAST_CROSSOVER

    assert crossover == pytest.approx(0.1791287847, abs=1e-9)
    assert (crossover + 0.05) ** 2 == pytest.approx(1.05 * 0.05)
    assert _contrast_ratio(crossover, "white") == pytest.approx(_contrast_ratio(crossover, "black"))


def test_text_colour_switches_across_the_crossover():
    """Below it white wins; above it black does. The old rule switched at 0.5 instead."""
    crossover = palette._TEXT_CONTRAST_CROSSOVER

    assert text_color_for_rgb(_grey_with_luminance(crossover - 0.01)) == "white"
    assert text_color_for_rgb(_grey_with_luminance(crossover + 0.01)) == "black"


@pytest.mark.parametrize("cmap_name", ["inferno", "viridis", "PuOr"])
def test_text_colour_picks_the_higher_contrast_option_across_a_whole_ramp(cmap_name):
    """Not merely "a readable colour" but *the better of the two*, at every sample.

    Asserted over a whole ramp rather than at hand-picked points, because the failure
    mode is a band of the ramp on which the rule selects the loser -- which no single
    sample reveals. The band the old BT.601-on-gamma rule got wrong sat just below its
    0.5 threshold.
    """
    cmap = plt.get_cmap(cmap_name)
    for i in range(65):
        rgb = cmap(i / 64.0)[:3]
        chosen = text_color_for_rgb(rgb)
        other = "black" if chosen == "white" else "white"
        luminance = relative_luminance(rgb)
        assert _contrast_ratio(luminance, chosen) >= _contrast_ratio(luminance, other)


def test_the_off_ramp_missing_fill_takes_dark_annotation_text():
    """The "never measured" grey is light, so its wording must be the dark option."""
    assert text_color_for_rgb(matplotlib.colors.to_rgb(MISSING_COLOR)) == "black"


# --------------------------------------------------------------------------- #
# the opaque compositor                                                         #
# --------------------------------------------------------------------------- #

#: Tolerance for a colour that has been through the hex round-trip an 8-bit RGB output
#: format imposes anyway. One channel step, so a comparison is exact to what is written.
_ONE_CHANNEL_STEP = 1.0 / 255.0


def test_opaque_returns_the_colour_matplotlib_would_have_painted():
    """The "over" operator on sRGB, which is what the raster backends themselves do.

    Asserted against a hand-computed midpoint rather than against the implementation:
    half of black over white is the mid grey, whatever the code does to get there.
    """
    assert matplotlib.colors.to_rgb(opaque("black", 0.5)) == pytest.approx(
        (0.5, 0.5, 0.5), abs=_ONE_CHANNEL_STEP
    )


@pytest.mark.parametrize("colour", ["#C44E52", "black", (0.1, 0.7, 0.3)])
def test_full_coverage_is_the_colour_itself_and_none_is_the_ground(colour):
    """The two endpoints, so a caller passing 1.0 never has its colour quietly shifted."""
    assert matplotlib.colors.to_rgb(opaque(colour, 1.0)) == pytest.approx(
        matplotlib.colors.to_rgb(colour), abs=_ONE_CHANNEL_STEP
    )
    assert matplotlib.colors.to_rgb(opaque(colour, 0.0)) == pytest.approx(
        matplotlib.colors.to_rgb(SURFACE), abs=_ONE_CHANNEL_STEP
    )


def test_the_ground_is_the_page_unless_the_caller_names_another():
    """A caller drawing over another artist passes that artist's colour."""
    on_page = opaque("black", 0.5)
    on_grey = opaque("black", 0.5, over="#808080")
    assert on_page != on_grey
    assert matplotlib.colors.to_rgb(on_grey) == pytest.approx((0.25098, 0.25098, 0.25098), abs=1e-4)


@pytest.mark.parametrize("alpha", [-0.01, 1.01, 2.0])
def test_a_coverage_outside_the_unit_interval_raises(alpha):
    """Never a colour matplotlib would have drawn, so it is always a caller bug."""
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        opaque("black", alpha)


#: Calls whose ``alpha=`` is a significance level, not a coverage. Named rather than
#: pattern-matched: the test must keep failing on a *drawing* call that acquires an
#: alpha, and the only way to keep that sharp is to enumerate the statistical ones.
_STATISTICAL_ALPHA_CALLS = frozenset({"resolve_pairs"})


def _called_name(node) -> str:
    """The bare name of a call's callee -- ``a.b.plot(...)`` -> ``plot``."""
    import ast

    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_the_layer_draws_no_transparent_artist():
    """The EPS backend flattens alpha, so an alpha= anywhere splits EPS from PNG/SVG.

    Scanned over the whole analysis package rather than asserted on one module: the
    divergence is invisible in review because it appears only in the one file that leaves
    the repository. Read from the syntax tree, not from the text, so the module docstrings
    that *explain* the rule are not mistaken for breaches of it, and so
    ``framealpha=`` -- a different keyword, opaque by definition at the ``1.0`` the
    legends pass -- is not swept in by a substring match.
    """
    import ast

    root = Path(palette.__file__).resolve().parent.parent
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _called_name(node) in _STATISTICAL_ALPHA_CALLS:
                continue
            for keyword in node.keywords:
                if keyword.arg == "alpha":
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []

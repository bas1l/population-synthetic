"""palette.py -- The shared colour vocabulary for every analysis-layer figure.

One definition of the house ramp *and* of every categorical hue and grey the layer
draws with, so the figures scattered across ``03_Analysis/`` (fidelity, model_ranking,
generation_metadata, realism_ranking, ...) read as one figure family rather than as a
dozen unrelated ones. Before this module each chart module named its own colormap at its
own ``imshow`` call, and the same quantity -- a model x method mean -- was drawn on
viridis in one folder and on Reds in another. Categorical colour then followed the same
path: the seven-hue series below was copy-pasted verbatim into five chart modules and
renamed into a sixth, and roughly twenty-five greys were written as bare hex literals at
the call site that used them.

**The ramp is sequential, and every heatmap that plots a magnitude now uses it** --
including the two whose quantity is genuinely two-sided (``realism_ranking``'s
typicality statistic, read against the real population's own value, and
``method_significance``'s trend slope, read against zero). Those two previously used
diverging ramps, and unifying them has a real cost that their renderers must pay back
explicitly: a sequential ramp orders cells by **magnitude alone**, so two values equally
far above and below the reference are drawn differently and neither drawing says which
side it was on.

Both renderers therefore carry the side in the annotations instead of in the hue -- a
signed number in every cell plus a rule across the colourbar at the reference -- and say
so in a printed caption. A future two-sided heatmap must do the same or keep its own
diverging ramp; what it must not do is adopt this ramp and leave the sign implicit,
because the resulting figure looks complete while having silently dropped half its
content.

One family departs from the house ramp on purpose: the significance grids paint an
*ordinal grade* rather than a magnitude, and take the single-hue
:data:`SIGNIFICANCE_CMAP` for the reason given at that entry.

Annotation colour is *derived*, never chosen: :func:`text_color_on` asks the
mappable what colour it actually painted the cell and picks white or black by that
colour's relative luminance. A hand-tuned "white above 60% of the range" threshold
is a property of one ramp's luminance profile, and silently produces unreadable
text when the ramp changes -- inferno is bright at its top end where Reds is dark,
so the two want opposite rules.

**What this module knows nothing about.** Which metric is plotted, which country is
analysed, which analysis process or which figure is being drawn, what the models,
strategies, severities or funnel stages are called, or how any value was computed. It
holds colour *roles* -- the names below say what a colour is *for*, never what hue it is
-- and a caller maps its own domain vocabulary onto them. That is why, for example, the
severity levels ``S1``/``S2``/``S3`` do not appear here: ``persona_realism`` owns that
mapping and reaches into :data:`SEVERITY_SERIES` for the hues. It also imports nothing
from any analysis subpackage, and imports matplotlib lazily inside the one function that
needs it, so importing it never pulls in a backend.
"""

from __future__ import annotations

#: The module's public surface, listed rather than inferred so that *removing* a role is
#: a deliberate act. ``tests/test_palette.py`` asserts this set equals the module's
#: public names, so a colour added without an entry here fails the suite rather than
#: quietly becoming a half-exported role.
__all__ = [
    "ACCENT_PAIR",
    "ANNOTATION_GREY",
    "BAND_EDGE",
    "BAND_FILL",
    "BAR_EDGE",
    "BASELINE_DARK",
    "BEST_CELL_EDGE",
    "CAPTION_GREY",
    "CATEGORICAL_SERIES",
    "CELL_STROKE",
    "ERROR_BAR_GREY",
    "FAINT_LINK",
    "FOOTNOTE_GREY",
    "GRID_RULE",
    "HEATMAP_CMAP",
    "HIGHLIGHT_ACCENT",
    "HOLLOW_EDGE",
    "HOST_COLORS",
    "LARGE_CATEGORICAL_CMAP",
    "MISSING_COLOR",
    "MUTED_GREY",
    "NEUTRAL_GREY",
    "ORDERED_QUALITATIVE_SERIES",
    "PALE_FILL",
    "RESIDUAL_GREY",
    "SECONDARY_GREY",
    "SEVERITY_SERIES",
    "WORST_CLASH_COLORS",
    "SIGNIFICANCE_CMAP",
    "STAGE_SERIES",
    "SURFACE",
    "WARNING_FILL",
    "WARNING_TEXT",
    "heatmap_cmap",
    "heatmap_levels",
    "opaque",
    "relative_luminance",
    "text_color_for_rgb",
    "text_color_on",
    "worst_clash_color",
]

# ------------------------------------------------------------------
# The sequential ramp
# ------------------------------------------------------------------

#: The house sequential heatmap ramp. ``inferno`` because the manuscript fidelity
#: tables (``{country}_models_table``) already publish on it, and those are the
#: figures that leave the repository; matching them makes the internal grids read
#: as drafts of the published ones rather than as a separate visual language. It is
#: perceptually uniform and monotone in lightness, so the annotated numbers stay
#: legible at both ends once :func:`text_color_on` picks their colour.
HEATMAP_CMAP = "inferno"

#: The ramp for a **significance tier**, and the layer's one sanctioned departure from
#: :data:`HEATMAP_CMAP`. ``Blues_r``: a single hue, so brightness alone carries the
#: ordering and no step can be told from its neighbour by anything but how dark it is;
#: reversed, so the *darkest* step is the *most* significant rung and the palest is the
#: one reported not significant.
#:
#: Deliberately not the house ramp, and the reason is what the quantity is rather than a
#: preference. A tier is an ordinal grade read off a ladder a config file declares, not a
#: magnitude: the distance between two rungs is not a number. Inferno moves through
#: black, purple, red, orange and yellow, and a hue change of that size across adjacent
#: steps invites reading the ladder as a set of *kinds* -- the red tier and the yellow
#: tier -- when the only relation between them is more and less. One hue removes the
#: invitation.
#:
#: The palest step must also stay distinguishable from :data:`MISSING_COLOR`, because
#: "never tested" and "tested, not significant" are different findings that the
#: significance grids paint differently on purpose. ``Blues_r`` ends near white, well
#: clear of that grey; ``Greys_r`` was rejected for landing a painted step on top of it.
SIGNIFICANCE_CMAP = "Blues_r"

#: Fill for a cell with no value at all. Deliberately off-ramp: rendering an
#: unmeasured cell at the ramp's low end would present "never measured" as "measured
#: and lowest", which is the most damaging misreading a grid can produce.
MISSING_COLOR = "#DDDDDD"

# ------------------------------------------------------------------
# Categorical colour
# ------------------------------------------------------------------

#: The house categorical series, cycled positionally by every chart that draws several
#: unordered series at once. Seven hues because that is the point past which position in
#: a cycled series stops being recognisable anyway; a chart with more series than this
#: wraps and must carry identity by something other than hue as well (see
#: :data:`LARGE_CATEGORICAL_CMAP`).
#:
#: Qualitative, **not** the sequential ramp: an element's index is a slot, not a
#: magnitude, and neighbouring entries are deliberately far apart in hue so adjacent
#: bars separate without relying on a legend.
CATEGORICAL_SERIES: tuple[str, ...] = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)

#: A second two-hue categorical accent, for a pair of series overlaid on the *same* axes
#: as filled shapes rather than set side by side. Distinct from
#: ``CATEGORICAL_SERIES[:2]`` so a two-series overlay drawn on top of other categorical
#: content cannot be misread as the first two slots of that series.
ACCENT_PAIR: tuple[str, str] = ("#2A9D8F", "#E9C46A")

#: A qualitative series for a set of categories that *has* an order which is read off the
#: legend rather than off the hue. ColorBrewer Dark2. Deliberately not the sequential
#: ramp: a sequential ramp would additionally imply that the distance between two
#: adjacent categories is a magnitude, which for an ordered-but-not-numeric factor it is
#: not.
ORDERED_QUALITATIVE_SERIES: tuple[str, ...] = (
    "#1B9E77",
    "#D95F02",
    "#7570B3",
    "#E7298A",
    "#66A61E",
)

#: A four-step series for the disjoint slices of a funnel or partition, in stage order.
#: ColorBrewer's 4-class RdBu: these encode **which stage** a unit left at -- a category
#: with a direction, not a score -- so they are deliberately not the sequential score
#: ramp, and the pair of blues (the retained stages) reads against the pair of reds (the
#: lost ones) without relying on hue discrimination alone.
STAGE_SERIES: tuple[str, ...] = ("#0571B0", "#92C5DE", "#F4A582", "#CA0020")

#: An ordered three-step alert series, **severest first**: Okabe & Ito's vermillion,
#: orange and sky blue (Wong 2011, *Nature Methods* 8:441), the colour-blind-safe
#: categorical set. Severity is ordinal, so the three run warm-to-cool as well as
#: dark-to-light: the severest step is the darkest and warmest, the mildest the coolest.
#: The mildest step is a hue rather than a grey on purpose -- as a grey it sat too close to
#: the light-grey "no clash" fill and to the reference outline to be told apart in a small
#: glyph. Under simulated deuteranopia, protanopia and tritanopia (Machado et al. 2009)
#: every pair of :data:`WORST_CLASH_COLORS` stays above CIEDE2000 10; the figures are in
#: docs/development/figure-conventions.md.
SEVERITY_SERIES: tuple[str, str, str] = ("#D55E00", "#E69F00", "#56B4E9")

#: The worst-clash-per-individual categories (``config/analysis/realism_ranking/
#: worst_clash_split.yaml``), keyed by category id; the categorical severity palette of the
#: worst-clash figures. ``none`` is a neutral light grey (no clash is not a severity step);
#: ``S1``/``S2`` are :data:`SEVERITY_SERIES`'s mild and middle steps. The stage-2 split of
#: the severest level stays in the Okabe-Ito set: an impossible individual (``S3a``) keeps
#: the severest step's vermillion, contradictory labels (``S3b``) take the reddish purple
#: beside it, and the unsplit ``S3`` (the reference, or a failed stage-2 call) the dark blue
#: -- a hue outside the warm run, because "not split" is a missing classification, not a
#: degree. Black was rejected there: it merges with the reference step outline drawn over
#: the bars. ``pipeline`` (a mapping or judge artefact) is the bluish green, outside the
#: severity run on purpose: it is not a verdict on the individual. The yellow of the set is
#: not used -- it is unreadable as a thin bar or as count text on white.
WORST_CLASH_COLORS: dict[str, str] = {
    "none": "#E4E4E4",
    "S1": SEVERITY_SERIES[2],
    "S2": SEVERITY_SERIES[1],
    "S3b": "#CC79A7",
    "S3a": SEVERITY_SERIES[0],
    "S3": "#0072B2",
    "pipeline": "#009E73",
}


def worst_clash_color(category: str) -> str:
    """The colour of worst-clash *category*; raises on an id the palette does not know."""
    if category not in WORST_CLASH_COLORS:
        raise KeyError(f"no worst-clash colour for category {category!r}; known: {sorted(WORST_CLASH_COLORS)}")
    return WORST_CLASH_COLORS[category]


#: The single series singled out for contrast against a field of
#: :data:`CATEGORICAL_SERIES` members -- a reference competitor among ordinary ones, or
#: the tail of a distribution against its body. It once shared its hue with
#: ``SEVERITY_SERIES[0]``; the two roles are independent and are retuned separately.
HIGHLIGHT_ACCENT = "#C44E52"

#: Provenance colours for the hosted/local split. Colourblind-safe categorical hues that
#: encode *category* (hosting class), not score, and are deliberately distinct from the
#: sequential score ramp. Drawn as a tick-label colour and a legend swatch, never as a
#: data mark, so the two entries only have to separate from each other.
HOST_COLORS: dict[str, str] = {"hosted": "#4878CF", "local": "#E8935A"}

#: Colormap a chart samples when it has more series than :data:`CATEGORICAL_SERIES` can
#: name -- ``tab20`` is qualitative and twenty wide. Sampling a *ramp* would be worse
#: still, so this is the escape hatch, not an invitation: a figure needing it should also
#: separate its series by marker or position.
LARGE_CATEGORICAL_CMAP = "tab20"

# ------------------------------------------------------------------
# Greys and furniture
# ------------------------------------------------------------------

#: Near-black rule marking a distinguished cell (the best in its column). Near-black
#: rather than pure black so it reads as a rule on the bright end of the ramp without
#: vibrating on the dark end.
BEST_CELL_EDGE = "#111111"

#: A baseline or reference series drawn alongside a set of :data:`CATEGORICAL_SERIES`
#: members. Outside that series by construction, so the thing being compared *against*
#: never reads as one of the things being compared.
BASELINE_DARK = "#222222"

#: Primary in-figure annotation text on a light ground, and short near-black rules that
#: belong to the annotation layer rather than to the data.
ANNOTATION_GREY = "#333333"

#: Subtitle and caption text sitting immediately beside a title -- one step back from
#: :data:`ANNOTATION_GREY` so it reads as subordinate to it.
CAPTION_GREY = "#444444"

#: Footnote text at the figure margin: the caveats and provenance notes that travel with
#: the figure but are not read alongside the data.
FOOTNOTE_GREY = "#555555"

#: Secondary inline notes inside the data area -- a "n/a" standing in for an absent
#: value, or the label naming a reference line.
SECONDARY_GREY = "#666666"

#: Reference rules and de-emphasised notes: a threshold line the data is read against,
#: and text saying something was omitted.
MUTED_GREY = "#888888"

#: A neutral, non-judging categorical step -- an interval whisker, or a category that is
#: deliberately given no valence. Distinct from :data:`MUTED_GREY`, which de-emphasises;
#: this one is a full-strength member of a series that simply has no hue.
NEUTRAL_GREY = "#8C8C8C"

#: The unexplained remainder of a decomposition. Grey because the residual is what is
#: *left over* after every named component, and a hue would enlist it as one of them.
RESIDUAL_GREY = "#BBBBBB"

#: Background grid rule behind the data. Shares its value with :data:`MISSING_COLOR`;
#: the two roles are independent -- one is furniture, the other is a datum -- and either
#: may be retuned without the other.
GRID_RULE = "#DDDDDD"

#: Separator drawn along the boundary between two abutting heatmap cells. Two tiles that
#: touch shift each other's apparent value -- simultaneous contrast, named as a defect of
#: unseparated raster grids in Crameri, Shephard and Heron (2020), *Nature Communications*
#: 11:5444, citing Wong (2011), *Nature Methods* 8:441 -- and ``imshow`` draws no
#: separator of its own. White, because the stroke's job is to read as a *gap* between the
#: tiles, the page showing through, rather than as a rule with a value of its own that
#: would itself be read against the ramp. Shares its value with :data:`SURFACE`; the two
#: roles are independent and either may be retuned without the other.
CELL_STROKE = "#FFFFFF"

#: Dark outline separating abutting filled bars, boxes and patches from each other and
#: from the ground.
BAR_EDGE = "#33486F"

#: Error bars and interval whiskers drawn *over* a filled mark: dark enough to read on
#: the fill, one step back from :data:`ANNOTATION_GREY` so it does not compete with the
#: labels beside it. Shares its value with :data:`CAPTION_GREY`; the roles are
#: independent -- one is furniture over the data, the other is text beside it.
ERROR_BAR_GREY = "#444444"

#: Pale fill for a summary bar that individual observations are drawn on top of: light
#: enough that the overlaid points stay readable, saturated enough to still read as a bar.
PALE_FILL = "#BFD1EA"

#: Faint connector drawn between paired observations, to show the pairing without letting
#: the connectors dominate the points they join.
FAINT_LINK = "#8899AA"

#: Fill and edge of an annotated *region* of the axes -- a band whose horizontal or
#: vertical extent is a statement about the scale rather than about any datum.
BAND_FILL = "#E8E8E8"
BAND_EDGE = "#9A9A9A"

#: The figure surface itself, named so a hollow marker or an emptied cell says "nothing
#: is here" by matching the ground rather than by carrying a fill of its own.
SURFACE = "#FFFFFF"

#: Light edge around a :data:`SURFACE`-filled cell, so an emptied cell still has a
#: boundary and cannot be mistaken for a gap in the grid.
HOLLOW_EDGE = "#CCCCCC"

#: Text/edge and box fill of an in-axes notice saying the panel *cannot* be drawn.
#: Deliberately outside every data series: it is a statement about the figure, not a
#: value in it.
WARNING_TEXT = "#B00020"
WARNING_FILL = "#FDECEC"


def opaque(color, alpha: float, *, over: str = SURFACE) -> str:
    """The flat colour a translucent *color* resolves to when composited over *over*.

    **Why this exists.** Matplotlib's PostScript backend has no transparency: it logs
    "partially transparent artists will be rendered opaque" and writes every ``alpha=``
    artist at full strength. The submitted EPS therefore diverges from the PNG a draft is
    read in and the SVG a deck is built from, at every faint grid rule, band and fill --
    silently, and only in the one file that leaves the repository. Compositing the colour
    here instead gives all three formats the same picture, and it is the *drawn* colour
    that becomes a house decision rather than a rendering accident.

    The arithmetic is the "over" operator on the sRGB values matplotlib is handed, which
    is what the raster backends themselves do -- so a figure converted this way keeps the
    pixels it had. *over* names the ground the artist actually sits on, defaulting to the
    page; a caller drawing over another artist passes that artist's colour instead.

    Args:
        color: Any matplotlib colour specification -- a role from this module, a name,
            a hex string or an RGB(A) tuple.
        alpha: The coverage the artist would have been drawn at, in ``[0, 1]``. ``1``
            returns *color* unchanged and ``0`` returns *over*.
        over: The opaque ground being covered. Defaults to :data:`SURFACE`, the page.

    Returns:
        The composited colour as a hex string, ready to pass as ``color=``.

    Raises:
        ValueError: If *alpha* is outside ``[0, 1]``, which is always a caller bug: a
            coverage outside that range is not a colour matplotlib would ever have drawn.
    """
    import matplotlib.colors as mcolors

    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must lie in [0, 1], got {alpha!r}")
    source = mcolors.to_rgb(color)
    ground = mcolors.to_rgb(over)
    return mcolors.to_hex(
        tuple(alpha * s + (1.0 - alpha) * g for s, g in zip(source, ground))
    )


def heatmap_cmap(name: str = HEATMAP_CMAP, *, missing: str = MISSING_COLOR):
    """A private copy of colormap *name* with ``set_bad`` at *missing*.

    Copied because ``set_bad`` mutates, and matplotlib's registry hands out the
    *same* object to every caller -- mutating it in place would repaint the missing
    cells of every other figure drawn in the same process.

    *name* is a parameter rather than a constant read so a chart that must depart from
    the house ramp -- the significance grids do, on :data:`SIGNIFICANCE_CMAP` -- still
    routes through one ``set_bad`` policy; callers wanting the house ramp pass nothing.
    """
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(name).copy()
    cmap.set_bad(color=missing)
    return cmap


def heatmap_levels(n: int, *, name: str = HEATMAP_CMAP, missing: str = MISSING_COLOR):
    """Colormap *name* reduced to *n* discrete steps, with ``set_bad`` at *missing*.

    For a quantity that arrives already **binned into ordered tiers** -- a significance
    ladder, a banded rate -- rather than as a continuous magnitude. Sampling the ramp at
    *n* points instead of drawing it continuously is what makes a tier boundary visible:
    on a continuous ramp two values either side of a cutoff are painted almost the same
    colour, which invites reading the pair as near-identical when the figure's own claim
    is that they fall on opposite sides of a threshold.

    **Ordered quantities only.** This is a bin of a sequential ramp, so its steps inherit
    that ramp's meaning: step *k+1* reads as *more* than step *k*. It is
    therefore not a source of categorical hues -- a set of unordered categories drawn on
    it acquires a magnitude ordering it does not have. :data:`CATEGORICAL_SERIES` and its
    siblings above exist for that case.

    **``set_bad`` is preserved**, which is load-bearing rather than incidental:
    :func:`~population_synthetic.analysis.utils.grids.render_grid` derives the colour of
    an annotation over an unpainted cell from the colormap's bad colour and *raises* when
    that colour is transparent. ``resampled`` carries the bad/under/over entries across in
    the matplotlib versions this repository runs on; the entry is reapplied here anyway
    so the guarantee is this function's own rather than a borrowed implementation detail.
    Reapplying is safe because ``heatmap_cmap`` already handed back a private copy.

    Args:
        n: Number of discrete steps. The caller pairs it with its own norm -- typically a
            ``BoundaryNorm`` over *n* bins whose cutoffs come from that figure's config.
        name: Colormap to bin. Defaults to the house ramp; the significance grids pass
            :data:`SIGNIFICANCE_CMAP` instead.
        missing: Fill for a cell the ramp did not paint.

    Returns:
        A ``ListedColormap`` with ``N == n``, independent of matplotlib's registry.

    Raises:
        ValueError: If *n* is not a positive integer. A non-positive or fractional step
            count is always a caller bug, and matplotlib would answer it with an empty or
            silently rounded colormap rather than an error.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"heatmap_levels needs a positive integer step count, got {n!r}")
    levels = heatmap_cmap(name, missing=missing).resampled(n)
    levels.set_bad(color=missing)
    return levels


#: Relative-luminance crossover between white and black text, from WCAG 2 contrast:
#: white gives ``1.05 / (L + 0.05)`` and black gives ``(L + 0.05) / 0.05``, so the two
#: are equal where ``(L + 0.05) ** 2 == 1.05 * 0.05``. Solving gives this value. Below
#: it white wins, above it black wins -- and picking the winner is exactly the point,
#: because the loser can fall under the 4.5:1 AA floor while the winner does not.
_TEXT_CONTRAST_CROSSOVER = 0.17912878474779202


def _linearize_srgb_channel(channel: float) -> float:
    """One gamma-encoded sRGB channel in [0, 1] to its linear-light value.

    The sRGB transfer function (IEC 61966-2-1, and the identical definition in WCAG 2):
    a short linear segment near black, a 2.4-power curve above it.
    """
    if not 0.0 <= channel <= 1.0:
        raise ValueError(
            f"sRGB channel out of range: {channel!r}. Channels must be floats in [0, 1] "
            "-- matplotlib colormaps and 'matplotlib.colors.to_rgb' both produce that "
            "scale; a 0-255 value has not been converted."
        )
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb) -> float:
    """WCAG 2 relative luminance of gamma-encoded sRGB *rgb*.

    Linearises each channel and weights the result with the BT.709 primaries
    (0.2126 / 0.7152 / 0.0722). Both halves matter and both were previously wrong here:
    applying luma weights to *gamma-encoded* values overstates the luminance of dark
    colours, and BT.601's weights describe a different set of primaries than sRGB uses.

    Any alpha channel is ignored -- the caller has already resolved what was painted.
    """
    r, g, b = (_linearize_srgb_channel(float(rgb[i])) for i in range(3))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def text_color_for_rgb(rgb) -> str:
    """``"white"`` or ``"black"`` -- whichever reads on a fill of colour *rgb*.

    Implements the WCAG 2 contrast model: sRGB channels are linearised, weighted into a
    relative luminance by the BT.709 coefficients, and compared against the crossover at
    which white and black text give equal contrast ratios
    (:data:`_TEXT_CONTRAST_CROSSOVER`, ~0.179).

    Relative luminance rather than the raw value, because the eye is far more sensitive
    to green than to blue: an unweighted mean calls a saturated blue light and a
    saturated yellow dark, which is backwards for both.
    """
    return "white" if relative_luminance(rgb) < _TEXT_CONTRAST_CROSSOVER else "black"


def text_color_on(im, value: float) -> str:
    """Annotation colour for *value* as the mappable *im* actually paints it.

    Resolves the colour through ``im``'s own cmap and norm rather than through the
    caller's idea of the range, so a chart that later changes its ``vmin``/``vmax``,
    its normalisation or its ramp cannot end up with annotations tuned to the old
    one. Works unchanged on a diverging ramp, should one return: those are dark at
    both ends and pale at the centre, which luminance reads with no special case
    where a "dark above a threshold" rule needs an explicit second branch.

    *value* must be finite -- a masked or NaN cell has no ramp colour, and callers
    annotate those with their own explicit "not measured" wording.
    """
    return text_color_for_rgb(im.cmap(im.norm(value)))

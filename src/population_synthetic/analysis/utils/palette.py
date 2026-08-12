"""palette.py -- The shared colour vocabulary for every analysis-layer heatmap.

One definition of the house ramp, so the grids scattered across ``03_Analysis/``
(fidelity, model_ranking, generation_metadata, realism_ranking) read as one figure
family rather than as four unrelated ones. Before this module each chart module
named its own colormap at its own ``imshow`` call, and the same quantity -- a
model x method mean -- was drawn on viridis in one folder and on Reds in another.

**The ramp is sequential, and every heatmap in the layer now uses it** -- including the
two whose quantity is genuinely two-sided (``realism_ranking``'s typicality statistic,
read against the real population's own value, and ``method_significance``'s trend slope,
read against zero). Those two previously used diverging ramps, and unifying them has a
real cost that their renderers must pay back explicitly: a sequential ramp orders cells
by **magnitude alone**, so two values equally far above and below the reference are drawn
differently and neither drawing says which side it was on.

Both renderers therefore carry the side in the annotations instead of in the hue -- a
signed number in every cell plus a rule across the colourbar at the reference -- and say
so in a printed caption. A future two-sided heatmap must do the same or keep its own
diverging ramp; what it must not do is adopt this ramp and leave the sign implicit,
because the resulting figure looks complete while having silently dropped half its
content.

Annotation colour is *derived*, never chosen: :func:`text_color_on` asks the
mappable what colour it actually painted the cell and picks white or black by that
colour's relative luminance. A hand-tuned "white above 60% of the range" threshold
is a property of one ramp's luminance profile, and silently produces unreadable
text when the ramp changes -- inferno is bright at its top end where Reds is dark,
so the two want opposite rules.
"""

from __future__ import annotations

#: The house sequential heatmap ramp. ``inferno`` because the manuscript fidelity
#: tables (``{country}_models_table``) already publish on it, and those are the
#: figures that leave the repository; matching them makes the internal grids read
#: as drafts of the published ones rather than as a separate visual language. It is
#: perceptually uniform and monotone in lightness, so the annotated numbers stay
#: legible at both ends once :func:`text_color_on` picks their colour.
HEATMAP_CMAP = "inferno"

#: Fill for a cell with no value at all. Deliberately off-ramp: rendering an
#: unmeasured cell at the ramp's low end would present "never measured" as "measured
#: and lowest", which is the most damaging misreading a grid can produce.
MISSING_COLOR = "#DDDDDD"


def heatmap_cmap(name: str = HEATMAP_CMAP, *, missing: str = MISSING_COLOR):
    """A private copy of colormap *name* with ``set_bad`` at *missing*.

    Copied because ``set_bad`` mutates, and matplotlib's registry hands out the
    *same* object to every caller -- mutating it in place would repaint the missing
    cells of every other figure drawn in the same process.

    *name* is a parameter rather than a constant read so a chart that must depart from
    the house ramp still routes through one ``set_bad`` policy; callers wanting the
    house ramp pass nothing, which is all of them today.
    """
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(name).copy()
    cmap.set_bad(color=missing)
    return cmap


def text_color_for_rgb(rgb) -> str:
    """``"white"`` or ``"black"`` -- whichever reads on a fill of colour *rgb*.

    Relative luminance (ITU-R BT.601 weights), not the raw value: the eye is far
    more sensitive to green than to blue, so an unweighted mean calls a saturated
    blue light and a saturated yellow dark, which is backwards for both.
    """
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if luminance < 0.5 else "black"


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

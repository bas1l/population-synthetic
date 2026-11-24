"""Figure 2: A) the 13 reference tables by level (hand-drawn, reused unchanged);
B) the reference population's attribute distributions (re-sampled 2026-10-04).

Panel A is taken pixel-for-pixel from the docx artwork (600 dpi export of
F01-F02_reference_population_01.svg; byte-identical to the staged
F01-F02_reference_category_proportions_01.png) and embedded as an image. Panel B is
redrawn in vector from real_population_stats/<country>/<attribute>.csv on the docx's
hand-made layout: 14 mini bar charts, 0-50 % scale with dashed 25/50 rules (taller bars
overflow the scale as in the docx), hand-shortened tick labels, pale pink panel ground.
456 x 400.248 pt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from PIL import Image

import common
from population_synthetic.analysis.utils.palette import BASELINE_DARK, CATEGORICAL_SERIES, MUTED_GREY, NEUTRAL_GREY, opaque
from population_synthetic.analysis.utils.style import (
    AXIS_TITLE, FIGURE_TITLE, HEADING_WEIGHT, PANEL_TITLE, TICK_LABEL, TICK_LABEL_LARGE,
)

W, H = 456.0, 400.248
PX_PER_PT = 3800 / W
A_CROP_PX = (0, 0, 2468, 936)        # panel A region of the docx export (pink beyond it)
PANEL_GROUND = "#FFFFFF"  # the docx panel-B ground, sampled from the artwork
GROUND_RADIUS = 14.0
BAR = CATEGORICAL_SERIES[0]
BOX_GREY = opaque(NEUTRAL_GREY, 0.245)
SUP = r"2$^{\mathrm{nd}}$"

# Row geometry (points from the top): y of the 0 % line and of the 50 % line.
ROWS = {1: (76.4, 44.0, 27.85), 2: (177.2, 144.8, 129.5), 3: (324.4, 292.1, 277.7)}
# attribute: (row, x0, x1, title, labels, first-in-row)
# labels: list of (bar index or float position, text, rotation, extra) ; "ALL" = one per bar
PANELS = {
    "age_group": (1, 324.9, 385.8, "Age\ngroup", "ALL", True),
    "biological_sex": (1, 394.9, 454.5, "Biological\nsex", "ALL", False),
    "education_level": (2, 20.5, 81.4, "Education\nlevel", [
        (0, f"Pre-{SUP} < 9"), (1, "9-10"), (2, f"Upper {SUP} ≤ 2"), (3, "3"),
        (4, f"Post-{SUP} < 3"), (5, "3+"), (6, "Post-Graduate"), (7, "Unknown")], True),
    "employment_status": (2, 92.3, 153.2, "Employment\nstatus", "ALL", False),
    "socioeconomic_class": (2, 173.7, 234.4, "Socioeconomic\nclass", "ALL", False),
    "parental_structure": (2, 253.0, 314.2, "Parental\nstructure", [
        (0, "Natural Parents"), (1, "Mother & Stepparent"), (2, "Father & Stepparent"),
        (3, "Single Mother"), (4, "Single Father"), (5, "Other Than Parents")], False),
    "region": (2, 324.9, 385.8, "\nRegion", [(0, "Stockholm"), (6.5, "Västra\nGötaland"), ("dots", "..."), (-1, "Gotland")], False),
    "civil_status": (2, 394.9, 454.5, "Civil\nstatus", [
        (0, "Never Married"), (1, "Married"), (2, "Divorced"), (3, "Widowed")], False),
    "industry_sector": (3, 21.2, 81.4, "Industry\nsector", [(0, "Agriculture"), ("dots", "..."), (-1, "Not Applicable")], True),
    "employment_type": (3, 93.7, 155.0, "Employment\ntype", [(0, "Permanent Full-time"), ("dots", "..."), (-1, "Not Applicable")], False),
    "housing_tenure": (3, 171.0, 232.6, "Housing\ntenure", [
        (0, "Owner-occupied\nhouse"), (1, "Tenant-owned\napartment"), (2, "Rental")], False),
    "household_size": (3, 244.6, 306.0, "Household\nsize", "HOUSEHOLD", False),
    "income_source": (3, 314.0, 389.0, "Income\nsource", [
        (0, "Wage"), (1, "Capital"), (2, "Pension"), (3, "Insurance"), (4, "Social Assist."),
        (5, "Activity Comp."), (6, "General Allow."), (7, "Housing Allow.")], False),
    "birth_country_detail": (3, 394.9, 454.5, "Birth\ncountry", [(0, "Sweden"), ("dots", "..."), (-1, "China")], False),
}
# The raw categories each hand label stands for, in CSV order (fail loudly on drift).
EXPECTED_FIRST_LAST = {
    "education_level": ("Pre-Secondary < 9 yrs (ISCED 1)", "Unknown / Not reported", 8),
    "parental_structure": ("Natural Parents", "Other Than Parents", 6),
    "region": ("Stockholm", "Gotland", 21),
    "civil_status": ("Single/Never Married", "Widowed", 4),
    "industry_sector": ("Agriculture, Forestry & Fishing", "Not Applicable", 13),
    "employment_type": ("Permanent Full-time", "Not Applicable", 10),
    "housing_tenure": ("Owner-occupied (villa/house)", "Rental apartment", 3),
    "household_size": ("1 person", "7+ persons", 7),
    "income_source": ("Wage / Business", "Housing Allowance", 8),
    "birth_country_detail": ("Sweden", "China", 21),
}
INCOME_ORDER = ["Wage / Business", "Capital", "Pension", "Insurance / Allowance", "Social Assistance",
                "Sickness / Activity Compensation", "General Allowances", "Housing Allowance"]
TICK_GAP = 2.0
PERCENT_X = {1: 309.0, 2: 5.0, 3: 5.0}  # centre of the rotated "Percent" label
# Title nudges (points, +x right) where a bar taller than the 50 % scale would cross the title.
TITLE_NUDGE = {"parental_structure": 4.5}


def load(attr):
    d = pd.read_csv(common.adir("real_population_stats") / common.COUNTRY / f"{attr}.csv")
    if d["total"].nunique() != 1 or int(d["total"].iloc[0]) != 10000:
        raise ValueError(f"{attr}: expected one total of 10,000 individuals")
    if attr in EXPECTED_FIRST_LAST:
        first, last, n = EXPECTED_FIRST_LAST[attr]
        if (d["value"].iloc[0], d["value"].iloc[-1], len(d)) != (first, last, n):
            raise ValueError(f"{attr}: categories changed: {d['value'].tolist()}")
    if attr == "income_source" and d["value"].tolist() != INCOME_ORDER:
        raise ValueError(f"income_source categories changed: {d['value'].tolist()}")
    return d


def draw(fig, *, ox=0.0, oy=0.0, cw=W, ch=H, with_a=True, letters=True):
    def frac(x, y_top):
        return (ox + x) / cw, 1 - (oy + y_top) / ch

    ground = fig.add_axes((0, 0, 1, 1), zorder=-10)
    ground.set_axis_off()
    ground.set_xlim(0, cw)
    ground.set_ylim(ch, 0)
    ground.add_patch(FancyBboxPatch((0.3, 0.3), cw - 0.6, ch - 0.6, boxstyle=f"round,pad=0,rounding_size={GROUND_RADIUS}",
                                    facecolor=PANEL_GROUND, edgecolor="none"))
    if with_a:
        a = Image.open(common.DOCX_IMAGES / common.PANEL_A_IMAGE).convert("RGB").crop(A_CROP_PX)
        aw, ah = A_CROP_PX[2] / PX_PER_PT, A_CROP_PX[3] / PX_PER_PT
        ground.imshow(np.asarray(a), extent=(0, aw, ah, 0), interpolation="none", zorder=2)
        ground.set_xlim(0, cw)
        ground.set_ylim(ch, 0)
    if letters:
        fig.text(*frac(297.5, 0.8), "b",
                  fontsize=FIGURE_TITLE + 0, fontweight=HEADING_WEIGHT, ha="left", va="top",
                 color="black")

    axes = {}
    for attr, (row, x0, x1, title, labels, first) in PANELS.items():
        y0, y50, ty = ROWS[row]
        d = load(attr)
        n = len(d)
        pct = d["percent"].to_numpy(float)
        fx0, fy0 = frac(x0, y0)
        fx1, fy1 = frac(x1, y50)
        ax = fig.add_axes((fx0, fy0, fx1 - fx0, fy1 - fy0))
        ax.set_facecolor("none")
        ax.bar(np.arange(n), pct, width=0.8 if n < 15 else 0.6, color=BAR, clip_on=False, zorder=3)
        ax.set_xlim(-0.6, n - 0.4)
        ax.set_ylim(0, 50)
        for v in (25, 50):
            ax.axhline(v, color=MUTED_GREY, linewidth=0.8, linestyle=(0, (3.5, 2.5)), zorder=1)
        ax.axhline(0, color="black", linewidth=1.2, zorder=4)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        if first:
            ax.set_yticks([0, 25, 50])
            ax.tick_params(axis="y", labelsize=TICK_LABEL, length=2.0, width=0.8, pad=0.6)
            fig.text(*frac(PERCENT_X[row], (y0 + y50) / 2), "Percent", fontsize=AXIS_TITLE, rotation=90,
                     ha="center", va="center", color="black")
        else:
            ax.set_yticks([])
        xc = (x0 + x1) / 2 + TITLE_NUDGE.get(attr, 0.0)
        fig.text(*frac(xc, ty), title, fontsize=PANEL_TITLE, fontweight=HEADING_WEIGHT, ha="center", va="center",
                 linespacing=1.25, color="black")

        def tick(pos, text, rotation=90, **kw):
            ax.annotate(text, xy=(pos, 0), xycoords=("data", "axes fraction"), xytext=(0, -TICK_GAP),
                        textcoords="offset points", rotation=rotation, ha="center", va="top",
                        fontsize=TICK_LABEL, rotation_mode="anchor" if rotation == 0 else "default",
                        annotation_clip=False, **kw)

        if labels == "ALL":
            for i, v in enumerate(d["value"]):
                tick(i, v)
        elif labels == "HOUSEHOLD":
            for i, v in enumerate(d["value"]):
                tick(i, v.split(" ")[0], rotation=0, )
            ax.annotate("person(s)", xy=((n - 1) / 2, 0), xycoords=("data", "axes fraction"), xytext=(0, -12.5),
                        textcoords="offset points", ha="center", va="top", fontsize=TICK_LABEL, annotation_clip=False)
        else:
            for pos, text in labels:
                if pos == "dots":
                    tick((n - 1) / 2, text, rotation=0)
                else:
                    tick(n - 1 if pos == -1 else pos, text, linespacing=0.85)
        if attr == "education_level":
            for lo in (0, 4):  # grey bands pairing the two sub-levels of a level
                band_depth = 45.6 / (y0 - y50)  # 45.6 pt below the axis, as in the docx
                ax.add_patch(Rectangle((lo - 0.5, -band_depth), 2, band_depth - 0.03,
                                       transform=ax.get_xaxis_transform(), facecolor=BOX_GREY,
                                       edgecolor="none", clip_on=False, zorder=0))
        axes[attr] = ax
    return axes


def main():
    jobs = (("fig2", dict(with_a=True)), ("fig2B", dict(with_a=False, letters=False)))
    for stem, kw in jobs:
        with plt.rc_context(common.rc()):
            fig = plt.figure(figsize=(W / 72, H / 72))
            draw(fig, **kw)
            out = common.save(fig, stem)
        print(out[0])
    # Panel A alone: the reused docx pixels, written unchanged in the same three formats.
    a = Image.open(common.DOCX_IMAGES / common.PANEL_A_IMAGE).convert("RGB").crop(A_CROP_PX)
    with plt.rc_context(common.rc()):
        aw, ah = A_CROP_PX[2] / PX_PER_PT, A_CROP_PX[3] / PX_PER_PT
        fig = plt.figure(figsize=(aw / 72, ah / 72))
        ax = fig.add_axes((0, 0, 1, 1))
        ax.imshow(np.asarray(a), interpolation="none", aspect="auto")
        ax.set_axis_off()
        print(common.save(fig, "fig2A")[0])


if __name__ == "__main__":
    main()

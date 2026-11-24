# Plan: Pair-grid significance ramp and editable SVG text

**Date:** 2026-09-16
**Author:** Basil
**Status:** Completed
**Completed:** 2026-09-16 18:42
**Base Branch:** `feature/figure-selection-04-figures`
**Branch:** `feature/method-pair-significance-grids`

> Retrospective record. Both changes were made as follow-ups on the method-pair-significance
> branch after its planned tasks were done, and are recorded here so each has a plan of its own.

---

## Overview

Two follow-ups to the method × method pair-significance grids: the two `method_significance`
significance grids now bin a dedicated single-hue ramp instead of the house `inferno`, and every
SVG the layer writes carries real, editable `<text>` nodes instead of glyph outlines.

## Problem Statement

1. **A tier is not a magnitude.** The pair squares and the reference-method gap grid paint a
   significance tier: one rung of a ladder the config declares. The rungs are ranked, but the
   distance between two is not a number. Binned onto `inferno`, adjacent tiers differ in hue
   (purple, red, orange, yellow), which invites reading them as kinds rather than degrees.
2. **The SVG had no text.** matplotlib's default `svg.fonttype = 'path'` writes every glyph as an
   outline. The SVG is the format a figure is edited in, and a heatmap's labels reached Inkscape as
   about 1700 anonymous shapes that cannot be retyped.

## Goals

### In Scope
- `palette.SIGNIFICANCE_CMAP = "Blues_r"`, used by both significance grids through
  `heatmap_levels(n, name=SIGNIFICANCE_CMAP)`.
- `svg.fonttype: "none"` in `style.house_rc_params()`, pinned on write through
  `figures.EXPORT_RC_KEYS`.
- Tests and figure-convention docs for both.

### Out of Scope
- Any other heatmap. Every magnitude grid stays on `HEATMAP_CMAP`.
- Embedding the font in the SVG. matplotlib no longer offers an embedding mode.

## Technical Design

### Significance ramp
- `Blues_r` is a single hue, so brightness alone carries the ordering. It is reversed, so the
  darkest step is the most significant rung (`****`) and the palest is `ns`.
- The palest painted step (`#f7fbff`) stays clearly lighter than `MISSING_COLOR` (`#DDDDDD`),
  because "never tested" and "tested, not significant" are different findings the grids paint
  differently. `Greys_r` was rejected because one of its steps lands on that grey.
- Annotation colour needs no change: `palette.text_color_on` picks white or black from the painted
  colour's WCAG relative luminance.

### Editable SVG text
- `svg.fonttype: "none"` writes `<text>` nodes that name the font family. The face is referenced,
  not embedded, so a host without any font in `FONT_STACK` substitutes one with different metrics.
  This is accepted: the SVG is the working copy, and the EPS stays the submission file with its
  embedded face.
- Adding the key to `EXPORT_RC_KEYS` applies it on the driver path too, where a figure is saved
  outside `apply_house_style`.

## Files Changed

| File | Change |
|------|--------|
| `src/population_synthetic/analysis/utils/palette.py` | `SIGNIFICANCE_CMAP`, docstrings for the one sanctioned departure |
| `src/population_synthetic/analysis/method_significance/charts.py` | both grid call sites pass `name=SIGNIFICANCE_CMAP` |
| `src/population_synthetic/analysis/utils/style.py` | `svg.fonttype: "none"` in `house_rc_params()` |
| `src/population_synthetic/analysis/utils/figures.py` | `svg.fonttype` added to `EXPORT_RC_KEYS` |
| `tests/test_palette.py` | ramp is single hue, darkens towards the most significant rung, clears `MISSING_COLOR` |
| `tests/test_method_significance_charts.py` | both grids paint on the ramp; darkening; single hue; cell text legible at both ends |
| `tests/test_figures.py` | SVG keeps its text as text when saved outside the style |
| `docs/development/figure-conventions.md` | "One ramp" narrowed to magnitudes; new "A tier is not a magnitude" section; four-state table updated |
| `docs/architecture/sub-packages.md` | `SIGNIFICANCE_CMAP` in the palette entry |

## Testing

`pytest tests/test_palette.py tests/test_figures.py tests/test_style.py
tests/test_method_significance_charts.py tests/test_method_comparison.py
tests/test_stats_tests_significance.py` on a clean worktree of the committed branch: 194 passed.
`ruff check src/`: clean.

## Decisions

- Blues_r over the house ramp for significance tiers only, because a tier is an ordinal grade.
  Any other departure from `HEATMAP_CMAP` still needs its own justification.
- An SVG with a referenced font instead of glyph outlines. Editable text matters more in the working
  copy than exact metrics on a host without the font.

## Rollback

Revert the two commits. No data, config or output-contract changes are involved.

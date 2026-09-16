# Plan: Reference-Method Gain Forest

**Date:** 2026-09-16
**Author:** Basil
**Status:** Completed
**Completed:** 2026-09-16 18:48
**Base Branch:** `feature/method-pair-significance-grids`
**Branch:** `feature/method-gain-forest`
**Sequencing:** branch only after the uncommitted work on the base branch is committed (see
*Risks*, first row).

---

## Overview

Promote a validated scratch prototype into the `method_significance` analysis process: a **forest
figure** of what the reference method gains over each simpler method, per analysed attribute.

For every attribute on the x-axis (the canonical scheme order) it draws one marker per simpler
method — on the live Swedish v2 axis, E−A, E−B, E−C and E−D — at the mean over complete models of
the per-model paired difference in TV-similarity, with the 95 % t confidence interval of that mean
as a vertical bar. The marker is filled when the Holm-corrected paired t-test is significant and
open otherwise, and the significance symbol is printed vertically directly above the bar. A text
track above the plot carries each attribute's repeated-measures ANOVA F, partial η² and BH p.

The figure shows **attributes only**. There is no Overall column, no separating rule and no Overall
track entry. The builder's existing `overall` panel is untouched and remains available to the
figures that already draw it.

**Fixed layout (settled on the prototype, 2026-09-16).** The canvas is exactly **456 × 150 pt**
(± 1 pt) in all three written formats, with every text at 8 pt. The graphic carries **no title, no
method key, no explanatory caption and no significance key**; those live in the manuscript caption.
Inside the graphic, top to bottom: a one-row legend (`E minus A` … `E minus D`); the three ANOVA
track rows (`F(4, 36)`, `Partial η²`, `BH p`) at tight line pitch; the plot with y label `E − method`
and y ticks 0 to 0.6; x labels (attribute display names) broken onto two lines and written
vertically (90°, centred on the tick). Vertical labels reach further down than the 45° labels of the
V1b prototype, so the plot area is shorter (about 51 pt against 64 pt); that is the approved layout.

Provenance: the prototype is `v1b_forest_stars.py`, fed by `compute.py`, `prep.py` and `figures.py`
in the session scratchpad `e_gain_mockups/`, rendered as `V1b_E-gain-forest-stars.png`; the approved
reference is its vertical-label variant `v1c_forest_stars_vertical_x.py`, rendered as
`V1c_E-gain-forest-stars-vertical-x.png`. The scratch folder is session-temporary; nothing in this
plan depends on it surviving.

## Problem Statement

The reference-method gap grid (`plot_reference_method_gap`) answers the same question — what does
the most complex method buy, and where — but as a tier fill plus a printed number. It shows neither
the **uncertainty** of a gain nor its **magnitude on a common axis**, so a reader cannot see that the
E−D gain on Housing tenure is large but imprecise while the one on Birth country is small and tight.
A forest plot shows both.

Four things block copying the prototype into `src/`:

1. **The confidence interval is not in the data block.** Every other number the prototype draws
   (mean difference, dz, raw and Holm p, wins, F, p, BH p, partial η²) already matches
   `03_Analysis/method_significance/swedish_02_method_comparison.json` to 1e-6. The interval and the
   standard deviation of the differences are the only new statistics, and the prototype computes
   them in its own script — in a chart module that would break *Presentation computes nothing*.
2. **The Birth-country caveat is hand-written.** The prototype's key says "methods A to D assign
   every individual to Sweden". That sentence is a claim authored in a chart, which the
   caveat-is-data rule forbids, and it is also incomplete: the live data has a second case the
   prototype never mentions (see *Technical Design → Research findings*).
3. **It sets 8 pt and the canvas as literals** (`FS = 8.0`, `W_PT, H_PT = 456.0, 150.0`, plus point
   offsets), bypassing the style layer's type scale and canvas vocabulary.
4. **It saves outside `save_figure`.** The house writer renders with `bbox_inches="tight"`; the
   two-line, rotated tick labels have text layout boxes wider than their ink, so the tight crop
   grew the output to 156 pt high. The prototype therefore wrote the three formats with its own
   `savefig` loop (`save_canvas`), which in `src/` would be a second `savefig` call site and would
   skip the budget checks.

## Goals

### In Scope

1. The builder emits, for every tested method pair, `sd_diff`, `ci_low`, `ci_high` at a
   config-declared confidence level, oriented in `pair_matrix` exactly like `mean_diff`.
2. The builder detects, per panel, groups of methods whose per-model TV-similarity columns are
   identical, and carries them plus a caveat clause as data.
3. A new renderer `charts.py::plot_reference_method_gain_forest` drawing the fixed layout above:
   attributes only, all text at the house 8 pt size, a 456 × 150 pt canvas, no in-graphic title, key
   or caption.
4. A fixed-canvas save mode in `utils/figures.py::save_figure` that writes the figure at its own size
   without the tight crop, still enforcing every budget on write.
5. Wiring into `scripts/analyze/analyze_method_significance.py`; docs. No roster entry in
   `config/analysis/figure_selection.yaml`: a figure enters that roster only when Basil lists it.

### Out of Scope

- The Overall column and its track values (removed by decision on 2026-09-16).
- The mechanism / mode-collapse figure (prototype `V3_mechanism`).
- The attribute-structure statistics (collapse TV, noise floor, entropy, correlations — `prep.py`).
- The grid variant of the gain figure (prototype `V2_E-gain-grid`).
- The Word results draft (`build_docx.py`).
- New columns in `{country}_method_comparison.csv`.
- Other countries beyond what the process already generalises to (it is country-agnostic; no
  country-specific code is added).

## Success Criteria

- [x] On the live `swedish_02` run, every pre-existing field of `{country}_method_comparison.json`
      (per-attribute `mean_diff`, `dz`, `p_raw`, `p_holm`, `wins`, omnibus F, p, `p_bh`,
      `partial_eta_sq`) is unchanged from the stored file to 1e-6 after a `--force` rerun.
- [x] `ci_low`/`ci_high`/`sd_diff` agree with an independent `scipy.stats.t.interval` /
      `numpy.std(ddof=1)` computation to 1e-12 in a unit test on a synthetic matrix, and with the
      prototype's `e_contrasts_by_attribute.csv` to 1e-9 in a one-off check recorded in the PR.
- [x] A test collects every visible, non-empty `Text` artist of the drawn figure and asserts the set
      of font sizes is exactly `{style.FONT_FLOOR_PT}`.
- [x] A test asserts the written PNG (pixels ÷ `RASTER_DPI` × 72), SVG (`width`/`height`) and EPS
      (`%%HiResBoundingBox`) canvases are each 456 × 150 pt ± 1 pt.
- [x] `save_figure` in fixed-canvas mode writes exactly the figure's size, rejects (writing nothing)
      a figure whose ink reaches past the canvas edge, and keeps the canvas and file-size checks;
      the default tight mode is byte-for-byte unchanged for existing callers.
- [x] `src/` still holds exactly one `savefig` call site.
- [x] The drawn figure contains no title, no `caption_block` text and no method or star key; its
      only texts are the legend, the track, the significance labels, the axis label and the tick labels.
- [x] A test asserts, for every significance label, the horizontal distance between the rendered ink
      centre and its marker x is within the label-centring tolerance defined below.
- [x] The identical-comparator caveat is detected generically: a builder test on a synthetic matrix
      with two identical columns yields exactly that group; on the live rerun the JSON carries groups
      for Birth country and Parental structure and for no other attribute; no attribute or country
      name appears in `charts.py` or `builder.py` for it.
- [x] No two significance labels' ink boxes overlap, none overlaps a CI bar or marker, and every
      label's ink lies inside the plot frame (asserted on the live-shape fixture).
- [x] `ruff check src/` clean; `pytest` green.

## Definitions

- **Complete model** — a model with a non-`None` TV-similarity under every compared method on that
  attribute (`builder._complete_case_matrix`). Only complete models enter the panel's tests.
- **Reference method** — the last entry of `metadata["method_order"]`, the most complex method under
  the config-resolved complexity order. On the live axis it is E,
  `all_generate_evaluate_random_pick_v2`. Derived, never named in code.
- **Comparator** — every other method on the axis, in complexity order.
- **Gain** — for a comparator *c* on an attribute: the mean over complete models of
  `tv_similarity(reference) − tv_similarity(c)`, i.e. `pair_matrix["mean_diff"][ref][c]`.
- **Confidence interval of the gain** — `mean ± t_{(1+L)/2, n−1} · sd_diff / √n`, where *L* is the
  config `confidence_level` and `sd_diff` the sample standard deviation (ddof 1) of the per-model
  differences. `None` when `sd_diff` is 0 (t undefined).
- **Holm family** — all `k(k−1)/2` method pairs of the attribute whose paired t is defined; a pair
  whose differences are all identical has `p_raw = None` and is left out of the family. This is the
  family `paired_t_pairwise` already corrects over and the one the pair squares and the gap grid
  print. On the live axis it has 10 members, except Parental structure (9) and Birth country (4).
- **Identical-method group** — a maximal set of ≥ 2 methods whose complete-case TV-similarity
  columns are bit-identical (`numpy.array_equal`) on that panel.
- **Identical-comparator caveat** — the statement, for an attribute whose panel carries at least one
  identical-method group, that those contrasts coincide. Its wording comes from the data block. With
  no caption in the graphic it is not drawn; it travels in the JSON and is printed by the script for
  whoever writes the manuscript caption.
- **Fixed canvas** — a written figure whose extent is the `Figure`'s own size, not the tight
  bounding box of its artists.
- **Label-centring tolerance** — 0.5 pt (≈ 2.1 px at `RASTER_DPI` 300) between the horizontal centre
  of a label's rendered ink (pixels of the label's hue inside its box) and the marker's x.

## Technical Design

### Research findings

- **Reference-method mechanism.** `plot_reference_method_gap` takes `method_order[-1]` from the
  result metadata; `method_order` is `strategy_complexity_order` over the strategies present, which
  reads `_families.yaml`. No config key names E. The forest reuses exactly this, through a helper
  extracted from the gap grid (below). No new method id appears anywhere.
- **Holm.** `stats_tests.paired_t_pairwise` corrects over every defined pair; `_method_panel` stores
  it as `pairwise_detail` and orients it in `pair_matrix`. The forest reads `p_holm[ref][c]`, so its
  family is by construction the pair squares' family. `_p_to_stars(None)` returns `ns`, which would
  present an undefined test as a non-significant one; the forest must branch on `None` first.
- **Identical columns in the live data.** The stored JSON shows Birth country with A, B, C, D all
  identical per model (six identical pairs, Holm family of 4) **and Parental structure with A and B
  identical** (one pair, family of 9). The prototype's caveat named only Birth country. A generic
  detector will print both, which is correct and is a visible change from the prototype.
- **The "why" of a caveat is not derivable here.** "A to D assign every individual to Sweden" needs
  the mapped populations; the builder only sees `ComboPerformance`. The generic caveat can state the
  fact (identical TV-similarity, coinciding contrasts, pairs leaving the family), not the cause.
- **Type scale.** `style.py` has no role for an 8 pt title or axis title: `FIGURE_TITLE` is 12,
  `PANEL_TITLE` 11, `AXIS_TITLE` 10. The 8 pt roles are `TICK_LABEL`, `LEGEND_LABEL`, `ANNOTATION`,
  all equal to `FONT_FLOOR_PT`. "All text 8 pt" therefore needs a style-layer decision.
- **Canvas.** 456 pt appears nowhere in the repository. `save_figure` enforces `FULL` (19.05 cm =
  540 pt); `DOUBLE` is 17.4 cm = 493 pt. The 456 pt manuscript text width is a manuscript rule.
- **Tight crop.** `figures._render` always passes `bbox_inches="tight"`, `pad_inches=PAD_INCHES`, and
  `_canvas_inches` measures the EPS bounding box that crop produced. Matplotlib sizes that box from
  text *layout* boxes; a rotated multi-line label's layout box is wider than its glyphs, so the crop
  grows a figure whose ink sits inside the canvas (150 → 156 pt here). There is no option today to
  write the canvas as drawn.
- **Method key in the graphic.** `figure-conventions.md` (*Generation methods render as A–E, with
  the key in the graphic*) states that PLOS and Springer require the key in the graphic and that "a
  figure that prints letters without printing the key is incomplete". The fixed layout prints letters
  in its legend and moves the key to the caption, which contradicts that rule. This plan does not
  resolve it; see *Decisions required*.
- **Schema.** Neither `{country}_method_significance.json` nor `{country}_method_comparison.json`
  carries a schema version. No code reads either file back: charts consume the in-memory result, and
  the only references are the script, `commands.md` and a plan. `tests/test_method_comparison.py`
  asserts panel keys as a superset (`>=`). Adding keys is therefore non-breaking and needs no version
  bump — the precedent is `pair_matrix`, added the same way. Stored files predate the new keys, so
  the renderer raises on their absence and the country must be re-run with `--force` (the script
  skips a country whose JSON exists).
- **Data-pipeline checklists (guides 02, 03, 05).** Rendering stays a pure sink; the new statistic is
  tested against a known answer with approximate comparison; the confidence level is config loaded
  once at the edge; zero-variance differences are an explicit absent state, not a degenerate interval;
  every multiplicity family is named; effect magnitude is shown with its interval; and the reference
  derivation is written once (DRY) rather than copied into a second renderer.

### Approach

The statistic lives where the paired difference is already computed — `paired_t_pairwise`, called
only by `builder._method_panel` — and is oriented by `builder._pair_matrices`, the sign convention's
one home. The chart reads the `(reference, comparator)` index pair, the same read the gap grid does.

### Alternatives Considered

| Option | Verdict | Reason |
|--------|---------|--------|
| Compute the CI in the chart from `per_model` | Rejected | Violates *Presentation computes nothing*. |
| A separate CI helper in `builder.py` recomputing the difference vector | Rejected | Two homes for one paired difference; `paired_t_pairwise` already holds `diff` and `sd`, and has one caller. |
| Extend `paired_t_pairwise` with `sd_diff`/`ci_low`/`ci_high`, called from the builder | **Chosen** | One computation, upstream of the chart, serialised with its siblings. Deviates from "in `builder.py`" literally; see *Decisions*. |
| Holm over only the four reference contrasts | Rejected | Would disagree with the pair squares and gap grid in the same folder, and would make the family a rendering choice — the objection `paired_t_pairwise`'s docstring records. |
| Add the gain as a `GridVariant` of the gap grid | Rejected | A variant is an annotation difference over one grid; a forest is a different figure. |
| Hardcode the caveat per attribute | Rejected | Caveat-is-data rule; also missed Parental structure. |
| Tolerance-based identity (`allclose`) | Rejected | Introduces a threshold nobody configured; the degenerate case is bit-identical by construction (same category counts give the same TV). |
| Confidence level as a literal 0.95 | Rejected | Config is the single source of truth; `comparison.json` already owns the star ladder. |
| Chart calls `savefig` itself without the crop (the prototype's `save_canvas`) | Rejected | Second `savefig` site; skips the canvas and file-size checks on write. |
| Shrink the axes until the tight crop lands at 150 pt | Rejected | The overshoot is layout-box slack, not ink; compensating for it wastes 6 pt of a 150 pt canvas and changes with label text. |
| A `fixed_canvas` keyword on `save_figure` | **Chosen** | One writer, one call site, budgets still checked on the rendered bytes; opt-in, so every existing figure is untouched. |

### Architecture & Module Contracts

| Module | Owns | Must NOT know about |
|--------|------|--------------------|
| `config/analysis/method_significance/comparison.json` | `confidence_level` (new, required, 0 < L < 1) beside `star_thresholds` | matplotlib, countries, method ids |
| `utils/stats_tests.py::paired_t_pairwise(blocks, *, labels, confidence_level)` | per pair `sd_diff`, `ci_low`, `ci_high` (second minus first); `None` interval when `sd == 0` | figures, reference method, orientation beyond its key order |
| `method_significance/builder.py` | `load_comparison_config` validation of `confidence_level`; `_pair_matrices` orients `ci_low`/`ci_high` (row-minus-column: cell `(i, j)` = `[−hi, −lo]` of the stored record) and mirrors `sd_diff`; `_identical_method_groups(matrix, methods) -> list[list[str]]`; panel keys `identical_method_groups`, `correction.family_size`; block keys `confidence_level`, `identical_methods_note` | labels, letters, fonts, which figure reads it |
| `method_significance/charts.py` | `_reference_axis(metadata) -> tuple[str, list[str]] | None` (extracted from `plot_reference_method_gap`, which then calls it); `plot_reference_method_gain_forest(result, out_path) -> Path | None`; private label placement | how a CI or group is computed; any attribute, country or method id literal |
| `utils/style.py` | the 8 pt role, the 456 pt width and the 150 pt height as named constants (see *Decisions*) | this figure |
| `utils/figures.py::save_figure(fig, png_path, *, dpi=RASTER_DPI, fixed_canvas=False)` | with `fixed_canvas=True`: `_render` passes `bbox_inches=None`; `_check_canvas` still runs on the EPS box (now the figure size); new `_check_ink_inside_canvas(png_bytes, png_path)` decodes the rendered PNG and raises `FigureBudgetExceeded` when non-background pixels touch any edge row/column (ink clipped); nothing is written on any failure | which figure asked, data, labels |
| `scripts/analyze/analyze_method_significance.py` | calling the renderer, printing written/skipped | statistics, layout |
| tests | builder numbers vs scipy; chart invariants | the scratch prototype |

**Renderer behaviour, precisely.**

- Columns: `metadata["attributes"]` filtered to present panels, in that order. `overall` is never a
  column. Positions `0..n−1`; comparator offsets are symmetric about each position, derived from
  the comparator count.
- For comparator *c*: `mean_diff`, `ci_low`, `ci_high`, `p_holm` read at `[ref][c]` of the panel's
  `pair_matrix`. Filled marker iff `p_holm ≤ significance_cutoff(star_thresholds)`; label
  `_p_to_stars(p_holm, …)`. If `p_holm is None`: open marker, no bar, no label, and the attribute
  falls under the caveat line. A pair carrying `p_holm` but no `ci_low` raises (same guard as the
  gap grid's missing difference).
- Hue per comparator from `palette.ORDERED_QUALITATIVE_SERIES` by comparator index, plus a private
  marker-shape ladder so series separate without hue. Open markers fill with `palette.SURFACE`; no
  `alpha=`. If the comparator count exceeds either ladder (a mixed-version axis gives 9), the
  function logs a WARNING naming the count and returns `None`, as the gap grid returns empty on a
  degenerate axis.
- Labels: `rotation=90`, anchored at the CI top, offset by the glyph **ink** centre measured with
  `matplotlib.textpath.TextPath` (the text bbox of `*` is lopsided), then moved **vertically only** to
  clear already-placed labels and other bars/markers. The prototype's fixed-point iteration is kept:
  the y upper limit is solved so the highest label ink sits a small fixed gap under the frame, and
  the plot's bottom edge is solved from the measured x tick-label ink so the lowest glyph clears the
  canvas edge. Convergence is bounded; non-convergence raises rather than overlapping or clipping.
- Layout in points on the fixed 456 × 150 pt canvas: legend row, then the track axes, then the plot.
  The point margins (left gutter for track row names and y ticks, legend row height, track pitch,
  label gap) are private named constants in `charts.py` beside the renderer, not literals at use sites.
- Legend: one row, `ncol` = comparator count, entries `"{ref letter} minus {letter}"` from
  `method_letters(method_order)`.
- Track axes above the plot: rows `F(df1, df2)`, `Partial η²`, `BH p`, read from each panel's
  `omnibus`. The row header prints the df only when every column shares them; otherwise the header
  is the bare test statistic name and each cell prints its own df. The test name comes from
  `_omnibus_test_label`, raising on mixed tests as the gap grid does. An `insufficient_n` panel keeps
  its column, draws no markers, prints the absent mark in the track and is logged with its note.
- Axes: y label `"{ref letter} − method"`; y ticks from a `MaxNLocator` over non-negative data range
  (0, 0.2, 0.4, 0.6 on the live data — not a literal list); x tick labels `attribute_label(attr)`
  broken at the first space onto two lines, rotated 90°, centred on the tick, `va="top"`.
- **No** title, `caption_block`, method key, star key or caveat line. The identical-method groups and
  their note stay in the JSON; the script prints one line per affected attribute
  (`attribute: methods … <note>`) so the caption author sees them.
- Saved with `save_figure(fig, out_path, fixed_canvas=True)`. All sizes from the 8 pt style role;
  canvas from the named width and height constants.

## Implementation Plan

### Phase 1: The interval and the identical-method groups (builder)

- [x] `config/analysis/method_significance/comparison.json`: add `"confidence_level": 0.95` and
      describe it in `description`.
- [x] `builder.py::load_comparison_config`: require a float strictly inside (0, 1); raise otherwise.
- [x] `utils/stats_tests.py::paired_t_pairwise`: add keyword-only `confidence_level` (no default);
      emit `sd_diff` always, `ci_low`/`ci_high` via `stats.t.ppf((1 + L) / 2, n − 1)` or `None` when
      `sd == 0`. Update the docstring's return shape.
- [x] `builder.py::_method_panel`: pass the level; add `identical_method_groups` from new
      `_identical_method_groups(matrix, methods)` (empty list for a degenerate panel); add
      `correction["family_size"]` = count of pairs with non-`None` `p_holm`.
- [x] `builder.py::_pair_matrices`: add oriented `ci_low`, `ci_high` and mirrored `sd_diff`; extend
      the docstring's convention paragraph (the convention's only home).
- [x] `builder.py::_method_comparison`: thread the level; echo `confidence_level` and a fixed
      `identical_methods_note` clause in the block (the clause is data authored in the builder, the
      precedent being `_CAVEATS`).
- [x] Tests: `tests/test_stats_tests_significance.py` (interval vs `scipy.stats.t.interval`, zero-sd
      pair), `tests/test_method_comparison.py` (orientation of CI in `pair_matrix`, group detection,
      family size 10/9/4-style shrinkage, config validation).

### Phase 2: Style and writer seams

- [x] `utils/style.py`: add the width constant (proposed `TEXT_WIDTH = 456 / POINTS_PER_INCH`, beside
      `SINGLE`/`DOUBLE`/`FULL`, documented as the manuscript text width), the strip height (proposed
      `STRIP_HEIGHT = 150 / POINTS_PER_INCH`) and the 8 pt role chosen in *Decisions*; register any
      new size in `FONT_SCALE`.
- [x] `tests/test_style.py`: pin the new constants (`TEXT_WIDTH < DOUBLE < FULL`; role == floor).
- [x] `utils/figures.py`: add keyword-only `fixed_canvas: bool = False` to `save_figure`; thread it
      into `_render` (`bbox_inches=None` when set, unchanged otherwise); add
      `_check_ink_inside_canvas`, run only in fixed mode, before any write; document the mode in the
      module and function docstrings (why: layout-box slack of rotated multi-line text).
- [x] `tests/test_figures.py`: fixed mode writes the figure size exactly in PNG/SVG/EPS; a figure
      with a rotated two-line tick label that tight mode grows is written unchanged in fixed mode; an
      artist drawn past the edge raises `FigureBudgetExceeded` and leaves no file; a figure larger
      than `FULL` still raises; tight mode output is unchanged for an existing fixture.

### Phase 3: The renderer

- [x] `charts.py`: extract `_reference_axis(metadata)` and switch `plot_reference_method_gap` to it
      (behaviour-preserving; its tests must pass unchanged).
- [x] `charts.py`: add `plot_reference_method_gain_forest(result, out_path) -> Path | None`, private
      `_ink_centre_offset(text, fontsize)` and `_place_vertical_labels(...)`, marker ladder constant;
      update the module docstring's figure list.
- [x] `tests/_method_significance_fixtures.py`: a builder for the new block fields (CI, groups,
      family size, note), on `LIVE_ATTRIBUTES` and `FIVE_METHODS`.
- [x] `tests/test_method_significance_charts.py`: tests listed under *Testing Plan*.

### Phase 4: Wiring, roster, docs

- [x] `scripts/analyze/analyze_method_significance.py`: call the renderer after the gap grid, write
      `{country}_reference_method_gain_forest.png/.svg/.eps`; print the identical-method caveat lines
      read from the block; add it to the module docstring's output list. No new CLI flag; registry
      unchanged (same process, same folder).
- [ ] ~~Optional, on Basil's call: `config/analysis/figure_selection.yaml` entry~~ (not added: Basil
      lists roster entries himself)
      `source: "method_significance/{country}_reference_method_gain_forest"` with an `n` he assigns,
      and the hardcoded 23 in `tests/test_figure_selection.py` moved accordingly.
- [x] Docs per *Documentation Plan*.
- [x] Rerun `python scripts/analyze/analyze_method_significance.py --countries swedish_02 --force`;
      run the stored-JSON and prototype-CSV comparisons; inspect the PNG against the prototype.

## Testing Plan

### Unit Tests

- `paired_t_pairwise`: interval equals `scipy.stats.t.interval(L, n−1, loc=mean, scale=sd/√n)`;
  `sd_diff` equals `np.std(ddof=1)`; all-identical differences give `sd_diff == 0`, `ci_* is None`,
  `p_holm is None` and exclusion from the family; missing `confidence_level` is a `TypeError`.
- `load_comparison_config`: absent, non-numeric, 0, 1 and 1.2 all raise.
- `_pair_matrices`: `ci_low[i][j] == −ci_high[j][i]`; `sd_diff` symmetric; diagonal `None`.
- `_identical_method_groups`: two identical columns → one group; three → one group of three; none →
  `[]`; order follows `methods`.
- Renderer:
  - writes PNG + SVG + EPS; returns `None` when no panels or a single-method axis;
  - no `Overall` tick, no `overall` column even when the block holds that panel;
  - every visible text size == `style.FONT_FLOOR_PT`;
  - PNG, SVG and EPS canvases 456 × 150 pt ± 1 pt at the live 14-attribute shape;
  - no title, caption, method key or star key text; legend has one row with one entry per comparator;
  - x tick labels are two lines at 90°;
  - label ink-centre within 0.5 pt of marker x (pixel scan of the rendered buffer, independent of the
    placement code);
  - label ink boxes do not overlap each other, bars or markers, and lie inside the plot frame;
  - filled vs open follows the config cutoff, including a p exactly on it;
  - a `None` p draws an open marker and no label (never `ns`);
  - no caveat text is drawn even when the block carries identical-method groups;
  - the reference follows `method_order[-1]` at two axes with different last families;
  - more comparators than the hue ladder → `None` plus a WARNING;
  - `insufficient_n` column kept, logged, absent mark in the track;
  - missing `ci_low` on a tested pair raises.

### Integration Tests

- `build_method_significance` on the existing synthetic records fixture, then the renderer, end to
  end (extends `test_all_charts_write_files`).

### Manual Verification

- `--force` rerun on `swedish_02`; diff old vs new JSON on pre-existing keys (≤ 1e-6); compare new
  interval fields with the prototype CSV (≤ 1e-9); open the PNG beside `V1c_E-gain-forest-stars-vertical-x.png`
  — expected: same layout at 456 × 150 pt; the script prints caveat lines for Parental structure and
  Birth country.

### Edge Cases

Zero-variance comparator contrast; reference identical to a comparator; a panel with a dropped
model (non-uniform df); `insufficient_n` panel; mixed-version axis; single attribute.

## Documentation Plan

- `docs/architecture/sub-packages.md` — `method_significance` paragraph: the gain forest, the
  interval fields and the identical-method groups.
- `docs/development/figure-conventions.md` — new section after the reference-method gap grid:
  vertical, ink-centred significance labels that move only vertically; open vs filled vs
  undefined-test markers; why the forest reuses the ten-pair Holm family; a caption-free figure whose
  caveats travel as data for the manuscript caption. Also: the new width/height constants in the
  publication-constraints table; the fixed-canvas mode under *Budgets are checked on the written
  bytes* (when to use it, and that ink past the edge is rejected); and whatever the method-key
  decision yields in *Generation methods render as A–E, with the key in the graphic*.
- `docs/architecture/commands.md` — the method-significance output list (no CLI change).
- `CLAUDE.md` — no change expected; the presentation-layer membership is unchanged.

## Rollback Plan

All changes are additive. Revert the branch's commits: the new JSON keys disappear, no reader
depends on them, and a `--force` rerun restores the previous files. The `_reference_axis` extraction
is behaviour-preserving and reverts with the rest. If a roster entry was added, remove it and restore
the count in `tests/test_figure_selection.py`.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Uncommitted work on the base branch.** `charts.py`, `utils/figures.py` (`svg.fonttype`), `palette.py` (`SIGNIFICANCE_CMAP`), `style.py`, tests and `figure-conventions.md`/`sub-packages.md` are modified but uncommitted. Branching now either carries them into this feature or leaves them behind. | High | High | Commit (or finish) the `method-pair-significance-grids` work first, then branch. This plan edits the same files — `charts.py` (different functions), the same `sub-packages.md` paragraph, and the section of `figure-conventions.md` right after the one being rewritten — so textual conflicts are likely if the order is reversed. |
| Interaction with the pending `transposed-reference-centred-grids` plan | Low | Low | That plan targets `realism_ranking`/`validation_attrition`/`model_ranking` and the `### One ramp` text, lands after the grids branch merges, and draws no forest. Overlap is limited to `sub-packages.md` (it fixes the "seven modules" count) and possibly `figure_selection.yaml` numbering; whichever lands second rebases the doc lines. |
| Label collisions on other data (wider CIs, more significant stars) push the y limit so high the data squashes | Med | Med | Bounded growth that raises; test on a fixture with maximal-length labels on the tallest bars. |
| House tight crop grows the fixed canvas (rotated two-line tick labels' layout boxes: 150 → 156 pt at 45°) | Certain without the fix | High | `fixed_canvas` mode in `save_figure` plus `_check_ink_inside_canvas`; tests on all three formats. |
| Fixed mode hides real clipping that the tight crop used to absorb by growing | Med | Med | The ink-at-edge check rejects it and writes nothing; the renderer solves its bottom margin from measured tick-label ink. |
| Fixed-mode edits to `figures.py` regress existing figures | Low | High | Keyword-only, default off; a test pins tight-mode output for an existing fixture. `figures.py` is also in the uncommitted base-branch diff, so commit that first. |
| A 150 pt strip cannot fit the labels on other data (taller CIs, longer attribute names) | Med | Med | Layout solve raises on non-convergence or clipping rather than shrinking type below 8 pt. |
| Method key moved to the caption contradicts the in-graphic key rule | Certain | Med | Explicit user decision below; docs follow the decision. |
| 8 pt everywhere conflicts with the house type scale (title 12, axis title 10) | High | Med | Resolved by the style decision below, never by a literal; the font-size test pins the outcome. |
| Stale JSON on disk lacks the new keys | High | Low | Renderer raises naming the missing key and `--force`; the script's idempotent skip is called out in the PR. |
| Generic caveat wording is less informative than the prototype's "everyone assigned to Sweden" | Certain | Low | The caption author adds the cause; the script output gives the fact. The mechanism analysis is out of scope. |
| The interval assumes normal differences at n = 10 | Med | Low | Same assumption as the stored paired t; `p_sign` already travels beside it. The key names the interval as a t interval. |

## Decisions (settled 2026-09-16 on the approved V1c mock-up)

1. **Where the interval is computed.** `paired_t_pairwise`, called from the builder.
2. **The 8 pt role.** Option (a): a documented style role, `style.STRIP_AXIS_TITLE`, equal to
   `FONT_FLOOR_PT` and registered in `FONT_SCALE`.
3. **The 456 × 150 pt canvas.** Named constants `style.TEXT_WIDTH` and `style.STRIP_HEIGHT`; written
   in the `fixed_canvas` mode with no tight crop. `save_figure` still enforces `FULL`/`MAX_HEIGHT`.
4. **Method key in the graphic.** Option (a): the key is in the manuscript caption, recorded in
   `figure-conventions.md` as an exception for this figure only, with its reason (a 150 pt-tall
   canvas). The rule is unchanged for every other figure.
5. **Significance key.** Also in the caption, under the same exception; no title either.
6. **Roster.** Not added. A figure enters `figure_selection.yaml` only when Basil lists it.
7. **Caveat wording.** Adapted from the V1c results draft, where the attribute-specific sentence
   read "give identical TV-similarity in every model, so the contrasts E minus A and E minus B are
   identical". The generic builder clause, prefixed by the group's methods when printed: "give
   identical TV-similarity in every complete model, so their contrasts with any other method are
   identical and the pairs among them have no t statistic".
8. **Tick labels.** Vertical (90°), two lines, as in V1c. There is no Overall column.

## Timeline

| Phase | Estimate |
|-------|----------|
| 1 — Builder interval and groups | 0.5 day |
| 2 — Style and writer seams | 0.5 day |
| 3 — Renderer and tests | 1–1.5 days |
| 4 — Wiring, rerun, docs | 0.5 day |

## References

- `src/population_synthetic/analysis/method_significance/builder.py` — `_method_panel`,
  `_pair_matrices`, `_method_comparison`, `load_comparison_config`
- `src/population_synthetic/analysis/method_significance/charts.py` — `plot_reference_method_gap`,
  `_reference_gap_grid`, `_p_to_stars`, `_star_key_text`, `_omnibus_test_label`
- `src/population_synthetic/analysis/utils/stats_tests.py` — `paired_t_pairwise`
- `src/population_synthetic/analysis/utils/style.py`, `palette.py`, `labels.py`, `figures.py`
- `scripts/analyze/analyze_method_significance.py`
- `config/analysis/method_significance/comparison.json`, `config/analysis/figure_selection.yaml`
- `docs/development/figure-conventions.md`, `docs/architecture/design-principles.md`,
  `docs/architecture/sub-packages.md`
- `docs/development/plans/active/method-pair-significance-grids.md`,
  `docs/development/plans/pending/transposed-reference-centred-grids.md`
- `~/.claude/knowledge/data-pipeline-engineering/` guides 02, 03, 05 (review checklists)
- Stored data: `<project-data>/02_Data/03_Analysis/method_significance/swedish_02_method_comparison.json`

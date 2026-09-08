# Plan: Per-attribute method × method pairwise-significance grids

**Date:** 2026-09-08
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/figure-selection-04-figures`
**Branch:** `feature/method-pair-significance-grids`

---

## Overview

Add one square **method × method** significance grid per analysed attribute to the
`method_significance` analysis process. Each cell reports the pairwise comparison of two
generation methods on that attribute: its fill is the significance tier (the same star
ladder the existing bracket figure uses) and its printed text is the signed
row-minus-column difference in TV similarity. The statistics already exist in
`method_significance/builder.py`; this plan adds the rendering, the one builder field that
makes the square orientable without arithmetic in the renderer, and the discrete colour
level helper the presentation layer does not yet have.

## Problem Statement

`plot_method_comparison` today draws the pairwise results as significance **brackets** over
a bar panel. With five methods there are ten pairs, and the config's default `pairs_mode`
is `vs-most-complex` — so only the four "most complex method vs each simpler one" brackets
are drawn. The remaining six comparisons are computed, Holm-corrected, serialised to JSON
and CSV, and then never shown. Reading them today means opening
`{country}_method_comparison.json` by hand.

A square matrix shows all `k(k-1)/2` comparisons at once, per attribute, at a glance —
which method pairs separate, on which demographic axis, and by how much. That is the
question "does the generation method matter, and where?" in its most direct visual form,
and it is currently unanswerable from any published figure.

## Goals

### In Scope

1. One grid figure per analysed attribute, plus one for the pooled `overall` panel, written
   into `03_Analysis/method_significance/` alongside the existing charts.
2. Cell fill = the significance tier of the Holm-corrected paired t-test p-value, binned on
   the `star_thresholds` already declared in `config/analysis/method_significance/comparison.json`.
3. Cell text = the signed row-minus-column ΔTV similarity, so direction is legible without
   a diverging ramp.
4. Two published variants per attribute, per the layer's existing grid-variant contract: a
   canonical `clean` variant and a `with_counts` sibling that adds each pair's block count.
5. A named discrete-level helper in `palette.py`, since no chart module may name or bin a
   ramp at its own `imshow` call site.
6. A new annotation policy in `grid_annotations.py` that declares the keys it reads.
7. Full house-style compliance: three output formats, print budgets, font floor, no `alpha=`.

### Out of Scope

- **Any new statistic.** No new test, no new correction, no new effect size. The one builder
  change (§ Technical Design) re-serialises values the builder already computed; it derives
  nothing new.
- **A new analysis process or registry entry.** Rejected precedent: `model-method-tv-heatmap.md`
  ("a process per figure does not scale").
- **A diverging colormap.** Rejected by ADR `2026-08-12-self-contained-typicality-axis.md`;
  introducing one would require an ADR superseding it.
- **Changing the existing bracket figure.** `plot_method_comparison` and its `pairs_mode`
  config are untouched.
- **The across-model mean ± SD of method-vs-reference deltas** that this feature was
  originally scoped as. The grid reduces the models to a p-value and a mean difference; it
  does not show their spread. If the spread is wanted it is a separate figure and a separate
  plan.
- **The Nemenyi rank-based p-values.** They stay in the artifact under
  `pairwise_p_nemenyi`; the grid draws the value-based headline only.

## Success Criteria

- [x] Running `python scripts/analyze/analyze_method_significance.py` for Sweden emits
      `2 × (14 + 1) = 30` figure stems × 3 formats = 90 files under
      `03_Analysis/method_significance/{country}_method_pair_significance/`.
- [x] Every emitted EPS passes `figures.save_figure`'s canvas and file-size budgets without
      a `FigureBudgetExceeded`.
- [x] A cell whose pair was never tested renders visibly distinct from a cell whose pair
      tested non-significant, and both are distinct from the blanked diagonal.
- [x] An attribute panel flagged `insufficient_n` renders a labelled placeholder, not a blank
      or a missing file, and logs a warning.
- [x] The method key (`labels.method_key_lines`) is drawn inside the graphic, not deferred to
      a caption.
- [x] `grep -n "alpha=" src/population_synthetic/analysis/method_significance/charts.py`
      returns no artist call.
- [x] `pytest tests/` passes, including new tests for the policy, the palette helper, and the
      variant substitutability of the new grid family.
- [x] Both variants of at least one attribute are rendered and visually inspected.

## Definitions

- **Method pair cell `(i, j)`**: the comparison of the method on row `i` against the method on
  column `j`, for one attribute. Its *significance* is symmetric (`p(i,j) == p(j,i)`); its
  *difference* is antisymmetric (`Δ(i,j) == −Δ(j,i)`). The grid draws both channels, which is
  why colour is symmetric and text is not.
- **Signed ΔTV**: `mean_TV_similarity(row method) − mean_TV_similarity(column method)`, over
  the complete-case models that entered that attribute's test. Positive means the **row**
  method scored closer to the real population.
- **"Not tested"**: a pair for which the builder stored no `p_holm` — because the attribute
  panel was degenerate (`n < 2` models or `k < 2` methods), or the pair itself carried too few
  paired blocks. It is rendered as an **unpainted** cell (the colormap's `set_bad` fill), which
  is a different visual state from the palest painted tier (`ns`). Collapsing "not tested" into
  "not significant" is a correctness failure, not a cosmetic one.
- **Blanked diagonal**: `values[i, i] = np.nan` **and** `cells[i][i] = None`. The fill is the
  same `set_bad` grey as "not tested", but the diagonal carries no annotation at all, whereas a
  "not tested" off-diagonal cell prints its `absent_text`. The two are distinguished by text,
  and the in-figure key says so.
- **Star tier**: one of the five states `****`, `***`, `**`, `*`, `ns`, resolved from
  `star_thresholds` in `config/analysis/method_significance/comparison.json` by the existing
  `charts._p_to_stars`. Five tiers ⇒ five discrete colour levels.
- **Chart-only**: the renderer computes no statistic. This plan is *almost* chart-only; the one
  exception is § "The one builder change", which is a re-serialisation, not a computation.

---

## Technical Design

### Approach

The grid is a pure consumer of `result["method_comparison"]["panels"][<attribute|"overall">]`,
which already carries everything except one thing: an **orientation**.

`builder._pair_key(a, b)` stores each unordered pair once, under a single ordering
(`"all_pick|all_pick_dag"`). `pairwise_detail[key]["mean_diff"]` is therefore signed with
respect to *that* ordering only. Filling a square matrix from it means negating the stored
value for every mirrored cell — arithmetic in the renderer, on a signed quantity, which is
exactly the "smuggled computation" the pipeline guides flag and which the presentation
boundary forbids.

The fix is upstream and small: `_method_panel` additionally serialises the oriented `k × k`
matrices it already has in hand. The renderer then reads cell `(i, j)` directly and performs
no arithmetic at all.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Builder serialises the oriented `k × k` p and Δ matrices; renderer reads cell `(i,j)` verbatim | Renderer computes nothing; the JSON is self-describing; sign convention has exactly one home | Touches `builder.py`, so not literally chart-only; the artifact grows by `k²` floats per panel | **Chosen** |
| Renderer negates `mean_diff` for mirrored cells | Truly chart-only | Puts a sign convention in the presentation layer, where a future edit can silently invert half the figure; violates "presentation computes nothing" | Rejected |
| Draw only the lower triangle | No orientation needed at all | Halves the information the user asked for; a triangle reads worse than a square; still needs the diagonal convention | Rejected |
| Diverging colormap on signed ΔTV, stars as text | Direction in the hue, which is the intuitive encoding | Explicitly rejected by ADR 2026-08-12; breaks consistency with the published manuscript tables | Rejected |
| Continuous `Normalize` on raw p (or −log10 p) rather than discrete tiers | No new palette helper needed | Colour then does not correspond to the star ladder, which is the thing asked for; and a continuous p ramp invites reading a p of 0.049 as meaningfully different from 0.051 | Rejected |
| One faceted sheet of all attribute panels instead of one file per attribute | One figure to publish, one roster entry | 15 panels of a 5×5 matrix on one printable canvas is illegible; overflows `MAX_HEIGHT` | Rejected |
| `statannotations` for the star rendering | Off-the-shelf | New dependency, seaborn-coupled, unmaintained; already rejected in `method-comparison-significance-figures.md` | Rejected |

### The one builder change

In `_method_panel`, after `paired = paired_t_pairwise(matrix, labels=methods)`, serialise two
oriented matrices alongside the existing pair map:

```python
# Oriented k x k views of the pair map, so a square-matrix renderer reads cell (i, j)
# directly instead of negating a stored difference for the mirrored half. The sign
# convention (row minus column) then has exactly one home: here.
"pair_matrix": {
    "methods": list(methods),          # index order for both matrices
    "p_holm": [[float | None, ...], ...],   # symmetric; None on the diagonal and untested
    "mean_diff": [[float | None, ...], ...],# antisymmetric; row minus column
    "n_blocks": [[int | None, ...], ...],   # per-pair paired-block count
    "dz": [[float | None, ...], ...],       # antisymmetric, same convention
},
```

Degenerate panels (`n < 2` or `k < 2`) emit `pair_matrix` with `methods` populated and every
matrix entry `None`, so the key is always present and the renderer never branches on absence.

This adds no test, no correction, and no derived quantity — every value is already in
`paired["pairs"]`.

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `method_significance/builder.py::_method_panel` | Also serialise the oriented `k × k` views of the pair map it already computed | `matrix`, `methods` → `panel["pair_matrix"]` | matplotlib, colours, figures, filenames |
| `analysis/utils/palette.py::heatmap_levels(n)` | Return an `n`-step discrete copy of the house ramp, `set_bad` preserved | `n: int` → `ListedColormap` | p-values, stars, statistics, what the levels mean |
| `analysis/utils/grid_annotations.py::SignedValueWithStarsPolicy` | Decide the **text** of a cell that carries a signed value, a symbol, and optionally a count | cell record → `str | None` | colour, extent, which cells are drawn, matplotlib |
| `method_significance/charts.py::plot_method_pair_significance` | Draw one grid per attribute panel from stored numbers; write via the one writer | `result`, `out_dir` → `list[Path]` | how a p-value was computed, what a correction is, file formats, country paths |
| `scripts/analyze/analyze_method_significance.py` | Call the new plotter inside the existing `if not args.no_charts:` block and report the paths | `result`, `significance_dir` → stdout + files | matplotlib, cell records |
| `config/analysis/figure_selection.yaml` | Record which of the emitted stems a human chose to publish | — | — |

**Colour construction.** The five star tiers map to five discrete levels via
`palette.heatmap_levels(5)` plus a `matplotlib.colors.BoundaryNorm` whose boundaries are the
config `max_p` cutoffs (`[0, 1e-4, 1e-3, 1e-2, 5e-2, 1.0]`). Boundaries come from config, never
from a literal in the chart. Because `p` ascends left-to-right and `inferno` runs dark→bright,
the most significant tier renders darkest and `ns` palest — no inversion needed. The
`BoundaryNorm`/`ListedColormap` pair flows through `render_grid`'s `cmap=`/`norm=`
pass-throughs untouched; `heatmap_levels` must call `.set_bad(MISSING_COLOR)` or
`grids._missing_text_color` raises.

**Cell record shape** (extra keys are permitted by `_validate_records`; the policy declares
only what it reads):

```python
{"value": <signed ΔTV, float | None>, "stars": "<****|***|**|*|ns>", "n": <int | None>}
```

**The two variants**, following `validation_attrition/charts.py:161-193`:

```python
GRID_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,                                  # "clean", unsuffixed filename
    policy=SignedValueWithStarsPolicy(value_key="value", stars_key="stars"),
    cell_clause="Cell: signed row-minus-column difference in TV similarity, "
                "beneath it the significance symbol for the Holm-corrected paired t-test.",
    fontsize=ANNOTATION_LARGE, linespacing=None,
)
GRID_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,                                    # "_with_counts" suffix
    policy=SignedValueWithStarsPolicy(value_key="value", stars_key="stars", count_key="n"),
    cell_clause="... printed with the number of paired blocks the test used.",
    fontsize=ANNOTATION, linespacing=1.35,
)
GRID_VARIANTS = variant_map(GRID_VARIANT_CLEAN, GRID_VARIANT_WITH_COUNTS)
```

`SignedValueWithStarsPolicy.required_keys` is `{value_key, stars_key}` plus `count_key` when
declared, exactly mirroring how `RateWithCountsPolicy` conditionally extends its own set. It
declares `absent_text` (default `"—"`) so an untested pair prints a mark rather than raising
`MissingCellValue`.

**Draw sequence** (mirrors `plot_slope_heatmap`, `charts.py:214-296`):

```
@house_style
plot_method_pair_significance(result, out_dir) -> list[Path]
  panels     = result["method_comparison"]["panels"]
  order      = [a for a in result["metadata"]["attributes"] if a in panels] + ["overall"]
  thresholds = block["star_thresholds"];  ns_symbol = block["ns_symbol"]
  letters    = labels.method_letters(result["metadata"]["method_order"])
  for each panel, for each variant:
      build values (k x k of p_holm, np.nan where untested), cells (None on the diagonal)
      fig, ax = plt.subplots(figsize=(grow_width(k, ...), grow_height(k, ...)))
      im = render_grid(ax, values, cells, policy=variant.policy,
                       cmap=heatmap_levels(5), norm=BoundaryNorm(boundaries, 5),
                       aspect="equal", interpolation="none",
                       fontsize=variant.fontsize, linespacing=variant.linespacing)
      ticks: letters on both axes (categories_on_top for the columns)
      colourbar: 5 discrete swatches, ticked with the star symbols
      in-figure key: labels.method_key_lines(...) + the star definitions + the sign convention
      title: attribute_label(attr) + the panel's omnibus F/p and n_models
      fig.tight_layout(); fit_to_page(fig); paths.append(save_figure(fig, path))
```

**Output naming.** A directory, as `plot_method_trends` already does:

```
03_Analysis/method_significance/{country}_method_pair_significance/
    {attribute}.png|.svg|.eps                 # canonical "clean" variant, unsuffixed
    {attribute}_with_counts.png|.svg|.eps
    overall.png|.svg|.eps
    overall_with_counts.png|.svg|.eps
```

---

## Implementation Plan

### Phase 1: The oriented pair matrix
**Goal:** The artifact carries an orientable square, so the renderer never does arithmetic.

- [x] 1.1 — Add the `pair_matrix` block to `_method_panel`, built from `paired["pairs"]`.
- [x] 1.2 — Populate the degenerate branch with `methods` + all-`None` matrices, so the key is
      unconditional.
- [x] 1.3 — Document the row-minus-column sign convention in the `_method_panel` docstring, and
      state there that this is the convention's only home.
- [x] 1.4 — Extend `_write_method_comparison_json` coverage if the block needs explicit
      inclusion; confirm the CSV writer is unaffected.

**Files Modified:**
- `src/population_synthetic/analysis/method_significance/builder.py` — `_method_panel` gains
  the `pair_matrix` serialisation.

**Dependencies:** None

### Phase 2: Presentation-layer primitives
**Goal:** Discrete house-ramp levels and a declaring policy exist as named, tested helpers.

- [x] 2.1 — Add `palette.heatmap_levels(n, *, name=HEATMAP_CMAP, missing=MISSING_COLOR)`
      returning `heatmap_cmap(name, missing=missing).resampled(n)`, with a docstring stating
      that it preserves `set_bad` and that binning an *ordered* quantity is its only sanctioned
      use (it is not a categorical-hue source).
- [x] 2.2 — Export it in `palette.__all__`.
- [x] 2.3 — Add `SignedValueWithStarsPolicy` to `grid_annotations.py`, frozen dataclass, with
      `value_key`, `stars_key`, `count_key: str | None = None`, `number_format`, `absent_text`,
      and a `required_keys` property conditional on `count_key`.
- [x] 2.4 — Export it in `grid_annotations.__all__`.

**Files Modified:**
- `src/population_synthetic/analysis/utils/palette.py`
- `src/population_synthetic/analysis/utils/grid_annotations.py`

**Dependencies:** None (parallel with Phase 1)

### Phase 3: The grid renderer
**Goal:** One figure per attribute per variant, house-compliant, budget-clean.

- [x] 3.1 — Declare `GRID_VARIANT_CLEAN` / `GRID_VARIANT_WITH_COUNTS` / `GRID_VARIANTS` in
      `method_significance/charts.py`.
- [x] 3.2 — Implement `plot_method_pair_significance(result, out_dir) -> list[Path]`,
      `@house_style`, matplotlib imported inside the function.
- [x] 3.3 — Blank the diagonal (`np.nan` value **and** `None` cell); render untested
      off-diagonal pairs with the policy's `absent_text` over the `set_bad` fill.
- [x] 3.4 — Render an `insufficient_n` panel as a labelled placeholder with the panel's own
      `note` string read from the block, and log a warning. Never author the wording in the
      chart.
- [x] 3.5 — Build the discrete colourbar, ticked with the star symbols read from config.
- [x] 3.6 — Draw the in-figure key: `method_key_lines`, the star definitions
      (`_star_key_text`), and the sign convention.
- [x] 3.7 — `fit_to_page(fig)` before `save_figure`; confirm no budget breach at `k = 5` and at
      `k = 10` (both strategy versions live).

**Files Modified:**
- `src/population_synthetic/analysis/method_significance/charts.py`

**Dependencies:** Phases 1 and 2

### Phase 4: Wiring, publication, docs
**Goal:** The sweep emits the figures and a human can publish a chosen subset.

- [x] 4.1 — Call the plotter in the `if not args.no_charts:` block of
      `scripts/analyze/analyze_method_significance.py`, printing the directory and file count
      in the style of the existing `plot_method_trends` line.
- [x] 4.2 — Extend the script's module docstring output inventory.
- [x] 4.3 — Add roster entries to `config/analysis/figure_selection.yaml` for the two or three
      attributes actually published (each stem written out literally — there is no attribute
      placeholder, and a pinned literal is deliberate).
- [x] 4.4 — Update `docs/development/figure-conventions.md` (new grid family, its two
      variants, the discrete-level helper), `docs/architecture/commands.md`, and
      `docs/architecture/sub-packages.md`.

**Files Modified:**
- `scripts/analyze/analyze_method_significance.py`
- `config/analysis/figure_selection.yaml`
- `docs/development/figure-conventions.md`, `docs/architecture/commands.md`,
  `docs/architecture/sub-packages.md`

**Dependencies:** Phase 3

### Phase 5: Generate the figures
**Goal:** Real output on the live grid, inspected.

- [x] 5.1 — Run `python scripts/analyze/analyze_method_significance.py` for Sweden.
- [x] 5.2 — Confirm the expected file count and that no `FigureBudgetExceeded` was raised.
- [x] 5.3 — Open one `clean` and one `with_counts` variant and check legibility, key placement,
      and that the untested/diagonal/`ns` states are visually distinguishable.

**Dependencies:** Phase 4

### Phase 6: The reference-method gap grid
**Goal:** One figure summarising the whole run — the most complex method against every
simpler one, on every analysed category at once — so the question "what does the hardest
method buy, and where?" is answerable from a single published graphic instead of from
fifteen squares read side by side.

The squares of Phases 1–5 are per category and show every pair. This is their transpose
and their summary: rows are the non-reference methods in complexity order, columns are the
analysed categories with the pooled `overall` panel last, and each cell is the reference
method's comparison against that row's method inside that column's panel. It is a pure
consumer of the same `pair_matrix` block, adds no statistic, and reads the **other index
pair** of it rather than negating anything.

Two decisions are the family's own and are recorded here:

- **The reference is derived, never named.** `metadata["method_order"][-1]` — the most
  complex method under the config-resolved complexity ordering — labelled by its letter
  and family phrase, so a retired family, an added one, or a live version split re-points
  the figure with no edit and the letters become `A1/A2/…` on their own.
- **The sign is reference minus row**, the opposite orientation from the squares'
  row-minus-column, because the question is what the reference *gains*. The convention
  keeps its single home in `builder._method_panel`; the renderer only chooses which of the
  two stored orders to read. Because two figures in one folder then carry opposite
  orientations, this one's key names its orientation explicitly.
- **The omnibus is per column, not per figure**, so it travels under each column heading
  rather than in the title, and the test that produced it is named once in the key rather
  than fifteen times — the same ink economy the `clean` variant applies to a constant
  count. `_omnibus_note` was split into `_omnibus_test_label` + `_omnibus_p_text` so the
  test name still has exactly one home; `_omnibus_note`'s own output is unchanged.

- [x] 6.1 — Split `_omnibus_note` into `_omnibus_test_label` / `_omnibus_p_text` /
      `_omnibus_note`, preserving the existing output byte for byte.
- [x] 6.2 — Declare `REFERENCE_GRID_VARIANT_CLEAN` / `_WITH_COUNTS` /
      `REFERENCE_GRID_VARIANTS` — a **new** map, not the squares', because this family is
      bound by column width rather than by the dropped line and both its variants
      therefore sit at the house floor size.
- [x] 6.3 — Implement `_reference_gap_grid`: read `pair_matrix` at `(reference, row)`;
      untested comparisons take `np.nan` with an all-`None` record; no diagonal.
- [x] 6.4 — Implement `plot_reference_method_gap(result, out_path) -> list[Path]`,
      `@house_style`, matplotlib imported inside, enumerating `variant_suffixes`.
- [x] 6.5 — An `insufficient_n` category keeps its column, unpainted and marked, and is
      logged with the panel's own `note` — never blanked, never re-worded in the chart.
- [x] 6.6 — In-figure key: method key, star definitions, the cell clause, the
      reference-minus-row convention named explicitly, the column headings' omnibus, and
      what an unpainted cell means.
- [x] 6.7 — Size with `grow_width`/`grow_height` against `FULL`/`MAX_HEIGHT`, then
      `fit_to_page` before `save_figure`; verified at the live 15 × 4 shape and at the
      version-split 15 × 9 one.
- [x] 6.8 — Call it from the `if not args.no_charts:` block of
      `scripts/analyze/analyze_method_significance.py` and extend the script's output
      inventory.
- [x] 6.9 — One roster entry, `n: 28`, `name: reference_method_gap`, for the canonical
      (unsuffixed) stem. 28 is the next free number, taken for the same reason 27 was:
      every number below it is either claimed or is a gap the manuscript's own numbering
      has reserved. Its `as_generated/` basename is `{country}_reference_method_gap`,
      which collides with nothing (the squares' basenames are bare category names).
- [x] 6.10 — Tests in `tests/test_method_significance_charts.py`: the three formats per
      variant and exactly those PNGs returned; the reference resolved from `method_order`
      at two axis widths; the printed sign asserted against the panel's own `means`;
      untested distinct from `ns`; the `insufficient_n` column; the budget at 4 and 9
      rows over the country's own 15-column axis; a single-method axis drawing nothing;
      and a painted tier with no difference raising. The family is also registered in
      `tests/test_grids.py`, so it is held to the layer-wide substitutability rules.
- [x] 6.11 — Docs: the new family and its inverted orientation in
      `figure-conventions.md`, `commands.md` and `sub-packages.md`.
- [x] 6.12 — Generate on the live Swedish axis (`--country swedish_02 --force`) and
      inspect both variants.

**Files Modified:**
- `src/population_synthetic/analysis/method_significance/charts.py`
- `scripts/analyze/analyze_method_significance.py`
- `config/analysis/figure_selection.yaml`
- `tests/_method_significance_fixtures.py`, `tests/test_method_significance_charts.py`,
  `tests/test_grids.py`, `tests/test_figure_selection.py`
- `docs/development/figure-conventions.md`, `docs/architecture/commands.md`,
  `docs/architecture/sub-packages.md`

**Dependencies:** Phases 1–5 (the `pair_matrix` block, the discrete levels, the policy and
the star ladder are all reused unchanged)

---

## Testing Plan

### Unit Tests

- [x] `heatmap_levels(5)` returns a `ListedColormap` with `N == 5` whose `get_bad()` is
      `MISSING_COLOR` and is **not** transparent (the condition `_missing_text_color` raises on).
- [x] `SignedValueWithStarsPolicy.required_keys` is `{"value","stars"}` without `count_key` and
      `{"value","stars","n"}` with it.
- [x] The policy prints the sign explicitly (`"+0.031"`, not `"0.031"`) and returns
      `absent_text` for a `None` value rather than raising.
- [x] A cell record missing `stars` raises `CellRecordMismatch` naming the policy and the
      `(row, column)`.
- [x] `_method_panel` on a synthetic 4-model × 3-method matrix produces a `pair_matrix` whose
      `p_holm` is symmetric, whose `mean_diff` is antisymmetric to within floating point, and
      whose diagonal is all `None`.
- [x] `_method_panel` on a degenerate panel (1 model) still emits `pair_matrix` with populated
      `methods` and all-`None` entries.

### Integration Tests

- [x] `plot_method_pair_significance` on a fixture `result` writes, for each panel and variant,
      all three of `.png`/`.svg`/`.eps`, and returns exactly those PNG paths.
- [x] Variant substitutability, asserted the way `tests/test_grids.py` already does for the
      existing families: both variants share canvas, extent, norm, painted array, ticks and
      marking count; only cell text differs.
- [x] A fixture with one `insufficient_n` panel still emits that panel's files, carrying the
      placeholder text from the block's own `note`.
- [x] An untested pair renders text distinct from an `ns` pair (guards the "distinguish zero
      from absent" failure).

### Manual Verification

- [x] Both variants of `education_level` and of `overall` open cleanly in Inkscape with real
      `<text>` nodes (the SVG-as-editing-artifact contract).
- [x] The in-figure method key matches the axis letters exactly.
- [x] Colourbar swatch boundaries line up with the star symbols.

### Edge Cases

- [x] `k = 2` methods — a 2×2 grid with one real cell per triangle.
- [x] `k = 10` methods (both strategy versions live) — letters render as `A1/A2/…`, and the
      canvas stays inside `FULL × MAX_HEIGHT`.
- [x] An attribute where every pair is `ns` — the grid is uniformly pale but not blank.
- [x] A `p_holm` of exactly a boundary value (`0.05`) — lands in the tier `_p_to_stars` assigns,
      and the `BoundaryNorm` bin agrees with it.

---

## Documentation Plan

- [x] `docs/development/figure-conventions.md` — the new grid family, its two variants, the
      discrete-level helper, and the "not tested ≠ not significant" rule.
- [x] `docs/architecture/commands.md` — the new output under `analyze_method_significance.py`.
- [x] `docs/architecture/sub-packages.md` — `palette.heatmap_levels` in the presentation-layer
      description.
- [ ] `CLAUDE.md` — only if the presentation-layer paragraph needs the discrete-ramp helper
      named; otherwise unchanged.
- [x] Docstrings: `_method_panel` states the sign convention is defined there and nowhere else;
      the chart docstring states the statistical design it draws and that it claims no p-value
      of its own.

---

## Rollback Plan

1. **Before publication:** the feature is purely additive — no existing figure, artifact key or
   CSV column changes. Reverting the branch removes the new files and the `pair_matrix` key.
2. **Data considerations:** `pair_matrix` is an added JSON key; older consumers ignore it and
   no reader requires it. No migration. Previously written
   `{country}_method_comparison.json` files simply lack the key, and re-running the script
   regenerates them.
3. **Rollback procedure:** revert the phase commits in reverse order; delete
   `03_Analysis/method_significance/{country}_method_pair_significance/`; remove the
   `figure_selection.yaml` roster entries (leaving them would make the copier fail on a missing
   source, which is the intended fail-loud behaviour).

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Canvas budget breach — `plot_method_comparison` already overflowed at 19.71 cm | Med | Med | `fit_to_page(fig)` before `save_figure`; size via `grow_width`/`grow_height` with `FULL`/`MAX_HEIGHT` caps; explicit `k = 10` edge-case test |
| `BoundaryNorm` + `ListedColormap` is the first discrete scale in the layer; `_missing_text_color` raises on a transparent `set_bad` | Med | Med | `heatmap_levels` builds from `heatmap_cmap()` (which sets `set_bad`) and `resampled()` preserves it; unit-tested directly |
| A wrong or reversed sign convention silently inverts half of every figure | Low | High | The convention lives only in `_method_panel`; the renderer performs no arithmetic; antisymmetry is unit-tested; the sign is printed in every cell and stated in the in-figure key |
| "Not tested" read as "not significant" | Med | High | Unpainted `set_bad` fill + `absent_text` mark + an explicit line in the in-figure key; integration-tested |
| 30 stems per country is a lot to curate into the publication roster | High | Low | Nothing is auto-discovered; a human lists the two or three published stems, which is the roster's stated philosophy |
| Cell text too dense at 5 lines × 5 columns on `SINGLE` width | Med | Med | The `clean` variant is canonical and drops the count line; `with_counts` is the diagnostic sibling |
| Version split (`A1/A2/…`) makes a 10×10 grid unreadable | Low | Med | Edge-case test at `k = 10`; if it fails the budget, the plan's answer is to publish the `k = 5` single-version run, not to shrink the font below `FONT_FLOOR_PT` |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — oriented pair matrix | ~40 lines, 1 file | None |
| Phase 2 — palette + policy | ~60 lines, 2 files | None (parallel with 1) |
| Phase 3 — the renderer | ~200 lines, 1 file | Phases 1, 2 |
| Phase 4 — wiring, roster, docs | ~40 lines + docs, 5 files | Phase 3 |
| Phase 5 — generate and inspect | run + review | Phase 4 |

---

## References

- Existing machinery: `src/population_synthetic/analysis/method_significance/builder.py::_method_panel`,
  `charts.py::plot_slope_heatmap` (the worked grid example), `charts.py::_p_to_stars`
- Config: `config/analysis/method_significance/comparison.json` (star thresholds, `ns_symbol`)
- Presentation contracts: `analysis/utils/{grids,grid_annotations,grid_variants,palette,style,figures,labels,table_style}.py`
- Related plans: `plans/completed/method-comparison-significance-figures.md`,
  `plans/completed/per-category-method-model-significance.md`,
  `plans/completed/model-method-tv-heatmap.md`,
  `plans/active/publication-figure-presentation-layer.md`,
  `plans/active/figure-selection-04-figures.md`
- ADR: `docs/development/decisions/2026-08-12-self-contained-typicality-axis.md` (one ramp; sign
  travels in the annotation)
- Conventions: `docs/development/figure-conventions.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/analysis/figure_selection.yaml
- docs/architecture/commands.md
- docs/architecture/sub-packages.md
- docs/development/figure-conventions.md
- docs/development/plans/active/method-pair-significance-grids.md
- scripts/analyze/analyze_method_significance.py
- src/population_synthetic/analysis/method_significance/builder.py
- src/population_synthetic/analysis/method_significance/charts.py
- src/population_synthetic/analysis/utils/grid_annotations.py
- src/population_synthetic/analysis/utils/palette.py
- tests/_method_significance_fixtures.py
- tests/test_figure_selection.py
- tests/test_grids.py
- tests/test_method_comparison.py
- tests/test_method_significance_charts.py
- tests/test_palette.py

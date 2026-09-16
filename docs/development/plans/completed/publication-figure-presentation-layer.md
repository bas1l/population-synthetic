# Plan: Publication-Ready Figure Presentation Layer

**Date:** 2026-08-24
**Author:** Basil
**Status:** Completed (with open items)
**Completed:** 2026-09-16 19:04
**Base Branch:** `dev`
**Branch:** `feature/publication-figure-presentation-layer`

---

## Overview

The analysis layer computes and renders in the same place, so every figure decision — colour,
font, size, export format, and what a tick label says — is made independently in ~15 `charts.py`
modules. This plan introduces a **presentation boundary** under `analysis/utils/`: five
single-responsibility collaborators (palette, style, labels, export, heatmap renderer) that every
chart module draws through, so the published figures become visually homogeneous and compliant
with `figure-preparation-standards.docx` by construction rather than by inspection.

## Problem Statement

Six separate symptoms share one cause.

1. **No display-name layer.** Every figure prints raw snake_case ids — `openrouter_kimi_k3`,
   `all_generate_evaluate_random_pick_v2`. The labels *already exist* in config: all 28 model
   YAMLs and all 10 strategy YAMLs carry a `label:` field, read today only by the Qt GUI and by
   `manifest_loader.py:271-274` for run-naming. The analysis layer discards it — all six callers
   of `discover_axis_values()` do `sorted(d["id"] for d in ...)`. The only id transformation
   anywhere in the codebase is `strategy.replace("_", "\n")` (`fidelity/charts.py:614`), which
   stacks `all_generate_evaluate_pick` as five lowercase lines.
2. **No style layer at all.** No `rcParams`, no `.mplstyle`, no font family set anywhere — every
   figure ships in matplotlib's default DejaVu Sans where the standards require Arial.
   `fontsize=` is passed ~310 times across 29 distinct values, including 4.5, 5, 5.6, 6, 6.5 and
   7 — all below the 8 pt hard floor. DPI has three regimes (150 hardcoded, 180 for one radar,
   200 from five CLI defaults), so the same figure family exports at different resolutions
   depending on which process drew it. 58 unconstrained `figsize` call sites. 52 in-function
   `matplotlib.use("Agg")` calls.
3. **Half the figures never emit vector.** All of `fidelity`, most of `method_significance` and
   `model_ranking/charts`, all of `consistency` and `multivariate_fidelity` bypass
   `analysis/utils/figures.py::save_figure` with direct `fig.savefig(..., dpi=150)` and produce
   **PNG only**. There is no EPS or PDF anywhere in the repo — and EPS is the one format all four
   target venues accept.
4. **Categorical colour is copy-pasted.** The 7-tuple `_COLOR_SERIES` is duplicated verbatim in
   five modules (`fidelity/charts.py:52`, `model_ranking/charts.py:58`,
   `multivariate_fidelity/charts.py:23`, `method_significance/charts.py:50`,
   `consistency/charts.py:20`) plus a renamed sixth copy in `generation_metadata/charts.py:45-49`,
   alongside ~25 unnamed inline hex greys. Heatmap colour is the *only* colour that is unified.
5. **F05 has no clean variant.** `validation_attrition/charts.py:352 plot_mapped_validity_grid`
   prints the retention rate and the `clean/generated` counts in every cell at 7.0 pt — below the
   8 pt floor, and too dense for the manuscript.
6. **A shared style module lives in the wrong package.** `model_ranking/table_style.py` is
   imported by `cost_efficiency`, `validation_attrition` and `manuscript_tables`, violating the
   repo's own "cross-subpackage helpers move to `analysis/utils`" rule.

Fixing these one at a time leaves ~15 places for the next drift to appear.

## Goals

### In Scope

1. Five single-responsibility presentation modules under `analysis/utils/`, with every analysis
   `charts.py` drawing through them.
2. A config-driven label resolver: axis ids to display labels read from the existing axis YAMLs,
   failing loudly on an unresolvable id.
3. Camera-ready labelling — spaces not underscores, sentence case with proper nouns preserved,
   API-provider prefixes dropped from axis labels.
4. Generation methods rendered as **A–E**, derived from `_families.yaml` order, with an in-figure key.
5. A generated model-provenance table (model, provider, endpoint, host) so the provenance dropped
   from the axes is preserved for reproducibility.
6. An unannotated variant of F05, produced by an annotation *policy*, not a duplicated function.
7. Compliance with `figure-preparation-standards.docx`: vector EPS alongside SVG and PNG, Arial,
   8–12 pt, strokes above 0.25 pt, RGB, at most 19.05 by 22.23 cm, at most 10 MB.
8. Fix `palette.py::text_color_for_rgb`, which computes luminance incorrectly.

### Out of Scope

- **Any change to the heatmap colormap.** `inferno` stays. No diverging ramp is introduced, and
  `MISSING_COLOR` is unchanged. This is settled by
  `docs/development/decisions/2026-08-12-self-contained-typicality-axis.md`, which rejected a
  diverging ramp in favour of the single sequential house ramp with the sign carried in
  annotations. Revisiting it is a separate plan with its own ADR.
- Recomputing or restating any statistic. This plan changes how figures look, never what they claim.
- Output folder and filename renames — owned by `plans/pending/uniform-analysis-output-naming.md`.
- A shared `03_Analysis` paths/constants module — that plan explicitly declined it; do not smuggle
  it in here.
- Figure alt text. Not required at any of the four target venues; worth doing later.
- LaTeX table output (`manuscript_tables.py::write_*_fidelity_latex`) — different medium, unaffected.

## Success Criteria

- [x] `grep -rn "matplotlib.use\|plt.rcParams\|plt.style.use" src/` matches only `analysis/utils/style.py`.
- [x] `grep -rn "fig.savefig" src/` matches only `analysis/utils/figures.py`.
- [x] Every figure-producing call site emits PNG, SVG and EPS. *(One writer, three formats or
      nothing. Confirmed on the live `swedish_02` reports in task 6.1: every one of the 37
      figures re-rendered there wrote all three, including the nine that Phase 5 could not.)*
- [x] No literal hex colour string outside `analysis/utils/palette.py`. *(And no literal
      named colour either — `model_ranking`'s white column rule was the last one, now the
      `SURFACE` role. The remaining hex literals in `src/` are the Qt GUI's widget colours,
      which are not figures and are not in this layer.)*
- [x] No `fontsize=` numeric literal below 8.0 anywhere in `src/`.
- [x] No axis tick label, legend entry or title in any emitted figure contains an underscore.
      *(Task 6.9. Asserted by `tests/test_figure_compliance.py` over 15 rendered figures, and
      swept over the live report set in 6.1.)*
- [x] No axis label contains `openrouter`, `ollama`, `claude_`, or any other provider token.
      *(The three leaks 6.1 found are fixed at their source; the compliance test now walks
      the whole artist tree of each figure, not just the accessors a chart happens to use.)*
- [x] Method axes render as A–E with an in-figure key.
- [x] The clean F05 and its counted sibling both exist, produced by the same renderer with a
      different annotation policy. *(Superseded on 2026-08-25 by the layer-wide naming rule: the
      clean figure now takes the bare `{country}_mapped_validity_grid.{png,svg,eps}` and the counted
      one is `..._with_counts`. The `_clean` suffix no longer exists — see the Phase 4 revision.)*
- [x] `labels.resolve()` raises on an unknown id; a unit test asserts the raise.
- [x] Every emitted EPS is within 19.05 by 22.23 cm and under 10 MB — asserted by a test.
      *(Enforced on write, not merely asserted: an over-budget figure raises and nothing
      reaches disk. `tests/test_figures.py` covers both budgets and the raise.)*
- [x] A generated model-provenance table exists as a CSV artifact.
      *(`scripts/analyze/export_model_provenance.py`, writing under `03_Analysis/model_provenance/`.)*
- [x] `pytest` passes, including the existing seven chart test modules and `test_palette.py`.
      *(2058 passed, 1 failed. The one failure is unrelated to this plan and deliberately left:
      `tests/test_axis_facet_defaults.py::test_flow_default_selects_exactly_the_highest_version_strategies`
      fails on an uncommitted operator edit to `config/gui/flows/generate_parallel.yaml`,
      which this branch does not touch.)*

## Definitions

- **Camera-ready**: an emitted figure whose every text element is Arial at 8–12 pt, whose strokes
  exceed 0.25 pt, whose colours are RGB, whose canvas is within 19.05 by 22.23 cm, and none of
  whose displayed strings contains an underscore or an API-provider token. Testable by inspecting
  the figure object before export, not by eye.
- **Display label**: the string a reader sees for a config id, resolved from that id's axis YAML
  `label:` field. Not derived by string manipulation of the id, and never the id itself.
- **Annotation policy**: an object deciding what text, if any, each heatmap cell prints, given that
  cell's already-computed data record. It decides *text only* — never colour, extent, or which
  cells are drawn.
- **Presentation layer**: the five modules under `analysis/utils/` listed in Architecture. A module
  belongs to it if and only if it can draw or format without importing any analysis subpackage.
- **Fails loudly**: raises a named exception naming the offending id and the config files searched.
  Not a warning, and never a fallback to the raw value.

---

## Technical Design

### Approach

Extract a presentation boundary and route every chart through it. The layer is **five separate
modules, not one facade**: a chart needing colour and export must not be forced to depend on label
resolution (interface segregation). Each module has exactly one reason to change.

The layer is a **pure sink**. It receives finished numbers and draws them; it computes no
statistic, no rate, no threshold. Dependency direction is one-way — presentation modules import
`analysis/utils` siblings, the standard library and matplotlib, and nothing from any analysis
subpackage.

Three existing assets are extended rather than replaced, per repo precedent:

- `analysis/utils/palette.py` gains categorical colours; the sequential ramp is untouched.
- `analysis/utils/figures.py::save_figure` gains an EPS branch. A second writer would violate the
  one-savefig-idiom rationale recorded in `plans/completed/fidelity-radar-svg-export.md`.
- `model_ranking/table_style.py` is **promoted** to `analysis/utils/`, not re-implemented. It
  already states the exact boundary rule this layer needs (`table_style.py:16-21`: it "knows
  nothing about which metric is plotted, which country, what things are called"), and its
  `HOST_COLORS` is the existing categorical-colour precedent.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Presentation modules, charts draw through them | One place per decision; testable in isolation; matches the `analysis/utils/` precedent | Touches every `charts.py` | **Chosen** |
| Fix the six symptoms in place | Small diffs, no refactor | Leaves ~15 sites to drift again; does not solve F05 without duplication | Rejected |
| Separate publication-export stage re-rendering selected figures | Working figures keep raw ids for debugging | Two rendering paths to keep in sync; the second silently rots | Rejected |
| One `PresentationContext` facade over all five | One import per chart | Forces charts to depend on modules they do not use; becomes a god-object with five reasons to change | Rejected |
| A new hand-maintained `figure_labels.yaml` | Whole figure vocabulary on one screen | Duplicates the `label:` that already exists in every axis YAML, and will drift from it | Rejected |
| `labels.resolve()` falling back to the raw id | Never crashes a long run | Exactly the banned `attr or DEFAULT` pattern; a new arm silently ships as `openrouter_kimi_k3` and is caught only at proofing | Rejected |
| A second `plot_mapped_validity_grid_clean()` function | Trivial to write | Duplicates the draw loop; the two diverge on the next edit | Rejected |
| Rendering camera-ready everywhere, no diagnostic mode | One path | Loses the `openrouter_` versus `ollama_` distinction when debugging a bad run | Rejected — provenance moves to the generated table instead |

### Architecture and Module Contracts

| Module / layer | Responsibility | Inputs to Outputs | Must NOT know about |
|----------------|----------------|-------------------|---------------------|
| `analysis/utils/palette.py` *(extend)* | Every colour decision: sequential ramp, categorical series, missing/off-ramp, annotation text contrast | colour role or value to RGBA/hex | Which metric, country, process or figure is being drawn |
| `analysis/utils/style.py` *(new)* | matplotlib global state: backend, rcParams, font family and size scale, line weights, the figure-size vocabulary | style name to applied rcParams; size name to (w, h) inches | Any data, any label text, any colour value |
| `analysis/utils/labels.py` *(new)* | Resolving config ids to display strings, and method letters | axis kind plus id(s) to display string(s); raises on unknown | matplotlib, figures, colours, statistics |
| `analysis/utils/figures.py` *(extend)* | Writing a finished figure to disk in every required format, within the size budget | `Figure` plus stem path to PNG, SVG and EPS on disk | What the figure shows, how it was drawn |
| `analysis/utils/grids.py` *(new)* | The shared heatmap draw loop: cells, extent, colour mapping, ticks, colourbar | matrix plus cell records plus policy to a drawn `Axes` | Which quantity, its units, its caveat text |
| `analysis/utils/grid_annotations.py` *(new)* | Annotation policies: what text a cell prints | one cell record to a string or `None` | Colour, extent, layout, other cells |
| `analysis/utils/table_style.py` *(moved)* | Grid furniture: dividers, best-cell boxes, category headers, colourbars | axes plus geometry to drawn furniture | (already documented — unchanged) |

Key signatures:

```
# labels.py -- every resolve raises UnknownAxisValue on a miss; no .get(id, id) anywhere
def model_label(model_id: str) -> str                     # "openrouter_kimi_k3" -> "Kimi K3"
def strategy_label(strategy_id: str) -> str               # "all_pick_dag_v2" -> "Pick with DAG context"
def method_letters(strategy_ids: Sequence[str]) -> dict[str, str]
def method_key_lines(strategy_ids: Sequence[str]) -> list[str]
def attribute_label(attribute: str) -> str
def model_provenance_rows() -> list[dict]                 # feeds the generated methods table

# grids.py
def render_grid(ax, matrix, cells, *, policy: CellAnnotationPolicy, cmap, norm, ...) -> AxesImage

# grid_annotations.py
class CellAnnotationPolicy(Protocol):
    required_keys: frozenset[str]
    def text(self, cell: Mapping[str, Any]) -> str | None: ...

class RateWithCountsPolicy: ...   # rate over "clean/generated" -- current F05 behaviour
class RateOnlyPolicy:       ...   # rate alone -- the clean F05 variant
class SignedValuePolicy:    ...   # "+0.031" -- two-sided quantities
class NoAnnotationPolicy:   ...   # None
```

### Binding Constraints

Carried from the ADRs, `design-principles.md`, and the engineering guides.

- **The sequential ramp is the only ramp.** `2026-08-12-self-contained-typicality-axis.md` rejected
  a diverging colormap in favour of `inferno` with the sign in annotations. `grids.py` must not
  introduce a second ramp module.
- **Annotation policies are key-aware and fail-fast.** The same ADR records a rejected approach
  where a lenient renderer read `cell["rate"]` by literal key and silently rendered every cell of a
  differently-shaped block as grey and unavailable — a silent-wrong-output path producing a
  plausible figure. Each policy therefore declares `required_keys` and `render_grid` validates the
  first cell record against it, raising on a mismatch. No key-guessing.
- **Caveat text is data, not code.** Fields such as `reference_note`, `direction_reason`,
  `counting_unit`, `n_confound` and `statistic_caveat` are read from the data block and printed;
  they are never authored in a chart module.
- **No fallback on missing config.** `design-principles.md:30-45`. An unresolvable id raises.
- **Lazy matplotlib import.** Per `table_style.py:29-31`, importing a presentation module must not
  pull in a backend; `style.py` owns backend selection at its one call site.
- **Presentation computes nothing.** No `scipy`, no aggregation, no threshold decisions in the layer.
- **DTOs at the boundary.** Plain dicts, arrays and frozen dataclasses cross into the renderer,
  never a report object carrying behaviour.

### Labelling Conventions

Adopted from the figure-guideline research. None is mandated by the standards doc, which is silent
on labelling, so they are recorded here as the project's chosen convention.

- **Sentence case for the phrase, proper nouns preserved**: `Kimi K3`, `Claude Sonnet`,
  `Housing tenure`. This is Nature's documented standard; APA's title case is the social-science
  alternative and is not adopted.
- **No underscores.** No journal guideline sanctions them; they are a code-identifier convention.
- **No API-provider prefix on any axis.** LMArena's leaderboard column names the model's *creator*,
  not its serving layer; the Kimi K2 report and the HuggingFace leaderboard do the same. The
  serving layer is genuine provenance for this project — OpenRouter can reroute quantizations, and
  the two Ollama hosts are different GPUs — so it moves to the generated provenance table, the
  location HELM-style papers use, rather than onto the figure.
- **A–E for generation methods**, assigned from `_families.yaml` rank: `all_pick` to A,
  `all_pick_dag` to B, `all_generate_pick` to C, `all_generate_evaluate_pick` to D,
  `all_generate_evaluate_random_pick` to E. The letter is **derived** from that config at render
  time, never stored, so reordering the file reorders the letters.
- **Version marker.** v1 and v2 are distinct analysis levels the pipeline never pools, so a figure
  containing both must distinguish them. `method_letters()` sees the whole id set and returns a
  bare letter when only one version is present, and a subscripted letter when both are.
  **Flagged for review: this is a proposed rule, not a settled decision.**
- **The key travels with the figure.** PLOS and Springer both require figure keys to be in the
  graphic rather than deferred to the caption; `method_key_lines()` supplies it, and captions
  repeat it.

---

## Implementation Plan

### Phase 1: Consolidate what already exists
**Goal:** One home for colour and grid furniture, with no visual change to any figure.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 1.1 — Move `model_ranking/table_style.py` to `analysis/utils/table_style.py`; update the four importers.
- [x] 1.2 — Promote `_COLOR_SERIES` into `palette.py::CATEGORICAL_SERIES`; delete the five verbatim copies and the renamed sixth.
- [x] 1.3 — Promote `HOST_COLORS`, `METHOD_COLORS` and the ~25 inline hex greys into named `palette.py` roles.
- [x] 1.4 — Fix `text_color_for_rgb`: linearise sRGB (`c/12.92` below 0.04045, else `((c+0.055)/1.055)**2.4`), use BT.709 coefficients 0.2126/0.7152/0.0722, and threshold at **0.179** rather than 0.5. The current BT.601 weights on gamma-encoded values leave 17 of 256 sampled points below WCAG AA 4.5:1, worst case 3.61:1.
- [x] 1.5 — Extend `test_palette.py` for the categorical roles and the corrected luminance crossover.

**Files Modified:** `analysis/utils/palette.py`, `analysis/utils/table_style.py` (moved),
`analysis/{fidelity,model_ranking,multivariate_fidelity,method_significance,consistency,generation_metadata,cost_efficiency,validation_attrition}/charts.py`,
`tests/test_palette.py`

**Dependencies:** None

### Phase 2: The style module
**Goal:** One place that decides how every figure looks, meeting the standards doc.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 2.1 — Create `analysis/utils/style.py`: backend selection, an `apply_house_style()` context manager, rcParams for Arial with a documented fallback stack, the 8–12 pt size scale (headers 11–12 bold, axis titles 10, ticks 8–9, legend 8), `lines.linewidth` and `axes.linewidth` above 0.25 pt, RGB output.
- [x] 2.2 — Define the figure-size vocabulary in inches: `SINGLE` (8.9 cm), `DOUBLE` (17.4 cm), `FULL` (19.05 cm maximum), each capped at 22.23 cm tall, plus the growth helpers replacing the 12 ad-hoc formulae.
- [x] 2.3 — Delete all 52 in-function `matplotlib.use("Agg")` calls.
- [x] 2.4 — Replace every `fontsize=` numeric literal with a named size from the scale, raising the sub-8 pt ones.
- [x] 2.5 — Unit-test that no rcParam permits a sub-8 pt or sub-0.25 pt value.

**Notes.** The style is applied by a `house_style` decorator over `apply_house_style()`, so
the 53 draw functions each carry one line rather than an indented `with` block; `rcParams` is
installed through `plt.rc_context`, so nothing leaks between draws. `font.family` names the
**resolved** family rather than the generic `sans-serif` alias — matplotlib resolves a generic
alias at render time, so a figure returned unsaved (as `cost_efficiency` does) and written by
its driver outside the context would otherwise have rendered in DejaVu Sans. All 58 `figsize=`
call sites now go through the vocabulary, not the 12 originally counted: 40 carried a growth
formula and the remaining 18 were fixed pairs, most of them wider than the printable canvas.

Three grids genuinely cannot breathe at the 19.05 cm cap with 8 pt text and need Phase 4's
annotation policy and a Phase 6 review: `fidelity/charts.py::plot_radar_grid` (a 3.2 in cell
times up to five strategy columns, previously ~17.5 in wide), `real_population_stats::plot_overview_panel`
(a 4x4 panel grid, previously 18 x 16.8 in, now taller than it is wide), and
`method_significance::_plot_facets` (4.6 in per facet column).

**Files Modified:** `analysis/utils/style.py` (new), every `analysis/**/charts.py`, `tests/test_style.py` (new)

**Dependencies:** Phase 1

### Phase 3: The label resolver
**Goal:** Ids stop reaching the canvas.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 3.1 — Create `analysis/utils/labels.py`, reading axis YAML `label:` fields directly, mirroring `axes.py`'s direct-read discipline since importing `manifest_loader` would be circular. No id-to-string table in code.
- [x] 3.2 — Implement `UnknownAxisValue`, raised with the offending id and the files searched. No `.get(id, id)`.
- [x] 3.3 — Strip provider prefixes for display, sourced from an explicit `display:` block added to each model axis YAML — not by string-splitting on `openrouter_`.
- [x] 3.4 — Implement `method_letters()` and `method_key_lines()` over `strategy_complexity_order`, including the version-marker rule.
- [x] 3.5 — Implement `model_provenance_rows()` and a script emitting the provenance CSV.
- [x] 3.6 — Unit tests: known ids resolve; an unknown id raises; letters follow `_families.yaml` order; reordering that file reorders the letters; a mixed-version set yields subscripted letters.

**Notes.** Nothing is wired into a chart module — that is Phase 4 and later; this phase
builds the resolver, adds the config it reads, and emits the table.

*The version marker is a plain digit, not a subscript.* Arial carries no U+2080–2089
glyph (verified against `C:\Windows\Fonts\arial.ttf`), so a true subscript would render
as a missing-glyph box or silently pull a second typeface in through matplotlib's
per-glyph fallback — the class of silent-wrong-output this layer exists to remove.
Mathtext (`$B_1$`) renders, but is matplotlib syntax and `labels.py`'s contract forbids
it knowing a renderer exists. `method_letters` therefore returns `B1`/`B2`, and the key
line disambiguates in words (`B1 — All Pick DAG (v1)`). The rule was flagged for review
in the conventions above; this is the renderable form of it.

*Letters are absolute, not dense.* A letter is the family's rank in `_families.yaml`, so
a figure omitting a family shows `A` and `C` rather than renumbering to `A` and `B` —
two figures drawn over different arms stay readable against each other. The version
marker is the opposite and is a property of the id *set*, exactly as specified.

*Two additions the task list did not name.* `axes.py` gains `strategy_families()`, the
public sibling of its existing `strategy_versions()` — the letter needs the family, and
the alternatives were importing `axes._strategy_family_version` or duplicating the read.
And `attribute_label()` needed a home for strings that exist nowhere in config today:
`config/analysis/attribute_labels.yaml`, country-agnostic, because the keys are canonical
mapped-schema names shared by all four mapping tiers and a `label` in each tier's
per-attribute JSON would be four copies of one string. This is not the `figure_labels.yaml`
rejected above — that was rejected for *duplicating* the axis YAMLs' existing `label:`,
which this file does not touch. A test asserts every attribute of every tier's `_index.json`
resolves.

*The provenance CSV's folder is deliberately unregistered.* `model_provenance/` sits under
`03_Analysis/` (stage segment from the registry, never a literal) but is not an
analysis-registry process: registry entries are DAG nodes with run inputs, a GUI task and
dependents, and this table is derived from the axis config alone.

**Files Modified:** `analysis/utils/labels.py` (new), `analysis/utils/axes.py`
(`strategy_families`), `config/synthetic/axes/models/*.yaml` (add `display:`),
`config/analysis/attribute_labels.yaml` (new),
`scripts/analyze/export_model_provenance.py` (new), `tests/test_labels.py` (new)

**Dependencies:** Phase 1

### Phase 4: The heatmap renderer and F05
**Goal:** One draw loop, pluggable annotations, and the clean F05 variant.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 4.1 — Create `analysis/utils/grid_annotations.py` with the four policies and the `required_keys` contract.
- [x] 4.2 — Create `analysis/utils/grids.py::render_grid`, validating the first cell record against `policy.required_keys` and raising on a mismatch.
- [x] 4.3 — Refactor `validation_attrition/charts.py:352 plot_mapped_validity_grid` to call it, with `RateWithCountsPolicy` reproducing today's output exactly.
- [x] 4.4 — Emit the clean F05 as the same call with `RateOnlyPolicy`, at 8 pt or above — room freed by dropping the count line — to `{country}_mapped_validity_grid_clean.*`.
- [x] 4.5 — Migrate the other 10 heatmap call sites onto `render_grid`.
- [x] 4.6 — Substitutability test: both policies over the same input produce identical dimensions, extent and colour scale, differing only in cell text.
- [x] 4.7 — (2026-08-25) Extend the variant mechanism to the other four `n=`-printing grids, move `GridVariant` and the suffix rule into `analysis/utils/grid_variants.py`, and make the **unsuffixed** filename the clean figure everywhere (counted form → `_with_counts`; F05's two names swap and `_clean` disappears).

**Notes.** `grep -rn "\.imshow(" src/` now matches exactly one line, in `grids.py`. All
eleven grids share the draw loop, the annotation-colour rule and the missing-cell
treatment; the ramp, the norm and every piece of furniture (dividers, boxes, hatches,
marginals, colourbars, captions, legends) stay with the caller, so `grids.py` still knows
nothing about which quantity is drawn.

*Validation is on every record, not the first.* The task list said the first; a block can
be uniform in its first row and ragged afterwards, and the cell that silently loses its
number is exactly the one a first-record-only check would skip. The cost is one dict
subtraction per cell.

*The policies are key-declaring, not key-fixed.* Each takes the record keys it reads as
fields (`value_key`, `denominator_key`, ...) and derives `required_keys` from that
declaration. This is not the banned key-guessing — nothing falls back to a second key or
reads through `.get(key, default)`; a caller *states* the shape and a typo still raises.
It is what let eleven differently-shaped blocks share four policies. Two knobs earned
their place the same way: `RateWithCountsPolicy.numerator_key=None` prints the base as
`n=` rather than as a fraction (the value is then not a quotient of two printed counts),
and `qualifier_key` names an already-formatted suffix — the typicality grid's signed
distance to the real population, which needs a *second* unit's value and so is formatted
by the chart that owns the reference, never derived in the policy. `COMPACT_NUMBER_FORMAT`
is a named formatting rule rather than a format spec, which is what preserved
`generation_metadata`'s existing mixed-magnitude cell labels byte-for-byte.

*The clean F05 is a `GridVariant` record, not a boolean.* The annotated and clean figures
differ in three things — the policy, the annotation size, and one sentence of the caption
— and the caption sentence *describes* the policy, so a clean figure captioned "printed
with the two counts it is the quotient of" would be a figure disagreeing with itself. The
three travel together in one frozen record; the CLI enumerates `GRID_VARIANTS` rather than
naming the variants, and the default variant keeps the historical unsuffixed filename so
no downstream reference moves.

**Revision, 2026-08-25 -- the clean variant becomes the default, layer-wide.** Four grids
outside F05 printed `n=<denominator>` on a second line of **every** cell
(`generation_metadata`'s metric heatmaps, `model_ranking`'s model x method TV grid, and
`realism_ranking`'s impossibility/severity and typicality grids). On a camera-ready figure
that is noise: the denominator is constant down a column, and it is already in the CSV the
grid is drawn from. All four now publish the same two variants F05 does, and the naming rule
is uniform across the five families: **the unsuffixed filename is the clean figure** and the
counted form is written beside it as `_with_counts`.

*This swaps F05's two filenames.* `{country}_mapped_validity_grid` was the annotated figure
and `..._clean` was the camera-ready one; it is now the other way round, and the `_clean`
suffix is gone. The swap is the point of the revision -- one rule rather than two -- but the
deck references those filenames, so anything pointing at `..._mapped_validity_grid_clean`
must move to `..._mapped_validity_grid`, and anything wanting the counts must move to
`..._mapped_validity_grid_with_counts`.

*The mechanism moved rather than multiplied.* `GridVariant` left
`validation_attrition/charts.py` for `analysis/utils/grid_variants.py`, which now also owns
the suffix rule (`variant_suffixes()`, canonical -> `""`, everything else -> `_{name}`) and a
`variant_map()` that raises on a duplicate name or a missing canonical variant. Each family
declares its own two variants -- the wording differs because a `cell_clause` *describes that
figure's* cells -- and each driver enumerates the map instead of naming them, so `rank_models`,
`rank_persona_realism` and `analyze_validation_attrition` all publish through one rule.
`RateOnlyPolicy` gained `qualifier_key`, because the typicality grid's clean variant must keep
its parenthesised signed delta: on a sequential ramp that is the only reading of the
reference's side there is (ADR 2026-08-12), so dropping it would remove content, not ink.

*Two things stay on the clean figures deliberately.* Row and column **marginals** keep their
counts, and `realism_ranking`'s **real-population band** keeps its own `n` -- each states a
base once for the whole figure rather than fifty times, which is what makes dropping the
per-cell repetition a loss of ink rather than of evidence. `generation_metadata`'s metric grid
has no marginal, so its key line moved from the legacy unclipped `ax.text` idiom onto
`caption_block`, which reserves its strip *inside* the canvas, and the clause naming where the
count went travels there.

*Type size rose on four of the five, not all five.* The freed line buys a step up the house
scale (8 -> 9 pt) on the grids whose cell is a bare number -- the three newly varianted ones
plus F05, which already had it. The typicality grid keeps 8 pt: its
cell carries an inline qualifier, so it is bound by the cell's **width** rather than by the
line it dropped, and that grid is already over the printable width. Nothing was reduced, and
the tests assert every variant sits at or above `FONT_FLOOR_PT` and that no clean variant is
smaller than its counted sibling.

*Substitutability is now asserted on all five families*, not on F05 alone
(`tests/test_grids.py`): same canvas, same extent, same norm, same painted array, same ticks,
same marking count -- and the clean cell text is its counted twin with the count line removed
and nothing else, which is what catches a variant that quietly drops a qualifier.

*Tick labels: F05 only, deliberately.* The validity grid now draws model display labels
and method letters A–E with the key in the graphic — it was being rebuilt anyway. The
other ten grids still print ids, for two reasons. `test_model_ranking_charts.py` and
`test_method_significance_charts.py` build their figures from synthetic ids (`model_a`,
`model_b`) that `labels.py` rejects *by design*, so relabelling those grids means
rewriting two fixture sets and the ordering assertions that rest on them. And relabelling
is a visible change to the manuscript figure family, which task 6.1 exists to review as
one diff; landing it in fragments across two phases would give that review a moving
target. Moved to Phase 6, where the compliance test that enforces it also lands.

**Files Modified:** `analysis/utils/grids.py` (new), `analysis/utils/grid_annotations.py` (new),
`analysis/utils/grid_variants.py` (new, 2026-08-25),
`analysis/{fidelity,generation_metadata,method_significance,model_ranking,realism_ranking,validation_attrition}/charts.py`,
`analysis/model_ranking/manuscript_tables.py`,
`scripts/analyze/{analyze_validation_attrition,rank_models,rank_persona_realism}.py`,
`tests/test_grids.py` (new), `tests/test_{validation_attrition_charts,model_ranking_charts,realism_ranking_builder}.py`

**Dependencies:** Phases 1–3

### Phase 5: Export
**Goal:** Every figure emits vector, in every required format, within budget.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 5.1 — Extend `figures.py::save_figure` with an EPS branch: fonts embedded or outlined, RGB.
- [x] 5.2 — Route the ~20 direct `fig.savefig(..., dpi=150)` calls through it; remove the `dpi=180` outlier.
- [x] 5.3 — Unify DPI to one source, replacing the 150/180/200 regimes and the five `--dpi` CLI defaults.
- [x] 5.4 — Validate on write: canvas within 19.05 by 22.23 cm and file under 10 MB, raising on violation.
- [x] 5.5 — Test asserting all three formats appear and satisfy the budget.

**Notes.** `grep -rn "fig.savefig" src/` now matches one line, inside `save_figure` itself.
The 19 direct writers are routed; `RASTER_DPI` in `figures.py` is the layer's only
resolution and the five `--dpi` flags default to it rather than to a literal (a test
asserts both, and that no chart module carries a `dpi=<number>` at all). Its value is
**300**, which unifies *upwards* — no figure loses resolution against the 150/180/200 it
replaces. The standards document's 600 dpi is for unavoidable raster content, of which
this layer has none: every figure is line art whose submission artifact is the EPS.

*The budgets are checked on the rendered bytes, and a rejection writes nothing.* All
three formats are rendered to memory first, the canvas is measured from the EPS
`%%HiResBoundingBox` and each format's length against the 10 MB ceiling, and only then is
anything written — so a figure that breaks a budget leaves no partial output. The canvas
is measured from the *written* file rather than from `fig.get_size_inches()` because
`bbox_inches="tight"` is what decides the written extent: it trims unused margin, and it
grows past the figure rectangle for any artist placed outside it. The figure's nominal
size is therefore not the size the printer receives, and the budget applies to the latter.

*`pad_inches` is pinned to zero.* matplotlib adds 0.1 in of whitespace on each side of the
tight box, so a figure drawn exactly at the printable cap was written 0.5 cm over it and
Phase 2's size vocabulary was unreachable by construction. At zero, the written canvas is
the content extent, so it can exceed the cap only when an artist genuinely overflows the
figure rectangle — which is the case worth failing on. This is a visible change to every
figure's crop (tighter), and is part of what task 6.1 reviews.

*The three grids flagged in Phase 2 resolved two-to-one.* `fidelity::plot_radar_grid` now
fits at 18.30 x 22.04 cm and `real_population_stats::plot_overview_panel` at 18.86 x 21.49 cm
on synthetic labels — both were only over by the padding. `method_significance::plot_method_comparison`
still fails, at 19.71 cm: with three columns at the cap, the rightmost panel's two-line title
is centred on a column whose centre leaves less than half the title's width to the page edge.
Widening is impossible (it is already at the cap) and narrowing makes the overhang worse, so
the fix is a layout change, not a size reduction.

*Enforcement found six more figures the plan had not counted*, all overflowing the printable
**width** by drawing text (a caption, a legend, a label column) wider than the canvas itself:

| Figure | Rendered canvas | What overflows |
|--------|-----------------|----------------|
| `method_significance::plot_method_comparison` | 19.71 cm | rightmost panel title |
| `model_ranking::plot_model_method_heatmap` | 21.60 cm | marginal column, colourbar and legend |
| `validation_attrition::plot_mapped_validity_grid` (F05) | 23.18 cm | caption line and legend entry |
| `validation_attrition::plot_attrition_funnel` | 26.63 cm | caption and legend |
| `cost_efficiency::plot_cost_vs_accuracy` | 21.86 x 25.20 cm | model labels and two annotation blocks (both axes over) |
| `realism_ranking::plot_typicality_heatmap` | 23.24 cm | caption and colourbar furniture |
| `realism_ranking::plot_impossibility_forest` | 19.16 cm | competitor labels |
| `fidelity::plot_radar_comparison` | 19.53 cm | attribute labels and legend outside the polar axes |
| `real_population_stats::plot_overview_panel` (real labels) | 20.04 cm | outermost panels' category labels |

None is a new defect — each figure's content was always wider than the printable page, and
`bbox_inches="tight"` silently grew the canvas to fit it. Nothing was clamped to accommodate
them: the fix is per-figure layout work, added as task 6.7. Of the 47 tests that render them,
14 are marked `xfail(strict=True)` carrying the measured size and the cause, so each breaks
again the moment its figure is fixed. The other 33 are `model_ranking`'s: its `_render` helper
swallows that one budget rejection and nothing else, so every structural assertion about what
was drawn keeps running, and only its two persistence tests are marked.

*EPS fidelity, verified.* Hatching survives — the withdrawn-cell hatch in F05 is written as a
PostScript pattern, not dropped. Transparency does **not**: the PostScript backend logs
"partially transparent artists will be rendered opaque" and flattens every `alpha=`, so the
EPS differs from its PNG and SVG siblings wherever alpha is used (grid lines, radar fills,
scatter points). That is the risk row already recorded in this plan; the opaque-equivalent
replacement is task 6.8. Fonts are embedded as TrueType (`FontType 42` plus the `sfnts`
program) even when a chart module returns an unsaved `Figure` and its driver saves it outside
`apply_house_style`, because `save_figure` installs the save-time `rcParams` subset itself —
read from the house style rather than restated.

**Files Modified:** `analysis/utils/figures.py`, `analysis/{fidelity,method_significance,model_ranking,consistency,multivariate_fidelity,generation_metadata}/charts.py`, `analysis/model_ranking/manuscript_tables.py`, `analysis/{persona_realism,real_population_stats}/artifacts.py`, the five `scripts/analyze/*.py` carrying `--dpi`, `tests/test_figures.py` (new), `tests/test_{comparison_artifacts,cost_efficiency_charts,method_comparison_chart,model_ranking_charts,real_population_stats_integration,realism_ranking_e2e,validation_attrition_charts}.py`

**Dependencies:** Phase 2

### Phase 6: Sweep and document
**Goal:** Prove compliance; leave the conventions written down.

**Started:** 2026-08-24
**Completed:** 2026-08-24

- [x] 6.1 — Regenerate the full figure set for `swedish_02`; diff against the current set and review every change.
- [x] 6.2 — Compliance test over emitted figures: no underscore, no provider token, no sub-8 pt text, all three formats present.
- [x] 6.3 — Fix the stale docstring at `scripts/analyze/rank_persona_realism.py:74`, which documents a diverging typicality ramp that no longer exists.
- [x] 6.4 — Add a thin cell stroke to grid heatmaps: abutting tiles cause simultaneous contrast (Crameri et al. 2020, citing Wong 2010), and `imshow` currently draws no separator.
- [x] 6.5 — Update `CLAUDE.md`, `docs/architecture/sub-packages.md` and `docs/architecture/design-principles.md`.
- [x] 6.6 — Write `docs/development/figure-conventions.md`: the standards-doc constraints, the labelling conventions and their sources, and the A–E key.
- [x] 6.7 — Bring the nine over-cap figures under the printable width (table in Phase 5's notes): each draws a caption, legend or label column wider than the canvas, so the fix is wrapping or relocating that text, never shrinking the figure. Clearing one un-`xfail`s its tests — the markers are `strict=True` and will fail loudly if left behind.
- [x] 6.8 — Replace every `alpha=` in the chart modules with an opaque equivalent: the PostScript backend flattens transparency, so the submitted EPS currently differs from its PNG and SVG siblings wherever alpha is used.
- [x] 6.9 — Relabel the ticks of the ten grids Phase 4 deferred, through `labels.py`, rewriting the two chart-test fixture sets onto real axis ids so the resolver can reach them. This is what closes the "no tick label contains an underscore" criterion.

**Notes.**

*6.1 was done against the real reports, not fixtures.* `03_Analysis/` holds a complete
`swedish_02` run, so every persisted report was read **read-only** and its figures
re-rendered into a scratch tree — 26 chart entry points writing 37 files across
`model_ranking`, `validation_attrition`, `method_significance`, `cost_efficiency`,
`generation_metadata` and `realism_ranking` — each inspected as a `Figure` before export and
then checked on disk for all three formats. Nothing under `03_Analysis/` was written. Three
figure families have no persisted intermediate to re-render from: the `generation_metadata`
comparison object is rebuilt from raw telemetry on every run, so its ten figures were driven
from the `ComboSummary` fixtures with **real** axis ids; and `fidelity::plot_radar_comparison`
and `real_population_stats::plot_overview_panel` are covered by their own integration tests,
whose `xfail`s 6.7 removed. The review found three real defects, all id leaks that only appear
at production scale, and all now fixed:

| Leak | Where | Fix |
|------|-------|-----|
| `ollama_deepseek_r1_14b, ollama_gemma4_e4b, ollama_mistral_nemo_12b` printed in a caption | `cost_efficiency::_rented_equivalent_note` | resolve each id through `model_label` |
| `the local ollama_* models` | the `unmetered_note` **document field** | reworded in the builder to "the locally served models" — caveat text is data, so the fix belongs where the sentence is authored |
| `local (Ollama)` on a legend | `table_style.HOST_LABELS` | `locally served` |

Only the second of those three survives a re-run of the sweep, and only because the
`swedish_02` cost document on disk predates the reworded note: substituting what the builder
emits today makes that figure camera-ready, and every other figure in the sweep already is.

That third one is the labelling convention applied to itself. The convention keeps the
serving layer off the figure and in the provenance table; `local (Ollama)` put it on a
legend, and named the *software* without naming the machine while the two local hosts are
different GPUs — so the parenthetical was provenance a reader could not act on. The LaTeX
caption that restated the same wording is now bound to `HOST_LABELS` rather than repeating
it, and so is the test that asserts it.

*6.7 cleared all nine.* No figure is `xfail`ed any more and no `strict=True` marker survives
anywhere in `tests/`. The mechanism is `table_style.fit_to_page`, called last, after every
artist and after the caption layout pass: it measures the drawn title, figure-level texts and
legends and pulls the ones reaching outside the figure rectangle back inside it. Nothing was
shrunk — the canvas each caller chose from the size vocabulary is preserved exactly, which is
what the task required. `method_significance::plot_method_comparison`, the one the plan
singled out as a layout rather than a size problem, is fixed by re-anchoring the overhanging
panel title, not by narrowing the column. Verified twice over: the previously-`xfail`ed tests
now pass unmarked, and every one of the nine wrote all three formats from the real reports in
6.1's sweep.

*6.8 chose removal over an EPS-only workaround.* Every `alpha=` is gone from the analysis
layer; `palette.opaque(color, alpha, over=...)` composites the colour the artist *would* have
had onto the ground it actually sits on, using the same "over" operator the raster backends
apply, so the converted figures keep the pixels they had and all three formats now show one
picture. The alternative — leaving alpha in and accepting a different EPS — was rejected
because the divergence is silent and lands only in the file that leaves the repository. The
only surviving `alpha=` tokens in `src/` are three that are not transparency at all — a
statistical significance level, two Krippendorff reliability coefficients, and the docstring
that explains the rule.

*6.9 rewrote both fixture sets onto real ids.* `model_a`/`model_b` were placeholders
`labels.py` rejects by design, so relabelling those grids meant replacing them with
`claude_haiku` / `claude_sonnet` / `openrouter_kimi_k3` and re-deriving every ordering
assertion that rested on alphabetical placeholder order. All eleven `render_grid` call sites
now tick through the resolver: model rows as `model_labels`, method columns as
`method_letters` with the key in the graphic, attribute axes as `attribute_label`. The
`consistency` bar chart — the one figure in the layer whose axis is neither models nor
methods — needed its own vocabulary: rules now carry a required `label:` in
`config/analysis/consistency/{country}.yaml` (an underscore in one raises at load), and the
scanned populations resolve through a new `labels.population_label`, which decomposes a run
slug against the declared axis ids rather than splitting on `_`.

*The last literal colour outside the palette is gone.* `model_ranking`'s "Overall" column
rule was drawn in a literal white; it is now the palette's `SURFACE` role, so a change of
ground moves it with everything else.

**Files Modified:** `CLAUDE.md`, `docs/architecture/{design-principles,sub-packages}.md`,
`docs/development/figure-conventions.md` (new), `scripts/analyze/rank_persona_realism.py`,
`analysis/utils/{grids,labels,table_style}.py`,
`analysis/consistency/{rules,builder,charts}.py`, `analysis/cost_efficiency/{builder,charts}.py`,
`analysis/model_ranking/{charts,manuscript_tables}.py`,
`config/analysis/consistency/scb_native.yaml`, `tests/test_figure_compliance.py` (new),
`tests/test_{consistency,labels,cost_efficiency_charts,model_ranking_charts,comparison_artifacts,real_population_stats_integration}.py`

**Dependencies:** Phases 1–5

---

## Testing Plan

### Unit Tests
- [x] `palette`: categorical roles are stable and distinct; the corrected luminance crosses at 0.179; every ramp sample yields text at 4.5:1 or above, or is reported.
- [x] `labels`: known ids resolve; an unknown one raises `UnknownAxisValue` naming the id; no `.get` fallback exists in the resolve path.
- [x] `labels`: A–E follow `_families.yaml`; reordering the file reorders the letters; mixed-version sets subscript.
- [x] `style`: no rcParam admits sub-8 pt text or sub-0.25 pt strokes; the size vocabulary stays within the caps.
- [x] `grid_annotations`: each policy declares `required_keys`; a mismatched cell record raises rather than rendering blank.
- [x] `labels`: a consistency rule and a scanned population both resolve, and an undecomposable population id raises rather than legending as itself.

### Integration Tests
- [x] Both F05 policies over one input: identical dimensions, extent and colour scale; only cell text differs.
- [x] Every figure-producing entry point emits PNG, SVG and EPS within the size and file-size budget.
- [x] A run whose model axis lacks a `display:` block fails before any figure is written.
- [x] Compliance sweep: 15 rendered figures across three families walked artist-by-artist for ids, provider tokens and out-of-band type, plus a deliberately non-compliant figure asserting the sweep itself can fail.

### Manual Verification
- [x] Regenerate `swedish_02`; confirm every figure renders and exports. *(Done programmatically
      against the live reports — read-only, into a scratch tree — rather than by eye: the
      camera-ready properties are defined as inspectable on the `Figure`, and the 8 pt floor,
      the font stack and the canvas budget are each asserted rather than judged. Opening the
      EPS files at 100% remains a human step before submission.)*
- [x] Confirm no emitted figure shows an underscore or a provider token.
- [x] Confirm the A–E key is readable without the caption. *(Present in the graphic on every
      figure carrying a method axis — eleven call sites — and rendered within the type scale.
      Whether it reads well at print size is the human step above.)*
- [x] Confirm the clean F05 is legible at single-column width.

### Edge Cases
- [x] A figure with one model and one method (degenerate grid).
- [x] A method axis containing only v2 strategies — bare letters, no subscripts.
- [x] A withdrawn combination — the hatch and grey survive the refactor.
- [ ] A very long attribute label at single-column width. *(Not covered. `wrap_to_width` and
      `fit_to_page` both handle it in principle and no live attribute is long enough to
      exercise it, so there is no regression test pinning the behaviour.)*
- [x] A model axis YAML with `label:` present but empty — must raise, not render blank.

---

## Documentation Plan

- [x] Update `CLAUDE.md` — the presentation layer in the architecture paragraph.
- [x] Update `docs/architecture/sub-packages.md` — the seven `analysis/utils/` presentation modules.
- [x] Update `docs/architecture/design-principles.md` — presentation-computes-nothing as a stated rule.
- [x] Create `docs/development/figure-conventions.md` — constraints, conventions, sources, the A–E key.
- [x] Docstring every new module with what it "knows nothing about", matching the existing
      `analysis/utils/` house style.

---

## Rollback Plan

1. **Before merge:** each phase is its own commit, so any phase can be reverted independently.
   Phase 1 is a pure move plus deduplication and is safe to keep even if later phases are dropped.
2. **Data considerations:** no data migration. Only figure files change, and they are regenerable
   from unchanged inputs. No analysis output CSV or JSON changes.
3. **Rollback procedure:** revert the phase commits in reverse order and re-run the analysis
   workflow to regenerate the previous figure set. The one non-figure artifact introduced is the
   provenance CSV, which is additive and can simply be deleted.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Arial unavailable on the render host and silently substituted | High | High | Assert the resolved font family after applying rcParams; raise if it is not Arial. Document the install. |
| Enforcing the 8 pt floor makes dense grids illegible or clipped | High | Med | Raise text to 8 pt, widen to the double-column vocabulary, and use the clean annotation policy for camera-ready variants; review every grid in 6.1 |
| The seven existing chart tests pin current behaviour and break wholesale | Med | Med | Phase 1 and task 4.3 are behaviour-preserving by construction; update tests per phase, never in bulk |
| Matplotlib's EPS backend mishandles transparency or hatching | Med | Med | The withdrawn-cell hatch is the known case; verify in 6.1 and fall back to an opaque equivalent |
| Rebase collision with `uniform-analysis-output-naming` | Med | Low | Land that plan first — it is smaller and fully scoped; the overlap is `rank_models.py` filenames versus rendering calls, mechanical rather than semantic |
| Adding `display:` to 28 model YAMLs drifts from `label:` | Med | Med | `display:` carries only what `label:` cannot express; a test asserts every model axis has both and that they agree on the model name |
| Regenerating figures changes a manuscript figure unnoticed | Med | High | Task 6.1 diffs the full set; the deck's `figures selection/` F01–F26 pairs are the review checklist |
| Scope creep into the colormap decision | Med | Med | Out of Scope is explicit; a diverging ramp requires its own ADR superseding `2026-08-12` |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — consolidate | ~0.5 day | None |
| Phase 2 — style | ~1 day | Phase 1 |
| Phase 3 — labels | ~1 day | Phase 1 |
| Phase 4 — grids and F05 | ~1 day | Phases 1–3 |
| Phase 5 — export | ~0.5 day | Phase 2 |
| Phase 6 — sweep and docs | ~1 day | Phases 1–5 |

---

## References

- `figure-preparation-standards.docx` — in the manuscript folder under
  `Manuscripts/40_llm-population-fidelity-benchmark/`
- `docs/development/decisions/2026-08-12-self-contained-typicality-axis.md` — the sequential-ramp-only decision
- `docs/development/plans/pending/uniform-analysis-output-naming.md` — sequence before this plan
- `docs/development/plans/completed/fidelity-radar-svg-export.md` — the one-savefig-idiom rationale
- `docs/architecture/design-principles.md:30-45` — no hardcoded fallbacks
- `config/synthetic/axes/strategies/_families.yaml` — the source of A–E order
- Crameri, Shephard and Heron (2020), *Nature Communications* 11:5444 — colour in science communication
- Wong (2011), *Nature Methods* 8:441 — colourblind-safe categorical palettes

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->

92 paths across Phases 1–6 (including the 2026-08-25 Phase 4 revision), from
`git log --name-only dev..HEAD` plus the working tree. Two operator run-configuration files that are dirty in the tree —
`config/gui/flows/analysis_workflow.yaml` and `config/gui/flows/generate_parallel.yaml` —
are excluded: they carry run parameters (`--n`, the selected model, a `force` flag), not
presentation-layer changes, and this branch does not touch them.

- `CLAUDE.md`
- `config/analysis/attribute_labels.yaml`
- `config/analysis/consistency/scb_native.yaml`
- `config/synthetic/axes/models/claude_haiku.yaml`
- `config/synthetic/axes/models/claude_opus.yaml`
- `config/synthetic/axes/models/claude_sonnet.yaml`
- `config/synthetic/axes/models/gemini_flash.yaml`
- `config/synthetic/axes/models/ollama_deepseek_r1_14b.yaml`
- `config/synthetic/axes/models/ollama_gemma2_9b.yaml`
- `config/synthetic/axes/models/ollama_gemma4_e4b.yaml`
- `config/synthetic/axes/models/ollama_llama31_8b.yaml`
- `config/synthetic/axes/models/ollama_llama32_3b.yaml`
- `config/synthetic/axes/models/ollama_llama33_70b.yaml`
- `config/synthetic/axes/models/ollama_lucie_7b.yaml`
- `config/synthetic/axes/models/ollama_mistral_nemo_12b.yaml`
- `config/synthetic/axes/models/ollama_qwen3_14b.yaml`
- `config/synthetic/axes/models/openrouter_deepseek_v4.yaml`
- `config/synthetic/axes/models/openrouter_deepseek_v4_flash.yaml`
- `config/synthetic/axes/models/openrouter_fable_5.yaml`
- `config/synthetic/axes/models/openrouter_gemini_flash_lite.yaml`
- `config/synthetic/axes/models/openrouter_glm_52.yaml`
- `config/synthetic/axes/models/openrouter_gpt56_sol.yaml`
- `config/synthetic/axes/models/openrouter_gpt_oss_120b.yaml`
- `config/synthetic/axes/models/openrouter_haiku_45.yaml`
- `config/synthetic/axes/models/openrouter_kimi_k3.yaml`
- `config/synthetic/axes/models/openrouter_mistral_medium.yaml`
- `config/synthetic/axes/models/openrouter_nemotron3_super.yaml`
- `config/synthetic/axes/models/openrouter_opus_5.yaml`
- `config/synthetic/axes/models/openrouter_qwen35_flash.yaml`
- `config/synthetic/axes/models/openrouter_qwen37_max.yaml`
- `config/synthetic/axes/models/openrouter_sonnet_5.yaml`
- `docs/architecture/design-principles.md`
- `docs/architecture/sub-packages.md`
- `docs/development/figure-conventions.md`
- `docs/development/plans/active/publication-figure-presentation-layer.md`
- `scripts/analyze/analyze_cost_efficiency.py`
- `scripts/analyze/analyze_method_significance.py`
- `scripts/analyze/analyze_persona_realism.py`
- `scripts/analyze/analyze_real_population_stats.py`
- `scripts/analyze/analyze_validation_attrition.py`
- `scripts/analyze/export_model_provenance.py`
- `scripts/analyze/rank_models.py`
- `scripts/analyze/rank_persona_realism.py`
- `scripts/analyze/summarize_generation_metadata.py`
- `src/population_synthetic/analysis/consistency/builder.py`
- `src/population_synthetic/analysis/consistency/charts.py`
- `src/population_synthetic/analysis/consistency/rules.py`
- `src/population_synthetic/analysis/cost_efficiency/builder.py`
- `src/population_synthetic/analysis/cost_efficiency/charts.py`
- `src/population_synthetic/analysis/fidelity/charts.py`
- `src/population_synthetic/analysis/generation_metadata/__init__.py`
- `src/population_synthetic/analysis/generation_metadata/charts.py`
- `src/population_synthetic/analysis/method_significance/charts.py`
- `src/population_synthetic/analysis/method_significance/marginal_charts.py`
- `src/population_synthetic/analysis/model_ranking/charts.py`
- `src/population_synthetic/analysis/model_ranking/manuscript_tables.py`
- `src/population_synthetic/analysis/model_ranking/table_style.py`
- `src/population_synthetic/analysis/multivariate_fidelity/charts.py`
- `src/population_synthetic/analysis/persona_realism/artifacts.py`
- `src/population_synthetic/analysis/persona_realism/charts.py`
- `src/population_synthetic/analysis/real_population_stats/artifacts.py`
- `src/population_synthetic/analysis/real_population_stats/charts.py`
- `src/population_synthetic/analysis/realism_ranking/charts.py`
- `src/population_synthetic/analysis/utils/axes.py`
- `src/population_synthetic/analysis/utils/figures.py`
- `src/population_synthetic/analysis/utils/grid_annotations.py`
- `src/population_synthetic/analysis/utils/grid_variants.py`
- `src/population_synthetic/analysis/utils/grids.py`
- `src/population_synthetic/analysis/utils/labels.py`
- `src/population_synthetic/analysis/utils/palette.py`
- `src/population_synthetic/analysis/utils/style.py`
- `src/population_synthetic/analysis/utils/table_style.py`
- `src/population_synthetic/analysis/validation_attrition/charts.py`
- `tests/test_comparison_artifacts.py`
- `tests/test_consistency.py`
- `tests/test_cost_efficiency_charts.py`
- `tests/test_figure_compliance.py`
- `tests/test_figures.py`
- `tests/test_grids.py`
- `tests/test_labels.py`
- `tests/test_manuscript_tables.py`
- `tests/test_method_comparison_chart.py`
- `tests/test_method_significance_charts.py`
- `tests/test_model_ranking_charts.py`
- `tests/test_palette.py`
- `tests/test_real_population_stats.py`
- `tests/test_real_population_stats_integration.py`
- `tests/test_realism_artifacts.py`
- `tests/test_realism_ranking_builder.py`
- `tests/test_realism_ranking_e2e.py`
- `tests/test_style.py`
- `tests/test_validation_attrition_charts.py`

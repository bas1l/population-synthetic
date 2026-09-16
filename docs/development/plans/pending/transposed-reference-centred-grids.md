# Plan: Transposed, Ranking-Ordered Grids (Reference-Centred and Sequential)

**Date:** 2026-09-10
**Author:** Basil
**Status:** Pending — blocked on two decisions (see *Decisions required*)
**Base Branch:** `dev`
**Branch:** `feature/transposed-reference-centred-grids`
**Sequencing:** land **after** `feature/method-pair-significance-grids` merges. That branch is
rewriting the exact `### One ramp` passage this plan must amend again.

---

## Overview

Four proof-of-concept figures were built in the session scratchpad, reviewed, and approved. They
re-cut grids the analysis layer already computes so that **methods A–E are the rows and models are
the columns, ordered by the published model × method fidelity ranking**. Three of them additionally
centre a diverging colour ramp on the real (SCB-sampled) population's own value.

| Proof of concept | Promotes to | Ramp |
|---|---|---|
| `poc_severity_s1_centered_*` | `realism_ranking` — severity S1 | diverging, centred on the real population |
| `poc_severity_s2_centered_*` | `realism_ranking` — severity S2 | diverging, centred on the real population |
| `poc_impossibility_centered_one_sided` | `realism_ranking` — impossibility (axis A) | diverging, upper half only (reference is 0) |
| `poc_F05_mapping_survival_transposed` | `validation_attrition` — mapped-validity grid | **unchanged** house sequential ramp, 0–100 % |

The reusable procedure is written up as the `centred-heatmap` skill
(`.claude/skills/centred-heatmap/SKILL.md`); this plan is the promotion of its first two
applications into `src/`.

## Problem Statement

The proofs of concept live outside `src/` because each of them does something the repository
forbids there. Promotion is not a copy; it is the resolution of six distinct violations.

1. **A diverging ramp is currently prohibited by ADR.** `docs/development/figure-conventions.md`
   (`### One ramp`, and the two-sided rule beneath it) states that a two-sided quantity carries its
   side in the annotations, never the hue, and that this is settled by
   `docs/development/decisions/2026-08-12-self-contained-typicality-axis.md`, which **rejected a
   diverging ramp**. That doc also says introducing one *requires an ADR superseding it*.
2. **The column order lives in a private helper of the wrong subpackage.** Both proofs of concept
   import `_model_method_rows`, `_tier1_sort_key` and `_tier2_sort_key` from
   `model_ranking/charts.py`. `realism_ranking` and `validation_attrition` importing across
   subpackages violates the convention that shared helpers live in `analysis/utils/`.
3. **A chart derives a statistic.** `poc_centered_heatmaps.py` computes `count = rate × denominator`
   because the impossibility grid does not carry the count. `CLAUDE.md`'s *Presentation computes
   nothing* invariant forbids this; the count must come from the builder.
4. **The proofs of concept own their own `imshow`, `savefig` and `rcParams`.** `src/` holds exactly
   one of each, in `grids.py`, `figures.py` and `style.py` respectively.
5. **The two-size cell is not expressible as an annotation policy.** `render_grid` writes one text
   artist per cell at one size; the proof of concept draws the count large and the signed delta
   small beneath it, as two artists.
6. **The realism figures need data the realism process never read.** They depend on
   `model_ranking`'s `{country}_performance.json` and on the cap index. `rank_persona_realism.py`
   reads neither, and has no hosting wiring either.

## Decisions required (blocking)

**D1 — the ADR.** Do the three centred grids get a sanctioned diverging ramp? The existing rule
already carries the escape hatch (*"must do the same **or keep its own diverging ramp**"*), so the
ADR's job is to argue these grids are that case, not to overturn the sequential default. The
in-flight `SIGNIFICANCE_CMAP` work has already converted `### One ramp` from an absolute
prohibition into an enumerated-exceptions structure, which makes this the *second* enumerated
departure rather than a first breach. **Without D1 the three centred grids cannot ship**; the
transposed F05 (sequential ramp, no centring) is unaffected and can land alone.

**D2 — new stems or replacements?** For each family, does the transposed figure sit *beside* the
existing one or *replace* it?
- *Replace* keeps `figure_selection.yaml` untouched and keeps the manuscript numbering stable, but
  discards the model-as-row reading.
- *Add* needs new `n:` entries and moves two hardcoded counts in `tests/test_figure_selection.py`.

Note a transposition is **not** a `GridVariant`: that mechanism names a cell-annotation difference
over an otherwise identical figure. A transposed grid needs its own public plot function.

## Phases

### Phase 1 — Lift the model ordering into `analysis/utils/model_order.py`

New module, **not** part of the presentation boundary (it computes a ranking, which is the
boundary's exclusion test). Lift `_ModelRow`, `_row_summary`, `_model_method_rows`,
`_tier1_sort_key`, `_tier2_sort_key` verbatim from `model_ranking/charts.py:512-639`; the block is
matplotlib-free and label-free and depends only on `dataclasses`, `typing`, `numpy` and
`utils/cap_index.CapIndex`.

Add two public façades the proofs of concept each hand-rolled:
- `ranked_model_order(result, requested_n) -> list[str]` — reads `models`/`strategies` off
  `result["metadata"]`, returns tier-1-then-tier-2 model ids.
- `align_to_ranking(present, ranked) -> tuple[list[str], int]` — the ordered ids plus the index at
  which unranked models begin, which is the datum the vertical rule is drawn from. Raises when the
  ranking knows a model the grid does not.

`model_ranking/charts.py` keeps `_column_marginals` and `_row_marginal_text` (figure furniture) and
imports the rest. Its call site at 737-740 keeps calling `model_rows` + the two keys, because it
needs the rows themselves, not just the ids.

Add `tests/test_model_order.py`, reusing the fixtures in `tests/test_model_ranking_charts.py`. The
ordering is currently tested only indirectly, by rendering and reading tick labels; a direct test
is strictly better and this is the moment to add it.

Document the new module in `docs/architecture/sub-packages.md` beside `cap_index.py` — **not**
inside the presentation-layer bullet. Fix the stale "seven modules" count there and in `CLAUDE.md`
while in the file (the list already names eight).

### Phase 2 — Carry the impossibility count through the builder

`realism_ranking/builder.py:309-316` (`_axis_a_grid._cell`) emits `slug`, `rate`, `ci_lo`, `ci_hi`,
`denominator`. Add `impossible_count`, which already exists one level up at `builder.py:192`. The
severity grids already carry `affected` and need no change. This removes violation 3.

### Phase 3 — Presentation-layer seams

- **`palette.py`** — add `DIVERGING_CMAP` in the ramp block beside `SIGNIFICANCE_CMAP`, and
  `diverging_cmap(*, one_sided=False, ...)` beside `heatmap_cmap`, sharing its `set_bad` policy
  (`grids._missing_text_color` raises on a colormap with a transparent bad colour, which a
  from-scratch `LinearSegmentedColormap` has). Both names into `__all__`, or `tests/test_palette.py`
  fails. Rename the now-wrong `# The sequential ramp` block header.
  Delete the proof of concept's own `text_colour()` — it is a gamma-encoded luminance
  reimplementation of the bug `palette.py` documents as fixed. Use `text_color_on`.
- **`style.py` / `figures.py`** — delete the proof of concept's `rcParams["hatch.linewidth"]`
  assignment; `HATCH_LINEWIDTH = 0.6` and the rcParams entry already exist. Separately, add
  `"hatch.linewidth"` to `figures.EXPORT_RC_KEYS`: F05's withdrawn-hatch is currently drawn at
  matplotlib's default 1.0 because the figure is saved outside `apply_house_style`, and this fixes
  that *and* lets `model_ranking/charts.py:486, 923-926` delete its local workaround.
- **The reference strip** — a second `render_grid` call on a second axes with a 1×`n_rows` matrix at
  the centre value, same cmap and norm. Do **not** extend `render_grid`: its docstring is explicit
  that everything but the image and the annotations belongs to the caller.
- **The two-size cell (violation 5)** — resolve one of two ways, and say which in the plan review:
  (a) drop to one size and use `RateOnlyPolicy(value_key="count", scale=1.0, number_format="d",
  qualifier_key="delta")` with the chart pre-formatting `delta` — the mechanism
  `plot_typicality_heatmap` already uses at `charts.py:1158-1165`; or (b) keep two sizes, pass
  `NoAnnotationPolicy`, and have the chart draw its own annotations, which is what that policy
  exists for. **(a) is preferred** — it needs no new policy, no `_ALL_POLICIES` entry, and matches
  the closest existing figure.

### Phase 4 — The three centred realism grids

Base them on **`realism_ranking/charts.py:1097-1308` `plot_typicality_heatmap`**, not on the proof
of concept's layout code. That function already does, in-repo and inside the invariants: reference
read from the data block never a literal, per-cell pre-formatted signed delta, a rule across the
colourbar at the reference coloured by `text_color_on`, graceful degradation when there is no
reference, and caption wording read from the data block.

Driver work in `scripts/analyze/rank_persona_realism.py`:
- add hosting wiring, copied from `analyze_validation_attrition.py` (its lines 65-68, 96, 210);
  capture the model dicts at line 414, which currently discards them;
- read `{country}_performance.json` and `load_cap_index(output_base)` beside the `output_base`
  resolution at line 446. **This makes the realism figures depend on `rank_models.py` having run
  for that country** — decide whether that is a fail-fast with a useful message or a documented
  skip, and record it in the analysis registry's dependency edges.
- new `charts += [...]` block at ~line 596, using the `lambda variant=variant, level=level:` binding
  idiom the comment at 576-577 explains.

### Phase 5 — The transposed F05

A new public function in `validation_attrition/charts.py` (transposed; not a `GridVariant`).
Everything about the colour is unchanged: `inferno_cmap()` and the fixed `Normalize(0, 1)` at
lines 546-549 carry over verbatim. Replace the pooled-survival row ordering at 499-510 with
`align_to_ranking`. Hosting is already wired in this driver; only the emission block at 270-291
needs a new stem.

### Phase 6 — Docs, config, tests

- **ADR** superseding `2026-08-12-self-contained-typicality-axis.md` (gated on D1).
- **`figure-conventions.md`** — a new section modelled on `### A tier is not a magnitude`, naming
  the exact callers, the ramp, why the quantity is not a magnitude, and the `MISSING_COLOR`
  separability check. The parallel prose in `palette.py`'s docstring moves in lockstep.
- **`figure_selection.yaml`** (gated on D2) — new `n:` entries take the next free number above the
  top, per the file's own precedent; check every new basename against every existing one, because
  `as_generated/` flattens the set and rejects a collision.
- **Tests to budget for:** `test_grids.py` (`_ALL_POLICIES` if a policy is added; `_variant_pairs`
  registration), `test_palette.py` (a diverging-ramp property test — it inverts two assertions of
  the sequential one, so it needs its own test rather than an amendment), `test_figure_compliance.py`
  (add both families to the roster; this is the only place a stray raw model id on a tick label gets
  caught, and the centred grids put model ids on an axis that never had them),
  `test_figure_selection.py` (two hardcoded `== 23` counts), `test_realism_ranking_builder.py` (the
  Phase 2 builder change), `test_realism_ranking_e2e.py` (exact stem list at 215-223),
  `test_validation_attrition_charts.py` (stem list plus an exact PNG count at 565), and the new
  `tests/test_model_order.py`.

## Risks

- **Canvas budget.** `save_figure` enforces `FULL` × 22.23 cm off the rendered EPS bounding box and
  writes nothing on rejection. The proofs of concept draw four `fig.text` blocks at absolute figure
  coordinates rather than through `style.caption_block` / `table_style.fit_to_page`, so the tight
  bbox after promotion is not the declared figsize. `publication-figure-presentation-layer.md:533`
  records F05 already measuring 23.18 cm and being rejected once. Expect to route the caption,
  method key and legend through the house helpers.
- **Tick rotation.** `table_style.categories_on_top` rotates 40° / `ha="left"`; the proofs of concept
  rotate 90° / `ha="center"`, which is what makes 13 long model names fit across a full-width canvas.
  Either extend `categories_on_top` with a rotation parameter or accept 40°.
- **Merge collision.** One passage only — the `### One ramp` register in `figure-conventions.md` and
  `palette.py` — and it is favourable, since the in-flight branch has already built the
  enumerated-exception structure this work needs. Sequencing removes the conflict entirely.

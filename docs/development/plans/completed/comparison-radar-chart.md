# Plan: Comparison Pipeline — Radar Chart

**Date:** 2026-05-09
**Author:** Basil
**Status:** In Progress
**Started:** 2026-05-09
**Completed:** 2026-05-09
**Base Branch:** `dev`
**Branch:** `feature/comparison-radar-chart`

---

## Overview

Add a single radar (spider) chart to the SCB population comparison pipeline that overlays per-dimension similarity scores on one figure. With a fixed axis order and fixed radial scale, multiple radar PNGs from different comparison runs become visually comparable side-by-side, letting the user quickly judge which generation approach matches the reference more closely.

## Problem Statement

`scripts/compare_populations.py` currently produces a JSON report and a folder of per-attribute bar charts (`<attr>.png`) — one PNG per demographic dimension (~9–18 files per comparison). To assess overall fidelity of a generation strategy, the user must flip through all per-attribute PNGs and mentally aggregate. When evaluating multiple strategies (e.g., seed 007 vs seed 008 against the same SCB reference), this becomes prohibitively slow and error-prone — there is no single artefact summarising "how close is population B to population A across all dimensions?".

## Goals

### In Scope
1. Add a `plot_radar_comparison()` function in `scripts/compare_populations.py` that produces one radar chart per comparison run
2. Overlay two polygons: `1 - tv_distance` (TV-similarity, solid) and `chi_sq_p` (statistical-significance, dashed) on the same axes
3. Provide a `--radar-tv-only` CLI flag to suppress the chi-squared overlay
4. Generate the radar by default whenever per-attribute charts are generated (suppressed by existing `--no-charts`)
5. Use a fixed `[0, 1]` radial scale and a fixed axis order (`DEMOGRAPHIC_ATTRIBUTES`) so radars from different runs are directly comparable

### Out of Scope
- Multi-comparison grid script (one PNG containing several radars side-by-side) — visual comparison happens in the file browser by opening multiple `radar.png` files
- Changes to `StatisticalEvaluator`, JSON/CSV writers, normalization code, or `analyze_scb_population.py`
- New similarity metrics beyond what's already in the report (`chi_sq_p`, `kl_divergence`, `tv_distance`, `max_diff`)
- Interactive/HTML radar (matplotlib PNG only, matching existing chart format)

## Success Criteria

- [ ] Running `python scripts/compare_populations.py <pop_a.json> <pop_b.json>` produces `data/analysis/comparison_report/radar.png` alongside the per-attribute bar charts
- [ ] The radar shows two overlaid polygons (teal solid for TV-similarity, amber dashed for chi-squared p-value) on a fixed `[0, 1]` radial scale
- [ ] Each TV-similarity vertex is annotated with its numeric value (`0.XX`)
- [ ] `--radar-tv-only` produces a radar with only the TV polygon and no legend
- [ ] `--no-charts` suppresses the radar along with the per-attribute charts
- [ ] Two `radar.png` files generated from different comparison runs (against the same reference) have axes in the same order at the same angles, enabling direct visual comparison
- [ ] When `marginals` has fewer than 3 attributes, the radar is skipped with a stderr warning rather than producing a degenerate plot
- [ ] NaN `chi_sq_p` values are visually marked (open-circle scatter at the radial origin) rather than silently rendered as 0

---

## Technical Design

### Approach

Add one self-contained function `plot_radar_comparison()` to `scripts/compare_populations.py` that consumes the already-computed `report["marginals"]` dict (no metric recomputation, no risk of drift from `_marginal_metrics` at line 290). The function uses matplotlib's polar projection with the existing `Agg` backend pattern from `plot_comparison_charts()`. Wire it into `main()` immediately after the existing chart-generation call.

The chart's cross-run comparability hinges on two enforced invariants:
1. **Axis order:** filtered `DEMOGRAPHIC_ATTRIBUTES` (line 26 of `compare_populations.py`) — canonical, never re-sorted by content
2. **Radial scale:** fixed `[0, 1]` with gridlines at 0.2/0.4/0.6/0.8/1.0 — never auto-scaled

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Single radar PNG per comparison run, in same charts dir | Trivial integration; user compares by opening multiple files; no new script | User must arrange windows manually | **Chosen** |
| Multi-comparison grid script taking N comparison_report.json files | One artefact contains all comparisons | New script + CLI; opinionated layout; rebuild on every change | Rejected (deferred — single-radar enables this later if needed) |
| Plotly interactive HTML radar | Hover tooltips, zoom | Extra dependency; not the existing chart format; harder to share as image | Rejected |
| Single metric only (just `1 - tv_distance`) | Simpler chart | Loses statistical-significance lens (chi-sq p-value) | Rejected (overlay chosen with opt-out flag) |
| Re-derive metrics inside the radar function from raw populations | Function self-contained | Duplicates `_marginal_metrics` logic, risks drift | Rejected |

### Architecture Changes

Single-file change. No new modules.

```
scripts/
└── compare_populations.py   — Add 2 color constants, 1 helper, 1 plot function, 1 argparse flag, 1 call site
```

#### Code anchors in `compare_populations.py`

| Line | Anchor | Change |
|---|---|---|
| 26 | `DEMOGRAPHIC_ATTRIBUTES` | Reuse for axis ordering (no edit) |
| 290 | `_marginal_metrics` | Source of `tv_distance` / `chi_sq_p` per attribute (no edit) |
| 549 | `_ATTR_COLORS` | Add `_RADAR_TV_COLOR` and `_RADAR_CHI_COLOR` constants below |
| 642 | End of `plot_comparison_charts` | Insert `_close_polygon` helper + `plot_radar_comparison` |
| 681 | After `--no-charts` argparse block | Add `--radar-tv-only` flag |
| 721 | Inside `if not args.no_charts:` block | Add `plot_radar_comparison(...)` call + print |

---

## Implementation Plan

### Phase 1: Radar function and constants

**Goal:** Self-contained radar chart function with no integration changes yet.

**Tasks:**
- [x] 1.1 — Add `_RADAR_TV_COLOR = "#2A9D8F"` (teal) and `_RADAR_CHI_COLOR = "#E9C46A"` (muted amber) module-level constants below `_ATTR_COLORS` at line 549. Use new colors (not `_ATTR_COLORS`) because the radar visualizes the comparison itself, not pop A vs pop B — reusing the per-population palette would mislead the eye.
- [x] 1.2 — Add `_close_polygon(values: list[float]) -> list[float]` helper that returns `values + values[:1]`. Insert immediately above `plot_radar_comparison`.
- [x] 1.3 — Add `plot_radar_comparison()` function with this signature:
  ```python
  def plot_radar_comparison(
      marginals: dict[str, dict[str, Any]],
      output_dir: Path,
      pop_a_label: str = "Population A",
      pop_b_label: str = "Population B",
      *,
      show_chi_sq: bool = True,
  ) -> Path | None:
  ```
  Behavior:
  - Filter `DEMOGRAPHIC_ATTRIBUTES` to those present in `marginals`. If `< 3`, print `"Skipping radar: needs >=3 attributes (got N)"` to stderr and return `None`.
  - Compute `tv_sim = [1.0 - marginals[a]["tv_distance"] for a in attrs]`.
  - Compute `chi_plot` from `chi_sq_p`, replacing NaN with `0.0`; track NaN positions via `np.isnan` (numpy already imported at line 20 — no new import).
  - Create polar axes: `subplot_kw={"projection": "polar"}`, figsize `(8, 8)`, `set_theta_offset(np.pi / 2)`, `set_theta_direction(-1)` (start at top, clockwise).
  - Plot TV-similarity polygon (solid teal): `linewidth=2`, fill `alpha=0.20`. Close with `_close_polygon`.
  - If `show_chi_sq`: plot chi-sq polygon (dashed amber): `linestyle="--"`, `linewidth=1.5`, fill `alpha=0.20`. Add open-circle scatter (`facecolors="none"`) at NaN-spoke angles at radial origin.
  - X-tick labels rotated to follow each spoke (`np.degrees(ang) - 90` if `ang <= np.pi` else `+ 90`), `fontsize=7`.
  - Annotate each TV vertex with `f"{val:.2f}"` just outside the polygon (`fontsize=7`, `color=_RADAR_TV_COLOR`). TV only — annotating chi-sq would clutter.
  - Title (two-line): `f"Per-dimension similarity\n{pop_a_label} vs {pop_b_label}"` (`fontsize=11`, `fontweight="bold"`, `pad=24`).
  - Radial scale: `set_ylim(0, 1)`, `set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])`, light-gray gridlines, `spines["polar"].set_linewidth(1.2)`.
  - Legend `loc="lower left"`, `bbox_to_anchor=(-0.1, -0.05)`, `fontsize=8` — only when `show_chi_sq` (otherwise the single-polygon legend is redundant).
  - Save to `output_dir / "radar.png"` at `dpi=150`, `bbox_inches="tight"`. Return path.

**Files Modified:**
- `scripts/compare_populations.py` — additions only (constants, helper, function); no edits to existing code

**Dependencies:** None

### Phase 2: CLI integration

**Goal:** Generate the radar by default; allow opt-out of chi-sq overlay.

**Tasks:**
- [x] 2.1 — Add argparse flag in `main()` after the `--no-charts` block (after line 681):
  ```python
  parser.add_argument(
      "--radar-tv-only",
      action="store_true",
      help="On the radar chart, show only the TV-similarity polygon (omit chi-squared p-value overlay).",
  )
  ```
- [x] 2.2 — Inside the existing `if not args.no_charts:` block, after the `plot_comparison_charts(...)` call and its print (after line 721), add:
  ```python
  radar_path = plot_radar_comparison(
      report["marginals"],
      charts_dir,
      pop_a_label=Path(args.pop_a).stem,
      pop_b_label=Path(args.pop_b).stem,
      show_chi_sq=not args.radar_tv_only,
  )
  if radar_path is not None:
      print(f"Radar chart written to {radar_path}")
  ```
  Reuses `charts_dir` already resolved at lines 710–713; the `is not None` guard surfaces the `< 3` skip cleanly without printing a fake path.

**Files Modified:**
- `scripts/compare_populations.py` — argparse + call site additions

**Dependencies:** Phase 1

---

## Testing Plan

No automated test suite exists in the repo (per `CLAUDE.md`). Verification is manual.

### Manual Verification

- [ ] **Default flow** — Run `python scripts/compare_populations.py <pop_a.json> <pop_b.json>`. Verify `data/analysis/comparison_report/radar.png` exists alongside `<attr>.png` files. Open it: two overlaid polygons (solid teal + dashed amber), all available demographic axes labelled, title shows both stems on two lines, radial scale visibly capped at 1.0.
- [ ] **TV-only flag** — Run with `--radar-tv-only`. Verify `radar.png` shows only the teal solid polygon and no legend.
- [ ] **No-charts flag** — Run with `--no-charts`. Verify no `radar.png` and no per-attribute PNGs are written.
- [ ] **Custom charts dir** — Run with `--charts-dir data/test_radar/`. Verify `radar.png` lands in that dir.
- [ ] **Cross-run comparability** — Generate two distinct comparisons (e.g., seed 007 vs SCB reference, seed 008 vs SCB reference) into separate output directories. Open both `radar.png` files: axes must appear in the same order at the same angles in both PNGs.
- [ ] **Skip path** — Construct a synthetic `marginals` dict with 0, 1, and 2 attributes (or feed populations sharing fewer than 3 attributes); verify stderr message and no `radar.png` written.
- [ ] **NaN chi-sq markers** — Find/construct a comparison where at least one attribute yields NaN `chi_sq_p` (line 314 / 316 in `_marginal_metrics`); verify the radar shows an open-circle marker at the corresponding spoke at the radial origin rather than silently plotting 0.

### Edge Cases

- [ ] **Long axis labels** (`current_environment_type`, `socioeconomic_class`, `industry_sector`) — confirm rotated labels remain readable, no overlap. If overlap occurs, drop label fontsize to 6 before considering abbreviation.
- [ ] **All-perfect comparison** (pop_a vs pop_a) — radar should be a fully-extended unit polygon at radius 1.0 with all vertex annotations reading `1.00`.
- [ ] **Maximum-divergence case** — radar polygon should collapse near the centre; vertex annotations should still be readable (not behind the polygon).

---

## Documentation Plan

- [ ] No README/CLAUDE.md updates required — radar generation is automatic, no new commands or workflows. The new `--radar-tv-only` flag is self-documenting via `--help`.
- [ ] Add a one-line mention in the comparison-pipeline section of any future `pipeline_documentation.md` describing the radar artefact, if/when that section is added.

---

## Rollback Plan

Single-file, additive change. To revert:

1. **Before any merge:** `git checkout scripts/compare_populations.py` on the feature branch, then delete the branch.
2. **After merge to dev:** `git revert <commit-hash>` on dev. The change is self-contained — no migrations, no shared-state side effects, no other files touched.
3. **Generated `radar.png` files:** Safe to leave in place (just unused PNGs); or delete with `rm data/analysis/*/radar.png` if desired.

No data considerations — the change does not modify report JSON/CSV structure or any persisted state.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Polar label rotation collides for 18-attribute case | Medium | Low | Drop fontsize to 6 if needed; tested on real data during verification step |
| Two overlaid translucent polygons become muddy in mid-range | Low | Low | Alpha tuned to 0.20 each; `--radar-tv-only` lets user disable chi-sq overlay |
| User reads chi-sq p-value as a "similarity" (it isn't, strictly) | Medium | Low | Distinct dashed style and amber colour signal it's a different metric class; legend label is `"Chi-sq p-value"` not `"Chi-sq similarity"` |
| Radar PNGs from different runs aren't truly comparable if one has fewer attributes | Low | Medium | Axis order is canonical (`DEMOGRAPHIC_ATTRIBUTES`); missing attributes simply don't get a spoke. Document this in verification step. |
| NaN `chi_sq_p` silently plotted as 0 misleads user | Low | Medium | Open-circle scatter marker explicitly flags NaN positions |

---

## References

- Related plan: `docs/development/plans/active/comparison-pipeline-outputs.md` (in progress; this radar chart is a natural follow-on extending the same script)
- Critical file: `scripts/compare_populations.py` (lines 26, 290, 549, 642, 667, 681, 721)

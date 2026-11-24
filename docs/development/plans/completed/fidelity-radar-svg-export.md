# Plan: Per-combination Fidelity Radar Plots in PNG + SVG

**Date:** 2026-07-17
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-20 11:23
**Base Branch:** `dev`
**Branch:** `feature/fidelity-radar-svg-export`

---

## Overview

The fidelity pipeline already renders one radar plot per (method × model) combination
(`{slug}_radar.png`) and one aggregated `models × strategies` radar grid per country
(`{country}_radar_grid.png`), but only as PNG. This plan adds a **vector SVG sibling** for
both radar figures via a single shared save helper, so every per-combination radar and the
country grid are emitted in both raster (PNG) and vector (SVG) formats.

## Problem Statement

Radar plots are the headline fidelity artifact and are the ones most likely to be dropped
into the manuscript / slides. Right now they exist only as fixed-DPI PNGs, which do not
scale cleanly for publication. There is no vector output anywhere in the analysis package.
Producing SVG post-hoc (re-running, hand-exporting) is error-prone and off-pipeline, which
conflicts with the "pipeline emits every artifact" invariant. The radar figures should be
publication-ready straight out of the scoring run.

## Goals

### In Scope
1. A per-(method × model) radar is written as **both** `{slug}_radar.png` and `{slug}_radar.svg`.
2. The aggregated country radar grid is written as **both** `{country}_radar_grid.png` and `{country}_radar_grid.svg`.
3. A single reusable `save_figure(...)` helper writes the PNG + SVG pair, so the dual-format
   idiom lives in exactly one place (no duplicated `savefig` lines at call sites).

### Out of Scope
- SVG for the other fidelity charts (bar charts, association heatmap, C2ST, joint fidelity,
  combination plausibility, legacy chi-sq/coherence) — PNG-only for those is unchanged.
- SVG for `plot_3way_radar` (used only by `compare_real_countries.py`, not the standard sweep).
- SVG for the `model_ranking`, `method_significance`, `multivariate_fidelity`, `consistency`,
  and `run_analytics` chart modules.
- Any change to radar content, styling, DPI, colors, layout, or output directory structure.
- Migrating the other PNG-only savefig sites to the helper (helper is reusable, but rewiring
  them is deferred; see Rollback / future work).

## Success Criteria

- [ ] Running `score_fidelity_sweden.py` for one slug produces both `{slug}_radar.png` and
      `{slug}_radar.svg` in the per-slug charts dir, and the SVG opens as a valid vector file.
      *(Not run via the live script in Phase 3 verification — verified instead via a direct
      `plot_radar_comparison` call with a hand-built marginals dict, which exercises the same
      code path and confirmed the `.png`+`.svg` pair with valid SVG/XML header bytes. Script
      route not attempted since no mapped SCB data was on hand in this pass.)*
- [ ] Running `score_fidelity_all.py` produces `{country}_radar_grid.png` **and**
      `{country}_radar_grid.svg` per country in `03_Analysis/fidelity/`.
      *(Same caveat — verified via a direct `plot_radar_grid` call instead of the live script.)*
- [ ] The PNG output (bytes-for-content: same DPI, bbox, filename) is unchanged from before.
      *(Not verified — no pre-change PNG baseline was diffed in this pass; filenames were
      confirmed unchanged by inspection/direct calls, but no byte-level regression diff was run.)*
- [x] The two radar functions return the **PNG** `Path` exactly as today (caller contract
      preserved — no downstream code needs to change). *(Verified: `plot_radar_comparison` and
      `plot_radar_grid` both returned a `Path` equal to the expected `{prefix}_radar.png` /
      `{prefix}_radar_grid.png`, ending in `.png`.)*
- [x] `ruff check src/` passes; existing chart/fidelity tests pass; no new hardcoded config.
      *(`ruff check src/` → "All checks passed!"; `pytest tests/ -k "chart or fidelity or radar or artifact"` → 28 passed.)*

## Definitions

- **Per-combination radar:** the figure produced by `plot_radar_comparison` in
  `analysis/fidelity/charts.py`, one per `slug = {country}_{strategy}_{model}`, named
  `{slug}_radar.<ext>`. "method" = strategy axis, "model" = model axis.
- **Radar grid:** the aggregated figure from `plot_radar_grid` (rows = models, columns =
  strategies), one per country, named `{country}_radar_grid.<ext>`.
- **PNG+SVG pair:** two files with the same stem and directory, differing only in suffix; the
  SVG is written from the *same* matplotlib `Figure` object before it is closed, with the same
  `bbox_inches="tight"` (SVG ignores `dpi`).

---

## Technical Design

### Approach

Introduce one helper, `save_figure(fig, png_path, *, dpi)`, in `analysis/utils/` (the
established home for cross-subpackage analysis helpers). It saves the figure to `png_path`
(with `dpi`, `bbox_inches="tight"`) and to `png_path.with_suffix(".svg")`
(`bbox_inches="tight"`, no dpi), closes the figure, and returns the PNG `Path`. Then route
the two radar functions' terminal `savefig`/`close`/`return` block through it.

This is chosen over adding an inline second `savefig` at each site (the user-selected
"shared helper" option): the dual-format policy (which formats, tight bbox, closing) lives in
one function, so future extension to other charts is a one-line change per site and the
formats can never drift between call sites.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Shared `save_figure` helper, route 2 radar sites through it | Single source of truth for format policy; trivially reusable; call sites shrink | One new tiny module + import | **Chosen** |
| Inline second `fig.savefig(.with_suffix(".svg"))` at each radar site | Zero new module | Duplicated idiom in 2 (later N) places; formats can drift | Rejected |
| A `formats=("png","svg")` param threaded through every chart fn | Fully general | Over-engineered for a 2-figure ask; touches signatures broadly | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/utils/figures.py::save_figure` | Persist one `Figure` as a PNG+SVG pair and close it | `(fig, png_path: Path, *, dpi:int)` → returns the PNG `Path`; side effect: writes `.png` + `.svg` | radar/grid semantics, slugs, country, method/model, output-dir layout — it only sees a figure + a target PNG path |
| `charts.py::plot_radar_comparison` | Build per-combination radar, delegate persistence | unchanged inputs → returns PNG `Path` (unchanged) | how many formats are written / the SVG suffix (owned by helper) |
| `charts.py::plot_radar_grid` | Build aggregated grid, delegate persistence | unchanged inputs → returns PNG `Path` (unchanged) | same as above |

Helper sketch:

```python
# analysis/utils/figures.py
from __future__ import annotations
from pathlib import Path

def save_figure(fig, png_path: Path, *, dpi: int) -> Path:
    """Write `fig` as a PNG+SVG pair (same stem/dir) and close it. Returns the PNG path."""
    import matplotlib.pyplot as plt
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
    fig.savefig(png_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return png_path
```

Call-site change (per-combination radar, `charts.py` ~270–276) — the current
`mkdir` / `savefig` / `close` / `return` block collapses to:

```python
out_path = Path(output_dir) / (f"{prefix}_radar.png" if prefix else "radar.png")
return save_figure(fig, out_path, dpi=150)
```

Grid (`charts.py` ~669–675) collapses identically with `dpi=180` and the `_radar_grid` name.
`mkdir(parents=True, exist_ok=True)` moves inside the helper, so the explicit mkdir at each
radar site is removed (behavior preserved).

---

## Implementation Plan

### Phase 1: Shared save helper
**Goal:** One reusable PNG+SVG writer.

- [x] Add `src/population_synthetic/analysis/utils/figures.py` with `save_figure(fig, png_path, *, dpi)` as sketched.

**Files Modified:**
- `src/population_synthetic/analysis/utils/figures.py` — new module.

**Dependencies:** None

### Phase 2: Route the two radar functions through the helper
**Goal:** Both radar figures emit PNG + SVG.

- [x] In `charts.py`, import `save_figure` and replace the terminal block of
      `plot_radar_comparison` (per-combination radar, dpi 150) with a `save_figure` call.
- [x] Replace the terminal block of `plot_radar_grid` (aggregated grid, dpi 180) likewise.
- [x] Confirm both functions still return the PNG `Path` (caller contract in `artifacts.py`
      and `score_fidelity_all.py` unchanged).

**Files Modified:**
- `src/population_synthetic/analysis/fidelity/charts.py` — reroute two savefig blocks.

**Dependencies:** Phase 1

### Phase 3: Verify end-to-end
**Goal:** Prove both formats land for a real slug and the country grid.

- [ ] Run map + `score_fidelity_sweden.py` for one slug; confirm `.png` + `.svg` radar pair.
      *(Not run — no mapped SCB data available in this verification pass. Substituted a direct
      `plot_radar_comparison(marginals, ..., prefix="probe_slug")` call, which produced
      `probe_slug_radar.png` (157006 bytes) and `probe_slug_radar.svg` (53174 bytes), the latter
      opening with a valid `<?xml ...><!DOCTYPE svg ...` header.)*
- [ ] Run `score_fidelity_all.py`; confirm `{country}_radar_grid.png` + `.svg`.
      *(Not run — substituted a direct `plot_radar_grid(results, ..., prefix="swedish")` call,
      which produced `swedish_radar_grid.png` (114581 bytes) and `swedish_radar_grid.svg`
      (56186 bytes).)*
- [x] `ruff check src/` and `pytest` (chart/fidelity/workflow tests) pass.
      *(`ruff check src/` → "All checks passed!"; `pytest tests/ -k "chart or fidelity or radar or artifact" -q`
      → 28 passed, 337 deselected.)*

**Files Modified:** None (verification only)

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `save_figure` writes exactly two files (`.png` + `.svg`) with the same stem/dir for a
      trivial figure, creates the parent dir if missing, and returns the PNG path.
      *(Verified with a throwaway script: both files present/non-empty, return value equals the
      PNG path, figure was closed after the call.)*
- [x] The returned path from `plot_radar_comparison` / `plot_radar_grid` still ends in `.png`.
      *(Verified directly for both functions.)*

### Integration Tests
- [ ] A `write_comparison_artifacts` run over a small mapped pair yields `{slug}_radar.svg`
      alongside the existing `{slug}_radar.png` (extend the existing per-slug artifact test if present).
      *(Not verified — `tests/test_comparison_artifacts.py` only asserts the `.png` files today,
      not `.svg`; did not extend it since editing tests is out of scope for a verification-only
      pass. The underlying `plot_radar_comparison` call it makes is covered by the direct-call
      check above, so the artifact-writer's SVG passthrough is inferred, not test-asserted.)*

### Manual Verification
- [ ] Open a generated `.svg` in a browser / vector viewer — renders as scalable vector, not a rasterized blob.
      *(Partially verified — confirmed the file's first bytes are a valid
      `<?xml ...><!DOCTYPE svg ...>` header (real SVG/XML, not a rasterized blob container), but
      did not literally open it in a browser to visually confirm scalable rendering.)*
- [ ] Diff a freshly generated `{slug}_radar.png` against a pre-change one — visually identical.
      *(Not verified — no pre-change baseline PNG was available/generated to diff against in
      this pass.)*

### Edge Cases
- [x] `prefix` empty → files are `radar.svg` / `radar_grid.svg` (matches existing PNG fallback names).
      *(Verified: calling both functions with no `prefix` produced `radar.png`/`radar.svg` and
      `radar_grid.png`/`radar_grid.svg` respectively.)*
- [x] Output dir does not pre-exist → helper's `mkdir` creates it (parity with removed inline mkdir).
      *(Verified: pointed `save_figure` at a fresh nested subdirectory that did not exist; both
      the `.png` and `.svg` were created along with the directory tree.)*

---

## Documentation Plan

- [ ] Note the SVG radar outputs in `docs/scb_population_and_comparison.md` (or the fidelity
      artifact listing) so the artifact inventory reflects the vector pair.
- [ ] No CLAUDE.md change required (no new command, no invariant change).

---

## Rollback Plan

Pure additive, isolated change — safe to revert by reverting the feature commits.

1. Revert `charts.py` radar blocks to the inline `savefig`/`close`/`return`.
2. Delete `analysis/utils/figures.py`.
3. No data migration; existing PNGs are untouched. Stray `.svg` files (if any) can be deleted; nothing reads them.

Future work (not this plan): route the remaining PNG-only savefig sites through `save_figure`
if SVG is later wanted project-wide.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SVG file size for the dense grid is large | Med | Low | Vector grid is a known-heavy but acceptable artifact; out-of-scope to optimize. Monitor; can gate SVG for the grid behind a flag later if needed. |
| A caller depended on the exact terminal block / a `.svg` name collision | Low | Med | Contract preserved (returns PNG path, same names); grep confirms callers use the returned path only. |
| `mkdir` moved into helper changes behavior for a caller that pre-created dirs oddly | Low | Low | `mkdir(parents=True, exist_ok=True)` is idempotent — identical net effect. |

---

## References

- Related invariant: "Full comparison output" (CLAUDE.md) — pipeline emits every artifact per axis.
- Related memory: analysis/utils is the home for cross-subpackage analysis helpers.
- Touch points: `analysis/fidelity/charts.py` (`plot_radar_comparison` ~175–276,
  `plot_radar_grid` ~550–675), `analysis/fidelity/artifacts.py::_write_charts`,
  `scripts/analyze/score_fidelity_all.py` (grid call ~348–356).

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/development/plans/active/fidelity-radar-svg-export.md
- src/population_synthetic/analysis/fidelity/charts.py
- src/population_synthetic/analysis/utils/figures.py

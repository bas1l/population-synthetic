# Brainstorm: Manuscript fidelity heatmap-tables (models + methods)

**Started:** 2026-07-20   **Last matured:** 2026-07-20   **Status:** Handed off
**Plan:** `docs/development/plans/pending/manuscript-fidelity-tables.md`

## Real goal (north star)
Produce **manuscript-grade** heatmap-tables that let a reader see at a glance which
model (and separately, which method/strategy) achieves the best per-category and overall
demographic fidelity. Primary message: **"model X is best overall."** A companion table
carries the method comparison (supports the existing strategy>model finding indirectly by
letting readers compare method rows).

## Where it stands
Two companion tables, both TV-similarity (=1-TV-distance) heatmaps, rows sorted by an
"overall" column (mean over the demographic axes), best cell per column highlighted:

- **Table 1 — Models.** Rows = models, columns = 14 SCB demographic axes + Overall.
  **Fixed to the best strategy only** (see Open Q1: single global-best strategy vs each
  model at its own best). Provenance encoded: hosted/API (Claude/Gemini/OpenRouter) vs
  local (Ollama). Message: model X wins overall.
- **Table 2 — Methods.** Rows = strategies/methods, columns = same axes + Overall.
  Each cell = **mean across models** of that method's per-axis TV-similarity.

An almost-identical renderer already exists: `model_ranking/charts.py::plot_performance_heatmap`
(viridis, rank-sorted, overall column + divider, per-cell annotations, NaN grey). It reads
`{country}_performance.json`. New work is: (a) per-column best-cell highlight, (b) row
collapse to model-only / method-only, (c) provenance channel, (d) SVG via `save_figure`,
(e) the method-mean aggregation for Table 2.

## Alternatives on the table
- Restyle/extend `plot_performance_heatmap` in place vs author a separate manuscript renderer
  (leaning: separate, since manuscript needs colorblind+grayscale-safe styling distinct from
  the internal viridis artifact).
- Provenance as a row-label gutter band vs grouped blocks (hosted above / local below) vs marker.

## Threads explored
- **Real goal / target:** manuscript figure. (firmed)
- **The one message:** (a) model X best overall; table fixes the best strategy only. (firmed)
- **Rows:** Table 1 = models (best strategy); Table 2 = methods, cells = mean across models. (firmed)
- **Service-vs-self note:** = hosted/API models vs local Ollama models -> a provenance channel. (firmed)

## Locked decisions (2026-07-20)
- Best strategy = **one global-best strategy** applied to all model rows (apples-to-apples).
- Provenance shown by **row background in two different color families** (hosted vs local).
- Scope = **Sweden only**, metric = **TV-similarity**. => exactly 2 figures (models + methods).
- Methods table has NO provenance split (rows are strategies) -> single encoding there.

## Final design (matured 2026-07-20)
Two Sweden manuscript figures, TV-similarity, rows sorted by Overall (mean over 14 axes),
best-per-column cell = **bold + box**, routed through `utils/figures.save_figure` (PNG+SVG).

- **Table 1 — Models.** Rows = models at the single global-best strategy. Cols = 14 SCB axes
  + Overall. **Encoding (A): two sequential colormaps** — one hue family for hosted/API models
  (Claude/Gemini/OpenRouter), a different family for local (Ollama); cell darkness = TV-sim.
  Rows interleave by global Overall rank; the family hue reads provenance per row.
- **Table 2 — Methods.** Rows = strategies, cols = same axes + Overall. Each cell = mean across
  models of that method's per-axis TV-sim. Single sequential ramp (no provenance split).

Source: `{country}_performance.json` (model_ranking builder). New renderer modeled on
`plot_performance_heatmap`, adding: dual-colormap-by-provenance, best-per-column bold+box,
row collapse (models@best-strategy / methods-mean), method-mean aggregation, SVG output.

## Open questions
1. Global-best strategy selection rule = highest mean-over-models Overall TV-sim.
   (assumed; confirm at plan time). Which exact hue families for hosted vs local (e.g.
   Blues vs Oranges) — a styling detail, decide at implementation.

## Session log
- 2026-07-20: Framed intent; recon found existing near-identical renderer; locked target
  (manuscript), message (model X best, best strategy only), rows, and decoded service-vs-self
  as hosted-vs-local. Split into two companion tables (models; methods=mean over models).
- 2026-07-20: Matured. Locked Sweden-only + TV-sim (2 figures), one global-best strategy,
  encoding (A) dual-colormap-by-provenance, best-per-column bold+box. Design settled; buildable.

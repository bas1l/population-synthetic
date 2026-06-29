# Plan: Run Analytics Charts

**Date:** 2026-06-01
**Author:** Basil
**Status:** Implementation complete (Phases 1–5) — pending commit + branch close-out (see "What's left")
**Base Branch:** `dev`
**Branch:** `feature/run-analytics-preprocessor`

---

## Context

`analyze_run.py` currently produces console tables and JSON export only. Matplotlib is already a core dependency and the project has an established charting pattern in `comparison/charts.py`. This plan adds a `charts.py` module to the `analysis` sub-package and a `--charts DIR` flag to `analyze_run.py`, generating up to 9 PNG charts from the `compute_metrics()` output.

**Scope expanded (2026-06-01):** beyond per-run charts, the plan now also (a)
restructures the output so `llm_metrics` is a single master folder under
`03_Analysis` with one slug subfolder per run (Phase 3), (b) adds a `--all` batch
mode (Phase 3), and (c) adds a **cross-run scientific comparison** of metrics
across models and methods — box plots / heatmaps with Kruskal-Wallis + Dunn
significance testing (Phase 4), plus a token/timing join fix uncovered while
running it (Phase 5). See those phases and the Outcomes section below.

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `src/population_synth/analysis/charts.py` | Create — new charting module |
| `scripts/analyze_run.py` | Modify — add `--charts DIR` flag and call site |
| `config/analyze_defaults.yaml` | Create — output path config for the script |

No changes to `pyproject.toml` (matplotlib >= 3.8 is already a core dependency) or `__init__.py`.

---

## Pattern to Follow

Mirror `src/population_synth/comparison/charts.py` exactly:
- Defer matplotlib import **inside each function body** (not at module level):
  ```python
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  ```
- Save: `fig.savefig(out_path, dpi=150, bbox_inches="tight")`
- Cleanup: `plt.close(fig)` — always, even on early return (place all guards before `fig, ax = plt.subplots(...)`)
- Directory: `output_dir.mkdir(parents=True, exist_ok=True)` in each function

Color constants at module level (no matplotlib import needed there):
```python
_COLOR_BLUE   = "#4878CF"   # prompt tokens / primary
_COLOR_ORANGE = "#E8935A"   # completion tokens / secondary
_COLOR_RED    = "#D65F5F"   # retry / warning metric
_COLOR_GREEN  = "#6AB187"   # median latency
_COLOR_YELLOW = "#E9C46A"   # p95 latency
```

---

## Charts (9 total)

Each private function: `_plot_<name>(metrics: dict, output_dir: Path) -> Path | None`

### Always-available (no token data required)

| # | Filename | Type | Data source | Edge-case guards |
|---|----------|------|-------------|-----------------|
| 1 | `category_call_count.png` | Horizontal bar | `per_category[cat]["call_count"]`, sorted descending | skip if `per_category` empty |
| 2 | `category_retry_rate.png` | Horizontal bar (red) | `per_category[cat]["retry_rate"]` | same; add dashed 10% reference line via `ax.axvline(0.10)` |
| 3 | `value_diversity_entropy.png` | Horizontal bar | `value_diversity[cat]["entropy_bits"]`, annotate with `(N unique)` | skip if `value_diversity` empty |
| 4 | `method_distribution.png` | Vertical bar | `method_distribution` | skip if empty; rotate x-tick labels 30° |
| 5 | `prompt_size_growth.png` | Line + band | Group `prompt_size_growth` list by `chain_position`, median per position; add p25–p75 fill if `total_personas > 1` | skip if list empty |
| 6 | `wall_clock_per_persona.png` | Horizontal bar | `wall_clock_per_persona`, filter `None` values | skip if ≤ 1 persona or all None |

### Token-gated (skip if key is `None`)

| # | Filename | Type | Data source |
|---|----------|------|-------------|
| 7 | `token_consumption_by_category.png` | Stacked horizontal bar | `token_consumption_per_category` — blue=prompt, orange=completion |
| 8 | `token_budget_by_step_type.png` | Grouped vertical bar | `token_budget_by_step_type` — two bars per step type |
| 9 | `latency_by_category.png` | Grouped horizontal bar (3 bars/cat) | `latency_by_category` — green=median, yellow=p95, red=max |

---

## Config: `config/analyze_defaults.yaml`

```yaml
output_base: "F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data"
analytics:
  analysis_subdir: "03_Analysis"
  task_subdir: "llm_metrics"        # master folder; slug subfolders nested inside
  json_filename: "run_analytics.json"
  charts_subdir: "charts"
  comparison_subdir: "_comparison"  # cross-run comparison output
  verbose: false
```

**Path derivation logic** (in `_derive_output_defaults`): when `run_dir` is directly under `{output_base}/01_Raw/`, the slug is `run_dir.name` and output lands at (note the **master-folder layout** — `llm_metrics` is a single folder directly under `03_Analysis`, with one subfolder per slug nested inside):
- JSON → `{output_base}/03_Analysis/llm_metrics/{slug}/run_analytics.json`
- Charts → `{output_base}/03_Analysis/llm_metrics/{slug}/charts/`

CLI flags `--output` and `--charts` always override these defaults.

---

## Implementation Plan

### Phase 1: Charts module
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] Create `src/population_synth/analysis/charts.py` with all 9 chart functions and `plot_run_charts()` entry point
- [x] Wire `--charts DIR` flag into `scripts/analyze_run.py`
- [x] Fix Windows cp1252 encoding issue: replace `─` with `-` in console table separators

### Phase 2: Config and output path wiring
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] Create `config/analyze_defaults.yaml` with `output_base` and `llm_metrics` task subdir
- [x] Add `_load_config()` and `_derive_output_defaults()` to `scripts/analyze_run.py`
- [x] Auto-derive `--output` and `--charts` defaults when `run_dir` is under `01_Raw/{slug}`
- [x] Rename task subfolder to `llm_metrics`

### Phase 3: Master folder + batch mode
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] Restructure layout so `llm_metrics` is a master folder under `03_Analysis` with slug subfolders nested inside (`_derive_output_defaults`)
- [x] Add `--all` flag to `analyze_run.py`: discover all subdirs of `{output_base}/01_Raw/`, process each into `llm_metrics/{slug}/`, print a per-run summary
- [x] Gracefully skip dirs with no interaction files (print skip list — no silent skips)
- [x] Print final summary: N runs processed, N skipped, total charts written

### Phase 4: Cross-run scientific comparison
**Started:** 2026-06-01
**Completed:** 2026-06-01

Compare metric values across the two experimental factors — **model** and
**method/strategy** (country fixed) — with publication-style box plots,
mean±SD bars, model×method heatmaps, and Kruskal-Wallis + Dunn (Holm-corrected)
significance testing.

- [x] `src/population_synth/analysis/run_comparison.py` — slug decomposition via axis registries (`discover_axis_values`), `extract_comparison_metrics`, `kruskal_test`, inline `dunn_posthoc` (no `scikit-posthocs`), `build_comparison`, `write_comparison_json`
- [x] `src/population_synth/analysis/comparison_charts.py` — box plots with significance brackets (capped, omissions logged), grouped bars, heatmaps; `plot_run_comparison()` entry point
- [x] `scripts/compare_runs.py` — CLI reading `llm_metrics/*/run_analytics.json`, writing `_comparison/comparison.json` + `_comparison/charts/`
- Metrics compared: retry_rate, error_rate, success_rate, wall_clock, value_diversity, tokens_per_persona (token-gated), latency (token-gated)

### Phase 5: Token/timing join fix (discovered during real-data run)
**Started:** 2026-06-01
**Completed:** 2026-06-01

**Symptom:** First full `compare_runs.py` reported `tokens_per_persona` and
`latency` as *"no runs carry token/timing data"* even though Ollama runs clearly
log `ollama call: ... elapsed_ms=.. prompt_tokens=.. completion_tokens=..` lines.

**Root cause (pre-existing bug, not in the new comparison code):** token/timing
data lives only in the **log files**, joined to JSONL entries by timestamp
(`log_parser.py` → `joiner.py`). Parallel runs write a **single top-level master
log** at `01_Raw/{slug}/logs/run_*.log`; the `persona_*/` dirs contain only
`identity.json` + `llm_interactions.json` and **no `logs/` of their own**.
`_process_batch_dir` joined logs *per-persona* (finding nothing) and parsed the
master log **only** for the `Done in…` summary — the master log's call records
(the token data) were built into a list and discarded, never joined. So
`has_token_data` was `False` for every parallel run.

- [x] Fix `_process_batch_dir` in `scripts/analyze_run.py`: when a top-level
  master log exists, `join_entries(all_entries, top_level_log_entries)` so the
  token/latency fields populate. (One-line-ish change; the parse was already there.)
- [x] Verified on `swedish_all_pick_ollama_qwen3_14b`: `token_match_rate` 1.0,
  100 personas with tokens, 17 latency categories.

**Known caveat (by design, documented in code comment):** the join matches by
±2 s timestamp proximity. In parallel runs, interleaved worker calls mean a
record can attach to the *wrong persona's* entry. Aggregate / per-category token
& latency distributions (what the comparison consumes) are sound; **exact
per-persona token sums are approximate.** Claude/Gemini runs legitimately have
no token counts (CLI doesn't report them), so token metrics there stay empty —
correct, not a bug.

---

## Verification

Phase 1–2 verified on `01_Raw/seed_022_all_pick_sonnet` (100 personas, 1700 entries):
- JSON + 6 charts written under the per-run task folder ✓
- Token-gated charts correctly skipped (no log data for Claude runs) ✓
- Config defaults kicked in automatically — no CLI flags needed ✓

Phase 3–4 (new layout + comparison):
1. `python scripts/analyze_run.py "<output_base>/01_Raw/<slug>"` → JSON+charts under `03_Analysis/llm_metrics/<slug>/`
2. `python scripts/analyze_run.py --all` → one `llm_metrics/{slug}/run_analytics.json` per decodable run; legacy `seed_*` dirs listed as skipped
3. `python scripts/compare_runs.py` → `llm_metrics/_comparison/comparison.json` + box/bar/heatmap PNGs; Kruskal-Wallis H/p in box-plot titles with Dunn significance brackets
4. Slug decomposition + stats pipeline smoke-tested with synthetic records (Kruskal detects injected differences; JSON round-trips) ✓
5. `ruff check src/ scripts/` clean ✓ (the 44 remaining ruff errors are all pre-existing `gui/` issues, untouched)

---

## Outcomes — full real-data run (2026-06-01)

Ran `analyze_run.py --all` then `compare_runs.py` against the live output tree.

**Batch (`--all`):** 49 runs processed, 4 skipped (no interaction data:
`psychiatrists_questionnaires_001`, `seed_000`,
`seed_037_all_generate_evaluate_random_pick_llama33`,
`swedish_all_generate_evaluate_random_pick_ollama_llama33_70b`). 284 per-run
charts written (Ollama runs now emit 9 each incl. the 3 token-gated charts;
Claude runs 6). Output under `03_Analysis/llm_metrics/{slug}/`.

**Comparison:** 28 decodable runs = **7 models × 5 methods** (all `swedish`).
21 legacy `seed_*` / `test_*` dirs skipped as "slug not decomposable" (expected —
not axis-composed). Artifacts:
`03_Analysis/llm_metrics/_comparison/comparison.json` (+ 35 charts under
`_comparison/charts/`: each of 7 metrics × {by_model box+bar, by_method box+bar,
heatmap}).

Kruskal-Wallis omnibus results (H, p, # significant Holm-corrected Dunn pairs):

| Metric | By model | By method |
|--------|----------|-----------|
| retry_rate | H=176, p=2.5e-35 (12) | H=55, p=2.9e-11 (8) |
| error_rate | H=14, p=0.029 (0) | H=3.0, p=0.55 (0) |
| success_rate | H=22, p=0.0012 (6) | H=2.3, p=0.68 (0) |
| wall_clock | H=1368, p=2.3e-292 (19) | H=746, p=3.2e-160 (10) |
| value_diversity | H=49, p=9.3e-09 (7) | H=220, p=1.6e-46 (7) |
| tokens_per_persona | H=407, p=8.1e-86 (11) | H=1491, p≈0 (10) |
| latency | H=293, p=4.0e-61 (13) | H=87, p=6.5e-18 (8) |

Reading: **model choice dominates** speed/retries/reliability/cost; **method
choice** dominates output diversity and (strongly) token volume. error_rate shows
no significant pairwise differences either way.

---

## What's left / follow-ups for next session

Nothing in the original plan is outstanding (Phases 1–5 done). Candidate
follow-ups, not yet started:

- [ ] **Decide branch close-out:** run `/plan-finish` to move this plan to
  `completed/`, merge `feature/run-analytics-preprocessor` into `dev` (`--no-ff`),
  delete the branch. Not done yet — commits are also still pending (working tree
  has the new files uncommitted; see `Modified Files`).
- [ ] **Per-persona token accuracy:** the ±2 s timestamp join blurs cross-persona
  attribution in parallel runs. If exact per-persona token sums ever matter,
  write per-persona logs at generation time (in the generator), or embed token
  counts directly in `llm_interactions.json` so no timestamp join is needed.
  Current comparison only needs aggregate/category distributions, so low priority.
- [ ] **Legacy `seed_*` runs excluded from comparison:** 21 dirs are skipped
  because their slugs aren't `{country}_{strategy}_{model}`. If we want them in,
  add an alias/override map or a `--slug-map` file. Currently intentional.
- [ ] **Significance-bracket clutter:** box plots cap brackets at
  `_MAX_BRACKETS = 8` (omissions logged + annotated; full pairwise p-values in
  the JSON). If a cleaner many-group display is wanted later, consider a compact
  letter display (CLD) instead of brackets.
- [ ] **Country axis:** only `swedish` exists today, so "two-way" is really
  model × method. If more countries are added, `--country` already filters, but
  a 3-way (country × model × method) view would need new figures.
- [ ] **Optional:** expose `_MAX_BRACKETS` and the box/bar/heatmap selection as
  CLI flags on `compare_runs.py` if output volume needs tuning.

### Context needed to resume
- **Branch:** `feature/run-analytics-preprocessor` (base `dev`). Work is
  **uncommitted**.
- **Output tree (not in repo):** `output_base` =
  `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`. Runs in `01_Raw/{slug}`,
  analytics in `03_Analysis/llm_metrics/{slug}/`, comparison in
  `03_Analysis/llm_metrics/_comparison/`. Config: `config/analyze_defaults.yaml`.
- **Re-run from scratch:** `python scripts/analyze_run.py --all` then
  `python scripts/compare_runs.py`. (compare reads the per-run JSONs, so `--all`
  must run first whenever runs change.)
- **Axis IDs** (drive slug decomposition) come from `config/{models,strategies,
  countries}/*.yaml` via `discover_axis_values` — adding a model/strategy YAML is
  enough for new runs to be picked up.
- **Metric definitions / stats live in** `src/population_synth/analysis/run_comparison.py`
  (`METRIC_SPECS`, `kruskal_test`, `dunn_posthoc`); **charts in**
  `comparison_charts.py` (`plot_run_comparison`).

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/analyze_defaults.yaml
- docs/development/plans/active/run-analytics-charts.md
- scripts/analyze_run.py
- scripts/compare_runs.py
- src/population_synth/analysis/charts.py
- src/population_synth/analysis/comparison_charts.py
- src/population_synth/analysis/run_comparison.py

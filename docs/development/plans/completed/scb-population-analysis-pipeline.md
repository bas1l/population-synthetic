# Plan: SCB Population Analysis Pipeline

**Date:** 2026-05-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-employment-education-correlation`
**Branch:** `feature/scb-employment-education-correlation`

---

## Overview

Create a CLI script that reads a generated SCB population JSON and produces distribution plots for every demographic dimension — both marginal distributions (one plot per attribute) and cross-tabulation plots (grouped/stacked bars for conditioned attribute pairs). All outputs are saved to `data/analysis/<input_stem>/` for post-hoc inspection.

## Problem Statement

The SCB population generator (`scripts/generate_scb_population.py`) produces JSON files with up to 18 demographic attributes per individual, but there is no way to visually inspect the distribution of a generated population. Analysts must manually aggregate and plot data to verify the generator is producing realistic distributions. This slows down iteration on the sampling chain and makes it hard to spot distributional anomalies.

## Goals

### In Scope
1. Marginal distribution plots for all 18 demographic attributes (appropriate chart type per attribute)
2. Cross-tabulation plots for key conditioned pairs (e.g., education by sex, employment by education, civil status by age group)
3. A summary dashboard PNG (grid of all marginal plots)
4. Individual high-resolution PNGs for each plot
5. Output organized into `data/analysis/<input_stem>/` with `marginal/` and `cross/` subdirectories
6. CLI with argparse, consistent with existing script conventions

### Out of Scope
- Interactive/web-based dashboards
- Comparison between two populations (already handled by `compare_populations.py`)
- Statistical tests (chi-squared, KL divergence — already in `compare_populations.py`)
- Modifications to the generator or existing scripts

## Success Criteria

- [ ] `python scripts/analyze_scb_population.py <population.json>` runs without error
- [ ] Output directory `data/analysis/<input_stem>/` contains `summary_dashboard.png`
- [ ] Output directory contains one PNG per present dimension in `marginal/`
- [ ] Output directory contains cross-tabulation PNGs in `cross/`
- [ ] Plots are readable: no overlapping labels, counts and percentages annotated
- [ ] Script handles older population files (missing dimensions) gracefully

---

## Technical Design

### Approach

Single new script `scripts/analyze_scb_population.py` driven by a `DIMENSION_CONFIG` dictionary that maps each attribute to its plot type, title, category order, and color. A separate `CROSS_TABULATIONS` list defines which attribute pairs to plot as grouped/stacked bars. The script uses matplotlib (Agg backend) + seaborn, consistent with existing project patterns.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Single script with config dict | Simple, self-contained, consistent with project | All logic in one file | **Chosen** — matches `compare_populations.py` pattern |
| Module in `anxiety_synthetic/` | Reusable, testable | Over-engineered for a plotting script | Rejected |
| Jupyter notebook | Interactive exploration | Not CLI-friendly, not in project conventions | Rejected |

### Architecture Changes

No changes to existing architecture. One new file added:

```
scripts/
  analyze_scb_population.py    # NEW

data/
  analysis/                    # NEW — output directory (git-ignored)
    scb_population_pop-10000_seed-12531/
      summary_dashboard.png
      marginal/
        age.png
        age_group.png
        ...
      cross/
        education_level_by_biological_sex.png
        employment_status_by_education_level.png
        ...
```

### Plot Type Decisions

**Marginal distributions:**

| Attribute | Plot Type | Notes |
|-----------|-----------|-------|
| `age` | Histogram + KDE | Continuous; 20 bins |
| `age_group` | Ordered bar | Order from `constants.AGE_GROUP_BOUNDS` |
| `biological_sex` | Bar | 2 categories |
| `education_level` | Ordered bar | Order from `constants.EDUCATION_LABELS` |
| `employment_status` | Ordered bar | Employed, Unemployed, Student, Retired |
| `birth_location` | Bar | |
| `ethnicity` | Bar | |
| `region` | Horizontal bar (sorted) | 21 counties — horizontal avoids label overlap |
| `current_environment_type` | Ordered bar | Urban > Suburban > Rural |
| `socioeconomic_class` | Ordered bar | Poverty > Working Class > Middle Class > Wealthy |
| `parental_structure` | Bar | |
| `civil_status` | Bar | |
| `industry_sector` | Horizontal bar (sorted) | Long labels, many categories |
| `employment_type` | Horizontal bar (sorted) | Long labels |
| `housing_tenure` | Horizontal bar (sorted) | Long labels |
| `household_size` | Ordered bar | 1 > 2 > 3-4 > 5+ |
| `income_source` | Bar | |
| `birth_country_detail` | Horizontal bar (sorted) | |

All bar charts annotate each bar with count and percentage.

**Cross-tabulations:**

| Pair | Plot Type | Rationale |
|------|-----------|-----------|
| `education_level` × `biological_sex` | Grouped bar | Generator conditions education on sex |
| `employment_status` × `education_level` | Grouped bar | Generator conditions employment on education |
| `employment_status` × `biological_sex` | Grouped bar | Generator conditions employment on sex |
| `civil_status` × `age_group` | Stacked bar (normalized) | Civil status varies strongly by age |
| `income_source` × `employment_status` | Grouped bar | Generator conditions income source on employment |
| `industry_sector` × `biological_sex` | Horizontal grouped bar | Many categories, long labels |
| `employment_type` × `biological_sex` | Horizontal grouped bar | Conditioned in generator |

### Key Design Decisions

1. **Config-driven** — `DIMENSION_CONFIG` dict centralizes all per-dimension decisions (plot type, title, order, color). Adding a new dimension means adding one dict entry.
2. **Reuse canonical orderings** from `scb_population/constants.py` and `compare_populations.py`'s `DEMOGRAPHIC_ATTRIBUTES` list.
3. **`matplotlib.use("Agg")`** — non-interactive backend; plots are saved, not displayed.
4. **Seaborn `whitegrid` style** — consistent with project's statistical character.
5. **Graceful degradation** — missing dimensions are skipped with a log warning; dashboard grid adapts dynamically.

---

## Implementation Plan

### Phase 1: Core Marginal Plotting
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Script produces individual marginal distribution plots for all present dimensions.

**Tasks:**
- [x] Task 1.1 — Create `scripts/analyze_scb_population.py` with imports, logging, argparse
- [x] Task 1.2 — Define `DIMENSION_CONFIG` dict with plot type, title, order, and color per attribute
- [x] Task 1.3 — Implement `load_population(path) -> (metadata, DataFrame)`
- [x] Task 1.4 — Implement `plot_histogram(df, column, ax, config)` for `age`
- [x] Task 1.5 — Implement `plot_bar(df, column, ax, config)` for vertical bar charts
- [x] Task 1.6 — Implement `plot_hbar(df, column, ax, config)` for horizontal bar charts
- [x] Task 1.7 — Implement `plot_dimension(df, column, ax)` dispatcher
- [x] Task 1.8 — Implement `create_individual_plots(df, output_dir, metadata)` saving to `marginal/`
- [x] Task 1.9 — Wire up `main()` with argparse and output directory creation

**Files Modified:**
- `scripts/analyze_scb_population.py` — New file

**Dependencies:** None

### Phase 2: Summary Dashboard
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Script produces a single grid PNG showing all marginal distributions.

**Tasks:**
- [x] Task 2.1 — Implement `create_summary_dashboard(df, output_dir, metadata)` with dynamic grid sizing
- [x] Task 2.2 — Add metadata suptitle (n, seed, vintage)
- [x] Task 2.3 — Handle subplot font sizing for readability in grid

**Files Modified:**
- `scripts/analyze_scb_population.py`

**Dependencies:** Phase 1

### Phase 3: Cross-Tabulation Plots
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Script produces grouped/stacked bar charts for conditioned attribute pairs.

**Tasks:**
- [x] Task 3.1 — Define `CROSS_TABULATIONS` list of `(row_attr, col_attr, plot_type)` tuples
- [x] Task 3.2 — Implement `plot_grouped_bar(df, row_attr, col_attr, ax, config)` for vertical grouped bars
- [x] Task 3.3 — Implement `plot_grouped_hbar(df, row_attr, col_attr, ax, config)` for horizontal grouped bars
- [x] Task 3.4 — Implement `plot_stacked_bar(df, row_attr, col_attr, ax, config)` for normalized stacked bars
- [x] Task 3.5 — Implement `create_cross_plots(df, output_dir, metadata)` saving to `cross/`
- [x] Task 3.6 — Add `--no-cross` CLI flag

**Files Modified:**
- `scripts/analyze_scb_population.py`

**Dependencies:** Phase 1

### Phase 4: Git-ignore and Documentation
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Output directory is git-ignored; CLAUDE.md updated.

**Tasks:**
- [x] Task 4.1 — Add `data/analysis/` to `.gitignore`
- [x] Task 4.2 — Update `CLAUDE.md` Commands section with the new script usage

**Files Modified:**
- `.gitignore`
- `CLAUDE.md`

**Dependencies:** Phase 3

---

## Testing Plan

### Manual Verification
- [ ] Run `python scripts/analyze_scb_population.py scb_population_pop-10000_seed-12531.json` — confirm output directory created at `data/analysis/scb_population_pop-10000_seed-12531/`
- [ ] Verify `summary_dashboard.png` exists and all subplots are readable
- [ ] Verify `marginal/` contains one PNG per present dimension (17-18 files)
- [ ] Verify `cross/` contains 7 cross-tabulation PNGs
- [ ] Open individual plots — confirm count + percentage annotations, no label overlap
- [ ] Run with `--no-individual`, `--no-dashboard`, `--no-cross` flags — confirm expected outputs are skipped
- [ ] Run against a smaller/older population file — confirm graceful handling of missing dimensions

### Edge Cases
- [ ] Population file with only Phase 0 attributes (no region, civil_status, etc.) — should produce reduced dashboard
- [ ] Population file with `age` field missing — histogram skipped, age_group still plotted
- [ ] Cross-tabulation where one attribute is missing — pair skipped with log warning
- [ ] Very small population (n < 50) — plots still render without errors

---

## Documentation Plan

- [ ] Update `CLAUDE.md` Commands section with analysis script usage
- [ ] Add `data/analysis/` to `.gitignore`

---

## Rollback Plan

This is a purely additive change (one new script, one new git-ignored output directory). Rollback is simply deleting the script file.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Label overlap in summary dashboard with 18+ subplots | Medium | Low | Use horizontal bars for high-cardinality dims; reduce font size in grid; `tight_layout(pad=2.0)` |
| Long county names truncated in region plot | Low | Low | Horizontal bar chart with auto-sizing figure height |
| Cross-tabulation plots cluttered with many category combinations | Medium | Medium | Limit cross-tabs to the 7 most meaningful pairs; use normalized stacking where appropriate |

---

## References

- `scripts/compare_populations.py` — `DEMOGRAPHIC_ATTRIBUTES` list, `JOINT_PAIRS`, argparse pattern
- `scripts/generate_scb_population.py` — output JSON schema, script conventions
- `anxiety_synthetic/scb_population/constants.py` — canonical orderings (`AGE_GROUP_BOUNDS`, `EDUCATION_LABELS`)
- `anxiety_synthetic/utils/pipeline_monitor/pipeline_monitor_live_plotter.py` — matplotlib/seaborn patterns

---

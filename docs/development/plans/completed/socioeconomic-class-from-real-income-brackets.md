# Plan: Socioeconomic class from real income brackets (SCB + SSB)

**Date:** 2026-05-11
**Author:** Basil
**Status:** In Progress
**Started:** 2026-05-11
**Base Branch:** `feature/norway-ssb-population-generator`
**Branch:** `feature/socioeconomic-class-from-real-income-brackets`

---

## Overview

Replace the current decile-based `socioeconomic_class` step in both the SCB (Sweden) and SSB (Norway) population generators with **real population-by-income-bracket** PxWeb tables, and bin those brackets into Poverty / Working / Middle / Wealthy using **country-relative thresholds** (Eurostat at-risk-of-poverty + OECD/Pew "upper income" definitions). Sampling becomes conditional on `(age_group, sex)`.

## Problem Statement

The current scb02 reference Swedish population (`data/scb_api/scb_population_pop-10000_02.json`, n = 10 000) shows the four socioeconomic classes at ~20 % / 30 % / 30 % / 20 %. The Norwegian ssb01 dataset shows ~20.3 % / 30.7 % / 29.1 % / 19.9 %. These are **not real demographic distributions** — they are mathematically locked by construction:

1. Both generators query an **income-decile** table (SCB `HE0110F/TabVX10InkStrukt`, SSB `12682`). Income deciles are by definition 10 % of the population each — no real demographic signal is recoverable.
2. The decile→class mapping in `category_mappings.json` (SCB) and `constants.py` (SSB) groups deciles **2 / 3 / 3 / 2** into the four classes, so the output is fixed at 20 / 30 / 30 / 20 regardless of the data.
3. The SCB parser `parse_socioeconomic()` in `anxiety_synthetic/scb_population/parsers.py:575-591` explicitly discards the API `values` array and returns `1/N` per decile — a silent hardcoded uniform that **violates the project's "no hardcoded statistical data" rule**.
4. Sampling is a flat marginal (`sample_service.py:154` SCB, `sample_service.py:193` SSB) — no correlation with age, sex, education, or employment.

SCB's classical *SEI* occupational class scheme was discontinued in 2026 and is not exposed via PxWeb, so the viable path is population-by-income-bracket tables that **do** carry real demographic signal.

## Goals

### In Scope
1. Replace SCB `fetch_socioeconomic()` to query `HE/HE0110/HE0110A/SamForvInk1` (27 SEK-thousand brackets × age × sex × region, `ContentsCode = Number of persons`).
2. Replace SSB `fetch_socioeconomic()` to query table `06655` (14 NOK brackets × age × sex, `ContentsCode = Personar`).
3. Add a shared helper that computes the country median from bracket midpoints + counts and applies Eurostat/OECD multipliers to assign each bracket to a class.
4. Make `socioeconomic_class` sampling **conditional on `(age_group, sex_label)`** in both generators — same conditioning the samplers already use for education / civil_status / employment_type.
5. Both parsers raise loudly on missing dimensions, missing values, or empty per-cell distributions — no silent fallbacks.

### Out of Scope
- Re-running every existing comparison seed (007–013) against a new scb02 reference. The plan regenerates scb02/ssb02 and sanity-checks one seed; full pipeline-vs-reference re-evaluation is a follow-on task.
- Cross-country harmonised thresholds. Each country uses its own median in its own currency.
- Switching the underlying income concept to *equivalised disposable household income*. The selected tables (SCB SamForvInk1, SSB 06655) both report individual gross income; the relative-position classifier is still valid, with one inline caveat comment at the threshold definition.
- LLM prompt changes for `socioeconomic_class` in the identity pipeline (separate plan).
- Adding `socioeconomic_class` to the chatbot / report side.

## Success Criteria

- [ ] Fresh SCB population (n = 10 000, seed 42): `socioeconomic_class` marginal is **non-uniform** and **not locked at 20 / 30 / 30 / 20**. Wealthy share visibly below 25 %.
- [ ] Fresh SSB population (n = 10 000, seed 42): same — non-uniform, not 20 / 30 / 30 / 20.
- [ ] Conditional check: among the generated SCB personas, men aged 45–54 have a strictly higher Middle+Wealthy combined share than women aged 18–24.
- [ ] Both `parse_socioeconomic()` functions raise `ValueError` on a synthetic empty-response input (no silent uniform fallback).
- [ ] `python scripts/compare_populations.py scb_population_pop-10000_02.json scb_population_pop-10000_03.json` reports `socioeconomic_class.tv_distance > 0` (i.e. the new reference is structurally different from the artificial old one).
- [ ] `parse_socioeconomic` for SCB no longer returns `{label: 1.0/N}` — verified by grep absence of that pattern.

---

## Technical Design

### Approach

Switch both countries to **population-by-absolute-income-bracket** PxWeb tables that expose `(age × sex × bracket)` cells. Compute each country's median income from the bracket midpoints weighted by the bracket counts, then assign each bracket to one of four classes using country-relative multipliers of the median:

| Class          | Threshold              | Source                                                  |
|----------------|------------------------|---------------------------------------------------------|
| Poverty        | < 0.60 × median        | Eurostat at-risk-of-poverty rate (AROP)                  |
| Working Class  | 0.60 – 1.00 × median   | OECD lower-middle floor                                  |
| Middle Class   | 1.00 – 2.00 × median   | OECD middle band                                         |
| Wealthy        | ≥ 2.00 × median        | OECD upper-income / Pew upper-income                     |

A bracket that straddles a threshold is **split proportionally** by its width on each side, so the per-cell class distribution sums to exactly 1.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Keep deciles, fix the parser | One-line change | Output stays mathematically locked at 20/30/30/20 — same root problem | Rejected |
| Use SCB SEI (occupational class) | True class scheme | Discontinued by SCB in 2026, not in PxWeb | Rejected |
| Income brackets + Eurostat/OECD relative thresholds | Real demographic shape, official thresholds, conditional on age × sex | Income concept is gross individual income, not equivalised disposable — caveat noted in code | **Chosen** |
| Drop the field entirely | Cleanest per "no hardcoded data" rule | Loses a meaningful schema attribute used downstream by identity prompts | Rejected |
| Harmonised SEK ↔ NOK / PPP thresholds | Cross-country comparable | Adds FX/PPP complexity; out of scope here | Rejected |

### Architecture Changes

- **New shared utility** `anxiety_synthetic/utils/income_class.py` (~50 LOC) with two pure functions:
  - `median_from_brackets(midpoints: list[float], counts: list[float]) -> float`
  - `classify_brackets(edges: list[tuple[float, float]], counts: list[float], median: float) -> dict[str, float]` — returns a `{class_label: probability}` dict.
- **Schema change in both `PopulationDistributions` dataclasses**: `socioeconomic` becomes `dict[tuple[str, str], dict[str, float]]` keyed by `(age_group, sex_label)` instead of a flat marginal.
- **Two PxWeb tables newly queried**: `HE/HE0110/HE0110A/SamForvInk1` (Sweden) and `06655` (Norway). Existing decile fetch + parse code paths for socioeconomic are removed.
- **Sampler call sites updated** — both samplers already key on `(age_group, sex_label)` for several other attributes; this is one extra lookup.

```
anxiety_synthetic/
├── utils/
│   └── income_class.py                    # NEW — median + threshold helper
├── scb_population/
│   ├── constants.py                       # +INCOME_BRACKET_TABLE, bracket-edge metadata
│   ├── fetch_service.py                   # rewrite fetch_socioeconomic
│   ├── parsers.py                         # rewrite parse_socioeconomic
│   ├── sample_service.py                  # line 154: conditional draw
│   └── data.py                            # updated typing
└── ssb_population/
    ├── constants.py                       # SOCIOECONOMIC_TABLE 12682 → 06655, drop DESIL_CODES
    ├── fetch_service.py                   # rewrite fetch_socioeconomic
    ├── parsers.py                         # rewrite parse_socioeconomic (lines 945-973)
    └── sample_service.py                  # line 193: conditional draw

config/assets/
├── scb_reference/category_mappings.json   # socioeconomic section: remove decile codes, keep class labels
└── ssb_reference/category_mappings.json   # same
```

---

## Implementation Plan

### Phase 1: Shared helper + Sweden switch

**Goal:** Replace the SCB decile path end-to-end and verify the new shape on a fresh population.

- [x] Create `anxiety_synthetic/utils/income_class.py` with `median_from_brackets()` and `classify_brackets()`. Include one short comment at the threshold constants noting the equivalised-disposable caveat.
- [x] In `anxiety_synthetic/scb_population/constants.py`, add `INCOME_BRACKET_TABLE = "HE/HE0110/HE0110A/SamForvInk1"` plus a list of `(bracket_code, low_sek, high_sek)` triples covering the 27 SCB brackets (top bracket `1000+` treated as `[1_000_000, 1_500_000]` by convention — document the open-bracket midpoint choice in code).
- [x] Rewrite `fetch_service.fetch_socioeconomic()` to query the new table with `Region = "00"`, all sexes, all available age bands ≥ 20, all brackets, `ContentsCode = "Number of persons"`, `Tid = 2024` (or latest available).
- [x] Rewrite `parsers.parse_socioeconomic()` to return `dict[tuple[age_group, sex_label], dict[class_label, float]]`. Use the SCB age-band labels and map them to the pipeline's `VALID_AGE_GROUPS`. For ages 18-19 (pipeline floor), fall back to the youngest available band (`20-24`). Raise `ValueError` on missing dimensions or empty cells.
- [x] Update `scb_population/data.py` `PopulationDistributions.socioeconomic` typing.
- [x] Update `sample_service.py:154` to draw conditional on `(age_group, sex_label)` with a sex-fallback identical to the existing pattern used by education / civil_status.
- [x] Update `config/assets/scb_reference/category_mappings.json` socioeconomic section: drop the decile-code lists; keep only the four class `schema_label` entries (description text updated to reference income thresholds).

**Files Modified:**
- `anxiety_synthetic/utils/income_class.py` — new file
- `anxiety_synthetic/scb_population/constants.py` — new bracket constants
- `anxiety_synthetic/scb_population/fetch_service.py` — `fetch_socioeconomic` rewrite
- `anxiety_synthetic/scb_population/parsers.py` — `parse_socioeconomic` rewrite (lines 575-591)
- `anxiety_synthetic/scb_population/data.py` — typing update
- `anxiety_synthetic/scb_population/sample_service.py` — conditional draw (line 154)
- `config/assets/scb_reference/category_mappings.json` — mapping cleanup (lines 116-140)

**Dependencies:** None

### Phase 2: Norway switch

**Goal:** Apply the same fix to SSB using table `06655` and the shared helper.

- [x] Update `anxiety_synthetic/ssb_population/constants.py`: replace `SOCIOECONOMIC_TABLE = "12682"` with `SOCIOECONOMIC_TABLE = "06655"`. Drop the `DESIL_CODES` static map. Add `BRUTTOINN_BRACKETS = [...]` with `(code, low_nok, high_nok)` triples for the 9 NOK brackets — top bracket `2 000 000 kr og over` treated as `[2_000_000, 3_000_000]` by convention.
- [x] Rewrite `ssb_population/fetch_service.py::fetch_socioeconomic()` to query table `06655` with `BruttoInn` (all 9 brackets), `Alder` (all 6 bands: 17-24 / 25-34 / 35-44 / 45-54 / 55-66 / 67+), `Kjonn` (1, 2), `ContentsCode = "Personar"`, latest year (2024).
- [x] Rewrite `ssb_population/parsers.py::parse_socioeconomic()` to return `dict[tuple[str, str], dict[str, float]]` keyed by `(age_group, sex_label)` using `income_class` helper. Map SSB age bands to pipeline `VALID_AGE_GROUPS` (`17-24` → `18-24`; `25-34`, `35-44`, `45-54` direct; `55-66` → `55-64`; `67+` → `65-74`).
- [x] Update `ssb_population/sample_service.py` for conditional draw on `(age_group, sex_label)` with sex-fallback identical to the existing pattern used for education/civil_status.
- [x] Update `config/assets/ssb_reference/category_mappings.json` socioeconomic section: removed decile-code lists; kept the four class `schema_label` entries with descriptions referencing income thresholds.

**Files Modified:**
- `anxiety_synthetic/ssb_population/constants.py` — lines 200-219 rewrite
- `anxiety_synthetic/ssb_population/fetch_service.py` — `fetch_socioeconomic` rewrite
- `anxiety_synthetic/ssb_population/parsers.py` — `parse_socioeconomic` rewrite (lines 945-973)
- `anxiety_synthetic/ssb_population/sample_service.py` — conditional draw (line 193)
- `config/assets/ssb_reference/category_mappings.json` — mapping cleanup

**Dependencies:** Phase 1 (reuses `utils/income_class.py`)

### Phase 3: Regenerate references + sanity-check one seed

**Goal:** Produce fresh scb03 / ssb03 references, confirm the new distribution shape, spot-check one identity-pipeline seed against the new SCB reference.

- [x] `python scripts/generate_scb_population.py --n 10000 --seed 42 --output data/scb_api/scb_population_pop-10000_03.json`
- [x] `python scripts/generate_ssb_population.py --n 10000 --seed 42 --output data/ssb_api/ssb_population_pop-10000_03.json` (bug fix: SSB `parse_socioeconomic` `_AGE_BAND_MAP` `67+` now maps to both `"65-74"` and `"75-85"` — sampler raised `ValueError` on `75-85` age group with the original single-entry map)
- [x] `python scripts/analyze_scb_population.py data/scb_api/scb_population_pop-10000_03.json` — class shares: Poverty 20.2%, Working Class 31.0%, Middle Class 40.9%, Wealthy 7.9% — non-uniform, not locked at 20/30/30/20
- [x] `python scripts/analyze_ssb_population.py data/ssb_api/ssb_population_pop-10000_03.json` — class shares: Poverty 28.8%, Working Class 30.6%, Middle Class 31.1%, Wealthy 9.5% — non-uniform, Wealthy well below old 20%
- [x] `python scripts/compare_populations.py data/scb_api/scb_population_pop-10000_02.json data/scb_api/scb_population_pop-10000_03.json` — `socioeconomic_class.tv_distance = 1.000` (scb02 used old decile-based labels; scb03 uses class labels — completely different schema, all B categories unmapped in A, confirming structural break)
- [x] Rerun comparison for seed009 (configurable-identity) against new scb03 — `socioeconomic_class.tv_distance = 0.591`, `p = 0.002`; divergence expected since LLM prompts still target the old 20/30/30/20 distribution; not catastrophic — pipeline outputs valid class labels (Middle Class, Working Class etc.), just different proportions. Follow-on prompt-update task documented in plan.

**Files Modified:**
- `data/scb_api/scb_population_pop-10000_03.json` — new reference
- `data/ssb_api/ssb_population_pop-10000_03.json` — new reference
- `data/analysis/scb_population_pop-10000_03/` — generated plots
- `data/analysis/ssb_population_pop-10000_03/` — generated plots

**Dependencies:** Phase 2

---

## Testing Plan

### Unit-style checks (manual)

- [ ] `income_class.median_from_brackets()` returns the bracket midpoint at the 50th-percentile cumulative count, verified on a small handcrafted bracket list.
- [ ] `income_class.classify_brackets()` proportionally splits a bracket that straddles a threshold (e.g. bracket [40, 60] with median = 100 should split between Poverty and Working at the 0.60 × 100 = 60 line — entirely Poverty).
- [ ] Both `parse_socioeconomic()` raise `ValueError` on (a) empty response, (b) missing age dimension, (c) missing sex dimension, (d) all-zero values cell.

### Integration / end-to-end

- [ ] Fresh SCB population n = 10 000 shows non-uniform class shares.
- [ ] Fresh SSB population n = 10 000 shows non-uniform class shares.
- [ ] In the SCB output: men aged 45–54 have a higher combined Middle+Wealthy share than women aged 18–24 (sex × age conditioning works).
- [ ] In the SSB output: same conditioning sanity check.

### Edge cases

- [ ] SCB personas aged 18–19 use the `20-24` fallback band — confirm no `ValueError` raised, confirm distribution matches the 20-24 band.
- [ ] Top-bracket persona (very high income) lands in Wealthy.
- [ ] Bottom-bracket persona (low/zero income, e.g. student) lands in Poverty or Working depending on band.

---

## Documentation Plan

- [x] Update `CLAUDE.md` SCB Population section: socioeconomic_class is now derived from real income brackets via `HE/HE0110/HE0110A/SamForvInk1` (replace any decile reference).
- [x] Update `CLAUDE.md` SSB Population section: replace table 12682 reference with 06655.
- [ ] Inline comment at the threshold constants in `utils/income_class.py` citing Eurostat AROP + OECD/Pew with the equivalised-disposable caveat.
- [ ] No user-guide doc change needed — the schema field name and class labels are unchanged.

---

## Rollback Plan

The change is self-contained to the socioeconomic-class fetch / parse / sample path plus a new utility module. Rollback is a single git revert.

1. **Before-merge rollback:** abandon the feature branch; the base branch is unaffected.
2. **Post-merge rollback:** `git revert` the merge commit. The deleted decile-based code paths are recoverable from history. `scb02` / `ssb01` reference files are untouched (new outputs go to `*_03.json`).
3. **Data considerations:** No DB migrations. The pipeline persona JSONs use the same schema key `socioeconomic_class: {label: ...}`. Old generated personas remain valid; new ones use the new class assignment logic. Stored personas from earlier seeds are not invalidated.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SCB / SSB API change the contents code or break the table response format | Low | Med | Both parsers raise `ValueError` loudly on missing dimensions — failure is detectable in the next pipeline run, not silent |
| Bracket midpoint convention for open-ended top bracket (`1000+`, `2 000 000+`) skews the median computation | Med | Low | Document the midpoint convention in code; the open bracket holds a small share of the population so impact on median is bounded |
| The new conditional distribution surfaces age-vs-class patterns that the identity-pipeline prompts don't match | High | Low | Documented as expected — Phase 3 confirms the divergence; LLM prompt adjustment is a follow-on plan |
| Eurostat AROP cutoffs computed on individual gross income don't match official Sweden AROP rate (~16 %) | High | Low | Documented in inline caveat comment; the goal is a relative-position classifier, not literal poverty measurement |
| SSB age-band `67+` is open-ended and covers 67-85+ in the pipeline | Low | Low | Sample from the band's distribution; this is the same limitation already accepted elsewhere in the SSB code |

---

## References

- Investigation memo: `C:\Users\basil\.claude\plans\investigate-the-scb02-socioeconomic-cosmic-gosling.md`
- SCB table: `HE/HE0110/HE0110A/SamForvInk1` — <https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__HE__HE0110__HE0110A/SamForvInk1/>
- SSB table: `06655` — <https://www.ssb.no/en/statbank/table/06655>, metadata: <https://data.ssb.no/api/pxwebapi/v2-beta/tables/06655>
- Eurostat AROP glossary: <https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Glossary:At-risk-of-poverty_rate>
- OECD *Under Pressure: The Squeezed Middle Class* (2019)
- Pew Research middle-class methodology (2024)
- Related plan: `docs/development/plans/active/norway-ssb-population-generator.md`
- Related plan: `docs/development/plans/pending/investigate-scb02-generation-issues.md`

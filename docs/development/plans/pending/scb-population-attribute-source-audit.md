# Plan: SCB PxWeb source audit for every population attribute

**Date:** 2026-07-15
**Author:** Basil
**Status:** Pending
**Base Branch:** `feature/sweden-employment-status-by-age`
**Branch:** `feature/scb-population-attribute-source-audit` (to be created at implementation time)

---

## Overview

The `employment_status` investigation (2026-07-15) produced a reusable SCB PxWeb
investigation kit under `docs/reference/scb-pxweb-catalog/` — a conceptual data-model
reference, a two-step stdlib sweep/report pipeline (`scb_dump.py` → `build_report.py`), and
a live 968-table AM+UF catalog. It also produced a hard lesson: the currently-wired table for
an attribute is often *not* the best available source, and "a variable appears in a table's
metadata" is **not** the same as "you can cross-tabulate by it" (the `ArbStatusUtbM`
age-`20–64` collapse trap).

This plan applies that same thorough investigation to **every other** attribute in
`DEMOGRAPHIC_ATTRIBUTES` for the Swedish (SCB) generator. The goal is to systematically
discover *better or alternative* SCB tables for each attribute — finer age granularity,
register vs survey source, more categories, genuine cross-tabs instead of collapsed ones, more
recent years, national coverage — and to **document gaps** where the API cannot serve a needed
cross-tab, rather than silently accepting the table that happens to be wired today.

This is a **research / audit** plan. Its deliverable is an evidence-backed source matrix and a
prioritized list of concrete source-change candidates — **not** source-code changes. Any
resulting fetch/parser rewiring is spun out into its own separate implementation plan(s).

## Problem Statement

The 15 attributes in `DEMOGRAPHIC_ATTRIBUTES` (defined via the `ComparisonScheme` /
`config/mapping/scb_native/_index.json` axis order:
`age_group, biological_sex, education_level, employment_status, birth_location,
socioeconomic_class, parental_structure, region, civil_status, industry_sector,
employment_type, housing_tenure, household_size, income_source, birth_country_detail`)
are each fetched from a single SCB table hardcoded in
`src/population_synthetic/generators/real/sweden/constants.py`, with a fixed query in
`src/population_synthetic/generators/real/sweden/fetch_service.py`.

Those table choices were made incrementally and were **never systematically audited** against
the full SCB catalog. The `employment_status` episode showed the cost: the wired table
(`NAKUBefUtbNivAr`) collapses age to the 15–74 universe, and the "obvious" three-way table
degrades age to a working-age total — facts only discovered by a full sweep + live verification.
Several other attributes have visible smells in the current queries worth auditing:

- `birth_location`, `industry_sector`, `housing_tenure`, `household_size` are fetched as
  **national aggregates with no age/sex breakdown** (e.g. `Alder: TOT1`, `Alder: tot15-74`,
  or no `Alder` at all) — possibly because a finer cross-tab was never sought, not because it
  doesn't exist.
- Labour-market attributes (`employment_status`, `industry_sector`, `employment_type`) are
  **AKU survey** sources capped at age 74; register alternatives (RAMS/BAS) may offer
  full-count coverage and different age edges.
- Mixed vintages (`Tid` ranges from 2024 to 2025 across attributes) and mixed source types
  (register vs survey) are used without a documented rationale.

Without a sweep-backed audit we cannot tell, per attribute, whether a strictly better table
exists — or confirm that the current one is genuinely the best the public API offers.

## Current source matrix (as wired today)

Compiled from `constants.py` + each `fetch_*` method in `fetch_service.py`. "Source type" is
inferred from the SCB product (BE/HE/BO/LE register products = full-count administrative; AM0401
= AKU Labour Force Survey, sample-based, ILO definitions, ages 15–74).

| # | Attribute | Current table (ID) | Query dims (breakdowns) | Source type | Known / suspected limitation |
|---|-----------|--------------------|-------------------------|-------------|------------------------------|
| 1 | age_group | `BE/BE0101/BE0101A/BefolkningNy` | Region=00, Alder=18–85 (single yr), Kon, Tid=2024 | Register (RTB) | Baseline; strong. Single-year age, national. |
| 2 | biological_sex | `BE/BE0101/BE0101A/BefolkningNy` | (same as age_sex) | Register | Shares the age_sex table. |
| 3 | education_level | `UF/UF0506/UF0506B/Utbildning` | Region=00, Alder=18–74, UtbildningsNiva=8 lvls, Kon, Tid=2025 | Register (education reg.) | **Caps at 74** — no 75–85 education. |
| 4 | employment_status | `AM/AM0401/AM0401P/NAKUBefUtbNivAr` | Arbetskraftstillh, UtbildningsNiva, Kon, Tid=2025 | AKU survey | **No age** (fixed 15–74 universe) — the blocked employment-by-age plan; register `AM0210` alt exists. |
| 5 | birth_location | `BE/BE0101/BE0101E/FolkmFodlandHVD` | Fodelseland(SV/EU/non-EU), HDI=TOT, Kon=1+2, Alder=TOT1, Tid=2025 | Register | **National aggregate, no age/sex.** |
| 6 | socioeconomic_class | `HE/HE0110/HE0110A/SamForvInk1` | Region=00, Kon, Alder=5-yr bands 20–85+, Inkomstklass, Tid=2024 | Register (income) | Derived to 4 classes; starts at age 20. |
| 7 | parental_structure | `LE/LE0102/LE0102B/LE0102T17` | Kon=5+6, Alder=0–17, UtlBakgrund, UtbNivaForalder, Tid=2024 | Survey (ULF/SILC, LE) | Describes children 0–17; small survey. |
| 8 | region | `BE/BE0101/BE0101A/BefolkningNy` (#region) | Region=county codes, Alder=18–85, Kon, Tid=2024 | Register | Shares age_sex table; county granularity. |
| 9 | civil_status | `BE/BE0101/BE0101A/BefolkningNy` (#civil_status) | Civilstand(4), Alder=18–85, Kon, Tid=2024 | Register | Shares age_sex table; 4 categories. |
| 10 | industry_sector | `AM/AM0401/AM0401I/AKURLSysSNI07Ar` | Anknytningsgrad=SYSTOT, SNI2007=12 grp, Kon=1+2, Alder=tot15–74, Tid=2025 | AKU survey | **Age collapsed to tot15–74; sex combined.** Register RAMS alt (workplace/industry) likely finer. |
| 11 | employment_type | `AM/AM0401/AM0401I/AKURLSysAnkAr` + `AM/AM0401/AM0401S/NAKUSysselOkArbtidAr` | attachment × age-bands × Kon merged with hours × age-bands × Kon (independence assumption) | AKU survey | **Two tables merged by independence; caps at 74.** |
| 12 | housing_tenure | `BO/BO0104/BO0104D/BO0104T04` | Region=00, Hustyp, Upplatelseform, Tid=2025 | Register (dwelling stock) | **Dwelling-level, no person age/sex.** |
| 13 | household_size | `BE/BE0101/BE0101S/HushallT03` | Region=00, Hushallsstorlek, Tid=2024 | Register | **No age/sex of household members.** |
| 14 | income_source | `HE/HE0110/HE0110F/TabVX13InkStruktN` | Region=00, Inkomstkomponenter=6, Alder=bands, Sysselsattning=5, Tid=2024 | Register (income) | Conditioned on employment × age bands. |
| 15 | birth_country_detail | `BE/BE0101/BE0101E/FodelselandArK` | Fodelseland=top 20, Alder=18–85, Kon, Tid=2024 | Register | Single-year age × sex; strong. |

(`constants.py` also defines `INCOME_TABLE`, `INCOME_SOURCE_TABLE`, and `URBANIZATION_TABLE`;
`urbanization` is **not** in `DEMOGRAPHIC_ATTRIBUTES` and is out of scope for this audit.)

## Goals

### In Scope
1. For each of the 15 attributes, run the SCB sweep kit over the relevant subject area(s) and
   produce an evidence-backed answer to: *is there a strictly better public SCB table than the
   one wired today?* ("Better" is defined per attribute below.)
2. For every candidate table, apply the **"present ≠ cross-tabulable"** rule with a **live
   verification query** confirming the desired cross-tab actually populates (not collapsed to an
   aggregate, not fully suppressed).
3. Produce a durable **source-audit matrix** doc (per attribute: current source, best candidate,
   verification result, recommendation, and — where nothing better exists — an explicit gap
   note honoring the no-synthetic-distributions rule).
4. Extend the reusable catalog kit to the newly-swept subject areas (BE, HE, BO, LE at minimum;
   AM/UF already captured) so future audits are a search, not a re-hunt.

### Out of Scope
- **Any source-code change** to `constants.py`, `fetch_service.py`, parsers, or samplers. This
  plan only *recommends*; rewiring is a follow-up implementation plan per accepted candidate.
- **SCB microdata / MONA.** If a needed cross-tab is not published on PxWeb, it is treated as
  "not available to us" (per the data-model doc §7). No microdata application is in scope.
- **Norway (SSB) and Italy (ISTAT/Eurostat).** This audit is SCB/Sweden only.
- **The `global` cross-country mapping tier** (`config/mapping/scb`) and any fidelity/comparison
  scoring changes.
- `urbanization` and any attribute not in `DEMOGRAPHIC_ATTRIBUTES`.

## Success Criteria

- [ ] A sweep JSONL + HTML catalog exists for each in-scope subject area (BE, HE, BO, LE; AM+UF
      reused), committed under `docs/reference/scb-pxweb-catalog/`.
- [ ] Every one of the 15 attributes has a completed audit row: current source, candidate(s)
      considered, **live verification outcome**, and a recommendation (keep / switch / gap).
- [ ] Every "switch" recommendation is backed by a real POST query showing the target cross-tab
      populates with genuine (non-collapsed, non-fully-suppressed) cells.
- [ ] Every "gap" recommendation explicitly states the API cannot serve the cross-tab and that
      the field must stay as-is or be dropped — never fabricated.
- [ ] The audit matrix doc is written and cross-links the data-model reference and per-area
      catalogs.
- [ ] No source code was modified by this plan.

---

## Methodology (applies to every phase)

Each phase sweeps one subject area with the existing kit and then verifies per attribute.

**Per subject area (once):**
1. Set `ROOTS=["<AREA>"]` in a copy of `scb_dump.py`; run the throttled dump (`DELAY ≥ 0.34 s`,
   respect the ~30 req/10 s limit). Write UTF-8; set `PYTHONIOENCODING=utf-8`.
2. Run `build_report.py` to render the searchable HTML catalog for that area.
3. Commit the `*-metadata.jsonl` + `*-catalog.html` under `docs/reference/scb-pxweb-catalog/`.

**Per attribute (using that area's catalog):**
1. **Locate by dimension, not name.** Search the catalog/JSONL for tables carrying the
   attribute's measure *and* the breakdowns we want (age, sex, region, …) — e.g. via the
   `jq` any-of-codes pattern in `HOW-TO.md`.
2. **Define "better" for this attribute** (see per-attribute notes below) and shortlist
   candidates: register vs survey, finer age, more categories, newer `Tid`, national coverage.
3. **Verification step (mandatory).** For each shortlisted candidate, issue a **real POST
   query** for the specific cross-tab cell combination and confirm:
   - the target breakdown is a *genuine* breakdown, not an aggregate range (normalize `–`
     U+2013 vs `-`; distinguish `20–24` bands from a `20–64` total — the `classify_age` rule);
   - cells are not wholesale confidentiality-suppressed (`".."`/`None`);
   - coverage edges (age caps, geography, year) are acceptable.
4. Record the outcome in the audit matrix as **keep / switch(→table, dims) / gap**.

---

## Implementation Plan (phases by subject area)

### Phase 1: AM — Labour market (reuse existing sweep)
**Goal:** Finish auditing the labour attributes against the already-captured AM catalog.
**Attributes:** `employment_status`, `industry_sector`, `employment_type`.

- [ ] 1.1 — `employment_status`: reconcile with the blocked
      `sweden-employment-status-by-age` plan. Confirm from the AM catalog the register option
      `AM/AM0210/AM0210D/ArRegArbStatus` (status × 5-yr age × sex, full-count) and the AKU option
      `AM/AM0401/AM0401A/AKURLBefAr` (status × age × sex). **Verify** each populates a real age
      band; record register-vs-survey tradeoff and the confirmed non-existence of
      status × age × education (catalog "Age+education+status jointly = 0").
- [ ] 1.2 — `industry_sector`: current query collapses age to `tot15-74` and combines sex.
      Search AM (and register RAMS folders `AM0207`/`AM0210`) for SNI2007 × age-band × sex.
      **Verify** a candidate cross-tab actually breaks down by age/sex rather than collapsing.
- [ ] 1.3 — `employment_type`: audit whether a single table gives attachment/hours by age×sex
      (removing the two-table independence merge) and whether a register source extends past 74.
      **Verify** any single-table candidate populates.
- [ ] 1.4 — Record all three rows (keep / switch / gap) with age-cap notes (AKU caps at 74).

**Artifacts:** reuse `scb-am-uf-catalog.html` / `scb-am-uf-metadata.jsonl`.
**Dependencies:** None.

### Phase 2: UF — Education (reuse existing sweep)
**Goal:** Audit `education_level` against the captured UF catalog.
**Attributes:** `education_level`.

- [ ] 2.1 — Current `Utbildning` caps at age 74. Search UF for an education-attainment table
      covering **75–85** by single-year/narrow age × sex, and for finer/updated attainment
      categories or a newer `Tid`. **Verify** a candidate covers the older ages with real cells.
- [ ] 2.2 — Record row; if no 75+ education table exists, note the gap (education for 75–85 must
      rely on the existing fallback, never fabricated).

**Artifacts:** reuse AM+UF catalog.
**Dependencies:** None.

### Phase 3: BE — Population
**Goal:** Sweep BE; audit the population-register attributes.
**Attributes:** `age_group`, `biological_sex`, `region`, `civil_status`, `birth_location`,
`birth_country_detail`, `household_size`.

- [ ] 3.1 — Sweep `ROOTS=["BE"]`; build + commit the BE catalog.
- [ ] 3.2 — `age_group`/`biological_sex`/`region`/`civil_status` (all on `BefolkningNy`):
      confirm this is the best register table; check for a newer `Tid` than 2024 and whether a
      single table can serve region × civil_status × age × sex without extra calls. **Verify**.
- [ ] 3.3 — `birth_location`: currently a national aggregate (`Alder=TOT1`). Search BE for
      birth-region × age × sex (register). **Verify** the age/sex breakdown populates; if the
      only tables are aggregates, record the limitation.
- [ ] 3.4 — `birth_country_detail`: confirm `FodelselandArK` (single-yr age × sex) is best;
      check for a wider country list or newer year. **Verify**.
- [ ] 3.5 — `household_size`: currently no age/sex. Search BE for household size crossed with a
      reference-person age/sex or household type. **Verify** any candidate; else record gap.
- [ ] 3.6 — Record all BE rows.

**Artifacts:** `scb-be-catalog.html`, `scb-be-metadata.jsonl`.
**Dependencies:** None.

### Phase 4: HE — Household finances
**Goal:** Sweep HE; audit the income-derived attributes.
**Attributes:** `socioeconomic_class`, `income_source`.

- [ ] 4.1 — Sweep `ROOTS=["HE"]`; build + commit the HE catalog.
- [ ] 4.2 — `socioeconomic_class`: audit `SamForvInk1` (income bracket × age-band × sex) for a
      finer income granularity, coverage below age 20, or a newer year. Confirm the 4-class
      derivation still rests on a real bracket distribution. **Verify** the chosen cross-tab.
- [ ] 4.3 — `income_source`: audit `TabVX13InkStruktN` (income components × age × employment)
      for finer components/age or newer year. **Verify** the employment × age conditioning
      populates and is not collapsed.
- [ ] 4.4 — Record rows.

**Artifacts:** `scb-he-catalog.html`, `scb-he-metadata.jsonl`.
**Dependencies:** None.

### Phase 5: BO — Housing & construction
**Goal:** Sweep BO; audit `housing_tenure`.
**Attributes:** `housing_tenure`.

- [ ] 5.1 — Sweep `ROOTS=["BO"]`; build + commit the BO catalog.
- [ ] 5.2 — `housing_tenure`: current `BO0104T04` is dwelling-stock-level (no person age/sex).
      Search BO for tenure crossed with household/person age or household type (person-weighted,
      not dwelling-weighted). **Verify** any candidate populates; else record that tenure is only
      published dwelling-level (a modelling limitation, not a fabrication).
- [ ] 5.3 — Record row.

**Artifacts:** `scb-bo-catalog.html`, `scb-bo-metadata.jsonl`.
**Dependencies:** None.

### Phase 6: LE — Living conditions
**Goal:** Sweep LE; audit `parental_structure`.
**Attributes:** `parental_structure`.

- [ ] 6.1 — Sweep `ROOTS=["LE"]`; build + commit the LE catalog.
- [ ] 6.2 — `parental_structure`: `LE0102T17` is a survey (ULF/SILC) describing children 0–17.
      Search LE (and BE household/family folders) for a register-based family-structure table
      with larger samples / newer year. Note the survey-vs-register tradeoff. **Verify** any
      candidate populates the family-structure categories used downstream.
- [ ] 6.3 — Record row.

**Artifacts:** `scb-le-catalog.html`, `scb-le-metadata.jsonl`.
**Dependencies:** None.

### Phase 7: Cross-cutting concerns + audit matrix
**Goal:** Synthesize per-area findings into one durable audit and flag systemic issues.

- [ ] 7.1 — **Confidentiality suppression.** Note which recommended cross-tabs risk small-cell
      suppression at the granularity we need; prefer sources that stay populated, and confirm the
      parsers' skip-vs-raise behavior would tolerate residual suppressed cells.
- [ ] 7.2 — **Age-coverage edges.** Consolidate every age cap (AKU labour tables cap at 74;
      education caps at 74; income starts at 20) and state the fallback/gap for each edge —
      never fabricate the missing band.
- [ ] 7.3 — **Register vs survey consistency.** Flag where switching one attribute from survey to
      register (or vice versa) would create an internal inconsistency with a related attribute
      (e.g. mixing AKU employment with register industry), and recommend a coherent source family.
- [ ] 7.4 — **Vintage alignment.** Note the spread of `Tid` (2024–2025) and whether aligning to
      a single reference year is feasible without losing coverage.
- [ ] 7.5 — **No-synthetic-distributions invariant.** For every attribute where no better (or no
      complete) source exists, record the gap explicitly with the rule: drop/keep-as-is, never
      invent a distribution to fill an API gap.
- [ ] 7.6 — Write the consolidated **`docs/reference/scb-pxweb-catalog/scb-source-audit.md`**
      matrix (one row per attribute: current source → best candidate → verification result →
      recommendation → gap notes), cross-linking the data-model doc and per-area catalogs.
- [ ] 7.7 — For each accepted "switch" recommendation, open a short follow-up implementation plan
      stub (out of scope to implement here) describing the constants/fetch/parser change.

**Files created:**
- `docs/reference/scb-pxweb-catalog/scb-{be,he,bo,le}-metadata.jsonl` + `*-catalog.html`
- `docs/reference/scb-pxweb-catalog/scb-source-audit.md`

**Dependencies:** Phases 1–6.

---

## Testing / Verification Plan

This is a research plan; "testing" = evidence quality, not unit tests.

- [ ] Every "switch" row has a saved live POST query + a note of the returned cells proving a
      genuine (non-collapsed, non-suppressed) cross-tab.
- [ ] Every age/geography breakdown claim passes the en-dash-normalized `classify_age` check
      (real band vs aggregate total).
- [ ] Sweeps respect the SCB rate limit (no `429` storms); JSONL is UTF-8 clean.
- [ ] The audit matrix accounts for all 15 attributes — no attribute left un-audited.
- [ ] No source code diff is produced by this plan.

---

## Out-of-Scope Note (microdata)

If a required cross-tab is not published on the public PxWeb API, it does **not** exist for this
project. The only route to it — SCB **microdata via the MONA platform** (formal research
application, ethics/legal basis) — is explicitly **out of scope**. "Not on PxWeb" is treated as
"not available to us," and the no-synthetic-distributions invariant governs the gap: drop or keep
the field as-is, never fabricate.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A "candidate" table lists the wanted dimension but collapses it (the `ArbStatusUtbM` trap) | High | Med | Mandatory live POST verification per candidate; en-dash-normalized age classification |
| Sweeps trip SCB's rate limit | Med | Low | `DELAY ≥ 0.34 s`, 429 backoff/retry, run in background |
| Finer cross-tabs trigger heavy confidentiality suppression | Med | Med | Phase 7.1 prefers populated sources; verify cells before recommending |
| Switching a source creates cross-attribute inconsistency (survey vs register) | Med | Med | Phase 7.3 recommends a coherent source family, not per-attribute local optima |
| Audit stalls into an endless "better table" hunt | Med | Low | "Better" is pre-defined per attribute; stop at first verified strict improvement or a documented gap |

---

## References

- `docs/reference/scb-pxweb-catalog/scb-pxweb-data-model.md` — SCB table model, sources, the
  "present ≠ cross-tabulable" trap, microdata boundary.
- `docs/reference/scb-pxweb-catalog/HOW-TO.md` — retarget the sweep to any subject area
  (`ROOTS=["BE"]`, `["HE"]`, …) and rebuild the report.
- `docs/reference/scb-pxweb-catalog/README.md` + `scb-am-uf-catalog.html` — the AM+UF sweep.
- `src/population_synthetic/generators/real/sweden/constants.py` — current `*_TABLE` IDs.
- `src/population_synthetic/generators/real/sweden/fetch_service.py` — current per-attribute
  queries/dimensions.
- `config/mapping/scb_native/_index.json` — the 15-attribute comparison axis order.
- Blocked precedent: `docs/development/plans/active/sweden-employment-status-by-age.md`.
- Core invariants: project `CLAUDE.md` (no synthetic distributions, config-as-source, fail-fast);
  `docs/architecture/design-principles.md`.

---

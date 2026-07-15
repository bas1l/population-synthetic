# Plan: Implement the SCB source-audit improvements (Sweden)

**Date:** 2026-07-15
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/sweden-employment-status-by-age`
**Branch:** `feature/scb-source-improvements`

> **Base-branch note:** captured branch is `feature/sweden-employment-status-by-age` (where the
> audit was produced). This plan is **broader than that branch's topic** (it touches 6 attributes,
> not just employment). Per the project convention (branch from `dev`, not a feature branch),
> consider re-basing the eventual `feature/scb-source-improvements` branch onto `dev` before work
> starts. Decision left to implementer.

---

## Overview

Rewire the Swedish population generator to the **best-available SCB PxWeb source** for the 6
attributes the [source audit](../../reference/scb-pxweb-catalog/scb-source-audit.md) found improvable,
and add the documented [two-table merge](../../reference/scb-pxweb-catalog/employment-status-merge-derivation.md)
for `employment_status`. All changes keep the **no-synthetic-distributions** invariant: every
distribution still comes from a real API response (or a documented derivation over real margins).

## Problem Statement

Six attributes are on sub-optimal sources, verified live during the audit:
- **employment_status** samples `SYS/ALÖS` from an education-crossed AKU table with **no age** — the
  originating branch's whole problem.
- **industry_sector** and (partly) **education_level** / **socioeconomic_class** lose or coarsen the
  age dimension; **housing_tenure** is dwelling-level (no person age/sex); **birth_location** is
  queried as an all-ages aggregate despite the table carrying age×sex.

Each has a verified better source. Fixing them improves demographic fidelity and closes the
education 75+ coverage gap, at the cost of some taxonomy/collapse work and one explicit register↔
survey coherence decision.

## Goals

### In Scope
1. Switch the 5 table-change attributes (education_level, employment_status, industry_sector,
   socioeconomic_class, housing_tenure) to their audited sources.
2. Enrich `birth_location` (same table) to an age×sex conditional.
3. Update the `scb_native` mapping config `real` blocks wherever raw category labels change.
4. Implement the `employment_status` two-table merge per its spec (opt-in, all-register).
5. Preserve fail-fast + no-synthetic-distributions throughout; add parser/derivation tests.

### Out of Scope
- **Norway/Italy** generators (Sweden only).
- The **coarse/global** mapping tier (`config/mapping/scb/`) beyond keeping it consistent — it is
  deferred/design-only and not used by the primary Sweden comparison.
- **Microdata (MONA/RTB)** — the true status×edu×age cube; unavailable via public API.
- Ages **75+ labour status** — no source exists; modelled as out-of-labour-force (documented).
- Re-deriving socioeconomic **class thresholds** (income_class.py is unchanged).

## Success Criteria

- [ ] Generating a Swedish population succeeds end-to-end with all 6 attributes on the new sources.
- [x] `employment_status` is conditioned on age (single-table) — and, with the merge enabled, on
      age × education.
- [ ] `education_level` covers ages up to 95+ (75+ no longer dropped).
- [ ] `industry_sector` and `housing_tenure` carry the correct canonical categories after their
      collapse maps; mapping resolves with **no unmatched raw labels**.
- [ ] No hardcoded probability enters the pipeline; every new distribution traces to a real API
      response or the documented merge derivation.
- [ ] New unit tests for each rewritten parser + the merge derivation pass; full `pytest` green.
- [ ] The register↔survey coherence decision is made explicitly and recorded in provenance docs.

---

## Technical Design

### Approach

Work attribute-by-attribute along the existing data flow — `*_TABLE` constant → `fetch_*` →
`parse_*` → `PopulationDistributions` field → `sample_service` step → `scb_native` mapping — touching
only what each change requires. Order phases by **rising coupling/risk**: source-only refreshes
first, taxonomy-changing switches next, the employment_status rewrite (branch core) after, and the
opt-in merge last. Each phase is independently shippable and independently verifiable by generating a
population and diffing the affected marginal against the live SCB table.

Key design rules (from `docs/architecture/design-principles.md` and the data-pipeline guides):
- **Fail-fast** on missing/suppressed cells that aren't legitimately null; **tolerate** confidentiality
  nulls (never impute, never treat as certain-zero).
- **Config is source of truth** — category label maps live in `config/mapping/scb_native/*.json`, not
  in Python. In-parser collapses (NACE→12 sectors, Boendeform→3 tenures) **sum real cells only**.
- **No silent register/survey mix** — the merge stays all-register; the coherence decision is surfaced.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Per-attribute source swap along existing flow** | Minimal blast radius; each verifiable alone | Several parsers rewritten | **Chosen** |
| Single big "re-fetch everything" refactor | One pass | High risk; hard to verify; conflates independent changes | Rejected |
| employment_status: keep education, drop age | No rewrite | Fails the branch's goal | Rejected |
| employment_status: **merge** as the *only* path | Max fidelity | Adds a modeling assumption before the simple win lands | Rejected as primary; **kept as opt-in Phase 6** |
| industry_sector: update mapping to raw NACE labels | No in-parser aggregation | 52 fragile matchers; loses the clean 12-sector canonical | Rejected — aggregate in parser instead |

### Architecture Changes

- **No new modules** for Phases 1–5; changes live in the existing Sweden `constants.py`,
  `fetch_service.py`, `parsers.py`, `sample_service.py`, `data.py`, and `config/mapping/scb_native/`.
- **Phase 6 (merge)** adds a two-fetch `fetch_employment_status` + a combining
  `parse_employment_status_combined` (odds-multiplication), mirroring the existing two-table pattern
  `fetch_employment_type_by_age` (FETCH:218-252) / `parse_employment_type_combined` (PARSE:341-467).
- Two `PopulationDistributions` fields are re-typed to conditional dicts (`employment_by_sex_education`
  → `{(age_group,sex):{status:prob}}`; `birth_location` → age×sex-keyed). `data.py` is a frozen
  dataclass — update field types + `load_all` wiring together.

---

## Implementation Plan

### Phase 1: Low-coupling source refreshes (no canonical taxonomy change)
**Goal:** Land the two switches that need no mapping-config edits and no marginal→conditional change.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 1.1 **education_level → `UF0506B/UtbBefRegionR`.** Point `EDUCATION_TABLE` (CONST:15) at the new
      matrix; extend `Alder` to 16–95+ in `fetch_education_by_age` (FETCH:68-85); drop the `tot16-74`
      synthetic total. **Verify the raw `UtbildningsNiva` labels are identical** to the current series
      (they should be — same 8-level ISCED); only touch `education.json` if they differ.
      *Done: labels verified byte-for-byte identical (8-level ISCED97) against live SCB; `education.json`
      untouched. ContentsCode changed to `000000I2` (the new table's "Number"). Live smoke test confirms
      the 75-85 age group is now populated.*
- [x] 1.2 **socioeconomic_class → `HE0110A/SamForvInk1a`.** Point `INCOME_BRACKET_TABLE` (CONST:34);
      replace the hard-coded 5-yr `age_bands` in `fetch_socioeconomic` (FETCH:141-145) with single
      years; fix `ContentsCode` (`HE0110AD`). Replace `_SCB_BAND_TO_AGE_GROUP` (PARSE:584-600) with a
      single-year→age-group mapper (reuse `resolve_age_group`/`age_to_group`). **income_class.py is
      unchanged** (age-agnostic). Tolerate confidentiality nulls in sparse young×high-bracket cells.
      *Done: `ContentsCode` set to `HE0110AD`, `Tid=2024`, single-year `Alder` 18–85; the new table has
      no `Region` dimension so that selection was removed. `_SCB_BAND_TO_AGE_GROUP` deleted and replaced
      with `resolve_age_group(label, {})`. Null (`.. `/`None`) bracket cells are now skipped, not summed
      as zero. income_class.py unchanged. Live smoke test parses without crashing across all age groups.*

**Files Modified:**
- `.../sweden/constants.py` — lines 15, 34 (table IDs)
- `.../sweden/fetch_service.py` — `fetch_education_by_age` (68-85), `fetch_socioeconomic` (139-160)
- `.../sweden/parsers.py` — `parse_education_by_age` (47-107) tolerance; `_SCB_BAND_TO_AGE_GROUP` (584-600) → single-year mapper

**Dependencies:** None

### Phase 2: birth_location — marginal → age×sex conditional (same table)
**Goal:** Query the age×sex breakdown the table already carries.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 2.1 In `fetch_birth_location` (FETCH:105-120) select `Kon=1,2` and single-year `Alder` instead
      of `Kon=1+2, Alder=TOT1`; move to `Tid=2025`; handle the `OKANT` (unknown) birth bucket.
      *Done: query now selects `Kon=1,2`, single-year `Alder` 18–85, `Tid=2025`; `Fodelseland` includes
      `OKANT` so counts stay faithful to the true population, and the parser drops it explicitly (no
      canonical target). Live verify confirmed non-collapsed cells varying by age×sex.*
- [x] 2.2 Rewrite `parse_birth_location` (PARSE:208-227) to emit `{(age_group,sex):{region:prob}}`
      (mirror `parse_birth_country_detail`, PARSE:723-764).
      *Done: re-typed to `dict[tuple[str,str], dict[str,float]]`. The live `id` order is
      `[Fodelseland, HDI, Kon, Alder, ...]` (singleton HDI wedged between region and sex, Kon before
      Alder), so instead of the mirror's fixed loop nesting the parser derives row-major strides from
      the response's own `id`/`size` — order-independent and correct. `OKANT` skipped by code; regions
      normalised per (age_group,sex).*
- [x] 2.3 Re-type the `birth_location` field (DATA:26) and condition Step 4 sampling (SAMPLE:159);
      keep the `_SWEDEN_LABELS` gate to `birth_country_detail` (SAMPLE:70-74) working.
      *Done: `data.py` field re-typed; Step 4 now looks up `(age_group, sex_label)` with an
      opposite-sex fallback and fail-fast, mirroring the other conditional attributes. The
      `_SWEDEN_LABELS` gate at Step 11 still consumes `birth_location_label` unchanged. No
      `scb_native` edit (same table/labels). Ruff clean; smoke test (n=50, seed=42) generated without
      crash and birth_location varies with age/sex.*

**Files Modified:**
- `.../sweden/fetch_service.py` (105-120) · `parsers.py` (208-227) · `data.py` (26) · `sample_service.py` (159, 70-74)

**Dependencies:** None (independent of Phase 1). **No `scb_native` edit** — same table/labels.

### Phase 3: Taxonomy-changing switches (collapse maps + mapping-config updates)
**Goal:** Switch industry_sector and housing_tenure, aggregating real cells to canonical categories.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 3.1 **industry_sector → `AM0210F/ArRegSNI2007Riket`.** Repoint `INDUSTRY_SECTOR_TABLE`
      (CONST:23); rewrite `fetch_industry_sector` (FETCH:197-216) for real `Alder` bands + `Kon`;
      in `parse_industry_sector` (PARSE:315-338) **aggregate ~52 NACE codes → the 12 canonical
      sectors** (sum real cells) and key by `(age_group,sex)`; condition Step 6 sampling
      (SAMPLE:186-192). **Design choice:** aggregate to the *same 12 sector labels* the mapping already
      knows so `NATIVE/industry_sector.json` (18-96) needs minimal change; otherwise update its `real`
      block. Note unit change (counts, not thousands) and register "employed" definition.
      *Done: live metadata check confirmed the table offers no API-provided section-level SNI aggregate
      (only ~52 fine codes + TOTAL + "00" unknown), so a hand-map was required. Added
      `_SNI2007_TO_SECTOR` (51 fine codes → the 12 canonical English sector labels, following SCB's own
      standard SNI aggregation) plus `_IND_AGE_BAND_TO_GROUPS` expanding the coarse register bands
      (20-24, 25-54, 55-64, 65-74 — the table has no single-year age and no `Region` dimension) onto
      every canonical age group; the 25-54 band is shared across 25-34/35-44/45-54 and 65-74 also
      covers 75-85 (register employment caps at 74). `TOTAL` and `00` (unknown activity) are excluded
      from the query, so the parser only sees mappable codes and raises on any it can't map. Query uses
      `Yrkesstallning=TOT`, `Fodelseregion=tot`, `ContentsCode=0000071V` (employed by region of
      residence — person counts, not thousands), `Tid=2024`. Parser re-typed to
      `{(age_group,sex):{sector:prob}}` (sums real cells only); Step 6 sampling now conditions on
      (age_group, sex) with an opposite-sex fallback. `industry_sector.json` UNCHANGED (parser emits the
      canonical labels already in its `real`/`equals` block).*
- [x] 3.2 **housing_tenure → `HE0111A/HushallT31`.** Repoint `HOUSING_TENURE_TABLE` (CONST:26);
      rewrite `fetch_housing_tenure` (FETCH:254-268) for `Boendeform` × `Alder` × `Kon`; rewrite
      `parse_housing_tenure` (PARSE:470-511) with the **Boendeform→3-tenure collapse map**
      (`SMAG`→owner, `SMBO`/`FBBO`→tenant-owned, `SMHY0`/`FBHY0`→rented; `SPBO`/`OB`/missing folded or
      dropped explicitly). Decide marginal vs age×sex-conditional (recommend conditional — it's now
      person-level). Add the 3 Swedish tenure raw labels to `NATIVE/housing_tenure.json` `real` (7-26)
      **or** emit the existing English canonical labels from the parser.
      *Done: this is a person-level table (persons by type of housing × single-year age × sex), so the
      result is age×sex-conditional. Added `_BOENDEFORM_TO_TENURE` (SMAG→owner; SMBO/FBBO→tenant-owned;
      SMHY0/FBHY0→rented) and only those 5 mappable codes are requested; `SPBO`/`OB`/`ÖVRIGT`/`TOT` are
      excluded explicitly (no canonical tenure target — documented drop, mirroring the OKANT birth
      handling), and any other unrecognised code raises. Query uses `Region=00`, single-year `Alder`
      18-85, `Kon=1,2`, `ContentsCode=0000031S`, `Tid=2025`. Parser re-typed to
      `{(age_group,sex):{tenure:prob}}` (sums real cells only, single-year ages folded via
      `resolve_age_group`); Step 8 sampling now conditions on (age_group, sex) with an opposite-sex
      fallback. `housing_tenure.json` UNCHANGED (parser emits the canonical English tenure labels
      already in its `real`/`equals` block).*

**Files Modified:**
- `.../sweden/constants.py` (23, 26) · `fetch_service.py` (197-216, 254-268) · `parsers.py` (315-338, 470-511) · `sample_service.py` (186-192, 221-222) · `data.py` (31, 33)
- `config/mapping/scb_native/industry_sector.json`, `config/mapping/scb_native/housing_tenure.json` (+ coarse-tier `config/mapping/scb/` counterparts for consistency)

**Dependencies:** None (independent of 1–2).

### Phase 4: employment_status — single-table switch to `AM0210D/ArRegArbStatus` (branch core)
**Goal:** Condition status on age (× sex), full register spectrum. This is the originating branch's goal.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 4.1 Repoint the source (add/replace `EMPLOYMENT_BY_EDUCATION_TABLE`, CONST:17) to
      `ArRegArbStatus`; rewrite `fetch_employment_by_sex_education` (FETCH:87-103) → status ContentsCodes
      × 5-yr `Alder` × `Kon`, `Region=00`, `Fodelseregion=tot`, `Tid=2024`.
      *Done: `EMPLOYMENT_BY_EDUCATION_TABLE` now points at `AM/AM0210/AM0210D/ArRegArbStatus` (constant
      name kept — see 4.3 note — with a clarifying comment). Confirmed live: the six status count
      measures are ContentsCodes (`000002NT` employed, `NM` unemployed, `NR` students, `NP` retirees,
      `NQ` sick, `NO` others); the labour-force/total/rate measures are excluded. Fetch requests
      `Region=00`, `Kon=1,2`, the 5-yr `Alder` bands `20-24 … 70-74` (constant
      `EMPLOYMENT_STATUS_AGE_BANDS`), `Fodelseregion=tot`, all six status ContentsCodes, `Tid=2024`.*
- [x] 4.2 Rewrite `parse_employment_by_sex_education` (PARSE:110-205) to emit
      `{(age_group,sex):{status:prob}}` over the **6-cat** register status set
      (employed/unemployed/students/retirees/sick/others); keep the `".."`-suppression handling.
      *Done: status lives in the `ContentsCode` dimension (one measure per status), so the parser maps
      each code → a canonical status label (`_EMPLOYMENT_STATUS_CODE_TO_LABEL`) and folds the 5-yr bands
      into canonical groups via `_EMPLOYMENT_STATUS_AGE_BAND_TO_GROUPS`. Row-major strides derived from
      the response `id`/`size` keep it order-independent across the singleton Region/Fodelseregion/Tid
      dims. Null/`".."` cells → zero-count (never imputed); a fully-suppressed (age_group, sex) subgroup
      fails fast; unmapped ContentsCode or age band raises.*
- [x] 4.3 Re-type the field (DATA:25); rewrite Step 3 sampling (SAMPLE:136-155) to key on
      `(age_group,sex)`; **remove** `_resolve_edu_key` (SAMPLE:77-90) and `_SUN2020_TO_AKU_EDU`
      (SAMPLE:18-35).
      *Done: field `employment_by_sex_education` re-typed to `dict[tuple[str,str], dict[str,float]]` (data.py).
      NOT renamed — the field is shared by the Norway/Italy generators (out of scope), so per the plan's
      rename guidance the field/method/constant names were kept and clarifying comments added instead.
      Step 3 now looks up `(age_group, sex_label)` with an opposite-sex fallback and fail-fast; education
      no longer conditions employment. `_resolve_edu_key` and `_SUN2020_TO_AKU_EDU` deleted.*
- [x] 4.4 **Downstream fixups:** update the `is_employed` gate (feeds industry Step 6 + employment_type
      Step 7) for the new 6-cat set; update `_AKU_TO_INC_EMP` (SAMPLE:37-54) so income_source (Step 10)
      still resolves; add the new **retired/student** canonical values to `NATIVE/employment.json`
      `real` (6-24) and reconcile with the "Retired" KNOWN GAP in
      `config/analysis/consistency/scb.yaml` (24-29).
      *Done: `is_employed` gate now `employment_status_label in _EMPLOYED_STATUSES` (`{"Employed"}`) — only
      register-Employed personas receive industry_sector + employment_type (verified: 68/100 Employed got
      both, 32 non-employed got neither). `_AKU_TO_INC_EMP` replaced by `_STATUS_TO_INC_EMP` mapping the six
      canonical statuses onto the income table's `Sysselsattning` categories (confirmed live: Employed→
      gainfully employed, Unemployed→unemployed, Student→students, Retired→retired, Sick Leave/Other→
      non gainfully employed); fail-fast on any unmapped status retained. `config/mapping/scb_native/employment.json`
      `values` grew to `["Employed","Unemployed","Student","Retired","Sick Leave","Other"]` with `real`
      `equals` blocks for the four new statuses (parser emits these canonical labels directly, mirroring the
      Phase-3 industry/housing pattern). The COARSE `config/mapping/scb/employment.json` was left unchanged
      (deferred/design-only, not used by the Sweden comparison — matches the Phase 4 file list). Retired gap
      reconciled in `config/analysis/consistency/scb.yaml`: rewrote the KNOWN-GAP comment to RECONCILED and
      changed the `young_retiree` predicate to the canonical casing `employment_status: Retired`.*
- [x] 4.5 **75+ handling:** model ages beyond the 74 cap as out-of-labour-force/retired; document in
      the population provenance.
      *Done: the register caps at 74, so the oldest real band (70-74) is also applied to the 75-85 group
      (`"70-74": ("65-74","75-85")` in `_EMPLOYMENT_STATUS_AGE_BAND_TO_GROUPS`) — 75+ status is modelled
      from real 70-74 cells (predominantly retired) rather than an invented distribution, preserving the
      no-synthetic-distributions invariant. The 18-24 group is proxied by the 20-24 band (no 18-19 band
      free of minors). Both choices documented in inline comments; smoke test confirms 75-85 comes out
      mostly Retired.*

**Files Modified:**
- `.../sweden/constants.py` (17) · `fetch_service.py` (87-103, load_all 329-381) · `parsers.py` (110-205) · `sample_service.py` (18-35, 37-54, 77-90, 136-155) · `data.py` (25)
- `config/mapping/scb_native/employment.json` · `config/analysis/consistency/scb.yaml`

**Dependencies:** None strictly, but touches the most downstream logic — sequence after Phases 1–3.

### Phase 5: Cross-cutting hardening
**Goal:** Coherence decision, tests, docs — before the optional merge.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 5.1 **Register↔survey coherence decision (explicit).** employment_status + industry_sector now
      use register "employed"; employment_type stays AKU. Decide + record whether that mix is
      acceptable, or migrate employment_type's attachment leg too. Write the decision into the audit +
      provenance docs.
      *Decision: **accept the register/survey mix for now, documented, not silent** — do NOT migrate
      employment_type. `employment_status` (`ArRegArbStatus`) + `industry_sector`
      (`ArRegSNI2007Riket`) use the register "gainfully employed" definition; `employment_type`
      (attachment `AKURLSysAnkAr` × hours `NAKUSysselOkArbtidAr`) stays on the AKU survey ILO
      definition. Rationale: the mix is confined to a definitional boundary and is not a hidden
      inconsistency — within the sampler `employment_type` is attached only to register-`Employed`
      personas (the `is_employed` gate), so the two never contradict at the persona level; and no
      register table carries the attachment×hours cross, so migrating employment_type is a larger
      change outside this plan's core with no clean same-fidelity source. Flagged as a revisitable
      modelling choice in both the audit ("Register vs survey mixing" cross-cutting bullet) and the
      Swedish-populations provenance doc (§4.3).*
- [x] 5.2 Add unit tests: one per rewritten parser (education, socioeconomic single-year,
      birth_location conditional, industry aggregation, housing collapse, employment 6-cat) using
      recorded json-stat2 fixtures; extend `tests/_mapping_fixtures.py`; assert mapping resolves the
      new raw labels (guards `test_mapping_engine`/`test_real_mapper_base`).
      *Done: added `tests/test_sweden_parsers.py` (15 tests) driven by six small recorded json-stat2
      fixtures under `tests/data/sweden_parsers/` (captured once from the live SCB API with reduced
      age selections; tests never hit the network). Each parser test asserts the `(age_group, sex) ->
      {label: prob}` shape, per-subgroup normalisation, and — for the three collapses (NACE→12,
      Boendeform→3, status ContentsCode→6) — that the aggregation **sums real cells correctly** vs an
      independent re-indexing of the same fixture; plus the 75+ band-fold and the `OKANT` drop. A
      parametrized test loads the on-disk `config/mapping/scb_native` config and drives the concrete
      `SwedishRealMapper` to confirm every raw label the parsers now emit resolves (non-None) — the
      same resolution surface `test_mapping_engine`/`test_real_mapper_base` guard. (`_mapping_fixtures.py`
      left unchanged — the on-disk scb_native config is the more faithful driver for the switched
      labels; the shared in-memory fixture keeps exercising the engine's branch coverage.)*
- [x] 5.3 Docs: update `docs/reference/scb-pxweb-catalog/scb-source-audit.md` verdicts to "implemented",
      and note new provenance/units in the Swedish-populations doc.
      *Done: all 6 master-matrix verdicts now read "… — implemented (Phase N)"; added an
      implementation-status banner to the executive summary. Swedish-populations doc gained §4.3 "SCB
      source provenance & units" (per-attribute source table, the industry person-counts-not-thousands
      unit change, 75+ handling, and the register/survey coherence note).*

**Files Modified:**
- `tests/test_sweden_parsers.py` (new) · `tests/data/sweden_parsers/*.json` (new fixtures) · audit + provenance docs

**Dependencies:** Phases 1–4.

### Phase 6: employment_status two-table merge (opt-in, all-register)
**Goal:** Recover the status↔education link via the documented odds-multiplication derivation. Only if
the interaction is analytically material.

**Started:** 2026-07-15
**Completed:** 2026-07-15

**Tasks:**
- [x] 6.1 Add `EMPLOYMENT_STATUS_EDU_TABLE` = `AM0210A/ArbStatusUtbM` (CONST, near 17).
      *Done: added `EMPLOYMENT_STATUS_EDU_TABLE = "AM/AM0210/AM0210A/ArbStatusUtbM"` with an all-register /
      opt-in / not-fetched-when-off comment.*
- [x] 6.2 Add `fetch_employment_status` fetching **both** tables (mirror `fetch_employment_type_by_age`,
      FETCH:218-252); return both tags to `tables_used`.
      *Done: `fetch_employment_status` fetches ArRegArbStatus (5-yr bands + the `15-74` baseline aggregate,
      one call) and ArbStatusUtbM (status×edu×sex, `Alder=20-64`, `Tid=2024M12`, the three count
      ContentsCodes `0000088H/0000088A/0000088C`). Returns `(result, ArRegArbStatus, ArbStatusUtbM)`;
      `load_all` appends only the second table to `tables_used` (ArRegArbStatus already listed via the
      Phase-4 tag). Verified live: default-off tables_used has NO ArbStatusUtbM; merge-on does.*
- [x] 6.3 Add `parse_employment_status_combined(raw_status, raw_edu, age_group_map)` in `parsers.py`
      (mirror `parse_employment_type_combined`, PARSE:341-467) implementing the per-persona
      **odds-multiplication** `P(S|A,s)·P(S|E,s)/P(S|s)` with the education 8→coarse collapse and the
      3-cat status reduction + NILF re-expansion, per
      [`employment-status-merge-derivation.md`](../../reference/scb-pxweb-catalog/employment-status-merge-derivation.md).
      *Done: materialises `{(age_group, education_label_casefold, sex): {status: prob}}` over the 6-cat
      taxonomy. Reduces both legs to the common 3-cat set (emp/unemp/NILF), evaluates
      `w=P_A·P_E/P_base` per cell (`_combine_status_3cat`), then re-expands NILF using the age-only
      6-cat sub-split (`_expand_nilf`). Education collapse `_GEN_EDU_LABEL_TO_STATUS_EDU_CODE` maps the 8
      generator ISCED labels onto ArbStatusUtbM's 6 coarse codes (`1,2→21`; `5A→61`, `6→61`), codes
      confirmed against the live metadata dump. Confidentiality nulls tolerated: a suppressed edu leg (or
      a status baseline of 0) sets that status's edu factor to 1 → falls back to the age-only conditional
      (spec §8.2). 75+ handled as in Phase 4 (70-74 band folded onto 75-85); the edu leg is the 20-64
      total (documented mild extrapolation). Live check (35-44, men): post-graduate Employed 0.936 vs
      primary 0.854 vs age-only 0.858 — education now modulates within the band.*
- [x] 6.4 Gate behind an explicit config/flag (default **off** = Phase 4 single-table behavior); surface
      the no-3-way-interaction assumption at the call site and in provenance. Add a derivation unit test
      (known margins → expected combined vector).
      *Done: `merge_status_education` flag threads through `FetchService.load_all` →
      `SampleService.sample_population`/`sample_one` (default **False**) and is surfaced as the
      `--merge-status-education` CLI flag on `generate_scb_population.py` (default off, `store_true`).
      When off, `employment_status_by_edu` is `None`, ArbStatusUtbM is never fetched, and Step 3 is the
      byte-for-byte Phase-4 (age×sex) path (verified live). When on, Step 3 keys on
      `(age_group, education, sex)` with sex- then age-only fallbacks. The no-3-way-interaction assumption
      is stated at the Step 3 call site, in `fetch_employment_status`/`load_all`, and in the CLI log line.
      Tests added to `tests/test_sweden_parsers.py`: the pure-helper derivation test (known
      P_A/P_E/P_base → hand-computed combined vector), null-edu fallback, NILF re-expansion, and a full
      `parse_employment_status_combined` end-to-end against in-test json-stat2 payloads (asserts the exact
      vector, that education modulates, and the missing-edu-leg fallback). New field
      `PopulationDistributions.employment_status_by_edu` (optional, default None).*

**Files Modified:**
- `.../sweden/constants.py`, `fetch_service.py`, `parsers.py`, `sample_service.py`, `data.py` · `tests/`

**Dependencies:** Phase 4. **Guardrails mandatory** (all-register, assumption documented, real cells only) — else do not ship.

---

## Testing Plan

### Unit Tests
- [ ] Each rewritten parser emits the expected dict shape from a recorded json-stat2 fixture.
- [ ] Boendeform→3-tenure and NACE→12-sector collapses sum to the source totals (no cells lost/invented).
- [ ] Confidentiality-null cells are preserved as null, not zero, and don't crash the sampler.
- [x] Merge derivation: known P(S|A), P(S|E), P(S) → expected normalized combined vector.

### Integration Tests
- [ ] Full generate run (small N, fixed seed) succeeds with all 6 new sources.
- [ ] Mapping resolves every new raw label (no unmatched) via `test_mapping_engine`/`test_real_mapper_base`.
- [ ] `test_income_class`, `test_scheme_index`, `test_consistency` still green.

### Manual Verification
- [ ] For each switched attribute, diff the generated marginal against a fresh live SCB query — matches within sampling error.
- [ ] Confirm education attainment now present for ages 75–95+.
- [ ] Confirm the employed/unemployed/not-in-LF split varies by age (single-table) and by education (merge on).

### Edge Cases
- [ ] Age 75+ (beyond the 74 labour cap) → routed to out-of-labour-force, not dropped/crashed.
- [ ] Fully-suppressed subgroup → fail-fast (as `parse_employment_by_sex_education` does at 192-198).
- [ ] `OKANT`/`SPBO`/`OB` unknown buckets handled explicitly.

---

## Documentation Plan

- [ ] Update `docs/reference/scb-pxweb-catalog/scb-source-audit.md` verdicts → implemented.
- [x] Update the merge spec status when Phase 6 ships.
- [ ] Update `docs/swedish_synthetic_populations_and_analysis_outputs.md` — new sources, units, 75+ note, register/survey provenance.
- [ ] Inline comments at the merge call site stating the no-3-way-interaction assumption.
- [ ] Note the register↔survey coherence decision (Phase 5.1) in provenance.

---

## Rollback Plan

1. Each phase is an isolated commit set on `feature/scb-source-improvements`; revert per-phase.
2. **Data considerations:** no persisted migrations — outputs regenerate. Reverting a `*_TABLE`
   constant + its `fetch_*`/`parse_*`/mapping-config edits fully restores the prior source.
3. **Procedure:** `git revert` the phase's commits; regenerate a population to confirm the old marginal returns.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Register vs AKU "employed" mismatch mixed silently across attributes | Med | High | Explicit coherence decision (Phase 5.1); merge stays all-register |
| New raw category labels break mapping (unmatched) | High | Med | Update `scb_native` `real` blocks per attribute; mapping tests assert full resolution |
| employment_status 6-cat change breaks `is_employed`/income gates | Med | High | Phase 4.4 downstream fixups + integration run before merge |
| Merge misread as a synthetic distribution | Med | High | Dedicated spec + guardrails + call-site comment; default merge **off** |
| Single-year age switch breaks `_SCB_BAND_TO_AGE_GROUP` | High | Low | Replace with single-year mapper (Phase 1.2), covered by test |
| No existing fetch/parse tests to catch regressions | High | Med | Add parser unit tests with recorded fixtures (Phase 5.2) |
| Confidentiality nulls treated as zero | Med | Med | Explicit null-tolerance in parsers + edge-case tests |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| 1 — low-coupling refreshes | S | None |
| 2 — birth_location conditional | S | None |
| 3 — taxonomy switches | M | None |
| 4 — employment_status single-table | M–L | (sequence after 1–3) |
| 5 — coherence + tests + docs | M | 1–4 |
| 6 — two-table merge (opt-in) | M | 4 |

---

## References

- Audit: `docs/reference/scb-pxweb-catalog/scb-source-audit.md`
- Merge spec: `docs/reference/scb-pxweb-catalog/employment-status-merge-derivation.md`
- Data model: `docs/reference/scb-pxweb-catalog/scb-pxweb-data-model.md`
- Prior plan: `docs/development/plans/pending/scb-population-attribute-source-audit.md`
- Invariant: `docs/architecture/design-principles.md`
- Touchpoints: `constants.py`, `fetch_service.py`, `parsers.py`, `sample_service.py`, `data.py`, `config/mapping/scb_native/`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- .gitignore
- config/analysis/consistency/scb.yaml
- config/mapping/scb_native/employment.json
- docs/development/plans/active/scb-source-improvements-implementation.md
- docs/swedish_synthetic_populations_and_analysis_outputs.md
- scripts/generate/generate_scb_population.py
- src/population_synthetic/generators/real/data.py
- src/population_synthetic/generators/real/sweden/constants.py
- src/population_synthetic/generators/real/sweden/fetch_service.py
- src/population_synthetic/generators/real/sweden/parsers.py
- src/population_synthetic/generators/real/sweden/sample_service.py
- tests/data/sweden_parsers/ (fixtures, force-added past `data/` ignore)
- tests/test_evaluator.py
- tests/test_sweden_parsers.py

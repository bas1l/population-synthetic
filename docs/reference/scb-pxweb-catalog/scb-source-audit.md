# SCB source audit — best PxWeb table per population attribute

Outcome of the [attribute source-audit plan](../../development/plans/pending/scb-population-attribute-source-audit.md):
a verified pass over the SCB PxWeb source of **every one of the 15 population attributes** the
Swedish generator samples. For each, we found the best public table, and **confirmed it with a live
query** — not just metadata presence (see the ["present ≠ cross-tabulable" trap](./scb-pxweb-data-model.md#5-the-critical-trap-present-in-metadata--cross-tabulable)).

- **Date:** 2026-07-15 · **Scope:** Sweden / SCB. Public PxWeb API only (microdata/MONA out of scope).
- **Method:** metadata swept across 6 subject areas (AM, UF, BE, HE, BO, LE — 1,733 tables; see the
  [catalog](./scb-am-uf-catalog.html) + JSONL dumps), then per-attribute the best candidate was
  POST-queried live (json-stat2) to confirm the intended cross-tab populates and isn't collapsed.
- **Nature:** a **sourcing audit**. It recommends tables; it does not rewire code. Implementation
  (editing `fetch_service.py` + `constants.py`) is a separate task, gated on the
  no-synthetic-distributions invariant.

## Executive summary

**6 of 15 attributes have an actionable improvement; 9 are already on the best available source.**

> **Implementation status (2026-07-15).** All 6 improvements are now **implemented** on
> `feature/scb-source-improvements` (Phases 1–4 of the
> [implementation plan](../../development/plans/active/scb-source-improvements-implementation.md)):
> education_level + socioeconomic_class (Phase 1), birth_location (Phase 2), industry_sector +
> housing_tenure (Phase 3), employment_status (Phase 4). Each switched source has a parser unit test
> over a recorded json-stat2 fixture (`tests/test_sweden_parsers.py`, Phase 5.2). The optional
> two-table employment_status↔education merge ([Phase 6](./employment-status-merge-derivation.md))
> remains deferred/opt-in.

| Verdict | Count | Attributes |
|---------|------:|------------|
| **Switch table** | 4 | education_level, industry_sector, socioeconomic_class, housing_tenure |
| **Switch to add age** | 1 | employment_status *(the originating branch)* |
| **Enrich same table** | 1 | birth_location |
| **Keep (already best)** | 9 | age_group, biological_sex, region, civil_status, birth_country_detail, household_size, income_source, employment_type, parental_structure |

Highest-value wins:
- **education_level** — closes the **75+ coverage gap** (age 16–74 → 16–95+) at near-zero cost.
- **housing_tenure** — turns a dwelling-level marginal into a **person-level** tenure × age × sex distribution.
- **industry_sector** — restores a genuine **age × sex** breakdown the current AKU table collapses to a working-age total.

## Master matrix

| # | Attribute | Area | Current table | → Recommended | Verdict | Key gain / gap |
|---|-----------|------|---------------|---------------|---------|----------------|
| 1 | age_group | BE | `BE0101A/BefolkningNy` | — | **Keep** | Canonical single-year register; nothing finer. |
| 2 | biological_sex | BE | `BE0101A/BefolkningNy` | — | **Keep** | Binary only (register constraint); no alternative. |
| 3 | region | BE | `BE0101A/BefolkningNy` | — | **Keep** | DeSO tables go finer but drop single-year age. |
| 4 | civil_status | BE | `BE0101A/BefolkningNy` | — | **Keep** | Full 4-cat × age × sex × region. |
| 5 | birth_location | BE | `BE0101E/FolkmFodlandHVD` (Alder=TOT1) | **same table, add Alder×Kon, Tid=2025** | **Enrich — implemented (Phase 2)** | Gains age+sex on the 3-way SE/EU/non-EU split, free. |
| 6 | birth_country_detail | BE | `BE0101E/FodelselandArK` | — | **Keep** | Finest country×age×sex table (206 countries). |
| 7 | household_size | BE | `BE0101S/HushallT03` | — | **Keep** | No size-by-age/sex table exists; keep + aggregate. |
| 8 | education_level | UF | `UF0506B/Utbildning` (16–74) | **`UF0506B/UtbBefRegionR`** (16–95+) | **Switch — implemented (Phase 1)** | **Closes the 75+ gap.** Same series/values, age→95+. |
| 9 | employment_status | AM | `AM0401P/NAKUBefUtbNivAr` (no age) | **`AM0210D/ArRegArbStatus`** or `AM0401A/AKURLBefAr` | **Switch to add age — implemented (Phase 4)** | Adds status × age (× sex); drops the education cross (no 3-way exists). Caps at 74. |
| 10 | industry_sector | AM | `AM0401I/AKURLSysSNI07Ar` (age→total) | **`AM0210F/ArRegSNI2007Riket`** | **Switch — implemented (Phase 3)** | Restores real age × sex. Needs collapse to 12-sector schema; register def. |
| 11 | employment_type | AM | `AM0401I/AKURLSysAnkAr` + `AM0401S/NAKUSysselOkArbtidAr` | — | **Keep** | No single attachment×hours table exists; merge is structural. Caps at 74. |
| 12 | socioeconomic_class | HE | `HE0110A/SamForvInk1` (5-yr bands) | **`HE0110A/SamForvInk1a`** (single-year) | **Switch — implemented (Phase 1)** | Finer age, coverage from 16. Same income measure. |
| 13 | income_source | HE | `HE0110F/TabVX13InkStruktN` | — | **Keep** | Only sex-bearing alt loses the employment×age conditioning. |
| 14 | housing_tenure | BO | `BO0104D/BO0104T04` (dwelling-level) | **`HE0111A/HushallT31`** (person-level) | **Switch — implemented (Phase 3)** | Adds tenure × single-year age × sex. Needs `Boendeform`→tenure collapse map. |
| 15 | parental_structure | LE | `LE0102B/LE0102T17` | — | **Keep** | Already register full-count (not a survey); finest age. |

## Per-attribute detail (the 6 actionable ones)

### 8 · education_level → switch to `UF/UF0506/UF0506B/UtbBefRegionR`
Same register series as the current `Utbildning` table (identical `Region × UtbildningsNiva(8, ISCED97) × Kon`, values match byte-for-byte where they overlap) but single-year `Alder` runs **16–95+** instead of 16–74. **Verified:** age-30 cells identical between tables; age-80 cells populate. Directly closes the 75+ attainment gap; 2025 available. Only change: drop the `tot16-74` synthetic-total category (this table doesn't carry it — sampling should select explicit ages anyway).

### 9 · employment_status → switch to `AM/AM0210/AM0210D/ArRegArbStatus`
The originating investigation: **no SCB table gives status × education × age**. The current `NAKUBefUtbNivAr` is status × education × sex with **no age at all**. To gain age (the branch's goal), switch to the register `ArRegArbStatus` (status × 5-yr age bands × sex, full-count) or AKU `AKURLBefAr` — losing the education cross, which is unavoidable *in a single table*. **Coverage gap:** both cap at age 74; there is no labour-force status for 75+ anywhere on the API (treat 75+ as out-of-labour-force). Full rationale in [`scb-pxweb-data-model.md`](./scb-pxweb-data-model.md).

> **Optional enhancement — recover the education cross by merging two register tables.** The lost
> status↔education link can be restored *without* a 3-way table, by combining `ArRegArbStatus`
> (status×age×sex) with the register `ArbStatusUtbM` (status×education×sex) via a documented
> per-persona odds-multiplication ("no 3-way interaction") derivation. This is the **only** attribute
> that would combine multiple tables, so it has its own dedicated spec:
> **[`employment-status-merge-derivation.md`](./employment-status-merge-derivation.md)**. Ship the
> single-table switch first; treat the merge as an explicitly-documented, all-register follow-up.

### 10 · industry_sector → switch to `AM/AM0210/AM0210F/ArRegSNI2007Riket`
Current AKU table collapses `Alder` to `tot15-74` (a working-age total — the trap) and combines sex. The register table restores **industry × real age bands × sex** (verified: 12 non-collapsed cells, full-count, to 2024). Caveats: 2-digit NACE (~52 codes) must be **aggregated up** to the canonical 12-sector schema (summing real cells — legitimate); values are person counts (not thousands); register "employed" ≠ AKU/ILO definition. *Also:* the current code's `Kon=1+2` collapse is a choice — sex could be restored on the existing table for free even without switching.

### 12 · socioeconomic_class → switch to `HE/HE0110/HE0110A/SamForvInk1a`
Same income-bracket register measure as the current `SamForvInk1`, but **single-year `Alder`** (16–100) instead of 5-year bands, extending coverage down to 16. **Verified:** 26/30 cells non-null (the 4 nulls are legitimate confidentiality suppression at age-16 × high-bracket). `ContentsCode` differs (`HE0110AD`). The 4-class derivation must tolerate nulls in sparse cells.

### 14 · housing_tenure → switch to `HE/HE0111/HE0111A/HushallT31`
Current `BO0104T04` is **dwelling-level** — tenure has no person age/sex. `HushallT31` gives **`Boendeform` (housing type) × single-year age × sex × region**, register/full-count. **Verified:** 12/12 non-null person-level cells. `Boendeform` maps onto the 3-way owner / tenant-owned / rented split via a small **collapse map** (`SMAG`→owner-house, `SMBO`/`FBBO`→bostadsrätt, `SMHY0`/`FBHY0`→hyresrätt; `SPBO`/`OB`/missing folded or dropped explicitly). No table exposes `Upplatelseform` itself by person age/sex, so `Boendeform` is the route.

> **Addendum (2026-07-16) — a tenure × age × income joint table exists, but is not a drop-in.**
> Not surfaced by the original sweep (which stored only AM+UF dumps and evaluated tenure and
> socioeconomic_class as independent best-sources): **`HE/HE0110/HE0110F/TabVXDispI4C`**
> ("Economic standard by region, age, type of household, tenure"). It **does** cross tenure with
> age *and* an income axis — variables `Upplatelseform` (rented / tenant-owned / owner-occupied,
> the same 3-way split), `Alder`, `Hushallstyp`, `Region`, `Tid` (2012–2024), and an economic-standard
> axis (`InkomstTyp` = equivalised disposable income incl./excl. capital gains; `ContentsCode` =
> mean/median SEK, relative-poverty threshold counts <40/50/60/70 % of median, >200 %, total persons).
> **Live-verified** as a genuine cross-tab (12/12 cells non-null): 2024, age 20–64, median equivalised
> disposable income — rented ≈ 265.5k, tenant-owned ≈ 381k, owner-occupied ≈ 397.2k SEK.
>
> **Why it is not adopted for `housing_tenure`** (each mismatch is against the generator's conditioning
> scheme, so using it would break like-for-like conditioning, not just add data):
> 1. **Age is coarse bands only** (`0–19`, `20+`, `20–64`, `20–65`, `65+`, `66+`) — no single-year `Alder`, unlike every other Sweden attribute.
> 2. **The income axis is household-*equivalised* disposable income** (relative-poverty framing), **not** the project's *personal* `SamForvInk1a` bracket → 4-class (`Poverty`/`Working Class`/`Middle Class`/`Wealthy`) derivation. Different unit *and* definition, so it does not condition on the same `socioeconomic_class` the sampler produces.
> 3. **No sex dimension** (it carries `Hushallstyp` instead).
> 4. It reports **per-cell income statistics** (median/mean/threshold counts), **not** a person-frequency joint distribution to sample from.
>
> **Consequence.** There is **no** public-API table crossing tenure × single-year age × sex × *personal*
> income bracket, so under the no-synthetic-distributions rule `housing_tenure` and `socioeconomic_class`
> stay on their separate marginals (both conditioned on shared age/sex, sampled independently). Coupling
> them would require either (a) deliberately adopting `TabVXDispI4C` and accepting its coarser,
> differently-defined axes, or (b) a documented max-entropy odds-merge of the two 2-way margins
> (age×sex×tenure ⊗ age×socioeconomic) — the same "no 3-way interaction" derivation already specced for
> [employment_status](./employment-status-merge-derivation.md). Neither is a pure API pull; both are
> explicit modelling choices for a future maintainer.
> Related non-tenure tables in the same folder, for reference: `TabVXDispI69` (economic standard ×
> employment × background × age) and `TabVX13InkStruktN` (income structure × age × occupation — the
> current `income_source` source).

### 5 · birth_location → enrich the existing `BE/BE0101/BE0101E/FolkmFodlandHVD`
Not a table switch — the current query pins `Alder=TOT1` (all-ages aggregate). The same table carries single-year `Alder` (elim=False) and `Kon`, now to 2025. **Verified:** age×sex cross-tab on the 3-category SE/EU/non-EU field populates 8/8, age not collapsed. Handle the `OKANT` (unknown) birth bucket.

## Cross-cutting findings

- **The 75+ age edge.** education_level's switch **closes** it (→95+). But **labour attributes cannot**: employment_status and employment_type both cap at 74 (AKU universe) with no register table beyond it — 75+ must be modelled as effectively out-of-labour-force. Population/income/housing attributes (BE/HE/BO) already cover the full age range.
- **Register vs survey mixing.** Three recommended switches (education already register; industry_sector, employment_status) move labour attributes onto **register (RAMS/BAS)** definitions, while employment_type stays **AKU survey**. Register "employed" ≠ AKU/ILO "employed" — a coherent generator should be aware it is mixing definitions across attributes. Worth a deliberate decision, not a silent switch.
  - **Decision (Phase 5.1, 2026-07-15): accept the register/survey mix for now, documented, not silent.**
    `employment_status` (`ArRegArbStatus`) and `industry_sector` (`ArRegSNI2007Riket`) both use the
    **register** "gainfully employed" definition; `employment_type` (attachment `AKURLSysAnkAr` +
    hours `NAKUSysselOkArbtidAr`) stays on the **AKU survey** ILO-employed definition. The mix is
    **explicit and confined to a definitional boundary**, not a hidden inconsistency: within the
    sampler, `employment_type` is attached only to personas the register marks `Employed`
    (the `is_employed` gate), so the two never contradict each other at the persona level — a
    register-employed persona simply gets an AKU-defined *type*. Rationale for not migrating now:
    `employment_type`'s attachment leg has no register equivalent that carries the attachment×hours
    cross (RAMS gives status, not contract type × weekly hours), so migrating it is a larger,
    separate modelling change outside this plan's core and with no clean same-fidelity source.
    **This is a known modelling choice the maintainer may revisit** — if attribute-level definitional
    coherence is later judged material, the follow-up is to source `employment_type` (or a proxy of
    it) from a register table, or to drop it in favour of register hours. Flagged again in the
    Swedish-populations provenance doc.
- **Confidentiality suppression** produces legitimate nulls in sparse cells (young × high-income, etc.). Recommended sources were checked for this; the samplers/derivations must tolerate null cells rather than treating them as zero-with-certainty.
- **Binary sex** is a hard SCB register constraint across every area — not fixable by table choice.
- **No-synthetic-distributions holds throughout.** Every "keep" where a breakdown is missing
  (household_size by age, income_source by sex) is kept *because no real table provides it* — the
  correct outcome is to drop/aggregate that dimension, never to fabricate it. No recommendation
  invents a distribution; the two aggregation steps required (industry→12 sectors, Boendeform→3
  tenures) sum **real** API cells.

## Out of scope

The one genuinely unavailable cross-tab (employment status × education × age) exists only in SCB
**microdata** (MONA/RTB), which requires a formal research agreement and is outside this project's
public-API sourcing model. Not pursued.

## See also
- [`scb-pxweb-data-model.md`](./scb-pxweb-data-model.md) — why SCB data is shaped this way
- [`scb-am-uf-catalog.html`](./scb-am-uf-catalog.html) — searchable table inventory (AM+UF)
- Plan: [`scb-population-attribute-source-audit.md`](../../development/plans/pending/scb-population-attribute-source-audit.md)
- Wiring today: `src/population_synthetic/generators/real/sweden/{fetch_service.py,constants.py}`

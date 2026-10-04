# Plan: Fix the Swedish Mapping Rules and Real-Reference Defects Found by the SCB-Checked Audit

**Date:** 2026-10-04
**Author:** Basil
**Status:** In progress — Phase 3 code done 2026-10-04 (re-sample pending, see Phase 3 implementation notes)
**Base Branch:** `dev` (note: `feature/household-size-persons-unit` is unmerged; implementation may
stack on it, since Phase 3 shares its re-sample)
**Branch:** `feature/mapping-fixes-scb-audit`

---

## Overview

The SCB-checked mapping audit (2026-10-03/04) checked every flagged synthetic-to-canonical mapping
of the Swedish native tier (`config/mapping/scb_native/`) against SCB's own definitions. It found
defects at three levels: the matching engine (substring hits, no negation, hours ignored,
declared-order tie-breaks), the per-attribute config rules, and the real-population sampler that
produces the reference the mapped personas are scored against. This plan fixes all three in
dependency order, then runs **one** combined re-sample and re-run that also absorbs the
household-size switch and the judge context-leak fix. No LLM persona generation is re-run.

## Problem Statement

The audit's curated per-row list holds **12,793 flagged rows** (combo × persona × attribute) from
the 58 capped combinations. Final verdicts:

| Verdict | Rows | Meaning |
|---|---|---|
| `real_error_wrong_category` | 7,268 | mapped to a category SCB's definition rules out |
| `real_error_unmapped` | 2,237 | left `__UNMAPPED__` although SCB's definition places it |
| `judge_false_alarm` | 1,643 | first-pass flag overturned; current mapping is correct and must be kept |
| `undeterminable` | 1,494 | text too vague to place; needs a policy rule, not a fix |
| `design_decision` | 151 | correct answer depends on a user decision (recorded below) |

Real errors total **9,505**, concentrated in civil_status (2,797), education_level (1,811),
housing_tenure (1,418), employment_type (837), income_source (699), industry_sector (639) and
parental_structure (486).

**Spot check** (60 cards drawn across groups, 42 answered by the user; agreement with the final
verdict, 95 % Wilson intervals):

| Group | Agree / n | Conclusion |
|---|---|---|
| Errors (wrong category or should be mapped) | 15/16 = 94 % (72–99 %) | apply the error verdicts |
| First-pass false alarms | 11/12 = 92 % (65–99 %) | keep current mappings |
| Too vague | 7/14 = 50 % (27–73 %) | not validated; resolve by policy rules (Open questions) |
| Overall | 33/42 = 79 % (64–88 %) | supports applying errors, not "every verdict is right" |

Education was barely spot-checked by the user (2 of 20 cards); its open calls were settled by
explicit decisions instead.

Two real-reference defects surfaced alongside: the sampler's output depends on `PYTHONHASHSEED`
and gives employed 18–24 personas the 65–74 employment_type mix, and `median_from_brackets`
returns bracket midpoints that are off by up to 45 tkr, which shifts the socioeconomic_class
reference by up to 10 points in single cells.

## Decisions recorded

| Decision | Rule |
|---|---|
| Sambo / cohabiting | Single/Never Married (civil status is legal register status; a sambo is not married) |
| Separated | Married (Sweden has no legal separation) |
| Upper secondary, length unstated | Upper Secondary 3 yrs (ISCED 3A); 3C only with an explicit ≤ 2-year length |
| Eftergymnasial / post-secondary | routed by stated length: < 3 yrs → 4+5B, ≥ 3 yrs / kandidat → 5A; never 3A |
| Bare "högskoleexamen" (337 rows) | Post-Secondary < 3 yrs (4+5B); "3 år"/"kandidat" → 5A; "högskoleexamen (bachelor)" stays undeterminable (unchanged) |
| Folkhögskola | unmapped (no general SUN level) |
| Income, main source | wage first: any stated paid work → Wage; Wage vetoes only negation, job-seeking and past-employer pension |
| Income components 325 / 330 | fetch them; two new income_source categories |
| Socioeconomic boundaries | low income / låginkomst / underklass → Poverty; modest / moderate / lower class / lägre klass → Working; median / average income → Middle |
| Socioeconomic occupation words | proxy via a sourced SCB income-by-occupation table — **reopened** as a decision point in Phase 4 after the assessment |
| Parental structure, two phases | the earlier phase wins ("both parents until divorce" → Natural Parents); drop the `mother remarried` token |
| Labour-market services | Arbetsförmedlingen / staffing → SNI 78 (Financial & Business Services) |
| Warehouse work without trade context | Transport (SNI H52) |
| Household-size reference unit | persons (`BE0101DK`); done on `feature/household-size-persons-unit`, joins the combined re-run only |
| Birth-region labels | rename to what FolkmFodlandHVD measures (EU vs non-EU) and fix the country lists |
| First-pass false alarms | keep the current mapping in every change (regression gate) |
| "Too vague" verdicts | handled by policy rules, not by further review |

## Phases

The ordering rule: engine first (it changes what every config token means), config second
(expressed natively on the new engine), real-population fixes third (they need a re-sample),
then the proxy decision and the label rename. Each phase is one or more self-contained commits.

**Token lists.** The full per-attribute token lists live in the audit's simulation scripts
(section A: six patch files, one per attribute; section B: the industry, parental, socio and
small-attribute simulators) and the engine prototype's reports, all in the session scratch area.
Before implementation starts, copy them into the branch's working notes; the tables below name
the rules, not every token. Every config change was simulated against the full extracted pool
(11,461 personas per attribute) through the repository's own `mapping_engine.resolve`, which
reproduced today's mapped value on 100 % of rows before any change.

### Phase 1 — Matching engine (plus the education tokens it requires)

**Goal.** Replace substring matching, add negation, an hours facet and explicit rule priority,
with every knob in config and malformed config raising.

**Files.** `src/population_synthetic/analysis/mapping/mapping_engine.py`,
`analysis/mapping/synthetic_mapper/base.py` (ties list beside `self.misses`, `:124`), the loader
that writes `{slug}.misses.csv` (add `{slug}.ties.csv`), `_index.json` and every attribute file
in **all four** mapping directories (`scb_native`, `scb`, `istat`, `ssb`), `education.json`.

| Commit | Change |
|---|---|
| 1a | Required `matching` block per side in every `_index.json` (`token_mode`, `negation`, `tie_break`) and a `priority` list per attribute file. New `validate_rules` raises on: missing block, unknown matcher key (replaces the silent composite fallback in `_is_composite`, `mapping_engine.py:163`), unknown `token_mode`, non-positive negation `window`, `priority` not a permutation of `values`, overlapping facet bands or a facet target outside `values`. Values set to reproduce today exactly (`substring` / `null` / `["priority"]`). |
| 1b | `tie_break`: collect every hitting value within the winning tier; `longest` (longest matched token; summed group hits for `all_of`) then `priority`. Tier precedence unchanged. `employment_status` uses BAS order Employed > Unemployed > Student > Retired > Sick > Other; `income_source` puts Wage first; the rest `["longest","priority"]`. Every multi-hit is written to `{slug}.ties.csv`. Add config token `it-konsult` (else 23 "IT-konsulting" rows regress to F&B). |
| 1c | `token_mode: prefix` for `scb_native` synthetic (character before the match must not be alphanumeric), with per-token `{"token": …, "mode": "substring"}` overrides for compound heads (`anställd`, `lön`, `teknik`, `vård`, `pension`, …). Generate the override worklist over the **full `01_Raw` pool**, not the capped mirror. **Same commit:** the education post-secondary length routing (4+5B `all_of` [HE] × [short], 5A `all_of` [HE] × [≥ 3 yrs / kandidat]) — without it 206 capped cells of "Eftergymnasial utbildning, 3 år eller längre" fall to `__UNMAPPED__`. |
| 1d | Negation: a cue (`inte`, `ej`, `ingen`, `not`, `no`, `never`, …) within `window` words before a token in the same clause discards that hit; applies to `contains`, `all_of` members and `none_of`; per-attribute opt-out (`non-binary`, `non-EU`). Past tense is not negation. |
| 1e | `numeric_facet` on synthetic `employment_type`: extract hours or % (40 h week), re-band with AKU agreed hours (1–19 / 20–34 / 35+) after the walk; a straddling range or a comparator ("över 30") leaves the walked value and logs `facet_ambiguous`. Then remove the hour tokens (`1-19`, `20-34`, `timmar i veckan`, `50%`, …) from the attachment `all_of` rules; keep `heltid`/`deltid` as the no-hours fallback. |

`scb`, `istat` and `ssb` keep the behaviour-preserving block; only `scb_native` synthetic switches.

**Rows (each fix measured alone on today's config; fixes overlap, so they do not add).**

| Fix | Curated rows changed | → correct category | wrong → `__UNMAPPED__` | False-alarm regressions | Capped cells changed |
|---|---|---|---|---|---|
| prefix + substring overrides | 1,030 | 559 | 385 | 3 | 700 (0.93 %) |
| negation | 140 | 28 | 107 | 0 | 47 |
| hours facet | 264 | 197 | 0 | 0 | ≈108 |
| longest + priority (chosen) | 1,763 | 1,384 | 0 | 25 (23 fixed by `it-konsult`) | — |
| all four combined | 3,136 | 2,087 | 493 | 47 | 2,509 (3.33 %) |

`word` mode (both boundaries) was rejected: 112 false-alarm regressions, 7.7 % of cells change.

**Tests** (`tests/test_mapping_engine.py`, fixtures in `tests/_mapping_fixtures.py`): prefix
rejects left-embedded tokens (eftergymnasial, female, parents, "40 timmar" vs `0 timmar`);
prefix accepts compound modifiers (högskoleexamen); substring override matches heads (månadslön);
`word` needs both boundaries; mode applies to `all_of` and `none_of`; negation suppresses
("inte gift"), stops at a clause break, spares cue-initial tokens ("never married"); a negated
veto does not veto; attribute opt-out; facet re-bands (15 h, 35 h, 34.5 h, 80 %, 90 %) and logs
straddles/comparators; `longest` beats declared order; `priority` uses the priority list; equal-
length ties fall to priority and are logged; every validator branch raises. Existing
`test_contains_substring_match` (l.27) and `test_first_matching_value_wins_by_declared_order`
(l.37) declare `substring` / `["priority"]` explicitly. Integration: ties sidecar records
candidates (`tests/test_synthetic_mapper_base.py`); golden test that `scb`, `istat`, `ssb` map
byte-identically to today; config test that every directory declares `matching` and every
attribute `priority`.

**Docs.** `mapping_engine.py` module docstring (l.1–63); `docs/architecture/comparison-mapping.md`
matcher vocabulary, tie rule and ties sidecar ("Unified symmetric mapping config", ~l.125–143);
`config/mapping/scb_native/README.md`; `docs/architecture/configuration.md` (`_index.json` keys).

**Exit check.** The 100 % reproduction harness passes after 1a; after each later commit, re-map
the capped mirror and count personas newly `__UNMAPPED__` per combo (Impact, full-N risk).

### Phase 2 — Config rule changes per attribute

**Goal.** Apply the error verdicts and decisions in `config/mapping/scb_native/` synthetic blocks.
Rules simulated as config stop-gaps for engine defects (`none_of` vetoes standing in for word
boundaries or negation; single-group `all_of` standing in for priority) are implemented
**natively** on the Phase 1 engine instead: drop the veto, use a `priority` entry. Re-run both
simulation harnesses after the conversion; each attribute must reach the fixed counts below with
zero broken rows and zero false-alarm regressions beyond the three named.

**2A — civil, education, employment, housing, income (simulated together).**

| Attribute (file) | Main rule changes | Real errors | Fixed | Coverage |
|---|---|---|---|---|
| civil_status (`civil_status.json`) | sambo/cohabiting/särbo/partner → Single; separated → Married; registered partnership stays Married; 31 new misspelling/foreign tokens | 2,797 | 2,785 | 99.6 % |
| education_level (`education.json`) | post-secondary length routing (Phase 1c); bare högskoleexamen → 4+5B; folkhögskola unmapped; upper secondary → 3A, 3C only with ≤ 2 yrs; folkskola → ISCED 1; incomplete gymnasium → ISCED 2; doctoral/entrance-qualification vetoes on 5A; programme names, old exams | 1,811 | 1,633 | 90.2 % |
| employment_status (`employment.json`) | job-seeking/negated/past text off Employed; working students and working pensioners stay Employed; förtidspension/sjukersättning → Sick Leave; homemaker/carer → Other; ~127 occupation tokens → Employed | 408 | 354 | 86.8 % |
| employment_type (`employment_type.json`) | negated/zero-hour → Not Applicable; fixed-term, project, probation → Temporary; own company → Self-employed; drop `timmar i veckan` from short-part-time groups; `fast tjänst`/`fastanställd` → Permanent. Hours conflicts (260 rows) are Phase 1e | 837 | 208 (+≈197 by 1e) | 24.9 % (≈48 % with 1e) |
| housing_tenure (`housing_tenure.json`) | Owner vetoes apartment/BRF/rental words; owned flat → Tenant-owned; `Ägarlägenhet` unmapped (OB not fetched); bostadsbolag → Rental; public/kommunal housing → Rental | 1,418 | 1,380 | 97.3 % |
| income_source (`income_source.json`) | wage first; parental/family support unmapped; förtidspension/disability → SAC; övertids-/semesterersättning → Wage; socialbidrag/försörjningsstöd → Social Assistance; ~430 occupation/employer tokens → Wage. CSN/barnbidrag and bostadsbidrag rows move in **Phase 3** with the new categories | 699 | 526 (+55 in Phase 3) | 83.1 % incl. Phase 3 |

Remaining employment_type rows are policy (193 partial targets, 145 no target): Open questions 1–2.

**2B — industry, parental, socio, small attributes.**

| Attribute (file) | Main rule changes | Errors with a category | Fixed |
|---|---|---|---|
| industry_sector (`industry_sector.json`) | SNI by activity, not ownership: "professional, scientific and technical" and R&D → F&B; `teknik` keeps I&C but vetoes engineering/chemistry/construction; municipal care → Healthcare; IT consultancy → I&C; `vård` vetoes beauty/nature/veterinary; warehouse → Transport; labour-market services → SNI 78; ~250 long-tail tokens; `pensionär` veto on Healthcare; `ikt-` not `ikt` | 537 | 520 |
| parental_structure (`parental_structure.json`) | cohabiting/married couples → Natural Parents; divorce + residence with mother/father → SM/SF; parent death → SM/SF/Other; NP vetoes divorce/death/joint custody; father-led stepfamilies → FS; adoptive parents → Natural Parents (SCB "ursprungliga" includes adoptive); `grandfather only` → Other | 407 | 382 |
| socioeconomic_class (`socioeconomic.json`) | explicit poverty cues → Poverty; boundary decision phrases; high-income/affluent → Wealthy (vetoes medelhög); lower-middle → Working (115 unflagged rows move, consistent with 19 kept false alarms); middle/upper misspellings | 176 | 166 |
| biological_sex | Male vetoes `female`; `cis man`, `herr`, `kvinn` | 11 | 10 |
| region | `ostergotland`, `västergötland`, `gästrik`; `equals "Svedala"` | 11 | 11 |
| birth_country_detail | Sweden vetoes "född i utlandet"/"born abroad" (also fixes 3 birth_location rows via `refine_from`) | 6 | 6 |
| household_size | "With parents (2)" → 3 persons; "N personer" tokens | 3 | 2 |
| age_group | none (86–90 outside the 18–85 frame; 42 false alarms kept) | — | — |

Gated in 2B (do not apply before sign-off): parental Q1's joint-custody → unmapped (Open
question 14) and socio S3's removal of `student`/`studerande`/`pensionär` (deferred to Phase 4).

**Tests.** One parametrised regression test per attribute over a fixed sample of curated rows
(raw → expected), including every first-pass false alarm named in this plan; a test that each
synthetic block's `priority` list matches the BAS / wage-first orders.

**Docs.** `config/mapping/scb_native/README.md` (per-attribute rule notes: adoptive = Natural
Parents, contradicting the old README l.85–87; sambo; högskoleexamen; folkhögskola).

### Phase 3 — Real-population fixes and one combined re-sample

**Goal.** Fix four sampler/fetch defects and re-sample the real reference **once**, together with
the household-size switch.

| Item | Files | Change |
|---|---|---|
| Hash-seed determinism | `generators/real/helpers.py:14`; `sweden/sample_service.py:87, :200`; `sweden/parsers.py:1028` | `VALID_AGE_GROUPS` set → ordered tuple; sort the key union at parsers `:1028`; check Italy uses (`italy/parsers.py`). Root cause: `employment_type_by_age` has no 18–24 or 75–85 cell, so the age fallback at `:200` takes whichever group the hash order yields (65–74 under the published seed); 1,140 of 10,000 personas affected, 871 values differ between hash seeds 0 and 1. Fill 18–24 from the AKU "15–24" cell via an explicit `age_group_map` (documented proxy incl. ages 15–17); 75–85 per Open question 17. |
| `median_from_brackets` | `generators/real/income_class.py:22–36` | Linear interpolation inside the median bracket (same within-bracket uniformity `classify_brackets`, `:39`, already assumes). Midpoints are off by up to 45 tkr; interpolation is within 3.3 tkr of SCB's published medians in all 20 band × sex cells. Norway uses the same function (`norway/parsers.py:1045`); its reference is not re-sampled here. |
| Income components 325 / 330 | `sweden/fetch_service.py:397` (`Inkomstkomponenter` at `:403–404`); `sweden/parsers.py:1173` (`parse_income_source`); `config/mapping/scb_native/income_source.json` | Add 325 (generella bidrag) and 330 (bostadsstöd); make the value stride at `parsers.py:1198` order-safe (derive from `id`); two new values with `real` equals on SCB's English labels read from TAB1388 `/en/` metadata; move synthetic CSN/barnbidrag (→ 325) and bostadsbidrag/bostadstillägg (→ 330) tokens out of Insurance (55 error rows + 76 unflagged). Category set 6 → 8; no strategy YAML lists income options. |
| Sex/age fallbacks | `sweden/sample_service.py:80–85, 86–90, 114–118, 121–125, 136–140, 149–154, 163–167, 176–180, 194–198, 199–203, 219–223, 240–244, 249–251, 261–265` | Replace every silent fallback with `raise ValueError(<cell>)`, except the declared 18–24 / 75–85 proxies. Dormant today: no (age_group, sex) cell is missing in any table. |

**Re-sample and expected-diff check.** `sample_from` draws one uniform per persona whatever the
probabilities, and no changed attribute conditions a later one, so a change is confined to its
own attribute. Re-sample stepwise from the cache (seed 42, n 10,000, `PYTHONHASHSEED=0`), diffing
each step against `data/scb_api/scb_population_n10000_seed42_merge-status-edu_2026-07-16.json`:

| Step | Attribute allowed to change | Why |
|---|---|---|
| household switch (already on branch) | `household_size` | persons series `BE0101DK` |
| hash-seed + AKU age map | `employment_type` | 18–24 and 75–85 employed personas leave the 65–74 mix |
| median interpolation | `socioeconomic_class` | class boundaries move with the median |
| 325 / 330 fetch | `income_source` | larger denominator per (status, age) cell; two new categories |
| fail-fast fallbacks | none | branches never execute on current data |

Any change outside the allowed column stops the run. All other attributes must be byte-identical.
Extend the SCB cache TTL (`config/database/caches/scb/`, 90 days on mtime) for this run so only
the new queries (`BE0101DK`, TabVX13 with 325/330) are fetched live; any other live re-fetch could
pick up an SCB revision.

**Tests.** Sample in two subprocesses with different `PYTHONHASHSEED`, assert byte-identical
output; interpolated band medians within ±5 tkr of SCB's published 2024 medians (fixture from
`SamForvInk1` `HE0110J8`); each fallback site raises on a missing cell; `parse_income_source`
gives the same result under a permuted dimension order.

**Docs.** `docs/scb_population_and_comparison.md`, `docs/scb_population_distribution_analysis.md`,
`docs/reference/scb-pxweb-catalog/scb-source-audit.md` (325/330, AKU age map, median method),
`docs/architecture/sweden-generation-explorer/js/data.js` (income node).

#### Phase 3 implementation notes (code done 2026-10-04; re-sample NOT run)

Commits: `3b0dfa3` (hash-seed determinism + AKU age proxies + fail-fast), `74b135e` (interpolated
median), `80d827b` (325/330), plus the docs / `--cache-ttl-days` commit that follows them. All
numbers below come from a scratch copy of the SCB cache (seed 42, n 10,000), never from
`data/scb_api/`.

| Item | What was done | Measured effect |
|---|---|---|
| Hash-seed determinism | `VALID_AGE_GROUPS` is an ordered tuple (youngest first); attachment/hours key union sorted. AKU attachment label `"15-24 years"` → 18-24 (`constants.AKU_ATTACHMENT_AGE_LABEL_MAP`); 75-85 → 65-74 declared proxy (`constants.EMPLOYMENT_TYPE_AGE_PROXIES`, Open question 17 default), applied in `parse_employment_type_combined`, which now raises if any age group × sex cell is uncovered or a proxy would overwrite an API cell. Proxies recorded in the output's `tables_used` note for `AKURLSysAnkAr`. | Byte-identical output under `PYTHONHASHSEED` 0 and 1. Against the pre-P3 code run with hash seed 0 (which reproduces the published file except `household_size`): only `employment_type` changes, for 530 employed personas, all aged 18-24. 75-85 personas are unchanged, because the proxy is the cell hash seed 0 fell back to. |
| Reproduce published under hash seed 0 | Not possible as "determinism only": the deterministic code has no age fallback left, so the 18-24 change is the intended AKU fix, not an ordering artefact. | — |
| Norway / Italy | Shared `VALID_AGE_GROUPS` only; their samplers keep `reversed(VALID_AGE_GROUPS)` age fallbacks (out of scope). Reversed tuple order is 75-85, 65-74, …. Norway's education table has no 75-85 cell (checked offline on the SSB cache), so the fallback picks 65-74 — the same cell hash seed 0 picked: Norway output unchanged. Italy could not be checked offline (ISTAT cache incomplete); unchanged whenever 65-74 is present. **Follow-up:** Norway's 75-85 education fallback is itself an undeclared proxy. | — |
| Fail-fast | Every other-sex / other-age-group fallback in the Swedish sampler is `_require_cell(...)` → `ValueError` naming the cell; income_source raises on a missing status or age cell. Kept by design: the merged (age, education, sex) employment_status cell falls back to the person's **own** (age, sex) register cell (documented merge behaviour); its other-sex step was removed. | Dormant on current data (no output change). |
| Median | `median_from_brackets(edges, counts)`: linear interpolation in the median bracket. Oracle fixture `tests/data/income_class/scb_median_oracle_2024.json` (SamForvInk1a counts vs SamForvInk1 `HE0110J8`, 20 cells). | Max abs error vs SCB published median 45.3 → 3.3 tkr; mean 19.7 → 0.9 tkr. 544 personas change `socioeconomic_class` (Middle 40.5 → 41.4 %, Working 29.4 → 28.7 %). **Norway:** national median 625,000 → 514,594 NOK; its class shares move by up to 19 points (Poverty, women 65+); Norway's reference is not re-sampled. |
| 325 / 330 | `constants.INCOME_SOURCE_COMPONENTS` = 300…335 (8). Live `/en/` labels: `general allowance`, `housing allowance`; the table note lists studielån under 325 (Open question 10 resolved: studielån → General Allowances). `parse_income_source` derives strides from `id`/`size`, rejects an unselected extra dimension, and keys age on the **code** (`20-29`, `80-`): the live response switched its labels to en dashes, which the old label lookup missed and would have silently sent to the first age key. `scb_native/income_source.json`: values + `real` equals for **General Allowances** and **Housing Allowance**. | 1,082 personas change `income_source`; students 20-29 draw General Allowances 59 %. |

**Things the pipeline step must know.**

1. **Synthetic income tokens are not moved yet.** Only `values`, `real` and (uncommitted, see 3)
   `priority` were edited. Before the re-run the Phase 2 income config must move CSN / studielån /
   studiebidrag / studiemedel / barnbidrag / child support to General Allowances and bostadsbidrag /
   bostadstillägg / housing allowance to Housing Allowance (Pension `none_of`
   `bostadstillägg för pension`), else the real side has 8 categories and the synthetic side
   still files those rows under Insurance.
2. **Global tier not mirrored.** `config/mapping/scb/income_source.json` has neither new value
   (Open question 18); Sweden's axis files map through `scb_native`, so nothing breaks today.
3. **`priority` hunk left uncommitted.** The working tree's `scb_native/income_source.json`
   `priority` list (the Phase 1 engine work, not yet committed) already includes the two new
   values at the end; the committed file has only `values` + `real`.
4. **New raise paths.** TabVX13 has no cell for students aged 65+ or unemployed aged 80+. The
   register gives P(Student | 65-85) ≈ 0.1 %, so a run at another seed or n can raise. Seed 42,
   n 10,000 draws none. Open question 22 (new): accept the raise, or declare proxies (e.g. students
   65+ → students 50-64).
5. **Cache TTL.** Half the SCB cache files date from 2026-05-15 (> 90 days), so a default run
   would re-fetch them live. `generate_scb_population.py --cache-ttl-days` (new) overrides it.

**Re-sampling command** (writes a new file; never overwrite the published one):

```bash
PYTHONHASHSEED=0 python scripts/generate/generate_scb_population.py --n 10000 --seed 42 \
  --cache-ttl-days 100000 \
  --output data/scb_api/scb_population_n10000_seed42_mapping-fixes_<date>.json
# PowerShell: $env:PYTHONHASHSEED='0'; python scripts/generate/generate_scb_population.py ...
```

Expect exactly two live fetches (two new `data_*` files with today's mtime in
`config/database/caches/scb/`): `HushallT03` (BE0101DK) and `TabVX13InkStruktN` (8 components).

**Expected-diff check** (against `data/scb_api/scb_population_n10000_seed42_merge-status-edu_2026-07-16.json`):

```python
import json, collections
from population_synthetic.generators.real.helpers import age_to_group
old = json.load(open("data/scb_api/scb_population_n10000_seed42_merge-status-edu_2026-07-16.json", encoding="utf-8"))["individuals"]
new = json.load(open("data/scb_api/scb_population_n10000_seed42_mapping-fixes_<date>.json", encoding="utf-8"))["individuals"]
diff, ages = collections.Counter(), collections.Counter()
for a, b in zip(old, new, strict=True):
    for k in a.keys() | b.keys():
        if json.dumps(a.get(k), sort_keys=True) != json.dumps(b.get(k), sort_keys=True):
            diff[k] += 1
            ages[(k, age_to_group(a["age"]))] += 1
print(diff)
assert set(diff) <= {"household_size", "employment_type", "socioeconomic_class", "income_source"}, diff
assert {g for (k, g) in ages if k == "employment_type"} == {"18-24"}, ages
```

Expected counts on the 2026-10-04 SCB data: `household_size` 7,141, `income_source` 1,082,
`socioeconomic_class` 544, `employment_type` 530 (all 18-24); every other attribute 0. Measured
stepwise on the scratch cache, one commit at a time — each step changed only its own attribute:
household switch (`98e10a5`) 7,141; determinism + AKU map (`3b0dfa3`) 530; median (`74b135e`) 544;
325/330 (`80d827b`) 1,082. A different count in `household_size` or `income_source` alone means
SCB revised one of the two live-fetched tables; any change in another attribute stops the run.
Then point `swedish.yaml:5` and `swedish_02.yaml:5` at the new file.

### Phase 4 — Socioeconomic occupation proxy (decision point, not committed work)

The `socio_occupation = proxy` decision assumed a sourced SCB income-by-occupation table would
place occupation and status words in a class. The assessment does not support it:

- Best table: `AM/AM0110/AM0110A/LoneSpridSektYrk4AN` (monthly salary P10–P90 by SSYK-4 × sex,
  2023–2025). No age dimension; employees 18–68 only; self-employed excluded. SCB publishes no
  current taxable-income table by occupation, SEI or ESeG.
- Method: occupation median ÷ all-occupation median of the same sex, cut at 0.6 / 1 / 2.
- Rescue: about **60–100 of 459** undeterminable rows (13–22 %); 50–70 using fully current
  figures only. Not rescuable: ~69 "kunskapsarbetare/knowledge worker" (no SCB definition),
  25 non-employed, ~97 others.
- **No occupation reaches Poverty** (all-occupation P10 = 0.72 × median), while the real
  reference has 17–23 % Poverty at 40–44; Wealthy holds only specialist physicians and female
  CEOs. Rescued rows would inflate Working and Middle — a distortion the proxy itself creates.
- SEI (occupation title → socioeconomic group) is discontinued from 2026; its only income table
  ends 2013.

Options (Open question 20):

| Option | Effect | Trade-off |
|---|---|---|
| A. Adopt a limited proxy | generate an SSYK-4 → band table from the fetched SCB table; replace every unsourced occupational token (`arbetar`, `tjänsteman`, `akademi`, `it-`, `konsult`, `företagare`, …) | ~60–100 rows rescued; built-in bias toward Working/Middle; new fetch + generator code |
| B. Strict unmapped | remove the unsourced occupational and status tokens; class only from explicit income/class wording | definition-consistent; more personas `__UNMAPPED__` (S3 alone: 159 unflagged rows, 42 capped) |

Either option removes the status-only tokens (S3) here, not in Phase 2.

### Phase 5 — Birth-region label rename

FolkmFodlandHVD returns `FSV`/`FEU`/`FUEU`, i.e. Sweden / other EU / outside EU; the current
labels ("Europe (Other)", "Outside Europe") misdescribe them.

| Change | Where |
|---|---|
| Rename the two values (Open question 19) | `config/mapping/scb_native/birth_location.json` `values` (l.3–6) and `real` block |
| Move non-EU European countries (Norway, Iceland, UK, Switzerland, Serbia, Bosnia, Ukraine, …) to the outside-EU list | same file, `synthetic` block |
| Delete tokens that fit neither side (`nordic`, `scandinav`, `europe`, `european`, `immigrant`) and the dead legacy real labels | same file |
| Update quoted labels | `config/mapping/scb_native/README.md`; `docs/architecture/sweden-generation-explorer/js/data.js:101`; `docs/scb_population_and_comparison.md:178` (still lists "Nordic Country") |

No analysed result changes: `birth_location` is deprecated for Sweden and excluded from the
realism prompt. Tests use inline fixtures. Not fixed here: `refine_from` re-walks only the
resolved sibling (183 rows, no persona rescued) and the independent sampling of
birth_location and birth_country_detail (open investigation). Italy's "Europe (Other)" is the
same mislabel, out of scope.

## Impact summary

| Attribute | Real errors | Fixed | Coverage |
|---|---|---|---|
| civil_status | 2,797 | 2,785 | 99.6 % |
| education_level | 1,811 | 1,633 | 90.2 % |
| housing_tenure | 1,418 | 1,380 | 97.3 % |
| employment_type | 837 | 208 + ≈197 (hours facet) | ≈48 % |
| income_source | 699 | 581 (incl. 55 via 325/330) | 83.1 % |
| industry_sector | 639 | 520 | 81.4 % |
| parental_structure | 486 | 382 | 78.6 % |
| employment_status | 408 | 354 | 86.8 % |
| socioeconomic_class | 190 | 166 | 87.4 % |
| birth_location | 186 | 3 | 1.6 % (183 are the `refine_from` mechanism) |
| small (sex, region, birth country, household) | 34 | 29 | 85 % |
| **Total** | **9,505** | **≈8,240** | **≈87 %** |

Config counts were simulated per section on today's engine; the hours-facet count was measured
separately. The two overlap little (the facet fixes the rows config cannot), but the combined
figure is unmeasured until the harness re-runs after Phase 2.

**First-pass false alarms preserved:** 1,640 of 1,643. Lost: "Hyresrätt – lägenhet i villa"
(Owner → Rental) and two "Aktivitetsstöd kompletterat med bostadsbidrag" (Insurance → Housing
Allowance; kept only under Open question 8's first-listed rule).

**Intended side-effect changes on unflagged rows:**

| Change | Rows |
|---|---|
| education 3C → 3A (upper secondary, length unstated) | 753 |
| socio "Lägre medelklass" Middle → Working | 115 |
| income → new 325 / 330 categories | 109 |
| parental joint custody NP → unmapped (gated) | 103 |
| socio student/pensionär → unmapped (Phase 4) | 159 |
| parental unmapped → NP ("Samboförhållande", cohabiting couple) | 36 |
| income parental/family support → unmapped | 34 |
| parental adoptive parents Other → NP | 30 |
| housing "Eget hus eller lägenhet" Owner → Tenant-owned (Open question 9) | ≈30 |
| education folkhögskola → unmapped | 16 |
| other definition-consistent moves (civil, education, employment, housing, income, industry) | ≈260 |

**Full-N risk.** `population_cap` withdraws any combination left with fewer than `--n` clean
personas. Measured newly-unmapped counts in today's capped set (5,800 personas):

| Source | Capped personas / rows newly `__UNMAPPED__` |
|---|---|
| Engine, prefix mode alone | 289 personas (up to 61 in one gpt56_sol combo); mostly "Eftergymnasial … 3 år eller längre", which the Phase 1c education routing resolves |
| Engine, all four fixes | 329 personas; none cleared |
| industry_sector | 6 rows |
| parental joint custody (gated) | 58 rows |
| socio status words (Phase 4) | 42 rows |
| Phase 2A config | not measured — measure in the Phase 2 exit check |

A combination survives only if its pool beyond `--n` absorbs the loss; combos already near the
threshold are the risk. Before the re-run, re-map the full `01_Raw` pool, run `validate_mapped`
and `population_cap` in a scratch output base, and list every combination that would be
withdrawn. Any new withdrawal is a sign-off item, not an automatic outcome.

## Open questions needing sign-off

Each item: proposed default, rows affected.

1. **employment_type, attachment unstated** ("part-time job (< 20 h)", "student job",
   "pensionär med deltidsarbete") — Permanent (modal AKU attachment); student jobs → Temporary.
   193 partial + 145 no-target rows.
2. **employment_type, temporary with hours unstated** ("tidsbaserad anställning") — keyword band
   (Full-time when no part-time word); alternative: a "Temporary (hours unstated)" category.
   ≈60 rows.
3. **Former contracts** ("former permanent full-time", "tidigare …") — Not Applicable. 30 rows.
4. **Previously married, current status unstated** — Divorced; alternative unmapped. ≈8 rows.
5. **Incomplete or ongoing higher education, no credits** — Upper Secondary 3A (highest
   completed); alternative unmapped. 37 rows.
6. **Bare "eftergymnasial" / post-secondary with no length** — unmapped; alternative 5A.
   ≈45 rows.
7. **Not employed / NEET without AF registration**; "hemma med barn" with no job — Other.
   9 + ≈8 rows.
8. **Multiple non-wage income sources** — first-listed; alternative unmapped. 2 false alarms plus
   a handful; grants → unmapped, sjukpension by payer or unmapped (≈22).
9. **"Eget hus eller lägenhet"** (disjunctive tenure) — unmapped; alternatives Tenant-owned or
   first-named. ≈30 rows.
10. **325 / 330 category names and studielån** — "General Allowances" / "Housing Allowance";
    studielån in 325 after checking TAB1388 metadata. 55 errors + 109 unflagged.
    *Implemented with the defaults (Phase 3); the TAB1388 table note lists studielån under 325.*
11. **Kunskapsarbetare** — the user chose Working Class; Middle is the more plausible lenient
    reading; the proxy cannot place it. Default: follow Phase 4 (unmapped under option B,
    otherwise the user's Working). 35 exact, ~69 with variants.
12. **"Lägre socioekonomisk grupp", "låg socioekonomisk status", "low SES", "Lågklass"** →
    Working (read as "lower class"). Confirm; Lågklass is the plan's extension. ≥ 4 rows.
13. **Generic economy wording** — "begränsad/pressad/blygsam" → Working; "låg pension",
    "låglön" → Poverty; "trygg/stabil" → unmapped. ≈30 design rows.
14. **Joint custody and status-only socio words** — joint custody → unmapped (SCB: undeterminable
    without the registered parent); student/pensionär removal in Phase 4. Together 100 capped
    rows (58 + 42).
15. **Same-sex couple / "two dads"** with parenthood unstated — keep Natural Parents (README
    default); alternative unmapped. 45 rows.
16. **Industry undeterminables** — bare "Engineering" unmapped (alternative SNI M71 → F&B);
    Administration, charity/aid, teknisk service, media + kultur unmapped; Kundtjänst stays F&B.
    25 + ≈23 rows.
17. **employment_type for ages 75–85** (no AKU source) — config-declared 65–74 proxy recorded in
    provenance; alternative raise (drops the attribute for those personas). Part of the 1,140
    employed 18–24 and 75–85 personas in the real reference. *Implemented with the default
    (`constants.EMPLOYMENT_TYPE_AGE_PROXIES`); recorded in the output's `tables_used` note.*
18. **Mirror to the global tier** `config/mapping/scb/` — mirror attribute files identical today;
    skip industry and parental (they differ by design).
19. **Label wording** — birth region: "Born in another EU country" / "Born outside the EU"
    (alternative "EU (excl. Sweden)" / "Outside EU"). Also consider relabelling "Sickness /
    Activity Compensation", which the spot check showed is read as covering sjukpenning (13 rows).
20. **Occupation proxy** — Phase 4 option A or B. Default B (strict unmapped), given no
    Poverty reachability and the self-made bias. Also decides whether employment_status (≈40)
    and income_source (≈50) occupation tails keep growing as token lists.
21. **Minor unmapped defaults** — "Trans man", "Uppland", "Region Väst", "Serbia", "rötter
    från", "Ensamstående kvinna", bare "Borgerlig familj", "Bifamilj", living with parents
    (housing, 55), garbled values → unmapped; rented house → Rental (41). ≈150 rows.

22. **income_source cells with no SCB value** (students 65+, unemployed 80+) — now raise if drawn
    (Phase 3 fail-fast; ≈ 0.1 % of 65+ register persons are students; none at seed 42, n 10,000).
    Default: keep the raise; alternative: declared proxies (students 65+ → students 50-64).

## Combined re-run protocol

One run after all of: household-size switch, Phases 1–3 and 5 (Phase 4 as decided), and the judge
context-leak fix (`docs/development/plans/pending/fix-claude-cli-conversation-leak.md`). No LLM
persona generation. Every step needs `--force` because each skips existing outputs.

1. **Re-sample the real population** (`scripts/generate/generate_scb_population.py`, seed 42,
   n 10,000, `PYTHONHASHSEED=0` pinned even after the fix, cache TTL extended). Run the stepwise
   expected-diff check (Phase 3). Point `config/synthetic/axes/countries/swedish.yaml:5` and
   `swedish_02.yaml:5` at the new file.
2. **`mapping --force`** over the full `01_Raw` pool and the new real file.
3. **`validate_mapped --force`** (raw outputs are unchanged, so `validate_raw` is not re-run).
4. **`population_cap --force`**; compare `population_cap/_index.json` with the pre-run list of
   withdrawals; run `validation_attrition`.
5. **Compute analyses**, each `--force`: `fidelity`, `real_population_stats`, `model_ranking`,
   `method_significance`, `generation_metadata` (only if the capped selection changed),
   `cost_efficiency`.
6. **`persona_realism --force`, full run**: every combination plus the real competitor
   `real_sweden`. The leak fix invalidates every cached verdict and the mapped values changed;
   `--rewrite-artifacts` replays old values and is not a substitute. This is the only LLM step.
7. **`realism_ranking --force`** (manuscript basis `--rounds 1`), then **`figure_selection
   --force`**.

## Verification

- `ruff check src/` and `pytest` pass; the golden test shows `scb`, `istat`, `ssb` unchanged.
- Both simulation harnesses, re-run on the final config and engine, reproduce the fixed counts
  per attribute with zero broken rows and only the three named false-alarm losses.
- `{slug}.ties.csv` and `facet_ambiguous` counts are reviewed for one combo of each model family.
- The stepwise real-population diff changes only the allowed attribute at each step.
- Real `household_size` matches the `BE0101DK` shares; real income_source has 8 categories; the
  socio reference cells match the interpolated-median table within sampling error.
- No combination is withdrawn that was not on the signed-off pre-run list.

## Manuscript follow-up

- Methods: the mapping engine's boundary, negation, hours and priority rules; the persons unit for
  household size; the interpolated median; 325/330 in income_source; the AKU 15–24 and 75–85
  proxies; the occupation-proxy decision and why.
- Results: every fidelity, ranking, realism and cost number and figure after the re-run;
  civil_status and education shifts are large (≈2,800 and ≈2,400 rows moved).
- Limitations: residual child bias in household size; proxy bias or unmapped share in
  socioeconomic class; birth-location independence (still open).

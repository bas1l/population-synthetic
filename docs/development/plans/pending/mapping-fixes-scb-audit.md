# Plan: Fix the Swedish Mapping Rules and Real-Reference Defects Found by the SCB-Checked Audit

**Date:** 2026-10-04
**Author:** Basil
**Status:** In progress — Phase 1 done 2026-10-04; Phase 2A done 2026-10-04; Phase 2B, Phase 4 (option B, sign-off pending) and Phase 5 done 2026-10-04; Phase 3 done 2026-10-04 (re-sampled); combined re-run steps 1–4 (mapping gate) done 2026-10-04, see "Pipeline run 2026-10-04 — mapping gate"
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

**Status: done 2026-10-04** (commits `0977715` 1a, `dc1209b` 1b, `5877c43` 1c, `0803721` 1d,
`201fa4f` 1e, plus the docs/plan commit).

**Implementation notes (Phase 1).**

- *Reproduction.* After 1a the old engine (HEAD) and the new one map the full `01_Raw` pool
  (21,931 Swedish personas through `scb` and `scb_native`, 1,316 Italian through `istat`) and the
  real SCB reference with **0** differing cells; the real-engine harness reproduces 12,552 / 12,552
  curated rows. The Italian real reference (`data/istat_api/istat_population.json`) is not on disk,
  so the Italian real side was checked only through the config contract test.
- *`ssb` not touched.* `config/mapping/ssb/` has no `_index.json` and is not read by the engine (legacy
  Norway label maps); the `matching` block lives in `scb_native`, `scb`, `istat` only.
- *`priority` is per attribute file*, shared by both sides (as planned); every file starts with
  `priority == values` (today's order already is BAS for employment and wage-first for income).
  `tie_break` must end with `priority` (validator), so every tie resolves. Per-attribute overrides
  are block directives: `tie_break` (employment_status, income_source → `["priority"]`) and
  `negation: null` (biological_sex, birth_location).
- *Composite sub-fields* are declared in a new `subfields` directive (real `employment_type`, all
  three dirs); any other non-matcher key raises. Empty tokens raise; `equals` accepts strings only.
- *Ties sidecar* `{slug}.ties.csv` (`persona_id, attribute, raw_value, tier, candidates, winner,
  criterion`); ambiguous facet reads go to the **same** sidecar with `tier=numeric_facet`,
  `criterion=facet_ambiguous` (no separate file).
- *API change.* `mapping_engine.resolve` / `resolve_detailed` now require `matching=` and
  `priority=`; `flatten_raw_population` / `flatten_individual` take `matching=` (the directory's
  `matching.real`), wired in `scripts/analyze/compare_real_countries.py`.
- *Substring overrides (1c).* Worklist generated over the full `01_Raw` Swedish pool with a stricter
  criterion than the prototype: a token is listed only when the value's hit would be lost under
  `prefix` (not merely when the first-listed token was mid-word), and `none_of` vetoes that fire only
  mid-word are listed too (else e.g. `job` would stop vetoing "studentjobb" → Not Applicable, 211
  cells). Overrides are applied per (attribute, token) to every occurrence in that attribute's
  synthetic block. Kept `prefix` (the defect itself): the prototype's bug list plus `male`
  (Female→Male), `sysselsatt` (Osysselsatt), `höginkomst`, `urban` (Suburban), `gotland`
  (Ostergotland), `married parents`, `father only`, `secondary education` (Postsecondary),
  `hotel`/`hotell` (webbhotell), `n/a`, `äktenskap`, `relation`, `retired`/`retire` (semiRetired),
  `farfar`. Result: 127 (attribute, token) overrides / 168 occurrences in 10 attributes.
- *Education routing (1c)* is section_config_A row 2 verbatim, **plus** a 4+5B `none_of`
  [`master`, `magister`, `kandidat`, `bachelor`] (from row 3): without it 4 first-pass false alarms
  ("Masterexamen (2-årig …)", "120 hp") regress 5A → 4+5B. The other row-3 vetoes and rows 1, 4–12
  are left to Phase 2.
- *Hour tokens (1e)* removed from the attachment `all_of` groups and the PFT veto (17 tokens):
  measured zero effect on curated rows and capped cells beyond the facet alone.

**Measured impact (real engine; curated rows excl. age_group/birth_location; each fix alone on the
config committed with it).**

| Fix | Rows changed | → correct | wrong → `__UNMAPPED__` | FA regressions | Capped cells | Expected (section) |
|---|---|---|---|---|---|---|
| tie-break (1b, with `it-konsult`) | 1,740 | 1,384 | 0 | 2 | 1,648 | 1,763 / 1,384 / 0 / 25 (23 fixed by it-konsult) |
| prefix + overrides, no edu routing | 1,022 | 558 | 382 | 0 | 700 | 1,030 / 559 / 385 / 3; 700 |
| prefix + overrides + edu routing (1c) | 1,234 | 1,102 | 46 | 0 | 851 | — |
| negation (1d) | 140 | 28 | 107 | 0 | — | 140 / 28 / 107 / 0 |
| hours facet (1e) | 264 | 197 | 0 | 0 | — | 264 / 197 / 0 / 0 |
| all combined (final config) | 3,209 | 2,580 | 155 | 2 | 2,509 (3.33 %) | 3,136 / 2,087 / 493 / 47; 2,509 |

The two remaining false-alarm losses: "Hyresrätt – lägenhet i villa" (the plan's named loss) and
"Postgraduate diploma (Magisterexamen)" 5A → ISCED 6 (`longest`). Capped personas newly
`__UNMAPPED__`: 289 → **55** after the edu routing (prefix alone) and **95** with all four fixes
(expected 329), at most 13 in one combo (`…generate_pick_v2_ollama_mistral_nemo_12b`); none cleared.
Deviations from the section are explained by the edu routing (+~520 correct, −~340 wrong→unmapped),
`it-konsult` (−23 regressions) and the full-pool override list (−3 regressions).

**For Phase 2.** (1) Express the C\* stop-gaps natively: drop `none_of` vetoes that only stood in
for boundaries (`eftergymnasial`, `folkhögskol`, `enskild`, `penthouse`/`house`) or negation (civil
`ej gift` etc. now resolve to `__UNMAPPED__` and need positive Single tokens). (2) "post-secondary
education" without a length still hits 3A via `secondary education` (the hyphen is a word boundary):
needs the row-1 3A/3C vetoes. (3) Zero-hour text ("0 timmar/vecka") still walks to an attachment value
(the facet never overrides with 0); the planned Not Applicable rule is config. (4) The ties sidecar
lists every `longest`/`priority` decision for review. (5) `tests/test_mapping_config_no_on_miss.py::
test_every_declared_value_is_reachable[scb_native/income_source]` fails since Phase 3's `80d827b`
(General Allowances / Housing Allowance have no synthetic tokens yet) — Phase 2/3 token work.

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

#### Phase 2A implementation notes (done 2026-10-04)

Commits: `434d392` civil_status, `df26fde` education_level, `7dfa46a` employment_status,
`f1795b9` employment_type, `74fad2e` housing_tenure, `8dd7782` + `26a1e75` income_source,
`d02ebd0` regression tests (`tests/test_scb_native_audit_rules_core.py`), `bce4c5a` README.
The section-A token lists were ported onto the Phase 1 engine, not copied: the patch script that
applies them to the pre-2A config lives with the measurement harness in the session scratch area
(`p2a/apply_p2a.py`, `p2a/measure.py`).

*Native, not stop-gap.* Dropped the vetoes that only stood in for boundaries or negation:
civil `ogift`/`skild,`/`skild `/registered-partnership Single vetoes and Married
`utan giftermål`/`äktenskapsskillnad`/`skilsmäss` vetoes (longest or negation now decides);
education `eftergymnasial`/`förgymnasial`/`postgymnasial`/`folkhögskol` vetoes (prefix) and the
5A `doctoral`/`phd`/`doktors` vetoes (ISCED 6 wins on length); employment_status `unemploy`,
`not employed`, `ej/icke anställd`, `ingen anställning`, `utan arbete`, `osysselsatt`;
employment_type the negated-employment vetoes (the zero-hour vetoes stay, unparenthesised — prefix
keeps `0 timmar` off "40 timmar"); housing `penthouse` (now an apartment word of the Tenant-owned
`all_of`). Kept as definitional vetoes: civil Single vetoes on a stated prior status (a longer
Single token such as `ensamstående` would otherwise win on length), housing Owner vetoes on
apartment / BRF / rental words, income Insurance vetoes on the specific transfers.
Negated forms carry positive tokens: civil `ej gift`, `icke gift`, `utan sambo`, `ingen relation`,
`ej registrerad`; education `ingen avslutad grundskol`, `ej fullgjord grundskol` (the engine
negates `grundskol` after them); employment_type `ingen aktuell anställning`. Compound heads
added as `substring` tokens: employment_status `lärare`, `läkare`, `ingenjör`, `utvecklare`,
`specialist`, `konsult`, `anställning`, `direktör`, `arbeiter`, …; income `lärare`, `lärar`,
`utvecklare`, `ingenjör`, `sjuksköterska`, `säljare`, `analyst`, `entrepren`, `salar`,
`medarbetare`, Capital `utdelning`; education `förberedande`, `grundskol`; employment_status
Student `stud` (all_of) and veto `jobb`.

*Deviations from section A (and why).*
- `income_source` `priority` stays the `values` order: `priority` is shared with the real side,
  whose preserved-matching test requires `priority == values`. Ordering the generic Insurance /
  Allowance last was tried and rejected for that reason; Insurance instead vetoes every 325 / 330
  token. Wage vetoes `utdelning från` (own-company dividends) rather than every `utdelning`, so
  "Lön … samt kapitalinkomster (ränta/utdelning)" stays Wage (wage first). `studiestart` is not a
  General Allowances token: it would move the false alarm "Studiestartsstöd" (unmapped); "…från
  CSN" still reaches 325 through `csn`. `sickness benefit` / `sjukpenning` veto Sickness / Activity
  Compensation.
- Open-question defaults applied: 4 (previously married → Divorced, unless widowhood is named),
  6 (post-secondary with no length → unmapped), 9 (house-or-flat disjunctions → unmapped; listed
  phrase tokens, so BRF-named disjunctions such as "Villa or Bostadsrätt" stay Tenant-owned as
  before), 10 (studielån → General Allowances).
- Extra fixes beyond the section (all single rows): education `magisterexamen` (5A) restores the
  Phase 1 loss "Postgraduate diploma (Magisterexamen)"; "lower secondary education", "(9 years)",
  "less than 2 years", `post-upper secondary`; housing `cooperative ownership/housing` (else
  `bostadsbolag` wins on length), `hyrd`, `hyr `, `fastighetsägd`; Tenant-owned no longer vetoes
  bare `ägarlägenhet` or `municipal` (they broke "Bostadsrätt (ägarlägenhet)" and "… municipality").
- Not fixed (same as the section): "Tidigare pensionär men arbetar fortfarande" / "… med
  deltidsarbete" (employment_status → unmapped: the Employed `tidigare` veto and the Retired
  current-work veto both fire).

**Measured (real engine; curated rows; "fixed" = resolved value equals the verdict's category,
targets restricted to real values or `__UNMAPPED__`).**

| Attribute | Targeted | Fixed before 2A (Phase 1) | Fixed now | Section expected | FA kept | Unflagged capped cells changed | 01_Raw newly `__UNMAPPED__` / cleared |
|---|---|---|---|---|---|---|---|
| civil_status | 2,792 | 13 | **2,791** | 2,785 | 16/16 | 28 / 4,553 | 1 / 169 |
| education_level | 1,679 | 1,121 | **1,638** | 1,633 | 1,203/1,203 | 84 / 3,970 | 34 / 99 |
| employment_status | 363 | 40 | **355** | 354 | 15/15 | 10 / 5,746 | 10 / 300 |
| employment_type | 499 | 226 | **402** | 405 (208 + ≈197 facet) | 29/29 | 1 / 5,536 | 0 / 233 |
| housing_tenure | 1,393 | 1,077 | **1,381** | 1,380 | 15/16 | 15 / 4,832 | 508 / 133 |
| income_source | 690 | 1 | **525 + 59** reassigned to 325/330 | 526 + 55 | 105/107 | 88 / 5,693 | 262 / 760 |

No targeted row that was right before 2A is wrong after it. False alarms lost: exactly the two
named ("Hyresrätt – lägenhet i villa", "Aktivitetsstöd kompletterat med bostadsbidrag").
Unflagged changes are the intended moves (sambo / separated, upper secondary 3C → 3A,
folkhögskola, högskoleexamen, wage first, 325 / 330, parental support, förtidspension → Sick
Leave). The capped-mirror counts are far below the section's 753 / 214 because Phase 1's
longest tie-break had already moved most "upper secondary school (gymnasium)" rows to 3A.

*Full-N risk.* Full `01_Raw` Swedish pool (21,931 personas): **603 personas** gain a
`__UNMAPPED__` on one of the six attributes. Drivers: `Ägarlägenhet` 388 (decision: OB not
fetched), house-or-flat disjunctions ≈ 55 (Open question 9), `äganderätt (lägenhet)` 16, parental
/ family support 240 (decision), folkhögskola 25, `spouse's employment` 12. Per combination,
against today's `population_cap/_index.json` (65 `swedish_02` v2 combinations): 357
currently-clean personas lose cleanliness across the pool. **Sign-off item:
`swedish_02_all_pick_dag_v2_ollama_gemma4_e4b` would be withdrawn** — 116 clean today, 19 lost
(16 "Ägarlägenhet", 6 house-or-flat disjunctions; some personas carry both) → 97 < `--n` 100.
Every other included combination keeps a margin ≥ 8 (the 7 combinations already excluded stay
excluded). Larger losses sit in v1 pools the index does not hold
(`swedish_all_pick_dag_ollama_gemma4_e4b` 108, `swedish_all_generate_pick_ollama_mistral_nemo_12b`
39). Approximation: mapped validity over every attribute except `age_group` and the deprecated
`birth_location`, raw validity unchanged, Phase 2B changes not included; the exit check is still
the re-run's `population_cap`. Keeping that combination would need the Ägarlägenhet decision (OB
not fetched → unmapped) or Open question 9 reversed for it; neither was changed here.

*Global tier.* `config/mapping/scb/income_source.json` still declares six values and no 325 / 330
tokens. No country axis selects `scb` (both Swedish axes map through `scb_native`) and no test
requires it, so nothing was added; Open question 18 stays open. Note for that decision: `scb`
keeps the historic `substring` / `["priority"]` matching, so copying the `scb_native` files
(prefix-mode tokens, substring overrides, longest tie-break) would not be behaviour-equivalent.

#### Phase 2B implementation notes (done 2026-10-04)

Commits: `c5790c1` industry_sector, `e0cac42` parental_structure, `fc660e5` socioeconomic_class
(boundary rules + status words), `fe29df9` socioeconomic_class (Phase 4 option B, see Phase 4),
`eaa8202` small attributes, `5503dc5` README. Regression cases:
`tests/test_scb_native_audit_rules_social.py` (fixed rows, first-pass false alarms and every
decision / open-question default named below). The section-B simulators were ported onto the
Phase 1 engine; the port scripts and the real-engine harness live in the session scratch area
(`p2b/apply_*.py`, `p2b/ev.py`, `p2b/survive.py`).

*Native, not stop-gap.* Industry and parental: the section's priority `all_of` steps became plain
`contains` tokens (the longer phrase wins under `longest`), and every `none_of` veto that measured
**dead** on the full pool and the curated rows was not carried (industry 26, e.g. `webbhotell`,
`law`, `sjukhus`, `skönhetsvård`; parental: the father-led-stepfamily, grandfather and
`intact single-parent` stand-ins). The word-boundary stand-ins `non-profit` (industry), `female`
(biological_sex) and `ikt-` (now plain `ikt`) are not needed under `prefix`. Socio keeps its
explicit cues as a single-group `all_of`: under `longest`, "professional" (12 characters) would
beat "high-income" (11), so the "High-income / Affluent professional" rows need tier priority, not
length. Live semantic vetoes stay (parental divorce / death / custody, industry `bioteknik`,
`pensionär` on Healthcare). Dropped because they were wrong under the native engine: industry
`friskvård` / `personalvård` vetoes (they kept "Friskvård och rehabilitering" out of Healthcare).

*Decisions and open-question defaults applied.* Warehouse → Transport; labour-market services →
SNI 78; two-phase parental text → earlier phase (`mother remarried` dropped; the `single-parent`
Natural Parents veto dropped, it only fired on an "until … then single-parent" text); joint
custody → unmapped (OQ 14); bare same-sex couple → Natural Parents (OQ 15: the section's
`same-sex partner` veto was narrowed to parent-plus-partner wording, else 7 bare "two same-sex
partners" texts fell to unmapped); industry undeterminables (OQ 16: bare Engineering,
Administration, "Rådgivning (allmän)" and media + kultur → unmapped — the section's bare
`rådgivning` / `management` tokens were narrowed to business-advice phrases; Kundtjänst stays
F&B); socio OQ 12 (lägre / låg socioekonomisk, low SES, Lågklass → Working) and OQ 13 (begränsad /
pressad / blygsam → Working; låg pension / låglön → Poverty; trygg / stabil unmapped); OQ 21
(Trans man, Uppland, Region Väst, Serbia, rötter från, Ensamstående kvinna, bare Borgerlig
familj, Bifamilj stay unmapped; text naming both sexes → unmapped). Extra single-row fixes:
`waste management` (Manufacturing, not F&B via `management`), `agriculture and food production`
/ `jordbruk och livsmedel` stay Agriculture, `trafiken` as a substring head (Hallandstrafiken),
`uplandia` → Sweden, adoptive family → Natural Parents.

**Measured (real engine; base = Phase 1 HEAD `b9b0a4f`; curated rows; "fixed" = resolved value
equals the verdict's category; pool = full `01_Raw` Swedish, 21,931 personas).**

| Attribute | Errors with a category | Correct at Phase 1 | Correct now | Section expected | Broke | FA kept | Pool newly `__UNMAPPED__` (in capped set) | Pool cleared |
|---|---|---|---|---|---|---|---|---|
| industry_sector | 537 | 76 | **518** | 520 | 0 | 83/83 | 78 (7) | 409 |
| parental_structure | 407 | 4 | **383** | 382 | 0 | 82/82 | 147 (58) | 548 |
| socioeconomic_class, boundary rules + status words | 176 | 15 | **164** | 166 | 0 | 28/28 | 406 (38) | 195 |
| socioeconomic_class, + option B | 176 | 15 | 164 | — | 0 | 28/28 | **2,794 (887)** | 195 |
| biological_sex | 11 | 7 | 10 | 10 | 0 | — | 1 (0) | 12 |
| region | 11 | 0 | 11 | 11 | 0 | — | 0 | 49 |
| birth_country_detail | 6 | 0 | 6 | 6 | 0 | — | 4 (0) | 2 |
| household_size | 3 | 0 | 2 | 2 | 0 | 10/10 | 0 | 1 |

Open rows match the section's list (garbled text, mixed cues such as "Lower-income middle class",
"Moderately affluent", the negation rows "ej detaljhandel"). Undeterminable rows moved: industry 3
(media + kultur → unmapped), parental 6 (non-biological / step wording → unmapped; "Both parents
deceased by adulthood" → Other Than Parents), socio 5 (status words). **Deviation:** five
two-phase parental texts in the pool whose *later* phase carries a divorce / custody veto word
("…, then shared custody", "later separated", "until parents divorced") resolve to `__UNMAPPED__`
instead of the earlier phase: a `none_of` vetoes its value in every tier, so honouring the earlier
phase there needs clause splitting in the engine (not done). The curated design row ("…, then
mother-headed single-parent household") keeps Natural Parents.

*Full-N risk* (same approximation as 2A: mapped validity over every analysed attribute except
`age_group`, against today's `population_cap/_index.json` `clean_available`, n = 100). 2B without
option B: 105 currently-clean personas lose cleanliness; **no** combination falls below n. 2A + 2B
without option B: 582 personas; only the 2A withdrawal (`swedish_02_all_pick_dag_v2_ollama_gemma4_e4b`,
97). **2A + 2B with option B: 1,960 personas, 20 combinations below n** (see Phase 4 notes).

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

1. **Synthetic income tokens.** Committed in Phase 2A (`8dd7782`, `26a1e75`): CSN / studielån /
   studiebidrag / studiemedel / barnbidrag / child support → General Allowances, bostadsbidrag /
   bostadstillägg / housing allowance → Housing Allowance, each value keeping the `equals` on its own
   canonical name from `b1924b5`.
2. **Global tier not mirrored.** `config/mapping/scb/income_source.json` has neither new value
   (Open question 18); Sweden's axis files map through `scb_native`, so nothing breaks today.
3. **`priority`.** The engine commits' `priority` list for `scb_native/income_source.json`
   already ends with General Allowances, Housing Allowance.
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

#### Phase 4 implementation notes (option B applied 2026-10-04 as the default; sign-off pending)

Open question 20 was applied with its proposed default, **B (strict unmapped)**, in its own commit
(`fe29df9`) on top of the boundary rules (`fc660e5`), so it can be reverted alone. Removed from the
`scb_native` synthetic block: Working `arbetar` (substring head; `arbetarklass` kept),
`blue(-)collar`, `skilled / service / semi-skilled worker`, `Arbetare`, `Arbetsinkomst`, `Skilled
manual worker (class)`; Middle `tjänsteman` / `tjänstemän` and every tjänstemanna- equals,
`akademi(ker)`, `professional`, `professionell`, `white(-)collar`, `managerial`, `administrative`,
`högskoleutbildad`, `it-`, `konsult`, `(egen)företagare`, `urban`, `intellektuell`, `Specialist`,
`Mellanledande`, `B-skatt`, the small-business / entrepreneurial / technical-specialist equals;
Wealthy `högre tjänstemän`. Class words stay (arbetarklass, medelklass, överklass, kapitalist,
elite). **Open question 11 follows Phase 4: "Kunskapsarbetare" now resolves to `__UNMAPPED__`.
This reverses the user's spot-check answer (Working Class); the plan default was applied, not the
spot-check answer.**

**Measured deviation from the option table (sign-off item).** The table's "S3 alone: 42 capped"
undercounts option B by an order of magnitude. On the full `01_Raw` pool option B makes **2,794**
personas newly `__UNMAPPED__` on socioeconomic_class (status words alone: 406), **887** of them in
today's capped set (status words alone: 38); 1,541 currently-clean personas lose cleanliness, and
**18 combinations** fall below n = 100 on socio alone (20 with 2A + 2B), all `swedish_02` v2 arms
(gemma4_e4b, deepseek_r1_14b and the openrouter models; worst
`swedish_02_all_generate_pick_v2_ollama_gemma4_e4b`, 227 clean → 65). Largest strings lost
(case variants summed): "Professional class" 202, "IT-specialistklass" 74, "Professionell klass"
73, "Tjänstemannaklass" 93, "Arbetare" 83, "Urban professional" 61, "Akademiker" 59, "Högre
tjänstemannaklass" 56. Curated counts are unchanged by option B (164 / 176, 28 / 28 false alarms
kept). Before the combined re-run this must be signed off, or `fe29df9` reverted; the alternatives
are option A, or a narrower B that keeps EGP / SEI class labels ("Professional class",
"Tjänstemannaklass") while dropping bare occupations.

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

#### Phase 5 implementation notes (done 2026-10-04)

Commit `e8124ee`. Values renamed to **"Born in another EU country"** / **"Born outside the EU"**
(open question 19 default). `real` keeps only the FolkmFodlandHVD labels (sv + en, plus the value
names); the dead legacy labels (Norden, EU/EES utom Norden, Europa utom EU/EES, continents) are
deleted. Synthetic: Norway, Iceland, Albania, Belarus, Bosnia, Serbia, Switzerland, UK / England /
Scotland / Wales, Ukraine, Yugoslavia, Kosovo, Moldova, Montenegro, North Macedonia moved to the
outside-EU list; Cyprus, Luxembourg, Malta and Åland added to the EU list; `nordic`, `scandinav`,
`europe`, `european`, `eu/europe`, `immigrant` deleted. `island` (Swedish for Iceland) is a
`word`-mode token, else "Åland Islands" (Finland) went outside the EU. Updated:
`config/mapping/scb_native/README.md`, `docs/architecture/sweden-generation-explorer/js/data.js`,
`docs/scb_population_and_comparison.md:178`, the `validate_mapped` module docstring, and
`tests/test_synthetic_mapper_base.py` (the Norway case now asserts "Born outside the EU"; the other
birth-location tests use inline fixtures). The generator needs no change (it keys only on the
Sweden labels) and no chart or label config names these values. The global tier
`config/mapping/scb/` keeps the old labels (open question 18: not mirrored, see the README).

Measured (label-translated): 168 pool personas change birth region — 162 EU → outside the EU
(birth country Norway 99, UK 24, Yugoslavia 17, Bosnia 17, Ukraine 3, other 2), 4 Sweden →
`__UNMAPPED__`, 2 `__UNMAPPED__` → Sweden.
Curated: 5 of 186 errors fixed (3 expected, plus the "Sverige (född i utlandet)" rows via
birth_country_detail; the other 181 are the `refine_from` mechanism, still open); 12 / 12 false
alarms kept; 4 personas newly `__UNMAPPED__` ("Sverige (född i utlandet)" texts;
`birth_location` is deprecated, so `validate_mapped` exempts it and no persona is lost).

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
| Phase 2A config | 603 personas in the full `01_Raw` pool; `swedish_02_all_pick_dag_v2_ollama_gemma4_e4b` would fall to 97 < 100 (Phase 2A notes) |

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
    *Implemented by default (Phase 4 option B): unmapped — reverses the spot-check answer.*
12. **"Lägre socioekonomisk grupp", "låg socioekonomisk status", "low SES", "Lågklass"** →
    Working (read as "lower class"). Confirm; Lågklass is the plan's extension. ≥ 4 rows.
    *Implemented with the default (Phase 2B).*
13. **Generic economy wording** — "begränsad/pressad/blygsam" → Working; "låg pension",
    "låglön" → Poverty; "trygg/stabil" → unmapped. ≈30 design rows.
    *Implemented with the defaults (Phase 2B).*
14. **Joint custody and status-only socio words** — joint custody → unmapped (SCB: undeterminable
    without the registered parent); student/pensionär removal in Phase 4. Together 100 capped
    rows (58 + 42).
    *Implemented with the defaults (Phase 2B / Phase 4); measured capped rows newly unmapped: parental 58 (all 2B causes), status words 38.*
15. **Same-sex couple / "two dads"** with parenthood unstated — keep Natural Parents (README
    default); alternative unmapped. 45 rows.
    *Implemented with the default (Phase 2B).*
16. **Industry undeterminables** — bare "Engineering" unmapped (alternative SNI M71 → F&B);
    Administration, charity/aid, teknisk service, media + kultur unmapped; Kundtjänst stays F&B.
    25 + ≈23 rows.
    *Implemented with the defaults (Phase 2B).*
17. **employment_type for ages 75–85** (no AKU source) — config-declared 65–74 proxy recorded in
    provenance; alternative raise (drops the attribute for those personas). Part of the 1,140
    employed 18–24 and 75–85 personas in the real reference. *Implemented with the default
    (`constants.EMPLOYMENT_TYPE_AGE_PROXIES`); recorded in the output's `tables_used` note.*
18. **Mirror to the global tier** `config/mapping/scb/` — mirror attribute files identical today;
    skip industry and parental (they differ by design).
19. **Label wording** — birth region: "Born in another EU country" / "Born outside the EU"
    (alternative "EU (excl. Sweden)" / "Outside EU"). Also consider relabelling "Sickness /
    Activity Compensation", which the spot check showed is read as covering sjukpenning (13 rows).
    *Birth-region wording implemented with the default (Phase 5); the Sickness / Activity relabel not done.*
20. **Occupation proxy** — Phase 4 option A or B. Default B (strict unmapped), given no
    Poverty reachability and the self-made bias. Also decides whether employment_status (≈40)
    and income_source (≈50) occupation tails keep growing as token lists.
    *Default B implemented (`fe29df9`) — measured impact far above the estimate: 887 capped personas,
    18–20 combinations below n. Sign-off or revert before the re-run (Phase 4 notes).*
21. **Minor unmapped defaults** — "Trans man", "Uppland", "Region Väst", "Serbia", "rötter
    från", "Ensamstående kvinna", bare "Borgerlig familj", "Bifamilj", living with parents
    (housing, 55), garbled values → unmapped; rented house → Rental (41). ≈150 rows.
    *Implemented for the Phase 2B attributes (sex, region, birth country, parental); housing items are 2A.*

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

### Pipeline run 2026-10-04 — mapping gate

Steps 1–4 of the protocol (re-sample, `mapping`, `validate_mapped`, `population_cap`; plus
`validate_raw`), run for the committed `analysis_workflow.yaml` selection: `swedish_02` only, 13
models × 5 v2 strategies = 65 combinations, `--n 100 --sample-seed 0`, every step `--force`, default
`output_base`. Into an emptied `03_Analysis/`; the pre-run tree is the read-only reference
`03_Analysis_backup-2026-10-04/`. Steps 5–7 not run. Phase 4 stood as reverted (`698bfed`:
occupation tokens kept; status words still removed, `fc660e5`).

**Re-sample.** `PYTHONHASHSEED=0 python scripts/generate/generate_scb_population.py --n 10000
--seed 42 --cache-ttl-days 100000 --output
data/scb_api/scb_population_n10000_seed42_mapping-fixes_2026-10-04.json`. Exactly two live fetches
(`HushallT03`, `TabVX13InkStruktN`). Expected-diff check passed exactly: `household_size` 7,141,
`income_source` 1,082, `socioeconomic_class` 544, `employment_type` 530 (all 18-24); every other
attribute identical. Household shares 19.9 / 27.8 / 15.8 / 21.7 / 8.9 / 3.4 / 2.6 % vs BE0101DK
19.7 / 28.2 / 15.9 / 21.2 / 9.3 / 3.2 / 2.6 % (χ² ≈ 4.7, df 6, within sampling error);
income_source has 8 categories. Both Swedish axes point at the new file (`99b9b0d`); the old file is
kept. The mapped real reference differs from the backup's only in those four attributes, with the
same counts.

**Curated rows** (new mapped value of each of the 12,793 rows; errors with a target category):
civil 2,791 / 2,795, education 1,638 / 1,679, employment_status 355 / 377, employment_type 402 /
692, housing 1,382 / 1,393, income 525 / 690 (the 59 reassigned to 325 / 330 count separately, as
in 2A), industry 518 / 537, parental 383 / 407, socio 164 / 176, sex 10 / 11, region 11 / 11, birth
country 6 / 6, household 2 / 3, birth_location 5 / 186 (`refine_from`, open). All equal to the 2A /
2B measured figures (housing +1, below). Overall 8,192 / 9,505 real errors (86.2 %). False alarms
kept 1,598 / 1,601 (age_group excluded: it is not a mapped field); lost exactly the three named
(two "Aktivitetsstöd kompletterat med bostadsbidrag", "Hyresrätt – lägenhet i villa").
Undeterminable rows: 1,061 unchanged, 347 moved (288 education, mostly length-unstated upper
secondary → 3A), 86 → `__UNMAPPED__` (48 housing disjunctions / Ägarlägenhet, 22 education).

**Whole-pool diff vs backup** (`mapping/`, 65 combinations, 11,461 personas):
changed cells civil 2,813, education 2,812, housing 1,593, income 862, industry 580,
employment_type 571, parental 570, socio 543, employment_status 412, birth_location 148 (after
translating the Phase 5 labels), sex 11, region 11, birth country 6, household 2. 10,934 changed cells: 8,975 are curated rows, 12 are the same string audited
elsewhere with the new value as verdict; the other 1,947 were matched against the plan's rules (3C → 3A 750, 325 / 330 168,
status words 159, Phase 5 country lists 143, lower-middle → Working 112, joint custody 80, wage first
59, hours facet / fixed-term 57, …). **First pass found five defects** — the `longest` tie-break
picking a shorter-head category against the SCB definition, invisible to the curated list because
the strings were never flagged: "Lower secondary school" → 3A (19 cells; `secondary school` beat
`lower secondary`), "Fastighetsförvaltning" → Public Administration (12; `förvaltning` beat
`fastighet`, SNI L 68 is F&B), "IT och konsulttjänster" / "IT and programming consultancy" → F&B
(4), "Förskola och barnomsorg" → Healthcare (3; förskola is SNI P 85), "Divorced and remarried" →
Divorced (3), plus "Gemensamt boende" (sambo) → unmapped and the Tenant-owned `seniorboende` veto
that unmapped "Bostadsrätt i seniorboende" (4). Fixed with longer tokens and the veto dropped
(`8c020a2`, regression cases added; simulated: 47 cells, one curated error fixed, none broken);
steps 2–4 re-run. Residue after the re-run: 141 cells / 130 strings, none above 2 cells, each a
documented rule (divorce without residence → unmapped, spouse's income → unmapped, civil marriage
→ Natural Parents, `fastighetsägare` Owner veto, "vulnerable" poverty cue, ongoing gymnasium →
ISCED 2) or a single garbled / mixed-cue text (e.g. "Förentalshus", "Blue-collar middle class",
"Byggnad och konstnärligt verk"). Not changed: these are single rows whose correct category is
itself undeterminable.

**population_cap.** 57 included, 8 withdrawn (backup: 58 / 7). The only new withdrawal is
`swedish_02_all_pick_dag_v2_ollama_gemma4_e4b` (116 → 99 clean < 100; predicted 97 in the 2A
notes), accepted by design (Ägarlägenhet unmapped, OB not fetched; house-or-flat disjunctions).
Lowest included margin: `…all_generate_pick_v2_openrouter_kimi_k3` 101. Largest drop:
`…all_generate_pick_v2_ollama_mistral_nemo_12b` 145 → 113.

**Verdict: EXPECTED** (after `8c020a2`). Not run: `validation_attrition` and steps 5–7.
`tests/test_axis_facet_defaults.py::test_flow_default_selects_exactly_the_highest_version_strategies`
fails on the committed `generate_parallel.yaml` (one strategy selected); unrelated, pre-existing.

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

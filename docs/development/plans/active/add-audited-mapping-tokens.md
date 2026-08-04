# Plan: Add Audited Mapping Tokens (scb_native)

**Date:** 2026-08-04
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/add-audited-mapping-tokens`

---

## Overview

Add 48 `equals` tokens to the `synthetic` block of 11 files under `config/mapping/scb_native/`,
recovering **103 personas** that currently fail the mapped-validity gate on a single attribute.
Every token is a spelling, inflection, diacritic, casing or translation variant of a token the
config **already declares for that same target value** — no new category, no new mapping policy.

## Problem Statement

The `/audit-unmapped` pass of 2026-08-04 over `swedish_02` (v2 strategies, all models, 50 combos,
8,946 personas) found 3,204 personas failing `validate_mapped`, of which 1,762 fail on exactly one
attribute (sole cause). Reading the offending raw values against the config that failed to match
them, 103 of those personas are blocked by values the config already commits to mapping and simply
fails to recognise in that spelling — e.g. `not applicable (retired)` where both `not applicable`
and `retired` are already `equals` tokens under Not Applicable.

Every such persona is a persona `population_cap` cannot draw, and the projection currently puts 12
of 50 combos below the N=100 clean target.

## Goals

### In Scope

1. Add the Tier A tokens below to the `synthetic` block of the named files, under the named target
   values, in the `equals` matcher only.
2. Gate the change on `regress.py` reporting **0 regressions** across all selected combos, with
   every re-routed pair reviewed by eye.
3. Re-run `mapping` → `validate_mapped` → `project.py` and record the measured persona delta
   against the 103 predicted here.
4. Optionally (Phase 4, independently droppable) add the Tier B tokens.

### Out of Scope

- **Adding any entry to an attribute's `values`** — the real population defines the category space.
  The five schema gaps found by the audit are recorded below as findings, not as work.
- **Adding `on_miss` to any attribute.** No attribute in this tier currently declares it (0 of
  5,485 misses were masked); it stays that way.
- **Any `contains` token.** Every edit here is `equals`.
- Mapping macro-regions (`Svealand`, `Götaland`), macro-sectors (`Services`, `Tjänstesektorn`),
  occupations answered into a non-occupation axis, or free-text sentences.
- **Fixing the `Rental apartment.contains: 'rent'` substring defect** — a real, separately-scoped
  problem (it over-maps: `'rent'` matches "pa**rent**s"). It needs `substring.py` + its own
  regression gate and must not ride along with an additive change.
- Regenerating personas to close the 12 under-target combos.

## Success Criteria

- [x] 48 `equals` tokens added across 11 files; `values` and the `real` block byte-identical.
- [ ] `probe.py` shows every listed value resolving to its stated target value, and no listed value
      resolving to a *different* value than stated.
- [ ] `regress.py` over all 50 combos reports `regressions == 0`.
- [ ] Every re-routed pair reported by `regress.py` reviewed and recorded in the plan.
- [ ] Miss counts of untargeted attributes unchanged.
- [ ] `ruff check src/` clean.
- [ ] Post-edit `rank.py` shows sole-cause personas recovered ≈ 103 (deviation explained if not).
- [ ] No file gained a `contains`, `all_of`, `none_of` or `on_miss` key it did not already have.

## Definitions

- **Precedent token**: an existing token, in the **same attribute**, under the **same target
  value**, of which the candidate is a written variant. A proposal without a named precedent is not
  a proposal. String similarity is explicitly *not* a precedent — `Götaland`→`Gotland` scores 0.93
  and is wrong.
- **Parity**: the candidate differs from its precedent only in spelling, inflection, diacritics,
  casing, punctuation or language. It introduces no concept the config had not already committed to.
- **Sole cause**: a persona whose `unmapped_fields` list, after the `birth_location` deprecation
  exemption, has length 1 and contains this attribute. Only sole-cause personas are recoverable by
  a single-attribute fix; the persona counts below are all sole-cause counts.
- **`equals` semantics** (`analysis/mapping/mapping_engine.py`): both sides are normalised by
  `text.lower()` with `_` → space, then stripped, then compared exactly. Consequences: casing folds
  (one token covers every observed casing), underscores fold to spaces, and an added `equals` token
  is **provably additive** — it can only match strings that previously matched nothing in the
  `equals` tier, and `equals` is the first tier in the sweep.
- **Recovered**: the persona passes `validate_mapped` after the edit *because* this attribute now
  resolves. Pre-edit sole-cause count is the estimate; Phase 3 measures the truth.

---

## Technical Design

### Approach

Append literal tokens to existing `equals` arrays. Nothing in `src/` changes. The mapping engine,
the tier selection (`parameters.mappings` in `config/synthetic/axes/countries/swedish_02.yaml`) and
the category space are all untouched.

The design constraint is not technical but **methodological**: the mapping config is part of the
measuring instrument. Any rule added to absorb what a model happens to emit moves that model's
fidelity score for a reason unrelated to the model. The parity test (precedent named, same target,
written variant only) is what keeps this change a spelling fix rather than a benchmark widening,
and it is why the audit refused ~250 personas' worth of plausible-looking candidates.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `equals` tokens with a named precedent (this plan) | Matches only strings that resolve to nothing today (verified: all 48 currently miss); reviewable one line at a time | Verbose — one token per observed spelling. **Not** unconditionally safe: `_walk` sweeps tier-outer/value-inner, so an `equals` under value A *does* pre-empt a string that value B's `contains` resolves today. The safety here is empirical, not structural — which is what Phase 2's `regress.py` gate exists to confirm | **Chosen** |
| `contains` stems (e.g. `högskola`, `arbetande`, `konsult`) | Fewer tokens, catches unseen variants | Steals across values: `contains: 'arbetande'` under Employed would capture `hemarbetande`, already a `contains` token under Unemployed — and Employed is declared first, so it wins. Same class of defect as the live `'rent'` → "pa**rent**s" bug. It also silently absorbs strings nobody has read, which is precisely the benchmark widening this audit refuses | Rejected |
| Add an `Other` / `Unknown` value where the model keeps answering outside the space | Would recover ~55 more personas (birth country, biological sex) | Forbidden: the real population defines the category space, and an invented category has no reference distribution to score against | Rejected — recorded as a schema gap |
| Add `on_miss` fallbacks | Recovers every persona instantly | Fabricates the marginal that TV distance measures; the score improves for no reason | Rejected |
| Fix generation prompts instead of config | Addresses the cause, not the symptom | Orthogonal — does nothing for the 9,036 personas already generated, and most of the mass is free text no prompt fix fully removes | Deferred (separate work) |

### Architecture & Module Contracts

No module changes. The contract being edited is the config file schema.

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/mapping/scb_native/*.json` (`synthetic` block) | Declare, per target value, the raw strings that resolve to it | raw string → target value | Which model or strategy produced the string; how often it occurs |
| `config/mapping/scb_native/*.json` (`values`, `real` blocks) | Declare the category space and the real-population mapping | **unchanged by this plan** | — |
| `analysis/mapping/mapping_engine.py` | Tiered resolution `equals → all_of → contains → numeric`, `none_of` as cross-tier veto | **unchanged by this plan** | Any specific token |

```
config/mapping/scb_native/
├── parental_structure.json    ← Single Mother, Single Father
├── housing_tenure.json        ← Owner-occupied, Tenant-owned, Rental
├── employment_type.json       ← Not Applicable
├── employment.json            ← Employed          (file name ≠ attribute name)
├── education.json             ← ISCED 5A
├── socioeconomic.json         ← Middle Class, Wealthy   (file name ≠ attribute name)
├── civil_status.json          ← Married, Single/Never Married, Widowed
├── region.json                ← Västra Götaland, Södermanland
├── income_source.json         ← Wage / Business, Insurance / Allowance
├── industry_sector.json       ← Financial & Business Services, Manufacturing
└── birth_country_detail.json  ← Sweden
```

---

## Implementation Plan

### Phase 1: Tier A token additions
**Goal:** Add the 48 tokens below to the `synthetic` block `equals` arrays. Nothing else.

**Started:** 2026-08-04T15:05:00+02:00
**Completed:** 2026-08-04T15:30:02+02:00

Each table is one file. `personas` is the sole-cause count this token recovers, from the
2026-08-04 audit. `precedent` is the existing token in the same attribute, under the same target
value, that justifies it.

#### `config/mapping/scb_native/parental_structure.json` — 24 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Single Mother | `single parent (mother)` | 16 | `single_parent_mother` (equals) |
| Single Mother | `Single-parent household (mother)` | 5 | `Single-mother household` (equals) |
| Single Mother | `Endast mor` | 2 | `Endast biologisk mor` (equals) |
| Single Mother | `Endast mamma` | 1 | `Endast biologisk mor` (equals) |
| Single Father | `Single-parent household (father)` | 0 | `Single-father household` (equals) — symmetry only |

#### `config/mapping/scb_native/housing_tenure.json` — 22 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Owner-occupied (villa/house) | `Äga bostad` | 6 | `Ägt bostad`, `Äga` (equals) — inflection |
| Owner-occupied (villa/house) | `äga sin bostad` | 4 | `Ägt bostad`, `Äga` (equals) — inflection |
| Owner-occupied (villa/house) | `bostad med hypotek` | 2 | `mortgage` (contains) — translation |
| Owner-occupied (villa/house) | `Hypotek` | 0 | `mortgage` (contains) — translation |
| Tenant-owned apartment (bostadsrätt) | `ägs lägenhet` | 4 | `Ägd lägenhet`, `Owned apartment` (equals) |
| Rental apartment | `Subletting` | 2 | `Andrahandsuthyrning` (equals) — translation |
| Rental apartment | `Subletting (andrahandskontrakt)` | 2 | `Andrahandskontrakt` (equals) |
| Rental apartment | `Kollektivboende` | 1 | `shared housing`, `shared accommodation` (contains) |
| Rental apartment | `Socialbostad` | 1 | `social housing` (contains) — translation |

#### `config/mapping/scb_native/employment_type.json` — 21 personas

All under **Not Applicable**. Precedents, all already `equals` under that same value:
`not applicable`, `retired`, `arbetslös`, `ingen anställning`, `ingen`; plus `volontär` (contains)
for the volunteer pair.

| target value | tokens to add | personas |
|---|---|---|
| Not Applicable | `not applicable (retired)` | 7 |
| Not Applicable | `Not applicable (unemployed)` | 4 |
| Not Applicable | `Not applicable/No current employment` | 2 |
| Not Applicable | `not_applicable_retired` | 2 |
| Not Applicable | `No employment` | 2 |
| Not Applicable | `retired (no employment)` | 1 |
| Not Applicable | `none` | 1 |
| Not Applicable | `Volunteer work` | 1 |
| Not Applicable | `voluntary work` | 1 |
| Not Applicable | `unemployed` | 0 |

> Check on the last three: Not Applicable declares `none_of: ['jobb','job','assistant','worker','intern']`.
> None of the added tokens contains any of them (`work` ≠ `worker`). Confirm with `probe.py`.

#### `config/mapping/scb_native/employment.json` (employment_status) — 9 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Employed | `consultant` | 3 | `Konsult` (equals) — translation |
| Employed | `Självständig` | 2 | `selvständig` (contains) — the Norwegian spelling is already listed |
| Employed | `Fast anställning` | 2 | `Arbetande i fast anställning` (equals) |
| Employed | `arbetad` | 2 | `Arbetande`, `Arbetar` (equals) — inflection |

#### `config/mapping/scb_native/education.json` — 6 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Post-Secondary 3+ yrs (ISCED 5A) | `Socionomexamen` | 2 | `Lärarexamen`, `Sjuksköterskeexamen` (equals) |
| Post-Secondary 3+ yrs (ISCED 5A) | `Civilekonomexamen` | 1 | `Civilekonom`, `Civilingenjörsexamen` (equals) |
| Post-Secondary 3+ yrs (ISCED 5A) | `Högskola (3 år)` | 1 | `Högskola` (equals) |
| Post-Secondary 3+ yrs (ISCED 5A) | `Högskola (3 år eller mer)` | 1 | `Högskola/universitet, 3 år eller mer` (equals) |
| Post-Secondary 3+ yrs (ISCED 5A) | `Högskola 3 år eller mer` | 1 | `Högskola/universitet, 3 år eller mer` (equals) |

> `equals` deliberately, not `contains: 'högskola'`. The exact string `Yrkeshögskola` would survive
> such a stem (it is an `equals` token under Post-Secondary < 3 yrs (ISCED 4+5B), and the global
> `equals` sweep runs before any `contains`) — but every *unlisted* `yrkeshögskola`-compound would
> then be contested between two values on declaration order alone, which is not a resolution rule
> anyone should rely on.

#### `config/mapping/scb_native/socioeconomic.json` — 5 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Middle Class | `pensioner class` | 3 | `pensionär` (contains, Middle Class) — translation of a commitment already made |
| Wealthy | `Högstatus` | 2 | `Högklass` (equals, Wealthy) — the `Hög-` family under this same value. (`Mellanstatus` sits under Middle Class and is *not* a valid precedent by this plan's own rule: same attribute **and** same target value.) |

#### `config/mapping/scb_native/civil_status.json` — 5 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Married | `Sammanboende med barn` | 1 | `Sammanboende` (equals) |
| Married | `Sammanboende utan barn` | 1 | `Sammanboende` (equals) |
| Single/Never Married | `engaged` | 2 | `Förlovad` (equals) — translation |
| Widowed | `Enka` | 1 | `Änka` (equals) — diacritic |

#### `config/mapping/scb_native/region.json` — 4 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Västra Götaland | `Västra Götarelands län` | 2 | `Västra Götalands län` (equals) — one-letter insertion |
| Västra Götaland | `Västra Götareland` | 1 | `Västra Götaland` (equals) — one-letter insertion |
| Södermanland | `Södermanaland` | 1 | `Södermanland` (equals) — one-letter insertion |

#### `config/mapping/scb_native/income_source.json` — 4 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Wage / Business | `lon_fran_anstallning` | 2 | `Lön från anställning` (equals) — diacritic fold |
| Wage / Business | `Inkomst från tjänst` | 1 | `Inkomst av tjänst` (equals) — one preposition |
| Insurance / Allowance | `Arbetsförmedlingen` | 1 | `försäkringskassa` (contains) — a named benefit agency is already mapped |

#### `config/mapping/scb_native/industry_sector.json` — 2 personas

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Financial & Business Services | `Vetenskaplig och teknisk verksamhet` | 1 | `Professionell, vetenskaplig och teknisk verksamhet` (equals) — the same string minus one leading word |
| Manufacturing, Mining & Energy | `Industry` | 1 | `Industri` (equals) + `industrial` (contains) — translation |

#### `config/mapping/scb_native/birth_country_detail.json` — 1 persona

| target value | tokens to add | personas | precedent |
|---|---|---|---|
| Sweden | `Göteborg` | 1 | `stockholm` (contains) — a Swedish place name already resolves to Sweden |

**Files Modified:** the 11 files listed above, `synthetic` block only. (`biological_sex.json` is a
12th file, but it is touched only by the optional Phase 4.)

**Dependencies:** None.

---

### Phase 2: Verification gate
**Goal:** Prove the change is additive and that nothing moved that should not have.

- [ ] 2.1 — `probe.py` per touched attribute with the full value list; confirm every value resolves
      to its stated target and no value resolves elsewhere.
- [ ] 2.2 — `regress.py` over all 50 combos, **run in the background** (it exceeds the 120 s default
      on ~9,000 personas). Acceptance: `regressions == 0`.
- [ ] 2.3 — Review **every** re-routed pair by eye and record them in this plan under a
      "Verification results" heading.
- [ ] 2.4 — Confirm the miss counts of untargeted attributes are unchanged (`rollup.py` diff).
- [ ] 2.5 — `ruff check src/`.
- [ ] 2.6 — Confirm no `contains` token was added anywhere, so `substring.py` is not required.

```bash
python .claude/skills/audit-unmapped/scripts/probe.py --attribute housing_tenure \
    --value "Äga bostad" --value "ägs lägenhet" --override housing_tenure.json=<edited>
python .claude/skills/audit-unmapped/scripts/regress.py --report <scratch>/regress.md   # background
ruff check src/
```

**Files Modified:** none (verification only; reports go to the scratchpad).

**Dependencies:** Phase 1.

---

### Phase 3: Re-map, re-validate, re-project
**Goal:** Replace the predicted 103 with a measured figure and refresh the projection.

- [ ] 3.1 — Re-run the mapping stage for the `swedish_02` v2 combos with `--force`.
      **Entry point:** a bare `scripts/analyze/map_populations.py --force` maps only the targets in
      `config/analysis/comparison_targets.yaml` (one legacy combo) — it is **not** the command that
      re-maps the axis-composition combos. Use its `--model-id/--strategy-id/--country-id` mode
      instead: one combo per invocation, no bulk form, so this is a loop over the combos in scope.
- [ ] 3.2 — Re-run `validate_mapped_personas.py` (requires `--model-id`, `--strategy-id`,
      `--country-id`; there is no bulk `--force` form) for every affected combo.
- [ ] 3.3 — `rank.py`: record sole-cause personas recovered vs the 103 predicted.
- [ ] 3.4 — `project.py --target-n 100`: record the new grid and the new run-size total against the
      pre-edit baseline (12 combos under target; 9,836 point / 15,575 safe).
- [ ] 3.5 — Record both figures in this plan.

**Files Modified:** none in the repo — `03_Analysis/` artefacts only.

**Dependencies:** Phase 2.

---

### Phase 4 (optional, independently droppable): Tier B tokens
**Goal:** Precedent-valid tokens recovering ≤1 persona each (~19 total). Drop this phase entirely
without touching Phases 1–3 if the added surface is not judged worth it.

| file | target value | tokens | personas |
|---|---|---|---|
| `region.json` | Gävleborg · Västernorrland · Örebro · Västra Götaland · Jönköping · Stockholm | `Hälsingland` · `Medelpad` · `Närke län` · `Bohuslän County` · `Jonköping` · `STH` | 0 each — precedent is `gästrikland`→Gävleborg (an historic province already mapped to its county) |
| `civil_status.json` | Married | `Samsbo`, `Sammanlevande`, `Co-habiter`, `Samregistrerad` | 1 each |
| `civil_status.json` | Single/Never Married · Divorced | `Singe` · `Separerad under process` | 1 · 1 |
| `employment.json` | Employed · Student | `Forvärvsarbetande`, `Fulltidsanställning`, `Full-time Work` · `Gymnasieelev` | 1 each |
| `education.json` | `Post-Secondary 3+ yrs (ISCED 5A)` · `Upper Secondary ≤ 2 yrs (ISCED 3C)` | `Gandidatexamen`, `Ekonomexamen från högskola`, `Förskollärarexamen` · `Handelsutbildning` | 1 each |
| `education.json` | `Post-Secondary 3+ yrs (ISCED 5A)` · `Pre-Secondary 9-10 yrs (ISCED 2)` | `Lärarutbildning` · `Grundskolexamen` | 0 · 0 |
| `income_source.json` | `Wage / Business` | `Consulting fees`, `Konsulttjänster`, `Konsultarvoden` | 1 · 1 · 0 |
| `housing_tenure.json` | `Owner-occupied (villa/house)` · `Rental apartment` | `Bostadsägning` · `Allmännyttan`, `Allmännyttig bostad`, `Kommunal bostad` | 1 · 0 each |
| `industry_sector.json` | `Education` | `Skolväsendet` | 1 |
| `socioeconomic.json` | `Middle Class` | `Småföretagarklass` | 1 |
| `biological_sex.json` | `Female` | `K` | 0 — closes the asymmetry where `m` is an `equals` token under Male but `k` is not under Female |
| `biological_sex.json` | `Male` | `mänlig` | 0 — precedent `manlig` (contains, **Male**); it is a Male-meaning string and must not go under Female |
| `birth_country_detail.json` | `Yugoslavia` | `Yugoslavia (former)` | 0 |

**Dependencies:** Phase 3 (so the Tier A delta is measured in isolation first).

---

## Testing Plan

### Unit Tests
- [ ] Existing `pytest` mapping suite passes unchanged (no engine change, so a failure means a
      malformed JSON edit).
- [ ] JSON parse check on all 12 edited files.
- [ ] Assert `values` and the `real` block are byte-identical pre/post for every edited file.

### Integration Tests
- [ ] `regress.py` two-arm run (candidate vs baseline) over all 50 combos: `regressions == 0`.
- [ ] `regress.py` provenance null-check (no `--candidate`, no `--override`) reports `0/0/0`,
      confirming the stored artefacts were produced by the config on disk.
- [ ] `rollup.py` before/after: untargeted attributes' miss counts unchanged.

### Manual Verification
- [ ] Every re-routed pair from `regress.py` read by eye and recorded.
- [ ] Spot-check one recovered persona per edited attribute in the mapped JSON.
- [ ] Confirm the diff adds only array elements — no key added, no key removed, no value renamed.

### Edge Cases
- [ ] `not_applicable_retired` — underscores normalise to spaces; confirm it does not collide with
      the existing `not applicable` token in a way that changes which value wins.
- [ ] `none` (4 chars) as an `equals` token under Not Applicable — exact match only, so it must not
      affect any longer string containing "none".
- [ ] `Volunteer work` / `voluntary work` against Not Applicable's `none_of` list.
- [ ] `Hypotek` and `Socialbostad` must not be captured by `Owner-occupied.none_of`
      (`hemförsäkring`, `ej ägd`, …) before reaching their intended value.
- [ ] `Göteborg` in `birth_country_detail` must not disturb `region.json`, where `göteborg` already
      maps to Västra Götaland — different attribute, confirm no interaction.

---

## Documentation Plan

- [ ] Add a changelog entry noting the token additions and the measured persona delta.
- [ ] Record the audit provenance in this plan: selection line, date, combo count (below).
- [ ] Add a knowledge-base note on the parity rule (precedent named, `equals` only, refuse when
      close) so the next audit does not re-litigate it.
- [ ] Cross-reference `docs/development/plans/pending/report-unmapped.md` and
      `investigate-unknown-unmatched-scb-labels.md`.
- **Not applicable:** README.md and CLAUDE.md — no command, architecture or invariant changes.

---

## Rollback Plan

1. **Before re-mapping:** `git revert` the single config commit. Nothing else in the repo changed.
2. **Data considerations:** no migration. `03_Analysis/mapping/` and `validate_mapped/` artefacts
   produced under the edited config are regenerated by re-running the map + validate stages against
   the reverted config. `01_Raw` is never written by any of this.
3. **Rollback procedure:** revert the config commit → re-run map + validate for the affected combos
   → confirm `regress.py`'s null-check reports `0/0/0` against the restored config.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A token widens the instrument and flatters a weak model | Low | High | Every token names a precedent under the same target value; `equals` only; the audit refused ~250 personas' worth of no-precedent candidates |
| An `equals` token silently does nothing (written under a value the axis does not declare) | Medium | Low | `probe.py` per value in Phase 2; the declared `values` list is printed by `extract.py` and reproduced above |
| Three combos' artefacts were stale when the audit ran (`ollama_deepseek_r1_14b` ×2, `claude_sonnet` ×1 — raw newer than mapped) | Certain | Low | Their values were re-resolved against the current config with 0 disagreements; Phase 3 re-maps everything anyway, which is where the measured delta comes from |
| Predicted 103 overstates the recovery | Medium | Low | It is a sole-cause count on a pre-edit snapshot; Phase 3 measures it. Under-recovery means a persona failed on a second attribute too — not a regression |
| A `contains` token creeps in during implementation | Low | High | Success criterion asserts it explicitly; if one is added, `substring.py` becomes mandatory before merge |
| Phase 3 blocked by the map/validate entry points | Medium | Medium | Known and flagged in task 3.1/3.2: the bare `map_populations.py --force` maps only `comparison_targets.yaml`, and the validators require explicit `--model-id/--strategy-id/--country-id` |

---

## Findings recorded, not actioned

**Schema gaps** — refused because the real population defines the category space:

1. `birth_country_detail` has no residual "Other country" value (21 values = Sweden + SCB's top-20).
   ~25 personas naming real countries outside that list are unmappable **by construction**. Lowest
   singleton rate of any attribute (0.5), so this is systematic, not noise. Worth checking whether
   the real SCB reference carries an "Övriga länder" bucket — if it does, this is a config omission
   rather than a true gap.
2. `biological_sex` has no unknown/indeterminate value — 27 personas on `Unknown`/`unspecified`/
   `Not specified`, plus 4 on `intersex`.
3. `parental_structure` has no alternating-residence (shared-custody) category — ~25 personas.
4. `housing_tenure` has no special/senior-housing tenure (~10 personas), no "living with parents",
   and no `Tomträtt` (site leasehold).
5. `civil_status` has no unknown bucket.

**Config defects** — each needs its own scope and gate:

- `Rental apartment.contains: 'rent'` matches "pa**rent**s". Confirmed live: matching is
  `lower()` substring, and `Living with parents` is absent from the miss log while its Swedish
  equivalents (`Boende hos föräldrar`, `Föräldrahem`) are present — i.e. the English form is being
  silently mapped to Rental through an infix. Confirmed directly: `resolve('Living with parents')`
  returns Rental apartment. This **over**-maps, so no validity CSV will ever flag it. Ranked #1 of
  the 611 tokens `substring.py` flags (the tier declares 1,216 `contains` tokens in total).
- `folkskola` is split: `Folkskola` is `equals` under ISCED 1 while `folkskola` is `contains` under
  ISCED 2. Same word, two targets.
- `biological_sex` asymmetry: `m` is `equals` under Male; `k` is not under Female (Phase 4).

**Generation defects** (not mapping problems): prompt-template leakage (`<your choice>`,
`<choice>`, `<chosen>`) and refusal-to-answer sentences (`Insufficient context to determine
biological sex.`) appear as raw values.

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Tier A edits | ~1 h (48 tokens, 11 files) | None |
| Phase 2 — Verification gate | ~1 h wall-clock, mostly waiting on background `regress.py` | Phase 1 |
| Phase 3 — Re-map / re-validate / re-project | ~1–2 h, dominated by the map + validate runs | Phase 2 |
| Phase 4 — Tier B (optional) | ~1 h including its own gate | Phase 3 |

---

## Audit provenance

All persona counts come from a single `/audit-unmapped` pass on **2026-08-04**:

```
selection -- country: swedish_02 (default) | strategies: v2 default (5 of 10 discovered):
all_generate_evaluate_pick_v2, all_generate_evaluate_random_pick_v2, all_generate_pick_v2,
all_pick_dag_v2, all_pick_v2 | models: all | combos: all
```

- 50 combos, 8,946 personas evaluated, 3,204 failing, 1,762 sole-cause recoverable
- 5,485 misses over 4,006 distinct values; **0 masked** (no attribute declares `on_miss`)
- Singleton rate 0.84–0.92 on every large attribute — the residual mass is free text, not
  vocabulary, and is not addressable by config
- Pre-edit projection at N=100: 12 of 50 combos under target; 9,836 (point) / 15,575 (safe)
  total run size across those 12

`inventory.py` returned **HALT** on this pass (three combos' raw pool newer than their mapping
artefacts). The audit proceeded on the existing mapping by explicit instruction; see the risk table.

---

## References

- Related plans: `docs/development/plans/pending/report-unmapped.md`,
  `docs/development/plans/pending/investigate-unknown-unmatched-scb-labels.md`
- Skill: `.claude/skills/audit-unmapped/` (Step 4 judgement criteria, the parity test, hard refusals)
- Engine: `src/population_synthetic/analysis/mapping/mapping_engine.py` (tier order, normalisation)
- `docs/real_mapper_philosophy.md` — why the real population defines the category space

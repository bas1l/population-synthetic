# Plan: Fix the `rent` Substring Over-Mapping (scb_native / housing_tenure)

**Date:** 2026-08-05
**Author:** Basil
**Status:** Draft
**Base Branch:** `dev`
**Branch:** `feature/fix-rent-substring-overmapping`

---

## Overview

`config/mapping/scb_native/housing_tenure.json` declares `"rent"` as a `contains` token under
**Rental apartment**. Matching is plain `lower()` substring, so it also matches **pa-rent-s**:
74 personas whose raw value says only that they live with their parents are currently assigned a
tenure they never stated, on a **scored** axis. This plan measures the defect exactly, evaluates
four candidate remedies against measured persona-level cost, puts the correctness-versus-pool-size
trade-off to the user as an explicit decision gate, applies the chosen remedy under the
`regress.py` gate, and re-runs the mapping → validation → cap chain so the published numbers
reflect the fix.

## Problem Statement

The `/audit-unmapped` pass of **2026-08-05** (`inventory.py` verdict `fresh`, 0 of 5,892 recorded
misses disagreeing with the config on disk) over `swedish_02`, the five v2 strategies, all models,
**50 combos / 9,448 personas** found this defect and priced it.

**Confirmed live** by `probe.py` against the current tier (`scb_native`, sha256 `cef9dd69a5cd`):

| raw value | resolves to |
|---|---|
| `Living with parents` | **Rental apartment** |
| `living with parents` | **Rental apartment** |
| `Parents' Home` | **Rental apartment** |
| `Föräldrahem` | `__UNMAPPED__` |
| `Allmännyttan` / `Kommunal bostad` / `Municipal housing` | `__UNMAPPED__` |

**Priced** by `substring.py --attribute housing_tenure` over the 9,448-persona corpus:

- 44 tokens flagged for `housing_tenure`; **26 of the 44 currently change a persona's mapping**.
- `rent` ranks **#1**: **586 personas via this token alone**, 1,041 personas affected, 303 distinct
  raw values.
- Split by boundary:
  - **infix — 62 value forms, 172 instances, 74 personas.** The accidents: `Living with parents`,
    `Living with Parents`, `Parents' Home`, `Parent's home`, `Lives with parents`,
    `Living with parent(s)`, `Living with parent, tenure unspecified`,
    `Living with parents as tenants`, `Living with parents/family`, `Parents' home with siblings`,
    `Boende i föräldrarnas hus (living with parents)`,
    `Familjsbostad (Family home, often provided by one of the parents)`, plus Swedish suffix noise
    (`Bostadsrent`, `Kontractrent`, `Förent bostad med en annan person`).
  - **prefix/suffix — 241 value forms, 869 instances, 373 personas.** The legitimate compounds:
    `rented apartment`, `rented`, `renting`, `renter`, `rented_apartment`, `Private rented`,
    `renting an apartment`, `rented studio apartment`, …
- Other `housing_tenure` tokens that currently move personas, for the same triage pass:
  `bostadsrätt` 140, `hyres` 133, `ägar` 87, `eigen` 67, `owned` 61, `ägd` 54, `owner` 53,
  `eget h` 34, `mortgage` 33, `uthyr` 17, `villa` 13.

### Why this outranks every recovery the same audit found

1. **It over-maps, so no validity CSV can ever flag it.** `validate_mapped` only sees the
   `__UNMAPPED__` sentinel. A persona given a wrong-but-plausible `Rental apartment` passes the
   gate, is drawn by `population_cap`, and enters every downstream analysis as clean data.
2. **It contaminates a scored marginal.** `housing_tenure` is one of Sweden's 14 analysed axes.
   The 74 personas inflate the `Rental apartment` proportion that total-variation distance is
   computed from, so `fidelity`, `multivariate_fidelity`, `model_ranking` and
   `method_significance` all inherit the error.
3. **The bias is language-correlated, therefore model-correlated.** The English forms
   (`Living with parents`) are silently absorbed while the Swedish equivalents (`Föräldrahem`,
   `Boende hos föräldrar` — 9 personas) fall to `__UNMAPPED__` and fail the gate. Two models
   expressing the *same* fact in different languages receive different treatment: one is scored,
   the other is discarded. A uniform bias would at least cancel across the ranking; this one does
   not.
4. **Scale.** 74 personas versus the ~17–24 personas the whole 2026-08-05 audit could recover
   across 9 precedent-backed token proposals — the defect is 3–4× the entire recovery opportunity.

### Relationship to the active token plan

`docs/development/plans/active/add-audited-mapping-tokens.md` (branch
`feature/add-audited-mapping-tokens`) is where this defect was **first recorded**, as a one-line
entry in its *Config defects* section alongside the `folkskola` split (`Folkskola` is `equals`
under ISCED 1 while `folkskola` is `contains` under ISCED 2) and the `biological_sex` asymmetry
(`m` is `equals` under Male, `k` is not under Female). That plan explicitly scoped the fix **out**,
on the grounds that a subtractive `contains` change must not ride along with an additive `equals`
change. **This plan supersedes that one-line record and does not duplicate any token-addition
work.** The two are independent: this plan touches exactly one matcher list; that plan adds
`equals` tokens to ten files.

## Goals

### In Scope

1. Establish provenance before measuring: `inventory.py` `fresh` and a `regress.py` provenance
   null-check reporting `0/0/0`.
2. Classify all 303 raw values that reach **Rental apartment** through `rent`, separating the
   infix accidents from the prefix/suffix compounds, and attribute both to personas, combos,
   models and methods.
3. Quantify the contamination: the share of the `Rental apartment` marginal in the **capped**
   mapped populations that exists only because of this token, per combo and per model.
4. Triage the other 11 `housing_tenure` `contains` tokens that currently move personas, and record
   a verdict for each (defect / legitimate compound / needs its own scope).
5. Evaluate the four candidate remedies below with `probe.py` + `regress.py` against
   scratchpad-materialised candidate configs — **measured**, never estimated.
6. Put the correctness-versus-pool-size trade-off to the user as an explicit decision gate.
7. Apply the chosen remedy to `config/mapping/scb_native/housing_tenure.json` under the full gate
   (`regressions == 0`, every re-routed pair read by eye).
8. Re-run `mapping` → `validate_mapped` → `population_cap` and every downstream consumer, and
   record the measured effect on the clean pool, on the `housing_tenure` TV similarity, and on the
   model ranking.
9. Add a regression guard that prevents a new sub-4-character `contains` token from being
   introduced.

### Out of Scope

- **Adding any entry to `housing_tenure.values`.** The real population defines the category space
  (`docs/real_mapper_philosophy.md`). There is no "living with parents" tenure in the SCB
  reference and none may be invented, however many personas it would rescue.
- **Adding `on_miss` to `housing_tenure`** — or to any scored axis. It would fabricate the very
  marginal TV distance measures. No attribute in this tier declares one today; it stays that way.
- **The full-tier `contains` sweep.** The tier declares ~1,216 `contains` tokens and a prior
  whole-tier `substring.py` run flagged 611. Auditing all of them is a **follow-up plan**
  (`audit-contains-tokens-scb-native`), not this one. This plan is bounded to `housing_tenure`:
  `rent` for remediation, the other 11 movers for triage only.
- **Remediating any token other than `rent`.** If triage finds a second defect, it is recorded and
  scoped separately — one subtractive change per gate, so the measured delta is attributable.
- Regenerating personas to close the 8 under-target combos, or any prompt-side fix.
- The `folkskola` split and the `k`/Female asymmetry (both belong to the token plan's Phase 4).

## Success Criteria

- [ ] `inventory.py` reports `fresh` and `regress.py` with no `--candidate`/`--override` reports
      `0/0/0` before any measurement is quoted.
- [ ] All 303 `rent`-matched values are classified, and the infix/prefix/suffix split is reproduced
      independently of `substring.py`'s own tally.
- [ ] The `Rental apartment` contamination share is stated per combo **and** per model, each with
      its denominator.
- [ ] Each of the four remedies has a measured `regress.py` outcome: newly-resolved / regression /
      re-routed counts over all 50 combos.
- [ ] The user has chosen a remedy from a table that states, for each, the personas made correct,
      the personas moved to `__UNMAPPED__`, and the resulting clean-pool size.
- [ ] The applied change modifies **only** the `synthetic → Rental apartment` matcher block:
      `values` and the `real` block are byte-identical, verified by diff.
- [ ] `regress.py` reports `regressions == 0`; every re-routed pair is listed in this plan with a
      by-eye verdict.
- [ ] `substring.py` re-run on the post-edit config no longer flags `rent`, and no new token enters
      the top 10.
- [ ] `rollup.py` before/after shows every attribute other than `housing_tenure` unchanged.
- [ ] The chain `mapping` → `validate_mapped` → `population_cap` is re-run for all 50 combos and
      the measured clean-pool delta is recorded against the prediction.
- [ ] `ruff check src/` clean; `pytest` green, including the new sub-4-character guard test.
- [ ] Any already-published `housing_tenure` figure in the manuscript is either confirmed unchanged
      or updated, and the change is noted in the changelog.

## Definitions

- **Over-mapping**: a raw value resolves to a canonical category the value does not support.
  Invisible to `validate_mapped`, which only detects the `__UNMAPPED__` sentinel. The opposite,
  **under-mapping**, is what the audit's miss log records.
- **Correct `housing_tenure` resolution**: the raw string states, or unambiguously implies, one of
  the three tenure forms — ownership (`äganderätt`/villa/house owned), tenant-ownership
  (`bostadsrätt`), or rental (`hyresrätt`/rented). A string that states *who a persona lives with*
  (`Living with parents`) states a household composition, **not** a tenure, and is therefore
  correctly `__UNMAPPED__` under the current category space.
- **Infix match**: the token has letters on both sides in the raw value (`rent` inside
  `pa-rent-s`). The shape most likely to be accidental.
- **Prefix / suffix match**: a word boundary on one side (`rent` in `rented apartment`). The
  compounding case, usually the reason a rule was written as `contains`.
- **Personas via token alone**: deleting *that one token* and re-resolving changes what those
  personas map to. Anything above zero is currently in the data.
- **Token subsumption**: token *A* is subsumed by token *B* under the same target value when every
  string containing *A* also contains *B*. `rental` is subsumed by `rent`; this is why
  `substring.py` reports `rental` at **0 personas via token alone**, and it must **not** be read as
  "`rental` is dead code". Deleting `rent` un-subsumes `rental`, which then covers `rental*` forms
  but **not** `rented` / `renting` / `renter` / `rents`.
- **Wrong-but-clean persona**: passes `validate_mapped`, is drawn by `population_cap`, and carries
  a value the raw input does not support. The population this plan exists to eliminate.
- **Clean pool**: `validate_raw.passed ∩ validate_mapped.passed` per combo — the set
  `population_cap` actually draws from. Currently **6,066 / 9,527 = 63.7 %**, with 8 combos below
  the N=100 operational target.
- **The audited slice**: country `swedish_02`, the five highest-version (v2) strategies, all
  models, 50 combos. Every figure in this plan is measured on it; none generalises to the v1 arms
  without re-measurement.

---

## Technical Design

### Approach

Measure first, decide second, edit third — the reverse of the order the defect invites. The
measurement phases (0–2) are read-only and touch nothing under `config/`, `01_Raw/` or
`03_Analysis/`; candidate configs live only in the scratchpad. The decision is the user's, because
it is not a technical one: it trades benchmark correctness against clean-pool size, and both are
legitimate objectives of this project.

**Engine mechanics the design depends on** (`analysis/mapping/mapping_engine.py`, verified by
reading, not assumed):

1. **Normalization** repairs double-encoded UTF-8, folds typographic punctuation to ASCII,
   lowercases, and collapses `_` to spaces. Hyphens are preserved; the string is not stripped.
   Both the raw value and every config token pass through it, so `rented_apartment` and
   `rented apartment` are the same string to the matcher.
2. **`contains` is plain substring** — `normalize(tok) in normalize(raw)`. There is no word
   boundary, and adding one would be an engine change affecting all ~1,216 tokens in the tier. That
   is a far larger blast radius than this defect justifies, which is why option (e) below is
   rejected.
3. **The sweep is globally tiered**: `equals` across *all* values → `all_of` → `contains` →
   numeric. A later value's `equals` therefore beats an earlier value's `contains`.
4. **Within a tier, declared `values` order breaks ties.** For `housing_tenure` that order is
   `["Owner-occupied (villa/house)", "Tenant-owned apartment (bostadsrätt)", "Rental apartment"]`.
   **Consequence:** a parent-string that also contains `house` — `"my parents' house"` — already
   resolves to **Owner-occupied** via that value's `contains: 'house'`, *not* to Rental. Removing
   `rent` will therefore re-route some strings to Owner-occupied rather than to `__UNMAPPED__`.
   That is a second over-mapping of the same shape and must be read pair-by-pair, not assumed away.
5. **`none_of` is a veto, not a tier**: it rejects its own value in every tier, but does not stop
   another value from claiming the string. A `none_of` under Rental apartment therefore hands
   parent-strings to whichever value matches next — see point 4.

**Pipeline-engineering principles applied** (`~/.claude/knowledge/data-pipeline-engineering/`,
guide 03 §6 "Handling missing and partial data honestly"):

- *Distinguish "zero" from "absent."* A persona whose tenure is unstated and a persona who rents
  are different facts; `rent`-on-`parents` collapses the first into the second. The explicit absent
  marker already exists (`__UNMAPPED__`) — the fix is to let it be used.
- *Gate metrics on data availability; exclude rather than impute.* Excluding a persona from the
  tenure axis is the honest outcome of an unstated tenure. That exclusion currently costs the whole
  persona, because `validate_mapped` is all-or-nothing per persona — a structural point worth
  recording, but not one this plan changes.
- *Report what was dropped.* Whatever remedy is chosen, the persona count it moves to
  `__UNMAPPED__` is stated in the changelog and, if the manuscript quotes housing figures, in the
  limitations section.

### Alternatives Considered

Every persona figure below is **to be measured in Phase 3**, not estimated; the table records the
shape of each option and the prediction it will be judged against.

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| **(a) Delete `rent`**, keep the existing longer tokens (`rental`, `hyres`, `hyresrätt`, `uthyr`, `hyra`) and add `equals` tokens for the legitimate forms the deletion drops | Removes the defect at the root; `equals` is provably additive within the attribute; matches the audit's "prefer `equals`" rule | Un-subsumes `rental`, which covers only `rental*`; the 373 prefix/suffix personas must be re-covered form by form, and the long tail (`rented studio apartment in central Stockholm`) cannot be enumerated as `equals` | **Candidate — measure** |
| **(b) Replace `rent` with longer `contains` tokens** — `rented`, `renting`, `renter`, `rents`, `private rented` (each ≥ 4 chars) | Keeps compound coverage for the open-ended tail; every token clears the 4-character floor | Still `contains`, so still capable of an accident (`renter` in nothing obvious, but the class of risk remains); needs the full gate; `rented` does not catch `rent-controlled` | **Candidate — measure** |
| **(c) Add `none_of` to Rental apartment** vetoing parent/family strings (`parent`, `föräldrahem`, `föräldrarnas`, `family home`) | Surgical: leaves all 373 legitimate matches untouched; `none_of` vetoes in every tier | Does not fix the class of defect, only this instance; a `none_of: 'parent'` also vetoes the genuinely ambiguous `Renting with parents` (4 personas); per §4 above, vetoed strings containing `house` fall through to **Owner-occupied**, replacing one over-mapping with another | **Candidate — measure** |
| **(d) Leave it; document the bias in the manuscript's limitations** | Zero risk to the clean pool; 8 combos already sit below N=100 | Knowingly ships a contaminated scored marginal with a model-correlated bias; the audit's own rule is that the mapping config is part of the measuring instrument | **Candidate — the null option, must be beaten on evidence** |
| **(e) Add word-boundary matching to the engine** (`\brent\b`) | Fixes the entire class in one place | Changes the semantics of all ~1,216 `contains` tokens in the tier at once — `hyres` in `hyresrätt`, `eget h` in `eget hus` and every Swedish compound would stop matching. Blast radius is orders of magnitude larger than the defect | **Rejected** |
| **(f) Add a "Living with parents" value to `housing_tenure`** | Would map all 74 personas correctly | **Forbidden.** The real population defines the category space; a synthetic-only value has no reference distribution, so TV distance against it is undefined | **Rejected — hard refusal** |

Options (a) and (b) are not mutually exclusive with (c); the Phase 3 measurement may show that
(a)+(c) dominates either alone. The decision gate compares whatever the measurement produces.

### Guardrails carried verbatim from `.claude/skills/audit-unmapped/SKILL.md` (Step 4)

These are binding on every phase of this plan:

- **Never add a new entry to an attribute's `values`.** The **real population defines the category
  space**. A synthetic-only value has no real counterpart, so a category invented for it has no
  reference distribution. Report the schema gap; never fill it.
- **Never add `on_miss` to a scored axis.** It fabricates the marginal that TV distance measures —
  every miss silently becomes a real-looking category and the score improves for no reason.
- **Prefer `equals`.** The engine's resolution is a global tiered sweep, so an added `equals` token
  is provably additive within its attribute, while an added `contains` token can steal values
  **from another attribute**.
- **Never add a `contains` token shorter than 4 characters.**
- **Any `contains` edit requires the full `regress.py` gate before it is applied**
  (`regressions == 0`, every re-routed pair reviewed by eye).
- **When a call is close, refuse.** A refusal costs one manual review. A wrong edit silently
  corrupts a benchmark and nothing downstream will ever flag it.
- **The mapping config is part of the measuring instrument.** Every rule added to absorb a model's
  free text makes a weak model look better without it having improved.
- **Inputs are immutable**: nothing under `01_Raw/`, `03_Analysis/` or `config/` is written by any
  audit script. Candidate configs are materialised in the scratchpad only.

### Architecture & Module Contracts

This is a **config-only** change to the measuring instrument; no Python module changes except the
new guard test. The contract table records who owns which decision.

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|---|---|---|---|
| `config/mapping/scb_native/housing_tenure.json` (`synthetic → Rental apartment`) | Declare which raw strings mean "rental tenure" | raw string → canonical value | Which model or method produced the string; how many personas a token rescues |
| `analysis/mapping/mapping_engine.py` | Resolve one raw value by the global tiered sweep | (raw, rules block, values) → value + miss flag | The tokens themselves; any attribute-specific semantics — **unchanged by this plan** |
| `.claude/skills/audit-unmapped/scripts/substring.py` | Price each `contains` token's false positives by single-token ablation | tier config + corpus → ranked flags | Whether a flag is a defect (that verdict is the reader's) |
| `.claude/skills/audit-unmapped/scripts/regress.py` | Two-arm re-map and diff: newly-resolved / regression / re-routed | candidate + baseline tier → per-persona diff | Whether a re-route is desirable |
| `tests/test_mapping_contains_floor.py` (new) | Fail if a `contains` token shorter than 4 chars is added to any tier file outside the frozen allowlist | tier config → pass/fail | Which token is "important"; any persona count |
| `analysis/population_cap/cap.py` → `_mapped/` | Materialise the capped clean set every downstream analysis reads | validity CSVs + mapped files → capped mirror | Why a persona is unmapped — **unchanged by this plan** |

The new guard test **freezes**, rather than fixes, the existing sub-4-character tokens: the tier
already declares `ägd` (3), `ägt` (3) under Owner-occupied and `it-` (3) under
`industry_sector → Information & Communication`. Each goes on an explicit, commented allowlist with
its own follow-up note; the test's purpose is to stop the set from growing, not to force a
same-session remediation of tokens this plan has not measured.

---

## Implementation Plan

Every command below runs in the **popsynth** environment:
`D:\Programming\anaconda3\envs\popsynth\python.exe`. `regress.py` and `substring.py` exceed the
120 s default and **must be backgrounded**; both print progress to stderr. Reports go to the
scratchpad or an explicit `--report` path; raw values are read with `Read`, never echoed to the
console (Windows cp1252 will raise mid-report on the Swedish, CJK and Arabic values present).
Use absolute paths — the shell working directory resets between calls.

### Phase 0: Provenance
**Goal:** Establish that every number this plan quotes was measured against the config now on disk.

- [ ] 0.1 — Run `selftest.py` (fixture-only, seconds). Stop and report if it fails.
- [ ] 0.2 — Run `inventory.py --report <scratch>/inventory.md`. Require verdict `fresh`, 0 stale
      artefacts, 0 combos with raw newer than mapped, 0 miss disagreements. Exit code 2 halts the
      plan.
- [ ] 0.3 — Run `regress.py` **with no `--candidate` and no `--override`** over all 50 combos
      (background). Both arms are identical by construction, so every count must be `0/0/0`.
      Anything else means the stored artefacts were not produced by the config on disk, and Phase 1
      cannot start.
- [ ] 0.4 — Record the resolution line each script prints, verbatim, in this plan. Every figure
      below is meaningless without the slice it was measured over.

**Files Modified:** none (read-only).
**Dependencies:** None.

### Phase 1: Measure the defect
**Goal:** Know exactly what `rent` does, to which personas, in which combos, produced by which
models — independently of `substring.py`'s own tally.

- [ ] 1.1 — Re-run `substring.py --attribute housing_tenure --report <scratch>/substring-pre.md`
      (background) and archive the report path in this plan.
- [ ] 1.2 — Classify all **303** raw values reaching Rental apartment through `rent` into: infix
      accident / legitimate rental compound / genuinely ambiguous. Read the report with `Read`.
      Reproduce the 62 / 241 form split and the 74 / 373 persona split from the per-value rows as
      an independent check on the summary line.
- [ ] 1.3 — Attribute the 74 infix personas to combo, model and method. A bias concentrated in one
      model is a different finding from one spread evenly — state which it is, with denominators.
- [ ] 1.4 — Compute the contamination share: for each combo's **capped** mapped population
      (`03_Analysis/population_cap/_mapped/{slug}.json`), the proportion of `Rental apartment`
      records that exist only because of this token. This is the number that reaches TV distance;
      the raw-pool figure is not.
- [ ] 1.5 — Confirm the language-correlation claim: count the Swedish `Föräldrahem` /
      `Boende hos föräldrar` forms sitting in the miss log (audit figure: 9 personas) against the
      English forms silently absorbed (74). State the asymmetry per model.
- [ ] 1.6 — Verify the subsumption relationship by ablation: delete `rental` alone in a scratchpad
      candidate and confirm `probe.py` reports no change; delete `rent` alone and record exactly
      which of the 241 prefix/suffix forms fall out.

**Files Modified:** none (read-only; candidate configs in the scratchpad only).
**Dependencies:** Phase 0.

### Phase 2: Triage the other 11 movers
**Goal:** Decide, once, whether `rent` is an isolated accident or the visible end of a pattern —
without widening this plan's remediation scope.

- [ ] 2.1 — For each of `bostadsrätt` (140), `hyres` (133), `ägar` (87), `eigen` (67), `owned`
      (61), `ägd` (54), `owner` (53), `eget h` (34), `mortgage` (33), `uthyr` (17), `villa` (13):
      read its infix rows and record a verdict — defect / legitimate compound / needs its own
      scope.
- [ ] 2.2 — Flag the sub-4-character tokens (`ägd`, `ägt`) explicitly: they violate the audit's own
      floor and are grandfathered, not endorsed.
- [ ] 2.3 — Record every verdict in this plan. Any second defect found is written up as a follow-up
      plan, **not** folded into this one — one subtractive change per gate keeps the measured delta
      attributable.
- [ ] 2.4 — Decide and record whether the whole-tier sweep (611 flagged tokens across ~1,216) is
      worth a dedicated plan, and at what priority.

**Files Modified:** none (read-only).
**Dependencies:** Phase 1.

### Phase 3: Evaluate the remedies
**Goal:** A decision table built from measured persona counts, not from judgement about strings.

- [ ] 3.1 — Materialise candidate configs (a), (b), (c) and any combination in the scratchpad —
      **never** under `config/`.
- [ ] 3.2 — `probe.py` each candidate against a fixed value list: the 12 named infix forms above,
      10 representative prefix/suffix forms, `Renting with parents`, `my parents' house`,
      `Föräldrahem`, `Bostadsrent`.
- [ ] 3.3 — `regress.py --override housing_tenure.json=<candidate>` over all 50 combos, per
      candidate (background). Record newly-resolved / regression / **re-routed** counts.
- [ ] 3.4 — Read **every** re-routed pair by eye. Pay specific attention to strings re-routed to
      **Owner-occupied** via `house` (design note §4) — those are a substitution of one
      over-mapping for another, not a fix.
- [ ] 3.5 — For each candidate, compute the resulting clean pool and the number of combos below
      N=100, via `project.py --target-n 100`.
- [ ] 3.6 — Assemble the decision table: personas made correct · personas moved to `__UNMAPPED__` ·
      personas re-routed to another wrong value · clean pool · combos below target.

**Files Modified:** none under version control (scratchpad candidates only).
**Dependencies:** Phase 2.

### Phase 4: Decision gate — STOP
**Goal:** The user chooses. This is not a technical decision and must not be taken unilaterally.

- [ ] 4.1 — Present the Phase 3 table with both outcomes stated in personas, not percentages:
      **correctness** (wrong-but-clean personas eliminated) versus **pool size** (clean personas
      lost, and whether any combo crosses below N=100 as a result).
- [ ] 4.2 — State plainly that the null option (d) is live: shipping the bias with a documented
      limitation is a legitimate choice, given 8 combos already sit below target.
- [ ] 4.3 — State plainly that no option maps the 74 personas correctly, because the category does
      not exist and may not be created.
- [ ] 4.4 — **Wait for an explicit, itemised go-ahead naming the chosen remedy.** A general
      "sounds good" is not approval to edit config.

**Files Modified:** none.
**Dependencies:** Phase 3.

### Phase 5: Apply the chosen remedy
**Goal:** One file, one matcher block, fully gated.

- [ ] 5.1 — Edit `config/mapping/scb_native/housing_tenure.json`, `synthetic → Rental apartment`
      only.
- [ ] 5.2 — `git diff` proof that `values` and the entire `real` block are byte-identical, and that
      the diff touches no other value's matcher.
- [ ] 5.3 — `regress.py` two-arm run over all 50 combos: **`regressions == 0`** (background).
- [ ] 5.4 — Every re-routed pair listed in this plan with a by-eye verdict.
- [ ] 5.5 — `substring.py --attribute housing_tenure` on the post-edit config: `rent` no longer
      flagged, no new token in the top 10.
- [ ] 5.6 — `rollup.py` before/after: every attribute other than `housing_tenure` unchanged.
- [ ] 5.7 — `ruff check src/` and `pytest`.

**Files Modified:**
- `config/mapping/scb_native/housing_tenure.json` — the `synthetic → Rental apartment` matcher
  block only.

**Dependencies:** Phase 4 (explicit approval).

### Phase 6: Re-map, re-validate, re-cap, re-measure
**Goal:** Make the artefacts and every published number consistent with the fixed instrument.

- [ ] 6.1 — Re-map all 50 combos. The bare `map_populations.py --force` maps only
      `comparison_targets.yaml`; use the axis single-target mode
      (`--model-id/--strategy-id/--country-id --force`) per combo, or the GUI analysis workflow,
      which fans `per_combo` from the registry.
- [ ] 6.2 — `validate_mapped_personas.py` for all 50 combos (requires explicit
      `--model-id/--strategy-id/--country-id`).
- [ ] 6.3 — `cap_populations.py` for all 50 combos: `population_cap` re-materialises both the
      persona mirror and `03_Analysis/population_cap/_mapped/`, which every mapped-file consumer
      reads via `analysis/utils/capped_source.resolve_mapped_dir`. **A stale `_mapped/` would leave
      downstream analyses reading the pre-fix populations with no error raised** — this step is not
      optional.
- [ ] 6.4 — Re-run the downstream consumers: `fidelity`, `multivariate_fidelity`, `model_ranking`,
      `method_significance`. `generation_metadata` reads the capped mirror's telemetry and must be
      re-run too if the cap selection changed.
- [ ] 6.5 — Record the measured deltas against Phase 3's prediction: clean pool, combos below
      N=100, `housing_tenure` TV similarity per combo, and any change in model or method rank
      order. A rank change caused by a *mapping* fix is a finding in its own right and must be
      reported, not absorbed.
- [ ] 6.6 — Re-run `inventory.py`: verdict must return to `fresh` with 0 disagreements.

**Files Modified:** no source files; regenerated artefacts under
`{output_base}/03_Analysis/{mapping,validate_mapped,population_cap,fidelity,…}/`.
**Dependencies:** Phase 5.

### Phase 7: Guard and document
**Goal:** Make the same class of defect fail loudly next time.

- [ ] 7.1 — Add `tests/test_mapping_contains_floor.py`: walk every `*.json` in each mapping tier and
      fail on any `contains` token shorter than 4 characters that is not on the frozen, commented
      allowlist (`ägd`, `ägt`, `it-`, plus whatever Phase 2 finds). Fail-fast on a malformed tier
      file rather than skipping it.
- [ ] 7.2 — Record the outcome in this plan's *Findings* section, including the Phase 2 verdicts on
      the other 11 tokens.
- [ ] 7.3 — Changelog entry naming the personas moved and the measured TV delta.
- [ ] 7.4 — If the manuscript quotes any `housing_tenure` figure, update it via the
      `sync-manuscript` skill; if it quotes none, state that explicitly so the check is not
      repeated.
- [ ] 7.5 — Update `docs/architecture/comparison-mapping.md` with a short "substring tokens" note
      pointing at the 4-character floor and the guard test.

**Files Modified:**
- `tests/test_mapping_contains_floor.py` — new.
- `docs/architecture/comparison-mapping.md` — substring-token note.
- `docs/changelogs/fix-rent-substring-overmapping.md` — new.

**Dependencies:** Phase 6.

---

## Testing Plan

### Unit Tests
- [ ] `housing_tenure.json` parses; `values` and the `real` block byte-identical to their pre-edit
      state (diff-verified).
- [ ] The edited file adds/removes only array elements — no key added, renamed or removed.
- [ ] New `test_mapping_contains_floor.py`: a sub-4-character `contains` token outside the
      allowlist fails; an allowlisted one passes; a malformed tier file raises.
- [ ] Existing `pytest` mapping suite passes unchanged — the engine is untouched, so a failure
      means a malformed JSON edit.

### Integration Tests
- [ ] `regress.py` two-arm over all 50 combos: `regressions == 0`.
- [ ] `regress.py` provenance null-check (no `--candidate`, no `--override`): `0/0/0`, before and
      after.
- [ ] `rollup.py` before/after: miss counts of every attribute other than `housing_tenure`
      unchanged.
- [ ] `substring.py` post-edit: `rent` absent from the flag list; no new entrant in the top 10.
- [ ] Full chain `mapping` → `validate_mapped` → `population_cap` completes for all 50 combos and
      `inventory.py` returns `fresh`.

### Manual Verification
- [ ] Every re-routed pair from `regress.py` read by eye and recorded with a verdict.
- [ ] Spot-check three personas in the capped mapped JSON whose `housing_tenure` changed, against
      their `01_Raw` `identity.json`.
- [ ] Confirm the 74 infix personas now carry `__UNMAPPED__` (or the chosen outcome), and that no
      persona that legitimately stated a rental lost its mapping.
- [ ] Confirm no `Rental apartment` marginal moved in a combo whose personas were untouched.

### Edge Cases
- [ ] `my parents' house` — contains both `rent` (infix) and `house`; already resolves to
      **Owner-occupied** by declared-value order. Confirm the remedy does not change it, and that
      it is recorded as a *separate* over-mapping.
- [ ] `Renting with parents` (4 personas) — genuinely ambiguous; a `none_of: 'parent'` veto would
      wrongly discard it. Record the verdict explicitly.
- [ ] `Bostadsrent`, `Kontractrent`, `Förent bostad med en annan person` — Swedish suffix noise;
      confirm the remedy drops them rather than silently keeping them via another token.
- [ ] `rented_apartment` — underscore normalises to space; confirm it still resolves.
- [ ] `rental` subsumption — after the edit, confirm by ablation that `rental` is now doing real
      work (non-zero personas via token alone) or is genuinely redundant.
- [ ] `Föräldrahem` / `Boende hos föräldrar` — must remain `__UNMAPPED__` under every remedy; if a
      candidate maps them, it has invented the missing category by the back door.
- [ ] A combo whose clean count sits exactly at 100 before the fix — confirm whether it drops below
      target, and name it in Phase 4's table.

---

## Documentation Plan

- [ ] Add changelog entry `docs/changelogs/fix-rent-substring-overmapping.md` with the personas
      moved and the measured TV delta.
- [ ] Update `docs/architecture/comparison-mapping.md` with the substring-token note (4-character
      floor, guard test, why `contains` is not word-bounded).
- [ ] Record the Phase 2 triage verdicts for the other 11 movers in this plan's *Findings* section,
      so the next audit does not re-litigate them.
- [ ] Cross-reference from `docs/development/plans/active/add-audited-mapping-tokens.md`
      (*Config defects*) to this plan, replacing its one-line record.
- [ ] Update the manuscript's `housing_tenure` figures and limitations paragraph via
      `sync-manuscript`, or state explicitly that none are quoted.
- [ ] No `CLAUDE.md` change expected — no architecture change. Confirm at Phase 7 rather than
      assuming.

---

## Rollback Plan

1. **Before re-mapping (Phases 0–5):** nothing to roll back. All measurement is read-only and every
   candidate config lives in the scratchpad. `git checkout -- config/mapping/scb_native/housing_tenure.json`
   restores the file.
2. **Data considerations:** there is no migration. Every artefact under `03_Analysis/` is derived
   and reproducible from `01_Raw/` plus the tier config, so a rollback is: revert the config commit,
   then re-run Phase 6's chain. `01_Raw/` is never written by any step of this plan.
3. **Rollback procedure:**
   - `git revert` the single config commit (and the guard-test commit if it blocks other work).
   - Re-run `mapping --force` → `validate_mapped` → `population_cap` for all 50 combos.
   - Re-run the downstream consumers listed in 6.4.
   - `inventory.py` must return `fresh` with 0 disagreements; `regress.py` null-check `0/0/0`.
   - Revert the manuscript figures if Phase 7.4 changed them.
4. **Partial-state hazard:** a revert of the config *without* re-running Phase 6 leaves
   `population_cap/_mapped/` describing the post-fix mapping while the config says otherwise.
   `inventory.py` detects exactly this (config newer than artefact) and will halt — do not
   override it.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The fix shrinks the clean pool and pushes a combo below N=100 | High | Medium | Phase 3 measures it per combo before any edit; Phase 4 puts the trade-off to the user with numbers; option (d) remains live |
| Removing `rent` silently drops legitimate rental forms (`rented`, `renting`) via the `rental` subsumption trap | High | High | Explicitly named in Definitions; Phase 1.6 ablates it; Phase 3.3 measures the fallout per candidate rather than assuming coverage |
| A remedy re-routes parent-strings to **Owner-occupied** via `house`, replacing one over-mapping with another | Medium | High | Design note §4; Phase 3.4 reads every re-routed pair by eye, with this pattern called out by name |
| Scope creep into the other 11 flagged tokens, or the 611 tier-wide flags | Medium | Medium | Out of Scope is explicit; Phase 2 is triage-only and any second defect becomes its own plan — one subtractive change per gate |
| Re-mapping is blocked by the entry points (`map_populations.py --force` maps only `comparison_targets.yaml`; validators require explicit axis ids) | Medium | Medium | Known and pre-recorded in task 6.1/6.2; the GUI analysis workflow fans `per_combo` from the registry as the fallback path |
| A stale `population_cap/_mapped/` leaves downstream analyses reading pre-fix data with no error | Medium | High | Task 6.3 is mandatory and non-optional; `resolve_mapped_dir` is fail-fast with no `mapping/` fallback; `inventory.py` re-run in 6.6 catches it |
| The fix changes model or method rank order | Low | High | Phase 6.5 records rank order before and after; a rank change caused by a mapping fix is reported as a finding, never absorbed silently |
| New personas are generated into the pool mid-plan, invalidating the measurement | Medium | Medium | Phase 0.2 gates on `inventory.py` `fresh`; re-run it before Phase 3's decision table and again at 6.6. The 2026-08-04 audit was measured on 9,036 personas and this one on 9,527 — the pool moves |
| `regress.py` / `substring.py` time out at the 120 s default and are silently truncated | High | Low | Both are backgrounded by instruction; a `--limit`ed run is explicitly **not** an acceptance gate |
| Raw values echoed to a cp1252 console kill a run mid-report | Medium | Low | All reports written to `--report` paths and read with `Read`; never `cat`, never console echo |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 0 — Provenance | ~20 min (`regress.py` null-check dominates, backgrounded) | None |
| Phase 1 — Measure the defect | ~1.5 h, mostly reading 303 values | Phase 0 |
| Phase 2 — Triage the other 11 movers | ~1 h | Phase 1 |
| Phase 3 — Evaluate the remedies | ~2 h (3–4 backgrounded `regress.py` runs over 50 combos) | Phase 2 |
| Phase 4 — Decision gate | user-bound | Phase 3 |
| Phase 5 — Apply + gate | ~1 h including the by-eye re-route review | Phase 4 |
| Phase 6 — Re-map / re-validate / re-cap / re-measure | ~1–2 h, dominated by the map + validate + cap runs | Phase 5 |
| Phase 7 — Guard and document | ~1 h | Phase 6 |

---

## References

- Audit skill and the Step 4 judgement criteria: `.claude/skills/audit-unmapped/SKILL.md`
- Audit scripts: `.claude/skills/audit-unmapped/scripts/{inventory,rollup,rank,extract,probe,regress,substring,project}.py`
- Related plan (supersedes its *Config defects* one-liner, does **not** duplicate its work):
  `docs/development/plans/active/add-audited-mapping-tokens.md`
- Category-space principle: `docs/real_mapper_philosophy.md`
- Mapping tiers and the two-stage map → compare flow: `docs/architecture/comparison-mapping.md`
- Hard-rule rationale: `docs/architecture/design-principles.md`
- Engine: `src/population_synthetic/analysis/mapping/mapping_engine.py`
- Config under change: `config/mapping/scb_native/housing_tenure.json`
- Pipeline-engineering guides: `~/.claude/knowledge/data-pipeline-engineering/` (03 §6, "Handling
  missing and partial data honestly")

---

## Findings

<!-- Filled in as the plan executes. Phase 2's verdicts on the other 11 movers, Phase 3's decision
     table, Phase 5's re-routed pairs with their by-eye verdicts, Phase 6's measured deltas. -->

_Not yet started._

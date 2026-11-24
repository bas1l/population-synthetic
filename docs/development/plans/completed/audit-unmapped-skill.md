# Plan: `audit-unmapped` — local skill automating the `__UNMAPPED__` triage workflow

**Date:** 2026-07-30
**Author:** Basil
**Status:** Completed
**Completed:** 2026-08-01
**Base Branch:** `dev`
**Branch:** `feature/audit-unmapped-skill`

---

## Scope correction, 2026-07-30 (governs everything below)

After Phase 5, the user corrected the scope of the skill:

> *"The goal of this skill is simply to have a half Python, half your task. Python is just supposed
> to extract the data in a quick manner, but all the decision has to be made by you when you get the
> data from Python. Basically Python is just giving you, from the analysis output folder, the list
> of the models where things are unmapped, and extract those from the generation."*

**Python extracts and aggregates. The judgement happens in conversation.** Judgement encoded in
Python — the five-class taxonomy, the risk-flag heuristics, the auto-proposal gate — is precisely
what was rejected, and Phase 3's own amendment note had already shown why: the gate over-proposed
`Götaland` → `Gotland` at 0.93 similarity and could not derive one of the four edits a human
actually approved. String distance does not know what a word means.

**What this withdrew** (each is annotated in place below, never silently deleted):

- `classify.py` and `parity.py` are **deleted**, with their `fixtures/parity/` and their selftest
  checks. Goals 1 (the taxonomy clause) and 2 (the auto-proposal gate) are withdrawn; the success
  criteria resting on them are struck below.
- `rank.py` was reworked to consume `MissRecord` + `ValidityRow` directly. Sole-cause attribution
  is arithmetic and needs no taxonomy; the class tag it used to carry is gone.
- Three helpers moved to `_common.py` because they are **extraction, not judgement**, and other
  stages need them: `config_tokens` / `ConfigToken` (what the config declares), `load_rules` (which
  attributes have a matcher block), and `cross_attribute_collisions` (mechanical containment over
  the fold, formerly `parity._cross_attribute_collisions`). `_common.fold` was already shared and
  stays.
- **`llm_pool.py` (Goal 5) is deferred out of scope** by the same correction. It is a diagnostic
  over the candidate pool, not an extraction of the offending values; nothing in the corrected
  skill needs it. Not built, not stubbed.

**What this added:** `extract.py` — the piece the correction actually asks for. For every combo with
unmapped values it dumps the offending raw strings, grouped by attribute (ordered by personas
recovered), each with its instance count, combo count, sole-cause persona count and whether it was
`__UNMAPPED__` or `on_miss`-masked, **printed beside that attribute's existing config tokens**. It
renders and counts; it classifies, scores and proposes nothing.

**Where the judgement went:** into `SKILL.md`, as guidance for a reader rather than an algorithm —
the legitimate/config-miss distinction, the parity test with its precedent-token requirement, the
benchmark-integrity constraint, the hard refusals, the worked examples with their verdicts, the
substring trap, and the approval protocol.

## Scope amendment, 2026-08-01 — the audit's findings required tracked changes

The 2026-07-30 rescope asserted that **"no tracked repo file is modified except this plan
document."** That is no longer true, and the assertion was wrong in principle: the skill's default
path reads artefacts the repo did not yet produce.

**Three tracked changes are load-bearing for the skill itself, not optional fixes:**

- **(a) Miss observability in the engine.** `mapping_engine.resolve_detailed() -> (value, missed)`,
  with `resolve()` retained as a thin shim over it. The plan's own definition of **miss** is
  "`resolve_detailed()` returned `missed=True`"; without that return there is no miss to record.
- **(b) The miss sidecar.** `BaseSyntheticMapper.misses` accumulation, plus
  `loader.map_population(..., misses_out=...)` and the `03_Analysis/mapping/{slug}.misses.csv`
  sidecar written by `map_populations.py`. The plan names that file and its exact column tuple
  `persona_id, attribute, raw_value, mapped_to, masked_by_on_miss` as the skill's **primary input**.
- **(c) Deprecated-attribute resolution.** `deprecated_attributes_for_country()` shared into
  `analysis/utils/country_config.py` and wired into `validate_mapped`. The plan requires it in so
  many words — *"and are excluded, or the audit reports phantom gaps"*.

**A fourth group ships alongside as the audit's first substantive finding acted upon:** the four
`on_miss` sinks removed from both Swedish tiers (`scb` + `scb_native` × `income_source` → "Wage /
Business", `industry_sector` → "Other"), which this plan quantified at 729 masked misses.
`config/mapping/scb_native/industry_sector.json` correspondingly drops `"Other"` from `values`
(13 → 12 producible) as it was reachable only through the deleted sink, and ~591 lines of
compensating matcher tokens across 15 `scb_native` files absorb that mass honestly, per the parity
test. Italy deliberately retains its `on_miss`.

**Still out of scope, and NOT in this change:**

- The `"rent"` ⊂ `"parents"` substring defect. Still live in both `housing_tenure.json` tiers,
  unguarded by `none_of`. The audit surfaces it; the fix is its own change.
- The `loader.map_population` `mappings_path` asymmetry. Still unpatched, still worked around in
  skill-local code.

The skill directory `.claude/skills/audit-unmapped/` remains **gitignored** by the 2026-07-30
decision, so `SKILL.md` and the ten scripts are not in this change.

---

## Overview

Add a local Claude Code skill at `.claude/skills/audit-unmapped/` that automates the manual
`__UNMAPPED__` triage loop performed by hand on 2026-07-29/30: read the mapping stage's miss log,
decide per value whether the miss is **legitimate** (no canonical category, wrong axis answered,
free-text noise) or a **config miss** (a spelling/inflection/translation variant of a rule the
config already commits to), rank candidate config edits by *personas recovered*, verify any accepted
edit by re-mapping and diffing, and project how many personas each combo must generate to reach
N=100 valid. The audit logic lives as skill-local Python under the skill directory; `SKILL.md`
orchestrates it and carries the decision criteria the scripts cannot encode.

*(Rescoped 2026-07-30 — see the scope correction above. "The decision criteria the scripts cannot
encode" turned out to be **all** of them: the scripts extract and count, and every judgement is
made in conversation against `SKILL.md`'s criteria.)*

## Problem Statement

The triage was done twice by hand (transcripts `014de28b`, `eca9c71d`), each time re-deriving the
same one-off scripts from scratch: aggregating `unmapped_fields`, joining back to raw
`identity.json`, re-resolving values against the current config, probing candidate fixes,
re-mapping 5,250 personas to check for regressions, and computing N-to-100. That is roughly a day
of work per pass, and it is fragile in specific, repeatable ways:

- **Stale results are found by accident.** Six mapping configs had been edited ~7 h *after* the map
  run that produced the on-disk results being analysed; 1,844 recorded misses were re-tested and
  only 29 (1.6 %) would still miss under the then-current config. The user's verdict: *"it should be
  automatic, not something I stumble onto."*
- **Reading 326 distinct strings by hand** is the only way currently to separate "model answered a
  different question" from "model produced noise".
- **Fix candidates are ranked by instances, not by personas recovered**, so effort goes to the wrong
  attribute — an attribute with 690 misses spread over personas that fail on 3 other attributes too
  recovers nobody.
- **A whole class of miss is invisible.** Attributes declaring `on_miss` never emit the sentinel, so
  `validate_mapped` cannot see them: 729 misses were absorbed into real-looking categories
  (`industry_sector` → `Other` ×365, `income_source` → `Wage / Business` ×364) versus 2,580 left as
  `__UNMAPPED__`.
- **Over-broad `contains` tokens silently fabricate data and nothing checks for them.** The bare
  token `"rent"` in `Rental apartment.contains` matches **pa-rent-s**, mis-mapping 131 personas
  (`'Living with parents'` ×61, `'Parental Home'` ×12, …). It was found by accident.
- **Benchmark integrity is at stake in the fix decision itself.** Every rule added to absorb a
  model's free text makes a weak model look better without it having improved. The accept criterion
  the user landed on is narrow and must be enforced, not re-litigated each pass.

## Goals

### In Scope

1. A **read-only diagnose pass**: coverage/staleness pre-flight, per-attribute miss rollup (total /
   distinct / singleton / `on_miss`-masked), model × strategy attribution, ~~taxonomy classification
   including automated wrong-axis detection,~~ *(withdrawn 2026-07-30 — see the scope correction)*
   and a fix list ranked by **personas recovered**.
2. ~~An **auto-proposal gate implementing the parity test**: a candidate edit is proposed only when
   it is a spelling / inflection / diacritic / translation variant of a token the config *already*
   commits to for that same target value, and the justifying precedent token is printed alongside.
   Everything else is routed to a "requires a human decision" list and never auto-proposed.~~
   **Withdrawn 2026-07-30.** The parity test survives verbatim, as *guidance in `SKILL.md`* applied
   in conversation; no script implements it.
2a. **(added 2026-07-30)** An **extraction pass**: for every combo with unmapped values, dump the
   offending raw strings grouped by attribute (ordered by personas recovered), each with its
   instance / combo / sole-cause counts and its `__UNMAPPED__`-vs-masked outcome, printed beside
   that attribute's declared `values` and their current `equals` / `all_of` / `contains` /
   `none_of` tokens. Renders and counts; classifies nothing.
3. A **verification harness**: A/B probe of a candidate config directory, full re-map + diff
   regression gate (`newly_resolved` / `regressions` / `re_routed`), and a data-driven
   `contains`-token false-positive auditor. *(Off the default path — run only to check a judgement
   already made.)*
4. A **projection**: personas needed per combo to reach N=100 valid, from the *intersection* of the
   two validity gates, with a one-sided Wilson lower bound; plus post-fix re-projection without
   re-running the pipeline. *(Off the default path.)*
5. ~~**Opt-in LLM candidate-pool diagnostics** (`--llm-diagnostics`), off by default: per-category
   fraction of enumerated candidates that are unmappable, weight mass on them, and
   P(top-weighted candidate unmappable), from `llm_interactions.jsonl`.~~
   **Deferred out of scope 2026-07-30.** Not built.
6. `SKILL.md` carrying the decision criteria, the approval protocol, and the operational pitfalls
   (UTF-8, cwd resets, background execution). **This is now the substance of the skill, not its
   wrapper.**

### Out of Scope

- **Writing any config edit autonomously.** The skill proposes; the user names which to take; only
  then are edits applied. (Standing rule; it is also how both prior sessions ran.)
- **Adding entries to an attribute's `values` set.** The real population defines the category space
  (`docs/real_mapper_philosophy.md`); a synthetic-only value must remain unmapped. Schema gaps are
  *reported*, never auto-proposed.
- **Proposing `on_miss` on a scored axis** — it fabricates the marginal that TV-distance measures.
- Registering a `mapping_audit` process in `config/analysis/analysis_registry.yaml`, adding a GUI
  task, or writing into `03_Analysis/`. Decided against: this is an investigation tool, not a DAG
  stage. (Revisit only if the audit becomes a per-run artefact.)
- Fixing the defects the audit finds (including the `"rent"` substring bug) — the audit surfaces
  them; each fix is its own change.
- Re-running `map_populations.py` / `validate_mapped_personas.py`. The skill *prints* the commands
  and reads their outputs.
- ~~Modifying any `src/` module.~~ The one asymmetry found (`loader.map_population` ignores
  `mappings_path`) is worked around in skill-local code, not patched here.
  **Amended 2026-08-01** — the `mappings_path` asymmetry is indeed still unpatched and still worked
  around in skill-local code, but `src/` modules **were** modified: `resolve_detailed()`,
  `BaseSyntheticMapper.misses` + `misses_out=`, and `deprecated_attributes_for_country()`. All three
  are prerequisites for the skill's primary input, not incidental fixes; see *Scope amendment,
  2026-08-01*.

## Success Criteria

- [x] `/audit-unmapped swedish_02` completes the default pass (`inventory` → `rollup`/`rank` →
      `extract`) on the Sweden dataset and emits UTF-8 report files plus a conversation summary,
      with **no** manual scripting.
- [x] The staleness check fires automatically and refuses to report conclusions when any
      `config/mapping/{tier}/*.json` mtime is newer than the `mapping/{slug}.json` it is judging;
      it names the offending files and the re-map command.
- [x] **(added 2026-07-30)** The staleness check *also* halts when a `persona_*/identity.json` is
      newer than the `{slug}.json` / `{slug}.misses.csv` built from it, and reports — without
      halting — the weaker case where only combo bookkeeping (`logs/`, `run_metadata.json`) is
      newer. On the live dataset this turns a false `fresh` into a halt naming 3 genuinely
      regenerated combos, with 12 more reported as merely touched.
- [x] The rollup reproduces the hand-computed 2026-07-30 figures on the same inputs
      (`socioeconomic_class 375`, `employment_type 345`, `housing_tenure 292`, `region 244`, …;
      729 `on_miss`-masked). Over the current 61-combo pool the totals are 3,169 counted misses,
      2,440 unmapped vs 729 masked, `parental_structure` at 663.
- [ ] ~~Wrong-axis detection labels `'Senior Nurse'` in `employment_status` and `'Arbetslös'` in
      `socioeconomic_class` with the attribute that *does* resolve them, and marks `equals`-tier
      hits high-confidence vs `contains`-tier hits low-confidence.~~
      **Withdrawn 2026-07-30 (scope correction).** Wrong-axis detection was a `classify.py`
      predicate; the distinction survives as a reader's criterion in `SKILL.md` §4a, illustrated
      with those two exact values.
- [x] The ranked fix list is ordered by personas recovered (sole-cause), and every row carries its
      denominator.
- [ ] ~~**(amended 2026-07-30 — see the Phase 3 amendment note; the original wording is quoted
      there)** On a fixture replaying the mapping config as it stood *before* 2026-07-29, the
      parity gate **auto-proposes only fold-equal candidates** — one, `Hyresratt`, citing the
      existing `Hyresrätt` by name — and:
      the four edits the user approved that day appear in the **review queue**, never as proposals,
      each with its nearest config tokens and the risk flag naming the kind of judgement it needs;
      `Götaland`, `College diploma`, `Åland` and `divorced parents (shared custody)` are never
      proposed and each carries the flag that explains why.~~
      **Withdrawn 2026-07-30 (scope correction).** `parity.py` and `fixtures/parity/` are deleted.
      All eleven of those values now appear in `SKILL.md` §4e as worked examples **with their
      verdicts**, which is where the calibration belongs: the gate could derive none of the four
      accepted edits and would have proposed `Götaland`.
- [ ] The regression gate reproduces `personas re-mapped: 5250 / NEWLY RESOLVED: 49 / REGRESSIONS: 0
      / RE-ROUTED: 0` against the config state at commit of those four edits.
      **Blocked 2026-08-01:** requires the 35-combo pool at the git config state of those four
      edits. The pool is now 65 combos and the mapping config has since diverged, so the figure is
      not reproducible. The fixture-level gate **is** fully asserted (`check_regress_null_run`,
      `check_regress_additive_edit`, `check_regress_regression_gate`,
      `check_regress_provenance_detects_a_stale_baseline`).
- [ ] The substring auditor independently rediscovers the `"rent"` ⊂ `"parents"` defect ~~and
      quantifies it at \~131 personas~~, without being told which token to look at.
      **Struck 2026-08-01** (the reproduction claim only) — the *rediscovery* is done and ticked
      under Manual Verification: ranked **#1 of 611 flagged tokens**, fixture-asserted by
      `check_substring_rediscovers_the_rent_defect`. The count is deliberately not claimed to
      reproduce: 570 personas map through the token alone and 79 on an infix match, over a 61-combo
      corpus with stricter attribution — as this plan itself records.
- [ ] ~~The projection reproduces "12 of 35 combos under 100; +3,413 at point estimate, +5,636 at the
      Wilson bound"~~, and its interval is within `1e-9` of
      `statsmodels.stats.proportion.proportion_confint(method='wilson')` on fixtures.
      **Struck 2026-08-01** (the reproduction clause only) — see the Phase 5 "Finding, 2026-07-30":
      `12 of 35` and `+3,413` reproduce exactly, the contract's one-sided bound gives **+5,233**, and
      `+5,636` only reproduces at `--confidence 0.975` over the 12 under-target combos. The
      statsmodels-within-`1e-9` half stands and is covered by `check_wilson_matches_the_authority`.
- [x] **(added 2026-07-30)** `extract.py` dumps, per attribute in personas-recovered order, every
      distinct offending raw value with its instance / combo / sole-cause counts and its
      `__UNMAPPED__`-vs-`on_miss` outcome, **beside** that attribute's declared `values` and their
      current tokens; truncates at `--limit-values` and states the dropped count and dropped mass;
      falls back to `validate_mapped × 01_Raw` per combo and warns loudly that the fallback is blind
      to masked misses. It contains no classifier, no score and no proposal.
- [x] `python .claude/skills/audit-unmapped/scripts/selftest.py` passes with **no** access to the
      OneDrive data root (fixtures only) and completes in under 30 s.
      Current tally: `78/78 checks, 1130 assertions, 0 failure(s)`.
- [x] `ruff check` is clean on the skill scripts; the repo suite (`pytest`) passes at
      **1138 passed**; ~~the repo suite (`pytest`) is unaffected — no tracked repo file is modified
      by this branch outside this plan document.~~
      **Amended 2026-08-01** — tracked files *are* modified; see *Scope amendment, 2026-08-01*.

## Definitions

Terms whose meaning the plan's correctness depends on. These are the contract the implementation is
reviewed against.

- **miss** — a `(persona, attribute)` pair for which `resolve_detailed()` returned `missed=True`
  (primary walk *and* the optional `refine_from` walk both failed). Not the same as "the mapped
  value is `__UNMAPPED__`": an attribute declaring `on_miss` produces a real-looking value on a miss.
  One row of `03_Analysis/mapping/{slug}.misses.csv`.
- **unmapped** — the mapped output value satisfies
  `analysis.utils.mapping_sentinel.is_unmapped(value)`, i.e. it is `"__UNMAPPED__"` **or legacy
  `None`**. Always test with that predicate, never `== "__UNMAPPED__"`.
- **masked miss** — a miss where `masked_by_on_miss == True`; invisible to `validate_mapped`.
- **legitimate unmapped** — a miss that must not be fixed in the mapping config. Exactly four
  sub-classes: (A) *wrong axis* — the value resolves under another attribute's ruleset; (B) *free
  text / sentence* — not a category; (C) *noise* — coined non-word, decoder degeneration, or language
  drift; (E) *schema gap* — a real, correctly-spelled concept with no canonical category, where the
  real population emits no such category either.
- **config miss** — class (D): the value is a spelling, inflection, diacritic, casing, or
  translation variant of a token the attribute's config **already** lists for one specific target
  value. This is the *only* class eligible for auto-proposal.
- **parity test** — the accept criterion for an auto-proposal, quoted from the source session:
  *"all are spelling/language parity with rules the config already commits to, not new mapping
  policy… inconsistencies within rules you've already written, not new tolerance."* Operationally: a
  proposal is emitted only if a **precedent token** can be named — an existing token in the same
  target value's matcher block that the candidate is a variant of. No precedent ⇒ no proposal.
- **precedent token** — the specific existing config token cited as justification, printed with every
  proposal (e.g. `"studentbostad"` justifies `"dormitory"`; `gästrikland→Gävleborg` justifies
  `Hälsingland→Gävleborg`).
- **sole cause** — an attribute is the sole cause for a persona when that persona's
  `unmapped_fields` list has length 1 and contains it. **Personas recovered** by a fix = the count of
  personas for which the fixed attribute is the sole cause. This, not instance count, is the ranking
  key.
- **clean pool** — `validate_raw.passed ∩ validate_mapped.passed` for a combo, keyed on `persona_id`
  (the source `persona_XXXXX` dir name). This is what `population_cap` draws from, so it is the
  correct base for the projection — *not* the mapped pass rate alone.
- **stale** — an artefact under `03_Analysis/` whose mtime predates any file in the mapping config
  tier it was produced with. A stale artefact invalidates every conclusion drawn from it.
- **regression / re-routed / newly-resolved** — the three outcomes of diffing a re-map against the
  stored mapped JSON, per `(persona, attribute)`: *newly resolved* = was unmapped, now a value;
  *regression* = was a value, now unmapped; *re-routed* = was value X, now value Y ≠ X. Acceptance
  gate: `regressions == 0` **and** every re-routed pair explicitly reviewed.
- **combo / slug** — one `{country}_{strategy}_{model}` cell, e.g.
  `swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`. Decomposed with
  `analysis.utils.axes.decompose_slug` (naive `_`-splitting is wrong: both strategy and model ids
  contain underscores).

---

## Technical Design

### System classification

Per `~/.claude/knowledge/data-pipeline-engineering/01-system-classification.md`: a **batch**,
**ETL**, **pipe-and-filter**, **analytics/reporting** tool with a **two-level (per-combo /
cross-combo)** structure. Inputs are bounded and already on disk; there is no orchestration, no
watermarking, no incremental state. The dominant quality bar is **statistical validity and
reproducibility**, not throughput — which is what justifies spending the effort on the staleness
gate, the regression gate, and known-answer fixtures rather than on speed.

### Approach

`SKILL.md` drives a set of small, single-purpose Python scripts under the skill directory. Each
script is an independently callable stage over serializable records; `SKILL.md` supplies the parts
that are judgement rather than computation — the taxonomy, the parity test, the approval protocol,
and the benchmark-integrity constraint.

The split matters: the scripts must **never** decide to edit a config. They emit two lists — *parity
proposals* (each with its precedent token) and *requires-a-decision* — and the skill presents both
for explicit, itemised approval, exactly as the source sessions ran (*"what are the four above you
are mentioning?"* → *"apply these four"*).

Primary input is `03_Analysis/mapping/{slug}.misses.csv` (`persona_id, attribute, raw_value,
mapped_to, masked_by_on_miss`), which is the only artefact carrying the **raw offending string**.
When it is absent, the scripts fall back to reconstructing the join from
`validate_mapped/{slug}.csv` × `01_Raw/{slug}/{persona_id}/identity.json` — and must print a loud
warning that the fallback is **blind to `on_miss`-masked misses** (729 of 3,309 in the reference
dataset).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Skill-local Python scripts** (`.claude/skills/audit-unmapped/scripts/`) | Self-contained; no repo surface; iterate freely; the skill is portable as one directory | Not covered by repo `pytest`; departs from the two existing single-file skills; duplicates a `01_Raw` literal | **Chosen** (user decision) |
| Repo `tools/mapping_audit/` + thin skill | Versioned, importable, unit-testable under `pytest` | Adds repo surface for an investigation tool; needs tests, docs and review for code that may be used a handful of times | Rejected |
| Registered `mapping_audit` analysis process | GUI-dispatchable; `03_Analysis/mapping_audit/` outputs; canonical id | Far heavier; mixes an ad-hoc, judgement-driven audit into a validation-gate DAG whose stages are atomistic and non-destructive | Rejected |
| Inline `python -c` in `SKILL.md` (the `audit-population` / `sync-manuscript` precedent) | Matches existing skills exactly; single file | The re-map regression and the parity gate are hundreds of lines; heredocs are unreviewable and untestable | Rejected — documented departure |
| Trust the recorded `mapped_to` in `misses.csv` | Fast; no imports | Cannot detect stale results — the exact failure mode that wasted a whole pass | Rejected: always re-resolve |
| Rank fixes by miss instance count | Trivial | Ranks attributes nobody is blocked on; 690 instances recovered fewer personas than 244 did | Rejected: rank by sole-cause |
| Point-estimate `ceil(100/p̂)` only | Simple | Understates N systematically at n=150; the user asked for the safe bound | Rejected: report both |

### Architecture & Module Contracts

One-way dependency flow: `_common` (I/O + contracts) → per-stage computation → reporting. No stage
imports another stage. Config is loaded once at the edge and passed **as a value** — that is what
makes A/B-ing a candidate config directory possible at all.

*(Final shape, 2026-07-30, after the scope correction. `classify.py`, `parity.py` and `llm_pool.py`
are gone; their rows are struck rather than removed so the change is auditable.)*

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `_common.py` | Resolve roots, load/normalize the four artefact formats into frozen dataclasses, decompose slugs, resolve a mapping tier, write UTF-8 reports; **plus the three extraction helpers every stage shares**: `config_tokens`/`ConfigToken`, `load_rules`, `cross_attribute_collisions`, and the canonical `fold` | `output_base`, `country` → `list[MissRecord]`, `list[ValidityRow]`, `dict[slug, MappedPop]`, `dict[attr, AttributeRules]` | ranking, statistics, what a "fix" is, what a value *means* |
| `inventory.py` | Pre-flight: which combos exist in `01_Raw` vs each analysis stage; broken runs; **three** provenance checks — config-vs-artefact mtimes, raw-vs-artefact mtimes (persona payloads halt, combo bookkeeping is informational), miss re-resolution | roots → `CoverageReport`, `StalenessReport` | miss semantics, config matcher schema |
| `rollup.py` | Per-attribute totals: misses, distinct, singletons, repeat ratio, `on_miss`-masked share; sliced by model and by strategy. Owns `rate()` / `format_rate()`, the shared precision discipline | `list[MissRecord]` → `list[AttrMissStats]` | why a value missed; whether it is fixable |
| ~~`classify.py`~~ | ~~Taxonomy + wrong-axis detection~~ **Deleted 2026-07-30 (scope correction).** Criteria moved to `SKILL.md` §4a; `config_tokens` / `load_rules` moved to `_common.py` | — | — |
| `rank.py` | Sole-cause attribution → personas recovered, per attribute and per distinct value; carry denominators. **Pure arithmetic over `MissRecord` + `ValidityRow`** — no class tag, no taxonomy import | `list[MissRecord]`, `list[ValidityRow]` → `RankReport` | what a value is; how config is stored |
| `extract.py` **(new)** | For every combo with unmapped values: dump the offending raw strings grouped by attribute (personas-recovered order), each with instance / combo / sole-cause counts and its `__UNMAPPED__`-vs-`on_miss` outcome, **beside** that attribute's declared `values` and current tokens; `--limit-values` with an explicit dropped count; per-combo fallback to `validate_mapped × 01_Raw` with a loud blind-spot warning | roots, tier, slugs → one UTF-8 report | classification, similarity, scoring, proposals — it renders and counts |
| ~~`parity.py`~~ | ~~The parity gate: fold-equal auto-proposal + ranked review queue with risk flags~~ **Deleted 2026-07-30 (scope correction).** The parity test survives verbatim in `SKILL.md` §4b; `_cross_attribute_collisions` moved to `_common.cross_attribute_collisions` | — | — |
| `probe.py` *(optional)* | Resolve an explicit value list through a mapper built on an **arbitrary** config dir; before/after table | `values`, `mappings_path` → `list[ProbeOutcome]` | where the values came from |
| `regress.py` *(optional)* | Two-arm re-map of the selected combos under a candidate config, diffed against the stored mapped JSON; also the provenance null-check | `slugs`, `mappings_path` → `RegressionDiff` | why the config changed |
| `substring.py` *(optional)* | Data-driven `contains`-token false-positive audit: tokens matching as a substring but not as a word across the observed corpus, quantified in personas by ablation | `mappings: dict`, corpus → `list[SuspectToken]` | the ranking, what a token *should* match |
| `project.py` *(optional)* | Clean-pool pass rate → personas needed for target N; one-sided Wilson lower bound; pre/post-fix | `list[ValidityRow]` (both gates), target `N` → `list[Projection]` | misses, config |
| ~~`llm_pool.py`~~ | ~~Opt-in candidate-pool diagnostics from `llm_interactions.jsonl`~~ **Deferred out of scope 2026-07-30.** Not built | — | — |
| `selftest.py` | Run every pure function against `fixtures/`; assert known answers | `fixtures/` → exit code | the real data root |
| `SKILL.md` | Orchestration **and the judgement**: the legitimate/config-miss distinction, the parity test, benchmark integrity, the hard refusals, the worked examples with verdicts, the substring trap, the approval protocol | `$ARGUMENTS` → conversation | how any statistic is computed |

```
.claude/skills/audit-unmapped/          # gitignored: local-only, by decision
├── SKILL.md
├── scripts/
│   ├── _common.py  inventory.py  rollup.py  rank.py  extract.py     # default path
│   ├── probe.py    regress.py    substring.py  project.py           # optional tools
│   └── selftest.py
└── fixtures/            # tiny synthetic artefacts; no real data, no PII
    ├── mapping/{slug}.misses.csv, {slug}.json
    ├── validate_raw/{slug}.csv, validate_mapped/{slug}.csv
    ├── 01_Raw/{slug}/persona_0000{0,1}/identity.json
    ├── config_mapping/{_index,region,housing_tenure,civil_status,education}.json
    ├── diagnose/       # the rollup / rank / extract slice, with its own tier
    ├── project/        # the clean-pool + Wilson slice
    ├── verify/         # the probe / regress / substring slice (the "rent" corpus)
    └── malformed/      # boundary-validation fixtures
```

**Key API facts the design depends on** (verified against current source):

- `get_synthetic_mapper(country, mappings_path=Path(...))` already accepts an arbitrary config
  directory — **no `src/` change is needed** to A/B a candidate config.
- **Trap:** `synthetic_mapper.loader.map_population(raw_pop, country=...)` has **no**
  `mappings_path` parameter and hardcodes the default directory. `regress.py` and `probe.py` must
  build the mapper themselves and loop `map_individual`, or they will silently score the production
  config.
- `BaseSyntheticMapper.misses` accumulates and is never reset → **one fresh mapper per arm**.
- `load_mappings` requires a *complete* mapping directory (globs `*.json`, needs `_index`), so an
  A/B copies the whole tier dir and edits one file. `probe.py`/`regress.py` will materialise the
  candidate dir in the scratchpad, never in `config/`.
- `age.json` matchers are **not** consumed by `map_individual` (`age_group` is special-cased to an
  int passthrough); editing them has no mapping effect.
- Resolution is a **global tiered sweep** (`equals → all_of → contains → numeric`, `none_of` as a
  cross-tier veto), so an added `equals` is provably additive, while an added `contains` can steal
  values across attributes ⇒ `contains` proposals always require the full `regress.py` gate.
- Paths: `resolve_output_base(None)` + `analysis_output_dir("mapping"|"validate_mapped"|
  "validate_raw", base)`. `01_Raw` has **no** shared constant in the package (it is a private literal
  in three scripts); `_common.py` declares it **once** and the plan accepts that as a documented
  fourth copy rather than adding repo surface.
- Mapping tier is read from the country axis YAML via `mappings_for_country(country_id)` — never
  hardcode `scb_native`. Deprecated attributes come from
  `deprecated_attributes_for_country(country_id)` (Sweden: `birth_location`) and are excluded, or
  the audit reports phantom gaps.
- `misses.csv` is only refreshed on the re-map branch — if `{slug}.json` exists and `--force` was not
  passed, it is not rewritten. The staleness gate must therefore compare mtimes of the
  **`.misses.csv`** as well as the mapped JSON.

### Statistical contract (`project.py`)

- **Wilson score interval, one-sided 95 % lower bound, no continuity correction** — stated in code,
  in the report header, and in the docstring. A one-sided 95 % bound and the lower limb of a
  two-sided 95 % interval are different numbers; the choice is fixed and labelled.
- Justification for an interval over a point rate is the guide's own rule
  (`03-statistical-and-scientific-software.md` §4): *"prefer interval estimates over point rates when
  N is tiny"*. Both are reported side by side.
- **Denominators travel everywhere.** No bare proportion is ever stored or printed.
- Degenerate inputs guarded explicitly and reported with a reason, never `NaN`: `n=0`, `k=0`, `k=n`,
  `n=1`.
- Cross-checked against `statsmodels.stats.proportion.proportion_confint(..., method='wilson')` in
  `selftest.py` **when statsmodels is importable**; otherwise against pinned fixture values, so the
  skill takes no hard dependency.
- **The base is the clean pool** (`validate_raw.passed ∩ validate_mapped.passed`), not the mapped
  pass rate. The prior pass got away with the latter only because raw was ~100 % on that dataset;
  `docs/development/persona-data-quality-observations.md` records combos where raw attrition is the
  dominant term (`all_generate_evaluate_random_pick`: 120/500 persona dirs with `identity.json`).
- The report states plainly that **N=100 is an operational target, not a statistical one** —
  `docs/scb_sweden_category_power_analysis.md` puts the χ²-GOF validity floor near 1,000 and a sound
  working target near 3,000.
- The ranking is **exploratory and uncorrected**; selecting the top fix out of K candidates scored on
  the same data is a winner's-curse problem, and `regress.py` is the stated defence.
- **"Zero" ≠ "absent"**: an attribute with no misses and an attribute whose column was missing are
  distinct outcomes with distinct markers.

### Contracts, purity, provenance

- Frozen dataclasses for every intermediate; boundary validation with fail-fast on a missing column
  or malformed row, naming file **and** row — no `.get()` defaults leaking `None` into a count.
- Every input artefact is **immutable**; the scripts never write into `01_Raw/` or `03_Analysis/`.
  All output goes to the scratchpad or a user-named path, overwritten (never appended) so re-runs are
  idempotent.
- A `run_metadata.json` beside each report: artefact paths read, config tier + a hash of its files,
  `output_base`, Python/library versions, timestamp, and the target N. Without the config hash a
  report cannot be trusted six hours later — which is the precise failure this skill exists to
  prevent.
- The staleness check is framed as an **idempotency assertion over the upstream pipeline**: re-run
  the matcher over the recorded misses; if it disagrees with `mapped_to`, that is a provenance
  failure and the skill halts with the offending artefacts named, rather than silently preferring
  either answer.

---

## Implementation Plan

### Phase 1: Foundation — contracts, I/O, pre-flight
**Goal:** Everything downstream can load real data and refuses to reason about stale data.

**Started:** 2026-07-30
**Completed:** 2026-07-30

- [x] 1.1 Scaffold `.claude/skills/audit-unmapped/` with `scripts/` and `fixtures/`
- [x] 1.2 `_common.py`: root resolution (`resolve_output_base` + `analysis_output_dir`, single
      `_RAW_STAGE_DIR` literal), frozen dataclasses (`MissRecord`, `ValidityRow`, `MappedPersona`),
      loaders for the four artefact formats with boundary validation, slug decomposition via
      `axes.decompose_slug`, and a UTF-8 report writer (never print raw values to a cp1252 console)
- [x] 1.3 `_common.py`: mapping-tier + deprecated-attribute resolution from the country axis YAML
- [x] 1.4 `inventory.py`: coverage matrix (`01_Raw` vs `validate_raw` / `mapping` / `validate_mapped`),
      broken-run detection (persona dirs with zero `identity.json`), combo/model/strategy filters
- [x] 1.5 `inventory.py`: staleness — config-file vs `{slug}.json` vs `{slug}.misses.csv` mtimes,
      **plus** re-resolution of every recorded miss against the current config; halt-with-report on
      disagreement
- [x] 1.6 `fixtures/` + `selftest.py` skeleton covering 1.2–1.5

**Files:** `scripts/_common.py`, `scripts/inventory.py`, `scripts/selftest.py`, `fixtures/**` — all new
**Dependencies:** None

### Phase 2: Diagnose — rollup, taxonomy, ranking
**Goal:** Replace the hand-written aggregation and the manual reading of 326 strings.

**Started:** 2026-07-30
**Completed:** 2026-07-30

> **Scope correction, 2026-07-30 — tasks 2.2–2.4 were reverted.** `classify.py` was built, then
> deleted with its fixtures and its eight selftest checks. Its criteria are now `SKILL.md` §4a,
> written for a reader. `config_tokens` / `ConfigToken` / `load_rules` moved to `_common.py` as
> extraction helpers. Task 2.5 was reworked: `rank.build_ranking` now takes `MissRecord` +
> `ValidityRow` and aggregates its own per-value counts, and `CandidateFix` lost its `cls` /
> `label` / `confidence` / `auto_proposable` fields.

- [x] 2.1 `rollup.py`: per-attribute total / distinct / singleton / repeat-ratio /
      `on_miss`-masked-share, with denominators; `--by model` and `--by strategy` slices
- [ ] ~~2.2 `classify.py`: taxonomy assignment (A wrong-axis, B free text, C noise, D config miss,
      E schema gap) over distinct `(attribute, raw_value)` pairs~~ **Reverted 2026-07-30**
- [ ] ~~2.3 `classify.py`: wrong-axis detection — cross-resolve each miss against every *other*
      attribute's `synthetic` block, record which attribute matched **and at which tier**~~
      **Reverted 2026-07-30**
- [ ] ~~2.4 `classify.py`: noise heuristics — per-value repeat count and per-attribute singleton
      share; report the numbers and a *suggested* label~~ **Reverted 2026-07-30.** The counts
      survive: `extract.py` prints instances, combos, sole-cause personas and the singleton share
      per attribute. The *suggestion* is what was removed.
- [x] 2.5 `rank.py`: sole-cause attribution → personas recovered, ordered, with denominators and the
      instance count alongside so a large proportional gain on a tiny base is visibly trivial
      *(reworked 2026-07-30 to consume `MissRecord` directly)*
- [x] 2.6 Extend `selftest.py`; assert the 2026-07-30 reference figures on the fixture replay

**Files:** `scripts/rollup.py`, ~~`scripts/classify.py`~~, `scripts/rank.py` (new); `selftest.py`, `fixtures/**`
**Dependencies:** Phase 1

### Phase 3: ~~Propose — the parity gate~~ REVERTED
**Goal:** ~~Automate the accept criterion, including its refusals.~~

**Started:** 2026-07-30
**Completed:** 2026-07-30
**Reverted:** 2026-07-30

> **REVERTED IN FULL, 2026-07-30 (scope correction).** `parity.py`, `fixtures/parity/` and the nine
> parity selftest checks are deleted. Tasks 3.1–3.5 below are struck; they were implemented and
> passing, and were removed because automating the accept criterion is the thing the user rejected:
> *"all the decision has to be made by you when you get the data from Python."*
>
> Everything the gate encoded survives as prose in `SKILL.md` §4b–§4f — the parity test quoted
> verbatim, the precedent-token requirement, the three hard refusals, the `equals`-over-`contains`
> rule with its 4-character floor, and all eleven fixture values as worked examples **with their
> verdicts**. `_common.fold` stays (shared, mechanical); `_cross_attribute_collisions` moved to
> `_common.cross_attribute_collisions` for `substring.py`, which is the stage a `contains` deferral
> was always handed to.
>
> The Phase 2 amendment below is retained because it is the empirical record of *why* an automated
> gate cannot work here.

> **Amendment, 2026-07-30 — the similarity threshold was withdrawn after Phase 2.**
>
> Tasks 3.1, 3.2 and 3.5 originally specified a gate of fold-equality **or**
> `difflib.SequenceMatcher ≥ 0.8` (plus a shared-prefix stem), emitting `proposals` and
> `needs_decision`, with 3.5 asserting that the gate *"re-derives exactly the four edits the user
> approved on 2026-07-29"*. Phase 2's run over the real 35-combo Sweden dataset disproved that
> design in both directions, so it was replaced (user-approved before implementation):
>
> - **It over-proposes, dangerously.** `Götaland` → `Gotland` scores **0.93** — a macro-region one
>   accent from a real county, exactly the mapping the playbook's golden rule refuses because it
>   fabricates a distribution. Same shape: `mother and grandmother` → `mother and father` (0.82),
>   `Office Administration` → `Public Administration` (0.81), `Lägenhet` → `Ägarlägenhet` (0.80).
>   The failure mode is semantic narrowing and near-homography, neither of which a precedent-token
>   test rejects — the precedent is real; it is the *relation* to it that is wrong.
> - **It under-proposes the values that actually matter.** All four edits approved on 2026-07-29
>   are translation or semantic parity (`dormitory` ≈ `Studentbostad`, an `äktenskap` stem for the
>   existing exact token, `Realskole` ≈ `Realskola`, `Hälsingland` → Gävleborg beside
>   `gästrikland` → Gävleborg). No string-similarity test can derive them: only **5 of the 100**
>   class-D candidates in that dataset are fold-equal at all, and `gästrikland` ranks *below* the
>   wrong county `Halland` for `Hälsingland`.
>
> **The amended design:** scripts auto-propose **fold-equal only** (casing / diacritics /
> whitespace / hyphen), which is provably safe; everything else becomes a ranked **review queue**
> carrying candidate precedent tokens, the refusal reason and explicit risk flags. The queue is
> evidence, never a recommendation. The parity argument over it is applied in conversation by
> `SKILL.md` (Phase 6) — which is where translation and inflection judgement belongs, and how both
> prior sessions actually ran. Similarity survives only to *order* the tokens shown beside a queue
> entry; it can never promote one to a proposal.

- [ ] ~~3.1 `parity.py`: **fold-equality precedent search** — for a class-D candidate, find an
      existing token in the same target value's matcher block that it is fold-equal to (casing /
      diacritics / whitespace / hyphen). This, and only this, yields an auto-proposal. The fold is
      declared once in `_common.fold` and is rooted in the mapping engine's own `normalize`, so it
      inherits the UTF-8 repair and the typographic-punctuation fold and is provably **never
      stricter** than the engine's `equals` tier — it is looser in exactly three documented ways~~
- [ ] ~~3.2 `parity.py`: emit **`proposals`** (each naming its precedent token, target value, config
      file, matcher tier to edit, and personas recovered) and **`review_queue`** — everything else,
      total over the ranking and sorted by personas recovered, each entry carrying its nearest
      config tokens with similarities and targets, the reason it was not auto-proposed, and its
      risk flags (`no-precedent`, `near-homograph`, `broader-than-precedent`, `semantic-narrowing`,
      `orthography-mismatch`, `competing-targets`)~~
- [ ] ~~3.3 `parity.py`: hard refusals — never propose a new entry in `values`, never propose `on_miss`
      on a scored axis (refused by the same membership test: `on_miss` is a directive key and never
      a member of `values`), never propose a `contains` token shorter than 4 chars or that is a
      substring of an existing token in another attribute (defer those to `substring.py`)~~
- [ ] ~~3.4 Prefer `equals` over `contains` in every proposal where the value is a whole token; state
      why in the proposal (tier sweep is global, so `equals` is provably additive). Under the
      fold-equal rule a candidate is *always* a whole token, so every proposal is `equals` and the
      two `contains` refusals in 3.3 are the standing contract for a future widening — exercised
      directly by the selftest rather than left unproven~~
- [ ] ~~3.5 Fixture test: the amended behaviour — `fixtures/parity/` replays the config as it stood
      before 2026-07-29; the one fold-equal candidate is proposed, the four approved edits appear
      in the review queue with their surfaced precedents and flags, and `Götaland`,
      `College diploma`, `Åland` and `divorced parents (shared custody)` are never proposed and
      each carries the flag that explains why~~

**Files:** ~~`scripts/parity.py`, `fixtures/parity/**`~~ — deleted 2026-07-30. `_common.fold`
survives; `_cross_attribute_collisions` moved to `_common.cross_attribute_collisions`.
**Dependencies:** Phase 2

### Phase 4: Verify — probe, regression gate, substring auditor
**Goal:** No edit is accepted on argument alone.

**Started:** 2026-07-30
**Completed:** 2026-07-30

> **Two design notes, 2026-07-30 — recorded because the Testing Plan's wording assumed
> otherwise.**
>
> - **An over-broad `contains` cannot produce a regression.** The integration test was
>   specified as *"a deliberately over-broad `contains` token produces `regressions > 0`"*.
>   Under the engine's global tiered sweep, adding a rule can only *claim* a raw value, never
>   release one, so nothing becomes unmapped: the outcome is a **re-route**, which is the more
>   dangerous finding (it moves mass between two real categories, which is precisely what the
>   TV score measures) *and* is invisible to a miss-count gate — the fixture asserts both. The
>   regression path is exercised by a second candidate that **drops** a token, which is a
>   realistic edit (replacing an exact alias with a stem) and does unmap a value.
> - **`regress.py` runs two arms, not one.** Diffing only against the stored mapped file cannot
>   tell a real change from a stale artefact. The candidate arm is diffed against the stored
>   file (the headline numbers) *and* a baseline arm is re-mapped alongside it, giving (a) exact
>   per-attribute miss deltas for the noise-invariance gate — never read off a possibly-stale
>   `misses.csv` — and (b) a provenance check: the baseline arm must reproduce the stored file,
>   or every number is measured against a baseline that no longer exists.

- [x] 4.1 `probe.py`: build a mapper on an arbitrary `mappings_path` (materialise the candidate tier
      copy in the scratchpad), resolve an explicit value list, before/after table
- [x] 4.2 `regress.py`: re-map every persona of the selected combos under the candidate config, diff
      against the stored mapped JSON, classify each difference as newly-resolved / regression /
      re-routed; **exit non-zero if `regressions > 0`**
- [x] 4.3 `regress.py`: list every newly-captured `(attribute, value)` pair for eyeball review — the
      stems caught variants nobody had enumerated
- [x] 4.4 `substring.py`: corpus-driven `contains`-token audit — for every token, find observed values
      where it matches as a substring but not as a word, and count the personas currently mapped via
      that token alone
- [x] 4.5 Both heavy scripts: `--limit`, progress to stderr, and a documented note to run them in
      background (they exceed the 120 s default)

**Files:** `scripts/probe.py`, `scripts/regress.py`, `scripts/substring.py` (new); `scripts/_common.py`
(config digests, the provenance sidecar, candidate-tier materialisation); `selftest.py`,
`fixtures/verify/**`
**Dependencies:** Phase 2 (Phase 3 for the candidate-dir contract)

### Phase 5: Project
**Goal:** Answer "how many personas must this combo generate?" correctly.

**Started:** 2026-07-30
**Completed:** 2026-07-30

> **Finding, 2026-07-30 — the reference figure `+5,636` was computed with a different bound.**
>
> The smoke run over the 35 `swedish_02` combos reproduces `12 of 35 combos under 100` and
> `+3,413 at the point estimate` **exactly**. The safe-bound figure does not: the contract's
> one-sided 95 % Wilson bound (z = 1.6449) gives **+5,233** over all 35 combos, of which
> **+5,212** comes from the 12 under-target ones. Re-running at `--confidence 0.975` — i.e. the
> lower limb of a *two-sided* 95 % interval, z = 1.9600 — reproduces `+5,636` to the unit, summed
> over the 12 under-target combos only. So the hand-computed reference used the two-sided limb and
> a different summation set. That is precisely the confusion the statistical contract fixes, so the
> implementation follows the contract (one-sided), labels the bound with its sidedness everywhere
> it appears, and reports the all-combos and under-target totals as two separately named numbers.

- [x] 5.1 `project.py`: clean pool = `validate_raw.passed ∩ validate_mapped.passed` per combo
- [x] 5.2 `project.py`: one-sided Wilson lower bound with explicit degenerate-input guards; point
      estimate and safe bound side by side, denominators carried
- [x] 5.3 `project.py`: post-fix re-projection driven by `regress.py` output, without re-running the
      pipeline
- [x] 5.4 `project.py`: report the N=100-is-operational caveat and the raw-attrition term explicitly
- [x] 5.5 Cross-check against `statsmodels` when available; pinned fixture values otherwise

**Files:** `scripts/project.py` (new); `selftest.py`, `fixtures/project/**`
**Dependencies:** Phase 1

### Phase 6: Extraction, the staleness hole, and the judgement written down
**Goal:** Hand the evidence over, and write down how to read it.

**Started:** 2026-07-30
**Completed:** 2026-07-30

> **Rescoped 2026-07-30** by the correction at the head of this plan. The phase now also carries the
> deletion of `classify.py` / `parity.py`, the new `extract.py`, and the raw-vs-mapped staleness
> check Phase 4 proved was missing. The documentation tasks changed shape: ~~**no tracked repo file
> is modified.**~~ The skill directory is gitignored by deliberate decision, so registering it in
> `CLAUDE.md` would point at something a clone does not have; the playbook edit and the
> `report-unmapped.md` archiving are likewise repo-surface changes this branch does not make.
>
> **Amended 2026-08-01** — tracked repo files *are* modified by this branch: the three load-bearing
> `src/` changes plus the `on_miss`-sink removal in `config/mapping/`. See *Scope amendment,
> 2026-08-01*. The gitignore decision on the skill directory itself is unchanged.

- [x] 6.0 Delete `classify.py`, `parity.py`, `fixtures/parity/` and their selftest checks; rewire
      `rank.py` off the taxonomy and `substring.py` off `parity`; move `config_tokens` /
      `ConfigToken` / `load_rules` / `cross_attribute_collisions` into `_common.py`
- [x] 6.0a `extract.py`: the offending raw values per attribute (personas-recovered order) with
      instance / combo / sole-cause counts, the `__UNMAPPED__`-vs-`on_miss` outcome, the attribute's
      declared `values` and tokens beside them, `--limit-values` with an explicit dropped count and
      dropped mass, and the per-combo `validate_mapped × 01_Raw` fallback with a loud blind-spot
      warning
- [x] 6.0b `inventory.py`: close the staleness hole Phase 4 found — newest `persona_*/identity.json`
      vs `{slug}.json` **and** `{slug}.misses.csv`, halting on the same verdict as the config check.
      The whole-directory comparison is kept but demoted: all 15 combos it flagged on the live
      dataset were flagged by a `logs/run_*.log` or a `run_metadata.json`, files the mapping stage
      never reads, so those are reported as *informational* and the halt is reserved for persona
      payloads (3 combos, 2.6–3.7 h behind). Fixtures cover both directions of both cases.
- [x] 6.1 `SKILL.md`: frontmatter (`name`, `description`, `argument-hint`, `allowed-tools`), `Step 0:
      Parse Arguments` with a usage blockquote, path table, numbered steps
- [x] 6.2 `SKILL.md`: the decision criteria as *guidance for a reader* — legitimate vs config miss,
      the parity test verbatim with its precedent-token requirement, the benchmark-integrity
      constraint (*"every rule you add there makes a weak model look better without it having gotten
      better"*), the `values` / `on_miss` / macro-region refusals, the worked examples with their
      verdicts, and the substring trap with the live `"rent"` ⊂ `"parents"` defect
- [x] 6.3 `SKILL.md`: approval protocol — present proposals + refusals + schema gaps as a named,
      itemised list with counts, state *"I have not made these edits"*, wait for an itemised
      go-ahead, then apply, then `probe` → `regress` → `ruff check src/`
- [x] 6.4 `SKILL.md`: `Optional tools`, `Edge Cases` and `Important Constraints` — the four
      off-path scripts, the misses-CSV fallback and its `on_miss` blind spot, UTF-8 discipline, cwd
      resets/absolute paths, background execution, immutable inputs, the `probe.py` silent-no-op
      trap, and the 31-of-61 coverage caveat
- [ ] ~~6.5 `llm_pool.py` behind `--llm-diagnostics`~~ **Deferred out of scope 2026-07-30**
- [ ] ~~6.6 Register the skill in `CLAUDE.md`'s documentation table; add a how-to section to
      `docs/mapping_gap_investigation_playbook.md`~~ **Withdrawn 2026-07-30** — the skill directory
      is gitignored, so a `CLAUDE.md` entry would document something a clone does not have
- [ ] ~~6.7 Archive `docs/development/plans/pending/report-unmapped.md`~~ **Withdrawn 2026-07-30** —
      repo surface this branch does not touch; it remains a separate change

**Files:** `.claude/skills/audit-unmapped/SKILL.md`, `scripts/extract.py` (new); `scripts/_common.py`,
`scripts/inventory.py`, `scripts/rank.py`, `scripts/substring.py`, `scripts/selftest.py`;
deleted: `scripts/classify.py`, `scripts/parity.py`, `fixtures/parity/**`.
~~**No tracked repo file is modified except this plan document.**~~
**Amended 2026-08-01** — see *Scope amendment, 2026-08-01*: `mapping_engine.py`,
`synthetic_mapper/base.py`, `synthetic_mapper/loader.py`, `analysis/utils/country_config.py`,
`validate_mapped/validate.py`, `scripts/analyze/map_populations.py` and the Swedish
`config/mapping/` tiers are all modified.
**Dependencies:** Phases 1–5

---

## Testing Plan

### Unit Tests (`selftest.py`, fixture-driven, no data root)
- [x] Artefact loaders: well-formed rows parse; a missing/misspelled column raises naming file + row
      — `check_load_misses_rejects_malformed`
- [x] `is_unmapped` path: legacy `None` counts as unmapped, `== "__UNMAPPED__"` is never used
      — `check_unmapped_predicate_and_exemption` *(the "never `== "__UNMAPPED__"`" half is true by
      inspection — the only literal occurrence is a display string in `probe.py` — not asserted)*
- [x] Slug decomposition on `swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`
      and on a legacy `seed_*` slug (returns `None`, handled) — `check_slug_decomposition`
- [x] Rollup: hand-computed totals/distinct/singletons on a 12-row fixture; masked vs unmapped split
      — `check_rollup_totals` + `check_rollup_masked_share` *(the fixture is 19 rows / 17 counted,
      not the 12 originally written)*
- [ ] ~~Wrong-axis: `'Senior Nurse'` under `employment_status` → labelled with the matching
      attribute and tier; a `contains`-tier hit is flagged low-confidence~~
      **Withdrawn 2026-07-30 (scope correction)**
- [x] Sole-cause ranking: a persona failing on 3 attributes contributes to none of their recovery
      counts; a 1-attribute persona contributes to exactly one
- [ ] ~~Parity *(amended 2026-07-30)*: only a fold-equal candidate is proposed, naming its precedent
      token; the four accepted edits and the four rejected values all land in `review_queue`~~
      **Withdrawn 2026-07-30 (scope correction)** — `parity.py` and its nine checks are deleted
- [x] **(added 2026-07-30)** Raw-vs-mapped staleness, both directions: a newer
      `persona_*/identity.json` halts with the combo named and the `--force` remedy printed; a newer
      `logs/run_*.log` is reported under its own heading and does **not** halt
- [x] **(added 2026-07-30)** Extraction: the value table carries instances / combos / sole-cause and
      names the `on_miss` literal a masked value was absorbed into; truncation states the dropped
      count and the dropped mass; the reconstruction fallback joins on the identity key, raises on a
      missing key, marks every record unmasked, and renders a WARNING naming the blind spot and the
      affected combos
- [x] Wilson: matches `statsmodels` (or pinned values) at `1e-9`; `n=0`, `k=0`, `k=n`, `n=1` return
      documented values, never `NaN`; monotone in `k` for fixed `n`
- [x] Substring auditor: a synthetic `"rent"`/`"parents"` fixture is flagged with the right count
      (`fixtures/verify/`: seven personas map through the token alone, five of them on an `infix`
      match over `'Living with parents'` and `'Parental Home'`; a whole-word-only token is never
      flagged, and a token whose deletion changes nothing is priced at zero)

### Integration Tests
- [x] End-to-end fixture run: `inventory → rollup → rank → extract` produces the expected report
      sections and numbers, writing only into a temp dir *(the `classify → parity` legs were
      withdrawn 2026-07-30; `project` is exercised on its own fixture slice)*
- [x] Candidate-config A/B: `probe.py` against a fixture tier copy returns different outcomes from
      the production tier — proving `mappings_path` is actually honoured (guards the
      `map_population` trap). Pinned in *both* directions: an added rule resolves a value that
      missed, a removed rule loses one that resolved, identical arms move nothing
- [x] `regress.py` on fixtures: a deliberately over-broad `contains` token produces
      `regressions > 0` and a non-zero exit *(amended 2026-07-30 — see the Phase 4 note: an added
      `contains` provably cannot unmap anything, so the over-broad fixture asserts `re_routed == 2`
      with **zero** miss-count movement, and a token-dropping candidate carries the
      `regressions > 0` / non-zero-exit assertion)*

### Manual Verification (against the real 35-combo Sweden dataset)
- [ ] `/audit-unmapped swedish` reproduces the 2026-07-30 rollup figures
      **Blocked 2026-08-01:** the ticked Success Criterion above already records a live run, but over
      the current 61-combo pool; the 35-combo wording here was never re-confirmed and the pool it
      names no longer exists.
- [ ] Staleness gate fires when a mapping config is touched after a map run, and names the files
      **Blocked 2026-08-01:** fixture-asserted (`check_mtime_gate`,
      `check_staleness_verdict_and_report`), but the config-touch arm was never exercised live. A
      live run on 2026-08-01 over `--country swedish_02 --all-strategies` reported **65 combos, 0
      broken runs, 0 orphans, 0 stale artefacts, 0 disagreements over 4,046 re-resolved misses,
      `verdict: halt`** — so the halt path is confirmed live, but on the raw-newer-than-mapped arm
      (1 combo), not the config-touch arm.
- [ ] Fallback path (rename one `.misses.csv` away) reconstructs from raw and prints the `on_miss`
      blind-spot warning
      **Blocked 2026-08-01:** fixture-covered by `check_extract_fallback_is_blind_and_says_so`; no
      real-dataset rename run was performed.
- [ ] `regress.py` over all `swedish_02_*` reproduces `5250 / 49 / 0 / 0`
      **Blocked 2026-08-01:** requires the 35-combo pool at the git config state of those four
      edits. The pool is now 65 combos and the mapping config has since diverged, so the figure is
      not reproducible. The fixture-level gate **is** fully asserted (`check_regress_null_run`,
      `check_regress_additive_edit`, `check_regress_regression_gate`,
      `check_regress_provenance_detects_a_stale_baseline`).
- [x] `substring.py` rediscovers `"rent"` ⊂ `"parents"` at ~131 personas — **found, ranked #1 of 611
      flagged tokens, without being told which token to look at.** The count differs from the
      transcript's 131 for two stated reasons and the figure is *not* claimed to reproduce it: the
      corpus is the current 61-combo / 8,226-persona `01_Raw` state rather than the 35-combo
      snapshot, and the attribution is stricter (a value is only counted when *deleting that one
      token* changes its mapping). Result: 570 personas map through `"rent"` alone in total, of which
      **79 on an `infix` match with no fallback rule** — `'Living with parents'` ×45, its casing
      variants ×9, `"Parents' Home"` ×8, … The auditor also shows `'Parental Home'` ×11 is claimed by
      a *second* token as well, so deleting `"rent"` alone would not free it — a correction to the
      transcript's attribution
- [ ] ~~Projection reproduces 12 combos under 100, +3,413 / +5,636~~
      **Struck 2026-08-01** — see the Phase 5 "Finding, 2026-07-30": `12 of 35` and `+3,413`
      reproduce exactly, but the contract's one-sided bound gives **+5,233**, and `+5,636` only
      reproduces at `--confidence 0.975` summed over the 12 under-target combos. The reference
      figure was computed with a different bound and a different summation set, so it is not a
      criterion the implementation can meet as written.
- [ ] ~~`--llm-diagnostics --limit 25` on one `random_pick` combo returns the \~20 % unmappable-candidate
      fraction, run in background~~
      **Struck 2026-08-01** — orphan of Goal 5 / task 6.5, both already struck as *"Deferred out of
      scope 2026-07-30. Not built."* No `llm_pool.py` exists.
- [x] No file under `01_Raw/` or `03_Analysis/` has a changed mtime after a full run
      **(closed 2026-08-01)** — `check_a_full_run_never_modifies_its_inputs` snapshots 12 files as
      `(mtime_ns, size, sha256)` across `inventory → rollup → rank → extract`, and was verified
      non-vacuous against a bare `os.utime` touch, an equal-prefix content edit, and an added file.
      Now fixture-asserted rather than manually observed.

### Edge Cases
- [x] A combo with an empty `misses.csv` (mapped cleanly) — reported as zero, not dropped
      **(closed 2026-08-01)** — `check_rollup_present_but_empty_miss_log_is_a_measured_zero`
      materialises a header-only log in a scratch dir and asserts the combo lands in
      `slugs_with_miss_log`, that `combos_without_miss_log == ()`, and that the totals are unchanged
- [x] A combo with persona dirs but no `identity.json` — reported as a broken run, excluded from
      statistics, and the exclusion logged — `check_coverage_matrix`,
      `check_extract_reports_a_combo_that_contributes_nothing`
- [x] An attribute absent from a combo's records — marked *absent*, distinct from *zero*
      — `check_rollup_zero_is_not_absent` *(absence is tracked per combo / per declaration, never
      per (combo, attribute) cell)*
- [x] A country with no deprecated attributes (Italy) — no exemption applied, no crash
      **(closed 2026-08-01)** — `check_tier_with_no_deprecated_attributes` asserts
      `deprecated == ()` and `analysed_attributes == attributes`
- [ ] ~~A miss value that resolves under three other attributes — all listed, ranked by tier
      confidence~~
      **Struck 2026-08-01** — this was a `classify.py` predicate, deleted by the 2026-07-30 scope
      correction. The distinction survives as a reader's criterion in `SKILL.md` §4a with
      `Senior Nurse` / `Arbetslös`; the surviving `_common.cross_attribute_collisions` is
      token-containment only, with no tier ranking.
- [x] Non-ASCII values (Swedish, CJK, Arabic) survive to the report file intact
      — `check_report_writer_is_utf8_and_idempotent`, `check_extract_report_render`

---

## Documentation Plan

~~**Rescoped 2026-07-30: no tracked repo file is documented into.**~~ The skill directory is
gitignored, so every repo-surface entry below would point at something a clone does not have.

**Amended 2026-08-01** — two tracked docs *are* updated by this change, because the tracked code and
config changes require it: `docs/architecture/comparison-mapping.md` (the `on_miss` semantics and
the `{slug}.misses.csv` sidecar) and `config/mapping/scb_native/README.md` (the removed sinks and
the 13 → 12 `industry_sector` value count). The withdrawn entries below stay withdrawn. See *Scope
amendment, 2026-08-01*.

- [x] `SKILL.md` is the primary user documentation (how-to), with the path table as its reference
      section — kept separate per Diátaxis
- [ ] ~~Add `audit-unmapped` to the `CLAUDE.md` documentation table~~ **Withdrawn 2026-07-30**
- [ ] ~~Add a "superseded by `/audit-unmapped`" header to
      `docs/mapping_gap_investigation_playbook.md` and correct its stale paths~~
      **Withdrawn 2026-07-30** — repo surface this branch does not touch
- [x] Decision record inside `SKILL.md`: why the bound is one-sided Wilson and must be quoted with
      its summation set, why the freshness gate halts rather than preferring an answer, why ranking
      is by personas recovered, and why the judgement is prose rather than code
- [ ] ~~Move `docs/development/plans/pending/report-unmapped.md` to `archived/`~~
      **Withdrawn 2026-07-30** — remains a separate change

---

## Rollback Plan

1. **Before merge:** `git checkout dev` — *(~~as of 2026-07-30 the branch touches one **gitignored**
   directory plus this plan document; no other tracked file changes.~~)*
   **Amended 2026-08-01** — the branch carries the tracked G1 changeset (`src/` miss observability,
   the `on_miss`-sink removal in the Swedish `config/mapping/` tiers, the two doc updates, and the
   tests covering them). Before merge, `git checkout dev` still discards everything, since the
   skill directory is gitignored and survives independently.
2. **After merge:** `rm -r .claude/skills/audit-unmapped/` removes the skill itself. ~~No `src/`, no
   `config/`, no `CLAUDE.md`, no test-suite changes, so nothing downstream depends on it.~~
   **Amended 2026-08-01** — the tracked G1 changeset must be reverted separately: `git revert -m 1`
   the merge commit, then re-run `map_populations.py --force` followed by
   `validate_mapped_personas.py --force` for every affected combo. Removing the `on_miss` sinks
   changes the on-disk mapped output (misses that were absorbed into "Wage / Business" / "Other" now
   surface as `__UNMAPPED__`), so reverting the config without re-mapping leaves `03_Analysis/`
   inconsistent with `config/`.
3. **Data considerations:** none. Every script is read-only over `01_Raw/` and `03_Analysis/`; all
   output goes to the scratchpad or a user-named path. There is no migration and no state to reset.
4. If a config edit made *during* a skill run turns out wrong: `git checkout config/mapping/` and
   re-run `map_populations.py --force` + `validate_mapped_personas.py --force` for the affected
   combos.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Auto-proposals drift into absorbing model noise, inflating weak models and corrupting the benchmark | Med | **High** | *(tightened 2026-07-30)* Auto-proposal requires **fold-equality** with a named precedent token, not similarity to one; everything else ⇒ `review_queue` with risk flags; never add to `values`; the constraint is restated in `SKILL.md` and every proposal prints its justification |
| A `contains` proposal steals values from another attribute (the `"rent"` failure mode) | Med | High | Prefer `equals`; refuse `contains` tokens < 4 chars; `regress.py` gate is mandatory for any `contains` edit; `substring.py` runs on the post-edit config |
| Scripts silently score the production config because `map_population` ignores `mappings_path` | Med | High | Never call `map_population` in `probe`/`regress`; an integration test asserts an A/B actually differs |
| Analysis run against stale artefacts (the 7-hour gap that wasted a pass) | Med | High | Phase 1.5 halts on mtime disagreement **and** on re-resolution disagreement; config hash recorded in `run_metadata.json` |
| Fallback path used unknowingly, hiding all `on_miss`-masked misses | Med | Med | Loud warning naming the count; the report header states which input path was used |
| Projection wrong for `generate_*` strategies because raw attrition dominates | Med | Med | Base is the clean-pool intersection, not the mapped rate; raw and mapped attrition reported as separate terms |
| Skill-local scripts rot — not covered by repo `pytest` | Med | Med | `selftest.py` is fixture-only, runs in one command in under 30 s, and `SKILL.md` runs it as step 0 of every invocation |
| `regress.py` over 5,250 personas exceeds tool timeouts | High | Low | `--limit`, stderr progress, documented background execution |
| Non-ASCII values crash on the cp1252 Windows console | High | Low | All value output goes to a UTF-8 file; never printed directly |
| `01_Raw` literal duplicated a fourth time and drifts | Low | Low | Declared once in `_common.py`, noted in the plan; if it ever changes, the skill fails loudly on a missing dir |
| Over-engineering a tool used a handful of times a year | Med | Med | YAGNI enforced: no plugin architecture for classifiers, no rule engine, no templating; every script maps to a step that was manually re-invented at least twice |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Foundation + pre-flight | Medium (~350 lines + fixtures) | None |
| Phase 2: Diagnose | Medium (~300 lines) | Phase 1 |
| Phase 3: Parity gate | Medium (~200 lines, highest judgement density) | Phase 2 |
| Phase 4: Verify harness | Medium (~300 lines) | Phase 2 |
| Phase 5: Projection | Small (~120 lines) | Phase 1 |
| Phase 6: SKILL.md + docs + opt-in diagnostics | Medium (~600 lines of `SKILL.md` + ~150 of `llm_pool.py`) | Phases 1–5 |

---

## References

- Source sessions: transcripts `014de28b-60e8-4651-91ac-3b4c6b070f0c` (reconstruction method) and
  `eca9c71d-3732-4bfb-851f-6778876234a7` (misses-CSV method) — the manual procedure this automates
- `docs/mapping_gap_investigation_playbook.md` — the manual runbook; golden rule, fix ladder,
  three verification gates (paths stale)
- `docs/real_mapper_philosophy.md` — the real population defines the category space; synthetic-only
  values must stay unmapped
- `docs/architecture/comparison-mapping.md` — matcher vocabulary, global tiered sweep, stage order
- `docs/swedish_mapping_fix_2026-06-29.md`, `docs/swedish_mapping_fix_2026-05-29.md` — worked triage
  records; the empirical noise floor and the labelled examples used as fixtures
- `docs/development/plans/completed/persona-validation-gate-reorder.md` — the clean-pool definition
  and `population_cap`'s shortfall behaviour
- `docs/development/persona-data-quality-observations.md` — the second attrition cause (missing
  `identity.json`), strategy-dependent
- `docs/scb_sweden_category_power_analysis.md` — why N=100 is operational, not statistical
- `docs/development/plans/pending/report-unmapped.md` — superseded precursor; to be archived
- `docs/development/plans/pending/investigate-unknown-unmatched-scb-labels-findings.md` — prior
  ranked fix list; the output shape to emit, and a source of proposals the later doctrine forbids
- `~/.claude/knowledge/data-pipeline-engineering/` — `01` classification, `02` stage/contract/
  provenance patterns, `03` rates-with-small-denominators, `05` YAGNI and test-pyramid shape

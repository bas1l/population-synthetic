# Plan: Strip statistical framing from identity prompt files

**Date:** 2026-05-11
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-comparison-detailed-categories`
**Branch:** `feature/strip-stats-from-identity-prompts`

> **Base-branch caveat.** The current base branch has uncommitted work in progress (`identity_generator_configurable.py`, `compare_pipeline_to_scb.py`, `generate_persona_and_report.py`, and several new seed manifests). Decide at `/plan-implement` time whether to (a) commit/stash that work first, (b) branch off `main` instead, or (c) accept inheriting the in-flight state.

---

## Overview

The identity-generation prompt file `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` encodes extensive population-statistical priors in its category descriptions and constraints — percentages, prevalence words, country comparisons, and probabilistic coherence correlations. This plan strips that content so the LLM receives only neutral definitions plus locale anchoring and hard logical rules. The other three identity prompt files (`_001`, `_002_swedish`, `_003_swedish_flat`) were audited and found already clean; they are kept in policy scope but require no edits.

## Problem Statement

The project policy "no hardcoded statistical data" (already enforced for SCB/SSB fetch-and-sample services) has not been applied to LLM prompt content. As a result, `simulation_config_004_swedish_generative.json` primes the LLM with distributional claims that should come exclusively from the live SCB sampling layer.

This couples two layers the project deliberately keeps separate:

1. **Distributional realism layer** — `SampleService` / `SSBSampleService` produce statistically realistic draws from live SCB/SSB API data via conditional chained sampling.
2. **Persona-generation layer** — the LLM is supposed to receive a *neutral* schema and produce a coherent value for one attribute given upstream context, without any baked-in population prior.

Concretely, file 004 contains 20+ instances of forbidden framing — e.g. `"approximately 50/50 male and female"`, `"Single-person households are very common in Sweden (around 21%)"`, `"Sweden is one of the most secular countries in the world"`, `"younger personas (18–25) are more likely single"`. These cause the configurable identity generator (seed 013, `processing_type: configurable`) to silently consume a prompt-encoded prior rather than the SCB-sourced distribution.

The audit document `docs/audit_scb_comparison_api_rooting_2026-05-11.md` already enforces the API-source-vs-derivation separation on the comparison side; this plan extends the same principle to the LLM prompt content.

## Goals

### In Scope

1. Strip all four forbidden pattern classes from `simulation_config_004_swedish_generative.json` (Tier 4 strip — see Technical Design).
2. Audit the other three identity prompt files (`_001`, `_002_swedish`, `_003_swedish_flat`) and confirm cleanliness; document the audit result in the plan's completion note.
3. Add a residual-pattern guard (a `Grep` invocation documented here) so future edits can self-check.
4. Persist the rule as a feedback memory at `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\memory\feedback_no_statistics_in_prompts.md` so future sessions respect it without restatement.

### Out of Scope

- Narrative prompts (`config/assets/narrative/**/*`). May be a follow-up plan.
- First-person conversion instructions (`config/assets/narrative/narrative_first_person_instruction_*.txt`).
- The strategy files under `config/assets/identity/configurable/strategies/`. These are method-and-DAG configs, not prompts.
- The `generate_evaluate_random_pick` *methodology* itself — whether the LLM should produce candidate weights at runtime is a separate architectural question.
- SCB/SSB reference data (`config/assets/scb_reference/`, `config/assets/ssb_reference/`) — reference data, not LLM prompts.
- Any change to `category_mappings.json` or the comparison-pipeline normalization layer.
- Any change to the generator code itself (`identity_generator_configurable.py`, factories, services) — prompt-content-only change.

## Success Criteria

- [ ] `simulation_config_004_swedish_generative.json` contains zero numeric prevalence statements (percentages, averages, distribution shapes).
- [ ] `simulation_config_004_swedish_generative.json` contains zero prevalence words (`most`, `majority`, `common`, `rare`, `plurality`, `largest group`, `very common`, `widespread`).
- [ ] `simulation_config_004_swedish_generative.json` contains zero comparative country claims (`Sweden has X relative to …`, `one of the most …`, `among the most progressive …`).
- [ ] `simulation_config_004_swedish_generative.json` contains zero probabilistic within-persona coherence (`more likely`, `tends to`, `correlates with`, `generally aligns with`).
- [ ] All four identity prompt files still parse as valid JSON and keep their original top-level structure (`instruction[]` + categories container; keys, nesting, and types unchanged).
- [ ] All closed-list value enumerations are preserved verbatim.
- [ ] All hard logical constraints (`must`, `if X then Y`) are preserved and any soft constraints are either re-expressed as hard rules or dropped.
- [ ] A smoke run of seed 013 against a single persona produces a valid `identity.json` with all 15 SCB-compared categories populated.
- [ ] Feedback memory file is written and indexed in `MEMORY.md`.

---

## Technical Design

### Approach

A pure content-rewrite of category `description` and `constraints` strings in the affected prompt file. JSON shape, keys, nesting, and types remain identical. Allowed surviving content classes:

- **Neutral category definition** — what the attribute is.
- **Locale anchor** — "the persona lives in Sweden".
- **Locale-specific terminology** — `län`, `samboende`, `bostadsrätt`, `hyresrätt`, `villa`, `Church of Sweden`, `ISCED` codes; Swedish place names *as value enumerations* (not as prevalence framing).
- **Closed-list value enumerations** — verbatim.
- **Hard logical constraints** — `must`, `if X then Y` semantics.

Everything else is stripped.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Strip only numeric stats (Tier 1) | Minimal risk; preserves cultural framing | Leaves prevalence words and country comparisons in place — still encodes priors verbally | Rejected — user explicitly chose Tier 4 |
| Strip Tier 1 + prevalence words only (Tier 2) | Reads cleaner | Still allows "Sweden is one of the most …" and probabilistic coherence | Rejected — Tier 4 chosen |
| Strip Tier 1 + 2 + country comparisons (Tier 3) | Removes both numeric and country-prior framing | Still allows probabilistic coherence ("more likely"), which is a soft statistical claim | Rejected — Tier 4 chosen |
| **Strip Tier 1 + 2 + 3 + coherence correlations (Tier 4)** | **Total separation: prompt carries no statistical prior** | Coherence must be re-expressed as hard rules or dropped, which may slightly reduce intra-persona coherence | **Chosen** |
| Rewrite the schema entirely (drop description fields) | Cleanest separation | High blast radius; touches generator code (`_build_*_prompt`); breaks alignment with files 001–003 which keep descriptions | Rejected — out of scope |
| Move the population priors into a separate YAML for explicit use by the sampler | Preserves the information for future reuse | Adds a new artifact and integration surface; not asked for | Rejected — not requested |

### Architecture Changes

None to code. Only content of one JSON file changes. The generator (`identity_generator_configurable.py`, `_load_flat_schema`, `_build_enumerate_prompt`, `_build_evaluate_prompt`, `_build_numeric_distribution_prompt`) consumes `description` and `constraints` as opaque strings — the rewrite is invisible to the surrounding code.

```
config/assets/identity/
├── sequential/
│   ├── simulation_config_001.json                 ← audited, clean
│   └── simulation_config_002_swedish.json         ← audited, clean
└── configurable/
    ├── simulation_config_003_swedish_flat.json    ← audited, clean
    └── simulation_config_004_swedish_generative.json    ← MODIFIED
```

### Forbidden patterns (T4) — definitive list

1. **Numeric stats / percentages / distribution shapes** — `21%`, `1.7 children`, `50/50`, `over 50%`, `roughly uniform`, `declining tail`.
2. **Prevalence / frequency words** — `most`, `majority`, `common`, `rare`, `plurality`, `largest group`, `very common`, `widespread`, `dominant share`, `not common`.
3. **Comparative country claims** — `Sweden has X relative to other countries`, `one of the most …`, `high rate compared to …`, `among the most progressive in Europe`.
4. **Probabilistic within-persona coherence** — `more likely`, `tends to`, `correlates with`, `generally aligns with`, `slightly more varied for older personas`.

### Patterns to keep

- Locale anchor: "The persona lives in Sweden."
- Swedish institutional / cultural terms: `län`, `samboende`, `bostadsrätt`, `hyresrätt`, `villa`, `Church of Sweden`, `ISCED` codes.
- Swedish place names as enumerated *values* (Stockholm, Västra Götaland, Skåne, Jämtland, Gotland) — never as prevalence framing.
- Closed-list value enumerations (e.g. `birth_country_detail`'s 21-country list, `household_size`'s explicit list, `income_source`'s 6 categories).
- Hard logical constraints (e.g. "Must be 'Not Applicable' if `employment_status` is 'Unemployed', 'Student', or 'Retired'"; "Must be 'Sweden' if `birth_location` is 'Native (Born in Sweden)'").

### Example rewrites (file 004)

| Field | Before | After |
|---|---|---|
| `instruction` L6 | "The persona lives in Sweden. Generate values that are realistic for a Swedish population. Use Swedish conventions for regions, institutions, and cultural references where applicable." | "The persona lives in Sweden. Use Swedish conventions for regions, institutions, and cultural references where applicable." |
| `age.description` | "Age of the persona in years. The Swedish adult population spans … roughly uniform distribution … declining tail …" | "Age of the persona in years." |
| `biological_sex.description` | "The biological sex of the persona. The Swedish population is approximately 50/50 male and female." | "The biological sex of the persona." |
| `region.description` | "The Swedish county (län) where the persona currently resides. Stockholm, Västra Götaland, and Skåne are the three most populous regions … Urban personas are more likely in Stockholm; rural and northern personas in other counties." | "The Swedish county (län) where the persona currently resides." (If a value enumeration is needed it goes into a closed list, not into the prose.) |
| `religious_alignment.description` | "Sweden is one of the most secular countries … large majority non-religious or nominally affiliated with the Church of Sweden but non-practicing. Actively practicing individuals are a minority; fundamentalist religious observance is rare." | "The persona's relationship to religion. Possible stances include non-religious, nominally affiliated with the Church of Sweden, actively practicing, and fundamentalist." |
| `civil_status.constraints` | "Should be coherent with age: younger personas (18–25) are more likely single, older personas (65+) are more likely widowed." | "Must be coherent with age." *(soft correlation dropped; hard requirement of coherence retained)* |
| `industry_sector.constraints` | "Must be 'Not Applicable' if employment_status is 'Unemployed', 'Student', or 'Retired'. Should be coherent with education_level: IT/technology and healthcare typically require higher education; manufacturing and retail do not." | "Must be 'Not Applicable' if employment_status is 'Unemployed', 'Student', or 'Retired'." *(second sentence dropped — coherence correlation)* |
| `birth_country_detail` (closed list) | unchanged | unchanged — closed-list enumeration is preserved verbatim |

---

## Implementation Plan

### Phase 1: Memory persistence
**Goal:** Lock the policy into auto-memory so future sessions enforce it without restatement.
**Started:** 2026-05-11
**Completed:** 2026-05-11

- [x] Task 1.1 — Create `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\memory\feedback_no_statistics_in_prompts.md` with the wording in the appendix.
- [x] Task 1.2 — Add a single-line index entry to `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\memory\MEMORY.md`: `- [No statistics in LLM prompts](feedback_no_statistics_in_prompts.md) — Strip numbers, prevalence words, country comparisons, and coherence correlations from prompt category descriptions`.

**Files Modified:**
- `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\memory\feedback_no_statistics_in_prompts.md` *(new)*
- `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\memory\MEMORY.md` *(add 1 line)*

**Dependencies:** None.

### Phase 2: Rewrite `simulation_config_004_swedish_generative.json`
**Goal:** Strip all four forbidden pattern classes from file 004 while preserving JSON shape, locale anchor, closed lists, and hard constraints.
**Started:** 2026-05-11
**Completed:** 2026-05-11

- [x] Task 2.1 — Rewrite `instruction[]` block: keep operational/IO contract lines and the locale anchor; drop "Generate values that are realistic for a Swedish population".
- [x] Task 2.2 — Rewrite each of the 35 category `description` fields per the Technical Design. Demographic/socioeconomic categories (age, biological_sex, gender_identity, sexual_orientation, birth_location, region, birth_country_detail, parental_structure, sibling_constellation, civil_status, household_size, education_level, socioeconomic_class, religious_alignment, housing_tenure, employment_status, industry_sector, employment_type, income_source) need substantial rewrites. The Big Five personality fields (openness, conscientiousness, extraversion, agreeableness, neuroticism) and stylistic fields (cognitive_style, financial_behavior, social_media_usage, tone_baseline, speaking_pace, somatotype, disabilities_visible, childhood_atmosphere) are mostly already country-neutral but contain coherence correlations to strip.
- [x] Task 2.3 — Rewrite each `constraints` field: keep hard rules (must / if X then Y); re-express soft coherence as hard "must be coherent with X" or drop entirely.
- [x] Task 2.4 — Preserve all closed-list value enumerations (`birth_country_detail`'s 21-country list, `household_size`'s explicit value list, `education_level`'s ISCED list, `income_source`'s 6 categories) verbatim.

**Files Modified:**
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` — rewrite `instruction[]` and the `description`/`constraints` fields of all 35 categories.

**Dependencies:** Phase 1 (memory in place so it's enforced for future related edits).

### Phase 3: Verify the other three identity prompts remain clean
**Goal:** Confirm and document that files 001, 002_swedish, and 003_swedish_flat contain no forbidden patterns. No content edits expected.
**Started:** 2026-05-11
**Completed:** 2026-05-11

- [x] Task 3.1 — Run the residual-pattern grep (see Testing Plan) against all four files; expect zero hits in files 001, 002, 003.
- [x] Task 3.2 — If any hit surfaces in 001/002/003, treat it as an in-scope finding and rewrite under the same rules.
- [x] Task 3.3 — Record audit verdict in the plan completion note when this plan moves to `completed/`.

**Audit verdict (2026-05-11):** Files 001, 002_swedish, and 003_swedish_flat confirmed clean — zero forbidden-pattern hits. File 004 had exactly one hit: the known false positive in `financial_behavior.description` ("Spenders tend to spend most or all of their income") — a definitional sentence explicitly marked do-not-change. No rewrites required in any of the three audited files.

**Files Modified:**
- None expected.

**Dependencies:** Phase 2.

### Phase 4: Smoke test the seed-013 pipeline against the rewritten prompt
**Goal:** Confirm the cleaned prompt still produces a valid identity for at least one persona under the configurable generator path.
**Started:** 2026-05-11
**Completed:** 2026-05-11

- [x] Task 4.1 — Temporarily narrow `target_ids` in a throwaway manifest (or pass `--manifest` to `scripts/generate_persona_and_report.py`) so only `persona_00000` runs, and set `force_processing: true` for `generate_identity`.
- [x] Task 4.2 — Run `python scripts/generate_persona_and_report.py --workers 1`.
- [x] Task 4.3 — Inspect `<db_root>/seed_013_compared-only-identity/persona_00000/identity.json`: confirm all 15 SCB-compared categories are present, types are correct, closed-list values are within their declared sets, and hard constraints (e.g. `birth_country_detail` consistent with `birth_location`) hold.
- [x] Task 4.4 — Revert the throwaway manifest changes.

**Files Modified:**
- None permanent (manifest changes reverted).

**Dependencies:** Phase 2.

---

## Testing Plan

### Unit Tests
The project has no test suite (per `CLAUDE.md`). No new unit tests are added in this plan.

### Integration Tests
- [ ] Seed-013 single-persona smoke run produces valid `identity.json` (Phase 4 above).

### Manual Verification
- [ ] **JSON well-formedness** — for each file:
  ```bash
  python -c "import json; json.load(open('config/assets/identity/configurable/simulation_config_004_swedish_generative.json'))"
  python -c "import json; json.load(open('config/assets/identity/configurable/simulation_config_003_swedish_flat.json'))"
  python -c "import json; json.load(open('config/assets/identity/sequential/simulation_config_002_swedish.json'))"
  python -c "import json; json.load(open('config/assets/identity/sequential/simulation_config_001.json'))"
  ```
- [ ] **Residual-pattern grep guard** — run via the Grep tool with:
  - Pattern: `(?i)\b(\d+%|approximately|around \d|most|majority|common|rare|plurality|largest group|very common|widespread|relative to|one of the most|among the most|more likely|tends to|correlates|generally aligns)\b`
  - Path: `config/assets/identity/`
  - Glob: `*.json`
  - Expected: zero hits, with the exception of Swedish institutional terms accidentally matching (none of the regex tokens above should appear in those terms — verify).
- [ ] **Side-by-side diff** of file 004 before/after to confirm: (a) JSON shape unchanged, (b) closed-list values unchanged, (c) hard constraints retained.

### Edge Cases
- [ ] Field with closed-list values *and* prevalence framing in the same description (e.g. `birth_country_detail`) — confirm the closed list survives and the prevalence framing does not.
- [ ] Field with locale anchor *and* coherence correlation in the same constraint (e.g. `housing_tenure.constraints`) — confirm the locale terminology survives and the correlation does not.
- [ ] `employment_status` numeric description ("personas under 22 are more likely students") — confirm the coherence correlation is dropped, and that any *hard* age boundary requirement (if needed) is expressed as a `must` constraint or dropped.

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — under "Generation Pipeline" or "Configuration", add a one-line note: "LLM prompt files under `config/assets/identity/` and `config/assets/narrative/` must contain no population-statistical priors (no numbers, prevalence words, country comparisons, or probabilistic coherence)."
- [ ] No README change — this is internal policy.
- [ ] No user-guide change — this is a content-only refactor of internal prompts.
- [ ] No changelog directory exists in this project — skip.
- [ ] Plan-completion note (added when this plan moves to `completed/`) records the audit verdict for files 001/002/003 and links to the relevant `simulation_config_*` files.

---

## Rollback Plan

The change is content-only in a JSON file and is fully recoverable from git history.

1. **Before deployment:** No deployment surface — this is a local repo edit.
2. **Data considerations:** No migrations, no breaking schema changes. The keys, types, and JSON shape are preserved.
3. **Rollback procedure:**
   - If a regression is detected after merge: `git revert <commit-sha>` on the feature commit and re-merge — the prior file 004 is restored exactly.
   - If the smoke test in Phase 4 reveals an unexpected LLM behaviour (e.g. the LLM picks implausible values without the prior framing), the response is *not* to restore the priors but to investigate whether the strategy methodology (`generate_evaluate_random_pick` weight prompts in `identity_generator_configurable.py`) needs adjustment. That investigation is a follow-up plan.
   - Memory rollback: delete the memory file and remove the index line from `MEMORY.md`.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stripping prevalence framing causes the LLM to produce implausible value distributions in `generate_evaluate_random_pick` weight evaluation | Medium | Medium | Phase 4 smoke test on persona_00000; if implausible, document the gap and open a follow-up plan to adjust the strategy methodology rather than restoring priors. |
| Over-aggressive grep flags Swedish institutional terms as forbidden | Low | Low | The chosen regex tokens are all English-language statistical words; Swedish terms (`samboende`, `bostadsrätt`, `län`) don't match. Confirm at grep-run time. |
| Hard constraints accidentally dropped during rewrite | Low | High | Side-by-side diff of constraints; explicit checklist of `must` / `if X then Y` constraints preserved (e.g. `birth_country_detail` ↔ `birth_location`, `industry_sector` ↔ `employment_status`). |
| Closed-list enumerations get reworded and become inconsistent with downstream SCB normalization (`category_mappings.json`) | Medium | High | Preserve closed lists *verbatim* — explicit Phase 2 task (Task 2.4). |
| Base-branch contamination — current branch has uncommitted SCB-comparison work in progress | Medium | Medium | Caveat noted at top of plan; user decides at `/plan-implement` whether to branch off current state or off `main`. |
| Memory-file write accidentally overwrites an existing memory | Low | Medium | Filename `feedback_no_statistics_in_prompts.md` is new (verified — current `MEMORY.md` lists only `feedback_no_fallbacks.md`, `feedback_no_hardcoded_data.md`, `project_comparison_defaults.md`, `feedback_birth_country_aggregation.md`). |
| Future LLM prompt edits silently re-introduce statistical framing | Medium | Medium | Persisted feedback memory (Phase 1); plus the residual-pattern grep is documented here for future audits. |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 1: Memory | 5 min | None |
| Phase 2: Rewrite file 004 | 30–45 min | Phase 1 |
| Phase 3: Verify 001/002/003 | 5 min (grep + spot read) | Phase 2 |
| Phase 4: Smoke test seed 013 | 10–15 min (one LLM run) | Phase 2 |

Total: ~1 hour of focused work.

---

## References

- Trigger conversation: 2026-05-11 audit of seed 013 prompt content.
- Related audit: `docs/audit_scb_comparison_api_rooting_2026-05-11.md` (API-vs-derivation separation on the comparison side).
- Related mapping doc: `docs/scb02_comparison_category_mapping_2026-05-11.md`.
- Related active plans: `docs/development/plans/active/configurable-identity-pipeline.md`, `docs/development/plans/active/generative-identity-methods.md` (these introduced file 004).
- Affected file: `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`.
- Audited-clean files: `config/assets/identity/sequential/simulation_config_001.json`, `…/simulation_config_002_swedish.json`, `…/configurable/simulation_config_003_swedish_flat.json`.
- Read-only reference for the generator code path: `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py` (`_load_flat_schema`, `_build_enumerate_prompt`, `_build_evaluate_prompt`, `_build_numeric_distribution_prompt`, `generate_identity:349`).

---

## Appendix A: Feedback-memory wording (for Phase 1, Task 1.1)

```markdown
---
name: No statistics in LLM prompt files
description: LLM prompt files (config/assets/identity, narrative, …) must contain no population statistics, prevalence words, country comparisons, or probabilistic coherence correlations
type: feedback
---

LLM prompt files used by the persona-generation pipeline must contain no statistical insights or guidance. Strip:
(1) numeric stats (percentages, averages, distribution shapes),
(2) prevalence words (most / majority / common / rare / plurality / largest group / very common / widespread),
(3) comparative country claims ("Sweden has X relative to …", "one of the most …"),
(4) probabilistic within-persona coherence ("more likely", "tends to", "correlates with", "generally aligns with").
Keep only: neutral category definitions, locale anchor ("the persona lives in <country>"), locale-specific terminology (län, samboende, bostadsrätt, ISCED codes, …), closed-list value enumerations, and hard logical constraints ("must", "if X then Y").

**Why:** Extends the existing "no hardcoded statistical data" rule from SCB/SSB fetch-and-sample services into LLM prompt content. Distributional realism must come from the sampling layer (live SCB/SSB conditional chaining), not from priors baked into the LLM's prompt context. User flagged this explicitly on 2026-05-11 after auditing `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`.

**How to apply:** When editing any file under `config/assets/identity/` or `config/assets/narrative/`, audit category `description` and `constraints` fields for the four forbidden patterns. Soft prevalence framing ("Two-parent households are most common") is just as forbidden as explicit numbers ("21%"). Re-express coherence requirements as hard constraints, or drop them. The locale anchor and locale-specific terminology stay.
```

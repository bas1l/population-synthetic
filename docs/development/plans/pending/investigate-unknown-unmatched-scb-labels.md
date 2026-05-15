# Plan: Investigate Unknown and Unmatched Labels in SCB Comparison

**Date:** 2026-05-10
**Author:** Basil
**Status:** Investigation complete — see [findings](investigate-unknown-unmatched-scb-labels-findings.md)
**Base Branch:** `feature/configurable-identity-pipeline`
**Branch:** `feature/fix-unknown-unmatched-scb-labels`

---

## Overview

The SCB comparison for seed013 (100 personas) revealed two related problems: (1) the pipeline emits labels like `Unknown`, `Retired`, `Permanent`, `Permanent contract`, `Project-based employment`, and `Business/self-employment` that have no counterpart in the SCB category mappings, and (2) coherence sits at 63% largely because `employment_status=Retired` and `employment_status=Unknown` appear at age groups where the SCB reference has no matching joint distribution. This plan covers the investigation needed to decide on a fix before any code is changed.

## Problem Statement

The comparison pipeline flags "unmapped categories in B" for most attributes. These fall into two root causes:

1. **LLM free-text drift** — The LLM generates values that are semantically correct but lexically different from the SCB labels (e.g. `Permanent contract` instead of `Permanent employee`, `Business/self-employment` instead of `Self-employed`).
2. **Missing SCB mappings** — Some LLM-generated values (e.g. `Retired`, `Unknown`) may be valid but simply absent from `config/assets/scb_reference/category_mappings.json`.

The 63% coherence score and the significant joint-distribution divergence (age × employment p=0.000) both trace back to `employment_status` being a particularly noisy field.

## Goals

### In Scope
1. Audit every "unmapped category in B" from the seed013 comparison report against `category_mappings.json` to determine whether the fix is a mapping addition or an LLM prompt/constraint change.
2. For each unmapped value, decide: (a) add alias to mappings, (b) constrain the enumeration prompt, or (c) accept as legitimate unmappable value.
3. Document findings as a prioritised fix list ready for implementation.

### Out of Scope
- Implementing any fixes (prompt changes, new mappings, normaliser updates) — that is a separate plan.
- Rerunning the full pipeline; the existing seed013 data is sufficient for investigation.
- Investigating joint-distribution divergence beyond what `employment_status` explains.

## Success Criteria

- [ ] All unmapped categories from the comparison report are catalogued with their attribute, frequency in seed013, and root-cause classification (free-text drift vs. missing mapping vs. invalid value).
- [ ] `category_mappings.json` audited: every canonical SCB label is confirmed present; gaps are listed.
- [ ] `employment_status` coherence failure root-caused: determine whether `Retired` is a missing mapping or a prompt-side issue (the LLM should probably map it to `Pensionär` / `Outside labour force`).
- [ ] A prioritised fix list is written and attached to this plan (or as an addendum file).

---

## Technical Design

### Approach

1. Read `data/comparison_report.json` — the `marginals` section lists every unmapped label and its count.
2. Cross-reference each unmapped label against `config/assets/scb_reference/category_mappings.json` to see if an alias already exists or if the canonical label is missing entirely.
3. Inspect a sample of `identity.json` files for the highest-frequency unmapped attributes (`employment_status`, `employment_type`, `income_source`, `education_level`) to understand what the LLM actually generated.
4. Check the enumeration prompts in `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` for the relevant categories — does the schema constrain the allowed values?

### Key Files to Examine

- `data/comparison_report.json` — full unmapped label inventory
- `config/assets/scb_reference/category_mappings.json` — canonical SCB label aliases
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` — schema + category descriptions sent to the LLM
- `config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json` — which method is used per category
- A sample of `persona_*/identity.json` from seed013 — actual LLM output

---

## Implementation Plan

### Phase 1: Catalogue unmapped values

- [ ] Parse `data/comparison_report.json` and extract every `unmapped_in_b` entry with its attribute and count.
- [ ] For each unmapped label, check if it appears as an alias in `category_mappings.json`.
- [ ] Classify each as: `alias_missing` | `canonical_missing` | `invalid_value` | `acceptable_unmappable`.

**Files to read (no edits):**
- `data/comparison_report.json`
- `config/assets/scb_reference/category_mappings.json`

**Dependencies:** None

### Phase 2: Root-cause employment_status

- [ ] Check what `employment_status` values the LLM generates in seed013 identity files — count occurrences of `Unknown`, `Retired`, `Employed`, etc.
- [ ] Check whether `Retired` maps to any SCB employment category (it should likely map to `Outside labour force` / Swedish `Ej i arbete`).
- [ ] Check whether the `employment_status` schema in `simulation_config_004` provides an enum or just a description — if no enum, the LLM has free rein.
- [ ] Determine whether the 37 flagged coherence failures are age-conditioned (i.e. `Retired` is fine at 65+ but wrong at 25-34) or a pure mapping gap.

**Files to read (no edits):**
- Seed013 `persona_*/identity.json` (sample)
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`

**Dependencies:** Phase 1

### Phase 3: Write fix list

- [ ] Produce a prioritised list of fixes: which attributes need new aliases in `category_mappings.json`, which need schema enum constraints, which need normaliser extensions.
- [ ] Append the fix list to this plan as `## Findings` section or a linked `findings.md`.

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] After any future fix is applied, re-run `compare_pipeline_to_scb.py` on seed013 and confirm the "unmapped categories in B" list shrinks and coherence improves above 80%.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Some LLM-generated labels are genuinely unmappable (dialect variants, composite labels) | Med | Low | Accept as `acceptable_unmappable`; don't force a bad alias |
| Adding aliases to `category_mappings.json` changes comparison results for older seeds | Low | Med | Document which seeds are affected before merging fixes |
| Constraining LLM with an enum reduces diversity of generated personas | Med | Med | Only constrain categories that are directly compared to SCB; leave free-text categories untouched |

---

## References

- **Findings (this investigation's output):** [investigate-unknown-unmatched-scb-labels-findings.md](investigate-unknown-unmatched-scb-labels-findings.md)
- Comparison output: `data/comparison_report.json`, `data/comparison_report.csv`
- Charts: `data/analysis/comparison_report/`
- Related plan: `docs/development/plans/active/configurable-identity-pipeline.md`
- Related plan: `docs/development/plans/active/exhaustive-enumerate-and-flat-normalizers.md`

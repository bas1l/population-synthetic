# Plan: Attribute-vs-Category Terminology Consistency Investigation

**Date:** 2026-07-03
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/joint-fidelity-independent`
**Branch:** `feature/investigate-attribute-category-terminology`

---

## Overview

Verify that the comparison/analysis surface of the codebase uses the "attribute" vs.
"category" terminology exactly as now canonicalised in
`docs/architecture/comparison-metrics.md`, and reconcile any drift. This is an
**investigation** (audit + targeted prose/naming fixes), not a rewrite: the metric logic,
serialized report schema, and public config keys stay untouched.

## Problem Statement

`docs/architecture/comparison-metrics.md` locks a two-level vocabulary:

- **attribute** (a.k.a. *field*) = a demographic dimension — `education_level`, `age_group`,
  `sex`.
- **category** (a.k.a. *category value*) = one possible *value* of an attribute — Primary /
  Secondary / Tertiary. This matches `scheme.categories[attr]`: "category" **always means a
  value, never the field**.

If code, docstrings, comments, config keys, or adjacent docs use these words in a
contradictory way (e.g. calling `education_level` a "category", or calling Primary a
"field"/"attribute"), the freshly-written guide will disagree with the code a reader is
holding it next to, eroding the doc's value and inviting future logic bugs where the two
levels get conflated. A one-time consistency pass, plus a documented list of intentional
exceptions, closes that gap.

A preliminary audit (see Appendix A) has already scanned the in-scope surface and found
**no genuine contradictions** — the effort is therefore mostly *confirmation* plus a few
low-risk prose clarifications, and this plan is scoped accordingly.

## Goals

### In Scope
1. Audit every occurrence of "category"/"categories"/"attribute"/"field"/"value" across the
   comparison surface — `src/population_synthetic/analysis/comparison/` (`evaluator.py`,
   `multivariate.py`, `scheme.py`, `charts.py`), the comparison configs
   (`config/analysis/comparison/{scb,istat}.json`), the mapping configs
   (`config/mapping/{scb,istat}/`), and their READMEs — classifying each as CORRECT,
   CONTRADICTORY, or AMBIGUOUS against the canonical definitions.
2. Separate **locked** names (breaking to rename: `scheme.categories`, serialized report
   fields, CSV headers, public config keys such as `values`/`attributes`/`categories`) from
   **free-to-fix** prose (docstrings, comments, internal READMEs).
3. Produce a categorized findings list and a remediation decision per finding: reword/rename
   the free prose, or leave the locked name and record it as an **intentional exception** in
   the terminology callout.
4. Apply only the low-risk prose/comment fixes the findings justify, and document the locked
   exceptions — respecting the fail-fast and config-as-source-of-truth invariants (no logic,
   no schema, no key renames).

### Out of Scope
- Renaming any serialized report field, CSV column, or public config key (`scheme.categories`,
  report `"categories"`, CSV `"attribute"`/`"unmapped_categories"`/`attr_x`/`attr_y`, config
  `"values"`/`"attributes"`/`"categories"`). These are locked; touching them is a separate,
  higher-risk migration.
- Any change to metric computation, chart output, or the scheme-loading logic.
- Folding `config/mapping/ssb/` into the scb/istat scheme loader, or harmonising its
  `output_categories` key (flagged as adjacent, out-of-scope — see Appendix A).
- The GUI, generators, and any surface outside the comparison/analysis metrics stack.

## Success Criteria

- [x] Every in-scope file has been swept and each `category`/`attribute`/`field`/`value`
      occurrence is classified CORRECT / CONTRADICTORY / AMBIGUOUS in the findings list.
- [x] Every CONTRADICTORY finding is either fixed (prose) or, if locked, explicitly recorded
      as an intentional exception with rationale.
- [x] A "locked names" inventory exists (in this plan / the terminology callout) listing every
      identifier and config/report key that intentionally keeps its current wording.
- [x] Any applied edits touch only docstrings, comments, or internal READMEs — zero changes to
      code identifiers exercised by logic, serialized fields, CSV headers, or config keys
      (verifiable via `git diff` + a green `pytest` run).
- [x] `pytest` and `ruff check src/` pass unchanged after edits.

---

## Technical Design

### Approach

A read-only audit first, a decision table second, a minimal edit pass third. The audit uses
targeted `grep` over the in-scope surface plus close reading of the four comparison modules
and the config/READMEs. Each hit is bucketed by *artifact type* — (a) code identifier,
(b) docstring/comment prose, (c) config key, (d) serialized report/CSV output field — because
the artifact type, not the wording alone, decides whether a finding is fixable or locked.

The guiding rule: **wording that is wrong AND free (prose, type b) gets fixed; wording that is
right stays; wording that is arguably imperfect but locked (types a/c/d that logic or external
consumers depend on) is left and documented as an intentional exception.** This honours the
config-as-single-source-of-truth invariant (config keys are contracts, not free text) and the
fail-fast invariant (renaming a key consumed by `scheme.py`'s `raise`-on-missing loaders would
be a breaking change, not a cleanup).

The preliminary audit (Appendix A) already concludes there are no genuine contradictions, so
the expected outcome is: confirm the sweep, fix 0–3 AMBIGUOUS prose spots if the reviewer
agrees they read poorly, and formalise the locked-names inventory. The plan stays valid even
if a second, more exhaustive pass surfaces a contradiction the preliminary scan missed.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Audit + minimal targeted prose fixes + documented exceptions | Low risk; preserves locked contracts; closes the doc/code gap | Requires disciplined classification | **Chosen** |
| Global rename to make every identifier literally match "attribute"/"category" | Maximal literal consistency | Breaks serialized reports, CSV headers, config keys; violates fail-fast/config invariants; large blast radius | Rejected |
| Do nothing (rely on the doc callout alone) | Zero effort | Leaves ambiguous prose unreconciled; no locked-names record for future contributors | Rejected |

### Architecture Changes

None. No new modules, classes, or interfaces. Edits (if any) are confined to docstrings,
inline comments, and internal README prose. The canonical vocabulary already lives in
`docs/architecture/comparison-metrics.md`; this plan adds, at most, an "intentional exceptions"
subsection to that callout and touches prose in the files below.

Potentially-touched files (prose only):
- `config/analysis/comparison/scb.json` — `basis` strings using "field is not API-identical"
  (AMBIGUOUS prose inside a documentation-only value; reword only if it doesn't alter the
  semantics any consumer reads).
- `config/mapping/{scb,istat}/README.md` — "sub-fields" / "field" prose (secondary DB-column
  sense) — clarify wording if warranted.
- `docs/architecture/comparison-metrics.md` — add the locked-names / intentional-exceptions
  note.

---

## Implementation Plan

### Phase 1: Audit & classify (read-only)
**Goal:** A complete, bucketed findings list for the in-scope surface.

**Started:** 2026-07-03
**Completed:** 2026-07-03

- [x] 1.1 — Grep the in-scope files for `categor`, `attribut`, `field`, `value` (case-insensitive)
      and collect every hit with file + line.
- [x] 1.2 — Close-read `evaluator.py`, `multivariate.py`, `scheme.py`, `charts.py`; classify each
      hit as artifact type (a)/(b)/(c)/(d) and verdict CORRECT/CONTRADICTORY/AMBIGUOUS.
- [x] 1.3 — Do the same for `config/analysis/comparison/{scb,istat}.json`,
      `config/mapping/{scb,istat}/*.json`, and the two mapping READMEs.
- [x] 1.4 — Cross-check each `category`/`categories` identifier actually holds *values* and each
      `attribute`/`attr`/`field` identifier actually holds a *dimension* (confirm by tracing the
      assignment, not the name).

**Files Modified:** none (audit only).

**Dependencies:** None.

### Phase 2: Decision table (locked vs. free)
**Goal:** A per-finding remediation decision honouring the invariants.

**Started:** 2026-07-03
**Completed:** 2026-07-03

- [x] 2.1 — Build the "locked names" inventory: `scheme.categories`/`attributes`, report
      `"categories"`, CSV `"attribute"`/`"unmapped_categories"`/`attr_x`/`attr_y`, config keys
      `"values"`/`"attributes"`/`"categories"`/`joint_pairs`/`coherence_attributes`/
      `combination_checks`/`grounded_joint_pairs`. Mark each "leave + document".
- [x] 2.2 — For each CONTRADICTORY/AMBIGUOUS *prose* finding, decide reword vs. leave; write the
      replacement text.
- [x] 2.3 — For each locked finding that reads imperfectly, draft its intentional-exception note.

**Files Modified:** this plan (findings table) — treated as the working record, not source.

**Dependencies:** Phase 1.

### Phase 3: Apply minimal fixes & document exceptions
**Goal:** Reconcile the free prose and record the locked exceptions; verify nothing logic-bearing moved.

**Started:** 2026-07-03
**Completed:** 2026-07-03

- [x] 3.1 — Apply the approved prose rewrites (docstrings / comments / READMEs / `basis` strings).
- [x] 3.2 — Add the "Terminology — intentional exceptions" note to
      `docs/architecture/comparison-metrics.md` listing the locked names and why they keep their
      wording.
- [x] 3.3 — `git diff` review: confirm zero changes to code identifiers used by logic, serialized
      fields, CSV headers, or config keys; run `pytest` and `ruff check src/`.

**Files Modified:** the prose files enumerated in Architecture Changes; `comparison-metrics.md`.

**Dependencies:** Phase 2.

---

## Testing Plan

### Unit Tests
- [x] No new unit tests (no behaviour change). The existing comparison suite is the regression
      guard.

### Integration Tests
- [x] `pytest` passes unchanged (confirms no serialized field / CSV header / config key was
      renamed — those are exercised by the existing `llm_metrics`/comparison tests and scheme
      loaders).

### Manual Verification
- [x] `git diff --stat` shows only doc/comment/README (and, at most, `basis`-string) changes.
- [x] Grep confirms `scheme.categories`, report `"categories"`, and config keys `"values"`/
      `"attributes"` are byte-for-byte unchanged.
- [x] A reader can hold `comparison-metrics.md` next to `evaluator.py`/`scheme.py` and find no
      prose that calls a dimension a "category" or a value a "field"/"attribute".

### Edge Cases
- [x] "field" used correctly as an alias for attribute (e.g. `charts.py`
      `_HIGH_CARDINALITY_FIELDS`) is left as-is and noted, not "corrected".
- [x] Secondary/domain senses of "field" (raw DB columns / sub-fields in mapping READMEs) are
      disambiguated in prose without implying they violate "field = attribute".
- [x] `config/mapping/ssb/`'s divergent `output_categories` key is explicitly recorded as
      out-of-scope, not silently pulled into the fix.

---

## Documentation Plan

- [x] Update `docs/architecture/comparison-metrics.md` — add the intentional-exceptions /
      locked-names note under the existing terminology callout.
- [x] No README.md / CLAUDE.md architecture change (no structural change).
- [x] No changelog entry required (docs/prose-only consistency pass).
- [x] Update inline comments/docstrings only where a prose finding is fixed.

---

## Rollback Plan

Trivial — the change set is prose-only and self-contained.

1. Before merge: the entire diff is reviewable in one pass; revert the branch if any edit is
   contested.
2. Data considerations: none — no migrations, no serialized-format change, no config-key change.
3. Rollback procedure: `git revert` the single squashed commit (or delete the feature branch
   pre-merge); no state/report regeneration needed since outputs are unaffected.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A "fix" accidentally renames a serialized report field or CSV header | Low | High | Locked-names inventory (Phase 2.1); Phase 3.3 `git diff` gate; `pytest` regression |
| A config-key reword breaks a fail-fast loader in `scheme.py` | Low | High | Config keys are all classified locked; edits restricted to `basis`/`description` documentation values, never keys |
| Editing a `basis` documentation string changes meaning a report consumer reads | Low | Med | Treat `basis`/`description` as prose but reword conservatively; keep semantics identical |
| Scope creep into ssb / GUI / generators terminology | Med | Low | Out-of-scope section is explicit; ssb noted as adjacent-only |
| Over-correcting a legitimate "field = attribute" alias | Med | Low | Edge-case rule: correct aliases are left and documented, not rewritten |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (audit) | ~half day | None |
| Phase 2 (decision table) | ~1–2 hours | Phase 1 |
| Phase 3 (apply + verify) | ~1–2 hours | Phase 2 |

---

## Appendix A — Preliminary audit findings (read-only pre-scan)

A first read of all four comparison modules, both analysis-config JSONs, the mapping
`_index.json` masters, a representative per-attribute mapping file, and both mapping READMEs
(plus a full-text grep of the config trees) produced these results. This is a starting point
for Phase 1, not a substitute for it.

**Bottom line:** no genuine contradictions found. Nowhere is a dimension called a "category";
nowhere is a value called an "attribute"/"field". Every `category`/`categories` identifier
holds values; every `attribute`/`attr`/`field` identifier holds a dimension.

### Locked names (CORRECT, breaking to rename)
- `scheme.py` L100–101 `ComparisonScheme.attributes` / `categories` — the canonical
  `scheme.categories[attr]`. Built/validated at L69–71, L151, L299–310, L342–351. Also
  `CombinationCheck.attributes` (L71), `GroundedJointPair.pair` (L56).
- `evaluator.py` L109/L153 serialized report field `"categories"` (list of values); CSV headers
  `"attribute"`, `"unmapped_categories"` (L570–585), `attr_x/attr_y/v_real/v_syn/abs_delta_v`
  (L604–613). All type (d), locked.
- `multivariate.py` L69, L151–154 `cats/cats_x/cats_y` from `scheme.categories[...]`; docstrings
  L18–21, L57–58, L144–149 use category=value, attribute=dimension. All CORRECT.
- Config keys (type c, locked, all CORRECT): `config/analysis/comparison/{scb,istat}.json` →
  `joint_pairs`, `coherence_attributes`, `grounded_joint_pairs`, `combination_checks.attributes`,
  `pair`; `config/mapping/{scb,istat}/*.json` → `"values"` (category-value set) and
  `_index.json` `"attributes"`.

### Ambiguous spots (worth a note; not contradictions)
- `charts.py` L24 `_HIGH_CARDINALITY_FIELDS` — holds attribute names; "field" is a valid alias,
  so CORRECT. Only place using the "field" alias as a code identifier (used L117, L432). A
  vocabulary-consistency nit at most — leave + note.
- `config/analysis/comparison/scb.json` L39, L44 — `basis` prose "field is not API-identical":
  "field" used loosely for the joint/data-source being described. AMBIGUOUS prose (type b).
- `config/mapping/scb/README.md` L52–54 "sub-fields" / "value block that keys sub-field names",
  `config/mapping/istat/README.md` L38 "composite sub-field matcher" — "sub-field" = raw DB
  record columns, a secondary sense. AMBIGUOUS prose.
- `config/mapping/scb/README.md` L111 "SCB provides the field", `istat/README.md` L58 "no
  income-source field" — "field" = the `income_source` attribute. CORRECT (field=attribute),
  noted only because the alias appears in prose.
- READMEs otherwise spot-checked CORRECT (scb L5/L25/L88/L107; istat L5/L27/L46/L61).

### Adjacent / out-of-scope
- `config/mapping/ssb/` uses `"output_categories"` (e.g. `civil_status.json:21`,
  `birth_country_detail.json:59`, `housing_tenure.json:16`) instead of scb/istat's `"values"`
  to hold category values. Semantically CORRECT but a cross-directory key-name inconsistency —
  flag only, do not change here.

---

## Phase 1 — Audit findings

Full sweep of the in-scope surface (grep + close read + assignment tracing). Artifact
types: **(a)** code identifier, **(b)** docstring/comment/README prose, **(c)** config key,
**(d)** serialized report field / CSV header / printed console label. Verdicts:
**CORRECT** (matches canonical attribute=dimension / category=value), **CONTRADICTORY**
(a dimension called a category or a value called an attribute/field), **AMBIGUOUS** (a
secondary/loose sense of "field" or "sub-field" — not a contradiction, worth a note).

**Bottom line:** **0 CONTRADICTORY**, **6 AMBIGUOUS**, all remaining hits CORRECT.
Appendix A's "no genuine contradictions" conclusion **holds** and is confirmed by
assignment tracing (task 1.4). Two prose hits Appendix A did not enumerate are added
below and flagged `[+A]`; neither is a contradiction.

### 1.4 assignment-tracing confirmation (the two load-bearing chains)
- `scheme.categories[attr]` ← `list(block["values"])` (`scheme.py` L310) and
  `{attr: list(vals) for attr, vals in raw["categories"].items()}` (L347) — holds **values**. CORRECT.
- `scheme.attributes` ← `list(index["attributes"].keys())` (`scheme.py` L298) — holds
  **dimension names**. CORRECT.
- Every `all_categories`/`cats`/`cats_x`/`cats_y`/`categories` local in `evaluator.py` &
  `multivariate.py` is built from `scheme.categories[...]` or a union of `attr_value(...)`
  outputs → **values**. Every `attrs`/`coherence_attrs`/`attr_x`/`attr_y`/`check.attributes`
  is a **dimension** name (iterated as the first arg to `attr_value(ind, attr)`). CORRECT.
- `charts._HIGH_CARDINALITY_FIELDS` is tested `attr in _HIGH_CARDINALITY_FIELDS`
  (L117, L432) → holds **attribute names**; "field" is the sanctioned attribute alias. CORRECT.

### Findings table

| File | Line | Token | Type | Verdict | Note |
|------|------|-------|------|---------|------|
| `evaluator.py` | 23 | comment "attributes, categories, joint pairs, coherence attributes" | b | CORRECT | Describes the comparison axis; attribute=dimension, category=value. |
| `evaluator.py` | 31 | "Derived-attribute access" | b | CORRECT | `age_group` dimension. |
| `evaluator.py` | 38 | `except (TypeError, ValueError)` | a | CORRECT | Python builtin exception, not the domain term. |
| `evaluator.py` | 42–43 | `attr_value(ind, attr)` / "an individual's value for *attr*" | a/b | CORRECT | Returns a category **value**. Canonical helper. |
| `evaluator.py` | 65 | `raise ValueError(` | a | CORRECT | Builtin exception. |
| `evaluator.py` | 82–84 | param `categories` / `for c in categories` | a | CORRECT | Iterates **values** (smoothing vector). |
| `evaluator.py` | 91–98 | `scheme.categories[attr]`, `all_categories`, `unmapped` | a | CORRECT | `all_categories` = value list; `unmapped` = synthetic-only **values**. |
| `evaluator.py` | 103–153 | `all_categories`, report field `"categories"` (L109, L153) | a/d | CORRECT | Serialized `"categories"` = list of values (locked, type d). |
| `evaluator.py` | 160 | `attrs = self.scheme.attributes` | a | CORRECT | Dimension list. |
| `evaluator.py` | 166–175 | `attr_value(ind, attr_x/attr_y)` | a | CORRECT | Cell keys are values; `attr_x`/`attr_y` are dimensions. |
| `evaluator.py` | 203–228 | `coherence_attrs`, `attr_value(ind, a)`, `"age_group"` | a/d | CORRECT | `coherence_attrs` = dimensions; keys/labels = values. |
| `evaluator.py` | 248–302 | `attr_value` refs, `"p_value"` (L289), `attrs=self.scheme.attributes` (L302) | a/b/d | CORRECT | `p_value` = statistical probability value; `attrs` = dimensions. |
| `evaluator.py` | 360–399 | `check.attributes` (L367), `"attributes": list(attrs)` (L399) | a/d | CORRECT | Tuple of **dimensions** (combination check). Serialized key locked. |
| `evaluator.py` | 470 | printed header `'Attribute'` | d | CORRECT | Console label over dimension names. |
| `evaluator.py` | 483 | "unmapped categories in B" | b/d | CORRECT | Printed prose; unmapped **values**. |
| `evaluator.py` | 523 | `c2st["p_value"]` | a | CORRECT | Statistical p-value. |
| `evaluator.py` | 555 | `chk["attributes"]` joined | a/d | CORRECT | Dimension names. |
| `evaluator.py` | 564–585 | CSV `fieldnames`, headers `"attribute"`, `"unmapped_categories"` | a/d | CORRECT | `fieldnames` = csv.DictWriter API term; `"attribute"` col holds dimension, `"unmapped_categories"` holds a count of **values**. Locked. |
| `evaluator.py` | 592–613 | CSV headers `attr_x`, `attr_y`, `v_real`, `v_syn`, `abs_delta_v` | d | CORRECT | `attr_x/attr_y` = dimensions; `v_*` = Cramér's V values. Locked. |
| `multivariate.py` | 5–25 | module docstring "attributes … category sets", "category set", "attribute pairs" | b | CORRECT | attribute=dimension, category=value throughout. |
| `multivariate.py` | 41 | `import attr_value` | a | CORRECT | Value-deriving helper. |
| `multivariate.py` | 50–68 | "scheme's attributes", `scheme.attributes`, `scheme.categories`, "category list" (L60–61,68) | a/b | CORRECT | One-hot over dimensions × their values. |
| `multivariate.py` | 69–78 | `cats = list(scheme.categories[attr])`, `attr_value(ind, attr)` | a | CORRECT | `cats` = values. |
| `multivariate.py` | 100–107 | "observed categories", `raise ValueError` (L105) | a/b | CORRECT | Cramér's V over value rows/cols; builtin exception. |
| `multivariate.py` | 144–158 | docstring "fixed category grid", `cats_x/cats_y = scheme.categories[...]`, "an attribute the scheme declares no categories for" | a/b | CORRECT | Grid axes are values; attribute=dimension. |
| `multivariate.py` | 229–235 | "Any other value fails loudly", `raise ValueError` | a/b | CORRECT | Generic "value" (method arg); builtin exception. |
| `multivariate.py` | 289–376 | `p_value`, `p_values`, `"p_value"` | a/d | CORRECT | Statistical p-value throughout C2ST. |
| `scheme.py` | 1–16 | module docstring "in-scope attributes and DB-exact category set(s)", "category list", "mapper-synthesized categories" | b | CORRECT | Canonical two-level usage. |
| `scheme.py` | 24–25 | "Its categories are the age-bin labels declared as `values`" | b | CORRECT | age_group values. |
| `scheme.py` | 46 | `GroundedJointPair` docstring "One attribute pair" | b | CORRECT | pair of dimensions. |
| `scheme.py` | 66–71 | `CombinationCheck` "`attributes` tuple", field `attributes: tuple[str, ...]` | a/b | CORRECT | Tuple of dimensions. |
| `scheme.py` | 87–103 | `ComparisonScheme` docstring + fields `attributes: list[str]`, `categories: dict[str, list[str]]`, `coherence_attributes` | a/b | CORRECT | attributes=dimensions; categories maps dimension→value list. The canonical `scheme.categories[attr]`. Locked. |
| `scheme.py` | 137–189 | `raise ValueError(...)`, `grounded_joint_pairs`, `combination_checks`, key `"attributes"`, `attributes=tuple(...)` | a/c | CORRECT | Config keys locked; builtin exceptions; `attributes` holds dimensions. |
| `scheme.py` | 203–256 | `coherence_attributes` loader, `raise ValueError` | a/c | CORRECT | Tuple of dimensions from config key. Locked. |
| `scheme.py` | 272–283 | docstring "in-scope attributes", "`values` list supplies that attribute's DB-grounded category set", "omits `values`" | b | CORRECT | Traces values→categories mapping in prose. |
| `scheme.py` | 294–325 | `attributes=list(index["attributes"].keys())`, `categories[attr]=list(block["values"])`, `raise KeyError` on missing `'values'` | a | CORRECT | **1.4 core chain**: attributes←index keys (dimensions), categories←`values` (values). |
| `scheme.py` | 342–364 | `for key in ("attributes","categories",...)`, `categories={attr: list(vals) ...}`, "declares attributes without categories" | a | CORRECT | Legacy flat-scheme loader; same mapping, dimension→values. |
| `charts.py` | 4–5 | docstring "per attribute", "per-dimension TV similarity" | b | CORRECT | attribute=dimension. |
| `charts.py` | 17 | `import attr_value` | a | CORRECT | Value helper. |
| `charts.py` | 24 | `_HIGH_CARDINALITY_FIELDS = frozenset({...})` | a | AMBIGUOUS | Holds **attribute names**; "field" is the sanctioned attribute alias, so CORRECT-by-alias. Only code identifier using the "field" alias (used L117, L432). Leave + note (edge-case rule). |
| `charts.py` | 57–66 | `attr_value(ind, attr)`, `counts.values()`, `_close_polygon(values)` | a | CORRECT | `counts.values()` = dict API; `values` param = numeric series, not domain term. |
| `charts.py` | 82–148 | params `attributes`, `categories`, `all_categories`, `cat in all_categories` | a | CORRECT | attributes=dimensions; categories/all_categories=values. |
| `charts.py` | 117, 432 | `attr in _HIGH_CARDINALITY_FIELDS` | a | CORRECT | Membership test over dimensions (see L24). |
| `charts.py` | 180–309 | `attributes` params, "needs >=3 attributes", `attr_x`/`attr_y` (L310), "Attribute order" | a/b | CORRECT | Dimensions throughout; `results.values()` = dict API. |
| `charts.py` | 391–455 | `attributes`, `all_categories`, `vals`, `n_cats` | a | CORRECT | 3-way bar chart; attributes=dimensions, categories=values. |
| `charts.py` | 477–578 | `attributes` params, "needs >=3 attributes", `results.values()` | a/b | CORRECT | Radar helpers; dimensions. |
| `config/analysis/comparison/scb.json` | 2 | `description` "cross-attribute statistics", "{attributes, k, threshold}" | b/c | CORRECT | Prose + key names describe dimensions. |
| `config/analysis/comparison/scb.json` | 3–8 | keys `joint_pairs`, `coherence_attributes` (values = dimension names) | c | CORRECT | Locked config keys; hold dimension pairs/tuples. |
| `config/analysis/comparison/scb.json` | 10–35 | `grounded_joint_pairs`, `pair`, `grounded`, `basis` (grounded=true entries) | c/b | CORRECT | Keys locked; `basis` prose reads correctly. |
| `config/analysis/comparison/scb.json` | 39 | `basis` "…but sex pooled; **field** is not API-identical" | b | AMBIGUOUS | "field" = the joint/data-source loosely; not attribute=dimension. Documentation-only value. Reword candidate (Phase 3). |
| `config/analysis/comparison/scb.json` | 44 | `basis` "sex pooled and education ignored; **field** is not API-identical" | b | AMBIGUOUS | Same loose "field" sense as L39. |
| `config/analysis/comparison/scb.json` | 49 | `basis` "…across all education **levels** -> forced independence" | b | CORRECT | "levels" = education_level values. |
| `config/analysis/comparison/scb.json` | 52–56 | `combination_checks` → `attributes` (dimension tuple), `k`, `threshold` | c | CORRECT | Locked key; holds dimensions. |
| `config/analysis/comparison/istat.json` | 2 | `description` "No **per-field** ISTAT grounding audit" | b | AMBIGUOUS | `[+A]` Not enumerated in Appendix A. "per-field" = per-attribute (field=attribute alias); loose but not contradictory. |
| `config/analysis/comparison/istat.json` | 3–17 | `joint_pairs`, `coherence_attributes`, `grounded_joint_pairs` (empty), `combination_checks.attributes` | c | CORRECT | Locked keys; dimensions. |
| `config/mapping/scb/_index.json` | 2 | `description` "comparison attributes -> per-attribute config files" | b | CORRECT | `[+A]` description string (Appendix A cited the `attributes` key, not this prose). attribute=dimension. |
| `config/mapping/scb/_index.json` | 3 | key `"attributes"` (dimension→filename map) | c | CORRECT | Locked master key; keys are dimensions. |
| `config/mapping/scb/*.json` (16 files) | — | key `"values"` (category-value set + axis order) | c | CORRECT | Each holds that attribute's **values**. Locked. Confirmed via glob (16 `values` files). |
| `config/mapping/istat/_index.json` | 2–3 | `description` + `"attributes"` key | b/c | CORRECT | Same as scb; dimensions. |
| `config/mapping/istat/*.json` (15 files) | — | key `"values"` | c | CORRECT | Category-value sets. Locked. |
| `config/mapping/scb/README.md` | 5–6, 88–90 | "for which categories each attribute is scored on", "in-scope comparison attributes" | b | CORRECT | attribute=dimension, category=value. |
| `config/mapping/scb/README.md` | 25 | "`values` — the unified category set **and** the chart/axis order" | b | CORRECT | values = category-value set. |
| `config/mapping/scb/README.md` | 52–54 | "raw DB record has **sub-fields** (`attachment`+`hours`)", "keys sub-field names" | b | AMBIGUOUS | "sub-field" = raw DB record columns, a secondary DB sense (not attribute). Clarify-prose candidate. |
| `config/mapping/scb/README.md` | 69–77, 92, 98–108 | "Attribute-level directives", "sibling attribute", "cross-attribute statistics", "comparison categories" | b | CORRECT | Consistent canonical usage. |
| `config/mapping/scb/README.md` | 111 | "SCB provides the **field**" | b | CORRECT | field = the `income_source` attribute (field=attribute alias). |
| `config/mapping/istat/README.md` | 5, 27, 46 | "which categories each attribute", "`values` — the unified category set", "in-scope attributes" | b | CORRECT | Canonical usage. |
| `config/mapping/istat/README.md` | 38 | "composite **sub-field** matcher (`employment_type`)" | b | AMBIGUOUS | Same secondary "sub-field" DB sense as scb README L52–54. |
| `config/mapping/istat/README.md` | 58 | "ISTAT provides no income-source **field**" | b | CORRECT | field = the `income_source` attribute. |
| `config/mapping/istat/README.md` | 61–69 | "keeps categories Sweden drops", "`values` are human-readable labels" | b | CORRECT | category=value. |
| `docs/architecture/comparison-metrics.md` | 13–36 | canonical Terminology callout + "categorical attributes", "allowed categories", "one attribute at a time" | b | CORRECT | The reference definition itself; internally consistent. |

### AMBIGUOUS inventory (6, all type b prose — Phase 2/3 decide reword vs. leave)
1. `charts.py` L24 `_HIGH_CARDINALITY_FIELDS` — "field" alias code identifier (leave + note per edge-case rule).
2. `config/analysis/comparison/scb.json` L39 `basis` "field is not API-identical".
3. `config/analysis/comparison/scb.json` L44 `basis` "field is not API-identical".
4. `config/analysis/comparison/istat.json` L2 `description` "per-field ISTAT grounding" `[+A]`.
5. `config/mapping/scb/README.md` L52–54 "sub-fields" / "sub-field names".
6. `config/mapping/istat/README.md` L38 "composite sub-field matcher".

### Appendix A verification
- All Appendix A locked-name and CORRECT claims **confirmed** by re-read + assignment tracing.
- Appendix A's AMBIGUOUS spots (charts L24; scb.json basis L39/L44; scb/istat README sub-field
  prose; scb README L111 / istat README L58 "field"=attribute) all **reproduced**.
- **Additions Appendix A did not enumerate** (`[+A]`, neither a contradiction): istat.json L2
  "per-field" prose; the `_index.json` `description` prose strings (scb & istat L2).
- **No genuine contradictions** — Appendix A's bottom line **holds**.

---

## Phase 2 — Decision table

Authoritative spec for Phase 3. Every finding from the Phase 1 table is resolved here into
either a **locked-names inventory** entry ("leave + document") or a **prose remediation**
decision (REWORD / LEAVE). No source/config/canonical-doc edits are made in this phase —
this section only *decides* and drafts copy-paste-ready replacement text and the
intentional-exception note.

**Summary of decisions:** 2 prose findings REWORD (both `scb.json` `basis` strings, L39 & L44);
4 AMBIGUOUS spots LEAVE + document; 20 locked-name identifiers/keys in the inventory (all
"leave + document").

### 2.1 Locked-names inventory (all "leave + document")

Every entry is a type (a) code identifier, (c) config key, or (d) serialized/CSV/printed field
that logic or an external consumer depends on. Renaming any of them is a breaking migration
(explicitly Out of Scope) and would violate config-as-source-of-truth and/or fail-fast. All are
CORRECT under the canonical vocabulary (or CORRECT-by-alias for the one `field` identifier);
they are listed so future contributors have a single record of what intentionally keeps its
current wording.

| Identifier / Key | Artifact type | File(s) | Decision | Rationale |
|------------------|---------------|---------|----------|-----------|
| `ComparisonScheme.attributes` | (a) dataclass field | `scheme.py` L100 (built L298) | leave + document | Canonical dimension list; consumed across evaluator/charts/multivariate. |
| `ComparisonScheme.categories` | (a) dataclass field | `scheme.py` L101 (built L310, L347) | leave + document | The canonical `scheme.categories[attr]` value map; the vocabulary anchor itself. |
| `ComparisonScheme.coherence_attributes` | (a) dataclass field | `scheme.py` L87–103 | leave + document | Holds dimension tuples; loaded from the locked config key. |
| `CombinationCheck.attributes` | (a) dataclass field | `scheme.py` L66–71 | leave + document | Tuple of dimensions; serialized back out under `"attributes"`. |
| `GroundedJointPair.pair` | (a) dataclass field | `scheme.py` L46, L56 | leave + document | Dimension pair; mirrors config `pair` key. |
| `_HIGH_CARDINALITY_FIELDS` | (a) module constant | `charts.py` L24 (used L117, L432) | leave + document | Holds **attribute names**; `field` is the sanctioned attribute alias (edge-case rule). Only code identifier using the alias. |
| report field `"categories"` | (d) serialized JSON | `evaluator.py` L109, L153 | leave + document | List of **values**; read by downstream report consumers. |
| report field `"attributes"` | (d) serialized JSON | `evaluator.py` L399 | leave + document | Combination-check dimension tuple; serialized contract. |
| CSV header `"attribute"` | (d) CSV column | `evaluator.py` L570–585 | leave + document | Marginals column holding dimension names. |
| CSV header `"unmapped_categories"` | (d) CSV column | `evaluator.py` L570–585 | leave + document | Count of synthetic-only **values**; header is a consumed contract. |
| CSV headers `attr_x`, `attr_y`, `v_real`, `v_syn`, `abs_delta_v` | (d) CSV columns | `evaluator.py` L604–613 | leave + document | `attr_x/attr_y` = dimensions, `v_*` = Cramér's V values. |
| printed header `'Attribute'` | (d) console label | `evaluator.py` L470 | leave + document | Human-facing label over dimension names; not a logic identifier but a stable printed contract. |
| config key `"values"` | (c) config key | `config/mapping/{scb,istat}/*.json` (31 files) | leave + document | Each holds an attribute's **value** set + axis order; read by `scheme.py`'s fail-fast loader (`raise KeyError` on missing). |
| config key `"attributes"` (master index) | (c) config key | `config/mapping/{scb,istat}/_index.json` | leave + document | Dimension→filename map; `scheme.attributes` ← `index["attributes"].keys()`. |
| config key `"attributes"` (combination check) | (c) config key | `config/analysis/comparison/{scb,istat}.json` | leave + document | Dimension tuple inside `combination_checks`. |
| config key `"categories"` (legacy flat scheme) | (c) config key | consumed by `scheme.py` L342–364 | leave + document | Legacy flat-scheme loader reads `raw["categories"]` (dimension→values); locked loader contract. |
| config key `joint_pairs` | (c) config key | `config/analysis/comparison/{scb,istat}.json` | leave + document | Dimension-pair list; loader contract. |
| config key `coherence_attributes` | (c) config key | `config/analysis/comparison/{scb,istat}.json` | leave + document | Dimension tuple; fail-fast loader key. |
| config key `grounded_joint_pairs` (+ `pair`, `grounded`, `basis`) | (c) config key | `config/analysis/comparison/{scb,istat}.json` | leave + document | Structural keys read by the scheme loader; only the `basis` *value strings* are free prose (see 2.2). |
| config key `combination_checks` (+ `k`, `threshold`) | (c) config key | `config/analysis/comparison/{scb,istat}.json` | leave + document | Generalised coherence-check config block; loader contract. |

**Note (out of scope, not locked-here):** `config/mapping/ssb/*.json` uses `"output_categories"`
instead of scb/istat's `"values"` for its value sets. Semantically CORRECT but a cross-directory
key-name inconsistency; recorded as adjacent/out-of-scope per Appendix A — not part of this
inventory and not to be touched in Phase 3.

### 2.2 Prose remediation (CONTRADICTORY / AMBIGUOUS type-(b) findings)

0 CONTRADICTORY findings exist, so every row below is one of the 6 AMBIGUOUS prose spots.
Conservative rule applied: reword only where the loose `field` sense genuinely clashes with the
canonical `field = attribute` and the reword keeps semantics identical. Result: **2 REWORD, 4
LEAVE**.

| Finding (file:line) | Current text | Decision | Replacement text (exact) | Rationale |
|---------------------|--------------|----------|--------------------------|-----------|
| `config/analysis/comparison/scb.json` L39 | `"education_by_age (audit §2, 'conditioning lost'): education conditional on age_group but sex pooled; field is not API-identical."` | **REWORD** | `"education_by_age (audit §2, 'conditioning lost'): education conditional on age_group but sex pooled; the joint is not API-identical."` | `field` here loosely means the derived joint cross-tab, not a dimension — the exact loose usage this pass targets. `the joint` matches the `grounded_joint_pairs` framing (a joint over a `pair`); semantics identical. `basis` is a documentation-only value, not logic-consumed. |
| `config/analysis/comparison/scb.json` L44 | `"employment_by_age (audit §3): sex pooled and education ignored; field is not API-identical."` | **REWORD** | `"employment_by_age (audit §3): sex pooled and education ignored; the joint is not API-identical."` | Same loose `field`=joint sense as L39; identical reword for consistency and identical semantics. |
| `charts.py` L24 `_HIGH_CARDINALITY_FIELDS` | `_HIGH_CARDINALITY_FIELDS = frozenset({...})` | **LEAVE** | — | Locked code identifier holding attribute names; `field` is the sanctioned attribute alias (canonical doc states "attribute (also called a *field*)"). Renaming is out of scope and pointless. Documented in the 2.3 exception note. |
| `config/analysis/comparison/istat.json` L2 `description` | `"...No per-field ISTAT grounding audit exists yet..."` | **LEAVE** | — | `per-field` = per-attribute, using the sanctioned `field = attribute` alias correctly; reads fine and is not contradictory. Conservative rule → no change. |
| `config/mapping/scb/README.md` L52–54 | `"...for `employment_type`, whose raw DB record has sub-fields (`attachment` + `hours`). A value block that keys sub-field names..."` | **LEAVE** | — | `sub-field` is the secondary raw-DB-column sense, already disambiguated in-place by "raw DB record has sub-fields". Rewording (e.g. to "sub-columns") would reduce clarity, not improve it. Documented as an intentional secondary sense in 2.3. |
| `config/mapping/istat/README.md` L38 | `"...plus the composite sub-field matcher (`employment_type`)."` | **LEAVE** | — | Same secondary raw-DB-column sense; `sub-field matcher` is a matcher-type name mirroring the scb README's `employment_type` composite matcher. Consistent and non-contradictory; documented in 2.3. |

### 2.3 Drafted intentional-exception note (for Phase 3 → `comparison-metrics.md`)

Insert the block below into `docs/architecture/comparison-metrics.md` immediately **after** the
existing `> **Terminology — attribute vs. category ...`** callout (currently ending ~L29), before
the "The metrics come in four families:" paragraph. Copy-paste ready:

```markdown
> **Terminology — intentional exceptions (locked names).** A few identifiers, config keys,
> and output fields keep wording that does not read literally as "attribute"/"category". They
> are **contracts** — code identifiers exercised by logic, config keys read by fail-fast
> loaders, or serialized report/CSV headers consumed downstream — so renaming them would be a
> breaking migration, not a cleanup. They are all *correct* under the definitions above (or
> correct via the sanctioned `attribute` ⇄ `field` alias); they are listed here so the wording
> never gets "corrected" by mistake:
>
> - **`field` as an alias for attribute.** `charts._HIGH_CARDINALITY_FIELDS` (a set of
>   *attribute* names) and prose such as "SCB provides the field" / "no income-source field" /
>   "per-field grounding audit" all use `field` = attribute, exactly as this callout permits.
> - **`scheme.categories[attr]` / `scheme.attributes`.** `categories` maps each attribute to its
>   list of *values*; `attributes` is the list of dimensions. This is the vocabulary anchor and
>   stays as-is.
> - **Serialized report fields `"categories"` and `"attributes"`, and CSV headers `"attribute"`,
>   `"unmapped_categories"`, `attr_x` / `attr_y` / `v_real` / `v_syn` / `abs_delta_v`.** These are
>   the report/CSV contract; `"categories"` lists values, `"attribute(s)"` lists dimensions.
> - **Config keys `values`, `attributes`, `categories`, `joint_pairs`, `coherence_attributes`,
>   `grounded_joint_pairs`, `combination_checks`.** Read by the scheme loader, which raises on a
>   missing key. `values` always holds an attribute's *value* set (SSB's divergent
>   `output_categories` key is a separate, out-of-scope inconsistency).
> - **`sub-field` (raw DB columns).** In the mapping READMEs, `employment_type`'s raw record has
>   *sub-fields* (`attachment` + `hours`) matched by a "composite sub-field matcher". This is the
>   raw source-column sense of "field", distinct from `field = attribute`; it does not describe a
>   comparison attribute.
```

---

## References

- Canonical definitions: `docs/architecture/comparison-metrics.md` (Terminology callout, L20–29)
- Comparison code: `src/population_synthetic/analysis/comparison/{evaluator,multivariate,scheme,charts}.py`
- Config: `config/analysis/comparison/{scb,istat}.json`, `config/mapping/{scb,istat}/`
- Related invariants: CLAUDE.md "Core Invariants" (config as single source of truth; fail-fast)

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/analysis/comparison/scb.json
- docs/architecture/comparison-metrics.md
- docs/development/plans/active/investigate-attribute-category-terminology.md

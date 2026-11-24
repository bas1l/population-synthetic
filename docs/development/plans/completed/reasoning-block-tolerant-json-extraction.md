# Plan: Reasoning-Block-Tolerant JSON Extraction

**Date:** 2026-08-04
**Author:** Basil
**Status:** Completed
**Completed:** 2026-08-04 14:20
**Base Branch:** `dev`
**Branch:** `fix/reasoning-block-json-extraction`

---

## Overview

Reasoning models served over OpenRouter (observed: `qwen/qwen3.5-flash-02-23`) return their
chain-of-thought as literal text inside `message.content`, terminated by a bare `</think>` with the
opening tag suppressed. `_extract_json` has no notion of that block, so it scans the *reasoning*
for JSON and either finds nothing (retry storm) or finds a stray array quoted mid-thought (persona
crash). This plan makes the extractor strip the reasoning block, makes its fallback object scan
brace-balanced and last-first, and converts a wrong-shaped parse from a persona-killing
`AttributeError` into an ordinary retriable parse failure.

## Problem Statement

Measured over `01_Raw/swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`,
run `logs/run_20260804_103034.log` (3492 LLM calls, all made 2026-08-04):

| Observation | Count |
|---|---|
| Responses containing `</think>` | 3480 / 3492 |
| Responses containing `<think>` | **0** |
| Calls that failed JSON parse | **3080 (88%)** |
| Failed parses whose text after `</think>` **is** valid JSON | **3071 / 3071** |
| Completion tokens consumed | **18.1 M** |
| Personas killed outright | 11 (`'list' object has no attribute 'get'`) |

Median raw response: ~17 300 characters, nearly all of it reasoning, with the correct JSON at the
very end. The model answered correctly essentially every time; the pipeline discarded the answer.

Two distinct failure modes, both rooted in `_extract_json`
(`src/population_synthetic/generators/synthetic/resolution_context.py:37`):

1. **Wrong value silently accepted.** Step 3 runs `re.search(r"\{[^{}]*\}")` over the *entire*
   text — reasoning included — and takes the **first** non-nested brace pair. The model habitually
   quotes the prompt's own schema sketch (`{"distribution": "normal"|"uniform"|"beta", ...}`),
   which is not valid JSON. The loop then abandons the object pattern entirely and falls to
   `r"\[.*?\]"`, which matches a throwaway array from the prose — e.g. `[0, 1]` in a sentence about
   the Beta support. Verified on `persona_00458`: `parsed_value` was recorded as `[0, 1]` while the
   response ended with `{"distribution": "uniform"}`.
2. **Retry storm.** Where no array matches either, the call raises `No valid JSON found in
   response` and is retried against the `retry_until_success` ceiling (100 attempts here), each
   attempt regenerating ~17 k tokens and failing identically. This is where the 18.1 M tokens went.

Mode 1 then escalates: `NumericDistributionCategory.resolve` (`category.py:429`) calls
`spec.get("distribution", "uniform")` on the list. That raises `AttributeError`, which is **not** in
`call_json`'s `except (json.JSONDecodeError, KeyError, RuntimeError)` tuple, so it escapes the retry
budget entirely and kills the persona at its *first* category — logged as
*"Category 'age' … failed after resolving 0/N categories"*.

Why it matters: every reasoning-capable model in the sweep is affected, the failure is silent in
mode 1 (a persona records a value the model never chose), and the token cost makes the affected
arms unusable for the cost/latency figures `generation_metadata` reports.

## Goals

### In Scope

1. `_extract_json` recovers the answer from a response that carries a reasoning block, whether the
   block is closed by a bare `</think>` or wrapped in a `<think>…</think>` pair.
2. The fallback scan can never prefer a JSON fragment quoted inside prose over the real answer that
   follows it.
3. A parsed value whose shape contradicts the caller's declared `response_schema` becomes a
   retriable parse failure recorded as `invalid_response`, not an uncaught `AttributeError`.
4. Regression tests pinned to the actual failing responses from the 2026-08-04 run.

### Out of Scope

- **Retry-budget policy.** The 100-attempt ceiling amplified a deterministic bug into 18.1 M
  wasted tokens. Capping retries on repeated-identical failure is a real improvement but is a
  policy change to `clients/retry_policy.py`, separately reviewable. Noted, not done here.
- **Provider-side reasoning suppression** (OpenRouter's `reasoning: {"exclude": true}`). It is
  model- and provider-specific; the extractor fix must stand on its own so the pipeline stays
  provider-agnostic. May be added later as belt-and-braces.
- **Re-running the affected combos.** Regenerating `swedish_02_*_qwen35_flash` is an operational
  decision after the fix lands.
- **A general "reasoning tag" registry** (config-driven list of markers per model). YAGNI: one
  marker is observed, and a config surface for it would have to be threaded from the model axis
  YAML through the client into the extractor for no present benefit.

## Success Criteria

- [x] Replaying `_extract_json` over every `raw_response` in the 2026-08-04 run yields a parseable
      value for ≥ 3071 of the 3080 previously-failing calls (the 9 with no `</think>` at all are
      genuinely truncated and must still raise). *(3072 of the 3082 the replay finds failing;
      10 truncated responses still raise — see the completion note for the 3080/3082 and 9/10
      discrepancies.)*
- [x] No call in that replay returns a `list` where the call site declared an object schema.
      *(0 lists after, 15 before; every one of the 3482 successes is a `dict`.)*
- [x] `pytest tests/test_resolution_context.py tests/test_category.py` passes.
- [x] `pytest` (full suite) passes — no existing extraction behaviour regresses. *(1303 passed;
      the 3 failures are pre-existing and unrelated — `test_ollama_host_composition.py` ×2 and
      `test_workflow_state.py::test_dep_incomplete_blocks_then_mark_completed_unlocks`, all caused
      by uncommitted working-tree edits to config files.)*
- [x] `ruff check src/` clean.

## Definitions

- **Reasoning block**: the leading span of a response ending at the last occurrence of the literal
  string `</think>`. Testably: `raw.rsplit("</think>", 1)[0]` when that substring is present, else
  empty. The opening `<think>` is *not* required to be present — the observed model emits the
  closing tag only.
- **Answer payload**: what remains after the reasoning block is removed, stripped of surrounding
  whitespace. If that is the empty string, the response is treated as having no payload and the
  original text is re-scanned (so a model that emits JSON *before* a stray `</think>` is not lost).
- **Wrong-shaped parse**: a value whose Python type does not match the JSON type named by the
  caller's `response_schema["type"]` — `object`→`dict`, `array`→`list`. Only these two are checked;
  any other declared type, or an absent `response_schema`, imposes no shape constraint.
- **Retriable**: raised as `json.JSONDecodeError` so `call_json`'s existing `except` tuple catches
  it, records the attempt with `error_category="invalid_response"`, and spends one unit of budget.

---

## Technical Design

### Approach

Fix it in `_extract_json` — the single function every JSON-constrained call already funnels
through — plus one shape guard at the same seam in `call_json`. No call site changes, no client
changes, no config changes.

This keeps the **error boundary** where it already is (guide `02`, error-boundaries): the
resolution context owns "turn a raw response into a value, or fail retriably", and the category
layer stays ignorant of provider quirks. Putting the strip in `OpenAICompatClient` was rejected
because it would make one provider's client responsible for a model-family behaviour that Ollama-
served reasoning models exhibit too, splitting one concern across two layers.

The shape guard is driven by the `response_schema` the caller **already declares** — no new
per-call-site type literals, consistent with the repo's no-hardcoded-fallbacks rule.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Strip in `_extract_json` + schema-typed shape guard in `call_json` | One seam; provider- and model-agnostic; both failure modes closed; `category.py` untouched | Extractor grows a model-behaviour concern | **Chosen** |
| Strip in `OpenAICompatClient` before returning content | Keeps extractor pure | Same quirk appears via Ollama → duplicated logic in two clients; raw telemetry would lose the reasoning text | Rejected |
| Send OpenRouter `reasoning: {"exclude": true}` | No parsing change | Provider-specific; leaves the extractor still fooled by any model that inlines reasoning; doesn't fix the list-crash | Rejected as *the* fix; possible later addition |
| Guard `spec.get(...)` at `category.py:429` | Smallest diff | Fixes one call site of six; leaves the extractor returning wrong-typed values elsewhere; treats a symptom | Rejected |
| Config-driven reasoning-marker registry per model axis | Extensible | No second marker observed; threads config through three layers for nothing | Rejected (YAGNI) |

### Architecture & Module Contracts

No new modules. Two functions change contract; one gains a helper.

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `_strip_reasoning(text)` *(new, private)* | Reduce a raw response to its answer payload | `str` → `str` (original text when the payload would be empty) | JSON, schemas, providers, categories |
| `_iter_json_candidates(text)` *(new, private)* | Yield balanced `{…}` spans, **last-first** | `str` → `Iterator[str]` | JSON validity, schemas, callers |
| `_extract_json(text)` *(changed)* | Raw response → parsed JSON value | `str` → `dict \| list`, raises `json.JSONDecodeError` | Which model/provider produced the text; what the value means |
| `ResolutionContext.call_json` *(changed)* | Prompt → validated value, with budget and telemetry | prompt + optional `response_schema`/`expected_key` → value | How the text was formatted; which category asked |

Signatures that change: none public. `_extract_json` keeps its `(text: str) -> dict | list`
signature and its `json.JSONDecodeError` failure mode, so `call_json`'s `except` tuple and every
existing caller are unaffected.

```
src/population_synthetic/generators/synthetic/resolution_context.py
  _strip_reasoning(text)          # new
  _iter_json_candidates(text)     # new
  _extract_json(text)             # steps 0..4
  _check_shape(parsed, schema)    # new; raises json.JSONDecodeError on mismatch
  ResolutionContext.call_json     # calls _check_shape after _extract_json
```

New `_extract_json` order:

0. `text = _strip_reasoning(text)`
1. direct `json.loads`
2. markdown fence (unchanged regex, now applied to the payload only)
3. `_iter_json_candidates` last-first; return the first that parses
4. bare-array regex — **only** if step 3 produced no parseable object
5. raise `json.JSONDecodeError("No valid JSON found in response", text, 0)`

Step 4's demotion is what makes a prose `[0, 1]` unable to outrank a real object. Step 3's
last-first order is what makes a trailing answer beat a quoted schema sketch.

---

## Implementation Plan

### Phase 1: Reasoning-block strip

**Goal:** A response carrying a reasoning block parses to the answer that follows it.

- [x] 1.1 — Add `_strip_reasoning(text)`: if `</think>` is present, take
      `text.rsplit("</think>", 1)[-1]`; return the original text when the result strips to empty.
      Docstring states *why* (reasoning models inline chain-of-thought in `message.content` with the
      opening token suppressed) and cites the 2026-08-04 qwen3.5-flash observation.
- [x] 1.2 — Call it as step 0 of `_extract_json`; leave steps 1–3 otherwise untouched in this phase.
- [x] 1.3 — Update the `_extract_json`/module docstring to name the new step order.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/resolution_context.py` — new `_strip_reasoning`, step 0 in `_extract_json`, docstrings

**Dependencies:** None

### Phase 2: Brace-balanced, last-first candidate scan

**Goal:** No JSON fragment quoted inside prose can outrank the real answer.

- [x] 2.1 — Add `_iter_json_candidates(text)`: single left-to-right pass tracking brace depth and
      string/escape state, collecting balanced `{…}` spans; yield them **reversed**.
- [x] 2.2 — Replace step 3's `re.search(r"\{[^{}]*\}")` with a loop over `_iter_json_candidates`
      that tries **every** candidate rather than abandoning the pattern after one failed parse.
- [x] 2.3 — Demote the bare-array pattern to step 4, reached only when step 3 yields nothing
      parseable. Comment records that a stray array in prose must never outrank an object.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/resolution_context.py` — new `_iter_json_candidates`, rewritten steps 3–4

**Dependencies:** Phase 1

### Phase 3: Wrong-shaped parse becomes retriable

**Goal:** A list where an object was declared costs one retry, not a persona.

- [x] 3.1 — Add `_check_shape(parsed, response_schema)`: when `response_schema["type"]` is
      `"object"` and `parsed` is not a `dict`, or `"array"` and not a `list`, raise
      `json.JSONDecodeError` naming the declared and actual types. No `response_schema`, or any
      other declared type → no constraint.
- [x] 3.2 — Call it in `call_json` immediately after `_extract_json`, **before**
      `_extract_expected_key`, and unconditionally on `response_schema` — *not* gated on
      `use_structured_output`, which only controls whether the schema is sent to the provider.
- [x] 3.3 — Confirm no call site needs changing: all six `ctx.call_json(...)` sites in `category.py`
      (lines 272, 316, 345, 361, 378, 423) declare `"type": "object"`. Only the `distribution` site
      (423) passes `expected_key=None` and is therefore the only one that could reach `.get()` on a
      list — leave `category.py:429` as-is.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/resolution_context.py` — new `_check_shape`, one call in `call_json`, docstring note on the new retriable case

**Dependencies:** Phase 2

### Phase 4: Tests and verification

**Goal:** Both failure modes pinned by tests taken from the real responses.

- [x] 4.1 — New `tests/test_resolution_context.py` with fixtures excerpted from
      `persona_00458/llm_interactions.jsonl` of the 2026-08-04 run.
- [x] 4.2 — Replay `_extract_json` over the run's `llm_interactions.jsonl` files and record the
      before/after counts in the plan's completion note.

**Files Modified:**
- `tests/test_resolution_context.py` — new

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests

- [x] Reasoning prose + `</think>` + `{"distribution": "uniform"}` → the dict.
- [x] Reasoning containing a stray `[0, 1]` **and** an invalid schema sketch
      `{"distribution": "normal"|"uniform"|"beta"}`, with the real object last → the object, not the
      list. *(Regression pin for `'list' object has no attribute 'get'`.)*
- [x] Paired `<think>…</think>` wrapper → the trailing object.
- [x] Two `</think>` occurrences → payload after the **last** one.
- [x] `</think>` with nothing after it → raises `json.JSONDecodeError`.
- [x] JSON present *before* a stray `</think>` and nothing after → still extracted (empty-payload
      fallback).
- [x] Unchanged behaviour: bare object; fenced ```json object; nested object; bare array with no
      object anywhere.
- [x] Brace inside a JSON string value (`{"note": "a } brace"}`) → parsed correctly by the balanced
      scanner.
- [x] `_check_shape`: list vs `"type": "object"` → `JSONDecodeError`; dict vs `"object"` → passes;
      no schema → passes.

### Integration Tests

- [x] `call_json` with an object schema against a stub client returning a list: retries within
      budget, records `error_category="invalid_response"`, never raises `AttributeError`.
- [x] `call_json` against a stub client returning reasoning-then-JSON: succeeds on attempt 1 and
      records one telemetry entry with the correct `parsed_value`.
- [x] `NumericDistributionCategory.resolve` end-to-end against that reasoning stub → a value inside
      `[min, max]`. *(The class is `GenerateEvaluateRandomPickCategory`; its numeric branch is the
      distribution call site the plan names.)*

### Manual Verification

- [x] Replay script over the 2026-08-04 run's JSONL: previously 3080 failures / 3492 calls; expect
      ≤ 9 failures after the fix and zero list-typed results. *(10 failures after, all truncated;
      zero lists. See the completion note.)*
- [ ] Short live run: `python scripts/generate/generate_identities_parallel.py --model-id
      openrouter_qwen35_flash --strategy-id all_generate_evaluate_random_pick_v2 --country-id
      swedish --n 5 --force` — expect no `No valid JSON` warnings and no persona FAIL lines.

### Edge Cases

- [x] Response that is *only* a reasoning block (no closing tag, truncated at max tokens) → raises,
      retried, unchanged from today.
- [x] Unbalanced trailing `{` after `</think>` → falls through to the array step, then raises.
- [x] Non-reasoning models (claude/gemini paths): text without `</think>` takes the identical path
      it takes today.

---

## Documentation Plan

- [x] Inline docstrings in `resolution_context.py` — the module docstring already advertises
      "the JSON-extraction fallbacks"; extend it with the reasoning-strip step and the shape guard.
- [x] `docs/development/debugging-identity-generation.md` — add a short "reasoning models" note:
      what `</think>` in `raw_response` means and that the extractor now strips it.
- [x] No `README.md` change (no new command or flag).
- [x] No `CLAUDE.md` change — no invariant, config surface, or DAG stage moves.

---

## Rollback Plan

1. **Before merge:** the branch touches two files. `git revert` of the phase commits, or
   `git checkout dev -- src/population_synthetic/generators/synthetic/resolution_context.py`,
   restores the prior behaviour exactly.
2. **Data considerations:** no migration, no schema change, no on-disk format change. Personas
   already generated are untouched; the fix only changes how *future* responses are parsed.
   Resume fingerprints (strategy/schema/model/category-order) are unaffected, so a partially
   generated combo resumes across the fix without discarding checkpoints.
3. **Rollback procedure:** revert the branch merge commit. No state reset required.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Last-first ordering breaks a model that emits the answer *first* then commentary | Low | Med | Step 1 (direct parse) still wins for clean responses; unchanged-behaviour tests cover bare/fenced objects; observed models all put the answer last |
| Balanced-brace scanner mishandles braces inside string values | Med | Med | Scanner tracks string/escape state; dedicated unit test for `{"note": "a } brace"}` |
| `_check_shape` rejects a response some existing model legitimately returns | Low | Med | Only `object`/`array` are checked, only when the caller declared them; all six call sites declare `object` and every current consumer indexes it as a dict |
| A model emits `</think>` inside a legitimate JSON string value | Very Low | Med | `rsplit` takes the payload after the **last** occurrence; empty-payload fallback re-scans the original text |
| Fix lands but affected arms still carry bad data | High | High | Out of scope by design — flag to Basil that `swedish_02_*_qwen35_flash` combos need regeneration before they enter any analysis |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — reasoning strip | ~20 lines, small | None |
| Phase 2 — balanced last-first scan | ~35 lines, small | Phase 1 |
| Phase 3 — shape guard | ~20 lines, small | Phase 2 |
| Phase 4 — tests | ~150 lines, medium | Phase 3 |

---

## References

- Failing run: `01_Raw/swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash/logs/run_20260804_103034.log`
- Worked example of the silent-wrong-value mode: `persona_00458/llm_interactions.jsonl`, call 1
- Affected code: `src/population_synthetic/generators/synthetic/resolution_context.py:37`,
  `src/population_synthetic/generators/synthetic/category.py:429`
- Guides applied: `~/.claude/knowledge/data-pipeline-engineering/02-architecture-principles-and-patterns.md`
  (error boundaries, separation of concerns), `05-code-craftsmanship-and-maintainability.md`
  (cohesion, YAGNI, tests as the safety net)

---

## Completion Note

**Date:** 2026-08-04 · **Branch:** `fix/reasoning-block-json-extraction`

### Replay: `_extract_json` before vs after

Every `persona_*/llm_interactions.jsonl` under
`01_Raw/swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`, filtered to
entries timestamped `2026-08-04*`, replayed through both the pre-fix extractor (reconstructed
verbatim from `dev`) and the current one:

| Measure | Before | After |
|---|---|---|
| Calls replayed | 3492 | 3492 |
| Responses with no `</think>` at all | 12 | 12 |
| Raised `JSONDecodeError` | **3082** | **10** |
| … of which had no `</think>` | — | 10 (all of them) |
| Returned a `list` | **15** | **0** |
| Parsed types | — | 3482 × `dict`, 0 × `list` |

Derived: **3072 previously-failing calls now parse**, and **0 previously-parsing calls now fail** —
the change is strictly additive on this corpus.

Two figures differ from the ones in the Problem Statement, both because those were read off the
run log while these are replayed off the JSONL:

- **3082 pre-fix failures, not 3080.** The replay counts every recorded call; the log-derived
  baseline missed two. Immaterial to the criterion — the target of ≥3071 recovered is met at 3072.
- **10 responses still raise, not 9.** All 10 lack `</think>` entirely: they were truncated at the
  token ceiling before the model finished thinking, which is a genuine failure that must still be
  retried. The remaining 2 of the 12 no-tag responses were terse and parsed on both sides.

The 15 pre-fix `list` results are the silent-wrong-value mode. Only the `distribution` call site
passes `expected_key=None`, so only there could a list reach `.get()`; the other sites raised
`KeyError` and retried. That is why 15 bad extractions produced 11 killed personas.

### Test coverage

`tests/test_resolution_context.py` — 26 tests, all passing. Fixtures are excerpted from
`persona_00458/llm_interactions.jsonl` call 1 (category `age`, step `distribution`), the response
recorded with `parsed_value: [0, 1]` while ending in `{"distribution": "uniform"}`. The excerpt keeps
the four features that made it fail — the unparseable schema sketch quoted back from the prompt, the
throwaway `[0,1]` in the Beta sentence, the single bare `</think>`, and the trailing answer — and a
tag-stripped variant of the same text pins the last-first balanced scan independently of the strip.

Full suite: **1303 passed, 3 failed**. The 3 failures are pre-existing and unrelated to this branch
(`test_ollama_host_composition.py` ×2 and
`test_workflow_state.py::test_dep_incomplete_blocks_then_mark_completed_unlocks`), all caused by
uncommitted working-tree edits to config files. `ruff check src/` and
`ruff check tests/test_resolution_context.py` are clean.

### Still outstanding

- The live 5-persona confirmation run is unticked — it costs provider tokens and is an operational
  call, not a code one.
- Out of scope by design, and now due: the `swedish_02_*_qwen35_flash` combos carry values the model
  never chose (15 wrong extractions across 11 personas, plus 3072 calls' worth of retry cost) and
  must be regenerated before they enter any analysis.

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/development/debugging-identity-generation.md
- docs/development/plans/active/reasoning-block-tolerant-json-extraction.md
- src/population_synthetic/generators/synthetic/resolution_context.py
- tests/test_resolution_context.py

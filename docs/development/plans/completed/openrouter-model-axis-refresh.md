# Plan: OpenRouter model-axis refresh and GUI flow retargeting

**Date:** 2026-07-29
**Author:** Basil
**Status:** Completed
**Completed:** 2026-08-01
**Base Branch:** `dev`
**Branch:** `feature/openrouter-model-axis-refresh`

---

## Overview

Three of the seven `openrouter_*` model axes pointed at slugs that no longer exist in the
OpenRouter catalogue; each would abort on its first persona. This plan deletes those three arms,
adds five live replacements chosen for vendor/architecture diversity at matched capability,
reconciles `config/analysis/model_pricing.yaml` with the new axis inventory, and retargets both GUI
flows onto the resulting model set, the v2 strategies and `swedish_02`.

The evidence base is the audit record at
`docs/development/openrouter-model-axis-audit-2026-07-29.md` — catalogue fetch, concurrency probe,
token-volume measurements and telemetry comparison. This plan does not restate its measurements; it
records what was changed, why, and what was deliberately left undone.

## Problem Statement

The model axis is one of the two experimental factors in the benchmark. Three of its OpenRouter arms
were unrunnable and the rest were unpriced against reality:

1. **Dead slugs.** `openrouter_claude_sonnet5` → `anthropic/claude-sonnet-4-5`,
   `openrouter_gpt55` → `openai/gpt-4.5-preview`, and `openrouter_gemini_flash` →
   `google/gemini-flash-1.5` are all absent from the live catalogue (`GET /api/v1/models`, fetched
   2026-07-29, 367 entries). A dead slug returns HTTP 404, and 404 is a member of
   `OpenAICompatClient._FATAL_STATUS_CODES` (`src/population_synthetic/clients/openai_compat_client.py:24`
   — `{400, 401, 403, 404, 422}`), so the arm dies at the first persona with no retry. Their labels
   had drifted too: `openrouter_claude_sonnet5` was labelled "OpenRouter Claude Sonnet 4.5",
   `openrouter_gpt55` "OpenRouter GPT-4.5 Preview".

2. **No pre-flight on the cloud path.** Nothing checks a slug's existence before a sweep starts, so
   the failure surfaces only as a run that produces nothing.

3. **A stale pricing table.** `openrouter_glm_52` had drifted (0.77/2.42 against a live 0.739/2.323),
   and `model_pricing.yaml` carried rows for the three dead arms while carrying none for their
   replacements. `PricingTable.get()`
   (`src/population_synthetic/analysis/generation_metadata/pricing.py:64`) raises `KeyError` for an
   absent model id, so an axis file without a row breaks `generation_metadata` at read time.

4. **Flows aimed at the wrong targets.** `analysis_workflow.yaml` still selected the v1 strategies
   and `swedish`, and `generate_parallel.yaml` selected a single Ollama model — neither matched the
   arms the current experiment is meant to run. Independently, the mapping-config changes merged in
   PR #4 (`cae5a4a`, carrying `4a8b049` "feat(mapping): make misses observable and remove the Swedish
   `on_miss` sinks") invalidated the on-disk validate/map artefacts, which the flow's `force: false`
   settings would have silently reused.

## Goals

### In Scope

1. Remove the three dead OpenRouter arms from the catalogue outright.
2. Add five live OpenRouter arms, taking the OpenRouter block from 7 to 9 and the model axis from
   20 to 22 files.
3. Restore the axis-id → pricing-row coverage invariant: every one of the 22 axis ids has a row and
   no orphan axis-id row survives; correct the `openrouter_glm_52` drift; bump `observed_date`.
4. Repoint the one test that parametrizes a deleted axis id.
5. Retarget `analysis_workflow.yaml` and `generate_parallel.yaml` onto the new 9-model selection, the
   five v2 strategies and `swedish_02`, and force recompute of the three validation-gate stages so
   the PR #4 mapping changes take effect.

### Out of Scope

Each item below is an open item the audit names and this change deliberately does **not** implement
(audit §9 unless stated):

- **Capturing the discarded OpenRouter response fields.** `OpenAICompatClient` records
  `prompt_tokens` / `completion_tokens` only (`openai_compat_client.py:238-247`); the API also
  returns `usage.cost` (exact billed USD), `usage.completion_tokens_details.reasoning_tokens`,
  `usage.prompt_tokens_details.cached_tokens`, and an upstream `provider` name. The `provider` key
  written into `llm_interactions.jsonl` (line 170) is the client's static `provider_tag`, not the
  upstream backend that served the call. Capturing these would replace the hand-maintained pricing
  table with the number the API already returns.
- **Cloud pre-flight validation** — one catalogue call at startup asserting the slug exists, supports
  `structured_outputs`, and matches the configured price. It would have caught all three dead slugs
  and the `glm_52` drift automatically. This plan fixes the instances, not the class.
- **Per-model `parallel.workers` from the §5 concurrency measurements.** All five new files ship with
  `workers: 4`. See Risks.
- **The reasoning policy decision** (audit §4/§6 of this plan's Risks). Left unstated, as it was.
- **`run_metadata.model_config.base_url` for cloud providers** and logging the effective
  `generation_config` when it is all-`null`.
- **The GUI Workers column fix** — `population_summary.py::_workers_cell` shows the axis value while
  the run uses the flow value; needs a `workers` override on `refresh()` symmetric with
  `total_override`.
- **Any change to the OpenRouter client itself.** No code under `src/clients/` is touched.
- **Adding the three unselected new arms to a flow.** They enter the catalogue only.

## Success Criteria

- [x] `config/synthetic/axes/models/` holds 22 files, 9 of them `openrouter_*`.
- [x] No `openrouter_claude_sonnet5` / `openrouter_gpt55` / `openrouter_gemini_flash` reference
      survives in `config/`, `src/`, `scripts/` or `tests/`. Remaining hits are confined to
      historical plan records under `docs/development/plans/completed/`
      (`openrouter-provider.md`, `generation-metadata-analysis-task.md`,
      `selectable-ollama-host.md`), which are records of past state and are not live configuration.
- [x] Every model axis id resolves to a `model_pricing.yaml` row: the set difference
      `axis_ids - pricing_ids` is empty, and no pricing row names a non-existent axis. The `models:`
      block holds 26 keys — the 22 axis ids plus the 4 raw judge model strings
      (`claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-fable-5`) that
      `persona_realism` joins on directly.
- [x] `openrouter_glm_52` reads `{in: 0.739, out: 2.323}`; `observed_date` is `2026-07-29`.
- [x] Full suite green. 1138 passed (2026-08-01, current working tree). The audit recorded 1070
      passed at 2026-07-29; the difference is unrelated work in the tree, not a change in this
      plan's scope.
- [x] Both flow YAMLs select the same 9 models × 5 v2 strategies × `swedish_02` = 45 combos.
- [x] `validate_raw`, `mapping` and `validate_mapped` carry `force: true`; `fidelity` is enabled.

## Definitions

- **Dead slug:** a `model_config.model` string absent from the response of
  `GET https://openrouter.ai/api/v1/models`. Operationally testable: the first chat completion
  returns HTTP 404, which the client classifies as fatal and does not retry.
- **Live arm:** an axis file whose slug is present in that catalogue response **and** whose
  `supported_parameters` include `structured_outputs` — the hard constraint, since
  `OpenAICompatClient` sends `response_format: json_schema, strict: true`. An arm without it
  silently degrades to the `json_object` fallback and is not comparable to the others.
- **Discarded (the `discarded: true` axis key):** a *selection-side* retirement. Per CLAUDE.md, "a
  discarded model is still a model … a discarded model stays runnable if checked." The flag hides an
  arm from the GUI's default chip filter; it asserts nothing about the arm being broken.
- **Axis-id → pricing-row coverage:** for every `config/synthetic/axes/models/*.yaml`, its `id` is a
  key of `model_pricing.yaml::models`. The reverse containment does **not** hold and is not intended
  to: the four judge rows are keyed by raw `--model` strings, not axis ids.

---

## Technical Design

### Approach

Config-only. Two independent groups, the second depending on the first because it names ids the
first creates.

**G2 — catalogue refresh.** Delete three files, add five, reconcile the pricing table, repoint one
test parametrization. No Python under `src/` changes: the axis mechanism, the client and the
composition layer already handle an arbitrary set of OpenRouter arms.

**G4 — flow retargeting.** Two YAML edits under `config/gui/flows/`, consistent with the
GUI-translates-YAML→CLI contract: the flows carry selection and options; the spawned scripts never
read them.

### The deletion-vs-`discarded` decision

The obvious alternative to deletion was `discarded: true` on the three dead arms, preserving them as
historical record. It was rejected as a direct application of a documented invariant.

CLAUDE.md defines `discarded` as a **selection-side concept only**: "nothing downstream reads it, and
a discarded model stays runnable if checked." That is a promise about the arm — it is retired from
the default sweep, but checking it in the GUI still produces a working run. A 404 slug cannot honour
that promise: checking it produces a run that aborts on persona 1. Marking these three `discarded`
would therefore encode a false statement in config, which is worse than the absence the deletion
creates, and it would make the flag mean two different things (retired-by-choice, broken-by-decay)
depending on which file you read.

Two facts make deletion cheap. None of the three had run output in `01_Raw`, so no provenance is
lost; and the analysis layer keys levels on ids it discovers on disk, so a removed id simply stops
appearing rather than leaving a hole.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Delete the three dead axis files | Config states only what is true; the arms are unrecoverable anyway | Loses the label/slug record from live config | **Chosen** — history is in git and in the audit doc |
| Mark them `discarded: true` | Preserves the ids; one-key change | Contradicts the documented meaning of `discarded` (a discarded model must stay runnable); overloads one flag with two meanings | Rejected |
| Repoint the three slugs at their successors (`anthropic/claude-sonnet-5`, `openai/gpt-5.x`, `google/gemini-3.5-flash`) | Keeps ids stable | The id would then name a different model than it did historically — silently repartitions the model factor. Also expensive: the frontier tier is $30–150 /M input | Rejected |
| Add the five arms without deleting anything | Smallest diff | Leaves three landmines in the GUI's default-active chip set | Rejected |
| Leave pricing rows for the deleted arms | No pricing edit | Dead rows rot; the next reader cannot tell which rows are live | Rejected |
| Add frontier models (`gpt-5.5-pro`, `o1-pro`) for prestige | Stronger-sounding model axis | $1,700–8,600 per arm per 1000 personas; the paper's finding is *strategy > model*, strengthened by a wider **controlled** axis, not by more frontier models | Rejected |
| Use `openrouter/auto` or `*:free` variants | Cheap / self-routing | `auto` resolves to a different model per call, destroying the model factor in `model_ranking` and `method_significance`; `:free` is rate-limited to 20 req/min and rotates providers, unreproducible at 152 calls/persona | Rejected |

### Architecture & Module Contracts

No module is added or changed. The contract at stake is which file owns which fact:

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/synthetic/axes/models/openrouter_*.yaml` | Declare one arm: id, label, provider, slug, generation config, worker count | — → axis record | pricing, flows, analysis, which flows select it |
| `config/analysis/model_pricing.yaml` | Per-axis-id USD rates + observation date | axis id → `(in, out)` | slugs, providers, whether the arm is selected |
| `config/gui/flows/*.yaml` | Which combos to run and with which CLI options | — → GUI selection + option map | slugs, prices, script internals |
| `analysis/generation_metadata/pricing.py` | Load + validate the table, fail-fast | path → `PricingTable` | axis files, flows |

The coupling between the first two files is the axis id, and it is unenforced by any test — see
Risks.

---

## Implementation Plan

### Phase G2: Model-axis catalogue refresh
**Goal:** The `openrouter_*` block contains only arms that are live, structured-output capable, and
priced.

**Started:** 2026-07-29
**Completed:** 2026-07-29

- [x] G2.1 — Delete `openrouter_claude_sonnet5.yaml`, `openrouter_gpt55.yaml`,
      `openrouter_gemini_flash.yaml`.
- [x] G2.2 — Add five arms, each following the existing `openrouter_*` file shape exactly (id, label,
      `provider: openrouter`, slug, all four `generation_config` values `null`,
      `parameters.parallel.workers`):

      | New axis id | Slug |
      |---|---|
      | `openrouter_gpt_oss_120b` | `openai/gpt-oss-120b` |
      | `openrouter_gemini_flash_lite` | `google/gemini-2.5-flash-lite` |
      | `openrouter_qwen35_flash` | `qwen/qwen3.5-flash-02-23` |
      | `openrouter_nemotron3_super` | `nvidia/nemotron-3-super-120b-a12b` |
      | `openrouter_deepseek_v4_flash` | `deepseek/deepseek-v4-flash` |

- [x] G2.3 — `model_pricing.yaml`: drop the three dead rows, add the five new ones, correct
      `openrouter_glm_52` 0.77/2.42 → 0.739/2.323, bump `observed_date` 2026-07-23 → 2026-07-29.
      Re-align the `openrouter_*` block so the surviving nine sort alphabetically.
- [x] G2.4 — `tests/test_ollama_host_composition.py:286`: the
      `test_ollama_host_is_inert_for_other_providers` parametrize list becomes
      `["claude_sonnet", "gemini_flash", "openrouter_deepseek_v4"]` (was `openrouter_gpt55`). The
      case needs any non-Ollama axis; `openrouter_deepseek_v4` is a live one.
- [x] G2.5 — Confirm no other tracked reference to the three ids outside historical plan documents.

**Files Modified:**
- `config/synthetic/axes/models/openrouter_claude_sonnet5.yaml` — deleted
- `config/synthetic/axes/models/openrouter_gpt55.yaml` — deleted
- `config/synthetic/axes/models/openrouter_gemini_flash.yaml` — deleted
- `config/synthetic/axes/models/openrouter_gpt_oss_120b.yaml` — new
- `config/synthetic/axes/models/openrouter_gemini_flash_lite.yaml` — new
- `config/synthetic/axes/models/openrouter_qwen35_flash.yaml` — new
- `config/synthetic/axes/models/openrouter_nemotron3_super.yaml` — new
- `config/synthetic/axes/models/openrouter_deepseek_v4_flash.yaml` — new
- `config/analysis/model_pricing.yaml` — 3 rows out, 5 in, 1 corrected, date bumped
- `tests/test_ollama_host_composition.py` — one parametrize id

**Dependencies:** None

### Phase G4: GUI flow retargeting
**Goal:** Both flows run the current experiment — the refreshed model set, the v2 strategies, the
`swedish_02` country axis — and recompute the validation gate rather than reusing artefacts
invalidated by PR #4.

**Started:** 2026-07-29
**Completed:** 2026-07-29

- [x] G4.1 — `analysis_workflow.yaml`: `force: false → true` on `validate_raw`, `mapping` and
      `validate_mapped`. PR #4 (`cae5a4a` / `4a8b049`) changed the Swedish mapping config, so every
      on-disk validity CSV and mapped file predating it is stale; `force: false` would silently reuse
      them. The downstream stages (`population_cap`, `fidelity`, …) keep `force: false` — they
      consume the gate's output and are invalidated by it, not by the config change.
- [x] G4.2 — `analysis_workflow.yaml`: `fidelity.enabled: false → true`. It is the dependency of both
      `model_ranking` and `method_significance`, which were already enabled.
- [x] G4.3 — `analysis_workflow.yaml` selection retarget:
      - models 8 → 9: drop `claude_opus` and `claude_sonnet`; add `openrouter_gpt_oss_120b`,
        `openrouter_mistral_medium` and `openrouter_qwen35_flash`. Result:
        `[claude_haiku, ollama_deepseek_r1_14b, ollama_gemma4_e4b, ollama_llama31_8b,
        ollama_mistral_nemo_12b, openrouter_glm_52, openrouter_gpt_oss_120b,
        openrouter_mistral_medium, openrouter_qwen35_flash]`.
      - strategies: the five v1 families → their five v2 counterparts.
      - countries: `swedish` → `swedish_02`.
- [x] G4.4 — `generate_parallel.yaml`: `workers: 4 → 2`.
- [x] G4.5 — `generate_parallel.yaml`: models `[ollama_mistral_nemo_12b]` → the identical 9-model
      list, so generation and analysis address the same 45 combos. Strategies and `swedish_02` were
      already v2/`swedish_02` in this file.

**Files Modified:**
- `config/gui/flows/analysis_workflow.yaml` — force flags, `fidelity` enable, selection
- `config/gui/flows/generate_parallel.yaml` — workers, model selection

**Dependencies:** Phase G2 (G4.3 and G4.5 name ids that G2 creates; `AxisSelector` validates the
selection against discovered axis files, so ordering matters)

---

## Testing Plan

### Unit Tests

- [x] Full suite green after G2: 1138 passed.
- [x] `tests/test_ollama_host_composition.py::test_ollama_host_is_inert_for_other_providers`
      passes for `openrouter_deepseek_v4` — an `--ollama-host` value, including an unregistered one,
      remains inert for a cloud provider.
- [x] `tests/test_axis_facet_defaults.py` still green: the `Active`/`Discarded` chip derivation is
      unaffected, since none of the 22 live files carries a `discarded` key (absent means active).
- [x] `load_pricing_table()` loads the edited file without raising — it validates the mapping shape,
      the required top-level keys, every per-model rate entry and the `cache_multipliers` block.

### Integration Tests

- [x] Axis-id ↔ pricing-row set comparison over the files on disk: `axis_ids - pricing_ids` is empty;
      `pricing_ids - axis_ids` is exactly the four raw judge model strings. Run as a one-off check,
      **not** added as a permanent test — see Risks.
- [x] `composed = compose_manifest(model_id, ...)` resolves for each of the five new ids (implicitly,
      via the axis-discovery tests that enumerate `config/synthetic/axes/models/`).

### Manual Verification

- [x] Live catalogue fetch (`GET /api/v1/models`, 367 entries) confirms all five new slugs present
      with `structured_outputs` in `supported_parameters`, and all three deleted slugs absent.
- [x] Bounded concurrency probe against the project key (≈600 requests, `max_tokens=8`, cost < $0.01)
      — zero 429s up to 256 concurrent; recorded in audit §5.
- [ ] End-to-end generation run on a new arm. **Not performed** — the arms enter the catalogue and
      two of them enter the flows, but no sweep was executed as part of this change.
- [ ] GUI visual check that the Global tab lists 22 models with the five new ones under `Active`.
      **Not performed.**

---

## Documentation Plan

- [x] `docs/development/openrouter-model-axis-audit-2026-07-29.md` — the audit record: catalogue
      status per arm, measured token volumes and cost, the concurrency ramp, the OpenRouter-vs-Ollama
      telemetry comparison, selection criteria and exclusions, and the numbered open items. Written
      first; this plan references rather than duplicates it.
- [x] This plan — the change record and the deletion-vs-`discarded` rationale.
- [ ] `CLAUDE.md` — **not updated**. No invariant changed; the model count is not stated there.
- [ ] `docs/architecture/axis-composition.md` — **not updated**. The axis file shape is unchanged;
      only its instances differ.

---

## Rollback Plan

Config-only, no migrations, no state.

1. **Full revert:** `git revert` the G2 and G4 commits, G4 first. Restoring the three deleted axis
   files also requires restoring their three pricing rows in the same revert — an axis file without a
   pricing row raises `KeyError` in `PricingTable.get()` the moment `generation_metadata` runs.
2. **Partial revert — G4 only:** reverting the flow YAMLs alone is safe and leaves the refreshed
   catalogue in place, *provided* the restored selection does not name a deleted id. The pre-change
   `analysis_workflow.yaml` selection named none of the three (`claude_haiku`, `claude_opus`,
   `claude_sonnet`, four `ollama_*`, `openrouter_glm_52`), so this direction is clean.
3. **Partial revert — G2 only:** not safe while G4 is in place. `analysis_workflow.yaml` and
   `generate_parallel.yaml` both select `openrouter_gpt_oss_120b` and `openrouter_qwen35_flash`;
   removing those axis files while the flows name them makes the selection unresolvable. Revert G4
   first.
4. **Data considerations:** existing `01_Raw` output is untouched. `03_Analysis` artefacts for the
   three deleted arms do not exist (none of them ever ran). The `force: true` flags in G4.1 cause a
   **recompute**, overwriting the per-combo validity CSVs and the mapped files for the selected
   combos — that is the intent, and it is idempotent: re-running with `force: false` afterwards
   reuses the fresh artefacts.
5. **Pricing-only rollback:** restoring `openrouter_glm_52` to 0.77/2.42 would reintroduce a known-
   wrong price. If the rest is reverted, keep this row and the `observed_date` bump.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **The cost model is ~20× low on output tokens.** Measured over `openrouter_glm_52` Swedish runs: 80,150 output tokens per persona across the five v1 families, against ~3,900 for the non-reasoning `claude_sonnet`. `z-ai/glm-5.2` costs ≈$226 per 1000 personas × 5 families, not the ≈$49 a non-reasoning profile implies | Certain — measured | High — budget | Documented in audit §3 with both profiles for all 12 candidate slugs. All five added arms are cheaper than the incumbent under **either** profile (cheapest: `openai/gpt-oss-120b` at $2.7 / $15.6). At `n: 150` the per-arm figures are ≈0.15× the table |
| **~95% of billed output tokens are discarded reasoning trace.** Over 510 `glm_52` `all_pick` calls: mean `completion_tokens` = 111 against a mean visible `raw_response` of 24 characters ≈ 6 tokens | Certain — measured | Med — cost + interpretability | Recorded in audit §4. Closing it needs `reasoning_tokens` capture, which is Out of Scope |
| **Unmatched reasoning defaults are a live confound in the model factor.** All nine `openrouter_*` axes (and the four other cloud axes) set every `generation_config` value to `null`, so each vendor's own reasoning default is silently in force, unrecorded and different per arm. The nine `ollama_*` axes, by contrast, pin `temperature: 0.7` | Certain | **High — validity, not just cost** | Not mitigated. The policy decision (pin reasoning off for a sampling-matched comparison, or keep vendor defaults and state the choice) is deliberately deferred; audit §9 item 6 records that the current state is "an unstated accident" |
| **All five new arms ship `workers: 4`**, contradicting the audit's own §5 measurements (recommended 64–128 for `gpt-oss-120b`, 64 for `gemini-flash-lite`, 32 for `nemotron3_super`, 16–32 for `deepseek-v4-flash`, 16 for `qwen3.5-flash`) | Certain — self-declared | Med — throughput only | Known loose end, stated in audit §5 ("not yet applied") and §9 item 5. Correctness is unaffected. Compounded by G4.4: the GUI emits `--workers` unconditionally for every combo and `generate_identities_parallel.py:526` uses the axis value only when the flag is absent, so the flow's `workers: 2` overrides the axis `4` for **all** cloud combos. Ollama combos are unaffected (`ollama-auto-workers: true`) |
| **No test enforces axis-id ↔ pricing-row coverage.** The join is by string id across two config trees with nothing checking it; the next axis file added will break `generation_metadata` at read time, not at commit time | Med | Med | The failure is loud (`KeyError` naming the id) rather than silent. A permanent test was not added — it belongs with the cloud pre-flight work |
| **OpenRouter routes a slug to different upstream backends per request** (different quantizations, different sampling defaults) and the client discards the `provider` field that names them. No record exists of which backend produced any given persona; Ollama has no such ambiguity | High | Med — reproducibility | Documented in audit §7. Unmitigated; capture is Out of Scope |
| **Three of the five new arms are in the catalogue but selected in no flow** (`openrouter_deepseek_v4_flash`, `openrouter_gemini_flash_lite`, `openrouter_nemotron3_super`) | Certain | Low | Intentional — the catalogue is the menu, the flow is the order. `openrouter_deepseek_v4` and `openrouter_qwen37_max` were already in this state before the change |
| **`force: true` on the three gate stages re-runs the whole validation gate for 45 combos** on every GUI Run until someone turns it back off | High | Low — wall clock | The stages are cheap relative to generation, and the flags are one edit to revert once the PR #4 remap has landed on disk |
| **A future arm decays the same way** | High | High — a whole sweep produces nothing | Not fixed here. The cloud pre-flight (audit §9 item 2) is the structural answer and is explicitly Out of Scope |

---

## References

- `docs/development/openrouter-model-axis-audit-2026-07-29.md` — the evidence base for every number
  in this plan (catalogue status, cost measurements, concurrency ramp, telemetry gap, selection
  criteria, open items).
- `CLAUDE.md` — "A discarded model is still a model" (the invariant governing the deletion decision)
  and "Config is the single source of truth" / "Fail-fast".
- `docs/development/plans/completed/openrouter-provider.md` — the plan that introduced the
  `openrouter_*` arms, including the three deleted here.
- `docs/development/plans/completed/generation-metadata-analysis-task.md` — origin of
  `model_pricing.yaml` and its per-row confidence annotations.
- `docs/development/plans/completed/audit-unmapped-skill.md` — PR #4, whose mapping-config changes
  motivate the `force: true` flags in G4.1.
- `docs/development/gui.md` — the GUI-translates-YAML→CLI execution contract that makes G4 a
  config-only change.
- `src/population_synthetic/clients/openai_compat_client.py` — `_FATAL_STATUS_CODES` (L24), the
  telemetry record written per call (L170-260).
- `src/population_synthetic/analysis/generation_metadata/pricing.py` — `PricingTable.get` (L64) and
  `load_pricing_table` (L133).

---

## Modified Files

- config/analysis/model_pricing.yaml
- config/gui/flows/analysis_workflow.yaml
- config/gui/flows/generate_parallel.yaml
- config/synthetic/axes/models/openrouter_claude_sonnet5.yaml (deleted)
- config/synthetic/axes/models/openrouter_deepseek_v4_flash.yaml (new)
- config/synthetic/axes/models/openrouter_gemini_flash.yaml (deleted)
- config/synthetic/axes/models/openrouter_gemini_flash_lite.yaml (new)
- config/synthetic/axes/models/openrouter_gpt55.yaml (deleted)
- config/synthetic/axes/models/openrouter_gpt_oss_120b.yaml (new)
- config/synthetic/axes/models/openrouter_nemotron3_super.yaml (new)
- config/synthetic/axes/models/openrouter_qwen35_flash.yaml (new)
- docs/development/openrouter-model-axis-audit-2026-07-29.md (new)
- docs/development/plans/completed/openrouter-model-axis-refresh.md (this file)
- tests/test_ollama_host_composition.py

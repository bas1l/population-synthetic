# Plan: Individual Persona Realism Judge (LLM-as-judge analysis task)

**Date:** 2026-07-23
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-26 19:02
**Base Branch:** `feature/cap-population-to-n`
**Branch:** `feature/persona-realism-judge`

> ✅ **Base-branch decision (resolved 2026-07-23):** based on `feature/cap-population-to-n` (the
> current branch, user's explicit choice over `dev`). The `generation_metadata` cost pipeline
> (`persona_metrics.py`, `cost.py`, `pricing.py`) and `config/analysis/model_pricing.yaml` this task
> reuses are already committed here (merged via dev). This feature branch merges back into
> `feature/cap-population-to-n` on `/plan-finish`. Note: unrelated in-progress cap-population
> working-tree changes were present at branch time and travel along.

---

## Overview

A new analysis subpackage, `persona_realism`, that uses an LLM (Claude, default `claude-sonnet-5`)
as a judge to score the **individual coherence** of each synthetic persona — asking, per persona,
"could these demographic attributes belong to one real person?" It ranks every generation
combination (model × strategy) **plus the SCB-sampled real population as one more competitor** on
two orthogonal axes the existing statistical pipeline cannot measure: an **impossibility rate**
(share of internally-contradictory individuals) and a **typicality dispersion** (how far the
combination reaches into the real population's tails). The headline output is a 2-D map that surfaces
the coherence-vs-spectrum decoupling.

## Problem Statement

The `fidelity/`, `multivariate_fidelity/`, and `model_ranking/` subpackages measure **distributional**
realism — whether marginals and (fetched) joints match the real Swedish population. They cannot
measure **individual** realism: whether any *single* persona hangs together as a believable human.
This matters because the two properties can disagree. SCB is distributionally perfect by construction
(sampled from real tables) yet its chained sampling does not condition on every attribute pair, so it
can emit internally-incoherent individuals (e.g. a 19-year-old with a doctorate, or work-experience
exceeding the legally-workable years for the person's age). Conversely an LLM generator may skew the
marginals but rarely produce an incoherent individual. Multivariate statistics can only score joints
SCB actually fetched; only a world-knowledge judge catches impossibilities in **unfetched** joints.
Without this task, the benchmark has no measure of per-persona coherence, and the manuscript cannot
substantiate the "SCB tables lack links between them" claim quantitatively.

## Goals

### In Scope
1. A `persona_realism` analysis subpackage that judges each individual persona (bare mapped
   demographic tuple) with an LLM, N times per persona (default N=3), at low temperature.
2. Two orthogonal per-persona outputs: **`can_exist`** (binary possibility) and **`typicality`**
   (ordinal 0–10), plus a structured **`issues`** list (attribute-pair clashes, severity S1/S2/S3).
3. Nested aggregation (round ⊂ persona ⊂ combination) → per-combination **impossibility rate** with
   bootstrap CI + **typicality dispersion vs SCB** (variance-equality test) + a judge-**reliability**
   metric (ICC / Krippendorff's α across rounds).
4. SCB real population judged as an additional competitor per country and used as the dispersion
   reference.
5. Config-driven judge model (dropdown, default `claude-sonnet-5`), N-rounds, temperature, severity
   weights, typicality anchors, prompt template, sampling size, and bootstrap params — all in
   `config/analysis/persona_realism/`.
6. Resumable, parallel judge calls (per-persona on-disk cache, ThreadPool fan-out, round-based retry)
   with per-call cost/token telemetry reusing the `generation_metadata` cost chain.
7. Publication artifacts: the 2-D headline map, per-combination typicality-distribution and
   clash-taxonomy figures, reliability report, CSV/JSON, all dual PNG+SVG; integrated into the
   analysis registry and GUI workflow.
8. New reusable statistics primitives (bootstrap CI, ICC, Krippendorff's α, variance-equality test)
   added to `analysis/utils/stats_tests.py` with unit tests.

### Out of Scope
- **Population-level or pairwise LLM judging.** Distributional realism stays with `fidelity/`; the
  judge is pointwise only. (Rejected in brainstorm — see Alternatives.)
- **Statistical (SCB-density) typicality.** Typicality is LLM-judged; stats operate on judge outputs,
  not the tables. (Deferred.)
- **Self-preference-bias mitigation / judge panels.** Deferred to a future iteration; v1 uses a
  single configurable judge and relies on the standardized mapped schema to remove the stylistic
  self-recognition channel. (See Risks.)
- **Rich identity / narrative judging.** All personas are bare attribute tuples on every side; no
  names or life stories are judged.
- **Cross-country tuning.** v1 targets the countries already mapped (Sweden primary); no new
  country-specific constraint tables beyond the config-driven hard-rules subset.

## Success Criteria

- [ ] `python scripts/analyze/analyze_persona_realism.py --slug <slug>` produces, for each selected
      combination, a per-persona verdict cache, a combination CSV+JSON, and figures under
      `03_Analysis/persona_realism/`, resolved via `analysis_output_dir("persona_realism", base)`.
- [ ] Re-running without `--force` skips personas whose verdict file already exists (resumable);
      `--force` recomputes.
- [ ] Each selected country's `real_{country}.json` is judged and appears as a competitor point.
- [ ] The combination JSON reports impossibility rate + bootstrap CI, typicality dispersion +
      distance-to-SCB + variance-equality test result, and the ICC/α reliability metric — with N and
      the successful-call count carried on every metric.
- [ ] A failed/absent judge call is represented distinctly from a "judged possible" verdict; the
      impossibility rate is gated on successful calls and the dropped count is logged.
- [ ] The judge model is selected from config (default `claude-sonnet-5`); changing it requires no
      code edit; a missing/malformed judge config **raises**.
- [ ] Cost metadata (tokens + USD via `model_pricing.yaml`) is emitted per combination; a missing
      `claude-fable-5` pricing row raises (fail-fast), and the row is added.
- [ ] `pytest` passes new unit tests for the parser (malformed judge JSON raises), the stats
      primitives (known-answer fixtures via `pytest.approx`), degenerate-input guards, and one
      end-to-end smoke test with a **stubbed** judge client (no live CLI in CI).
- [ ] `persona_realism` appears in `analysis_registry.yaml` and `analysis_workflow.yaml`; the GUI
      node runs it with a Force checkbox and `depends_on: [mapping]`.

## Definitions

- **Persona / tuple:** one record from a mapped population file (`{"metadata", "individuals"}`); a
  flat dict of the mapped demographic attributes (Sweden: 15 emitted, 14 analyzed — `birth_location`
  is deprecated and excluded from the judged tuple, matching `ComparisonScheme.attributes`).
- **Combination:** a `{slug}.json` mapped synthetic population, decomposed to (country, strategy,
  model) via `decompose_slug`. The **real reference** `real_{country}.json` is treated as an
  additional competitor, labelled `real_{country}` (not a synthetic combo).
- **`can_exist`:** the judge's binary verdict that the attribute set can describe a single real
  person. False **only** on a hard biological/legal/temporal contradiction (severity S3). Not false
  for merely-unusual-but-possible people.
- **`typicality`:** integer 0–10 ordinal, judged **only if `can_exist` is true** (else null). 10 =
  modal/ordinary person; 0 = highly unusual yet still possible. It measures **commonness**, not
  quality — a low score is not a defect. Naming is load-bearing (see Alternatives).
- **Issue / severity:** an attribute pair in tension. **S3** = hard contradiction (drives
  `can_exist=false`); **S2** = near-impossible; **S1** = unusual-but-possible (reported, not
  penalized).
- **Impossibility rate:** over personas with a successful verdict, the fraction with `can_exist=false`
  (majority of N rounds; the per-round fraction `1−p_i` is retained). "Successful verdict" excludes
  personas whose judge calls all failed.
- **Typicality dispersion:** the spread (variance / entropy / tail-coverage) of per-persona mean
  typicality over `can_exist=true` personas in a combination. Reported as **distance from the SCB
  real population's dispersion**, not raw spread.
- **Reliability:** agreement of the judge with **itself** across the N rounds (ICC / Krippendorff's
  α). This is precision/consistency, **not** correctness — validity is not established internally.
- **Round:** one judge call for one persona; N rounds per persona (config, default 3).

---

## Technical Design

### Approach

A **batch, pipe-and-filter analytics pipeline** with a two-level structure (per-persona expensive
layer, cross-persona aggregation layer) and strict one-way layer separation. It mirrors the
`generation_metadata` subpackage decomposition (the closest sibling — same round→persona→combo
nesting and cost pricing) and reuses `ClaudeCodeClient` for the judge calls and
`generate_identities_parallel.py`'s skip-if-exists + ThreadPool + round-retry pattern for
resumable, parallel orchestration. All non-determinism (the LLM) is isolated in the judge-call
layer; everything downstream is pure and depends only on numeric/DTO contracts. The N rounds are the
statistical measurement of the judge's own stochasticity (quantified by the reliability metric), not
a defect to be eliminated — the judge output is treated as empirical data to be characterized.

Rationale for the key measurement decisions is settled in the brainstorm
(`docs/development/brainstorms/individual-persona-realism-judge.md`) and summarized below.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Pointwise coherence-flagging (`can_exist` + `typicality`) | Objective world-knowledge property; O(n) not O(pairs); interpretable rate; SCB competes fairly | Can't rank two fully-coherent combos apart | **Chosen** |
| Pairwise / Bradley–Terry ranking | Reliable relative judgments | Re-measures typicality (already the distribution branch's job); penalizes rare-but-valid people | Rejected |
| Pointwise 1–5 "realism" score | Simple | Calibration drift + blandness bias; conflates coherence with quality | Rejected |
| LLM emits the score directly | One output | Invites vibe/typicality leak; drift | Rejected — score derived from severity flags |
| Statistical SCB-density typicality | Grounded in real data | Blind to unfetched joints; not what user wants | Deferred |
| Judge panel (≥2 families) + interaction test | Cancels self-preference bias | Cost; deferred | Deferred (single configurable judge for v1) |
| Name axis 2 "realism" | — | Inverts the narrative (low = bad) when low-but-possible is the *virtue* | Rejected — named **typicality** |

Additional evidence-backed choices (from the judge-selection literature review, recorded in the
brainstorm): **ordinal 0–10 integers** (not continuous); **cold temperature** (0–0.1) for
reproducibility; **N≥2** required for any SD/reliability number; **anchored typicality exemplars**
in the prompt to counter central-tendency clumping; **constraint-category scaffolding** in the
prompt (biological/legal/temporal) with an explicit "unusual ≠ impossible" guardrail (this is the
sweet spot, not a rulebook — it scaffolds reasoning, not an enumerated pair-checklist).

### Architecture & Module Contracts

Four strictly one-way layers. The subpackage contains **no** argparse, registry lookup, or
output-dir resolution (those live in the script); it receives an already-resolved `out_dir: Path`.

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/persona_realism/prompt.py` | Render a persona tuple + system prompt from config | (persona dict, analyzed-axis list, config) → (system_str, user_str) | matplotlib, disk, the CLI, stats |
| `analysis/persona_realism/judge.py` | One judge call → parsed canonical verdict; the **single** normalization/validation point | (system_str, user_str, ClaudeCodeClient) → `RoundVerdict` \| raises on contract violation | aggregation, plotting, paths |
| `analysis/persona_realism/runner.py` | Fan-out: N rounds × personas, skip-if-exists cache, ThreadPool, round-retry, cost logging | (population, combo label, out_dir, config) → per-persona verdict JSON files + call log | stats formulas, chart rendering |
| `analysis/persona_realism/reduce.py` | Pure reduction round→persona→combo | list[`RoundVerdict`] → `PersonaVerdict`; list[`PersonaVerdict`] → `ComboRealism` | the CLI, LLM, matplotlib |
| `analysis/persona_realism/stats.py` | Pure combo-level statistics | `ComboRealism` (+ SCB reference) → `RealismStats` (rate+CI, dispersion+distance+test, reliability) | rendering, paths, the judge |
| `analysis/persona_realism/charts.py` | Pure sink: figures | structures → matplotlib `Figure`s | disk, DPI, country, paths |
| `analysis/persona_realism/csv_writer.py` | Pure sink: CSV | rows → path | compute |
| `analysis/persona_realism/report.py` | Pure sink: JSON (+ pricing/provenance meta) | structures → path | compute |
| `analysis/persona_realism/artifacts.py` | Orchestrator; only path-aware module; idempotent/force | (verdict cache, SCB ref, scheme, out_dir, cfg) → list[Path] | how inputs were loaded, GUI/dispatch |
| `analysis/utils/stats_tests.py` (extend) | Add `bootstrap_ci`, `icc`, `krippendorff_alpha`, `variance_equality_test` | numeric contracts → scalars/CIs | anything domain-specific |
| `scripts/analyze/analyze_persona_realism.py` | argparse, registry/output-dir resolution, load inputs, per-combo dispatch + real reference, idempotent skip | CLI → calls `artifacts` | the judge internals, stats formulas |

```
config/analysis/persona_realism/
  judge.yaml            # judge_model (default claude-sonnet-5) + model_options[] (dropdown);
                        # n_rounds: 3; temperature: 0.0; severity_weights {S3, S2, S1: 0};
                        # impossibility_severities: [S3]; sample_size (per combo, nullable);
                        # bootstrap {iterations, seed, ci_level}; workers; prompt_template: <path>
  judge_prompt.md       # system + user template (constraint scaffolding, anchors, JSON schema)
  hard_rules.yaml       # config-driven deterministic checks for the can_exist validation subset

03_Analysis/persona_realism/<combo>/
  raw/persona_XXXXX.json   # N RoundVerdicts for one persona (the durable cache boundary)
  llm_interactions.jsonl   # per-call telemetry (reuses LLMInteractionCollector)
  <axis>.png/.svg          # per-combo typicality + clash figures
  <combo>.csv / <combo>.json
03_Analysis/persona_realism/
  headline_map.png/.svg    # impossibility rate x typicality-dispersion-vs-SCB, all competitors
  run_metadata.json        # judge model+version, prompt hash, N, temp, seed, config snapshot, versions
```

Canonical id `persona_realism` = registry key = GUI task key = output folder. Dispatch `per_combo`;
the real reference is derived from the distinct countries among the selected combos.

---

## Implementation Plan

### Phase 1: Foundation (config, registry, stats primitives, pricing)
**Goal:** Everything the compute layers depend on exists and is config-driven.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 1.1 — Add `persona_realism` entry to `config/analysis/analysis_registry.yaml` (all five
      required keys; `dispatch: per_combo`).
- [x] 1.2 — Create `config/analysis/persona_realism/judge.yaml` (judge_model default
      `claude-fable-5`, model_options dropdown, n_rounds, temperature, severity_weights,
      impossibility_severities, sample_size, bootstrap{iterations,seed,ci_level}, workers,
      prompt_template path), `judge_prompt.md` (constraint-scaffolded, anchored 1/5/9 typicality,
      strict JSON output schema), and `hard_rules.yaml` (validation-subset rules).
- [x] 1.3 — Add a `claude-fable-5` (or `fable` axis id) row to `config/analysis/model_pricing.yaml`
      (`{in: 10.00, out: 50.00}`), matching the model string passed to `--model`.
- [x] 1.4 — Add `bootstrap_ci`, `icc`, `krippendorff_alpha`, `variance_equality_test`
      (Levene/Brown–Forsythe) to `analysis/utils/stats_tests.py`, using `np.random.default_rng(seed)`;
      return an explicit skipped-reason (not NaN) on degenerate input (single round, zero variance).
- [x] 1.5 — Unit tests for 1.4 against known-answer fixtures (`pytest.approx`) + degenerate guards.

**Files Modified:** `config/analysis/analysis_registry.yaml`, `config/analysis/model_pricing.yaml`,
`src/population_synthetic/analysis/utils/stats_tests.py`, new `config/analysis/persona_realism/*`,
new `tests/test_realism_stats.py`.
**Dependencies:** None.

### Phase 2: Judge-call layer (resumable, parallel, cost-logged)
**Goal:** Turn a mapped population into a per-persona verdict cache with cost telemetry.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 2.1 — `prompt.py`: render the analyzed tuple as raw `axis: value` lines (deprecated axis
      excluded via `scheme_attributes(country)`); build system prompt from config template.
- [x] 2.2 — `judge.py`: one call via `ClaudeCodeClient.generate_content(user, model=…,
      system_instruction=…)`; parse to `RoundVerdict` (`can_exist`, `typicality|None`, `issues[]`);
      **single normalization point** — malformed/contract-violating JSON raises (no `.get`-defaults).
- [x] 2.3 — `runner.py`: per-persona `raw/persona_XXXXX.json` skip-if-exists cache (gate on file
      existence unless `force`); `ThreadPoolExecutor(max_workers=cfg.workers)`; round-based retry of
      only failed rounds; distinct handling of failed vs possible; `sample_size` sampling.
- [x] 2.4 — Cost logging: reuse `LLMInteractionCollector` (immediate JSONL flush) to record each
      judge call's tokens/timing from `client.last_metadata`.

**Files Modified:** new `src/population_synthetic/analysis/persona_realism/{prompt,judge,runner}.py`,
new `tests/test_realism_judge_parse.py`.
**Dependencies:** Phase 1.

### Phase 3: Reduction + statistics layer (pure)
**Goal:** Verdict cache → per-combination realism statistics.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 3.1 — `reduce.py`: `RoundVerdict`→`PersonaVerdict` (possibility fraction p_i, typicality
      mean±SD over rounds, per-clash detection frequency), `PersonaVerdict`→`ComboRealism`
      (impossibility rate + N + successful-count, typicality distribution over can_exist personas,
      clash taxonomy). Frozen dataclasses; carry N and the successful-call count everywhere. Includes
      `LoadedPersona` + `load_persona_verdicts`/`load_combo_verdicts` (round-trips Phase 2's `asdict`
      cache back through `judge.parse_round_verdict`; `expected_ids` maps absent = failed → `None`).
- [x] 3.2 — `stats.py`: bootstrap CI on impossibility rate (over personas as the sampling unit);
      typicality dispersion (variance / entropy / tail-coverage) + distance-to-SCB + variance-equality
      test (Levene) among can_exist personas; ICC/α reliability across rounds (can_exist nominal;
      typicality ordinal by default, config-driven via new `judge.yaml` `reliability.typicality_level`).
- [x] 3.3 — Hard-rules validation subset (`validation.py`): load `hard_rules.yaml`, run its
      deterministic `incompatible_pair` checks (type-dispatched, extensible) on a seeded sampled
      subset, compare to judge `can_exist` (majority over rounds), report the 2×2 confusion +
      agreement + recall-on-rule-impossibilities (the validity anchor / QC).

**Files Modified:** new `.../persona_realism/{reduce,stats,validation}.py`, extend
`tests/test_realism_stats.py`. Also (additive, config-is-SoT for the Krippendorff level): added an
optional `reliability` block to `config/analysis/persona_realism/judge.yaml` and an optional
`reliability` field on `runner.JudgeConfig`.
**Dependencies:** Phase 1 (stats primitives), Phase 2 (verdict cache shape).

### Phase 4: IO / plotting + reporting (pure sinks + orchestrator)
**Goal:** Emit the publication artifacts idempotently.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 4.1 — `charts.py`: per-combo typicality-distribution + clash-taxonomy figures; the cross-combo
      `headline_map` (impossibility rate × typicality-dispersion-vs-SCB, SCB as a point). `Agg`
      backend, close figures. (Pure — returns `Figure`s; `HeadlinePoint` DTO is the map's plot input.)
- [x] 4.2 — `csv_writer.py` (fixed fieldnames via the `RealismRow` DTO) + `report.py` (per-combo +
      run-level JSON via `json.dump(indent=2, ensure_ascii=False)`, carrying pricing + provenance
      meta verbatim, the `cost_coverage` marker, the hard-rules validation block, and a
      reliability≠validity `reliability_note`).
- [x] 4.3 — `artifacts.py`: orchestrator taking a resolved combo `out_dir`; load verdict cache →
      reduce → stats (with SCB ref) → cost → sinks; per-unit idempotent skip unless `force`; dual
      PNG+SVG via `analysis/utils/figures.save_figure`; skip a chart only when genuinely empty. Also
      the cross-combo `write_headline_map` (map + combined `realism_summary.csv` + `run_report.json`).
- [x] 4.4 — Cost aggregation: reuse `generation_metadata` `persona_cost` + `persona_metrics.reduce_persona`
      over `llm_interactions.jsonl` to emit per-combination cost metadata; fail-fast if the judge
      model's pricing row is absent; attach the `cost_coverage` (`judged_this_run`/`total_personas`/
      `status`) resume-honesty marker.

**Files Modified:** new `.../persona_realism/{charts,csv_writer,report,artifacts}.py`,
new `tests/test_realism_artifacts.py`.
**Dependencies:** Phase 3.

> **Note (boundary decision, resolved in Phase 4):** `artifacts.py` consumes an *already-judged*
> verdict cache — it does NOT call the judge/runner (that side-effecting step is Phase 2's
> `runner.py`, invoked by the Phase-5 script *before* artifacts). Its per-combo entry
> `write_combo_artifacts` always computes the `RealismStats` (cheap/pure) so the cross-combo
> `write_headline_map` can seed the map even when every file is idempotently skipped; only the file
> *writes* honour the skip. Minor naming divergence: the run-level provenance/summary file is
> `run_report.json` (superset of the plan's `run_metadata.json` — carries provenance + per-combo
> summaries + the plotted headline points); the Phase-5 script may add/rename `run_metadata.json`.

### Phase 5: Script + GUI workflow wiring
**Goal:** Runnable via CLI and the GUI Flow Runner.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 5.1 — `scripts/analyze/analyze_persona_realism.py`: argparse (`--slug`/`--model`/`--strategy`/
      `--country`, `--output-base`, `--force`, `--workers`, `--sample`, `--judge-model` override,
      `--dpi`); `resolve_output_base`; `out_root = analysis_output_dir("persona_realism", base)`;
      read mapped combos + `real_{country}.json` with `for_read=True`; per-combo dispatch + real
      reference; idempotent per-combo skip; call `artifacts`.
- [x] 5.2 — Add `persona_realism` task to `config/gui/flows/analysis_workflow.yaml` (`enabled`,
      `supports_force`, `options` incl. `judge-model`/`sample`, `depends_on: [mapping]`) + node in the
      sibling `.layout.json`.
- [x] 5.3 — End-to-end smoke test with a **stubbed** judge client (no live CLI): tiny fixture
      population → runner → reduce → stats → artifacts; assert files written and metrics well-formed.

**Files Modified:** new `scripts/analyze/analyze_persona_realism.py`,
`config/gui/flows/analysis_workflow.yaml`, `config/gui/flows/analysis_workflow.layout.json`,
new `tests/test_persona_realism_smoke.py`.
**Dependencies:** Phase 4.

### Phase 6: Documentation
**Goal:** Discoverable and reproducible.
**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 6.1 — Add the `persona_realism` line to the CLAUDE.md analysis-registry paragraph.
- [x] 6.2 — Add the command to `docs/architecture/commands.md`.
- [x] 6.3 — Short guide `docs/development/persona-realism-judge.md` (invocation, config knobs,
      reliability-vs-validity caveat, cost sizing); link the brainstorm.

**Files Modified:** `CLAUDE.md`, `docs/architecture/commands.md`, new guide.
**Dependencies:** Phase 5.

---

## Testing Plan

### Unit Tests
- [ ] Parser: canonical JSON → `RoundVerdict`; malformed/contract-violating JSON **raises** (not
      `.get`-defaulted); `typicality` null iff `can_exist=false`.
- [ ] `bootstrap_ci` / `icc` / `krippendorff_alpha` / `variance_equality_test` against known-answer
      fixtures with `pytest.approx` (never `==`).
- [ ] Reduction: possibility fraction, typicality mean/SD, clash-frequency; N and successful-count
      carried through.
- [ ] Degenerate guards: single round → ICC skipped-reason (not NaN); all-identical typicality →
      zero dispersion handled; empty can_exist set → explicit skip.

### Integration Tests
- [ ] Runner resumption: second run without `--force` skips existing `persona_XXXXX.json`; `--force`
      recomputes.
- [ ] Failed-call accounting: a stubbed client that errors on some rounds → impossibility rate gated
      on successful calls; dropped count logged; failure ≠ "possible".

### Manual Verification
- [ ] Real run on a small Swedish combo + `real_swedish.json`: inspect the headline map shows SCB as
      a distinct competitor and the impossibility/dispersion values are plausible.
- [ ] Smoke-test Fable availability first: `claude -p "ping" --model claude-fable-5 --output-format
      json` (or via a one-persona run); if the model doesn't resolve, note the fallback tier.

### Edge Cases
- [ ] Combo with `sample_size` larger than the population (use all, no error).
- [ ] Persona missing an analyzed axis in the mapped file → fail-fast with persona/combo/field
      context.
- [ ] All personas judged possible (impossibility rate 0) → dispersion still computed; map point valid.

---

## Documentation Plan

- [x] Update `CLAUDE.md` analysis-registry paragraph with `persona_realism`.
- [x] Update `docs/architecture/commands.md` with the new command.
- [x] Create user guide: `docs/development/persona-realism-judge.md`.
- [x] Add a `claude-fable-5` note to the `model_pricing.yaml` header/source comment.
- [ ] Inline docstrings on the four-layer contract per module.

---

## Rollback Plan

1. **Before deployment:** the task is additive — a new subpackage, script, registry entry, and GUI
   node; no existing behavior changes. `stats_tests.py` and `model_pricing.yaml` are extended, not
   modified in place.
2. **Data considerations:** no migrations. Outputs are confined to
   `03_Analysis/persona_realism/`; deleting that folder fully reverts on-disk state.
3. **Rollback procedure:** revert the feature commits; remove the `persona_realism` blocks from
   `analysis_registry.yaml`, `analysis_workflow.yaml`(+layout), and the pricing row; delete the
   subpackage, script, config folder, and `03_Analysis/persona_realism/`. The added
   `stats_tests.py` functions are inert unless called and may be kept.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Base-branch coupling: cost pipeline lives only on the generation-metadata branch | High | Med | Merge that to `dev` first, or base this branch on it; flagged at top. Resolve before implement. |
| Judge cost (N × personas × combos ≈ 60k calls) | High | Med | Config `sample_size` per combo (default bounded); resumable cache; cost metadata surfaced per run. |
| `claude-fable-5` unavailable on the account | Med | High | Smoke-test before wiring; dropdown allows fallback to `claude-opus-4-8`/`sonnet-5`; document the check. |
| Judge conflates "unusual" with "impossible" (typicality trap) | Med | High | Prompt scaffolding + explicit "rare ≠ impossible" guardrail (twice); S1 costs 0; hard-rules validation subset audits can_exist. |
| Reliability ≠ validity misread as accuracy | Med | Med | Report ICC/α explicitly as consistency; state the validity limitation in report + guide; hard-rules subset is the only validity anchor. |
| Self-preference bias (judge favors same-family combos) | Low–Med | Med | Standardized mapped schema removes the stylistic channel; deferred panel approach noted; watch same-family combos scoring high. |
| Ragged/malformed LLM JSON | High | Low | Single fail-loud parser boundary; round-retry; failed rounds distinct from possible. |
| Non-determinism harms reproducibility | Med | Med | Cold temperature; seed the bootstrap RNG; persist run_metadata (model+version, prompt hash, N, config, lib versions) and raw per-round outputs. |
| Judge subprocess timeout too tight for Fable | Med | Med | Judge subprocess timeout is now **config-driven** (`judge.yaml` `timeout_seconds`, default 600) and threaded into the client via `_default_client_factory(timeout=cfg.timeout_seconds)`. Fable 5 single turns run for minutes; the client's own hardwired 120 s default caused whole rounds to fail. `ClaudeCodeClient`'s default stays 120 (only the judge factory raises it). |
| Cached judge input under-priced (`prompt_tokens=2`) | Med | Med | The judge prompt is prompt-cached, so `ClaudeCodeClient` sees `input_tokens≈2` (uncached remainder) while the real prompt lands in cache. The client now **additively** captures `cache_read_input_tokens`/`cache_creation_input_tokens` into `last_metadata` (as `cache_read_tokens`/`cache_creation_tokens`) without changing `prompt_tokens` semantics; these flow through `LLMInteractionEntry` → parser → `persona_metrics` → `cost.persona_cost(..., cache_read_tokens=, cache_creation_tokens=)`. Cache tokens are priced against the base input rate via a config-driven `cache_multipliers: {read: 0.1, write: 1.25}` block in `model_pricing.yaml` (fail-fast if cache tokens are supplied but the block is absent). Fully backward-compatible: `generation_metadata`'s cost path supplies no cache tokens, so its cost is byte-for-byte unchanged. |

---

## References

- Brainstorm (full matured design + judge-selection literature): `docs/development/brainstorms/individual-persona-realism-judge.md`
- Sibling to mirror: `src/population_synthetic/analysis/generation_metadata/`
- Judge-call client: `src/population_synthetic/clients/claude_code_client.py`
- Orchestration template: `scripts/generate/generate_identities_parallel.py`
- Registry + output-dir: `config/analysis/analysis_registry.yaml`, `src/population_synthetic/analysis/utils/registry.py`
- Shared stats: `src/population_synthetic/analysis/utils/stats_tests.py`, `.../utils/_stats.py`

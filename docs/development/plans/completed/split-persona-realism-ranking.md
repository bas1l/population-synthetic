# Plan: Split `persona_realism` into a per-combination judge + a `realism_ranking` aggregator

**Date:** 2026-08-05
**Author:** Basil
**Status:** Completed (2026-08-07)
**Base Branch:** `dev`
**Branch:** `feature/split-persona-realism-ranking`
**ADR:** [`decisions/2026-08-07-persona-realism-per-combination-split.md`](../../decisions/2026-08-07-persona-realism-per-combination-split.md)

> **Base-branch note.** Implemented on `feature/split-persona-realism-ranking`, branched from
> `dev` after the mapping-token PR merged (`864a827`). The working tree's unrelated
> in-progress changes (`fidelity/artifacts.py`, `population_cap/cap.py`, `utils/fs.py`, the two
> GUI flow YAMLs, `test_population_cap.py`) were carried onto the branch uncommitted at the
> author's request; `runner.py` and `test_persona_realism_smoke.py` carry both that
> persona-id-keyed-cache work and this plan's changes.

---

## Overview

The LLM-as-judge task (`persona_realism`) currently judges one combination *and* compares it
against the SCB reference *and* draws the cross-combination headline map, all inside one country
loop. This plan splits it into a strictly per-combination judge and a new downstream
`realism_ranking` task that owns every cross-combination claim. As part of the split the
SCB-sampled population stops being the *origin* of the impossibility axis and becomes an ordinary
judged competitor, so the hypothesis "SCB-sampled personas may be less realistic because
conditional chained sampling never cross-references attributes" becomes testable rather than
assumed-false by construction.

## Problem Statement

Three separate defects, all traceable to the same missing seam.

**1. The per-combination output is not per-combination.** `analyze_persona_realism.py:414-443`
judges `real_{country}` first, holds its `ComboRealism` in memory, and threads it as `scb_ref`
into every synthetic combination. `stats.py:207-228` then computes `distance_to_scb` and a
Levene/Brown-Forsythe `variance_equality` test *inside* `compute_realism_stats`. The results are
baked into `{combo}.json` (`dispersion.distance_to_scb`, `dispersion.variance_equality`) and into
five columns of `{combo}.csv` (`dist_variance`, `dist_entropy`, `dist_tail_coverage`,
`variance_equality_stat`, `variance_equality_p` — `artifacts.py:272-276`). A single combination's
artefact therefore cannot be reproduced without re-running a different combination first. This is
connascence of execution order between units: the strongest and most distant coupling form.

**2. The cross-combination half is unreachable from the GUI.** The registry declares
`dispatch: "per_combo"` (`analysis_registry.yaml:187`), so the GUI spawns one process per
combination and `write_headline_map` (`artifacts.py:494-595`) always receives a single-element
list. `analysis_workflow.yaml:131-133` and `docs/development/persona-realism-judge.md` both
document the ranking as a CLI-batch-only capability. Nothing anywhere in the repo reads
`realism_summary.csv`, `run_report.json`, or `headline_map.*`.

**3. The impossibility axis presupposes its own answer.** `distance_to_scb` and the headline map's
pinned `y = 0.0` for the reference (`artifacts.py:292-293`, red star at `charts.py:173-179`) encode
*SCB is the origin; closer to SCB is better*. The open research question is whether SCB-sampled
personas are themselves internally incoherent. A metric that measures distance *from* SCB cannot
answer a question *about* SCB.

**Directional caveat that must survive the fix.** `docs/development/brainstorms/individual-persona-realism-judge.md`
records that the target for **typicality dispersion** was *matching* SCB, not maximising spread,
precisely because the observed LLM failure mode is mode collapse. The two axes therefore need
opposite treatments, and conflating them would invert the interpretation:

| Axis | Quantity | SCB's role | Direction |
|------|----------|-----------|-----------|
| **A — validity** | impossibility rate (`can_exist`) | ordinary competitor, ranked | lower is better, for everyone including SCB |
| **B — coverage** | typicality dispersion (variance / entropy / tail coverage) | **target to match** | `distance_to_scb` near zero is better |

Removing SCB-as-origin applies to **Axis A only**. `distance_to_scb` survives on Axis B, moved
downstream unchanged.

## Goals

### In Scope

1. Make `persona_realism` a strictly per-combination filter: judging one combination requires no
   other combination, and its artefacts are byte-reproducible in isolation.
2. Enumerate `real_{country}` as an ordinary combination in the judge, with no reference role.
3. Emit a stable, self-describing per-persona tidy CSV as the inter-task contract.
4. Create the `realism_ranking` analysis task: cross-combination ranking on Axis A, the SCB
   contrast on both axes, and model-vs-method significance testing.
5. Move `headline_map.*`, `realism_summary.csv`, and `run_report.json` into the new task, with the
   headline map re-anchored so SCB is a plotted competitor rather than the origin.
6. Fix the four defects found during analysis (undeclared config defaults, dead config,
   structurally-zero `n_failed`, no staleness rule for partial combo dirs).

### Out of Scope

- **Changing what the judge asks or how it scores.** `judge_prompt.md`, `n_rounds`, temperature,
  the `can_exist`/`typicality`/severity contract, and `hard_rules.yaml` are untouched. Existing
  verdict caches must remain valid and reusable — no re-judging is required by this plan.
- **A multi-judge panel** to control self-preference bias. Deferred in the brainstorm; still
  deferred.
- **Ranking two fully-coherent combinations apart.** The brainstorm explicitly assigns that to the
  distribution/fidelity branch. `realism_ranking` must not quietly re-acquire it.
- **Reaching back to SCB marginal tables.** Statistics operate on judge outputs only; the judge
  never consults the API distributions. (`realism_ranking` compares against the *judged* SCB
  competitor, not against SCB proportion tables.)
- **Replicate generation runs.** One run per combination remains; the resulting confound is
  recorded as a caveat, not fixed.
- Any change to `population_cap`, `mapping`, or the validity gate.

## Success Criteria

- [x] `python scripts/analyze/analyze_persona_realism.py --slug <one-slug>` on a clean output base
      produces the complete artefact set for that slug, with no `real_*` combination judged and no
      reference-dependent field anywhere in its output.
- [x] Judging the same slug twice, in either order relative to any other slug, produces identical
      `{combo}.json` and `{combo}.csv` (modulo the timestamp field).
- [x] `grep -r "scb_ref\|distance_to_scb\|variance_equality" src/population_synthetic/analysis/persona_realism/`
      returns nothing.
- [x] `real_{country}` appears in the judge's combination enumeration and produces the same artefact
      set as any synthetic combination — including the per-persona tidy CSV — with no special-casing
      beyond its `real_sample_size` cap and prefix draw.
- [x] `03_Analysis/persona_realism/{country}/` contains **only** combination directories; no
      country-level aggregate file remains.
- [x] `python scripts/analyze/rank_persona_realism.py` produces
      `03_Analysis/realism_ranking/{country}/` containing `realism_ranking.json`,
      `realism_summary.csv`, `headline_map.png/.svg`, `impossibility_forest.png/.svg`, and
      `scb_contrast.csv`.
- [x] The Axis A ranking includes `real_{country}` as an ordinary ranked row, and the ranking is
      computable and correct whether SCB places first, last, or in the middle.
- [x] `realism_ranking.json` records: the multiple-comparison correction name, every rate's
      denominator, every skipped combination with a machine-readable reason, every skipped
      statistical test with a reason, the pseudo-replication and one-run-per-combination caveats,
      and the resolved library versions plus bootstrap seed.
- [x] Consuming combinations judged under different `judge_model`, `prompt_template_hash`, or
      `n_rounds` raises, naming the offending combination.
- [x] The GUI runs `persona_realism` per combination and `realism_ranking` once, chained
      `depends_on: [persona_realism]`; the ranking is no longer CLI-batch-only.
- [x] `pytest` passes, including a characterization test written before the split that pins the
      pre-split end-to-end output in order-normalized form.
- [x] `ruff check src/` passes.

## Definitions

- **Combination (unit):** one `(country, model, strategy)` triple identified by its slug, plus the
  synthetic competitor `real_{country}`. It is the atom of the per-combination task: exactly one
  directory under `03_Analysis/persona_realism/{country}/`.
- **Per-combination (strictly):** the task's output for unit *U* is a deterministic function of
  *U*'s own inputs and the config. It does not read, accumulate, or depend on the existence,
  content, or processing order of any other unit. Testable form: the two byte-identity criteria in
  Success Criteria.
- **Competitor:** any unit that appears as a ranked row in `realism_ranking`, including
  `real_{country}`. A competitor has no privileged position on Axis A.
- **Reference / target (Axis B only):** `real_{country}`'s typicality dispersion, which other units
  are scored against by absolute distance. This is the *only* surviving privileged role, and it is
  confined to Axis B.
- **Consumable combination:** a combination directory the aggregator will read. Testable form:
  `{combo}.json` exists **and** `{combo}_personas.csv` exists **and** the CSV's row count equals
  `{combo}.json`'s `n_personas`. Anything else is partial and is skipped-with-reason (or raises
  under `--strict`) — never silently ranked.
- **Homogeneous consumption set:** all consumed combinations share identical `judge_model`,
  `prompt_template_hash`, and `n_rounds`. A heterogeneous set raises: ranking units judged by
  different judges measures the judges, not the units.
- **Impossibility rate:** fraction of a unit's judged personas whose `can_exist` majority across
  successful rounds is `false`. Denominator = personas with ≥1 successful round. Always reported
  with its denominator.

---

## Technical Design

### System classification

Batch, pipe-and-filter analytics pipeline with a **two-level (per-unit / cross-unit) structure**.
The per-unit stage parses one unit's raw artefacts and persists a metrics record; the cross-unit
stage loads many such records and runs statistical comparisons. The file-backed intermediate
artefact between them is the deliverable that lets the expensive LLM work be cached once and the
statistical battery evolve independently. Dominant quality bar is statistical validity and
reproducibility, not throughput.

### Approach

Cut the seam at the on-disk contract, not at an in-memory hand-off. The judge writes per-persona
tidy rows plus its single-unit report; the aggregator depends on that schema and on nothing inside
the judge's implementation. Dependency direction is one-way: `realism_ranking` never imports
`persona_realism` judging internals, and `persona_realism` never learns that an aggregator exists.

The three shared concerns are placed as follows:

- **Tidy per-persona CSV schema** → `analysis/utils/realism_csv.py`, following the existing
  `analysis/utils/validity_csv.py` precedent (a writer used by the producer, a reader used by the
  consumer, one schema definition). This is cross-process shared infrastructure, which is exactly
  what `analysis/utils/` is for.
- **`JudgeConfig`** → extracted from `runner.py` into `persona_realism/config.py`, importable
  without dragging in the LLM client layer. `realism_ranking` needs only the `bootstrap` block from
  it.
- **Judge identity for the homogeneity guard** → read from each `{combo}.json`'s existing
  `provenance` block, not re-derived. The aggregator compares what was actually used, not what the
  config currently says.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Tidy per-persona CSV as the contract** | Full granularity for KW/Dunn and mixed models; schema is explicit and validated at the boundary; cheap repeat reads; matches `validity_csv.py` precedent | One new artefact per combination; schema must be versioned | **Chosen** |
| Aggregator re-reduces the `persona_*.json` verdict caches via `load_combo_realism` | No new artefact | Makes `reduce.py` a shared dependency (aggregator reaching into judge internals — common coupling); re-does reduction every run; sees partial combination dirs that have caches but no report, defeating the staleness rule | Rejected |
| Aggregator reads only `{combo}.json` | Smallest change | Aggregate-only — no per-persona rows, so no rank-based test, no mixed model, no effect size. Kills the significance half outright | Rejected |
| Leave the SCB contrast upstream, move only the map | Smallest diff | The split becomes cosmetic: the judge still must run `real_{country}` first and hold it in memory, so order dependence and non-isolated artefacts both survive | Rejected |
| Recompute `distance_to_scb` downstream from the tidy CSVs | Removes order dependence at its root; Axis B direction preserved; the aggregator already loads every unit's typicality values | Axis B numbers move out of `{combo}.json` (schema change, tests follow) | **Chosen** |
| Drop `distance_to_scb` entirely | Simplest | Inverts the interpretation of Axis B — mode collapse would read as success. Contradicts the design record | Rejected |
| Bradley–Terry / pairwise ranking of combinations | Familiar ranking machinery | Already rejected in the brainstorm: it silently re-measures typicality under the name of realism, and two coherent tuples have no coherence-based winner | Rejected (re-confirmed) |

### Canonical ids and human labels

Canonical id = registry key = GUI task key = `03_Analysis/` folder name = subpackage name. These
five must never drift.

| Canonical id | Human label (GUI) | Folder | Script | Dispatch |
|---|---|---|---|---|
| `persona_realism` | Persona Realism Judge (LLM-as-judge) | `persona_realism` | `scripts/analyze/analyze_persona_realism.py` | `per_combo` (unchanged) |
| `realism_ranking` | Realism Ranking (combinations vs SCB) | `realism_ranking` | `scripts/analyze/rank_persona_realism.py` | `slugs` (new) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `persona_realism/runner.py` | Judge one combination's personas N rounds; resume/top-up; write verdict + telemetry caches | slug, config, mapped individuals → per-persona JSON/JSONL + `RunnerSummary` | any other combination; SCB; ranking; aggregation |
| `persona_realism/config.py` *(new)* | Load + validate `judge.yaml`, `hard_rules.yaml`, prompt template; fail-fast | config dir → `JudgeConfig` | the LLM client; the runner; the filesystem layout of outputs |
| `persona_realism/stats.py` | Single-combination statistics only | one `ComboRealism` → `RealismStats` | any other combination; SCB; `variance_equality`; `distance_to_scb` |
| `persona_realism/artifacts.py` | Write one combination's artefacts | `ComboRealism` + config → `{combo}.json`, `{combo}.csv`, `{combo}_personas.csv`, 2 figures | the country loop; the headline map; the summary CSV |
| `analysis/utils/realism_csv.py` *(new)* | The per-persona tidy schema — one definition, writer + reader | rows ⇄ CSV | which task is calling it; country; ranking semantics |
| `realism_ranking/loader.py` *(new)* | Discover consumable combinations; enforce completeness + homogeneity; return typed records | output base, filters → `list[CompetitorRecord]`, `list[(slug, reason)]` | how the judge produced the files; LLM anything |
| `realism_ranking/builder.py` *(new)* | Axis A ranking, Axis B dispersion contrast, factor significance, caveats | `list[CompetitorRecord]` → ranking dict + rows | file paths; matplotlib; the judge |
| `realism_ranking/charts.py` *(new)* | Render only — never compute | ranking dict → figures | statistics; file discovery |
| `scripts/analyze/rank_persona_realism.py` *(new)* | CLI edge: parse args, resolve base, orchestrate, print paths | argv → files on disk + exit code | statistical method choices |

```
src/population_synthetic/analysis/
├── persona_realism/          # per-combination only
│   ├── config.py             # NEW — JudgeConfig, extracted from runner.py
│   ├── runner.py             # unchanged responsibility; loses JudgeConfig
│   ├── stats.py              # loses scb_ref, _SCB_GROUP, lines 207-228
│   ├── artifacts.py          # loses _headline_point, write_headline_map
│   ├── charts.py             # loses HeadlinePoint, plot_headline_map
│   ├── report.py             # loses write_run_report
│   └── csv_writer.py         # RealismRow loses 5 cross-combo columns
├── realism_ranking/          # NEW — cross-combination only
│   ├── __init__.py
│   ├── loader.py
│   ├── builder.py
│   └── charts.py
└── utils/
    └── realism_csv.py        # NEW — the inter-task tidy contract
```

### Statistical design

**Axis A — impossibility ranking (all competitors, SCB included).**
Point rate + bootstrap CI per competitor, reusing `bootstrap_ci` (`stats_tests.py:555`) with the
seeded local `default_rng` from `judge.yaml`'s `bootstrap` block. Ranking is by point rate with CIs
plotted; CI overlap is *displayed*, never asserted as a test.

**Axis A — SCB contrast.** Each synthetic competitor vs `real_{country}`: rate difference with a
bootstrap CI on the difference, plus a two-proportion test, Holm-corrected across the family of
contrasts. Effect magnitude reported alongside every p-value.

**Axis B — dispersion contrast.** `distance_to_scb` per measure (`variance`, `entropy`,
`tail_coverage`) plus `variance_equality_test` (`stats_tests.py:771`, `center` from config) vs the
SCB target. Moved verbatim from `stats.py:207-228`; direction and interpretation preserved.

**Factor significance — model vs method.** Kruskal–Wallis on per-persona typicality means grouped
by model, and again grouped by method, with Dunn + **Holm** post-hoc — mirroring
`generation_metadata`. `real_{country}` is **held out** of these tests: it is not a model×method
cell and would unbalance the design; it enters only via the pairwise contrasts above. The binary
`can_exist` gets a logit-linked mixed model where the `[analysis]` extra is available; where it is
not, the test is **skipped with a recorded reason**, never silently omitted.

**Mandatory honesty fields in the output JSON**, following the `model_ranking` /
`method_significance` precedent:
- `correction: "holm"` stated explicitly on every family of tests.
- Every rate carries `n` and `denominator`.
- `caveats: ["pseudo_replication", "single_run_per_combination"]` with prose.
- `skipped_combinations: [{slug, reason}]` and `skipped_tests: [{test, reason}]` — silent exclusion
  reads downstream as "everything was included".
- `provenance: {bootstrap_seed, library_versions{numpy,scipy,statsmodels,scikit-posthocs}, judge_model, prompt_template_hash, n_rounds, consumed_artifacts[]}`.
- Degenerate inputs (group with <2 samples, zero variance, non-convergent model) are guarded
  explicitly and skipped with a reason — never allowed to emit a `NaN` that flows into a chart.

---

## Implementation Plan

### Phase 1: Characterization + config hygiene
**Goal:** Pin current behaviour before touching it, and close the fail-fast holes so the split
doesn't inherit them.

- [x] Task 1.1 — Write a characterization test that runs the current end-to-end path over a tiny
      fixture directory and snapshots `{combo}.json`, `{combo}.csv`, `realism_summary.csv`, and
      `run_report.json` in **order-normalized** form (sort rows by slug, drop timestamps). This is
      the safety net for every later phase; it will be rewritten in Phase 6, not deleted silently.
- [x] Task 1.2 — Declare `tail_threshold` and `variance_center` under `reliability:` in
      `judge.yaml` with the documented rationale, and change `artifacts.py:395-396` from
      `cfg.reliability.get(..., default)` to fail-fast reads. These two tunables are currently
      hardcoded in practice and `tail_threshold` also drives the per-combination typicality chart.
- [x] Task 1.3 — Resolve the dead config. `severity_weights` and `impossibility_severities`
      (`judge.yaml:37-46`) are loaded, validated (`runner.py:155, 196-197`), and stamped into
      provenance (`artifacts.py:115-116`) but never used in any computation — impossibility is
      decided by `possible_majority` on the boolean `can_exist` (`reduce.py:213`).
      **Default decision: delete both keys, their validation, and their provenance stamping**,
      since a provenance field that describes nothing is worse than absent. *This is a
      user-confirmable decision point — the alternative is to wire severity gating into
      `reduce_persona`, which is a behaviour change and out of scope here.*
- [x] Task 1.4 — Thread the runner's persona roster into `write_combo_artifacts` as `expected_ids`
      so `n_failed` stops being structurally zero. `RunnerSummary` (`runner.py:209`) already holds
      it and is currently discarded at `analyze_persona_realism.py:308-316`.

**Files Modified:**
- `tests/test_persona_realism_characterization.py` — new, snapshot harness
- `config/analysis/persona_realism/judge.yaml` — declare 2 keys, delete 2 keys
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — fail-fast reads, `expected_ids`
- `src/population_synthetic/analysis/persona_realism/runner.py` — drop dead-config validation
- `scripts/analyze/analyze_persona_realism.py` — pass the roster through

**Dependencies:** None. Land before the `runner.py` working-tree changes are stacked on.

---

### Phase 2: Make the judge strictly per-combination
**Goal:** Remove every trace of cross-combination knowledge from `persona_realism`, and make
`real_{country}` an ordinary enumerated combination.

- [x] Task 2.1 — Delete the `scb_ref` parameter from `compute_realism_stats` (`stats.py:154`),
      delete `_SCB_GROUP` (`stats.py:60`) and the whole `stats.py:207-228` block. `RealismStats.dispersion`
      keeps only the unit's own `variance` / `entropy` / `tail_coverage`.
- [x] Task 2.2 — Drop the five cross-combination columns from `RealismRow` and `FIELDNAMES`
      (`csv_writer.py:24,61`) and from `_build_row` (`artifacts.py:272-276`).
- [x] Task 2.3 — Add `real_{country}` to the judge's combination enumeration (`_enumerate_combos`,
      `analyze_persona_realism.py:208`) so it is selected like any other unit, keeping only its
      `real_sample_size` cap and deterministic prefix draw (`runner.py:277`). The prefix draw stays
      as-is and is **not** a confound: `judge.yaml:55-59` documents that the SCB population is
      already an i.i.d. sample, so a prefix is a valid reproducible subsample.
- [x] Task 2.4 — Flatten the country loop (`analyze_persona_realism.py:414-454`): remove the
      real-first ordering, the `scb_ref` hand-off at `:433`, the `country_artifacts` accumulation
      at `:432,:443`, and the `write_headline_map` call at `:447`. Combinations become an unordered
      set.
- [x] Task 2.5 — Delete `_headline_point` (`artifacts.py:287`), `write_headline_map`
      (`artifacts.py:494-595`), `HeadlinePoint` + `plot_headline_map` (`charts.py:46,154`), and
      `write_run_report` (`report.py:92`). They are recreated in Phase 5, not moved by copy-paste —
      the headline map's reference special-casing is being redesigned, not relocated.
- [x] Task 2.6 — Extract `JudgeConfig` (`runner.py:116`) into `persona_realism/config.py` with no
      LLM-client imports, and update every importer.

**Files Modified:**
- `src/population_synthetic/analysis/persona_realism/stats.py` — remove the cross-combo block
- `src/population_synthetic/analysis/persona_realism/csv_writer.py` — schema shrinks by 5 columns
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — remove both cross-combo sinks
- `src/population_synthetic/analysis/persona_realism/charts.py` — remove the map
- `src/population_synthetic/analysis/persona_realism/report.py` — remove `write_run_report`
- `src/population_synthetic/analysis/persona_realism/config.py` — new
- `src/population_synthetic/analysis/persona_realism/runner.py` — `JudgeConfig` moves out
- `scripts/analyze/analyze_persona_realism.py` — flatten the loop, enumerate the real combo

**Dependencies:** Phase 1

---

### Phase 3: Emit the inter-task contract
**Goal:** Give the aggregator a stable, validated, per-persona input.

- [x] Task 3.1 — Create `analysis/utils/realism_csv.py` defining the tidy schema once — one row per
      judged persona: `persona_id`, `slug`, `country`, `model`, `strategy`, `is_real_reference`,
      `n_rounds_attempted`, `n_rounds_successful`, `can_exist_true_votes`, `can_exist_majority`,
      `typicality_mean`, `typicality_sd`, `typicality_rounds` (delimited), `max_severity`,
      `clash_count`. Counts are `int` and stay `int` across the round-trip. Writer + reader in one
      module, mirroring `validity_csv.py`.
- [x] Task 3.2 — Write `{combo}_personas.csv` from `write_combo_artifacts`, overwriting whole (never
      appending), so N runs are equivalent to one.
- [x] Task 3.3 — Validate on read: a missing column, an unparseable count, or a row count
      disagreeing with `{combo}.json`'s `n_personas` raises with the offending file named.
- [x] Task 3.4 — Ensure the tidy CSV distinguishes *zero* from *absent* — a persona with no
      successful round has an empty `typicality_mean`, not `0.0`.

**Files Modified:**
- `src/population_synthetic/analysis/utils/realism_csv.py` — new
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — emit the tidy CSV

**Dependencies:** Phase 2

---

### Phase 4: The `realism_ranking` loader
**Goal:** Discover and gate the consumption set. No statistics yet.

- [x] Task 4.1 — Create the `analysis/realism_ranking/` subpackage with `loader.py` defining a
      frozen `CompetitorRecord` DTO (slug, country, model, strategy, `is_real_reference`,
      per-persona rows, single-unit stats block, provenance block).
- [x] Task 4.2 — Resolve the upstream through the registry —
      `analysis_output_dir("persona_realism", output_base)` — never a literal path. Enumerate
      combinations from the capped `_mapped/_index.json` via `resolve_mapped_dir`, plus the
      `real_{country}` competitor, mirroring `model_ranking/loader.py:179-205`.
- [x] Task 4.3 — Implement the **consumable-combination** gate from Definitions. Partial directories
      (verdict caches present, no `{combo}.json`) are skipped with a machine-readable reason, or
      raise under `--strict`. This is the explicit complete-output marker; several such directories
      exist on disk today.
- [x] Task 4.4 — Implement the **homogeneity guard**: compare `judge_model`,
      `prompt_template_hash`, and `n_rounds` across the consumption set from each `{combo}.json`
      provenance block; a mismatch raises and names the offending combination.
- [x] Task 4.5 — Adopt the three-tier failure policy of `model_ranking/loader.py:15-24`: missing
      index or malformed artefact raises with a message naming the upstream script to re-run;
      missing per-combination artefact is a skip; degenerate values are omitted, never imputed.

**Files Modified:**
- `src/population_synthetic/analysis/realism_ranking/__init__.py` — new
- `src/population_synthetic/analysis/realism_ranking/loader.py` — new

**Dependencies:** Phase 3

---

### Phase 5: Statistics and sinks
**Goal:** Every cross-combination claim, plus the artefacts that carry it.

- [x] Task 5.1 — `builder.py`: Axis A ranking of all competitors (SCB included) by impossibility
      rate with seeded bootstrap CIs, each carrying its denominator.
- [x] Task 5.2 — `builder.py`: Axis A pairwise SCB contrasts — rate difference with bootstrap CI,
      two-proportion test, Holm-corrected across the family, effect magnitude beside every p-value.
- [x] Task 5.3 — `builder.py`: Axis B dispersion contrast — `distance_to_scb` per measure and
      `variance_equality_test` vs the SCB target, direction preserved (near zero is better).
- [x] Task 5.4 — `builder.py`: model-vs-method Kruskal–Wallis + Dunn/Holm on per-persona typicality
      means with `real_{country}` held out; logit mixed model on `can_exist` where the `[analysis]`
      extra resolves, skipped-with-reason where it does not. Guard every degenerate input (group
      <2, zero variance, non-convergence) explicitly.
- [x] Task 5.5 — `builder.py`: assemble the honesty block — correction name, denominators, skipped
      combinations, skipped tests, both caveats, bootstrap seed, library versions, consumed-artefact
      list. Write `realism_ranking.json`, `realism_summary.csv`, `scb_contrast.csv`.
- [x] Task 5.6 — `charts.py`: redesigned headline map with SCB plotted as an ordinary competitor
      (no pinned origin, no privileged marker on Axis A), plus an `impossibility_forest` chart
      showing every competitor's rate and CI. Charts render only — no computation, all numbers
      arrive pre-computed. Use `utils/figures.save_figure` for the PNG+SVG pair.
- [x] Task 5.7 — `scripts/analyze/rank_persona_realism.py` mirroring `rank_models.py`: docstring
      with consumed inputs, exact output inventory, `Usage:` and flag reference; repeatable
      `--country/--model/--strategy/--slug`; `--output-base`, `--no-charts`, `--strict`, `--force`;
      `resolve_output_base` then `analysis_output_dir("realism_ranking", base)`; per-country
      idempotent `--force`-guarded skip keyed on `realism_ranking.json`; print every written path;
      `sys.exit(1)` with an actionable message when there is nothing to rank.

**Files Modified:**
- `src/population_synthetic/analysis/realism_ranking/builder.py` — new
- `src/population_synthetic/analysis/realism_ranking/charts.py` — new
- `scripts/analyze/rank_persona_realism.py` — new

**Dependencies:** Phase 4

---

### Phase 6: Wiring, tests, documentation
**Goal:** The new task is a first-class node everywhere, and the docs stop lying.

- [x] Task 6.1 — Register `realism_ranking` in `config/analysis/analysis_registry.yaml` with all
      five required keys (`label`, `description`, `folder`, `script`, `dispatch: "slugs"`).
- [x] Task 6.2 — Add the DAG node to `config/gui/flows/analysis_workflow.yaml`:
      `depends_on: [persona_realism]`, `min_combos: 2`, `supports_force: true`, and `options:` keyed
      to the dash-form CLI flags. Add a layout position in `analysis_workflow.layout.json` to the
      right of `persona_realism`.
- [x] Task 6.3 — Update the task-set tests: `tests/test_analysis_registry.py:26-41`
      (`_EXPECTED_FOLDERS` set equality) and `tests/test_workflow_state.py:113-136` (ordering set +
      `order.index("persona_realism") < order.index("realism_ranking")`).
- [x] Task 6.4 — Rewrite the Phase 1 characterization test as two tests: an isolation test for the
      judge (the two byte-identity criteria) and an end-to-end smoke test for the ranking over a
      tiny fixture directory.
- [x] Task 6.5 — Update `tests/test_realism_stats.py` and `tests/test_realism_artifacts.py` — the
      cross-combination assertions (`test_write_headline_map_renders_map_and_summary` at `:276`,
      `test_write_run_report_structure` at `:126`) move to new
      `tests/test_realism_ranking_{loader,builder}.py`. Update
      `tests/test_persona_realism_smoke.py` (currently modified in the working tree).
- [x] Task 6.6 — Update docs: the canonical-id table in `docs/architecture/commands.md:174-190`;
      the analysis-registry paragraph and DAG description in `CLAUDE.md:111-118`;
      `docs/architecture/sub-packages.md:155-157` for the new subpackage; and
      `docs/development/persona-realism-judge.md`, whose GUI-limitation section is made obsolete by
      this split and whose output-layout section is now wrong.
- [x] Task 6.7 — Record a short ADR-style entry (context / decision / consequences) covering the
      two load-bearing decisions: per-unit output is order-independent, and SCB is a competitor on
      Axis A but the target on Axis B.

**Files Modified:**
- `config/analysis/analysis_registry.yaml`, `config/gui/flows/analysis_workflow.yaml`,
  `config/gui/flows/analysis_workflow.layout.json`
- `tests/test_analysis_registry.py`, `tests/test_workflow_state.py`,
  `tests/test_realism_stats.py`, `tests/test_realism_artifacts.py`,
  `tests/test_persona_realism_smoke.py`, `tests/test_realism_ranking_loader.py` (new),
  `tests/test_realism_ranking_builder.py` (new)
- `CLAUDE.md`, `docs/architecture/commands.md`, `docs/architecture/sub-packages.md`,
  `docs/development/persona-realism-judge.md`

**Dependencies:** Phase 5

---

## Testing Plan

### Unit Tests
- [x] `compute_realism_stats` accepts no reference argument and its output contains no
      `distance_to_scb` / `variance_equality` key.
- [x] `RealismRow`/`FIELDNAMES` no longer carry the five cross-combination columns.
- [x] `realism_csv` round-trip: counts stay `int`, an absent `typicality_mean` stays empty rather
      than becoming `0.0`, a missing column raises naming the file.
- [x] Loader: a directory with verdict caches but no `{combo}.json` is skipped with a reason; the
      same under `--strict` raises.
- [x] Loader: a row-count/`n_personas` disagreement raises.
- [x] Loader: a combination judged under a different `judge_model` raises, naming it.
- [x] Builder: impossibility rate and denominator hand-computed on a fixture with a known answer.
- [x] Builder: bootstrap CI reproducible across two calls with the same seed via a local
      `default_rng` (never the global RNG).
- [x] Builder: Kruskal–Wallis + Dunn/Holm validated against `scipy` / `scikit-posthocs` with
      `pytest.approx` — no exact float equality anywhere.
- [x] Builder: a group with <2 samples, a zero-variance group, and a non-convergent mixed model each
      produce a recorded skip reason, not a `NaN`.
- [x] Builder: `real_{country}` is present in the Axis A ranking and absent from the model/method
      KW groups.
- [x] `JudgeConfig` imports from `config.py` without pulling in the LLM client module.

### Integration Tests
- [x] Judge one slug on an empty output base: the full artefact set appears, no `real_*` directory
      is created, and no output field depends on another unit.
- [x] Judge slug A then slug B, and separately B then A: both `{combo}.json` files are identical
      across the two orderings modulo timestamp.
- [x] End-to-end over a tiny fixture: judge 3 synthetic combinations + `real_swedish_02`, then rank
      — every declared output file appears and `realism_ranking.json` validates against the honesty
      contract.
- [x] `realism_ranking` run twice without `--force` is a no-op that reports the skip; with `--force`
      it rewrites.
- [x] GUI ordering: `ordered_tasks()` places `realism_ranking` after `persona_realism`.

### Manual Verification
- [x] Run the judge from the GUI on a single checked combination and confirm no country-level file
      is produced.
- [x] Run `realism_ranking` from the GUI with ≥2 combinations checked and confirm the headline map
      renders SCB as an ordinary point.
- [x] Confirm existing verdict caches on the real output base are reused, not re-judged (no LLM
      cost incurred by this refactor).
- [x] Inspect `realism_ranking.json` and confirm every p-value is accompanied by an effect size and
      the correction name.
- [x] Sanity-check the headline direction: a deliberately mode-collapsed fixture must show a large
      Axis B `distance_to_scb`, not a good score.

### Edge Cases
- [x] Exactly one consumable combination in a country → ranking skips with a reason (`min_combos`),
      does not emit a one-point map.
- [x] `real_{country}` missing or unjudged → Axis B and the SCB contrasts are skipped with a
      reason; Axis A ranking of the synthetic competitors still runs.
- [x] Every competitor has an impossibility rate of exactly 0 → ranking is emitted with ties made
      explicit, no division by zero.
- [x] A combination where every persona failed every round → excluded with a reason, denominator 0
      never used as a divisor.
- [x] `n_rounds = 1` → ICC and Krippendorff's α are undefined upstream and must arrive as absent,
      not zero.

---

## Documentation Plan

- [x] Update `CLAUDE.md` — the analysis-registry paragraph and the DAG shape (new terminal node).
- [x] Update `docs/architecture/commands.md` — canonical-id table and the new command.
- [x] Update `docs/architecture/sub-packages.md` — the `realism_ranking` subpackage.
- [x] Rewrite the stale sections of `docs/development/persona-realism-judge.md` — output layout and
      the now-obsolete GUI-limitation section.
- [x] Add the ADR entry covering order-independence and the two-axis SCB treatment.
- [x] Add a changelog entry.

---

## Rollback Plan

1. **Before deployment:** the whole change is confined to one feature branch off `dev`; revert by
   dropping the branch. No merge to `dev` until the characterization and isolation tests pass.
2. **Data considerations:** No re-judging is required and no LLM cost is incurred — the
   `persona_*.json` verdict caches are the expensive artefacts and their schema is untouched.
   However, `{combo}.json` and `{combo}.csv` **change schema** (five columns and two dispersion keys
   removed, one new CSV added). Existing derived artefacts on the output base are stale after the
   change and must be regenerated with `--force` on the artefact-writing path only. The
   country-level `headline_map.*`, `realism_summary.csv`, and `run_report.json` under
   `persona_realism/{country}/` become orphans and should be deleted manually after the new task
   reproduces them under `realism_ranking/{country}/`.
3. **Rollback procedure:** revert the branch merge; regenerate `{combo}.json`/`{combo}.csv` with
   `--force`; delete `03_Analysis/realism_ranking/`. Verdict caches survive either direction.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `runner.py` has 163 uncommitted insertions and `test_persona_realism_smoke.py` is modified; Phase 2 moves `JudgeConfig` out of the same file | High | Med | Land or shelve the working-tree changes **before** starting Phase 2. Phase 1 deliberately touches `runner.py` only lightly so the conflict surface stays small |
| `config/gui/flows/analysis_workflow.yaml` is also modified in the working tree | Med | Low | Phase 6 is last; rebase before touching it |
| Schema change to `{combo}.json`/`{combo}.csv` silently invalidates artefacts on the shared OneDrive output base | Med | Med | Loader's staleness rule raises on shape mismatch naming the upstream script; document the one-time `--force` regeneration in the changelog |
| Dropping `distance_to_scb` from Axis A is misread as dropping it entirely, inverting the mode-collapse interpretation | Med | High | Axis A/B table in the plan, an explicit Definitions entry, the mode-collapsed fixture in Manual Verification, and the ADR entry |
| Ranking silently mixes combinations judged by different judge models or prompt versions | Med | High | Homogeneity guard (Task 4.4) raises; identity read from stamped provenance, not from current config |
| `[analysis]` extra absent → mixed model silently omitted | Med | Med | Skipped-with-reason contract (Task 5.4) plus a unit test asserting the reason is recorded |
| Pseudo-replication and single-run confounds make p-values look stronger than they are | High | Med | Both recorded as machine-readable caveats in the output JSON, following the existing `method_significance` precedent — not merely in prose |
| New aggregator quietly re-acquires "rank two coherent combinations apart", which the brainstorm assigned to the fidelity branch | Low | Med | Out of Scope entry; review gate at `/plan-review` |
| Characterization test is written against order-dependent output and so pins a bug | Med | Med | Task 1.1 mandates order-normalized snapshots |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Characterization + config hygiene | ~0.5 day | None |
| Phase 2 — Strictly per-combination judge | ~1 day | Phase 1 |
| Phase 3 — Inter-task contract | ~0.5 day | Phase 2 |
| Phase 4 — Loader + gates | ~0.5 day | Phase 3 |
| Phase 5 — Statistics + sinks | ~1.5 days | Phase 4 |
| Phase 6 — Wiring, tests, docs | ~1 day | Phase 5 |

---

## References

- `docs/development/brainstorms/individual-persona-realism-judge.md` — the design record; source of
  the typicality-matching (not maximising) constraint and the previously-rejected ranking approaches
- `docs/development/persona-realism-judge.md` — operator guide; documents the GUI limitation this
  split fixes
- `docs/development/model-method-significance-recap.md` — precedent for the significance half and
  the two honesty caveats
- `src/population_synthetic/analysis/model_ranking/loader.py` — the canonical downstream-reader
  pattern this plan follows
- `~/.claude/knowledge/data-pipeline-engineering/` — guides 01 (two-level pattern), 02 (idempotency,
  complete-output marker, provenance), 03 (bootstrap seeding, Holm, denominators), 05 (seams,
  connascence of execution order)

---

## Implementation record (2026-08-07)

Implemented in full. Four deliberate deviations from the plan as written, each because the plan's
text did not hold up against the code:

1. **`--rewrite-artifacts` was added (new).** Rollback §2 said stale artefacts "must be regenerated
   with `--force` on the artefact-writing path only" — but no such path existed: `--force` was
   threaded into *both* `run_combo_judgements` (which truncates every verdict cache and re-judges)
   and the artefact rewrite. Following that instruction literally would have re-judged all 4551
   cached personas at full LLM cost, contradicting the plan's own "no re-judging is required".
   `--rewrite-artifacts` now rebuilds the derived files from the existing cache at zero LLM cost,
   and the two triggers are documented as distinct everywhere they appear. The zero cost is
   structural: the flag puts the runner in a new **plan-only** mode that resolves the persona roster
   (so `n_failed` still works) and returns without constructing a client. Without that, the flag
   would have been a second trap — the caches hold **1 round** while `judge.yaml` declares
   `n_rounds: 3`, so an ordinary run tops every persona up by two rounds, which is a full re-judge
   in all but name.

2. **Task 1.3 resolved as *keep, stamped as declared-unused*** rather than the plan's default of
   deleting `severity_weights` / `impossibility_severities`. The keys, their validation and their
   provenance stamping stay; `judge.yaml` and every report now carry an explicit
   `severity_config_status` note saying they gate nothing. (Author's call at the plan's marked
   decision point.)

3. **Task 1.4's premise was wrong.** `RunnerSummary` did *not* already hold the persona roster (it
   had `n_selected`, a count). A `selected_ids` field was added to carry it, which is what makes
   `n_failed` stop being structurally zero.

4. **The homogeneity guard reads `prompt_template_sha256`**, not `prompt_template_hash` — the latter
   name does not exist in the stamped provenance block.

Two things found while implementing and fixed beyond the plan's scope, both in the direction the
plan's own honesty rules require:

- `variance_equality_test` returned `statistic=inf, p=0.0` when *some* group had zero spread but not
  all of them did (scipy's Levene denominator collapses). Passed through to `scb_contrast.csv` that
  reads as overwhelming evidence of unequal spread rather than as an undefined test. It is now
  skipped-with-a-reason naming the zero-spread group, with a regression test.
- `bootstrap_difference_ci`, `two_proportion_test` (with Cohen's h) and a public `holm_adjust` were
  added to `analysis/utils/stats_tests.py` rather than reimplemented inside the new subpackage — two
  Holm implementations in one codebase is one too many.

**Test surface:** `tests/test_realism_csv.py` (10), `tests/test_realism_ranking_loader.py` (11),
`tests/test_realism_ranking_builder.py` (20), `tests/test_realism_ranking_e2e.py` (6), plus the
updated `test_realism_stats.py`, `test_realism_artifacts.py`, `test_persona_realism_smoke.py`,
`test_analysis_registry.py`, `test_workflow_state.py`.

**Operational follow-up (not done by this change — it touches the shared OneDrive output base):**
the 51 existing combination directories under `03_Analysis/persona_realism/swedish_02/` hold
artefacts in the old schema. Regenerate them with
`analyze_persona_realism.py --rewrite-artifacts` (zero LLM calls — all 4551 personas are cached at
`n_rounds=1`), then delete the four orphaned country-level files (`headline_map.png`,
`headline_map.svg`, `realism_summary.csv`, `run_report.json`) once `rank_persona_realism.py` has
reproduced them under `03_Analysis/realism_ranking/swedish_02/`.

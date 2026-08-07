# Plan: Severity-Driver Attribution for the Clash Heatmaps

**Date:** 2026-08-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/split-persona-realism-ranking`
**Branch:** `feature/severity-driver-attribution`

---

## Overview

The `realism_ranking` severity heatmaps (`severity_heatmap_s1/s2/s3.png`) report *how much* of each
model × method cell carries a clash at a given severity, but cannot say *what* clashed. This plan
adds a second, finer-grained file to the `persona_realism` on-disk contract — one row per
`(persona, round, clash)` carrying both attribute names **and** their category values — and a
`severity_drivers` block in `realism_ranking` that ranks, per cell per level, which attribute pairs
and which category pairs produced the alert. Everything is re-derived deterministically from the
verdict caches already on disk: zero LLM calls, no prompt change, no re-judge.

## Problem Statement

The judge already returns the answer and the pipeline throws it away.

Each judge issue is `{"attributes": [attr_a, attr_b], "severity": "S1|S2|S3", "explanation": "..."}`
(`config/analysis/persona_realism/judge_prompt.md:53-76`), and the persona's own attribute *values*
sit in the same verdict-cache file. But:

- `reduce.py:204` collapses an issue to `ClashKey(sorted_pair, severity)` and drops `explanation`;
  the values are never attached.
- `{combo}.json`'s `clash_taxonomy` keeps the attribute pair but is combination-level with no
  persona linkage and no values.
- The inter-task contract `{combo}_personas.csv` carries only `max_severity`, `clash_count`, and
  `clash_count_s1/_s2/_s3` — counts of distinct `ClashKey`s, with zero issue-level detail.
- `realism_ranking/loader.py:145-190` reads only `{combo}.json` + `{combo}_personas.csv`, and lifts
  only `impossibility` / `dispersion` / `reliability` / `provenance` from the JSON. It never reads
  `clash_taxonomy`.

Consequence: no cross-combination code path can see which attributes clashed. A reader of
`severity_heatmap_s3.png` sees that `ollama_mistral_nemo_12b × all_pick_v2` has a high S3 rate and
has no way to learn — without opening individual JSON files by hand — that it is almost entirely
`employment_status × employment_type` (`Student × Permanent Full-time`). That is the single most
actionable fact the judge produces, and it is currently unreachable.

## Goals

### In Scope

1. A new per-clash tidy CSV in the `persona_realism` published contract, `{combo}_clashes.csv`,
   with its own `SCHEMA_VERSION`, writer, and strict reader, carrying attribute names, category
   values, severity, and round index.
2. A parallel explanations side file, `{combo}_clash_explanations.csv`, inside the combination
   directory, carrying the judge's free text keyed to the same rows. Not read by the loader.
3. A `severity_drivers` block in `realism_ranking`, reporting-only, ranking attribute pairs and
   nested category pairs per `(model, method, severity level)`, with SCB as an ordinary competitor.
4. Six flat output tables beside the existing heatmaps: `severity_drivers_s{1,2,3}.csv`
   (attribute-pair grain) and `severity_driver_values_s{1,2,3}.csv` (category-pair grain).
5. Extraction of the shared CSV-contract primitives now that this is the third case
   (`realism_csv`, `validity_csv`, `realism_clash_csv`).
6. Regeneration of the 51 existing `swedish_02` combinations via `--rewrite-artifacts`.

### Out of Scope

- **Any change to the judge prompt, judge schema, or `Issue` DTO.** A prompt change alters
  `prompt_template_sha256`, which invalidates the homogeneity guard against all 51 already-judged
  combinations and forces a full re-judge at full LLM cost. Nothing here touches it.
- **Any classifier, clustering, or verdict engine over the explanation text.** The pipeline counts
  and ranks; interpretation is a reading step over the emitted tables.
- **Wiring severity into any ranked number.** `severity_weights` / `impossibility_severities` stay
  declared-but-unwired, per the ADR.
- **Significance testing across driver prevalences.** Comparative claims would require a correction
  battery; the driver tables stay descriptive.
- Countries other than `swedish_02` (nothing is Sweden-specific, but only `swedish_02` exists).
- Backfilling `clash_taxonomy` into the loader — superseded by this finer-grained file.

## Success Criteria

- [ ] `{combo}_clashes.csv` and `{combo}_clash_explanations.csv` are written for all 51 `swedish_02`
      combinations by `analyze_persona_realism.py --rewrite-artifacts`, with **zero LLM calls**
      (asserted by the `plan_only is True` / `force is False` test triple).
- [ ] Running `--rewrite-artifacts` twice produces **byte-identical** files for both new artifacts.
- [ ] Judging combo A then B produces byte-identical artifacts to judging B then A (existing
      order-independence test extended to the two new files).
- [ ] The reconciliation invariant holds for every combination: the count of distinct
      `(persona_id, attr_a, attr_b, severity)` tuples at level *L* in `{combo}_clashes.csv` equals
      the sum of `clash_count_s{L}` over that combination's `{combo}_personas.csv` rows. A violation
      raises, naming both files and `--rewrite-artifacts`.
- [ ] A combination with no clashes at all produces a **header-only** `{combo}_clashes.csv`, not an
      absent file; the reader accepts it and raises only on a genuinely absent file.
- [ ] `realism_ranking.json` contains a `severity_drivers` block whose per-cell denominators are
      identical to the corresponding `severity.levels.{L}.grid` cell denominators.
- [ ] `severity_drivers_s3.csv` for `swedish_02_all_pick_v2_ollama_mistral_nemo_12b` ranks
      `employment_status × employment_type` first, and its nested value row names
      `Student × Permanent Full-time`.
- [ ] Every emitted driver row carries its denominator and the level's `penalised` flag.
- [ ] Excluded combinations (real reference where inapplicable, zero-successful-round personas,
      unresolvable attribute names) are counted and reported, never silently dropped.
- [ ] `ruff check src/` clean; `pytest` green.

## Definitions

Terms whose meaning this plan's correctness depends on. Pinned concretely because the counting is
otherwise ambiguous in at least three defensible ways.

- **issue** — a raw judge assertion, exactly as emitted:
  `{"attributes": [a, b], "severity": S, "explanation": str}`. The judge's own term. Used only when
  talking about the LLM's output.
- **clash** — an issue after canonicalisation: the attribute pair **sorted** (so `(a,b)` and `(b,a)`
  are one clash, matching `ClashKey` at `reduce.py:59-71`) and the explanation dropped. The
  codebase's existing term.
- **driver** — a clash ranked within a `(competitor, severity level)` cell by how many of that
  cell's personas exhibit it. The new term, and the only new one introduced.
- **row grain of `{combo}_clashes.csv`** — one row per
  `(persona_id, round_index, attr_a, attr_b, severity)`, deduplicated **within a round**, mirroring
  the `seen` set in `reduce_persona` (`reduce.py:200-206`). Therefore: rows per
  `(persona, pair, severity)` equals that key's `clash_frequency` value (rounds in which it was
  seen), and the count of distinct `(persona, pair, severity)` equals `clash_count_s*`.
- **driver prevalence** — `n_personas_with_this_clash_at_this_level / n_personas_in_the_cell`. The
  denominator is `len(record.personas)`, **identical** to the denominator `_severity_grids` uses for
  the heatmap cell (`builder.py:345-349`), so a driver prevalence is always readable against its
  heatmap cell.
- **non-additive** — driver prevalences within a cell do **not** sum to the heatmap cell rate, for
  three compounding reasons: one persona may exhibit several distinct clashes; each clash names two
  attributes, so per-attribute totals sum to 2× the clash count; and severity levels are not a
  partition (a persona with both S3 and S2 is counted in both grids). Consequence for rendering:
  never a pie, never a 100%-stacked bar. The counting unit is footnoted on every emitted table.
- **unresolved** — a clash whose `attr_a` or `attr_b` does not appear as a key in that persona's own
  `attributes` map, so the value join fails. `judge.py:92-113` does **not** validate attribute names
  against the persona's axes, so this is reachable via judge error. It is recorded as a boolean
  column and an aggregate count; it is **not** a new judge-emitted field and requires no prompt
  change.
- **reporting-only** — the block feeds no ranking, no contrast, and no significance test, and
  changes no number already published. Asserted by test, mirroring
  `test_realism_ranking_builder.py:553-556`.

---

## Technical Design

### Approach

Extend the published on-disk contract at the `persona_realism` side; consume it at the
`realism_ranking` side. The producer already holds everything needed —
`LoadedPersona.attributes` (`reduce.py:166`) supplies the values, the verdict cache supplies the
issues — so the value join is a dict lookup performed at write time, deterministic and free.

This is the only route consistent with the governing ADR
(`docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md`), which explicitly
rejects having the aggregator re-read the `persona_*.json` verdict caches: that would make
`reduce.py` a shared dependency, re-do reduction every run, and let the aggregator see partial
combination directories that have caches but no report — defeating the staleness rule. The
explanations, `attr_a`/`attr_b` and per-round detail all live in those caches, which makes reaching
into them the tempting shortcut; the ADR names it and forbids it.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New per-clash CSV in the contract; producer writes, aggregator reads | Respects the one-way file-backed seam; order-independent; zero-cost regeneration; per-unit rows enable per-cell ranking | Third contract file on the same seam; needs its own completeness invariant | **Chosen** |
| Aggregator reads the `persona_*.json` verdict caches directly | No contract change; no artifact rewrite | Explicitly rejected by the ADR (common coupling; re-reduces every run; sees partial dirs) | Rejected |
| Widen the existing `{combo}_personas.csv` with driver columns | One file, one version | Wrong grain — a persona has 0..N clashes; would force either a repeating-group encoding or lossy top-1 truncation | Rejected |
| Add `clash_taxonomy` (already in `{combo}.json`) to the loader | Smallest change | Combination-level only, no persona linkage, no category values — cannot produce a per-cell prevalence with a correct denominator | Rejected |
| Ask the judge to emit values / a category label directly | Richer, model-attributed | Changes `prompt_template_sha256` → invalidates the homogeneity guard against all 51 judged combos → full re-judge at full LLM cost, for data already derivable for free | Rejected |
| LLM-cluster the explanation text into themes | Human-readable themes | Introduces a classifier into the pipeline; non-deterministic; violates the counts-and-ranks-only constraint | Rejected (interpretation stays a reading step) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/utils/tidy_csv.py` *(new)* | Shared CSV cell codecs and header validation | scalar ↔ str; header tuple → validation error | Any specific column set, severity, personas, clashes |
| `analysis/utils/realism_clash_csv.py` *(new)* | The per-clash contract: schema, writer, strict reader | `Sequence[RealismClashRow]` → file; file → `list[RealismClashRow]` | Paths, output layout, how rows are derived, ranking |
| `persona_realism/reduce.py` *(extended)* | Pure derivation of clash rows from a reduced persona | `PersonaRealism` + `attributes` map → `list[RealismClashRow]` | File formats, CSV, paths |
| `persona_realism/artifacts.py` *(extended)* | Emit the two new files under the existing `force` gate | `ComboRealism` + out_dir + force → files on disk | Ranking, cross-combination anything |
| `realism_ranking/loader.py` *(extended)* | Read the new file into `CompetitorRecord`; gate on it | combination dir → `CompetitorRecord.clashes` | Verdict caches, `reduce.py`, judge internals |
| `realism_ranking/builder.py` *(extended)* | Pure computation of the `severity_drivers` block | `Sequence[CompetitorRecord]` + top_n + min_count → dict | Paths, figures, config files (values arrive as arguments) |
| `scripts/analyze/rank_persona_realism.py` *(extended)* | Resolve config at the edge; flatten and write the six CSVs | ranking dict → CSV files | How drivers are computed |

Directory delta, per combination:

```
03_Analysis/persona_realism/{country}/{combo}/
    {combo}.json                        (unchanged; gains 1 provenance key)
    {combo}.csv                         (unchanged)
    {combo}_personas.csv                (unchanged, schema v2)
    {combo}_clashes.csv                 NEW  — the contract, schema v1
    {combo}_clash_explanations.csv      NEW  — side file, not read by the loader
    persona_*.json / persona_*.jsonl    (unchanged, read-only inputs)

03_Analysis/realism_ranking/{country}/
    severity_drivers_s{1,2,3}.csv       NEW  — attribute-pair grain
    severity_driver_values_s{1,2,3}.csv NEW  — category-pair grain
```

Both new files live **inside** the combination directory. Country-level files under
`persona_realism/{country}/` are declared orphans by the ADR.

#### `{combo}_clashes.csv` — columns

`persona_id, slug, country, model, strategy, is_real_reference, round_index, attr_a, attr_b,
value_a, value_b, severity, unresolved`

`attr_a`/`attr_b` are the **sorted** pair, matching `ClashKey` canonicalisation — otherwise one
driver splits into two ranks. `value_a`/`value_b` are empty when `unresolved` is true; empty is
absent, never a substitute for a real value.

The row does not carry its own denominator — a deliberate divergence from `realism_csv.py`'s third
stated property, recorded in the module docstring. The base lives in the sibling
`{combo}_personas.csv`, and the loader reads both files per combination and joins on `persona_id`.
`round_index` is carried so round-level detail is not lost.

#### `{combo}_clash_explanations.csv` — columns

`persona_id, round_index, attr_a, attr_b, severity, explanation`

Always written, even when empty, so "no clashes" is distinguishable from "not run" — the convention
already established by `map_populations.py:162-179` for `{slug}.misses.csv`. Its documented hazard
there is staleness; the same coupling applies, and it is regenerated in the same `force` block as
its primary.

#### `severity_drivers` block shape

Reuses `_grid` (`builder.py:178-249`) verbatim, including the synthesised adapter dicts with the
`"_record"` back-pointer (`builder.py:357-364`). That resolves SCB placement for free: `_grid`
already extracts the real competitor via `is_real_reference` and carries it under `"real"` rather
than as a grid row — exactly as the heatmaps do.

```
severity_drivers: {
  levels: { S3|S2|S1: {
      meaning, direction, penalised,      # reused from the existing `directions` dict
      grid: { models, methods, cells{model}{method}, real, note } } },
  metric, counting_unit, non_additive, reporting_only,
  top_n, min_count, n_unresolved, excluded
}
```

Each cell payload: `{slug, denominator, affected, drivers: [{rank, attr_a, attr_b, n_personas,
prevalence, values: [{rank, value_a, value_b, n_personas, prevalence}]}]}`.

Tie-break is total and deterministic: `n_personas` desc → `attr_a` → `attr_b` (and for values,
→ `value_a` → `value_b`). Without it, ranks are not byte-stable in the tail.

### Constraints inherited from the ADR

1. **Order-independence.** The new writer must produce a deterministic byte stream. Total sort key:
   `(persona_id, round_index, attr_a, attr_b, severity)`, confirmed to have no residual ties.
2. **`--rewrite-artifacts`, never `--force`.** `--force` truncates verdict caches and re-judges 4551
   personas at full LLM cost. The regeneration pass goes through the existing plan-only path
   (`analyze_persona_realism.py:409`, `plan_only=rewrite_artifacts and not force`), where the runner
   returns before any client is constructed (`runner.py:521-538`) — zero cost structurally, not by
   operator discipline.
3. **S1 is never a defect.** The per-level `penalised` flag travels with every driver table. A
   ranking that ignores it asserts that unusual people are defects — the ADR names this the same
   class of error as treating SCB as the origin on Axis A.
4. **Severity stays reporting-only.** `severity_drivers` is a sibling descriptive block and must not
   become an input to any ranked number.
5. **Homogeneity guard untouched.** One `judge_model` / `prompt_template_sha256` / `n_rounds` across
   the consumption set, read from stamped provenance. Nothing here changes the prompt.

---

## Implementation Plan

### Phase 1: Shared primitives and the contract module
**Goal:** The per-clash contract exists, round-trips, and raises correctly — with no producer or
consumer wired to it yet.

**Started:** 2026-08-07
**Completed:** 2026-08-07

- [x] 1.1 — Extract `analysis/utils/tidy_csv.py`: the cell codecs (`_parse_int`, `_parse_bool`,
      `_parse_optional_float`, the `true`/`false` tokens, the "empty means absent, never 0.0" rule),
      the header-subset validation with its error-message shape, and the write-whole-never-append
      writer. Primitives only — no schema-driven CSV framework.
- [x] 1.2 — Repoint `realism_csv.py` and `validity_csv.py` at the shared primitives, preserving
      their public surfaces and error strings exactly.
- [x] 1.3 — Fold the duplicated severity ordering: `persona_realism/artifacts.py:85`
      `_SEVERITY_ORDER` duplicates `utils/realism_csv.py:62` `SEVERITY_LEVELS`. Import the one
      definition. Also fold the two `severity_rank` dicts (`artifacts.py:271`,
      `persona_realism/charts.py:107`).
- [x] 1.4 — Write `analysis/utils/realism_clash_csv.py`: module docstring arguing the design (why a
      second file at a finer grain rather than widening the existing one; the deliberate
      no-denominator-on-the-row divergence and the join that compensates); `SCHEMA_VERSION = 1`;
      frozen `RealismClashRow`; `FIELDNAMES = tuple(f.name for f in fields(...))`;
      `write_realism_clashes_csv(rows, path)`; `read_realism_clashes_csv(path, *, expected_counts)`.
- [x] 1.5 — Implement the reconciliation check inside the reader: `expected_counts` is the
      per-severity distinct-`(persona, pair, severity)` totals from the sibling personas CSV; a
      mismatch raises naming both files and `--rewrite-artifacts`.
- [x] 1.6 — Reader distinguishes absent file (raise `FileNotFoundError`) from present-with-zero-rows
      (valid, returns `[]`).

**Implementation notes (deviations worth a reviewer's attention):**

- `read_realism_clashes_csv` gained a third keyword, `expected_counts_source`. The reconciliation
  error must name *both* files, but the reader is forbidden to know the output layout, so it cannot
  derive the sibling's path from its own — the caller (which already holds both paths) supplies it.
  Omitted, the message names the sibling generically.
- `expected_counts` defaults to `None` (check skipped), mirroring `read_realism_personas_csv`'s
  `expected_rows`. A level *present in the schema but absent from the mapping* is asserted to be
  zero rather than skipped, so an omitted level cannot silently drop its invariant.
- The writer **enforces** the canonical sorted pair, the severity vocabulary, the
  unresolved-implies-empty-values rule, and grain uniqueness, raising on violation. Canonicalisation
  itself stays upstream in the Phase 2 derivation; the contract only refuses to serialise a row that
  breaks it.
- `SEVERITY_RANK` was added beside `SEVERITY_LEVELS` in `realism_csv.py` as the single definition
  behind both folded `severity_rank` dicts; `charts.py`'s legend order/captions now derive from
  `SEVERITY_LEVELS` too, which was the same literal a third time.

**Files Modified:**
- `src/population_synthetic/analysis/utils/tidy_csv.py` — new, shared primitives
- `src/population_synthetic/analysis/utils/realism_clash_csv.py` — new, the contract
- `src/population_synthetic/analysis/utils/realism_csv.py` — repoint at primitives
- `src/population_synthetic/analysis/utils/validity_csv.py` — repoint at primitives
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — remove duplicated constants
- `src/population_synthetic/analysis/persona_realism/charts.py` — remove duplicated constant

**Dependencies:** None

### Phase 2: Producer — derive and emit
**Goal:** All 51 combinations carry both new files, regenerated at zero cost.

- [ ] 2.1 — Add a pure `clash_rows(persona_realism, attributes, slug_fields)` function to
      `reduce.py` returning `list[RealismClashRow]`: iterate rounds, dedupe within a round using the
      same `seen` convention as `reduce_persona`, sort the attribute pair, join each name against
      the persona's `attributes` map, set `unresolved` + empty values on a failed join.
- [ ] 2.2 — Add the parallel explanations-row derivation, keyed identically.
- [ ] 2.3 — Extract an `_emit_csv(path, build_rows, force, logger)` helper in `artifacts.py`,
      mirroring the existing `_emit_figure`, and route the personas CSV plus both new files through
      it — `write_combo_artifacts` otherwise gains a fourth and fifth near-identical block on an
      already-long function.
- [ ] 2.4 — Wire both new writes into `write_combo_artifacts` under the same `force` gate as the
      other artifacts, so `--rewrite-artifacts` regenerates the **set**, never a mixed-generation
      tree.
- [ ] 2.5 — Stamp `clash_csv_schema_version` into `_provenance_meta` (`artifacts.py:146`) beside the
      existing `persona_csv_schema_version`, as a separate key.
- [ ] 2.6 — Run `analyze_persona_realism.py --rewrite-artifacts` over all 51 `swedish_02`
      combinations. Verify zero LLM calls and byte-identical output on a second run.

**Files Modified:**
- `src/population_synthetic/analysis/persona_realism/reduce.py` — pure row derivation
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — `_emit_csv`, two new writes, provenance key

**Dependencies:** Phase 1

### Phase 3: Consumer — load, rank, emit
**Goal:** `severity_drivers` in the JSON and six CSVs beside the heatmaps.

- [ ] 3.1 — `loader.py`: add `clashes_csv_path` at `:160`, a missing-file skip branch mirroring the
      personas-CSV branch at `:164-167` (same remediation wording naming `--rewrite-artifacts`), the
      reader call at `:173` with the reconciliation counts derived from the already-loaded rows, and
      a `clashes: tuple[RealismClashRow, ...]` field on `CompetitorRecord`.
- [ ] 3.2 — `builder.py`: add `_severity_drivers(records, *, top_n, min_count)` above
      `build_ranking`, modelled directly on `_severity_grids` — same adapter dicts with `"_record"`,
      same default-argument closure binding, same denominator, reusing the `directions` dict.
- [ ] 3.3 — Suppress or flag ranks below `min_count` rather than publishing a rank-1 driver with
      n=2; count what was suppressed into the block.
- [ ] 3.4 — Insert `"severity_drivers": _severity_drivers(...)` into the `build_ranking` return
      literal beside `"severity"` (`:728`), with the same two-line comment stating it is outside
      `axis_a` and changes no existing number. Append `_Skip` records rather than emitting `None`
      when it cannot compute.
- [ ] 3.5 — Add two module-level flatteners returning `list[dict]`, keyed by slug like
      `summary_rows` / `scb_contrast_rows`, and add both to `__all__`.
- [ ] 3.6 — `rank_persona_realism.py`: add `--driver-top-n` and `--driver-min-count`, resolved at the
      edge and passed as arguments (the builder docstring forbids it reading config); six
      `_write_csv` calls with their `None`-message branches.
- [ ] 3.7 — Report exclusions: combinations skipped, personas with zero successful rounds, and the
      `n_unresolved` total, all surfaced in the block and on stdout.

**Files Modified:**
- `src/population_synthetic/analysis/realism_ranking/loader.py` — third contract file, new record field
- `src/population_synthetic/analysis/realism_ranking/builder.py` — `_severity_drivers`, flatteners, `__all__`
- `scripts/analyze/rank_persona_realism.py` — two CLI flags, six CSV writes

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `tests/test_realism_clash_csv.py` — table-driven round-trip via a `_row(**overrides)` factory,
      mirroring `tests/test_realism_csv.py:23-45`.
- [x] Stale-schema raise, provoked by column surgery on a written file (the
      `test_realism_csv.py:112-115` pattern), asserting the message names `--rewrite-artifacts`.
- [x] Absent file raises `FileNotFoundError`; header-only file returns `[]`.
- [x] `unresolved=True` rows keep `value_a`/`value_b` empty and are never coerced to a value.
- [ ] Pair canonicalisation: an issue emitted as `(b, a)` produces the same row as `(a, b)`.
      *(Phase 2 — `reduce.py` owns the canonicalisation; Phase 1 only enforces the sorted pair at
      the contract boundary, tested there.)*
- [ ] Within-round dedupe matches `reduce_persona`'s `seen` convention. *(Phase 2.)*
- [x] Byte-determinism: write the same rows twice, compare bytes; and shuffle the input order,
      confirm identical output.
- [x] Reconciliation mismatch raises, naming both files and `--rewrite-artifacts` (unit level,
      against hand-built rows; the end-to-end producer↔consumer version stays under Integration).
- [ ] `_severity_drivers` on a hand-computed fixture — extend the `_with_severities` mutator pattern
      (`test_realism_ranking_builder.py:464-471`) with clash rows.
- [ ] Tie-break determinism: two drivers with equal counts always rank in the same order.
- [ ] `min_count` suppression is counted, not silently dropped.
- [ ] Assert `severity_drivers` has not leaked into `axis_a`, contrasts, or factor tests, mirroring
      `test_realism_ranking_builder.py:553-556`.

### Integration Tests
- [ ] **Reconciliation** — distinct `(persona, pair, severity)` count per level equals the summed
      `clash_count_s*` from the personas CSV. This is simultaneously the completeness invariant and
      the regression test; a deliberately corrupted pair must raise.
- [ ] Loader gate: a combination directory missing `{combo}_clashes.csv` yields the skip reason under
      default and raises under `strict`, using the `_write_combo(..., clashes_csv=False)` switch
      added to `test_realism_ranking_loader.py:61-105`.
- [ ] Denominator agreement: every `severity_drivers` cell denominator equals the corresponding
      `severity.levels.{L}.grid` cell denominator.
- [ ] `--rewrite-artifacts` CLI dispatch triple, extending
      `test_persona_realism_smoke.py:495-542`: `artifacts_force is True`, `force is False`,
      `plan_only is True`.
- [ ] e2e in `test_realism_ranking_e2e.py`: judge → rank on a `tmp_path` base produces all six CSVs.
- [ ] Order-independence: judging A-then-B vs B-then-A yields byte-identical new artifacts.

### Manual Verification
- [ ] Run the full `--rewrite-artifacts` pass over the 51 `swedish_02` combinations; confirm the run
      reports zero LLM calls and zero cost.
- [ ] Confirm `severity_drivers_s3.csv` ranks `employment_status × employment_type` first for
      `swedish_02_all_pick_v2_ollama_mistral_nemo_12b`, with `Student × Permanent Full-time` as its
      top value row — the case verified by hand in `persona_00213.json`.
- [ ] Read `severity_drivers_s1.csv` for a strong model and confirm the S1 drivers read as
      tail-reach, not defects.
- [ ] Confirm the SCB row (`real_swedish_02`) appears in all six tables as an ordinary competitor.

### Edge Cases
- [ ] A combination with zero clashes at every level (header-only file, cell with `drivers: []`).
- [ ] A persona with zero successful rounds (contributes no rows; still counted in the denominator).
- [ ] A cell where every persona shares one clash (prevalence 1.0).
- [ ] An unjudged `(model, method)` pair — `None`, never `0.0`, per `_grid`'s guarantee.
- [ ] A judge-hallucinated attribute name → `unresolved` row, counted, run does not fail.
- [ ] `n_rounds > 1` (the current data is all `n_rounds: 1`; the round dimension must be exercised
      by a fabricated fixture).

---

## Documentation Plan

- [ ] `docs/development/persona-realism-judge.md:99-104` — add both files to the per-combination
      artefact table; extend the `--rewrite-artifacts` section (`:106-127`) and the schema-version
      note (`:172-175`).
- [ ] `docs/architecture/commands.md:211-215` — the regeneration invocation and the two new ranking
      flags.
- [ ] `config/analysis/analysis_registry.yaml:171-220` — both task descriptions enumerate their
      published outputs in prose; add the new files.
- [ ] `CLAUDE.md` — the `persona_realism` / `realism_ranking` architecture paragraph gains the
      per-clash contract file.
- [ ] New ADR — a second on-disk contract file on the same seam, plus the deliberate
      no-denominator-on-the-row divergence. The existing ADR records two decisions together because
      the second only became expressible once the first was made; this is the same shape.
- [ ] The counting-unit and non-additivity footnote must appear on every emitted table and in the
      JSON block, not only in the docs.

---

## Rollback Plan

1. **Before regeneration:** the branch is revertible in isolation — no existing artifact schema
   changes, so `git revert` of the feature commits restores the prior behaviour exactly.
2. **Data considerations:** the two new files are purely additive. No existing file changes shape;
   `{combo}.json` gains one provenance key, which readers tolerate (the loader checks for required
   keys, not exact key sets). Deleting the new files returns the tree to its prior state.
3. **If the loader gate proves too strict** (every pre-existing output base is skipped until
   regenerated): the fallback is to downgrade the missing-clashes-CSV branch from a skip to an empty
   tuple plus a recorded reason, leaving Axis A unaffected. This is a one-branch change, noted here
   because the current loader has no precedent for a tolerated-missing artifact.
4. **Rollback procedure:** revert the feature commits; delete `{combo}_clashes.csv` and
   `{combo}_clash_explanations.csv` from the 51 combination directories; re-run
   `rank_persona_realism.py --force` to rewrite the country's ranking outputs without the new block.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Making the clashes CSV mandatory skips every combination on any output base not yet regenerated | High | Med | Regeneration is one zero-cost command; skip reason names it verbatim, matching the existing personas-CSV precedent. Rollback item 3 is the escape hatch. |
| Non-additive prevalences misread as a partition | Med | High | Counting unit footnoted on every table and carried in the JSON; no pie/stacked rendering; `non_additive` is a data field, not prose in a docstring. |
| S1 drivers read as defects | Med | High | `penalised` flag travels with every row; S1 tables carry an explicit caption, as the S1 heatmap already does (`charts.py:397-407`). |
| Byte-determinism broken by an unstable sort | Med | High | Total sort key with no residual ties; a double-write byte-comparison test and the A/B order test both gate it. |
| Reconciliation invariant is wrong because the dedupe convention diverges from `reduce.py` | Med | High | The grain is defined against `reduce_persona`'s `seen` set in Definitions, and a unit test asserts the two agree. |
| Extracting shared primitives regresses `realism_csv` / `validity_csv` error messages | Med | Med | Existing tests assert on message content; preserve public surfaces and strings exactly, and run the full suite before Phase 2. |
| Scope creep into classifying explanation text | Med | Med | Out of Scope is explicit; the side file is deliberately unread by the loader. |
| `n_rounds: 1` everywhere means the round dimension ships untested | High | Med | A fabricated multi-round fixture exercises it (`_write_cache` pattern, `test_realism_artifacts.py:125-139`). |
| A driver ranked rank-1 on n=2 is over-read | Med | Med | `--driver-min-count` suppresses-and-counts; denominators on every row. |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — primitives + contract module | ~1 session; 4 files touched, 2 new | None |
| Phase 2 — producer + regeneration | ~1 session; 2 files touched + a 51-combo rewrite pass | Phase 1 |
| Phase 3 — consumer + outputs | ~1 session; 3 files touched | Phase 2 |

---

## References

- ADR: `docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md`
- Completed plan: `docs/development/plans/completed/split-persona-realism-ranking.md`
- Operator guide: `docs/development/persona-realism-judge.md`
- Contract to mirror: `src/population_synthetic/analysis/utils/realism_csv.py`
- Side-file precedent: `scripts/analyze/map_populations.py:162-179`

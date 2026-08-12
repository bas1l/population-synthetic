# Plan: Severity-Driver Attribution for the Clash Heatmaps

**Date:** 2026-08-07
**Author:** Basil
**Status:** Completed
**Completed:** 2026-08-12 21:55
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
4. ~~Six flat output tables beside the existing heatmaps: `severity_drivers_s{1,2,3}.csv`
   (attribute-pair grain) and `severity_driver_values_s{1,2,3}.csv` (category-pair grain).~~
   **Revised post-implementation (2026-08-07, operator request): two flat output tables,
   `severity_drivers.csv` and `severity_driver_values.csv`, each covering all three severity levels
   with `severity` as a column** — one scannable table per grain rather than a three-file diff to
   compare a competitor against itself. The heatmaps stay one figure per level, and the JSON block
   keeps its `levels.{S3,S2,S1}` nesting. See the ADR amendment.
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

- [x] `{combo}_clashes.csv` and `{combo}_clash_explanations.csv` are written for all 51 `swedish_02`
      combinations by `analyze_persona_realism.py --rewrite-artifacts`, with **zero LLM calls**
      (asserted by the `plan_only is True` / `force is False` test triple).
- [x] Running `--rewrite-artifacts` twice produces **byte-identical** files for both new artifacts.
- [x] Judging combo A then B produces byte-identical artifacts to judging B then A (existing
      order-independence test extended to the two new files).
- [x] The reconciliation invariant holds for every combination: the count of distinct
      `(persona_id, attr_a, attr_b, severity)` tuples at level *L* in `{combo}_clashes.csv` equals
      the sum of `clash_count_s{L}` over that combination's `{combo}_personas.csv` rows. A violation
      raises, naming both files and `--rewrite-artifacts`.
- [x] A combination with no clashes at all produces a **header-only** `{combo}_clashes.csv`, not an
      absent file; the reader accepts it and raises only on a genuinely absent file.
- [x] `realism_ranking.json` contains a `severity_drivers` block whose per-cell denominators are
      identical to the corresponding `severity.levels.{L}.grid` cell denominators — guaranteed by
      construction (one `_affected_at` / one `len(record.personas)`) and asserted cell by cell.
- [x] The `S3` rows of `severity_drivers.csv` for `swedish_02_all_pick_v2_ollama_mistral_nemo_12b`
      rank
      `employment_status × employment_type` first, ~~and its nested value row names
      `Student × Permanent Full-time`~~ **and its nested value rows name
      `Unemployed × Permanent Full-time` (6) then `Student × Permanent Full-time` (5)**. The rank-1
      placement holds only via the declared tie-break — the pair is tied at 12 personas with
      `employment_status × income_source` — and the value-row order in the original criterion was
      wrong. See Manual Verification for the full corrected reading.
- [x] Every emitted driver row carries its denominator and the level's `penalised` flag — and, for
      the same reason, its counting unit and the non-additivity warning.
- [x] Excluded combinations (real reference where inapplicable, zero-successful-round personas,
      unresolvable attribute names) are counted and reported, never silently dropped. On the current
      `swedish_02` data: 0 unconsumable combinations, 0 personas with no successful round, 5
      unresolved clashes, 320 drivers below min-count and 45 below the top-n cut.
- [x] `ruff check src/` clean; `pytest` green (one **pre-existing**, unrelated failure:
      `test_axis_facet_defaults.py::test_flow_default_selects_exactly_the_highest_version_strategies`,
      caused by an uncommitted working-tree edit to `config/gui/flows/generate_parallel.yaml`).

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
| `scripts/analyze/rank_persona_realism.py` *(extended)* | Resolve config at the edge; flatten and write the driver CSVs (two after the 2026-08-07 revision, six as first shipped) | ranking dict → CSV files | How drivers are computed |

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
    severity_drivers.csv                NEW  — attribute-pair grain, all three levels
    severity_driver_values.csv          NEW  — category-pair grain, all three levels
```

*(Revised 2026-08-07, post-implementation: these first shipped as
`severity_drivers_s{1,2,3}.csv` / `severity_driver_values_s{1,2,3}.csv`, six files. The operator
asked for one file per grain with `severity` as a column; the six `_s*` files are obsolete and were
deleted from the output base. The heatmap PNGs are unaffected.)*

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

**Started:** 2026-08-07
**Completed:** 2026-08-07

- [x] 2.1 — Add a pure `clash_rows(persona_realism, attributes, slug_fields)` function to
      `reduce.py` returning `list[RealismClashRow]`: iterate rounds, dedupe within a round using the
      same `seen` convention as `reduce_persona`, sort the attribute pair, join each name against
      the persona's `attributes` map, set `unresolved` + empty values on a failed join.
- [x] 2.2 — Add the parallel explanations-row derivation, keyed identically.
- [x] 2.3 — Extract an `_emit_csv(path, build_rows, force, logger)` helper in `artifacts.py`,
      mirroring the existing `_emit_figure`, and route the personas CSV plus both new files through
      it — `write_combo_artifacts` otherwise gains a fourth and fifth near-identical block on an
      already-long function.
- [x] 2.4 — Wire both new writes into `write_combo_artifacts` under the same `force` gate as the
      other artifacts, so `--rewrite-artifacts` regenerates the **set**, never a mixed-generation
      tree.
- [x] 2.5 — Stamp `clash_csv_schema_version` into `_provenance_meta` (`artifacts.py:146`) beside the
      existing `persona_csv_schema_version`, as a separate key.
- [x] 2.6 — Run `analyze_persona_realism.py --rewrite-artifacts` over all 51 `swedish_02`
      combinations. Verify zero LLM calls and byte-identical output on a second run.

**Implementation notes (deviations worth a reviewer's attention):**

- **`clash_rows` takes the whole `LoadedPersona`**, not `(persona_realism, attributes, slug_fields)`
  as three arguments. The rounds and the attributes map must describe the *same* persona; passing
  them apart makes a silent mis-pairing — one persona's clashes joined against another's values —
  expressible, and the result would look entirely plausible. The slug fields stay as the same five
  keyword arguments `_persona_rows` already takes.
- **The within-round dedupe is now one function, not two implementations.** `_round_clashes(verdict)`
  returns the round's distinct `ClashKey`s mapped to the judge's (first) explanation for each, and is
  read by `reduce_persona`, `clash_rows` and `clash_explanation_rows` alike. The plan's stated risk
  ("the dedupe convention diverges from `reduce.py`") is therefore structurally impossible rather
  than test-guarded; the test asserting the two agree is retained as a regression check on the
  reconciliation arithmetic.
- **A new module, `persona_realism/clash_explanations_csv.py`,** holds the side file's row DTO and
  writer. It is deliberately *not* in `analysis/utils/`: that package is cross-process shared infra,
  and this file is read by no other process (nor by a human tool) — putting it beside the contract
  module would imply a promise to a reader it does not have. It carries no `SCHEMA_VERSION` for the
  same reason. `reduce.py` imports only its DTO, exactly as it imports only `RealismClashRow`.
- **`unresolved` covers three failure modes, not one.** The plan defines it as "the attribute name
  does not appear in the persona's `attributes` map"; the implementation also marks a key present but
  holding `None`, or holding a value that renders empty. All three mean "no category value to
  attribute this clash to", and the alternative for the second is writing the literal string
  `'None'` into `value_a` — a fabricated category. This keeps the contract's stated *iff* (values are
  empty exactly when the join failed) true rather than approximately true.
- **A partial join is unresolved as a whole.** The contract (Phase 1) rejects an `unresolved` row
  carrying values, so a clash where one name resolves and the other does not is written with both
  values empty. The row's claim is about a *pair*; half of one is not a weaker version of it.
  *The regeneration pass justified the broadened rule empirically:* all 5 unresolved rows in the
  51-combination corpus are `age_group × employment_status` on personas whose cached `age_group` is
  `null` (a mapped record with neither `age` nor `age_group`) — not a hallucinated name at all. Under
  the narrow key-presence rule those rows would have carried the literal string `"None"` as a
  category value, and Phase 3 would have ranked `None × Retired` as a driver.
- **`_emit_csv` took the combination summary CSV too**, not only the three files the task named. It
  is the same exists-else-write shape, so leaving it as the one un-extracted duplicate would have
  been the worse reading. All four writers share `(rows, path) -> Path`, so the helper never learns a
  column name; the skip log line now names the file (which begins with the combo label) rather than
  repeating the label separately.

**Files Modified:**
- `src/population_synthetic/analysis/persona_realism/reduce.py` — pure row derivation
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — `_emit_csv`, two new writes, provenance key
- `src/population_synthetic/analysis/persona_realism/clash_explanations_csv.py` — new, the side-file schema + writer

**Dependencies:** Phase 1

### Phase 3: Consumer — load, rank, emit
**Goal:** `severity_drivers` in the JSON and the flat driver CSVs beside the heatmaps.

**Started:** 2026-08-07
**Completed:** 2026-08-07

- [x] 3.1 — `loader.py`: add `clashes_csv_path` at `:160`, a missing-file skip branch mirroring the
      personas-CSV branch at `:164-167` (same remediation wording naming `--rewrite-artifacts`), the
      reader call at `:173` with the reconciliation counts derived from the already-loaded rows, and
      a `clashes: tuple[RealismClashRow, ...]` field on `CompetitorRecord`.
- [x] 3.2 — `builder.py`: add `_severity_drivers(records, *, top_n, min_count)` above
      `build_ranking`, modelled directly on `_severity_grids` — same adapter dicts with `"_record"`,
      same default-argument closure binding, same denominator, reusing the `directions` dict.
- [x] 3.3 — Suppress or flag ranks below `min_count` rather than publishing a rank-1 driver with
      n=2; count what was suppressed into the block.
- [x] 3.4 — Insert `"severity_drivers": _severity_drivers(...)` into the `build_ranking` return
      literal beside `"severity"` (`:728`), with the same two-line comment stating it is outside
      `axis_a` and changes no existing number. Append `_Skip` records rather than emitting `None`
      when it cannot compute.
- [x] 3.5 — Add two module-level flatteners returning `list[dict]`, keyed by slug like
      `summary_rows` / `scb_contrast_rows`, and add both to `__all__`.
- [x] 3.6 — `rank_persona_realism.py`: add `--driver-top-n` and `--driver-min-count`, resolved at the
      edge and passed as arguments (the builder docstring forbids it reading config); the
      `_write_csv` calls with their `None`-message branches (six as first shipped, two after the
      2026-08-07 revision below).
- [x] 3.7 — Report exclusions: combinations skipped, personas with zero successful rounds, and the
      `n_unresolved` total, all surfaced in the block and on stdout.

**Implementation notes (deviations worth a reviewer's attention):**

- **`_severity_drivers` takes two more arguments than the task states**: `skips` (positionally, as
  `_factor_significance(records, factor, skips)` already does) and `skipped_combinations`. Task 3.4
  requires it to append `_Skip` records and 3.7 requires it to report skipped combinations; neither
  is reachable from `(records, *, top_n, min_count)` alone, and the alternative — mutating the
  returned block from `build_ranking` — would put half the block's construction outside the function
  that owns it.
- **`build_ranking` gained `driver_top_n` / `driver_min_count` as *required* keyword arguments.** A
  default here would be a second source of truth for a number `rank_persona_realism.py` already
  declares, and the two could silently disagree; the module contract ("values arrive as arguments")
  is what makes required the right answer rather than merely a strict one. The call sites in the
  builder and e2e tests pass fixture-appropriate bounds through one helper each.
- **The block is built before the document literal, not inside it.** It appends to `skips`, which
  the same literal reads under `skipped_tests`, so building it inline would make the block's
  completeness depend on dict-literal key order — a trap for the next person to reorder the
  document.
- **Three things were lifted out of `_severity_grids` rather than copied**: the per-level
  `directions` dict (now the module-level `SEVERITY_DIRECTIONS`), the `_grid` adapter-entry builder
  (`_grid_entries`), and the "how many personas carry a clash at this level" count (`_affected_at`).
  The last one is load-bearing: the drivers exist to explain the heatmap cell's `affected`, and two
  implementations of that count could drift into explaining a different number than the one shown.
- **`min_count` applies at both grains**, attribute pair and category pair, with the suppressed
  counts reported separately at each. A rank-1 *value* on n=1 is as over-readable as a rank-1 pair
  on n=1, and a pair whose value list is empty because every category pair was a singleton is itself
  the finding (a broad problem with no single category driver) — which is why the count travels.
- **The cell payload carries five fields beyond the shape the plan sketches**: `model` / `strategy` /
  `is_real_reference` (so the flat tables are self-contained — the real competitor has no grid
  coordinate to re-derive them from) and `n_distinct_pairs` / `n_truncated` beside `n_suppressed`.
- **Ranks are positional, not shared on ties** (unlike `_axis_a_ranking`, where a tie shares a rank).
  The tie-break is total and declared, the equality stays visible in `n_personas`, and every grid
  note says to read the count rather than the rank.

**Post-implementation revision — 2026-08-07: the flat tables consolidate onto a `severity` column.**

*Reason: operator preference for a single scannable table per grain — the six-file layout mirrored
the heatmaps, but a heatmap can only show one grid while a table has columns, so comparing a
competitor's S3 drivers against its S2 drivers was a three-file diff over a sortable column.*

- The two flatteners lose their `level` parameter and iterate `SEVERITY_LEVELS` internally, emitting
  one combined list. `severity` becomes an identity column (renamed from `level`, and moved to sit
  after `slug`/`model`/`strategy`/`is_real_reference` and immediately before `penalised`), so a
  reader sees which level a row belongs to before any number on it.
- Row order is total and stated in the code: `slug` → severity by `SEVERITY_RANK` (the existing
  single ordering definition — S3, S2, S1, never alphabetical) → the existing within-cell `rank`,
  extended through `pair_rank` at the finer grain. No residual tie, asserted by test.
- **Ranks stay within `(competitor, severity)`** and are not renumbered across the merged file.
  Two rank-1 rows at different levels are not ambiguous once `severity` precedes `rank` on the row
  and the sort keeps a competitor's levels contiguous; renumbering across levels would have been a
  semantic change (ordering a hard contradiction against an unusual-but-possible pairing) and was
  rejected rather than made silently.
- Scope held to the flattening: the JSON block keeps `severity_drivers.levels.{S3,S2,S1}` nested,
  the heatmaps stay one PNG per level, and no producer artifact or computed number is touched — so
  no `--rewrite-artifacts` pass was needed.
- The six obsolete `severity_drivers_s*.csv` / `severity_driver_values_s*.csv` were deleted from the
  `swedish_02` output base; a stale file under the old name is worse than none.

**Post-implementation addition — 2026-08-07: three country-wide pair-summary figures.**

*Reason: the heatmaps answer "which cells have a high rate at this level" and the driver tables
answer "what drove one cell"; neither answers "at this level, what clashed, ranked", which is the
first question a reader asks and the one the manuscript needs a figure for.*

- `severity_pair_summary_s{3,2,1}.png/.svg` beside the heatmaps: horizontal bars, sorted descending,
  attribute-pair grain, pooled across the synthetic combinations, `--pair-summary-top-n` (default
  15) bars with the cut printed on the figure.
- **Computed from the full `CompetitorRecord.clashes` series, not from `severity_drivers.csv` or the
  `severity_drivers` JSON block** — those are already cut per cell by `--driver-top-n` and floored
  by `--driver-min-count`, so aggregating them into a country total over-weights pairs that merely
  clear many cells' cut and erases pairs that are broad but never locally top-ranked.
- **SCB is a separate red-diamond series over its own denominator, never pooled into the bars.** Its
  contribution must not be readable as the synthetic population's; the contrast (zero S3 clashes at
  all, S1 rates above the pooled synthetic rate on most pairs) is the most useful thing the numbers
  produced.
- Implemented as `builder.severity_pair_summary(records, level, *, top_n)` — a standalone pure
  function outside `build_ranking` — plus `charts.plot_severity_pair_summary`. Nothing is added to
  `realism_ranking.json`, so `axis_a` / `axis_b` / `severity` / `factor_significance` are provably
  unmoved. Named `pair_summary` rather than `driver_summary` because "driver" is pinned by this
  plan's Definitions to a within-cell ranking.
- See the second ADR amendment for the two decisions and their rejected alternatives.

**Files Modified (addition):**
- `src/population_synthetic/analysis/realism_ranking/builder.py` — `severity_pair_summary`
- `src/population_synthetic/analysis/realism_ranking/charts.py` — `plot_severity_pair_summary`
- `scripts/analyze/rank_persona_realism.py` — `--pair-summary-top-n`, the three chart writes
- `tests/test_realism_ranking_builder.py` — the pair-summary suite
- `tests/test_realism_ranking_e2e.py` — the CLI-level `--no-charts` / figures-written test

**Files Modified:**
- `src/population_synthetic/analysis/realism_ranking/loader.py` — third contract file, new record field
- `src/population_synthetic/analysis/realism_ranking/builder.py` — `_severity_drivers`, flatteners, `__all__`
- `scripts/analyze/rank_persona_realism.py` — two CLI flags, the driver CSV writes
- `tests/test_realism_ranking_loader.py` — `clashes_csv` switch + the new gate/reconciliation tests
- `tests/test_realism_ranking_builder.py` — the `_with_clashes` fixture mutator + the driver suite
- `tests/test_realism_ranking_e2e.py` — the driver-table end-to-end
- `tests/test_persona_realism_smoke.py` — optional S2/S1 clash markers on the stub judge

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
- [x] Pair canonicalisation: an issue emitted as `(b, a)` produces the same row as `(a, b)`.
      *(Phase 2 — `reduce.py` owns the canonicalisation; Phase 1 only enforces the sorted pair at
      the contract boundary, tested there.)*
- [x] Within-round dedupe matches `reduce_persona`'s `seen` convention. *(Phase 2.)*
- [x] Byte-determinism: write the same rows twice, compare bytes; and shuffle the input order,
      confirm identical output.
- [x] Reconciliation mismatch raises, naming both files and `--rewrite-artifacts` (unit level,
      against hand-built rows; the end-to-end producer↔consumer version stays under Integration).
- [x] `_severity_drivers` on a hand-computed fixture — extend the `_with_severities` mutator pattern
      (`test_realism_ranking_builder.py:464-471`) with clash rows. *(A sibling `_with_clashes`
      mutator: it attaches the clash rows **and derives** the per-persona `clash_count_s{L}` columns
      from them, mirroring the loader's reconciliation inside the fixture. Setting the two
      independently would let the denominator-agreement test pass only because both sides were
      hand-written to agree.)*
- [x] Tie-break determinism: two drivers with equal counts always rank in the same order — asserted
      both by name order and by re-building from the reversed row list.
- [x] `min_count` suppression is counted, not silently dropped; `top_n` truncation is counted
      **separately**, since those two exclusions mean different things.
- [x] Assert `severity_drivers` has not leaked into `axis_a`, contrasts, or factor tests, mirroring
      `test_realism_ranking_builder.py:553-556` — plus a stronger form: the same records built with
      loose and tight driver bounds produce identical `axis_a` / `axis_b` / `severity` /
      `factor_significance` blocks. *(The mixed logit is excluded from that comparison: its
      variational fit is not bit-reproducible between two calls, a property of the fitter that would
      mask rather than reveal a leak.)*
- [x] Degenerate bounds (`top_n < 1`, `min_count < 1`) raise rather than emitting an empty table.

### Integration Tests
- [x] **Reconciliation** — distinct `(persona, pair, severity)` count per level equals the summed
      `clash_count_s*` from the personas CSV. This is simultaneously the completeness invariant and
      the regression test; a deliberately corrupted pair must raise. *(Two corruptions are covered:
      dropping a clash breaks the count and raises the reconciliation error; swapping a pair into
      unsorted order raises the row-level invariant. A pair **renamed** without changing the count is
      by construction invisible to a count-based invariant — noted so a reader does not read the
      check as stronger than it is.)*
- [x] Loader gate: a combination directory missing `{combo}_clashes.csv` yields the skip reason under
      default and raises under `strict`, using the `_write_combo(..., clashes_csv=False)` switch
      added to `test_realism_ranking_loader.py:61-105`. *(Plus the producer↔consumer reconciliation
      at loader level — a header-only clashes CSV against personas declaring clashes raises naming
      `--rewrite-artifacts` — and a test that the loaded record carries its clash rows.)*
- [x] Denominator agreement: every `severity_drivers` cell denominator equals the corresponding
      `severity.levels.{L}.grid` cell denominator. *(Extended to `affected`, to the grids' axes, and
      to the real competitor's entry; and to the `None`-ness of each cell, so the two grids agree on
      which pairs were never judged.)*
- [x] `--rewrite-artifacts` CLI dispatch triple, extending
      `test_persona_realism_smoke.py:495-542`: `artifacts_force is True`, `force is False`,
      `plan_only is True`. *(Already asserted verbatim by
      `test_cli_combo_dispatch_skips_rewrite_when_nothing_changed`; no extension was needed, and it
      now covers the two new files because they sit under the same `force` gate.)*
- [x] e2e in `test_realism_ranking_e2e.py`: judge → rank on a `tmp_path` base produces all the driver
      CSVs — six as first written, **two after the 2026-08-07 revision**, each asserted to carry all
      three levels and to be byte-stable across two writes.
      *(The stub judge gained two optional markers, `S2_CLASH` / `S1_CLASH`, that a **possible**
      persona may carry — without them the fixture only ever produced S3 and two thirds of the
      tables would have shipped untested. The rows are serialised through `csv.DictWriter` rather
      than asserted in memory, because the flatteners' contract is that every value is a scalar a
      CSV cell can hold.)*
- [x] Order-independence: judging A-then-B vs B-then-A yields byte-identical new artifacts.

### Manual Verification
- [x] Run the full `--rewrite-artifacts` pass over the 51 `swedish_02` combinations; confirm the run
      reports zero LLM calls and zero cost. *(Run twice, 2026-08-07. Verified structurally rather
      than by reading a cost line: all **9102** verdict-cache + telemetry files (4551 personas × 2)
      were unchanged in size and mtime across both passes, and the runner logged "no LLM call made"
      for every combination. The config sits at `n_rounds: 3` while the cache holds 1, so this run
      is precisely the case the plan-only guard exists for — without it the pass would have topped
      up 4551 personas. The 51 combinations reconciled clean against the strict reader: 2235 clash
      rows, 5 unresolved, 2 header-only.)*
- [x] ~~Confirm `severity_drivers_s3.csv` ranks `employment_status × employment_type` first for
      `swedish_02_all_pick_v2_ollama_mistral_nemo_12b`, with `Student × Permanent Full-time` as its
      top value row~~ — **the emitted table was read, and the second half of this expectation is
      wrong.** Corrected statement of what the data says (`--driver-top-n 5 --driver-min-count 3`):
      the cell has exactly two S3 drivers, `employment_status × employment_type` and
      `employment_status × income_source`, **tied at 12 personas each** (prevalence 0.12 over a
      denominator of 100, matching the S3 heatmap cell and its `affected = 12` exactly — the same 12
      personas carry both). The declared tie-break puts `employment_type` at rank 1. Its value rows
      are `Unemployed × Permanent Full-time` (6) then `Student × Permanent Full-time` (5), so
      `Student × …` is the **second** value row, not the first. The rank-2 pair's values are
      `Unemployed × Wage / Business` (7) then `Student × Wage / Business` (5). The original
      expectation came from a hand-check of a single persona and was never a claim about the ranking.
- [x] Read the `S1` rows of `severity_drivers.csv` for a strong model and confirm the S1 drivers read as
      tail-reach, not defects. *(They do, and the sharper finding is what is **absent**:
      `swedish_02_all_pick_v2_claude_sonnet` has no S1 driver clearing min-count at all, and
      `..._claude_haiku` has one — `Upper Secondary ≤2 yrs × Middle Class`, 16% — while SCB itself
      carries five, led by `civil_status × household_size` at 27% (`Married × 1-person household`,
      `Owner-occupied villa × Poverty`). Every one of those is an unusual person, not an impossible
      one, and the strong models producing **fewer** of them than the real population is the
      mode-collapse concern Axis B exists for, seen from a second direction. 42 of the 52 competitors
      have at least one S1 driver; the largest is 80/100 personas.)*
- [x] ~~Confirm the SCB row (`real_swedish_02`) appears in all six tables as an ordinary competitor.~~
      **Corrected:** SCB is *enumerated* in all six tables as an ordinary competitor — nothing holds
      it out, and `_grid` places it by the same `is_real_reference` flag as everywhere else — but it
      appears in four of them, because it has no driver to show in the other two. It carries **zero**
      S3 clashes in the whole 100-persona sample and only 7 S2 clash rows, of which one pair
      (`employment_status × income_source`, 3 personas) clears min-count and none of whose category
      pairs do. So (counted in the consolidated tables): 5 SCB rows at S1 and 1 at S2 in
      `severity_drivers.csv`, 14 SCB rows at S1 and none at S2 in `severity_driver_values.csv`, and
      no SCB row at S3 in either. That
      absence is a **measurement**, not an exclusion, and is arguably the most interesting single
      number the tables produced: under this judge the chain-sampled reference population emitted no
      hard contradiction at all, and 198 of its 205 clash rows are S1.

### Edge Cases
- [x] A combination with zero clashes at every level (header-only file; the `drivers: []` cell is
      Phase 3).
- [x] A persona with zero successful rounds (contributes no rows; still counted in the denominator).
- [x] A cell where every persona shares one clash (prevalence 1.0), at both grains.
- [x] An unjudged `(model, method)` pair — `None`, never `0.0`, per `_grid`'s guarantee. Asserted
      against the neighbouring case it must stay distinct from: a judged cell with no clash has
      `drivers: []`, which claims "nothing drove this", while `None` claims nothing at all.
- [x] A cell whose personas declare clashes but whose per-clash rows hold none — records a `_Skip`
      naming `--rewrite-artifacts` rather than publishing an empty driver list as an answer.
- [x] A judge-hallucinated attribute name → `unresolved` row, counted, run does not fail.
- [x] `n_rounds > 1` (the current data is all `n_rounds: 1`; the round dimension must be exercised
      by a fabricated fixture).

---

## Documentation Plan

- [x] `docs/development/persona-realism-judge.md:99-104` — add both files to the per-combination
      artefact table; extend the `--rewrite-artifacts` section (`:106-127`) and the schema-version
      note (`:172-175`). *(Also: the ranking output table gains the driver tables, and a new
      "severity drivers" section states the three properties a reader needs before reading one.)*
- [x] `docs/architecture/commands.md:211-215` — the regeneration invocation and the two new ranking
      flags. *(Plus the note that a pre-existing output base is skipped until regenerated.)*
- [x] `config/analysis/analysis_registry.yaml:171-220` — both task descriptions enumerate their
      published outputs in prose; add the new files.
- [x] `CLAUDE.md` — the `persona_realism` / `realism_ranking` architecture paragraph gains the
      per-clash contract file.
- [x] New ADR — a second on-disk contract file on the same seam, plus the deliberate
      no-denominator-on-the-row divergence. The existing ADR records two decisions together because
      the second only became expressible once the first was made; this is the same shape.
      → `docs/development/decisions/2026-08-07-per-clash-contract-and-severity-drivers.md`
- [x] The counting-unit and non-additivity footnote must appear on every emitted table and in the
      JSON block, not only in the docs. *(As the `counting_unit` / `non_additive` columns on every
      row of every emitted table, and as fields on the block — repeated per row deliberately: a CSV has
      no footnote, and a column is the only place a caveat cannot be separated from its data.)*

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

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/analysis_registry.yaml
- docs/architecture/commands.md
- docs/development/decisions/2026-08-07-per-clash-contract-and-severity-drivers.md
- docs/development/persona-realism-judge.md
- docs/development/plans/active/severity-driver-attribution.md
- scripts/analyze/rank_persona_realism.py
- src/population_synthetic/analysis/persona_realism/artifacts.py
- src/population_synthetic/analysis/persona_realism/charts.py
- src/population_synthetic/analysis/persona_realism/clash_explanations_csv.py
- src/population_synthetic/analysis/persona_realism/reduce.py
- src/population_synthetic/analysis/realism_ranking/builder.py
- src/population_synthetic/analysis/realism_ranking/loader.py
- src/population_synthetic/analysis/utils/realism_clash_csv.py
- src/population_synthetic/analysis/utils/realism_csv.py
- src/population_synthetic/analysis/utils/tidy_csv.py
- src/population_synthetic/analysis/utils/validity_csv.py
- tests/test_persona_realism_smoke.py
- tests/test_realism_artifacts.py
- tests/test_realism_clash_csv.py
- tests/test_realism_ranking_builder.py
- tests/test_realism_ranking_e2e.py
- tests/test_realism_ranking_loader.py
- tests/test_realism_stats.py

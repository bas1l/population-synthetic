# Plan: GUI "N synthetic" cap for equivalent-size fidelity comparison

**Date:** 2026-07-09
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/openrouter-provider`
**Branch:** `feature/synthetic-population-size-cap`

---

## Context

Synthetic populations used to be a fixed 100 individuals, so cross-model fidelity
comparisons were implicitly size-matched. Generation now yields **variable** population
sizes (models emit different persona counts). Several fidelity metrics — especially the
multivariate ones (C2ST, joint chi-squared, per-pair joint TV) — are sample-size
sensitive, so comparing a 100-person model against a 250-person model is no longer
apples-to-apples.

The user wants a GUI-selectable **"N synthetic"** cap so the three analysis tasks —
**Compare Synthetic to Real** (fidelity), **Model Performance** (ranking), and
**Multivariate Joint Fidelity** — can be run with every synthetic population capped to
the same number of individuals, restoring equivalent population size for the calculation.

**Decisions confirmed with the user:**
- **Explicit N** typed in the GUI (blank = no cap = current behaviour). If a population
  has *fewer* than N individuals it is used in full and a loud warning is printed
  (fail-fast/loud, per project convention).
- **Seeded random** subsample — draw N without replacement via
  `np.random.default_rng(seed).choice(..., replace=False)`, the idiom already used in the
  C2ST test (`analysis/fidelity/multivariate.py`). Seed defaults to `0` for reproducibility.

---

## Problem Statement

The two fidelity scripts load each mapped synthetic population and feed its full
`individuals` list into the evaluator, whose metrics scale with `n`. With variable sizes
there is no way to hold `n` constant across models, so the fidelity report, the
multivariate report, and the derived model ranking all mix populations of different
sizes — biasing every cross-model comparison.

---

## Goals

### In Scope
1. A shared, seeded subsample helper that caps a mapped population to N individuals.
2. `--n-synthetic` (+ `--sample-seed`) CLI args on `score_fidelity_all.py` and
   `score_multivariate_fidelity.py`, applied at the single population-load point.
3. GUI exposure of the cap on the **Compare Synthetic to Real** and **Multivariate Joint
   Fidelity** tasks via the existing YAML-option → widget → CLI-arg pipeline.
4. Model Performance (ranking) inherits the cap automatically (it consumes the capped
   fidelity reports) — verified, documented, no code change.

### Out of Scope
- Capping at the MAP stage (`map_populations.py` / `load_synthetic_population`). Rejected:
  it would bake a single global N into the shared mapped artifacts and would surface the
  option on the Map task, not the analysis tasks the user named.
- Auto "cap to smallest" mode. The user chose explicit N.
- Any change to generation-side `n` (`config/synthetic/experiment_defaults.yaml`).
- Upsampling / bootstrapping populations smaller than N.

---

## Success Criteria

- [ ] `score_fidelity_all.py --n-synthetic 100` produces reports where every combo's
      `metadata.n` / report `n` is ≤ 100, and combos with fewer than 100 print a loud warning.
- [ ] `score_multivariate_fidelity.py --n-synthetic 100 --sample-seed 0` caps to the same
      subset of individuals as the fidelity run at the same seed (identical mapped-file
      order + seed → identical draw).
- [ ] Blank / omitted `--n-synthetic` reproduces current output byte-for-byte (no cap).
- [ ] The GUI Analysis Workflow shows an editable **N synthetic** field on the Compare and
      Multivariate task nodes; setting it appends `--n-synthetic <value>` to the built command.
- [ ] Model Performance ranking run after a capped Compare run reflects the capped `n`.
- [ ] `ruff check src/` clean; `pytest` green.

---

## Technical Design

### Approach

Insert the cap at the **one** place each analysis script turns a mapped file into an
in-memory population: immediately after `synthetic_pop = _load_json(synthetic_path)` in
both `main()` loops. A new shared helper in `analysis/utils/` does the seeded draw and
returns a new population dict with `individuals` capped and `metadata.n` corrected.
Because `StatisticalEvaluator` derives `n_b = len(pop_b["individuals"])`
(`evaluator.py:73-75`) and the multivariate builder reads the same `individuals` list, the
corrected count propagates through every metric and into the written report with no
consumer changes. Model ranking reads the report's recorded `n`
(`model_ranking/loader.py`: `n_synthetic = int(population_b["n"])`), so it inherits the cap.

### New shared helper

`src/population_synthetic/analysis/utils/sampling.py` (new module):

```python
def subsample_population(population: dict, n: int | None, seed: int = 0) -> dict:
    """Return a copy of *population* with its ``individuals`` capped to *n* by a seeded
    without-replacement draw. n=None -> unchanged. len(individuals) <= n -> unchanged
    (with a loud warning printed, since the requested equalised size cannot be met).
    Preserves original relative order of the drawn rows; updates metadata['n']."""
```

- Reuse the existing RNG idiom: `np.random.default_rng(seed).choice(len(individuals), size=n, replace=False)`, then `sorted(idx)` to keep deterministic ordering.
- Shallow-copy the dict, deep-enough copy `metadata` to set `n = len(subset)`; leave individual records untouched (referenced, not mutated).
- Fail-fast is honoured by printing a loud warning when `len < n` and returning the full
  population (comparison still runs, just below the requested equalised size).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Cap in each analysis script at load point (shared helper) | Option lands on the tasks the user named; per-task control; mapped artifacts stay full; two scripts share one helper | Cap logic invoked in two scripts (mitigated by shared helper) | **Chosen** |
| Cap at MAP `load_synthetic_population` | Single site, flows everywhere | Bakes one global N into shared mapped files; option would sit on the Map task; forces same N on all tasks; needs `--force` remap to change N | Rejected |
| Auto cap-to-smallest | Guaranteed exact equivalence, no user input | N varies per run/selection; user chose explicit N | Rejected |

### GUI wiring (existing contract, no framework change)

Per the Flow Runner contract, a YAML `options:` key **is** the CLI flag; the value's
Python type picks the widget, and `commands._option_args` turns it into argv
(`--key value`, or omitted when null/blank). So exposing the cap is pure config:

Add to `config/gui/v2/flows/analysis_workflow.yaml` under both `compare_synth_real.options`
and `joint_fidelity.options`:

```yaml
      n-synthetic:        # blank = no cap; integer = cap each population to this size
      sample-seed: 0      # seed for the without-replacement draw (reproducible)
```

- `n-synthetic:` is YAML null → renders as the nullable "(default)" line edit
  (`flow_options_panel.option_widget_kind`); blank writes null → omitted from argv → script
  default (no cap). A typed number is passed through `str(value)` → `--n-synthetic 100`,
  parsed by argparse `type=int`.
- `sample-seed: 0` renders as a numeric field defaulting to 0.
- No change to `flow_options_panel.py`, `commands.py`, or the workflow runner — the keys
  must exactly match the new argparse flags (the YAML key is the flag; nothing else validates it).
- **Model Performance** (`rank_models.py`) gets **no** new option: it recomputes nothing and
  reads the capped fidelity reports. It sits downstream of `compare_synth_real` in the DAG
  (`depends_on: [compare_synth_real]`), so a capped Compare run feeds it a capped ranking.

---

## Implementation Plan

### Phase 1: Shared subsample helper
**Goal:** One reusable, seeded, loud-on-undersize population capper.

- [x] Add `src/population_synthetic/analysis/utils/sampling.py` with
      `subsample_population(population, n, seed=0)` as specified above.
- [x] Unit-test it (see Testing Plan).

**Files:** `src/population_synthetic/analysis/utils/sampling.py` (new)

**Dependencies:** None

### Phase 2: CLI args on the two fidelity scripts
**Goal:** Cap applied at the single load point in each script.

- [x] `score_fidelity_all.py`: add `--n-synthetic` (`type=int, default=None`) and
      `--sample-seed` (`type=int, default=0`) to `_parse_args`; after
      `synthetic_pop = _load_json(synthetic_path)` (line ~270) call
      `subsample_population(synthetic_pop, args.n_synthetic, args.sample_seed)`; keep
      `n_synthetic = synthetic_pop["metadata"]["n"]` reading the post-cap value. Update the
      docstring usage block.
- [x] `score_multivariate_fidelity.py`: same two args; subsample after
      `synthetic_pop = _load_json(synthetic_path)` (line ~199); update docstring.

**Files:** `scripts/analyze/score_fidelity_all.py`,
`scripts/analyze/score_multivariate_fidelity.py`

**Dependencies:** Phase 1

### Phase 3: GUI config exposure
**Goal:** Editable N synthetic field on the Compare and Multivariate task nodes.

- [x] Add `n-synthetic:` (null) and `sample-seed: 0` under `compare_synth_real.options`
      and `joint_fidelity.options` in `config/gui/v2/flows/analysis_workflow.yaml`.
- [x] Manually confirm the nodes render the fields and the built command includes the flag.

**Files:** `config/gui/v2/flows/analysis_workflow.yaml`

**Dependencies:** Phase 2 (flag names must exist before the YAML references them)

### Phase 4: Docs
**Goal:** Record the new option and the equivalence semantics.

- [x] `docs/development/gui-v2.md` — note the `n-synthetic` / `sample-seed` options and that
      Model Performance inherits the cap via the fidelity reports.
- [x] Update the two scripts' `--` usage help (done in Phase 2 docstrings) and, if present,
      the command catalog (`docs/architecture/commands.md`) entries for the two scripts.
      (`score_fidelity_all.py` entry gained the flags; `score_multivariate_fidelity.py` is not
      listed in `commands.md`, so no entry was invented for it.)

**Files:** `docs/development/gui-v2.md`, `docs/architecture/commands.md`

**Dependencies:** Phases 2–3

---

## Testing Plan

### Unit Tests
- [x] `subsample_population`: n=None → identical object/contents; n < len → exactly n rows,
      original relative order preserved, `metadata.n == n`; n == len → unchanged; n > len →
      full population + warning; same seed → same subset, different seed → (generally) different.

### Integration / Manual Verification
- [ ] Build a small mapped fixture (or use an existing `03_Analysis/mapped/` output) and run
      `python scripts/analyze/score_fidelity_all.py --slug <slug> --n-synthetic 50 --no-charts`;
      confirm report `n == 50` and summary row `N == 50`.
- [ ] Run `score_multivariate_fidelity.py --slug <slug> --n-synthetic 50 --sample-seed 0`;
      confirm the multivariate report reflects n=50 and that the drawn subset matches the
      fidelity run at the same seed.
- [ ] Run without `--n-synthetic` and diff against a pre-change run → identical.
- [ ] Launch `python -m population_synthetic.gui_v2.main`, open Analysis Workflow, click the
      Compare and Multivariate nodes, set N synthetic = 50, and verify (via the runner's echoed
      command) that `--n-synthetic 50` is appended after the `--slug` args.
- [ ] Run the full Analysis Workflow (map → compare → multivariate → model performance) with the
      cap set and confirm the ranking table's `n` column shows the capped size.

### Edge Cases
- [ ] Population smaller than N → loud warning, runs in full, no crash.
- [ ] N = 0 or negative → argparse/`subsample_population` should reject loudly (add guard).
- [ ] `--n-synthetic` larger than every population → all warn, all run full (equivalent to no cap).

---

## Documentation Plan

- [x] Update `docs/development/gui-v2.md` with the new `n-synthetic` / `sample-seed` options
      and the Model-Performance-inherits-the-cap note.
- [x] Update `docs/architecture/commands.md` entries for the two fidelity scripts (if listed).
      (Only `score_fidelity_all.py` is listed and was updated; the multivariate script is absent.)
- [x] Docstring usage blocks in both scripts updated in Phase 2.

---

## Rollback Plan

1. Revert the three source/config edits and delete `analysis/utils/sampling.py`; the scripts
   fall back to full-population behaviour.
2. No data migration — mapped artifacts are untouched by this change; only re-run analysis to
   regenerate uncapped reports.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Fidelity and multivariate draw *different* subsets, breaking coherence between marginal and joint reports | Low | Med | Same deterministic mapped-file order + same default seed → identical draw; document that both tasks must use the same N and seed |
| YAML key typo ≠ argparse flag (silently dropped, nothing validates) | Med | Low | Keys added and tested together in Phase 2/3; manual command-echo check |
| Undersize population silently distorts "equivalent" comparison | Med | Med | Loud per-combo warning; N ≤ min guidance in docs |
| Regression when no cap set | Low | High | `n=None` early-return path + byte-diff verification against pre-change run |

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/gui/v2/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/development/gui-v2.md
- docs/development/plans/active/synthetic-population-size-cap.md
- scripts/analyze/score_fidelity_all.py
- scripts/analyze/score_multivariate_fidelity.py
- src/population_synthetic/analysis/utils/sampling.py

<!-- Note: tests/test_sampling.py (Phase 1 unit tests) exists on disk and passes,
     but /tests is gitignored repo-wide, so it is not committable. -->

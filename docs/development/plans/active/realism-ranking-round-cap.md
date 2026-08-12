# Plan: Realism-ranking round cap (`--rounds`)

**Date:** 2026-08-12
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/typicality-axis-metric`
**Branch:** `feature/realism-ranking-round-cap`

---

## Overview

Give `realism_ranking` a `--rounds N` option (surfaced as a GUI task option) that pins how many
judge rounds the ranking consumes per persona. When set, each competitor is re-reduced from its
`persona_realism` verdict caches over the **first N rounds** instead of being read from the
published per-combination artifacts. This unblocks ranking a sweep whose combinations are at
different round counts because a top-up is still in flight.

## Problem Statement

`realism_ranking` refuses a heterogeneous consumption set: `_assert_homogeneous`
(`loader.py:241`, called at `loader.py:364`) compares
`JUDGE_IDENTITY_KEYS = ("judge_model", "prompt_template_sha256", "n_rounds")` (`loader.py:69`)
across combinations and raises when they differ. That is correct — impossibility rate and
typicality dispersion are round-count dependent, so ranking a 5-round combination against a
2-round one measures the judge, not the combination.

But mid-sweep this is a hard stop. While `--rounds 5` is being topped up combination by
combination, the set is heterogeneous by construction, and the only escapes today are to wait for
the whole sweep or to narrow the ranking with `--slug` / `--model` / `--strategy` — i.e. to stop
ranking the thing you want ranked.

The round count is a **cross-unit** decision, and `realism_ranking` is the package that owns
cross-unit claims. It should be able to state "rank everyone at N rounds" and hold every
competitor to it.

## Goals

### In Scope

1. `--rounds N` on `scripts/analyze/rank_persona_realism.py`; when set, every consumed competitor
   is reduced over its first N successful rounds.
2. A cap-aware homogeneity gate: `judge_model` and `prompt_template_sha256` must still match
   exactly; `n_rounds` becomes a **capacity** requirement (every persona must hold ≥ N).
3. Truthful provenance: a capped ranking stamps the consumed N and records that it was capped.
4. `rounds:` exposed on the `realism_ranking` node's `options:` block in the GUI analysis flow.
5. **Auto-derivation when `--rounds` is blank:** a homogeneous set loads exactly as today; a set
   that differs *only* on `n_rounds` is re-loaded at the minimum cached depth instead of raising.

### Out of Scope

- Any change to `persona_realism`'s published artifacts, its CSV schemas, or its judging. No
  re-judge, no LLM call, no `SCHEMA_VERSION` bump.
- Capping at the *combination* level (different N per combination). One N for the whole run.
- Fixing the pre-existing `provenance.n_rounds`-is-the-target-not-the-cache divergence in
  `persona_realism` (`artifacts.py:150`). Noted as a risk, not repaired here.

## Success Criteria

- [ ] `python scripts/analyze/rank_persona_realism.py --rounds 2` completes on a set holding a
      2-round and a 5-round combination that previously raised the heterogeneity error.
- [ ] With no `--rounds`, byte-identical output to the current implementation on a homogeneous set
      (regression-checked by the existing e2e reproducibility test).
- [ ] With no `--rounds` on a set differing only on `n_rounds`, the run succeeds at the minimum
      cached depth, logs a warning naming the derived N and the combinations that were trimmed, and
      stamps `provenance.n_rounds_source == "auto"`.
- [ ] With no `--rounds` on a set differing on `judge_model` or `prompt_template_sha256`, the run
      still raises the existing heterogeneity error.
- [ ] A capped run whose set contains a combination with a persona holding < N successful rounds
      fails loudly, naming the combination and the shortfall — it does not rank it short.
- [ ] `ranking.json` `provenance.n_rounds` equals the consumed count (N when capped), and
      `provenance.n_rounds_source` distinguishes `"report"` from `"cap"`.
- [ ] Setting `rounds` in the GUI's `realism_ranking` task options emits `--rounds <value>` and a
      blank value emits nothing.
- [ ] `ruff check src/` clean; `pytest` green.

## Definitions

- **Consumed round count (N):** the number of leading successful rounds per persona used to
  compute every published statistic. Successful rounds only — failed rounds were never cached
  (`runner.py:392` appends only successes), so `rounds[:N]` is N successful rounds or a shortfall.
- **First N:** positions `0 .. N-1` of the cached `rounds` list, which is judgment order
  (append-only top-up, `runner.py:392`). Rounds are cold and independent, so the leading N is an
  unbiased subsample; no re-ordering or sampling is introduced.
- **Capacity check:** for every persona of every consumed competitor,
  `len(cache.rounds) >= N`. A single shortfall is a hard failure, not a skip.
- **Cap-active path:** the loading path taken when `rounds_cap is not None`. It reads
  `persona_XXXXX.json` caches and re-derives the record; it reads **neither** `{combo}_personas.csv`
  nor `{combo}_clashes.csv`.
- **Unchanged default:** with `rounds_cap is None` **and a homogeneous set**, not one line of the
  existing load path executes differently — same files read, same gate, same three-key identity
  tuple. The auto path is entered only after that gate has already failed, and only when it failed
  on `n_rounds` alone.
- **Auto-derived N:** `min` over the consumption set of each competitor's **actual cached** round
  count — itself the min over that competitor's personas of `len(cache.rounds)` — never the
  `provenance.n_rounds` target, which is known to diverge from the cache (`artifacts.py:150`).

---

## Technical Design

### Approach

Add `rounds_cap: int | None` to `load_competitors`. When `None`, everything behaves as today.
When set, `_load_one` takes a second implementation that rebuilds the `CompetitorRecord` from the
verdict caches using the **existing pure reducers** — no statistics are reimplemented:

```
load_combo_verdicts(combo_dir, expected_ids=...)      # reduce.py:460  -> {pid: LoadedPersona|None}
  -> capacity check: len(lp.rounds) >= N for every present persona
  -> lp_trimmed = dataclasses.replace(lp, rounds=lp.rounds[:N])
  -> reduce_persona(lp_trimmed.rounds, persona_id=pid) # reduce.py:209 -> PersonaVerdict
  -> reduce_combo(personas, combo_label)               # reduce.py:256 -> ComboRealism
  -> compute_realism_stats(combo, ...)                 # stats.py:154  -> impossibility/dispersion/reliability
  -> persona_rows(...) / combo_clash_rows(...)         # artifacts.py  -> the two tidy row sets
```

The report JSON is still read, but only for `provenance` (`judge_model`, `prompt_template_sha256`)
and `n_failed`; its `impossibility` / `dispersion` / `reliability` blocks are discarded and
replaced by the re-reduced ones. The record's `provenance["n_rounds"]` is restamped to N so the
builder's existing copy (`builder.py:1800`, `:1863`) publishes the truth with no builder logic
change.

Why re-reduce rather than filter the CSVs: per-round `can_exist` is not in the personas CSV (only
`can_exist_true_votes` / `can_exist_majority`, `realism_csv.py:138-139`), so impossibility at N is
not derivable from the contract. And filtering rows would break two hard reconciliations —
`read_realism_personas_csv(expected_rows=n_personas)` (`loader.py:211`) and the clash-count
reconciliation against `clash_count_s{L}` sums (`loader.py:216-220`). Bypassing both files on the
cap path avoids that entirely.

**Auto-derivation (blank `--rounds`).** Deriving N unconditionally would push every run — including
today's homogeneous ones — through the cache re-reduction, which is both slower and a silent change
of coupling. Instead the derivation is a **recovery step on the existing failure**:

1. Load as today (CSV path), run the three-key gate.
2. Passes → done. Nothing changed; this is the common case.
3. Fails on `judge_model` or `prompt_template_sha256` → raise as today. A different judge or prompt
   is not something a round cap can repair.
4. Fails on `n_rounds` **alone** → probe each competitor's actual cached depth, set
   `N = min(...)`, reload every competitor through the cap path, and log a warning naming N and
   which combinations were trimmed. Provenance records `n_rounds_source = "auto"`.

So the flag has three states: absent + homogeneous = today's behaviour; absent + round-heterogeneous
= ranked at the shallowest common depth, loudly; explicit `--rounds N` = pinned, with the capacity
check refusing anything shallower than N.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Cache-sourced cap in `realism_ranking` (this plan) | No schema change, no re-publish, works mid-top-up, reuses existing reducers | `realism_ranking` gains a read dependency on `persona_realism`'s cache layout | **Chosen** |
| Extend the personas CSV with per-round `can_exist_rounds`, cap from the CSVs | Keeps the tidy-CSV contract as the only coupling | `SCHEMA_VERSION` 2→3, re-publish every combination's artifacts, reducer API refactor — not hotfix scope | Rejected |
| Cap in `persona_realism` (`--reduce-rounds`) and re-publish artifacts | Keeps the ranking a pure consumer | Publishes truncated artifacts that must later be re-published uncapped; two report generations; the decision is cross-unit so it sits in the wrong package | Rejected |
| Just relax the gate | One line | Ranks 5-round against 2-round competitors — measures the judge | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `realism_ranking/loader.py` (cap path) | Rebuild one `CompetitorRecord` at N rounds from caches | `combo_dir, N, judge_cfg` → `CompetitorRecord` | How any statistic is computed (delegates to `reduce`/`stats`); chart rendering; ranking logic |
| `realism_ranking/loader.py::_assert_homogeneous` | Enforce one judge + one prompt; and one round count **only when uncapped** | `records, cap_active` → `None` \| raise | Why the cap was chosen; the CLI |
| `persona_realism/reduce.py`, `stats.py` | Unchanged pure reduction/statistics | as today | That a cap exists — it only ever sees the rounds it is handed |
| `persona_realism/artifacts.py` | Unchanged, except two row-builders become public | as today | The ranking layer |
| `scripts/analyze/rank_persona_realism.py` | Parse/validate `--rounds`, pass it down | CLI → `load_competitors(rounds_cap=...)` | Reduction internals |
| `config/gui/flows/analysis_workflow.yaml` | Declare the `rounds` option so the GUI can edit it | YAML → `--rounds <v>` via `gui/commands.py:41` | Everything else |

`reduce.py` and `stats.py` are **not modified**. The cap is expressed solely as which rounds get
handed to `reduce_persona`.

Signature changes:

```python
# realism_ranking/loader.py
def load_competitors(
    output_base, *, countries=None, models=None, strategies=None, slugs=None,
    strict=False, axis_ids=None,
    rounds_cap: int | None = None,      # NEW — None keeps today's path verbatim
    judge_cfg=None,                     # NEW — required when rounds_cap is set (bootstrap params)
) -> tuple[list[CompetitorRecord], list[tuple[str, str]]]: ...

# persona_realism/artifacts.py  (rename only, internal call sites updated)
_persona_rows      -> persona_rows
_combo_clash_rows  -> combo_clash_rows
```

---

## Implementation Plan

### Phase 1: Cap-aware loading

**Goal:** `load_competitors(..., rounds_cap=N)` returns records reduced over the first N rounds;
`rounds_cap=None` is bit-for-bit today's behaviour.

- [x] 1.1 — Promote `_persona_rows` → `persona_rows` and `_combo_clash_rows` → `combo_clash_rows`
      in `persona_realism/artifacts.py`; update the internal call sites. No behaviour change.
- [x] 1.2 — Add `_load_one_capped(...)` to `loader.py`: `load_combo_verdicts` → capacity check →
      `dataclasses.replace(lp, rounds=lp.rounds[:N])` → `reduce_persona` → `reduce_combo` →
      `compute_realism_stats` → `persona_rows` / `combo_clash_rows` → `CompetitorRecord`. Mirror
      the exact `compute_realism_stats` keyword arguments used at the `artifacts.py` call site so
      capped and uncapped statistics are computed identically.
- [x] 1.3 — Restamp the rebuilt record's provenance: `n_rounds = N`, `n_rounds_source = "cap"`;
      the uncapped path stamps `n_rounds_source = "report"`.
- [x] 1.4 — Capacity failure message: name the combination, the persona id, the cached count and N,
      and state that `--rounds` must not exceed the shortest cached persona.
- [x] 1.5 — Gate: `_assert_homogeneous(records, *, cap_active: bool)` compares
      `("judge_model", "prompt_template_sha256")` when `cap_active`, all three keys otherwise.
      Keep the existing message for the uncapped case.
- [x] 1.6 — `rounds_cap` set with `judge_cfg=None` raises immediately (fail-fast, not a default).
- [x] 1.7 — Auto-derivation: when `rounds_cap is None` and the three-key gate fails on `n_rounds`
      **alone**, probe each competitor's minimum cached depth, take the set-wide minimum, reload
      through the cap path, and `logger.warning` the derived N plus the trimmed combinations.
      A failure on `judge_model` / `prompt_template_sha256` still raises unchanged. Provenance
      stamps `n_rounds_source = "auto"`. The probe reads cached round counts only — never
      `provenance.n_rounds`.

**Files Modified:**
- `src/population_synthetic/analysis/realism_ranking/loader.py` — cap path, gate, provenance stamp
- `src/population_synthetic/analysis/persona_realism/artifacts.py` — two renames + call sites

**Dependencies:** None

### Phase 2: CLI + provenance

**Goal:** the flag exists, validates, and the published ranking states the consumed round count.

- [x] 2.1 — `--rounds` in `_parse_args` (`rank_persona_realism.py:185-273`), `type=int,
      default=None`, mirroring `analyze_persona_realism.py:166`; reject `< 1` with the same wording.
- [x] 2.2 — Thread it into the `load_competitors` call (`rank_persona_realism.py:421-429`) together
      with the already-loaded `cfg` (`:399`).
- [x] 2.3 — Document the flag in the module docstring flag list (`:102-124`).
- [x] 2.4 — Add `"n_rounds_source": provenance.get("n_rounds_source")` to the builder's provenance
      block (`builder.py:1856-1865`). `n_rounds` itself needs no change — it already reads from
      `records[0].provenance`, which Phase 1 restamped.

**Files Modified:**
- `scripts/analyze/rank_persona_realism.py` — flag, validation, threading, docstring
- `src/population_synthetic/analysis/realism_ranking/builder.py` — one provenance key

**Dependencies:** Phase 1

### Phase 3: GUI option, tests, docs

**Goal:** N is settable from the GUI task options and the behaviour is covered.

- [ ] 3.1 — Add `rounds:` (blank, with a comment) to the `realism_ranking` node's `options:` block
      in `config/gui/flows/analysis_workflow.yaml:169-173`. Purely a YAML change —
      `gui/commands.py:41` translates keys generically and blank values are omitted.
- [ ] 3.2 — Loader tests (below).
- [ ] 3.3 — One e2e CLI test through `_run_ranking_script` (`test_realism_ranking_e2e.py:338`).
- [ ] 3.4 — Docs: the `--rounds` row in the command catalog, a paragraph in the persona-realism
      operator guide, and the CLAUDE.md `realism_ranking` sentence (the gate is now two keys plus a
      capacity check when capped).

**Files Modified:**
- `config/gui/flows/analysis_workflow.yaml`
- `tests/test_realism_ranking_loader.py`, `tests/test_realism_ranking_e2e.py`
- `docs/architecture/commands.md`, `docs/development/persona-realism-judge.md`, `CLAUDE.md`

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [ ] `rounds_cap=None` yields records identical to the current loader (guards the default path).
- [ ] A set with `n_rounds` 5 and 2 in provenance loads under `rounds_cap=2` and raises without it.
- [ ] Differing `judge_model` (or `prompt_template_sha256`) still raises **with** a cap active.
- [ ] Capacity: a persona cache holding 2 rounds under `rounds_cap=3` raises naming combination,
      persona and counts.
- [ ] A capped record's `provenance["n_rounds"] == N` and `n_rounds_source == "cap"`.
- [ ] `rounds_cap=5` on a 5-round cache reproduces the uncapped record's `impossibility` /
      `dispersion` / persona rows — the cap is a no-op at full depth. (Strongest correctness check:
      it proves the re-reduction path agrees with the published artifacts.)
- [ ] Capped clash rows contain no `round_index >= N`.
- [ ] Auto: a set with cached depths 5 and 2 and no `rounds_cap` loads at N=2, stamps
      `n_rounds_source == "auto"`, and emits the warning.
- [ ] Auto: a homogeneous set with no `rounds_cap` never enters the cap path (assert the CSV
      readers are still the source — e.g. by spying, or by asserting `n_rounds_source == "report"`).
- [ ] Auto does not mask a differing `judge_model`: that set still raises.

### Integration Tests
- [ ] e2e: judge two combinations at different round counts, rank with `--rounds <min>`, assert the
      declared outputs exist and `provenance.n_rounds` is the cap.
- [ ] e2e: `--rounds 0` / `--rounds -1` exit non-zero with the validation message.
- [ ] `tests/test_workflow_commands.py`: `rounds: '2'` → `--rounds 2`; blank → flag absent.

### Manual Verification
- [ ] Run the real failing case: rank `swedish_02` with `all_generate_evaluate_pick_v2` (2 rounds)
      and `all_generate_evaluate_random_pick_v2` (5 rounds) at `--rounds 2`; confirm both appear in
      the ranking and the report states the cap.
- [ ] GUI: set `rounds` on the `realism_ranking` node, confirm the emitted command in the run log.

### Edge Cases
- [ ] `rounds_cap` greater than every cached count → capacity error, no partial output.
- [ ] The `real_{country}` competitor is subject to the same capacity check (it is an ordinary
      competitor).
- [ ] A combination whose personas have *unequal* cached counts, all ≥ N → passes, all trimmed to N.

---

## Documentation Plan

- [ ] `docs/architecture/commands.md` — `--rounds` in the `rank_persona_realism.py` flag list
- [ ] `docs/development/persona-realism-judge.md` — when to cap, and that it never re-judges
- [ ] `CLAUDE.md` — the `realism_ranking` gate sentence (one judge model / prompt hash, plus either
      one `n_rounds` or an explicit cap with a capacity check)
- [ ] Inline docstrings on `load_competitors` and the cap path stating that the cap reads caches,
      not the CSV contracts, and why

---

## Rollback Plan

1. The feature is inert unless `--rounds` is passed; reverting is dropping the branch.
2. No data migration, no schema change, nothing written to `persona_realism/` — capped runs only
   write into `03_Analysis/realism_ranking/`.
3. If a capped ranking was published and is unwanted, re-run without `--rounds` (with `--force`) to
   overwrite it once the sweep is homogeneous.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Re-reduction diverges from the published artifacts (different stats args) | Med | High | The `rounds_cap == cached count` no-op test asserts parity against the uncapped record; mirror the `artifacts.py` call site exactly |
| A capped ranking is later mistaken for a full one | Med | Med | `provenance.n_rounds` restamped + `n_rounds_source: "cap"`; capped run is visible in the report |
| `realism_ranking` now depends on the cache layout | High | Low | Cache reads go only through `reduce.load_combo_verdicts`, never raw globs/JSON parsing in the ranking package |
| Pre-existing divergence: `provenance.n_rounds` is the *target*, cache may hold more (`artifacts.py:150`) | Med | Med | The cap path reads actual cached counts, so it is immune; documented as a separate defect, out of scope here |
| GUI value typed as a string (`'2'`) | High | Low | `gui/commands.py:41` stringifies anyway; argparse `type=int` parses it |
| Auto-derived N drifts run to run as the sweep tops up, so two rankings are silently at different depths | High | Med | N is stamped in provenance and warned in the log; pin with `--rounds N` for anything published |
| Auto masks a genuinely broken combination (one persona stuck at 1 round drags the whole set to N=1) | Med | High | The warning names every trimmed combination and the derived N; the pinned form then refuses that set outright via the capacity check |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | ~120 lines, 2 files | None |
| Phase 2 | ~25 lines, 2 files | Phase 1 |
| Phase 3 | ~1 YAML line + tests + docs | Phase 2 |

---

## References

- Failing gate: `src/population_synthetic/analysis/realism_ranking/loader.py:241,364`
- Reducers reused: `analysis/persona_realism/reduce.py:209,256,460`; `stats.py:154`
- GUI option translation: `src/population_synthetic/gui/commands.py:41`
- Related plans: `docs/development/plans/pending/typicality-axis-metric.md`

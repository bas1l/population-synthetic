# Plan: Strategy v2 — SCB Chain Alignment and Strategy Versioning

**Date:** 2026-07-28
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/strategy-v2-scb-chain-alignment`

---

## Overview

Introduce a **version** dimension to the synthetic generation strategy axis and ship v2 of all five
strategy families. Each v2 strategy generates 14 categories instead of 17 (dropping `birth_location`,
`ethnicity_broad_global_approx`, `current_environment_type`) and wires `birth_country_detail` to
depend on `age` and `biological_sex`, mirroring the real SCB conditional chain. A companion fix makes
category resolution order deterministic, without which the rewire has no guaranteed effect.

## Problem Statement

Three distinct defects, all currently latent:

1. **The synthetic birth chain does not mirror the real one.** The SCB sampler conditions birthplace
   on `(age_group, sex_label)` at both steps — `birth_location` (`sample_service.py:133-145`) and
   `birth_country_detail` (`sample_service.py:255-275`, gated by `birth_location` with a
   Sweden-excluded re-draw). Every synthetic strategy declares `birth_location: depends_on: []` and
   `birth_country_detail: depends_on: [birth_location]`. Age and sex never appear.
   This is the "underlying independence bug" that `deprecate-birth-location-analysis-axis.md`
   deferred as Out-of-Scope item 6 ("a separate, larger effort; deprecation sidesteps it"). This plan
   is the successor to that deferred work.

2. **Category resolution order is non-deterministic across processes.**
   `identity_generator_configurable.py:91` builds `declared = set(category_config.keys())`, and `:109`
   seeds Kahn's queue by iterating that set:
   ```python
   queue = deque(cat for cat in declared if in_degree[cat] == 0)
   ```
   CPython randomizes string hashing per process, so the order of the in-degree-0 roots (`age`,
   `biological_sex`, `region`, `birth_location`, `parental_structure`) varies between invocations.
   Because `depends_on` controls scheduling only — the prompt context block serialises **all**
   resolved attributes (`identity_generator_configurable.py:278-281`) — this means `birth_location`
   currently sees age and sex in its prompt on *some* runs and not others, with no record of which.
   `_build_dag` is presented as a pure function and is not.

3. **Three generated categories are dead weight.** `ethnicity_broad_global_approx` and
   `current_environment_type` are synthetic-only inventions absent from every mapping index, fidelity
   config, and realism config; they were added in 2026-05 for a comparison extractor that no longer
   reads them. `birth_location` is in `deprecated_attributes` for Sweden and therefore unscored. Each
   costs one LLM call per persona and produces nothing the analysis consumes.

## Goals

### In Scope

1. A **versioning scheme** for the strategy axis: `family` and `version` keys in each strategy YAML,
   plus a `_families.yaml` ordering index, so v1 and v2 coexist as distinct experimental arms.
2. **Five new v2 strategy YAMLs** (one per family), each with the 14-category set and the rewired
   birth chain.
3. Replace the hardcoded `STRATEGY_COMPLEXITY_ORDER` list with a config-derived, total,
   simplest-first ordering that preserves the locked manuscript tie-break rule.
4. **Determinism fix** in `_build_dag`: topological order derives from YAML declaration order.
5. `expected_raw_keys()` subtracts `deprecated_attributes` per country, so Sweden stops requiring
   `birth_location` while Italy continues to require it.
6. A **fail-fast compatibility guard** rejecting a (strategy, country) pair where the strategy omits
   an attribute the country still requires.

### Out of Scope

- **Regenerating v1 populations.** v1 outputs stay as an archived baseline (see Risks).
- **Changing the real SCB sampler.** `sample_service.py` is untouched; `birth_location` remains in
  its output dict, as `deprecate-birth-location-analysis-axis.md` explicitly required.
- **Any mapping config change.** `_index.json`, per-attribute JSONs, and `refine_from` wiring are
  untouched; the 14 scored axes are unchanged.
- **Any fidelity config change.** `joint_pairs`, `grounded_joint_pairs`, and coherence lists stay as
  they are.
- **Filtering prompt context to `depends_on`.** Explicitly rejected in `fix-all-pick-context-leak.md`;
  `context: cumulative` semantics are unchanged.
- **Running v2 on Italy.** v2 is Sweden-only this pass (see Definitions).
- **A general version-migration framework.** Only the two keys actually needed now (YAGNI).
- **Superseding `_compared_only_generate_evaluate_random_pick.yaml`.** Left frozen as a historical
  definition; not deleted, not updated.

## Success Criteria

- [x] Five files `config/synthetic/axes/strategies/all_*_v2.yaml` exist, each with 14 categories,
      `family`, `version: 2`, and stem == `id`.
- [x] `python -c "from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values; print([d['id'] for d in discover_axis_values('strategies')])"` lists all five v2 ids.
- [x] All five v2 ids appear as tickable entries in the GUI's strategy axis with no code change.
      (Verified programmatically: the widget tests in `tests/test_axis_version_filter.py` construct a
      real `CheckableAxisList` populated from `discover_axis_values('strategies')`. Visual check in a
      running GUI still outstanding.)
- [x] `_build_dag` returns a byte-identical order across 20 separate interpreter processes
      (`PYTHONHASHSEED` unset) for every strategy file. (20 runs → 1 distinct md5; the same probe
      against the pre-fix implementation produced 20 distinct outputs.)
- [x] `expected_raw_keys("swedish")` returns 14 keys without `birth_location`;
      `expected_raw_keys("italian")` still returns 14 keys **with** `birth_location`.
- [ ] A full end-to-end run of one v2 combo (`--n 5`) passes `validate_raw` at 100%, passes
      `validate_mapped`, and yields 5 personas through `population_cap`. **NOT YET RUN** — requires a
      live LLM run; this is the main outstanding acceptance gate.
- [ ] Fidelity scoring of that combo emits all **14** scored axes, unchanged from v1. **NOT YET RUN**
      — blocked on the end-to-end run above.
- [x] `--country-id italian --strategy-id all_pick_dag_v2` raises before any LLM call.
- [ ] The manuscript global-best-strategy tie-break resolves identically to today when only v1
      strategies are present (regression: no published result moves). **PARTIAL** — the ordering
      regression is asserted by
      `tests/test_strategy_ordering.py::test_v1_only_order_equals_the_legacy_sequence`, but the
      manuscript table itself has not been regenerated and diffed.
- [x] `ruff check src/` clean; `pytest` green. (1053 passed on the combined tree.)

## Definitions

- **family**: which of the five generation methods a strategy implements — one of `all_pick`,
  `all_pick_dag`, `all_generate_pick`, `all_generate_evaluate_pick`,
  `all_generate_evaluate_random_pick`. Two strategies share a family iff they differ only by version.
- **version**: an integer revision of a family's category set and dependency wiring. v1 and v2 are
  **separate experimental arms**, never replicates, never pooled, never plotted in one series.
- **v2 category set (14)**: exactly `age`, `biological_sex`, `region`, `birth_country_detail`,
  `civil_status`, `household_size`, `education_level`, `employment_status`, `employment_type`,
  `industry_sector`, `socioeconomic_class`, `income_source`, `housing_tenure`, `parental_structure`.
- **Sweden-only**: a v2 strategy is valid for a country iff its category set is a superset of that
  country's required raw keys. For `swedish`/`swedish_02` that is 14 keys (15 attributes minus
  deprecated `birth_location`, with the `age_group`→`age` alias). For `italian` it is 14 keys
  **including** `birth_location`, which v2 does not generate — hence invalid.
- **Scored axis set is invariant**: the 14 attributes in `ComparisonScheme.attributes` for Sweden are
  byte-identical before and after this change. This is what makes v1↔v2 fidelity comparison valid.
- **Total simplest-first order**: a strict ordering over all present strategy ids in which, for any
  two, exactly one precedes; families ordered by declared complexity, versions ascending within a
  family. Required by the locked manuscript tie-break.

---

## Technical Design

### Approach

Additive config, minimal code. The five v2 strategies are new files — nothing existing is mutated
except metadata backfill (`family`/`version: 1`), which does not change generation behaviour. Version
lives in the strategy **id** (`all_pick_dag_v2`) because the output slug is
`{country}_{strategy}_{model}`: a new id yields new output directories, so v1 results stay intact and
re-derivable, and `decompose_slug` handles the suffix correctly (verified — it peels the longest model
suffix, then requires an exact strategy-set membership test on the middle, so `all_pick` and
`all_pick_v2` cannot be confused).

The determinism fix is a two-line change with outsized importance: without it, "birth country depends
on age and sex" is a statement the config makes and the runtime does not honour.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Version in strategy id (`all_pick_dag_v2`) | New slug ⇒ v1 outputs preserved; discovery, slug parsing, GUI all work unchanged | Five more files in the strategies dir | **Chosen** |
| Version subdirectory (`strategies/v2/*.yaml`) | Visually tidy | `discover_axis_values` globs non-recursively; `id` collision between v1/v2; needs code change | Rejected |
| In-place `version:` bump, id unchanged | No new files | Overwrites v1 arm; v1 no longer runnable; destroys the baseline | Rejected |
| Edit the five v1 strategies directly | Fewest files | Rejected twice before — `add-all-pick-dag-strategy.md` (destroys context-free baseline) and `fix-all-pick-context-leak.md` (touch exactly one strategy) | Rejected |
| Keep `birth_location` generated in v2 | No validator change; v2 stays country-agnostic; preserves the domestic/abroad gate | Costs one LLM call per persona for an unscored field | Rejected (user decision) |
| Drop `birth_location` from `_index.json` entirely | Removes it everywhere | Explicitly rejected in `deprecate-birth-location-analysis-axis.md`: drops it from the mapper, breaks `refine_from`, forces regen, irreversible | Rejected |
| Append v2 ids to `STRATEGY_COMPLEXITY_ORDER` | One-line change | Leaves a hardcoded per-axis list in Python; grows with every version | Rejected |
| Filter prompt context to `depends_on` | Would make the rewire a genuine conditioning change | Explicitly rejected in `fix-all-pick-context-leak.md` — alters every `all_pick_dag` and `generate_*` arm | Rejected |

**Addressing a prior rejection directly.** `align-strategies-scb-comparable-categories.md` rejected
creating parallel `scb_only_*` strategy variants on the grounds of "file proliferation, same
categories duplicated". That rejection was premised on variants with an *identical* category set,
where the duplication bought nothing. v2's category set genuinely differs from v1's (14 vs 17), and
prior results must remain reproducible, so the calculus differs. This plan is not a re-proposal of
`scb_only_*`.

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/synthetic/axes/strategies/all_*_v2.yaml` | Declare one generation arm: which categories, by what method, in what dependency order | — → `{id, family, version, label, description, context?, categories}` | Countries, models, mapping configs, analysis |
| `config/synthetic/axes/strategies/_families.yaml` | Declare the total simplest-first family order | — → ordered family id list | Versions, individual strategy ids, models, countries |
| `analysis/utils/axes.py::strategy_complexity_order(strategy_ids)` | Order a set of present strategy ids by (family_rank, version) | `list[str]` → ordered `list[str]`; raises on unknown family | Charts, statistics, file paths, output dirs |
| `analysis/validate_raw/validate.py::expected_raw_keys(country)` | Resolve the raw keys a country genuinely requires | `country_id` → `list[str]` (attributes − deprecated, alias applied) | Strategies, versions, which categories a run generated |
| `generators/synthetic/identity_generator_configurable.py::_build_dag` | Deterministic topological order of categories | `category_config` (ordered mapping) → `list[str]`; raises on cycle/undeclared | Hash order, process identity, wall-clock |
| `scripts/generate/generate_identities_parallel.py::_assert_strategy_covers_country` (guard) | Reject an incompatible (strategy, country) pair before generation | `(strategy_path, strategy_id, country_id)` → None or raise | LLM providers, workers, Ollama hosts |

Ordering is resolved **once** in the `analysis/utils` layer and passed down. No chart or statistics
module reads a strategy YAML, and there is no import-time module-level config load (the current
`STRATEGY_COMPLEXITY_ORDER` constant is replaced by a function, not by another constant).

**Correction (Phase 4, recorded here in Phase 5).** The guard row originally nominated
`generators/synthetic/manifest_loader.py` (`compose_manifest`). It could not live there: the
country's requirement comes from the mapping `_index.json` via
`analysis/validate_raw/validate.py::expected_raw_keys`, and `analysis/utils/country_config.py`
already imports `manifest_loader.discover_axis_values` — so importing `expected_raw_keys` into
`manifest_loader` would invert the layer dependency **and close an import cycle**, avoidable only by
a lazy in-function import that papers over the inversion. Reading `_index.json` directly inside
`manifest_loader` was rejected as a third copy of the deprecation-subtraction logic. The guard
therefore lives at the orchestration edge, `scripts/generate/generate_identities_parallel.py`, which
legitimately sees both layers and through which the CLI *and* the GUI both run. Consequence: it
covers the axis-composition path only — `--manifest` and explicit `--config`/`--strategy` carry no
country id and are unchecked.

```
config/synthetic/axes/strategies/
├── _families.yaml                              # NEW — total family order
├── all_pick.yaml                               # +family, +version: 1
├── all_pick_v2.yaml                            # NEW
├── all_pick_dag.yaml                           # +family, +version: 1
├── all_pick_dag_v2.yaml                        # NEW
├── all_generate_pick.yaml                      # +family, +version: 1
├── all_generate_pick_v2.yaml                   # NEW
├── all_generate_evaluate_pick.yaml             # +family, +version: 1
├── all_generate_evaluate_pick_v2.yaml          # NEW
├── all_generate_evaluate_random_pick.yaml      # +family, +version: 1
├── all_generate_evaluate_random_pick_v2.yaml   # NEW
├── _compared_only_generate_evaluate_random_pick.yaml  # frozen, untouched
└── _debug_minimal.yaml                         # untouched
```

The v2 birth chain, in the four DAG families:

```yaml
age:                  { method: <m>, depends_on: [] }
biological_sex:       { method: <m>, depends_on: [] }
birth_country_detail: { method: <m>, depends_on: [age, biological_sex] }
```

`all_pick_v2` keeps `context: none` and all-empty `depends_on` — the rewire is a structural no-op
there by design, since it is the context-free baseline. It differs from `all_pick` only by the three
dropped categories.

---

## Implementation Plan

### Phase 1: Determinism
**Goal:** `_build_dag` becomes a pure function of its input.

**Started:** 2026-07-28
**Completed:** 2026-07-28

- [x] 1.1 — Replace `declared = set(...)` at `:91` with an order-preserving structure; seed the Kahn
      queue at `:109` from `category_config` declaration order.
- [x] 1.2 — Ensure `dependents`/`in_degree` iteration is insertion-ordered so downstream release
      order is stable too.
- [x] 1.3 — Update the `_build_dag` docstring to state the tie-break rule explicitly: ties among
      in-degree-0 categories resolve in YAML declaration order.
- [x] 1.4 — Record the resolved category order into `run_metadata.json` for provenance.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — `_build_dag`
- `scripts/generate/generate_identities_parallel.py` — add resolved order to `run_metadata.json`

**Dependencies:** None

### Phase 2: Validation gate
**Goal:** A country stops requiring attributes it has deprecated.

**Started:** 2026-07-28
**Completed:** 2026-07-28

- [x] 2.1 — `expected_raw_keys()` subtracts `deprecated_attributes` from the index attributes,
      reusing the same source `analysis/fidelity/scheme.py:313-333` reads; do not re-derive a list.
- [x] 2.2 — Mirror `_scheme_from_index`'s fail-loud behaviour: raise if a deprecated name is absent
      from `attributes`; raise if the remaining list is empty.
- [x] 2.3 — Rewrite the docstring at `validate.py:11-14`, which currently documents the inclusion of
      deprecated attributes as deliberate, stating why it changed.
- [x] 2.4 — Carry the expected-key count `N` alongside every completeness rate in the per-combo CSV
      and `_summary.csv`, so a 14-key rate is not silently compared to a 15-key rate.

**Files Modified:**
- `src/population_synthetic/analysis/validate_raw/validate.py` — `expected_raw_keys`, summary writer
- `tests/test_validate_raw.py`, `tests/test_validity_summary.py` — deprecation + denominator coverage
- `docs/architecture/{comparison-mapping,sub-packages}.md` — the two sentences stating the old
  column list and the old "attributes = expected keys" rule (stale on contact with 2.1/2.4)

**Dependencies:** None

### Phase 3: Versioning scheme and ordering
**Goal:** Family/version become first-class, and ordering leaves Python.

**Started:** 2026-07-28
**Completed:** 2026-07-28

- [x] 3.1 — Create `config/synthetic/axes/strategies/_families.yaml` with the five families in
      simplest-first order. Must be `_`-prefixed or `discover_axis_values` will try to load it as a
      strategy and crash on the missing `id`.
- [x] 3.2 — Widen the strategy loader to read and validate `family` / `version`, following the
      `context:` precedent in `_load_strategy` (single seam, `ValueError` on unrecognised value).
- [x] 3.3 — Backfill `family` and `version: 1` into the five v1 YAMLs. Metadata only — no category or
      edge changes.
- [x] 3.4 — Replace `STRATEGY_COMPLEXITY_ORDER` with
      `strategy_complexity_order(strategy_ids) -> list[str]`, ordering by (family_rank, version) and
      raising on an unknown family. Must yield a **total** order — the locked manuscript tie-break
      depends on it.
- [x] 3.5 — Migrate the consumers: `analysis/method_significance/{builder,charts,marginal_charts}.py`,
      `analysis/model_ranking/{builder,charts}.py`, `analysis/fidelity/charts.py`,
      `analysis/generation_metadata/{report_writer,charts}.py`,
      `analysis/multivariate_fidelity/charts.py`.
- [x] 3.6 — Replace the silent "unknown strategy sorts last" behaviour in
      `generation_metadata/report_writer.py:62-64` with a loud error.
- [x] 3.7 — Add a version selector to `analyze_method_significance.py`: raise when combos of mixed
      versions are present unless a version is named explicitly. v1 and v2 are not replicates and
      must never be pooled into the `n = 1` per-cell design.

**Implementation notes:**

- The sort key is `(family_rank, version, strategy_id)`. The id is the third key purely to make the
  order **total by construction** — two files can never compare equal, so the manuscript tie-break
  is always decidable.
- `_load_strategy` requires `family`/`version` only for **selectable** strategies (stem without the
  `_` prefix), reusing the project-wide `discover_axis_values` convention. The frozen
  `_compared_only_*` record and `_debug_minimal` therefore stay untouched, as the file tree above
  requires. Malformed values raise regardless of prefix.
- `method_significance/builder.py` no longer holds a canonical five-method constant: the ordered
  method axis is resolved once per `build_method_significance` call from the strategies present in
  the records, and threaded into the helpers. The polynomial contrasts are generated for `k` levels
  by `_orthogonal_contrasts(k)`, which reproduces the classical `k = 5` vectors exactly, so no
  contrast estimate moves. A record on an unknown strategy now raises instead of being dropped;
  `metadata.dropped_combos` is kept (always empty) for output-schema stability.

**Files Modified:**
- `config/synthetic/axes/strategies/_families.yaml` — new
- `config/synthetic/axes/strategies/all_*.yaml` (×5) — metadata backfill
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — `_load_strategy`
- `src/population_synthetic/analysis/utils/axes.py` — ordering accessor
- eight analysis consumer modules listed in 3.5
- `scripts/analyze/analyze_method_significance.py` — version selector

**Dependencies:** None (parallel with Phases 1–2)

### Phase 4: The v2 strategies
**Goal:** Five runnable v2 arms, with an incompatible pair failing loudly.

**Started:** 2026-07-28
**Completed:** 2026-07-28

- [x] 4.1 — Author `all_pick_v2.yaml` (14 categories, `context: none`, all edges empty).
- [x] 4.2 — Author `all_pick_dag_v2.yaml` (14 categories, birth chain rewired).
- [x] 4.3 — Author `all_generate_pick_v2.yaml`.
- [x] 4.4 — Author `all_generate_evaluate_pick_v2.yaml`.
- [x] 4.5 — Author `all_generate_evaluate_random_pick_v2.yaml`.
- [x] 4.6 — Add the compatibility guard: raise when the strategy's category set does not cover the
      country's required raw keys, naming the missing attributes and both axis ids. Implemented at the
      orchestration edge rather than in `compose_manifest` — see the note below.
- [x] 4.7 — Initially **skipped** during Phase 4: `config/gui/flows/generate_parallel.yaml` held
      unrelated uncommitted state at implementation time. **Completed later in Phase 6**, once that
      state had been committed separately — `selection.strategies` is now the five v2 arms, and the
      strategies axis additionally defaults its version filter to the highest declared version.

**Implementation notes:**

- **Guard placement (a deliberate layering decision).** The contract table above nominated
  `manifest_loader.compose_manifest`, but the country's required raw keys come from the mapping
  `_index.json` via `analysis/validate_raw/validate.py::expected_raw_keys`, and
  `analysis/utils/country_config.py` already imports `manifest_loader.discover_axis_values`. Importing
  `expected_raw_keys` into `manifest_loader` would therefore both invert the layer dependency and close
  an import cycle, avoidable only by a lazy in-function import that papers over the inversion. Reading
  `_index.json` directly inside `manifest_loader` was rejected too: it would be a *third* copy of the
  deprecation-subtraction logic (`_scheme_from_index`, `expected_raw_keys`, and then this). The guard
  therefore lives in `scripts/generate/generate_identities_parallel.py`
  (`_assert_strategy_covers_country`), the orchestration edge that legitimately sees both layers and
  through which the CLI *and* the GUI both run. It fires immediately after `compose_manifest`, before
  any client is constructed or any persona directory is created.
- The strategy's category set is read via the generator's own `resolve_category_order`, so the guard
  tests the categories a run would actually resolve rather than a second, drifting parse of the YAML.
- Sweden's 14 required raw keys are exactly the v2 category set; Italy's 14 include `birth_location`,
  which v2 does not generate, so every v2 × `italian` pair raises naming it.
- `tests/test_method_significance_version_selector.py`'s `v2_strategy` fixture no longer writes a
  temporary `all_pick_v2.yaml` (it asserted the path was free, which Phase 4 makes false); it now uses
  the shipped arm and pins its `family`/`version`.

**Files Modified:**
- `config/synthetic/axes/strategies/all_*_v2.yaml` (×5) — new
- `scripts/generate/generate_identities_parallel.py` — `_assert_strategy_covers_country` guard
- `tests/test_strategy_v2.py` — new; `tests/test_method_significance_version_selector.py` — fixture

**Dependencies:** Phases 1–3

### Phase 5: Documentation and diagrams
**Goal:** No doc still claims five strategies or seventeen fields.

**Started:** 2026-07-28
**Completed:** 2026-07-28

- [x] 5.1 — `docs/architecture/axis-composition.md` — the versioning convention, `_families.yaml`,
      and the Sweden-only constraint.
- [x] 5.2 — `CLAUDE.md` — strategy versions and the country-compatibility rule.
- [x] 5.3 — `docs/architecture/sub-packages.md:138` — `axes.py` no longer owns a constant.
- [x] 5.4 — `docs/architecture/diagrams/synthetic_strategies/README.md` and
      `render_strategy_diagrams.py` — both hardcoded a 5-row table and the literal
      "17 demographic fields".
- [x] 5.5 — `docs/architecture/comparison-mapping.md` — note that the scored axis set is unchanged.
- [x] 5.6 — `docs/development/manuscript-motivation-map.md` (Pillar 6) — record v2 as a new arm.
- [x] 5.7 — ADR recording why the birth chain moved under age+sex, that v1↔v2 comparison is valid
      only over the 14 shared scored axes, and that the determinism fix makes pre-fix v1 personas
      non-reproducible.
- [x] 5.8 — Correct this plan's Architecture & Module Contracts table: the guard row nominated
      `manifest_loader.py`; the guard lives in
      `scripts/generate/generate_identities_parallel.py::_assert_strategy_covers_country`.

**Implementation notes:**

- **ADR placement.** The repository has no ADR directory or convention (no `adr/`,
  `decision-records/`, or equivalent anywhere in `docs/`), and inventing one was out of scope. The
  decision record is therefore a clearly-headed section, *"Decision record: strategy v2 (SCB chain
  alignment), 2026-07-28"*, at the end of `docs/architecture/axis-composition.md`, next to the
  versioning convention it justifies.
- **The render script was at `docs/architecture/diagrams/synthetic_strategies/`, not
  `scripts/dev/`.** It hardcoded a five-element `STRATEGIES` list and read layout coordinates from
  `config/gui/layouts/`, a directory that does not exist — the GUI writes its `.layout.json`
  sidecars *next to the strategy YAML* and they are git-ignored, so the script raised
  `FileNotFoundError` before rendering anything. It now discovers strategies via
  `discover_axis_values("strategies")` + `strategy_complexity_order`, treats the sidecar as
  optional, and falls back to a deterministic layered layout derived from the DAG. Verified by
  rendering all 10 strategies to a scratch directory; the committed figures were **not**
  regenerated (image files are outside this phase's scope).
- **Precision on the rewire.** Every doc states that `depends_on` controls *scheduling order only* —
  under `context: cumulative` the prompt still serialises every resolved attribute, per
  `fix-all-pick-context-leak.md`. No doc claims the rewire narrows prompt content.
- **Precision on the three drops.** `birth_location` is a deprecated *analysis* axis (in Sweden's
  `deprecated_attributes`, still mapped and emitted); `ethnicity_broad_global_approx` and
  `current_environment_type` appear in **no** mapping `_index.json` at all. The docs keep these
  distinct.

**Files Modified:**
- `docs/architecture/axis-composition.md` — versioning section + decision record
- `docs/architecture/sub-packages.md` — `axes.py` accessor functions replace the constant
- `docs/architecture/comparison-mapping.md` — scored-axis invariance across versions
- `docs/architecture/diagrams/synthetic_strategies/README.md`
- `docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py`
- `docs/development/manuscript-motivation-map.md` — Pillar 6
- `CLAUDE.md` — two Core Invariants bullets

**Dependencies:** Phase 4

### Phase 6: Version is a selection-side concept (added post-plan, 2026-07-28)
**Goal:** Versions become visible and filterable in the GUI, and invisible to the analysis pipeline.

**Started:** 2026-07-28 · **Completed:** 2026-07-28

Added after Phases 1–5 on the author's direction: *"the version should just be visible from the
GUI side and whatever the version, it is a strategy, no need for the analysis pipeline to know the
versioning idea."*

- [x] 6.1 — Remove `--version` and `select_version` from `analyze_method_significance.py`. Verified
      first in `method_significance/builder.py` that method levels resolve from **strategy ids**
      (`method_order = strategy_complexity_order(sorted({r.strategy for r in records}))`, cells keyed
      `(model, strategy)` and raising on duplicates) and that nothing groups by `family`. v1 and v2
      were therefore already distinct levels at `n = 1`; the Phase 3.7 guard defended against a
      collapse that could not occur. Deleted `tests/test_method_significance_version_selector.py`
      (5 tests; its surviving assertions are covered by `test_strategy_v2.py` and
      `test_strategy_ordering.py`).
- [x] 6.2 — Retained the `(family_rank, version, id)` sort key. Ordering metadata is not the pipeline
      branching on version; totality is still required by the locked manuscript tie-break.
- [x] 6.3 — GUI version filter: a **retaining filter** in `checkable_axis_list.py`, generic over
      facets (the widget never learns the word "version"). Rule: `visible = matches(facets) OR
      isChecked()`, enforced structurally — `_apply_filter` is the only place visibility is set, so
      no code path can hide a checked row. Invariant: `set(visible_ids()) >= set(selected_ids())`.
- [x] 6.4 — `axis_selector.py`: chips derived from `strategy_versions()` (config, never a literal
      version list) plus a Qt-free `mixed_version_notice()` advisory. Advisory only — a mixed-version
      run is legitimate and is never blocked.
- [x] 6.5 — `tests/test_axis_version_filter.py` (15 tests) with a session-scoped offscreen
      `QApplication` fixture — the repo's first widget-level test. `conftest.py` unmodified.
- [x] 6.6 — Docs corrected: the invariant now reads "a strategy version is just another strategy";
      Decision 4 records why the flag was added and then removed.

**Not done:** `config/gui/flows/analysis_workflow.yaml` was deliberately **not** given a `version:`
option — that was the rejected alternative, superseded by removing the guard entirely.

**Files Modified:**
- `scripts/analyze/analyze_method_significance.py` — flag and selector removed
- `src/population_synthetic/analysis/method_significance/builder.py`, `analysis/utils/axes.py` — docstrings
- `src/population_synthetic/gui/widgets/checkable_axis_list.py` — generic facet filter
- `src/population_synthetic/gui/widgets/axis_selector.py` — version chips + advisory
- `tests/test_axis_version_filter.py` — new
- `CLAUDE.md`, `docs/architecture/{axis-composition,sub-packages}.md`, `docs/development/manuscript-motivation-map.md`

**Dependencies:** Phases 1–5

---

## Testing Plan

### Unit Tests
- [ ] `_build_dag` returns a byte-identical order across ≥20 subprocesses with `PYTHONHASHSEED`
      unset, for every strategy YAML — the regression test that would have caught the original bug.
- [ ] `_build_dag` respects declaration order among in-degree-0 categories.
- [ ] Existing cycle and undeclared-dependency `ValueError`s still raise.
- [ ] `expected_raw_keys("swedish")` excludes `birth_location`; `expected_raw_keys("italian")`
      includes it.
- [ ] `expected_raw_keys` raises when a deprecated name is absent from `attributes`, and when the
      filtered list is empty — mirroring `tests/test_scheme_index.py`.
- [x] Each v2 YAML: stem == `id`, no `_` prefix, `family` present in `_families.yaml`, `version: 2`,
      categories ⊆ the country simulation-config schema, exactly the 14 defined in Definitions.
      (`tests/test_strategy_v2.py`, which also pins v2 == v1 minus the three drops: same `method`,
      same `context`, same surviving edges.)
- [x] `strategy_complexity_order` yields a total order; raises on an unknown family; with only v1 ids
      present it returns exactly the legacy `STRATEGY_COMPLEXITY_ORDER` sequence.
      (`tests/test_strategy_ordering.py`)
- [ ] `decompose_slug` round-trips `swedish_all_pick_v2_claude_opus` and `swedish_all_pick_claude_opus`
      to distinct, correct triples.

### Integration Tests
- [ ] Generate 5 personas with `all_pick_dag_v2` × `swedish_02` against a stubbed client; assert
      identity keys are exactly the 14, and that `age` and `biological_sex` precede
      `birth_country_detail` in the captured prompt sequence.
- [ ] Run `validate_raw` → `mapping` → `validate_mapped` → `population_cap` on that output: 100% raw
      pass, no `__UNMAPPED__` beyond baseline, 5 personas capped.
- [ ] Assert the mapper reconstructs `birth_location` from `birth_country_detail` when the raw key is
      absent (`Syria` → `Outside Europe`, `Poland` → `Europe (Other)`, `Sweden` → `Sweden`).
- [ ] Fidelity scoring of a v2 combo emits exactly the 14 scored axes, identical to v1's axis list.
- [x] `analyze_method_significance` raises on a mixed-version combo set without an explicit version.
      (`tests/test_method_significance_version_selector.py`)

### Manual Verification
- [ ] Launch the GUI; confirm all five v2 ids appear in the strategy axis and that the DAG preview
      renders the rewired birth chain via Sugiyama auto-layout (no `.layout.json` needed).
- [ ] Run one real v2 combo at `--n 5` end-to-end through the analysis workflow.
- [ ] Regenerate the manuscript fidelity table with v1-only inputs; diff against the current table —
      must be identical.

### Edge Cases
- [x] `--country-id italian --strategy-id all_pick_dag_v2` raises before any LLM call, naming
      `birth_location`. (`tests/test_strategy_v2.py`; the converse — every v2 on `swedish`/`swedish_02`
      and every v1 on all three countries — passes.)
- [ ] A country with no `deprecated_attributes` (Italy) is unaffected by the Phase 2 change.
- [x] A strategy YAML missing `family` or `version` fails loudly at load, not silently defaulted
      (selectable strategies; `_`-prefixed co-located definitions are exempt by convention).
- [x] `_families.yaml` accidentally renamed without the `_` prefix is caught by a test
      (`test_family_index_is_not_a_discoverable_strategy`).
- [ ] Mixed v1/v2 combos present in an output directory do not silently collapse into one chart
      series.

---

## Documentation Plan

- [x] Update `CLAUDE.md` — strategy versioning, country-compatibility rule
- [x] Update `docs/architecture/axis-composition.md` — versioning convention
- [x] Update `docs/architecture/sub-packages.md` — `axes.py` ownership change
- [x] Update `docs/architecture/comparison-mapping.md` — scored axis set unchanged
- [x] Update `docs/architecture/diagrams/synthetic_strategies/README.md` + `render_strategy_diagrams.py`
- [x] Update `docs/development/manuscript-motivation-map.md` — Pillar 6
- [x] Add ADR: birth-chain rewire rationale and v1↔v2 comparability boundary (no ADR tree exists in
      this repo — recorded as a "Decision record" section in `docs/architecture/axis-composition.md`)

---

## Rollback Plan

1. **Before any run:** the change is additive. Delete the five `*_v2.yaml` files and `_families.yaml`,
   and revert the four code commits. No data is touched.
2. **Data considerations:** no migration. v2 writes to new slug directories
   (`{country}_{strategy}_v2_{model}`); v1 directories are never opened for write. The only
   non-additive changes are `expected_raw_keys` and `_build_dag` — reverting them restores prior
   behaviour exactly, though see the Risks note on v1 reproducibility.
3. **Rollback procedure:** revert the Phase 3 commit last (it touches the most consumers); the
   ordering accessor must be reverted together with its eight call sites in one commit.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **v1 is not reproducible post-fix.** Existing v1 personas were generated under hash-random category order; re-running v1 after the determinism fix produces a different order and therefore different personas. | High | High | Treat existing v1 output as an archived baseline, not a re-derivable one. Record the code version in `run_metadata.json`. Decide explicitly — and state in the manuscript — whether v1 is regenerated for a clean comparison or cited as pre-fix. **This decision is open and belongs to the author, not the implementer.** |
| Replacing `STRATEGY_COMPLEXITY_ORDER` silently changes the locked global-best-strategy tie-break, moving a published manuscript result | Medium | High | Regression test asserting v1-only ordering equals the legacy sequence; regenerate the fidelity table and diff before/after |
| Chart palette overflow — `_COLOR_SERIES` has 7 colors and progression charts plot real + 5 methods | Medium | Low | Version-as-separate-run keeps each chart at 5 arms; add a fail-loud check if series exceed the palette |
| A v2 run on Italy silently produces zero capped personas | Low (guard) | High | Phase 4.6 compatibility guard raises pre-generation; edge-case test |
| Completeness rates across versions compared against different denominators | Medium | Medium | Phase 2.4 carries `N` alongside every rate |
| Cross-version aggregate means computed over different category counts | Medium | Medium | Restrict cross-version comparison to the 14 shared scored axes; ADR records the boundary |
| Dropping the `birth_location` gate degrades `birth_country_detail` fidelity — the real chain enforces the ~76% Sweden mass via an explicit two-step draw with a Sweden-excluded re-draw | Medium | Medium | `birth_country_detail` is currently insensitive to method (p_bh = 0.095); v2 gives a direct read. If TV degrades materially, revisit keeping `birth_location` as an unscored gate |
| `_families.yaml` discovered as a strategy if the `_` prefix is lost | Low | Medium | Test asserts `discover_axis_values('strategies')` never returns a `_`-prefixed stem |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Determinism | Small (2 files) | None |
| Phase 2 — Validation gate | Small (1 file) | None |
| Phase 3 — Versioning & ordering | Large (12 files, 8 consumers) | None |
| Phase 4 — v2 strategies | Medium (6 files) | Phases 1–3 |
| Phase 5 — Docs & diagrams | Medium (7 files) | Phase 4 |

---

## References

- `docs/development/plans/completed/deprecate-birth-location-analysis-axis.md` — Out-of-Scope item 6
  defers the independence fix this plan implements
- `docs/development/plans/completed/align-strategies-scb-comparable-categories.md` — the 32→17 trim;
  its `scb_only_*` rejection is addressed in Alternatives
- `docs/development/plans/completed/add-all-pick-dag-strategy.md` — strategy-authoring precedent
- `docs/development/plans/completed/fix-all-pick-context-leak.md` — `context:` key precedent; the
  rejected depends_on-filtered context
- `docs/development/plans/completed/configurable-identity-pipeline.md` — `_build_dag` origin
- `docs/development/plans/completed/persona-validation-gate-reorder.md` §3.1 — expected attribute list
  must stay config-derived
- `docs/development/plans/completed/manuscript-fidelity-tables.md` — the locked global-best-strategy rule
- `docs/development/plans/completed/per-category-method-model-significance.md` — `n = 1` per cell

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
<!-- config/gui/flows/generate_parallel.yaml is deliberately EXCLUDED: it carries unrelated -->
<!-- uncommitted selection state that predates this branch. Task 4.7 was skipped for the same reason. -->
- CLAUDE.md
- config/synthetic/axes/strategies/_families.yaml
- config/synthetic/axes/strategies/all_generate_evaluate_pick.yaml
- config/synthetic/axes/strategies/all_generate_evaluate_pick_v2.yaml
- config/synthetic/axes/strategies/all_generate_evaluate_random_pick.yaml
- config/synthetic/axes/strategies/all_generate_evaluate_random_pick_v2.yaml
- config/synthetic/axes/strategies/all_generate_pick.yaml
- config/synthetic/axes/strategies/all_generate_pick_v2.yaml
- config/synthetic/axes/strategies/all_pick.yaml
- config/synthetic/axes/strategies/all_pick_dag.yaml
- config/synthetic/axes/strategies/all_pick_dag_v2.yaml
- config/synthetic/axes/strategies/all_pick_v2.yaml
- docs/architecture/axis-composition.md
- docs/architecture/comparison-mapping.md
- docs/architecture/diagrams/synthetic_strategies/README.md
- docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py
- docs/architecture/sub-packages.md
- docs/development/manuscript-motivation-map.md
- docs/development/plans/active/strategy-v2-scb-chain-alignment.md
- scripts/analyze/analyze_method_significance.py
- scripts/generate/generate_identities_parallel.py
- src/population_synthetic/analysis/fidelity/charts.py
- src/population_synthetic/analysis/generation_metadata/charts.py
- src/population_synthetic/analysis/generation_metadata/report_writer.py
- src/population_synthetic/analysis/method_significance/builder.py
- src/population_synthetic/analysis/method_significance/charts.py
- src/population_synthetic/analysis/method_significance/marginal_charts.py
- src/population_synthetic/analysis/model_ranking/builder.py
- src/population_synthetic/analysis/model_ranking/charts.py
- src/population_synthetic/analysis/multivariate_fidelity/charts.py
- src/population_synthetic/analysis/utils/axes.py
- src/population_synthetic/analysis/validate_raw/validate.py
- src/population_synthetic/generators/synthetic/identity_generator_configurable.py
- src/population_synthetic/gui/widgets/axis_selector.py
- src/population_synthetic/gui/widgets/checkable_axis_list.py
- tests/test_axis_version_filter.py
- tests/test_identity_generator_configurable.py
- tests/test_method_comparison.py
- tests/test_method_comparison_chart.py
- tests/test_method_significance.py
- tests/test_method_significance_charts.py
- tests/test_method_significance_version_selector.py  (deleted)
- tests/test_strategy_ordering.py
- tests/test_strategy_v2.py
- tests/test_validate_raw.py
- tests/test_validity_summary.py

---

# Axis Composition System

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> **Axis composition** · [Configuration](configuration.md) · [Commands](commands.md)

How identity generation is configured via three orthogonal axes instead of a monolithic manifest.

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest.
`compose_manifest` in `src/population_synthetic/generators/synthetic/manifest_loader.py` merges YAML from four
layers:

1. `config/synthetic/experiment_defaults.yaml` -- base parameters (mode, output_base, parallel settings)
2. `config/synthetic/axes/models/{model_id}.yaml` -- provider, model name, API key env var (supported providers: `gemini`, `claude`, `ollama`, `openai_compat`, `openrouter`)
3. `config/synthetic/axes/strategies/{strategy_id}.yaml` -- generation strategy (all_pick, all_generate_pick, etc.)
4. `config/synthetic/axes/countries/{country_id}.yaml` -- country-specific simulation config and real population

Each strategy yaml is the **single source of truth** for that strategy: it carries `id`, `family`,
`version`, `label`, `description`, and the full per-category `categories` DAG
(`method` + `depends_on`) inline -- the generator's `_load_strategy` reads `categories` straight from
this file (there is no separate `strategy_defs/` json). Yamls whose filename starts with `_` (e.g.
`_debug_minimal.yaml`, `_compared_only_generate_evaluate_random_pick.yaml`, and the family index
`_families.yaml`) are co-located definitions that are usable via an explicit `--strategy <path>` but
are **not** selectable axis options -- `discover_axis_values` skips them, and `_load_strategy`
correspondingly requires `family`/`version` only for the selectable (non-`_`) ones. Node coordinates
for the GUI DAG preview are an optional `{strategy_id}.layout.json` sidecar written *next to* the
strategy yaml when a node is dragged; it is git-ignored and per-user, and both the GUI and the
diagram renderer fall back to an automatic layout when it is absent.

The output slug is `{country_id}_{strategy_id}_{model_id}`, and the run directory is
`{output_base}/01_Raw/{slug}/`. Use `--model-id`, `--strategy-id`, `--country-id` CLI flags instead
of `--manifest` to invoke this path.

## Strategy versioning: `family` + `version`

The strategy axis carries a **version** dimension. Every selectable strategy declares two metadata
keys alongside its `id`:

| Key | Meaning |
|-----|---------|
| `family` | Which of the five generation methods it implements -- one of `all_pick`, `all_pick_dag`, `all_generate_pick`, `all_generate_evaluate_pick`, `all_generate_evaluate_random_pick`. Two strategies share a family **iff** they differ only by version. |
| `version` | Integer revision (>= 1) of that family's category set and dependency wiring. |

`config/synthetic/axes/strategies/_families.yaml` declares the five families in **simplest-first**
order; a family's list position *is* its rank. The `_` prefix is load-bearing: it is what keeps
`discover_axis_values("strategies")` from trying to load the index as a strategy.

There are currently **10 selectable strategies** -- five families × two versions
(`discover_axis_values("strategies")` returns exactly those ten ids). The version is part of the
**id** (`all_pick_dag` → `all_pick_dag_v2`), and the strategy file's stem always equals its `id`.
That is deliberate: the output slug is `{country_id}_{strategy_id}_{model_id}`, so a versioned id
yields its own `01_Raw/` directory and v1 results are never overwritten. `decompose_slug` matches
the middle segment against the exact strategy-id set, so `all_pick` and `all_pick_v2` can never be
confused.

**v1 and v2 are separate experimental arms, not two runs of the same one.** They differ in what is
generated:

| | Categories | Birth chain |
|---|---|---|
| v1 | 17 | `birth_location: depends_on: []`, `birth_country_detail: depends_on: [birth_location]` |
| v2 | 14 | `birth_country_detail: depends_on: [age, biological_sex]` (no `birth_location`) |

v2 drops `birth_location`, `ethnicity_broad_global_approx` and `current_environment_type`; it is
otherwise identical to its v1 sibling (same `method`, same `context`, same surviving edges).
`all_pick_v2` is the exception to the rewire: like `all_pick` it keeps `context: none` and all-empty
`depends_on`, so the rewire is a structural no-op there by design -- it remains the context-free
baseline and differs from `all_pick` only by the three dropped categories.

**The analysis pipeline does not know about versioning.** A version is a *selection* concern -- it is
visible on the GUI / CLI side, where you pick which strategies to run. Downstream, `all_pick_v2` is
simply a strategy id like any other: it owns its own slug, its own `01_Raw/` directory, and its own
level on every method axis. Nothing pools a v2 into its v1 sibling, so no analysis ever fabricates
replication by mixing them, and a run may freely select both. `analysis/utils/axes.py` reads
`version` for **ordering only** (see below), and no analysis process branches on it.

The consequence is interpretive, not structural: `analyze_method_significance.py` runs an ordered
trend test (Page's L) along the complexity order, so on an axis that contains both v1 and v2 arms the
trend is measured across an ordering that **interleaves method complexity with strategy version**.
Read such a result as a trend over the ten-level ladder it actually ran on, not as a pure
complexity effect. Restricting to one version, when that is what you want, is a matter of selecting
the strategies (`--strategy`) for the run.

### Ordering the strategy axis

`analysis/utils/axes.py::strategy_complexity_order(ids)` orders any set of present ids simplest-first
by the total sort key `(family_rank, version, strategy_id)` -- family rank from `_families.yaml`,
then ascending version within a family, then the id itself so that no two entries can ever compare
equal. Totality is load-bearing: the manuscript's global-best-strategy rule breaks ties by preferring
the *earlier* (simpler) strategy, so a partial or unstable order would silently move a published
result. There is no Python constant holding a strategy list, and nothing is read at import time; an
unknown id or an undeclared family **raises** rather than sorting last.

### Country compatibility (v2 is Sweden-only)

A (strategy, country) pair is valid **iff** the strategy's category set covers the country's required
raw keys -- the country mapping `_index.json` attributes **minus** its `deprecated_attributes`, with
the `age_group`→`age` alias (`analysis/validate_raw/validate.py::expected_raw_keys`). Verified
counts:

| Country | Required raw keys | `birth_location` required? | v2 valid? |
|---------|-------------------|----------------------------|-----------|
| `swedish` / `swedish_02` | 14 | No (deprecated for Sweden) | Yes -- Sweden's 14 keys are exactly the v2 category set |
| `italian` | 14 | **Yes** (nothing deprecated for Italy) | No |

The guard is `scripts/generate/generate_identities_parallel.py::_assert_strategy_covers_country`. It
fires immediately after `compose_manifest`, before any client is constructed or any persona directory
is created, and names the missing attributes plus both axis ids. It lives at the orchestration edge
rather than in `manifest_loader.compose_manifest` because the requirement is an analysis-layer fact:
`analysis/utils/country_config.py` already imports `manifest_loader`, so pulling `expected_raw_keys`
into `generators/` would both invert the layer dependency and close an import cycle, and re-reading
`_index.json` there would be a third copy of the deprecation-subtraction logic. Consequently the
guard covers the **axis-composition path only** (`--model-id` / `--strategy-id` / `--country-id`);
`--manifest` and explicit `--config` / `--strategy` paths carry no country id and are not checked.

## Decision record: strategy v2 (SCB chain alignment), 2026-07-28

Recorded here rather than in a separate ADR tree because this repository has no ADR directory or
convention; this section is the decision record for the v2 arm.

**Context.** The real SCB sampler conditions birthplace on `(age_group, sex_label)` at both of its
steps -- `birth_location` and then `birth_country_detail`, the latter gated by the former with a
Sweden-excluded re-draw. Every v1 strategy instead declared `birth_location: depends_on: []` and
`birth_country_detail: depends_on: [birth_location]`; age and sex appeared nowhere in the chain.
Separately, three generated categories cost one LLM call per persona each while feeding no analysis.

**Decision 1 -- the birth chain moves under `age` + `biological_sex`.** In v2,
`birth_country_detail` declares `depends_on: [age, biological_sex]` and `birth_location` is not
generated at all, so the synthetic chain is rooted in the same two conditioning variables as the real
one.

*What this does and does not change.* `depends_on` controls **scheduling order only**. Under the
default `context: cumulative`, the prompt still serialises *every* already-resolved attribute, so the
rewire does not change what any prompt contains -- filtering prompt context to `depends_on` was
explicitly rejected in `fix-all-pick-context-leak.md` and remains rejected. What the rewire
guarantees is that `age` and `biological_sex` are always **already resolved** when
`birth_country_detail` is filled, which under v1's wiring they were not. This is only a guarantee
because of the determinism fix below.

**Decision 2 -- v1↔v2 comparison is valid only over the 14 shared scored axes.** The scored axis set
is untouched by this change: no mapping `_index.json`, per-attribute JSON, `refine_from` wiring or
fidelity config was modified, and `load_scheme("swedish").attributes` still returns 14 attributes,
byte-identical before and after. The two arms are therefore directly comparable on fidelity, TV
similarity and every per-axis statistic. They are **not** comparable on anything whose denominator is
the generated category count (17 vs 14) -- raw completeness rates, per-persona LLM-call counts, token
totals, cost -- and cross-version aggregate means over category counts are meaningless. The
per-combo validity CSVs carry `n_expected_keys` alongside every rate so a 14-key rate is never read
as a 15-key one.

Note the three dropped categories are not one kind of thing. `birth_location` **is** in Sweden's
`deprecated_attributes` (still mapped and emitted into the canonical population data, excluded from
the comparison axis). `ethnicity_broad_global_approx` and `current_environment_type` were never in
*any* mapping `_index.json` -- they are synthetic-only inventions from a 2026-05 comparison extractor
that no longer reads them, so they were never mapped or scored anywhere.

**Decision 3 -- pre-fix v1 personas are an archived baseline, not a re-derivable one.** `_build_dag`
previously seeded Kahn's queue from a `set`, and CPython randomises string hashing per process, so
the order of the in-degree-0 roots varied between invocations. Since the prompt context is cumulative,
that meant a given category saw a different set of already-resolved attributes on different runs,
with no record of which. `_build_dag` is now a pure function of its input -- topological order derives
from YAML declaration order, ties among in-degree-0 categories broken by declaration order -- and the
resolved order is written to `run_metadata.json` as `resolved_category_order`.

The consequence: **re-running a v1 strategy after the fix does not reproduce the existing v1
personas.** Existing v1 output must be treated as an archived baseline. Whether v1 is regenerated for
a clean comparison or cited as pre-fix is an authoring decision that belongs in the manuscript, not
in the code.

**Decision 4 -- versioning stops at the selection boundary; the analysis pipeline stays
version-unaware.** The version is visible where strategies are *chosen* (GUI / CLI); past that point
a v2 is just a strategy. An earlier iteration gave `analyze_method_significance.py` a `--version N`
flag that refused a mixed-version combo set; it was removed. The rationale it rested on -- that
pooling two arms fabricates replication -- does not apply, because nothing pools them: method levels
are keyed on the strategy **id**, so `all_pick` and `all_pick_v2` are two distinct levels with
``n = 1`` each, exactly as any two families are. A guard buys no statistical safety and costs a
config-level concept leaking into every analysis process. What remains is an interpretation note
(above): a mixed-version method axis interleaves complexity with version, so an ordered-trend
statistic on it is a trend over that ladder. Selecting one version is done by selecting strategies.

## Model retirement: `discarded`

A model axis file marks itself retired from the sweep with a top-level `discarded: true`. **An
absent key means active** — a documented default, which is why the 15 live model files carry no key
at all rather than an explicit `discarded: false`. Only `true`/`false` are accepted; any other value
raises (`axis_selector.model_status_facet_groups`), since a truthy string would silently retire a
model. The flag is a *selection* concern only — nothing downstream of the axis lists reads it, and a
discarded model stays fully runnable if you check it. Five Ollama models currently carry it; the flag
replaces the old `"… (discarded for now)"` suffix that encoded the same fact inside the `label`
string. It is unrelated to a mapping tier's `deprecated_attributes`.

### GUI chip rows and their defaults

The Flow Runner's Global tab (`gui/widgets/axis_selector.py::axis_facets`) gives two of the three
axis lists a chip row — a view-only filter over the rows on screen:

| Axis | Chips | Checked on open |
|------|-------|-----------------|
| Models | `Active` / `Discarded`, from the `discarded` key | `Active` |
| Strategies | `v{n}`, from each strategy's `version` | the **highest** discovered version |
| Countries | none (declares neither key) | — |

Both defaults are read off the config values, never hardcoded: dropping a v3 strategy file into
`config/synthetic/axes/strategies/` makes `v3` the checked chip and demotes `v2`, with no code
change. Filtering is **retaining** — `visible = matches(active chips) OR isChecked()` — so a chip
that starts unchecked can never hide a selected item: loading a flow that selects a v1 strategy shows
that row, de-emphasised and marked `· v1 kept`. A chip toggle emits no signal and never dirties the
flow YAML.

## Ollama model axes: per-host workers, no `base_url`

`provider: ollama` model axis files differ from every other provider in two ways, because an
Ollama run targets a *machine* and worker capacity is a function of (model × GPU VRAM):

- **No `model_config.base_url`.** The endpoint is a property of the selected host, not of the
  model. It is resolved at composition time from the host registry
  ([`config/synthetic/ollama_hosts.yaml`](configuration.md)) via the `--ollama-host` flag
  (`None` → the registry's `default_host`). There is no default base URL anywhere in code — the
  client requires an explicit one — so no run can be dispatched to an unintended GPU.
- **`parameters.parallel.workers` is a `{host_id: n}` map**, not a scalar:

  ```yaml
  parameters:
    parallel:
      # Per-host worker count. A host absent from this map does not serve this model.
      workers:
        linux_3060: 2
        windows_4070tis: 6
  ```

  A host id **absent** from the map *is* the "this host does not serve this model" signal — there
  is no separate availability list to keep in sync. A present key asserts both "the weights are
  pulled on that host" and "this worker count has been assessed for it".

`compose_manifest(model_id, strategy_id, country_id, ollama_host_id=None)` is the **one**
normalization point for both facts. It resolves the host, sets `ManifestConfig.base_url` from it,
records the resolved id in `ManifestConfig.ollama_host` (provenance: `run_metadata.json` and
`manifest_snapshot.yaml` both carry it), and **collapses** `workers[host_id]` to the scalar
`ManifestConfig.parallel_workers`. Nothing below this layer learns that hosts exist. The gate is
fail-fast in both directions:

| Condition | Result |
|-----------|--------|
| Selected host absent from a model's `workers` map | Raises, naming the model, the host, and the hosts that **do** serve it — before any persona directory is created |
| `workers` is a scalar (the pre-registry shape) | Raises: accepting it would silently reintroduce a host-implicit worker count |
| Provider is not `ollama` | `--ollama-host` is inert; no host is resolved, `workers` stays the axis file's own scalar |

`workers_for_host(model_data, host_id) -> int | None` is the non-raising twin, for callers that
must **display** an unsupported pair rather than fail on it (the GUI summary panel renders an
em dash). Both route through the same lookup, so they can never disagree.

Non-Ollama model axes keep the scalar `workers`, and the frozen
`config/synthetic/manifests/identity_manifest_0NN_*.yaml` seed manifests keep theirs too — they
are historical records of runs that already happened on one machine, and `load_manifest` (the
file path, not the axis path) reads that scalar unchanged.

## See also

- [Configuration](configuration.md) — the axis config files (`config/synthetic/axes/*`) and the
  simulation configs they point at.
- [Commands](commands.md) — the `--model-id` / `--strategy-id` / `--country-id` invocations.
- [`../development/debugging-identity-generation.md`](../development/debugging-identity-generation.md)
  — reconstructing a run's output directory from its axis IDs.

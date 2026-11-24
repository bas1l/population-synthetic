# Synthetic identity-generation strategy diagrams

Workflow / DAG diagrams for the configurable **LLM identity-generation
strategies**. These describe how persona identities are *generated* by an LLM —
distinct from the sibling [`../real/`](../real/README.md) diagrams, which
describe how the *real* population is sampled from real statistics.

The strategy axis has two dimensions: five **families** (the generation method)
× a **version** (the category set and dependency wiring) — 10 selectable
strategies in all. See [Axis composition](../../axis-composition.md#strategy-versioning-family--version)
for the versioning convention. Each strategy has two artefacts (same content,
different format), named `{strategy_id}.svg` / `{strategy_id}.png`:

| Family | Per-field method | LLM calls / field | v1 id (17 fields) | v2 id (14 fields) |
|---|---|---|---|---|
| `all_pick` | `pick` | 1 | `all_pick` | `all_pick_v2` |
| `all_pick_dag` | `pick` | 1 | `all_pick_dag` | `all_pick_dag_v2` |
| `all_generate_pick` | `generate_pick` | 2 (enumerate → select) | `all_generate_pick` | `all_generate_pick_v2` |
| `all_generate_evaluate_pick` | `generate_evaluate_pick` | 3 (enumerate → evaluate → select) | `all_generate_evaluate_pick` | `all_generate_evaluate_pick_v2` |
| `all_generate_evaluate_random_pick` | `generate_evaluate_random_pick` | 2 + Python sample (numeric: 1 + sample) | `all_generate_evaluate_random_pick` | `all_generate_evaluate_random_pick_v2` |

The table is descriptive, not authoritative: the renderer **discovers** the
strategy list via `discover_axis_values("strategies")` and orders it with
`strategy_complexity_order`, so a new family or version is picked up with no edit
to the script. Regenerate every file (2 per selectable strategy — 20 at present)
with:

```bash
python docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py
```

The committed SVG/PNG set currently covers the v1 strategies only; run the
command above to add the v2 figures.

## What each diagram shows

Two panels:

1. **Category dependency DAG** (left) — the strategy's demographic fields (17 for
   a v1 strategy, 14 for a v2 one) with their `depends_on` edges. Nodes sit at the
   coordinates in the strategy's `{strategy_id}.layout.json` sidecar if the GUI has
   written one (that file is git-ignored and per-user), and at automatic layered
   coordinates derived from the DAG otherwise.
   `depends_on` fixes the topological *resolution order* (Kahn's algorithm in
   `IdentityGeneratorConfigurable._build_dag`, ties among in-degree-0 categories
   broken by YAML declaration order); for the cumulative strategies the
   prompt context is cumulative (every already-resolved value is passed along),
   so the edges show which parents are *guaranteed* present when a child is
   filled. (`all_pick` is the exception — see below — where no context is passed
   at all.) `age` (the only numeric field) is drawn with a bold edge.
2. **Per-field method pipeline** (right) — the inner sequence of LLM calls /
   Python sampling that fills one field, with `×3 JSON retry` annotations on LLM
   steps, the weight/candidate reconcile retry loop where applicable, and the
   numeric-distribution side-branch for `generate_evaluate_random_pick`.

## Key distinction: `all_pick` vs `all_pick_dag`

Both use the identical `pick` method (1 LLM call). They differ in `depends_on`:
`all_pick` declares no edges (every field is a root, resolved in YAML declaration
order), while `all_pick_dag` declares the dependency edges that force parents to
resolve before children. The same contrast holds between `all_pick_v2` and
`all_pick_dag_v2`.

They also now differ in **context**. `all_pick` carries the top-level
`context: none` key and is genuinely **context-free**: no previously-resolved
attribute is serialised into any prompt (every field sees the first-category
sentinel), making it the manuscript's clean no-context baseline. `all_pick_dag`
and the `all_generate_*` strategies omit the key and default to
`context: cumulative` — the full accumulated persona is passed into every prompt
(the "leak" is intentionally retained there so those arms stay unchanged).

## Key distinction: v1 vs v2

A v2 strategy is its v1 sibling minus three categories — `birth_location`,
`ethnicity_broad_global_approx`, `current_environment_type` — with
`birth_country_detail` rescheduled to depend on `age` and `biological_sex` (so the
synthetic birth chain is rooted in the same two conditioning variables as the real
SCB one). `all_pick_v2` is the exception: like `all_pick` it keeps `context: none`
and all-empty `depends_on`, so it differs from `all_pick` only by the three drops.

The rewire changes **scheduling order only**. Under `context: cumulative` the
prompt still serialises every already-resolved attribute, so no prompt's *content*
narrows; what the edges guarantee is that `age` and `biological_sex` are always
already resolved when `birth_country_detail` is filled.

Source: `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` and
the strategy definitions under `config/synthetic/axes/strategies/` (with the
optional, git-ignored `{strategy_id}.layout.json` coordinate sidecars alongside
them).

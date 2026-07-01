# Synthetic identity-generation strategy diagrams

Workflow / DAG diagrams for the five configurable **LLM identity-generation
strategies**. These describe how persona identities are *generated* by an LLM —
distinct from the sibling [`../database/`](../database/README.md) diagrams, which
describe how the *reference* population is sampled from real statistics.

Each strategy has two artefacts (same content, different format):

| Strategy | Per-field method | LLM calls / field | Vector (SVG) | Image (PNG) |
|---|---|---|---|---|
| `all_pick` | `pick` | 1 | `all_pick.svg` | `all_pick.png` |
| `all_pick_dag` | `pick` | 1 | `all_pick_dag.svg` | `all_pick_dag.png` |
| `all_generate_pick` | `generate_pick` | 2 (enumerate → select) | `all_generate_pick.svg` | `all_generate_pick.png` |
| `all_generate_evaluate_pick` | `generate_evaluate_pick` | 3 (enumerate → evaluate → select) | `all_generate_evaluate_pick.svg` | `all_generate_evaluate_pick.png` |
| `all_generate_evaluate_random_pick` | `generate_evaluate_random_pick` | 2 + Python sample (numeric: 1 + sample) | `all_generate_evaluate_random_pick.svg` | `all_generate_evaluate_random_pick.png` |

Regenerate all ten files with:

```bash
python docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py
```

## What each diagram shows

Two panels:

1. **Category dependency DAG** (left) — the 17 demographic fields placed at the
   strategy's canonical `*.layout.json` coordinates, with `depends_on` edges.
   `depends_on` fixes the topological *resolution order* (Kahn's algorithm in
   `IdentityGeneratorConfigurable._build_dag`); the prompt context is cumulative
   (every already-resolved value is passed along), so the edges show which
   parents are *guaranteed* present when a child is filled. `age` (the only
   numeric field) is drawn with a bold edge.
2. **Per-field method pipeline** (right) — the inner sequence of LLM calls /
   Python sampling that fills one field, with `×3 JSON retry` annotations on LLM
   steps, the weight/candidate reconcile retry loop where applicable, and the
   numeric-distribution side-branch for `generate_evaluate_random_pick`.

## Key distinction: `all_pick` vs `all_pick_dag`

Both use the identical `pick` method (1 LLM call). They differ **only** in
`depends_on`: `all_pick` declares no edges (all 17 fields are roots, resolved in
arbitrary topological order), while `all_pick_dag` declares the dependency edges
that force parents to resolve before children.

Source: `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` and
the strategy definitions under
`config/synthetic/axes/strategies/` (layout coordinates under
`config/gui/layouts/`).

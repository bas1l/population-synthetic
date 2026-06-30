# Reference ("database") population generation diagrams

Per-country workflow / conditional-sampling DAGs for the three **reference
population** generators — the populations sampled directly from real national
statistical APIs (SCB / SSB / ISTAT+Eurostat) that the comparison pipeline
treats as the "database" ground truth. (For the LLM persona-generation side, see
the sibling [`../synthetic_strategies/`](../synthetic_strategies/README.md).)

Each country has three artefacts (same content, different format):

| Country | Vector (SVG) | Image (PNG) | DAG source (Graphviz) |
|---|---|---|---|
| Sweden (SCB) | `sweden_generation_dag.svg` | `sweden_generation_dag.png` | `sweden_generation_dag.dot` |
| Norway (SSB) | `norway_generation_dag.svg` | `norway_generation_dag.png` | `norway_generation_dag.dot` |
| Italy (ISTAT + Eurostat) | `italy_generation_dag.svg` | `italy_generation_dag.png` | `italy_generation_dag.dot` |

Regenerate all nine files with:

```bash
python scripts/dev/draw_generation_dags.py
```

The `.dot` files render with Graphviz if it is installed (`dot -Tsvg x.dot -o x.svg`);
the SVG/PNG are produced directly by the matplotlib generator (no Graphviz needed).

## What each diagram shows

Two stacked parts:

1. **ETL band** (top) — the fetch → parse → distributions pipeline: API client(s) →
   statistical tables/dataflows → `load_all` → parsers → `PopulationDistributions`
   (16-field container) → the country `SampleService`.
2. **Conditional chained-sampling DAG** (below) — the order in which `sample_one`
   draws each demographic attribute for one individual, and what each draw is
   conditioned on. Node colours: dark-blue root joint draw `(age, sex)`; blue causal
   chain (`education → employment → {industry, employment_type, income_source}`);
   teal one-hop conditionals on `(age, sex)`; grey independent marginals (no parents);
   beige dropped/not-emitted fields. Edge styles: solid = conditioning, green = drawn
   only if employed, dashed grey = age/sex conditioning, dotted orange = broadcast
   marginal (a marginal table broadcast to every `(age, sex)` cell because no
   conditional source exists).

## Key cross-country differences captured

- **Sweden** is the data-richest: real `income_source` conditional table, and
  `employment_type` built from two tables (attachment × hours) at true `(age, sex)` cells.
- **Norway** drops `income_source` (no SSB v2 table); `employment_type` and
  `birth_country_detail` are sex/age-agnostic marginals broadcast to every cell;
  `birth_location` is derived as population − immigrants (2 API calls).
- **Italy** is dual-client (Eurostat demographics + ISTAT SDMX labour/income); has no
  `income_source` step at all; `employment_status` is binary (Employed / Not Employed,
  rate-derived); 20 NUTS2 regions with a `demo_r_d2jan` fallback.

Source modules: `src/population_synth/population/{sweden,norway,italy}/{constants,fetch_service,parsers,sample_service}.py`
and the shared layer `population/{data,helpers,income_class}.py`.

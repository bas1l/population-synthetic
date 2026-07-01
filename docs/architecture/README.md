# Architecture — Home

> **Wiki:** **Home** · [Sub-packages](sub-packages.md) · [Comparison & mapping](comparison-mapping.md) ·
> [Design principles](design-principles.md) · [Axis composition](axis-composition.md) ·
> [Configuration](configuration.md) · [Commands](commands.md)

The reference for how **population-synth** is put together. This area is organised as a small
**wiki**: `CLAUDE.md` at the repo root is the lean hub (overview, quick-start, hard-rule
one-liners, secrets); the pages here hold the depth it links to. Every page opens with the
navigation line above and closes with a *See also* section — start here, then follow the links.

**population-synth** is a standalone extraction from the `anxiety-synthetic` monorepo providing
three capabilities: **population generation** (real demographic distributions from national
statistical APIs, sampled via conditional chained sampling), **identity generation** (LLM-based
persona creation), and **population comparison** (statistical evaluation of any two populations).

## Documents in this set

| File | What it covers |
|------|----------------|
| [`sub-packages.md`](sub-packages.md) | Full per-package breakdown of `src/population_synth/` (`population`, `identity`, `comparison`, `gui`, `llm_metrics`, `utils`, `clients`) plus `_paths.py` path resolution. |
| [`comparison-mapping.md`](comparison-mapping.md) | The densest subsystem: the unified symmetric mapping config, the `mapping_engine` tiered resolver, and the reference/synthetic mapper hierarchies. |
| [`design-principles.md`](design-principles.md) | Recurring patterns **and** the hard behavioral rules (no synthetic distributions, config-is-the-single-source-of-truth, full comparison output) in full — the rationale behind the one-liners in `CLAUDE.md`. |
| [`axis-composition.md`](axis-composition.md) | How `--model-id` / `--strategy-id` / `--country-id` compose a run manifest from four YAML layers, and the resulting output slug. |
| [`configuration.md`](configuration.md) | The `config/` inventory: what each config tree holds and which code reads it. |
| [`commands.md`](commands.md) | The exhaustive command catalog (install, generate, map, compare, analyse, GUI, lint, test). |

## Related architecture references (already in this directory)

| File | What it covers |
|------|----------------|
| [`gui-dag-launcher-reference.md`](gui-dag-launcher-reference.md) | Standalone reference for the GUI-driven DAG pipeline launcher (generic, for external teams). |
| [`dag-graph-view-reference.md`](dag-graph-view-reference.md) | The DAG graph-view widget reference. |
| [`diagrams/`](diagrams/) | Architecture and strategy diagrams (database, synthetic strategies). |

## See also

- [`../database_mapper_philosophy.md`](../database_mapper_philosophy.md) — *why* the reference
  mapper exists and the principle that governs it.
- [`../scb_population_and_comparison.md`](../scb_population_and_comparison.md) — end-to-end SCB
  pipeline and comparison design.
- [`../istat_population_data_sources.md`](../istat_population_data_sources.md) — Italy field-by-field
  API source matrix.
- [`../code-standards/`](../code-standards/) and [`../data-pipeline-engineering/`](../data-pipeline-engineering/)
  — repository-agnostic engineering-standards wiki sets.
- [`../development/`](../development/) — in-progress development notes, plans, and the
  [identity-generation debugging runbook](../development/debugging-identity-generation.md).

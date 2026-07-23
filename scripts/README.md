# scripts/

Command-line entry points for the project. Every script is a thin CLI wrapper —
all real logic lives in the `population_synthetic.*` package (installed via
`pip install -e .`). Scripts are run by path, e.g.
`python scripts/generate/generate_scb_population.py --n 1000`.

## Layout

### `generate/` — produce populations and identities
| Script | Purpose |
| --- | --- |
| `generate_scb_population.py` | Sample a Swedish population from live SCB PxWeb data |
| `generate_ssb_population.py` | Sample a Norwegian population from live SSB PxWebApi data |
| `generate_istat_population.py` | Sample an Italian population from ISTAT SDMX + Eurostat |
| `generate_real_population.py` | Dispatcher: `--source scb\|ssb` runs the matching generator above |
| `generate_identity.py` | Generate a single LLM persona identity (manifest / axis IDs / explicit CLI) |
| `generate_identities_parallel.py` | Generate N identities in parallel with retry rounds |
| `extract_population_from_pipeline.py` | Extract demographic profiles from pipeline `identity.json` files into a population JSON |
| `scheduled_generate.py` | Clock-time scheduler that launches `generate_identities_parallel.py` |

### `analyze/` — compare and evaluate
| Script | Purpose |
| --- | --- |
| `score_fidelity.py` | Generic two-file statistical comparison |
| `score_fidelity_sweden.py` | Compare LLM pipeline output against an SCB real population |
| `score_fidelity_italy.py` | Compare LLM pipeline output against an ISTAT real population |
| `score_fidelity_all.py` | Batch comparison over every model × strategy × country |
| `compare_real_countries.py` | Cross-country marginals (Sweden vs Norway vs Italy) |
| `summarize_generation_metadata.py` | The single LLM-metrics task: per country × model × method(strategy) cost/token/latency/retry summaries + per-combo deep diagnostics + cross-factor significance (Kruskal-Wallis + Dunn) |

### `dev/` — exploratory / one-off tooling
| Script | Purpose |
| --- | --- |
| `prototype_istat_api.py` | Probe ISTAT/Eurostat SDMX APIs; cache raw responses |
| `test_istat_discovery.py` | Systematic discovery of working ISTAT dataflows (not a pytest test) |
| `benchmark_claude_latency.py` | Benchmark one-shot vs persistent Claude CLI subprocess latency |

### Root
- `launch_gui.py` — launches the primary Flow Runner GUI (`python -m population_synthetic.gui.main`).

## Pipeline chains

- **Generate → evaluate population quality:**
  `generate/generate_identities_parallel.py` → `analyze/score_fidelity_{sweden,italy}.py`
  (or `analyze/score_fidelity_all.py` for the full matrix).
- **Analyze LLM-call behaviour across runs:**
  `analyze/summarize_generation_metadata.py` (one command over `01_Raw` emits the enriched
  per-country summary — cost, means±spread, distribution, significance, deep diagnostics).

These are standalone CLIs, not an importable package — there is intentionally no
`__init__.py` here.

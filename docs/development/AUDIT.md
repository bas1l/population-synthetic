# Audit: code, configs and docs that exist only for older dataset versions

Date: 2026-11-24. Branch: `chore/latest-dataset-only` (off `dev`).

The latest dataset is:

- **Reference population ref-v3** (`real_swedish_02`): seed 42, n = 10,000; region drawn
  conditional on age group and sex; employment status drawn from the single register table
  `ArRegArbStatus` (no status-by-education merge); students aged 65 and over borrow the 55-64
  income mix.
- **LLM populations**: the `swedish_02` runs with the five `*_v2` strategies
  (`all_pick_v2`, `all_pick_dag_v2`, `all_generate_pick_v2`, `all_generate_evaluate_pick_v2`,
  `all_generate_evaluate_random_pick_v2`) and the 58 populations in `population_cap/_mapped`.

Decision per item: **delete**, **simplify** (the ref-v3 behaviour becomes the only behaviour),
**keep (generic)**, or **deferred** (needs the author's decision, not applied on this branch).

## Applied

| # | Item | Decision | What changed |
|---|---|---|---|
| 1 | `--no-merge-status-education` CLI option and the `merge_status_education` parameter of `FetchService.load_all`, `SampleService.sample_one`, `SampleService.sample_population` | simplify | Option and parameter removed; the single-table register path is the only path. |
| 2 | Merge code: `FetchService.fetch_employment_status`, the merge block of `sweden/parsers.py` (odds-multiplication, `parse_employment_status_combined` and helpers, about 330 lines), merge constants in `sweden/constants.py`, `PopulationDistributions.employment_status_by_edu` | delete | Removed. `ArbStatusUtbM` is no longer fetched. |
| 3 | Tests of the merge (`_combine_status_3cat`, `_expand_nilf`, end-to-end merge parser test and its fixtures) and the `employment_status_by_edu=None` fixture argument | delete | Covered only the deleted behaviour. |
| 4 | `scripts/generate/generate_scb_population.py` defaults (n = 100, random seed) | simplify | Defaults are n = 10,000 and seed 42, so a plain run reproduces ref-v3. |
| 5 | `scripts/dev/draw_generation_dags.py`, `scripts/dev/embed_population_in_explorer.py` | simplify | Stop referring to the merge; employment is `(age, sex)`. |
| 6 | `config/synthetic/axes/countries/swedish.yaml` (earlier country axis: config 004, October reference) | delete | `swedish_02` is the only Swedish axis. |
| 7 | `config/synthetic/axes/countries/swedish_02.yaml` reference path (October 2026 file name) | simplify | Points to `scb_population_n10000_seed42_ref-v3.json`. |
| 8 | `swedish_02.README.md` (A/B arm against the baseline) | simplify | Rewritten to describe the one axis. |
| 9 | `simulation_config_003_swedish_flat.json`, `simulation_config_004_swedish_generative.json` (earlier prompts) | delete | Every reference now names config 006; its README is rewritten without the baseline comparison. |
| 10 | 39 frozen seed manifests `config/synthetic/manifests/identity_manifest_0NN_*.yaml` (earlier runs on config 004 and v1 strategies; contained machine paths) | delete | Removed. |
| 11 | `docs/reference/scb-pxweb-catalog/employment-status-merge-derivation.md` | delete | Spec of deleted code; links in the catalog README and `scb-source-audit.md` reworded. |
| 12 | `docs/swedish_mapping_fix_2026-05-29.md`, `swedish_mapping_fix_2026-06-29.md`, `swedish_model_state_and_mapping_2026-06-29.md`, `swedish_persona_matrix_2026-05-29.md` | delete | Dated snapshots of earlier runs and mapping states. Links from the playbook removed. |
| 13 | `income-source-student-65plus-fallback.md`, `docs/architecture/diagrams/real/README.md`, a comment in `sample_service.py` | simplify | Reworded: no "merge ON/OFF" case. |
| 14 | `README.md`, `CLAUDE.md`, `docs/architecture/commands.md` | simplify | Generator defaults, `swedish_02`, `*_v2` strategies, no manifests, no config 004. |
| 15 | `scripts/dev/audit_persona_realism.py`, `docs/scb_sweden_category_power_analysis.md` reference file name (July merge reference) | simplify | Name points to the ref-v3 file. The numbers inside the power-analysis document were computed on the July reference and are not recomputed. |

## Kept (generic)

- Norway (SSB) and Italy (ISTAT) generators, mappers, tests and docs.
- Strategy family and `version` machinery (`_families.yaml`, version sort and filter): it is how
  `*_v2` strategies are selected; it is not tied to one dataset.
- Mapper and scoring factories keyed by country type (`swedish`, `swedish_02` aliases).
- The `real_swedish` labels in test fixtures (arbitrary labels, not data).
- The `scripts/analyze/*` pipeline stages, the GUI and the analysis packages.
- `docs/development/decisions/*` (dated decision records, not instructions).

## Deferred: needs the author's decision

| Item | Why not applied | Suggested action |
|---|---|---|
| The five v1 strategy YAMLs (`all_pick`, `all_pick_dag`, `all_generate_pick`, `all_generate_evaluate_pick`, `all_generate_evaluate_random_pick`) | Used as fixtures by `test_identity_generator_configurable`, `test_identity_generator_resume`, `test_ollama_preflight_cli`, `test_prompt_stability`, `test_axis_version_filter` and others; the version-filter tests need a v1 to filter. | Separate branch: migrate those tests to `*_v2`, then delete the v1 files. |
| `--manifest` mode (`load_manifest`, `generate_identity*.py`, `score_fidelity_sweden.py`, `score_fidelity_italy.py`) and the frozen-manifest section of `docs/architecture/axis-composition.md` | Removing the mode touches four CLIs and their tests. The manifests it loaded are deleted (item 10). | Remove the mode in one follow-up. |
| `docs/architecture/sweden-generation-explorer/` (3 MB page embedding the 2026-07-16 merge snapshot; `data.js` and `catalog-view.js` describe the merge) and `sweden_generation_dag.{dot,svg,png}` | Generated artefacts; regeneration needs the page's JS reworked. `embed_population_in_explorer.py` no longer produces the merge field, so the page would lose its education selector. | Regenerate the DAG files from `draw_generation_dags.py`; delete or rework the explorer. |
| Completed plans that describe the merge or the October reference (for example `scb-source-improvements-implementation.md`, `sweden-employment-status-by-age.md`) and pending plans naming the July reference file (`mapping-fixes-scb-audit.md`, `household-size-persons-unit.md`) | Historical plan records; deleting breaks links from other plans. | Archive or delete in bulk after the author has read them. |
| Figure-builder prototypes in `scripts/analyze/figures/fig2` that keep switches for earlier panel wording (`INCOME_MODE`, `REFV3_REGION_L2`) | Layout options of a gallery, not data paths. | Delete the unused options when the figures are final. |
| `config/gui/flows` default strategy selection | The test `test_flow_default_selects_exactly_the_highest_version_strategies` fails before and after this branch. | Review with the GUI owner. |

## Counts

Applied: delete 7 groups (items 2, 3, 6, 9, 10, 11, 12), simplify 8 groups (items 1, 4, 5, 7, 8, 13, 14, 15),
kept-generic 6 groups, deferred 6.

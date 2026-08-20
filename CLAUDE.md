# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository. It is a lean **hub**: the always-needed guardrails and quick-start live here; the
depth lives in the [architecture wiki](docs/architecture/README.md).

## Project Overview

**population-synthetic** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real demographic distributions from national statistical APIs (SCB for Sweden, SSB for Norway, ISTAT/Eurostat for Italy) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation via pluggable providers (Gemini, Claude CLI, OpenRouter) with configurable strategy mode
3. **Population Comparison** -- Statistical evaluation and visual comparison between any two population files

## Quick Start

Requires Python 3.10+. Install in editable mode (required for imports to work):

```bash
pip install -e ".[dev]"          # editable install + dev tools; add ".[gui]" for the PyQt5 Flow Runner GUI
pip install -e ".[analysis]"     # optional: scikit-learn backend for the C2ST multivariate metric (MMD fallback otherwise)

# Generate a Swedish population from live SCB data
python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Generate identities via axis composition (model × strategy × country)
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Fidelity scoring is two-stage: MAP first, then SCORE (scoring consumes the pre-mapped files)
python scripts/analyze/map_populations.py
python scripts/analyze/score_fidelity_sweden.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

python -m population_synthetic.gui.main   # GUI: config-driven Flow Runner (requires ".[gui]")
ruff check src/                       # lint (line-length 120, rules E/F/W/I)
pytest                                # full suite (sampling, mapping, fidelity, multivariate, comparison, workflow, generation_metadata)
pytest tests/test_sampling.py::test_name   # run a single test (testpaths=tests/ is set in pyproject.toml)
```

**Full command catalog → [Command reference](docs/architecture/commands.md)** (`docs/architecture/commands.md`).

## Import Convention

The project uses `src/` layout. The `pyproject.toml` configures `setuptools` to find packages under `src/`, so after `pip install -e .`, the `population_synthetic` namespace is available:

```python
from population_synthetic.generators.real.sweden.fetch_service import FetchService
from population_synthetic.clients.scb_client import SCBPxWebClient
from population_synthetic.generators.synthetic.factory_identity_generator import FactoryIdentityGenerator
```

All imports use the fully-qualified `population_synthetic.*` package namespace. Scripts in `scripts/` depend on the editable install.

## Core Invariants (hard rules)

These are enforced guardrails, not suggestions. Full rationale in
[Design principles](docs/architecture/design-principles.md) (`docs/architecture/design-principles.md`).

- **No synthetic distributions** -- Every probability distribution in population generation must come from a real statistical API response; no hardcoded probability tables, fallback distributions, or parametric approximations. If no API provides a field, **drop it** -- never invent values. (Structural constants like dataset IDs and label maps are fine.)
- **Config is the single source of truth** -- Attribute lists / axis order / category values / matcher rules / joint-coherence pairs / sex-harmonization maps live **only** in config (`config/mapping/{scb,istat}/`, `config/analysis/fidelity/*.json`). No in-code `attr or DEFAULT` fallback. Missing/empty/malformed config **fails loudly** (raise) -- never silently reverts to a baked-in list.
- **Full comparison output** -- A real-population comparison emits every artifact for each analyzed axis (`ComparisonScheme.attributes`): a bar chart per attribute, the TV-similarity radar, the JSON report (marginals + joint chi-squared + coherence), and the CSV marginals. Skip a chart only when the attribute has zero data in **both** populations. The analyzed axis is config-driven, not a fixed 15: a name listed under `deprecated_attributes` in a mapping tier's `_index.json` is still mapped/emitted into population data but excluded from analysis (Sweden deprecates `birth_location`, so it analyzes 14 axes; other countries keep their full axis set).
- **A strategy version is just another strategy** -- Each selectable strategy YAML declares `family` (one of the five generation methods) and an integer `version`; `config/synthetic/axes/strategies/_families.yaml` (`_`-prefixed so it is not discoverable as a strategy) declares the simplest-first family order. There are 10 selectable strategies: five families × v1 (17 categories) and v2 (14 categories -- v1 minus `birth_location`, `ethnicity_broad_global_approx`, `current_environment_type`, with `birth_country_detail` scheduled after `age` + `biological_sex`). The version is part of the id (`all_pick_dag_v2`), so each arm owns its own output slug. **Versioning is a selection-side concept only** -- it is visible when picking strategies in the GUI/CLI, and the analysis pipeline is version-unaware: method levels are keyed on the strategy *id*, so v1 and v2 are distinct levels that are never pooled, and a run may freely mix them (the only caveat is interpretive -- an ordered-trend test then runs along an axis interleaving complexity with version). `version` is read for **ordering only**, in `analysis/utils/axes.py::strategy_complexity_order(ids)` -- a function over config, **not** a Python constant -- keyed `(family_rank, version, id)` so each v2 sits beside its v1; unknown id or family raises.
- **A discarded model is still a model** -- A model axis YAML retires itself from the sweep with a top-level `discarded: true`; **an absent key means active** (a documented default -- the 15 live model files carry no key, never `discarded: false`), and a non-boolean value raises. Like `version`, it is a selection-side concept only: nothing downstream reads it, and a discarded model stays runnable if checked. The GUI's Global tab derives its `Active`/`Discarded` chip row from it (opening on `Active`), just as it derives the strategy `v{n}` chips from `version` (opening on the highest discovered version) -- both defaults come from config, never a literal. Filtering is view-only and retaining (`visible = matches(chips) OR isChecked()`), so a default can never hide something a flow selects. See [Axis composition](docs/architecture/axis-composition.md).
- **Strategy × country compatibility** -- A pair is valid iff the strategy's categories cover the country's required raw keys (mapping `_index.json` attributes **minus** `deprecated_attributes`, `age_group`→`age`). Sweden requires 14 keys **without** `birth_location`; Italy requires 14 **with** it, so **v2 is Sweden-only**. Enforced pre-generation by `scripts/generate/generate_identities_parallel.py::_assert_strategy_covers_country` on the axis-composition path (`--model-id`/`--strategy-id`/`--country-id`); `--manifest` and explicit `--config`/`--strategy` carry no country id and are unchecked.
- **Generation is crash-safe and resumable** -- The process may die at any instruction (the GUI's Abort is `taskkill /F /T`), so every durable write is atomic (tmp + `fsync` + `os.replace`) and a persona checkpoints after **every** resolved category into `identity.partial.json`. Re-running the same command resumes: a *complete* persona (parses, flat, every category in this run's resolved order present and non-empty -- not merely "the file exists") is skipped, an unfinished one continues from its checkpoint, and a checkpoint written under a different strategy/schema/model/category-order fingerprint is discarded rather than spliced. **`--force` is the only thing that discards a checkpoint** -- a retry round deliberately keeps it. There is **no `--resume` flag and none may be added**: resuming is the default. `llm_interactions.jsonl` is truncated **iff** the checkpoint is discarded, which is what keeps `(persona_id, call_index)` unique without any downstream dedupe. No signal handler -- explicitly rejected, it cannot help against `taskkill /F` and would be a second, weaker recovery path. See [Aborted and resumed runs](docs/development/aborted-and-resumed-runs.md).
- **Fail-fast** -- Raise loudly on unexpected or malformed input rather than silently defaulting.

## Architecture

`src/` layout; the `population_synthetic` namespace holds the two data producers under
`generators/` -- `generators/real/` (per-country data layers over a shared parent) and
`generators/synthetic/` (LLM persona generation) -- plus `analysis/` (the
post-generation family, one subpackage per process: `validate_raw/` the analysis-DAG **root** —
an atomistic per-combo raw-completeness check (per persona: `identity.json` present + every
config-derived category populated) writing one CSV per combo; `mapping/` raw -> canonical schema
(two tiers, selected per country by the axis YAML `parameters.mappings`: a **native**
within-country high-fidelity tier — `config/mapping/scb_native`, the default for Sweden —
and a coarser, cross-country **global** tier — `config/mapping/scb` — whose collapse is
deferred/design-only; see [Comparison & mapping](docs/architecture/comparison-mapping.md)),
`validate_mapped/` an atomistic per-combo check writing one CSV per combo (row per mapped persona:
which canonical fields are left as the `__UNMAPPED__` sentinel), `population_cap/` the validation
gate's final stage — intersects the two validity CSVs to the clean persona ids, enforces the
**full-N rule** on them (a combination with fewer than `--n` clean personas is *excluded*: it is
withdrawn — no mirror, no capped mapped file, any earlier ones deleted — logged at WARNING, recorded
in `population_cap/_index.json`, and exits 0, so it is simply absent downstream), then seeded-caps
`--n` of them, copies the selected `persona_*` dirs (plus combo logs/metadata) into the capped
mirror at `03_Analysis/population_cap/{slug}/` (telemetry for `generation_metadata`) and writes the
capped mapped file + copied real reference under `.../population_cap/_mapped/` (read by every
mapped-file analysis via `analysis/utils/capped_source.resolve_mapped_dir`, fail-fast, no `mapping/`
fallback), `validation_attrition/` the gate's own report on what it discarded — per combination the
five-stage funnel (generated -> raw-valid -> mapped-valid -> clean -> selected) read back out of
`population_cap/_index.json` and the two validator roll-ups, plus `retention_rate` (clean/generated)
and `generation_multiplier` (generated/clean, personas generated per *usable* persona, deliberately
not denominated on `selected`, which is zero for every withdrawal); it validates nothing and caps
nothing, and its row grain is **every** combination the gate recorded **including the withdrawn
ones**, which makes it the only artifact in the layer on which an excluded combination appears at
all (one tidy CSV + JSON per country, a normalised per-combination funnel and a model × method
validation-survival grid drawing four cell states without collapsing any of them),
`fidelity/` two-stage map -> score statistical scoring + charts (synthetic vs real), `multivariate_fidelity/` standalone
multivariate fidelity (recomputes the `multivariate` block over the mapped populations into
its own `03_Analysis/multivariate_fidelity/` folder), `model_ranking/` cross-model
ranking of the fidelity reports (models × strategies per country), `method_significance/`
per-category significance of the generation method vs model on TV fidelity (Page's L / Friedman /
Nemenyi CD + a mixed-model interaction, categories as blocks; needs the `[analysis]` extra),
`real_population_stats/` publication-ready per-category reference figures + proportion CSVs for the
real (API-sourced) population only, one country at a time, `generation_metadata/` the single
LLM-metrics task — per country × model × method(strategy) mean/spread(median/q1/q3)/n of the
per-persona generation cost (wall-clock time, input/output/total tokens, LLM calls, retry & error
rates, latency p95/max, success rate, estimated USD cost from `config/analysis/model_pricing.yaml`)
plus per-combo deep diagnostics and per-country cross-factor significance (Kruskal-Wallis + Dunn/Holm
across the model and method factors), read from the LLM-call telemetry of the **capped mirror**
(`03_Analysis/population_cap/`, produced by `population_cap`), not `01_Raw` directly,
`cost_efficiency/` the accuracy-vs-cost join — pairs `model_ranking`'s TV fidelity with the same
per-call LLM telemetry, but totalled over the **full generated pool in `01_Raw`** rather than over
the capped mirror, because the discarded personas were paid for: the two bases differ by up to 4.8×
on the live grid and the gap is widest exactly where retention is worst, so a capped figure flatters
the models that wasted the most tokens. The basis is a CSV column and is printed on the figure; the
join key is the run slug reconstructed from `generation_metadata`'s slug-less `model` + `method`
columns through `manifest_loader.axis_slug` and verified on every read against the slug
`model_ranking` publishes for the same pair (an unmatched key on either side, or an empty join,
raises); the output row set is the attrition set **minus** the withdrawals, each withdrawal instead
reported with the money it cost and the personas it kept; and **no composite score** is computed —
about a third of the model axis is unmetered (priced `{in: 0, out: 0}`, the local `ollama_*` models)
and unmetered is not free, so the flag travels as a data column and the scatter draws those models
in a labelled zero-cost band on a symlog x-axis,
`persona_realism/` an LLM-as-judge coherence task — judges each individual mapped persona N cold
rounds (`can_exist` binary + `typicality` 0-10 ordinal + severity-tagged clash issues) and reduces
round → persona → combination into **that combination's own** impossibility rate (bootstrap CI),
typicality dispersion, and judge self-reliability metric (ICC / Krippendorff's α — self-consistency,
**not** validity; the config-driven hard-rules subset is the only validity anchor). It is **strictly
per-combination**: it emits no field that depends on another unit, so its artifacts are
byte-reproducible in isolation and order-independent, and the SCB real population is enumerated as
an **ordinary competitor** `real_{country}` with no reference role; judge model + params
config-driven in `config/analysis/persona_realism/`, cost via `model_pricing.yaml`,
`realism_ranking/` the cross-combination half — consumes **two** tidy CSV contracts, the per-persona
`{combo}_personas.csv` (`analysis/utils/realism_csv.py`) and the per-clash `{combo}_clashes.csv`
(`analysis/utils/realism_clash_csv.py`, one row per persona × round × sorted attribute pair ×
severity with that persona's category values, independently versioned and reconciled against its
sibling at read time) — and owns every cross-unit claim with **no
LLM work at all**: Axis A ranks impossibility rate with SCB as an ordinary ranked competitor (lower
is better for everyone — so "is the chain-sampled population itself incoherent?" is asked, not
assumed), Axis B contrasts typicality dispersion against SCB **as the target** (near zero is better;
the failure mode guarded against is mode collapse), plus Holm-corrected SCB contrasts with effect
sizes, Kruskal-Wallis + Dunn/Holm on the model and method factors (SCB held out) and a logit mixed
model on `can_exist`; alongside them a **reporting-only** severity dimension — one prevalence heatmap
per level, the driver attribution that says what clashed in each cell (attribute pairs, and the
category pairs beneath them, over the heatmap's own denominator; counts are personas and are
non-additive, S1 is never a defect), *and* one `severity_pair_summary_s{3,2,1}` figure per level
ranking those pairs country-wide, computed from the **full** per-clash series rather than from the
per-cell-truncated driver tables and drawing SCB as its own series over its own denominator rather
than pooling it into the bars; beside those a second **reporting-only** dimension, the **typicality
axis** — the same per-persona judge scores Axis B turns into a distance, read *self-contained*
instead: one statistic per competitor computed from that competitor's own scores alone
(`analysis/utils/ordinal.py`, default Berry-Mielke IOV, ordinal-valid, `--typicality-metric mean`
the interval-assuming alternative whose caveat then travels as a column on every row), over the
`can_exist`-survivor denominator that is never `n_personas` (both counts on every row), carrying
`"direction": null` because the optimum is interior — direction enters only at render time as a
**signed distance to SCB's own value**, printed in every cell and ruled onto the colourbar, both
dropped with a printed reason when SCB is absent. Every heatmap in the analysis layer, this one
included, draws on the single house ramp in `analysis/utils/palette.py` (`inferno`, matching the
published manuscript tables), which orders cells by **magnitude only**: a two-sided quantity must
therefore carry its side in the annotations, never in the hue — so it feeds no ranking, no contrast
and no test and does **not** replace
`axis_b.dispersion_contrast`, which remains the only *tested* SCB typicality contrast; it gates on
completeness and on one judge model / prompt hash across the consumption set, plus **either** one
`n_rounds` **or** an explicit `--rounds N` cap that re-derives every competitor from its
`persona_realism` verdict cache over its first N rounds (zero LLM calls, nothing written upstream)
and turns the round count into a per-persona **capacity** check — a persona holding fewer than N
fails the run rather than being ranked short — with a blank `--rounds` on a set differing on
`n_rounds` alone doing the same at the shallowest cached depth, loudly; which of the three it was
travels as `provenance.n_rounds_source` (`report` | `cap` | `auto`),
and `utils/` cross-process shared infra), plus `gui/`, `clients/`, and a
top-level `utils/`. The full breakdown and the design patterns live in the wiki:

**Analysis registry (single source of truth for the analysis layer):**
`config/analysis/analysis_registry.yaml` (+ its accessor `analysis/utils/registry.py`) maps each
analysis process's **canonical id** → {label, description, output folder, script, dispatch}, and is
consumed by BOTH the GUI workflow and the analysis scripts. The canonical id is simultaneously the
registry key, the GUI workflow task key, and the `03_Analysis/` output-folder name, so those three
can never drift. Scripts resolve their output dir via `analysis_output_dir(id, base)` — no hardcoded
`03_Analysis`/folder literals (the sole `"03_Analysis"` definition lives in `registry.py`). The map
stage folder was renamed `mapped/` → `mapping/`; readers pass `for_read=True` to transparently fall
back to any legacy on-disk `mapped/` (deprecation-logged) until re-mapped. The analysis DAG is a
validation gate: `validate_raw` (**root**) → `mapping` (reads the full `01_Raw` pool) →
`validate_mapped` → `population_cap` → every other process. `population_cap` intersects the two
per-combo validity CSVs and returns a per-combination verdict, not merely a cap: reaching `--n`
clean personas materializes both the capped persona-dir mirror and
`03_Analysis/population_cap/_mapped/`, while falling short of it excludes the combination outright —
no capped outputs at all, and its `_mapped/_index.json` entry carries `skipped: true` + a
`skip_reason`, the predicate every mapped-file consumer already honours, so `--n` is a real
invariant rather than a ceiling; `generation_metadata` reads the
mirror's telemetry via `analysis/utils/capped_source.py` and the mapped-file consumers read
`_mapped/` via `resolve_mapped_dir` (fail-fast, no `01_Raw`/`mapping/` fallback). `validation_attrition`
hangs directly off the gate (`depends_on: [population_cap]`) and re-reads what it wrote, so it is
the one process whose row grain still includes the combinations the full-N rule withdrew. Two
processes are chained further still — the only analysis nodes whose upstreams are other analysis
nodes rather than the gate: `realism_ranking` declares `depends_on: [persona_realism]`, and
`cost_efficiency` declares `depends_on: [model_ranking, generation_metadata, validation_attrition]`.
That third edge is why `generation_metadata` is `enabled: true` in the workflow — a disabled task
never enters `completed_tasks`, so every dependent would sit at `SKIPPED_DEP` and never fire; an
operator who has already run it ticks `bypass` on that node rather than disabling it. A workflow task's
per-node **`bypass`** flag is GUI-only orchestration that is invisible to every script and emits no
CLI flag: it runs nothing yet still unlocks the dependents, asserting with **zero** verification
that the task's outputs are already on disk — so it is confirmed by an unskippable pre-run modal.

| Topic | Page |
|-------|------|
| Per-package breakdown + path resolution | [Sub-packages](docs/architecture/sub-packages.md) |
| Two-stage map -> compare flow + mapping config + mapper hierarchies | [Comparison & mapping](docs/architecture/comparison-mapping.md) |
| Design patterns + hard-rule rationale | [Design principles](docs/architecture/design-principles.md) |
| Axis composition (model × strategy × country) | [Axis composition](docs/architecture/axis-composition.md) |
| `config/` inventory | [Configuration](docs/architecture/configuration.md) |
| Command catalog | [Commands](docs/architecture/commands.md) |
| Wiki home / index | [Architecture home](docs/architecture/README.md) |

## Environment & Secrets

- `GEMINI_API_KEY` environment variable required for identity generation with `--provider gemini` (raises `ValueError` if missing)
- `--provider claude` requires the `claude` CLI on PATH; raises `RuntimeError` at construction if not found; no extra API key needed (Claude Code manages its own auth)
- `OPENROUTER_API_KEY` environment variable required for identity generation with `--provider openrouter` (raises `ValueError` if missing)
- `--provider ollama` needs no API key, but it **does** need an endpoint: select one with `--ollama-host <id>` from the registry at `config/synthetic/ollama_hosts.yaml` (omitted → that file's `default_host`). There is no default base URL in code and no `OLLAMA_BASE_URL` env read — both were removed, since a silent fallback dispatches a whole sweep to the wrong GPU while the outputs look normal. `--base-url` remains as an explicit ad-hoc override. Worker counts are per (model × host), declared in each `ollama_*` axis file's `parameters.parallel.workers` map; an unsupported (host, model) pair raises before any persona is generated. See [Ollama hosts](docs/ollama_server_models.md).
- `--ollama-reconfigure` (off by default on the CLI, **on by default in the GUI flow**) adds a once-per-invocation pre-flight that sets the selected host's `OLLAMA_NUM_PARALLEL` to the run's resolved worker count via that host's optional `control_url` (`:11435`), then warms the model and gates on the server serving again. **A run may therefore restart the host's Ollama container**, evicting the loaded model and killing another user's in-flight request — accepted deliberately, and bounded by the skip check (a server already at the requested value is read and left untouched) and by the flag being opt-in. Never fatal: the outcome is one of `already_correct` / `applied` / `mismatch` / `failed` / `no_control_url` and is recorded in `run_metadata.json` with the `observed` value read back from `/status` (never the requested one).
- Population generation (SCB/SSB scripts) does not require any API keys

## Documentation

Design and audit notes worth consulting before non-trivial changes:

| Doc | What it covers |
|-----|----------------|
| [Architecture wiki](docs/architecture/README.md) | **Start here** — the architecture wiki (sub-packages, comparison/mapping, design principles, axis composition, config, commands). |
| [Debugging identity generation](docs/development/debugging-identity-generation.md) | Runbook for diagnosing a failed persona generation (locating run dirs, reading crash-surviving logs). |
| [Aborted and resumed runs](docs/development/aborted-and-resumed-runs.md) | The resume protocol: what each persona file means, the shared-lifecycle invariant, the five ordering constraints, and why there is no signal handler. |
| [gui Flow Runner](docs/development/gui.md) | The config-driven `gui` launcher: two-tier config, GUI-translates-YAML→CLI execution contract, and the workflow DAG chaining contract. |
| [SCB population & comparison](docs/scb_population_and_comparison.md) | End-to-end SCB pipeline and comparison design. |
| [Real mapper philosophy](docs/real_mapper_philosophy.md) | *Why* the real mapper exists and the principle governing it. |
| [SCB distribution analysis](docs/scb_population_distribution_analysis.md) (+ [verification](docs/scb_population_distribution_analysis_verification.md)) | Per-field distribution analysis. |
| [SCB comparison API-rooting audit](docs/audit_scb_comparison_api_rooting_2026-05-11.md) | Audit of comparison-vs-API field routing. |
| [SCB02 category-mapping rationale](docs/scb02_comparison_category_mapping_2026-05-11.md) | Category-mapping rationale. |
| [ISTAT population data sources](docs/istat_population_data_sources.md) | Italy field-by-field API source matrix, protocol details, sampling chain, known limitations. |
| [Code standards](docs/code-standards/README.md) · [Data-pipeline engineering](docs/data-pipeline-engineering/README.md) | Repository-agnostic engineering-standards wiki sets. |
| [Persona realism judge](docs/development/persona-realism-judge.md) | Operator guide for the two-task persona-realism pipeline: the per-combination judge, the `realism_ranking` aggregator, the two axes and their opposite directions, the reporting-only severity and typicality dimensions, and `--rewrite-artifacts` vs `--force`. |
| [Development notes](docs/development/) | In-progress development notes, plans, and `decisions/` (ADRs). |

# Persona Realism Judge (LLM-as-judge)

A short operator's guide to the `persona_realism` analysis process. **Design record:**
[`brainstorms/individual-persona-realism-judge.md`](brainstorms/individual-persona-realism-judge.md).
**Implementation record:** [`plans/active/persona-realism-judge.md`](plans/active/persona-realism-judge.md).

## What it measures

The `fidelity/`, `multivariate_fidelity/`, and `model_ranking/` tasks measure **distributional**
realism — whether a combination's marginals and (fetched) joints match the real Swedish population.
They cannot measure **individual** realism: whether a *single* persona hangs together as a believable
human. The two can disagree — SCB is distributionally perfect by construction (sampled from real
tables) yet its chained sampling does not condition on every attribute pair, so it can emit
internally-incoherent individuals (a 19-year-old with a doctorate); an LLM generator may skew the
marginals but rarely emit an incoherent individual. This task fills that gap.

Per persona (the bare mapped demographic tuple; Sweden's deprecated `birth_location` is excluded to
match `ComparisonScheme.attributes`, and `age` is shown to the judge as the bracketed `age_group`
derived on demand from the raw integer via the canonical `attr_value` accessor, matching the analyzed
scheme), the judge is called **N cold rounds** and returns two orthogonal axes plus a structured
clash list:

- **`can_exist`** — binary: can this attribute set describe one real person? False **only** on a hard
  biological/legal/temporal contradiction (severity S3), never for merely-unusual-but-possible.
- **`typicality`** — integer 0–10 ordinal, judged only when `can_exist` is true. 10 = modal person,
  0 = highly unusual yet still possible. It measures **commonness, not quality** — a low score is not
  a defect.
- **`issues`** — attribute pairs in tension, tagged S3 (hard contradiction) / S2 (near-impossible) /
  S1 (unusual-but-possible, reported not penalized).

Rounds reduce to personas reduce to combinations. Each combination (and **the SCB real reference,
judged as one more competitor**) gets a per-combination **impossibility rate** (bootstrap CI), a
**typicality dispersion** reported as distance from SCB's dispersion (Levene variance-equality test),
and a judge **self-reliability** metric (ICC / Krippendorff's α). The headline artifact is a 2-D map:
impossibility rate × typicality-dispersion-vs-SCB, every competitor as a point.

## How to run it

Two-stage — the judge reads the **mapped** populations, so map first:

```bash
python scripts/analyze/map_populations.py
python scripts/analyze/analyze_persona_realism.py --country swedish
```

CLI flags (`--help` is authoritative):

| Flag | Meaning |
|------|---------|
| `--country ID` / `--model ID` / `--strategy ID` / `--slug SLUG` | Repeatable combo filters (default: all). |
| `--country-id` / `--model-id` / `--strategy-id` | GUI `per_combo` singular aliases; fold into the plural filters. |
| `--output-base DIR` | Analysis-stage parent (default: `experiment_defaults.yaml` `output_base`). |
| `--force` | Re-judge personas and re-write artifacts (default: resume — skip a combo whose report exists and personas already cached). |
| `--workers N` | Override the config judge-call fan-out width. |
| `--sample N` | Override the config per-combo persona sample size. |
| `--rounds N` | Override the config judge rounds per persona (`n_rounds`; must be ≥ 1). |
| `--judge-model MODEL` | Override the config judge model (must be in `model_options`). |
| `--dpi N` | PNG resolution (default 200). |

Outputs land under `03_Analysis/persona_realism/` (resolved via
`analysis_output_dir("persona_realism", base)`): per-combo `raw/persona_XXXXX.json` verdict cache,
`llm_interactions.jsonl` telemetry, per-combo CSV/JSON + figures, and the cross-combo
`headline_map.png/.svg` + `run_report.json`.

### GUI headline-map limitation

The registry dispatch is `per_combo`, so a GUI node run judges **one combination per subprocess**
(that combo + its country's real reference — a valid 2-point map). The **full cross-combo headline
map** (every combination on one map) is a **CLI-batch capability**: run the script once with broad
filters so a single process enumerates every combo, e.g. `analyze_persona_realism.py --country
swedish`. A multi-country batch emits the map without a marked SCB reference marker (the `y==0`
reference is only set for a single-country run).

## Config knobs — `config/analysis/persona_realism/`

All judge behaviour is config-driven; a missing or malformed value **raises** (no silent default).

`judge.yaml`:

| Key | Purpose |
|-----|---------|
| `judge_model` | Raw string passed to `claude -p ... --model`; must match a row in `model_pricing.yaml`. Default `claude-sonnet-5` (best coherence-judge tier + low latency + cost). |
| `model_options` | GUI dropdown (Claude family). `judge_model` must be one of these; Fable-5 is the slowest/most-expensive selectable option. |
| `n_rounds` | Independent judge calls per persona (default 3). N≥2 is required for any reliability or per-persona SD. |
| `temperature` | Judge sampling temperature (default 0.0 — cold, for reproducibility). |
| `severity_weights` | Weight per severity when folding clashes into a per-persona clash score (S1 = 0). |
| `impossibility_severities` | Which severities force `can_exist=false` at aggregation (default `[S3]`). |
| `sample_size` | Personas judged per combination (nullable → all). Caps judge cost via seeded sampling. |
| `bootstrap` | `{iterations, seed, ci_level}` for the impossibility-rate CI (seed recorded in run metadata). |
| `reliability.typicality_level` | Krippendorff's-α measurement level for typicality: `ordinal` (default) or `interval`. `can_exist` reliability is always nominal (not configurable). |
| `workers` | Parallel judge-call fan-out (ThreadPool `max_workers`). |
| `timeout_seconds` | Per-call subprocess wall-clock timeout (default 600). Threaded into the `ClaudeCodeClient` the judge factory builds; 600 s is a generous ceiling that also covers the slowest *selectable* judge (a Fable/Opus single turn can run for minutes) if you select it — Sonnet, the default, finishes in seconds. The client's own 120 s default is too tight for the slow tiers and is raised only for the judge. |
| `prompt_template` | Path (relative to the config dir) to the system+user template. |

`judge_prompt.md` — the constraint-scaffolded system + user template (biological/legal/temporal
categories, anchored typicality exemplars, strict JSON output schema, explicit "unusual ≠ impossible"
guardrail).

`hard_rules.yaml` — config-driven deterministic `incompatible_pair` checks (see below).

## Reliability is self-consistency, not validity

The ICC / Krippendorff's α metric measures the judge's agreement **with itself** across the N rounds
— its precision/consistency, **not** its correctness. Internal validity is **not** established by it.
The only validity anchor is `hard_rules.yaml`: on a seeded subset the aggregation layer evaluates
those deterministic structural rules and compares their verdict to the judge's `can_exist`, reporting
a 2×2 confusion + agreement + recall-on-rule-impossibilities. Read the reliability number as "the
judge is repeatable", never as "the judge is right".

## Cost sizing

The judge issues roughly **N × personas × combinations** LLM calls (N = `n_rounds`, default 3), so a
full run over every combination is large. Controls:

- `sample_size` (or `--sample`) caps personas per combination via seeded sampling.
- `n_rounds` (or `--rounds`) is the N multiplier — lowering it cuts cost proportionally but N ≥ 2 is
  required for any reliability or per-persona SD number.
- `workers` (or `--workers`) sets the parallel fan-out width, and `timeout_seconds` bounds each call's
  wall clock; neither changes total cost, only wall-clock time and per-call failure behaviour.
- The per-persona `raw/` cache makes runs **resumable**: a re-run without `--force` skips personas
  already cached and skips a combo whose report already exists.
- Per-combo cost (tokens + USD) is priced from `config/analysis/model_pricing.yaml`; a missing
  pricing row for the judge model **raises** (fail-fast).
- **Cache tokens:** the judge prompt is prompt-cached, so the client sees `input_tokens ≈ 2` (the
  uncached remainder) while the bulk lands in cache. The cost chain additionally records
  `cache_read_tokens` / `cache_creation_tokens` and prices them against the base input rate via the
  `cache_multipliers: {read, write}` block in `model_pricing.yaml` (fail-fast if cache tokens are
  present but the block is absent).

**Resume/truncate cost-coverage caveat:** `llm_interactions.jsonl` is truncated each run, so a
resumed run's cost report covers only personas judged *that run*. The report carries a
`cost_coverage` marker — `judged_this_run` / `total_personas` and a `status` of `complete`
(log covers every cached persona), `partial` (resumed run — cost is under-counted), or `none`.
Treat a `partial` cost figure as a lower bound.

## Judge-model availability smoke-test

The default judge is `claude-sonnet-5` (best coherence-judge tier, low latency, low cost). Any judge
model's availability is **account-dependent** — smoke-test the one you intend to use before a large
run:

```bash
claude -p "ping" --model claude-sonnet-5 --output-format json
```

**If you select Fable** (`--judge-model claude-fable-5`, the slowest/most-expensive selectable
option) — smoke-test it too, since its availability is plan-dependent:

```bash
claude -p "ping" --model claude-fable-5 --output-format json
```

Fable/Opus single turns can run for **minutes** on hard personas, which is why `timeout_seconds`
defaults to 600 (a ceiling generous enough for the slow tiers if chosen; Sonnet finishes in seconds,
and the client's own 120 s default is raised only for the judge). A round that times out or errors
is recorded as a **failed** round — kept distinct from a judged "possible" verdict — and only failed
rounds are retried; the impossibility rate is gated on successful calls and the dropped count is
logged.

If a model does not resolve, pick another entry from `model_options` (`--judge-model
claude-opus-4-8` / `claude-haiku-4-5` / `claude-fable-5`); every dropdown model already has a
pricing row in `model_pricing.yaml`.

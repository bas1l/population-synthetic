# ADR: cost is measured over the generated pool, and the cost join key is reconstructed

**Date:** 2026-08-20
**Status:** Accepted
**Plan:** [`plans/active/validation-attrition-and-cost-efficiency-processes.md`](../plans/active/validation-attrition-and-cost-efficiency-processes.md)
**Supersedes:** the unresolved denominator question left open in
[`plans/archived/pipeline-model-method-cost-and-attrition-figures.md`](../plans/archived/pipeline-model-method-cost-and-attrition-figures.md)

Two load-bearing decisions came out of building `cost_efficiency`. Both are cheap to re-litigate and
expensive to get wrong a second time, because both look like implementation detail and are not: the
first fixes what population a published dollar figure describes, the second fixes how two artifacts
that name the same combination differently are matched.

---

## Decision 1 — cost is totalled over the full generated pool, never over the capped mirror

### Context

`generation_metadata` reads its telemetry from the capped mirror
(`generation_metadata/__init__.py` → `capped_source.resolve_stage_source(base)` →
`03_Analysis/population_cap/`), which by construction holds the `--n` personas each combination was
subsampled down to. That is correct for its own purpose — per-persona distributions of time, tokens
and latency, compared across combinations at equal N.

It is wrong for a cost figure. The discarded personas were paid for. On `swedish_02` the gap is not
a rounding artefact:

| Basis | Personas | Input tok | Output tok | Total USD |
|---|---|---|---|---|
| `01_Raw` generated pool | 549 | 6,581,464 | 103,294,407 | **27.2843** |
| capped mirror | 100 | 1,379,172 | 21,711,233 | **5.7346** |

(`swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`, priced
`{in: 0.065, out: 0.26}`.) A **4.758×** understatement — and the error is not random across the
grid. It is largest exactly where retention is worst, so a mirror-based figure **flatters the models
that wasted the most tokens**, inverting the purpose of the figure it appears on.

Two options were live. (a) Read the `01_Raw` telemetry directly. (b) Keep reading the mirror and
scale by the generation multiplier `generated / selected`.

### Decision

Option (a). `cost_efficiency/raw_cost.py` totals `llm_interactions.jsonl` over every `persona_*`
directory in `01_Raw/{slug}/`, prices it through `config/analysis/model_pricing.yaml`, and stamps
`cost_basis = "generated_pool_01_raw"` onto every record, every CSV row and the figure's caption, so
no consumer can print a cost without its denominator. `generation_metadata` is left exactly as it
is: the reader lives inside the consumer, not in the shipped process, so option (a)'s only stated
cost — modifying a shipped read contract — does not arise.

Option (b) is not merely less accurate. It is **uncomputable for the cases that matter most**: a
withdrawn combination has no capped mirror, so `generation_metadata` holds zero telemetry for it and
`selected = 0` makes the correction factor undefined. It would have silently omitted exactly the
seven combinations whose waste the figure exists to show.

### Consequences

- The correction factor option (b) would have applied is measurably wrong even where it is defined.
  On the case above the drawn personas cost **0.05735 USD** each against a pool average of
  **0.04970** — the keeps are ~15% *more* expensive than the discards, because a persona typically
  fails the mapped gate through a truncated generation and a truncated generation emits fewer output
  tokens. Option (b) would have over-corrected by that margin, in a direction correlated with
  retention. `generation_multiplier` is therefore carried on the cost row for interpretation only,
  read from the attrition contract rather than recomputed, and is explicitly **not** the correction.
- The arithmetic is cross-checked against the shipped process rather than merely asserted: summing
  this reader over only the 100 `selected_ids` from `population_cap/_index.json` reproduces
  `generation_metadata`'s `cost_mean × cost_n` to its published rounding (5.73457 vs 5.7346). Only
  the denominator differs, never the pricing.
- `raw_cost.py` re-implements the `model_pricing.yaml` parser instead of importing
  `generation_metadata.pricing`. That duplication is deliberate and was measured: importing any
  submodule of that package executes its `__init__`, which pulls `utils/capped_source` into
  `sys.modules` — putting the capped-mirror reader back into the import graph of the one module
  written to avoid it. The config file remains the single source of truth; only the parser is local,
  and a test asserts that importing `raw_cost` leaves `capped_source`, `generation_metadata` and
  `matplotlib` all absent from `sys.modules`.
- Reading the full pool re-opens a double-counting risk the mirror did not have, since an
  aborted-and-resumed run appends to `llm_interactions.jsonl`. The resume protocol's guarantee —
  the log is truncated iff the checkpoint is discarded, which keeps `(persona_id, call_index)`
  unique — is now **enforced** on read: a repeat raises, naming the persona and both files. Records
  with no `call_index` fall outside that assertion and are counted into `n_unkeyed_calls`, a field on
  the record, so the limit of the guard travels as data.
- Anything published from `generation_metadata`'s own `cost_*` columns still describes ~100 personas.
  The two processes answer different questions and their numbers are not interchangeable; the
  `cost_basis` column is what keeps that legible in a table that has travelled away from the code.

---

## Decision 2 — the join key is reconstructed from the axis vocabulary and verified, not added upstream

### Context

`cost_efficiency` joins three artifacts that identify a combination three different ways.
`validation_attrition`'s CSV and `model_ranking`'s CSV both publish the run `slug`;
`generation_metadata`'s per-country summary publishes `model` and `method` columns and **no slug** —
its grain is the (model × method) cell, and it has never needed one.

The obvious fix is to add a `slug` column to `generation_metadata`'s summary. It is also a change to
a shipped artifact's schema, for the benefit of one consumer that did not exist when it was written,
and it makes a producer carry a field only because a consumer exists — the coupling direction the
`persona_realism` split ADR was written to avoid.

The alternative — rebuilding `{country}_{strategy}_{model}` in the consumer — is a **reconstructed
join key**, which the data-pipeline guidance flags as a thing to be cautious about: the rule can
drift from the producer's, and when it does the failure is a silent mis-attribution rather than an
error.

### Decision

Reconstruct, through `generators/synthetic/manifest_loader.axis_slug` — the same function the
generation side uses to name the output directory, so there is one slug rule and the consumer does
not own a copy of it. Then **prove it on every read** rather than trusting it: the identical
reconstruction is applied to `model_ranking`'s rows, which carry the producer's own slug, and any
disagreement raises. Reconstructed keys are additionally asserted unique within each file, so the
join cannot silently degrade to many-to-one.

`generation_metadata` gains no column and learns nothing about `cost_efficiency`.

### Consequences

- The verification is a live proof executed against the real data on every run, not a unit test over
  a fixture that can drift from production. It is only possible because one of the three inputs
  publishes both spellings of the key; had none of them, adding the column upstream would have been
  the honest choice.
- Membership across the three inputs legitimately differs and is therefore **declared**, not
  inner-joined away: `validation_attrition` records every combination the gate saw including the
  withdrawals, while a withdrawn combination has neither a fidelity report nor a capped mirror. The
  output row set is *the attrition set minus the withdrawals* and must equal the other two row sets
  exactly — 65 − 7 = 58 = 58 = 58 on `swedish_02` — published as a `membership` block so the count is
  auditable rather than merely asserted. Four failure modes raise, each naming the key and both
  files: a survivor missing from either file, a scored combination the attrition CSV records as
  withdrawn, a scored combination absent from the attrition CSV, and an empty join — which would
  otherwise publish an empty cost figure that reads as a measured absence of cost.
- A withdrawn combination cannot be plotted, having no accuracy score, so it is reported rather than
  dropped: `withdrawn_combinations` carries its slug, reason, pool, clean count and money, and the
  totals appear in the figure's caption and on the driver's stdout. On `swedish_02` all seven are
  local models, so the withdrawals cost **0.00 USD** across 1,150 generated personas — GPU time, not
  money, and the artifact now says which.
- One integrity check came free from having both sides in hand and is kept:
  `generation_metadata`'s `has_token_data` is measured over a mirror copied out of the `01_Raw` pool,
  so `True` there with no telemetry in the pool is impossible and raises. The converse — the pool
  reports tokens and the mirror does not — is legitimate and does not.

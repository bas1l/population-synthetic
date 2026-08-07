# ADR: split `persona_realism` into a per-combination judge and a `realism_ranking` aggregator

**Date:** 2026-08-07
**Status:** Accepted
**Supersedes:** the single-task design recorded in
[`plans/active/persona-realism-judge.md`](../plans/active/persona-realism-judge.md)
**Plan:** [`plans/completed/split-persona-realism-ranking.md`](../plans/completed/split-persona-realism-ranking.md)

Two load-bearing decisions came out of this change. They are recorded together because the second
only became expressible once the first was made.

---

## Decision 1 — a per-unit task's output is order-independent

### Context

The LLM-as-judge task judged one combination, *and* compared it against the SCB reference, *and*
drew the cross-combination headline map, all inside one country loop. The loop judged
`real_{country}` first, held its reduction in memory, and threaded it into every synthetic
combination. Two fields of `{combo}.json` (`dispersion.distance_to_scb`,
`dispersion.variance_equality`) and five columns of `{combo}.csv` were computed from it.

A single combination's artefacts therefore could not be reproduced without first judging a
*different* combination. That is connascence of execution order between units — the strongest and
most distant coupling form. Its practical consequences: the registry dispatch is `per_combo`, so a
GUI run always produced a one-element cross-combination map; and nothing in the repo read
`realism_summary.csv`, `run_report.json`, or `headline_map.*` because they were only meaningful
after a CLI batch.

### Decision

`persona_realism` emits, for unit *U*, a deterministic function of *U*'s own inputs and the config.
It does not read, accumulate, or depend on the existence, content, or processing order of any other
unit. `03_Analysis/persona_realism/{country}/` contains combination directories and nothing else.

The seam is cut at an **on-disk contract**, not an in-memory hand-off: the judge writes
`{combo}_personas.csv` (one row per judged persona, schema in `analysis/utils/realism_csv.py`) and
the new `realism_ranking` task depends on that schema and on nothing inside the judge. Dependency
direction is one-way — the aggregator never imports the judge's reduction internals, and the judge
never learns that an aggregator exists.

Alternatives rejected: having the aggregator re-reduce the `persona_*.json` verdict caches (makes
`reduce.py` a shared dependency — the aggregator reaching into judge internals — and it would see
partial combination directories that have caches but no report); having it read only `{combo}.json`
(aggregate-only, so no rank-based test, no mixed model, no effect size — it kills the significance
half outright).

### Consequences

- Testable as two byte-identity properties, both pinned in `tests/`: one slug judged on an empty
  output base produces its complete artefact set, and judging A-then-B versus B-then-A produces
  identical bytes.
- The expensive LLM work is cached once and the statistical battery downstream can evolve
  independently. Re-running `realism_ranking` is free and touches no verdict cache.
- The file-backed seam needs its own gates, since a half-written combination now looks like a
  consumable one: a combination is consumed only if report + per-persona CSV + a row count matching
  `n_personas` all agree, and the whole consumption set must share one `judge_model` /
  `prompt_template_sha256` / `n_rounds` (read from stamped provenance, not from current config —
  ranking units judged by different judges measures the judges).
- `{combo}.json` and `{combo}.csv` changed schema. **No re-judging is required**: the verdict caches
  are untouched, and `analyze_persona_realism.py --rewrite-artifacts` rebuilds every derived file
  from the cache already on disk at zero LLM cost. `--force` must not be used for this — it
  truncates the caches and re-judges from scratch. That flag split is part of this decision, not an
  incidental convenience: the rewrite flag puts the runner in **plan-only** mode (roster resolved,
  no client constructed, no call made), so the guarantee holds structurally rather than depending on
  the operator matching `--rounds` to whatever round count happens to be cached.
- The country-level `headline_map.*`, `realism_summary.csv` and `run_report.json` under
  `persona_realism/{country}/` are orphans; delete them once `realism_ranking` has reproduced them.

---

## Decision 2 — SCB is a competitor on Axis A and the target on Axis B

### Context

`distance_to_scb`, and the headline map's pinned `y = 0` with a reference star for the real
population, encoded one claim into the measurement itself: *SCB is the origin; closer to SCB is
better*.

But the open research question is whether SCB-sampled personas are themselves internally incoherent.
Conditional chained sampling draws each attribute conditioned on a subset of the others and never
cross-references every pair, so it can emit a 19-year-old with a doctorate. A metric that measures
distance *from* SCB cannot answer a question *about* SCB — the design assumed the answer.

The opposite error was equally available. The design record
([`brainstorms/individual-persona-realism-judge.md`](../brainstorms/individual-persona-realism-judge.md))
establishes that the target for **typicality dispersion** was *matching* SCB, not maximising spread,
precisely because the observed LLM failure mode is mode collapse. Dropping `distance_to_scb`
wholesale would have inverted that axis: a mode-collapsed combination would have read as a success.

### Decision

The two axes get opposite treatments, and are named and documented separately everywhere they appear:

| Axis | Quantity | SCB's role | Direction |
|------|----------|-----------|-----------|
| **A — validity** | impossibility rate (`can_exist`) | ordinary ranked competitor | lower is better, for everyone including SCB |
| **B — coverage** | typicality dispersion (variance / entropy / tail coverage) | **the target to match** | `distance_to_scb` near zero is better |

Removing SCB-as-origin applies to **Axis A only**. `distance_to_scb` survives on Axis B, moved
downstream unchanged, and is an **absolute** distance so collapsing is penalised exactly as much as
over-spreading.

On Axis A, `real_{country}` is enumerated by the judge like any other combination (differing only in
its `real_sample_size` first-N prefix draw) and ranked like any other competitor. The ranking is
computable and correct whether it places first, last, or in the middle. On the headline map it is
one point among many, distinguishable by colour so a reader can find it — it sits at `y = 0` on Axis
B for the arithmetic reason that its distance to itself is zero, which is a fact about that axis's
definition rather than a claim about quality.

It is **held out** of the model-vs-method factor tests: it is not a model × method cell and would
unbalance the design. It enters those comparisons only through the pairwise contrasts.

### Consequences

- The hypothesis "SCB-sampled personas may be less realistic than LLM-generated ones" became
  testable rather than assumed-false by construction. If it is true, the real point simply sits to
  the right of the synthetic ones.
- The inversion risk on Axis B is real and permanent, so it is guarded in four places: the axis table
  above and in the ranking JSON's own `axis_definitions` block, the Definitions entry in the plan,
  a mode-collapsed fixture in `tests/test_realism_ranking_builder.py` asserting that a collapsed
  spread scores *badly* and symmetrically with an over-spread one, and this ADR.
- Axis B is skipped-with-a-reason (never silently omitted) when no real competitor has been judged;
  the Axis A ranking of the synthetic competitors still runs.

# 02 — Architecture Principles & Patterns for Staged Data Pipelines

This is the design checklist. It collects the patterns and principles that make
a batch analytics pipeline maintainable, testable, and correct — drawn from
software-architecture classics, the data-engineering literature, and research
software-engineering practice. Each section states the principle, why it
matters, and how to apply it. A consolidated review checklist closes the doc.

---

## 1. Pipe-and-Filter: the backbone

**Principle.** Decompose processing into a sequence of independent *filters*
connected by *pipes*. Each filter has a narrow, well-defined input/output
contract and does one transformation. Filters do not know about each other; they
know only their data contract.

**Why.** Composability, reuse, independent testability, and the option of
parallelism. A filter you can call in isolation is a filter you can unit-test in
isolation. This style is the canonical example in Garlan & Shaw's work on
architectural styles and is documented in full in POSA1 ("Pipes and Filters")
and Hohpe & Woolf's *Enterprise Integration Patterns*.

**How to apply.**

- Make each stage a function (or small module) with an explicit signature:
  `parse(path) -> records`, `join(a, b) -> enriched`, `aggregate(enriched) ->
  metrics`, `plot(metrics) -> paths`.
- The composition *is* the pipeline: `plot(aggregate(join(parse(x), parse(y))))`.
  Resist adding an orchestration framework until stages must cross process
  boundaries (see `01`, Axis 3).
- Keep filters **uniform** at their boundaries — prefer plain, serializable data
  (dicts, dataclasses, DataFrames) over passing live objects with behavior.

```
[parse]──pipe──▶[join]──pipe──▶[aggregate]──pipe──▶[test]──pipe──▶[visualize]
   ▲ file in                                                         ▼ files out
```

---

## 2. Separation of Concerns & Layering

**Principle.** Keep distinct responsibilities in distinct places. Dijkstra's
"separation of concerns" (EWD447) is the intellectual root: study one aspect at
a time. In a pipeline this means separating, at minimum:

- **I/O** (reading files, parsing) from **computation** (aggregation, stats)
  from **presentation** (charts, report serialization).
- **Configuration** from **logic**.
- **Orchestration** (the CLI / the run loop) from the **stages** it invokes.

**Why.** When parsing changes, computation shouldn't. When you add a chart type,
the statistics shouldn't move. Layering makes the dependency direction explicit
and one-way: orchestration depends on stages; stages depend on shared helpers;
nothing depends back upward.

**How to apply — a typical layering:**

| Layer | Responsibility | Depends on |
|-------|----------------|------------|
| Orchestration | CLI parsing, config load, batch loop, output paths | all below |
| Visualization | metrics/results → PNG/JSON/CSV | computation outputs (data only) |
| Statistical | hypothesis tests, corrections, effect sizes | numeric libs |
| Computation | aggregate, derive metrics | data contracts |
| Transformation | join/enrich/normalize | data contracts |
| I/O / Parsing | files → in-memory records | nothing project-specific |

Keep imports flowing one way down this table. A parser that imports the chart
module is a smell.

**Cohesion and coupling — the underlying metric.** Layering and separation of
concerns are really about the oldest maintainability rule (Stevens, Myers &
Constantine, 1974): **maximize cohesion *within* a stage, minimize coupling
*between* stages.** A stage with *functional cohesion* does one task on one kind
of data (a parser parses); a "utils" grab-bag of unrelated helpers has weak
*coincidental cohesion* and should be split. Between stages, prefer *data
coupling* — passing a small, explicit record — over reaching into another
module's globals (*common coupling*) or passing a flag that switches its
behavior (*control coupling*). The design rule that produces low coupling is
**information hiding** (Parnas, 1972): hide the decisions most likely to change
behind a stable interface, and decompose around *what varies*, not around the
processing steps. This — together with **SOLID** as a finer set of heuristics —
is treated in full in `05-code-craftsmanship-and-maintainability.md`; the
present document applies it at the stage/pipeline granularity.

---

## 3. Data Transfer Objects (DTOs) and explicit contracts

**Principle.** The data flowing between stages is an interface. Make it explicit
and, where it matters, typed.

**Why.** Stages coupled through a stable data contract can each change
internally without breaking the others. The contract is also where bugs hide —
a silently misspelled key or a type that's sometimes `int` and sometimes
`float` propagates downstream and corrupts a statistic.

**How to apply.**

- Use **frozen dataclasses** (or typed records) for structured, long-lived
  intermediate objects — they document the shape, are immutable, and compare by
  value. Good for "one record per unit/metric/spec".
- Plain dicts are fine for loose, schema-light streams (e.g. parsed log lines),
  but then **validate at the boundary** rather than trusting `.get()` with
  defaults everywhere — silent `None` fallbacks make malformed input
  undebuggable.
- Decide *once* whether a numeric field is int or float and preserve it through
  the pipeline (e.g. keep counts as `int` to avoid rounding artifacts).
- Consider a lightweight schema check (pydantic, `dataclasses` + a validator, or
  an explicit assert) at the entry to the computation layer. Fail loudly on
  contract violations rather than producing a quietly wrong number.

---

## 4. Purity, Statelessness, and Functional Data Engineering

**Principle.** Make stages pure functions of their inputs wherever possible: no
hidden global state, no in-place mutation of shared structures, deterministic
output for a given input. Maxime Beauchemin's "Functional Data Engineering"
articulates this for batch: **pure, idempotent tasks** operating on **immutable**
input partitions.

**Why.** Pure stages are trivially testable, trivially re-runnable, and safe to
parallelize. Mutation and shared state are the source of the "works the first
time, wrong the second time" class of bugs.

**How to apply.**

- A stage should *return* its result, not mutate its argument.
- Avoid module-level mutable state. Pass config in; return data out.
- Treat raw inputs as **immutable**. Never edit source artifacts in place;
  derive new outputs.
- Where you accumulate (e.g. grouping samples by key), build new structures
  (`defaultdict(list)` then summarize once) rather than mutating inputs.

---

## 5. Idempotency and Clean Re-runs

**Principle.** Running the pipeline twice on the same input must produce the same
output, and re-running a partially completed batch must not double-count or
corrupt. Idempotency (RFC 9110's definition: N identical executions ≡ one) is
what makes a batch pipeline safe to retry.

**Why.** Batch jobs fail halfway — disk fills, a parse errors, the machine
reboots. Idempotent stages let you just run it again. Non-idempotent stages
(appending to an output, incrementing a counter on disk) accumulate corruption
on retry.

**How to apply.**

- **Overwrite, don't append**, when materializing a stage's output for a given
  unit (Beauchemin's "immutable partitions, fully overwritten").
- Make "skip if already done" logic explicit and based on a complete-output
  marker, not a partial one.
- Ensure deterministic outputs (see `03` on seeds) so that re-running is a true
  no-op, not a source of drift.
- If a stage records "I processed message/unit X", dedupe on that id (the
  Idempotent Consumer pattern) so reprocessing is safe.

---

## 6. Provider / Strategy normalization

**Principle.** When inputs come in several shapes (multiple source formats,
multiple providers, multiple variants of a log line), normalize them to **one
canonical internal schema** at the boundary, then write the rest of the pipeline
against that single schema.

**Why.** Without normalization, every downstream stage grows conditional
branches for each input variant — the combinatorial mess that becomes a
"pipeline jungle". One normalization point keeps the core simple.

**How to apply.**

- A single parsing/adapter layer maps each input variant to the canonical
  record. Add a new variant by adding one adapter, touching nothing downstream
  (open/closed).
- The **Strategy** pattern fits selection-at-runtime (different parse strategy,
  different chart per data condition); a small **Factory** picks the strategy.
- Keep the canonical schema documented next to the adapter.

---

## 7. Configuration handling

**Principle.** Configuration is separate from code and resolved once, near the
edge. The Twelve-Factor App's config principle applies even to local batch
tools: behavior that varies (paths, thresholds, output layout) lives in config,
not in scattered literals.

**Why.** Centralized, override-able config makes runs reproducible and
parameterizable without code edits, and keeps the layers below it pure (they
receive resolved values, they don't read the environment themselves).

**How to apply.**

- Load config (e.g. a YAML file) **once** in the orchestration layer; derive
  defaults; allow CLI flags to override.
- Pass resolved values *down* into stages as plain arguments. Stages should not
  reach back out to read global config or the environment.
- No global mutable config singletons. They defeat testability and purity.

---

## 8. Error boundaries and fail-fast

**Principle.** Decide deliberately where errors are *fatal* and where they are
*tolerated*, and make both explicit. Default to **failing loudly** on unexpected
conditions rather than silently substituting a default.

**Why.** A statistical pipeline that silently swallows a malformed input and
emits a number is worse than one that crashes — the crash is debuggable, the
silent wrong number is not. But some degradation is legitimate (an optional
metric whose source data is genuinely absent).

**How to apply.**

- Missing *required* input → raise with context (which file, which field).
- Missing *optional* data → return an explicit, documented `None`/absent marker
  and make downstream code branch on it visibly (e.g. "skip this chart because
  the field has zero data in both inputs"), never a silent zero.
- Wrap low-level parse errors with the context that identifies the offending
  artifact, then re-raise.
- Avoid blanket `try/except: pass`. Catch the specific exception you can handle.

---

## 9. Visualization & reporting as a pure sink

**Principle.** Treat chart/report generation as a terminal, side-effecting sink
that takes finished data structures and writes files. Keep all computation
*upstream* of it; the visualizer should not compute statistics.

**Why.** Separating "decide the numbers" from "draw the numbers" lets you test
the numbers without rendering, and re-style charts without touching analysis.
It also surfaces a faithfulness requirement: charts must not silently drop data
the analysis produced.

**How to apply.**

- Each plotter takes a data structure and returns the path(s) it wrote; it
  checks its own preconditions and returns "nothing" when a chart genuinely
  doesn't apply (no data) — a clean conditional-inclusion strategy.
- Be aware of global state in plotting libraries (e.g. matplotlib's global
  figure registry / `pyplot`): create and **close** figures explicitly; this
  matters for memory and is not automatically thread-safe if you parallelize
  rendering. Prefer the non-interactive backend for headless/batch runs.
- Don't lose information needed to re-plot: if you persist results to JSON for
  later charting, persist the data the charts need, or accept that re-plotting
  requires recomputation.

---

## 10. Testing strategy

**Principle.** Each layer gets the kind of test it deserves; the pipeline as a
whole gets at least one end-to-end smoke test on a small fixture.

**Why.** Pure stages make unit tests cheap; the value is realized only if you
write them. Statistical code in particular needs tests against *known answers*
because a wrong formula still returns a plausible number.

**How to apply.**

- **Parsers / adapters:** table-driven tests mapping raw fixtures → expected
  canonical records, including malformed inputs that should raise.
- **Transformations / aggregations:** small hand-computed fixtures with known
  outputs.
- **Statistics:** test against values from an authoritative library or textbook
  example (see `03`); use approximate comparison for floats (`pytest.approx`,
  not `==`).
- **End-to-end:** run the whole pipeline on a tiny fixture directory and assert
  the expected artifacts appear and key numbers match.
- Tools: `pytest` (fixtures, parametrization, `approx`) is the de-facto standard.

---

## 11. Documentation & provenance

**Principle.** A future reader (often you) must be able to tell *how* an output
was produced and *from what*. Record provenance.

**Why.** Reproducibility and debuggability both depend on knowing the inputs,
versions, config, and code path behind any artifact. This is a recurring theme
in the research-software literature ("track how every result was produced").

**How to apply.**

- Persist a run-metadata record alongside outputs: inputs, config snapshot,
  tool/library versions, timestamps, and (for anything stochastic) the seed.
- Document each stage's contract where the code lives.
- Keep intermediate artifacts (the per-unit metrics records) so a result can be
  traced back without re-running everything.

---

## Review checklist

Use this when designing or reviewing a staged analytics pipeline.

**Structure**
- [ ] Is each stage an independently callable filter with an explicit
      input/output contract?
- [ ] Does the dependency direction flow one way (orchestration → stages →
      helpers)? Any upward imports?
- [ ] Is I/O separated from computation separated from presentation?

**Data contracts**
- [ ] Are structured intermediates typed (frozen dataclasses) or validated at
      the boundary?
- [ ] Are numeric types (int vs float) deliberate and stable end-to-end?
- [ ] Is there a single normalization point for multi-variant inputs?

**Correctness & robustness**
- [ ] Are stages pure / free of hidden mutable state?
- [ ] Is the pipeline idempotent — safe to re-run and to resume after partial
      failure (overwrite, not append)?
- [ ] Are required-vs-optional inputs handled distinctly (fail loud vs explicit
      absent), with no silent default substitution?
- [ ] Is anything stochastic seeded and recorded? (see `03`)

**Configuration & ops**
- [ ] Is config loaded once at the edge and passed down, with CLI overrides?
- [ ] Is provenance (inputs, versions, config, seed) recorded per run?

**Outputs**
- [ ] Does visualization only render, never compute?
- [ ] Are charts/reports faithful — no silently dropped data the analysis
      produced?
- [ ] Are plotting library global-state / threading hazards handled?

**Tests**
- [ ] Unit tests per layer, statistics tested against known answers with
      approximate float comparison, and at least one end-to-end smoke test?

---

## See also

- `01-system-classification.md` — naming the system these patterns serve.
- `03-statistical-and-scientific-software.md` — the analytics-specific
  reproducibility and method-correctness concerns.
- `05-code-craftsmanship-and-maintainability.md` — the same ideas at the
  code-inside-the-stage level: SOLID, cohesion/coupling, DRY/KISS/YAGNI,
  complexity, refactoring, code smells, technical debt.
- `04-reading-list.md` — sources: Garlan & Shaw and POSA1 (pipe-and-filter),
  Dijkstra EWD447 (separation of concerns), Beauchemin (functional data
  engineering / idempotency), RFC 9110 & Azure/MS patterns (idempotency),
  Twelve-Factor (config), Sculley et al. (pipeline-jungle / hidden debt),
  Kleppmann & Reis/Housley (foundations), Nelson & Viafore (SE for data code).

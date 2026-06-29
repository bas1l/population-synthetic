# 01 — System Classification: Naming What You Are Building

Before you can design or critique a data-processing system well, you have to
name it precisely. The label you choose ("it's an ETL job", "it's a streaming
service", "it's a reporting tool") carries a whole bundle of expectations about
latency, failure handling, state, and testing. Naming it wrong leads to
over-engineering (building stream infrastructure for a once-a-day batch) or
under-engineering (treating a statistical-analysis tool as a throwaway script).

This document gives you the axes to classify a staged data-processing /
analytics pipeline, with the trade-offs each choice implies.

---

## Axis 1 — Batch vs. Streaming

The single most important distinction.

| | **Batch** | **Streaming** |
|---|---|---|
| Input | Bounded dataset, known size, processed in one run | Unbounded, continuous, processed as it arrives |
| Trigger | Scheduled or manual ("run the analysis") | Event-driven, always-on |
| Latency | Minutes to hours; latency is acceptable | Milliseconds to seconds; latency is the point |
| State | Usually stateless per run; re-run from scratch | Stateful; windows, watermarks, checkpoints |
| Correctness model | Re-run produces the same answer | "Exactly-once" semantics are a hard problem |
| Canonical engines | MapReduce, Spark, plain Python/SQL scripts | Kafka Streams, Flink, Beam, Spark Structured Streaming |

**How to tell which you have:** Ask "does new data arrive while I'm processing,
and must I react to it immediately?" If the answer is no — you collect a set of
artifacts and then analyze them — you are building **batch**, and you should
*not* import streaming machinery (windowing, watermarks, checkpoint stores).

Most analysis-of-experiment-runs pipelines are batch: a run finishes, it writes
files, and later something reads all of those files and produces a report.

> **Lambda and Kappa architectures** are attempts to reconcile the two: Lambda
> (Marz, 2011) runs a batch layer and a speed layer in parallel; Kappa (Kreps,
> 2014) replaces both with a single replayable stream. You only need to know
> these exist when you genuinely have both low-latency *and* full-reprocessing
> requirements. A pure batch analytics tool needs neither.

---

## Axis 2 — ETL vs. ELT

Both move data from sources to a place where it can be analyzed. The difference
is *where the transformation happens* relative to loading.

- **ETL (Extract → Transform → Load):** transform in flight, in application
  code, then write the finished artifact. Classic for file-based pipelines where
  the "load" target is a report, a chart, or a curated JSON file. The transform
  logic lives in your code and is fully under your control and testable.
- **ELT (Extract → Load → Transform):** dump raw data into a warehouse/lake
  first, then transform *in* the warehouse (typically SQL/dbt). Favored when a
  powerful warehouse is the destination and many consumers transform the same
  raw data differently.

**How to tell which you have:** If your transformations are Python/pandas/NumPy
functions that produce a finished output file, you are doing **ETL**. If you are
loading raw rows into a database and writing SQL models on top, you are doing
**ELT**. A self-contained analytics pipeline that parses files and emits
charts/JSON is almost always ETL.

---

## Axis 3 — Pipe-and-Filter vs. DAG-Orchestrated

How the stages are wired together.

- **Pipe-and-filter (linear composition):** independent "filter" steps connected
  by "pipes", each taking the previous step's output as its input. Stages are
  pure-ish functions composed in sequence. This is the natural structure for a
  single analysis run: `parse → join → aggregate → compare → plot`. It needs no
  orchestration framework — function composition *is* the pipeline.
  *Canonical references:* Garlan & Shaw (architectural styles); POSA1 "Pipes and
  Filters"; the Unix pipe.
- **DAG orchestration:** stages are nodes in a directed acyclic graph, scheduled
  by an orchestrator (Airflow, Dagster, Prefect, Luigi) that handles
  dependencies, retries, backfills, and parallel fan-out. You need this when you
  have many interdependent jobs, scheduling, retries across process boundaries,
  and operational monitoring.

**How to tell which you need:** If the whole pipeline runs in one process and
finishes in one sitting, pipe-and-filter (plain function composition) is
correct and an orchestrator is overkill. Reach for a DAG orchestrator when
stages span machines/processes, must be scheduled, or must independently retry.
A useful middle ground: structure your code as pipe-and-filter *now* so that
each filter could later become an orchestrated task without rewrite.

---

## Axis 4 — What the system is *for*

The same plumbing serves different goals. Naming the goal sets the quality bar.

| Goal | Description | What "good" means |
|------|-------------|-------------------|
| **Ingestion / ETL** | Move and reshape data from sources to a usable form | Completeness, idempotency, schema stability |
| **Data warehousing** | Model data dimensionally for BI/reporting | Conformed dimensions, query performance (Kimball) |
| **Analytics / statistical pipeline** | Compute metrics and run hypothesis tests over collected data | **Statistical validity, reproducibility, correctness of methods** |
| **Reporting / visualization** | Turn metrics into charts and documents | Clarity, faithful representation, no silently dropped data |
| **ML / feature pipeline** | Produce features and train/serve models | Avoiding the "pipeline jungle" and hidden-debt anti-patterns (Sculley et al.) |

A system can be several at once. A common and important combination is an
**analytics + reporting pipeline**: it ingests raw run artifacts (ETL), computes
statistics (analytics), and emits charts/JSON/CSV (reporting). Its dominant
quality concern is *statistical and reproducible correctness*, not throughput —
which is why such systems borrow as much from **research software engineering**
as from data engineering. See `03-statistical-and-scientific-software.md`.

---

## Axis 5 — Single-run vs. Cross-run (the "two-level" pattern)

Analytics pipelines frequently have **two distinct entry points** operating at
different granularities:

1. **Per-unit analysis** — process one run/experiment/subject: parse its raw
   artifacts, join/enrich, aggregate into a metrics record, persist it.
2. **Cross-unit comparison** — load *many* per-unit metrics records and run
   statistical comparisons across them (group differences, ranking, significance
   testing).

This two-level structure is worth recognizing because it shapes the data
contract: the per-unit stage's output (often one JSON/record per unit) becomes
the cross-unit stage's *input*. Keeping that intermediate artifact stable,
self-describing, and file-backed is what lets the two levels evolve
independently and lets the expensive per-unit work be cached and reused.

---

## A worked classification

A typical "analyze experiment runs" tool classifies as:

> A **batch**, **ETL**-style, **pipe-and-filter** **analytics + reporting**
> pipeline with a **two-level** (per-run / cross-run) structure.

Each label is actionable:

- *Batch* → no streaming infrastructure; design for clean re-runs.
- *ETL* → transformations are testable code; own them.
- *Pipe-and-filter* → compose pure functions; no orchestrator until proven
  necessary.
- *Analytics + reporting* → statistical validity and reproducibility are the
  primary quality bar (see `03`).
- *Two-level* → invest in a stable, self-describing intermediate artifact.

Get the classification right and most architecture decisions follow from it.

---

## See also

- `02-architecture-principles-and-patterns.md` — how to build it well once
  classified.
- `03-statistical-and-scientific-software.md` — the analytics-specific bar.
- `04-reading-list.md` — sources for every concept named here (Kleppmann on
  batch vs stream; Reis & Housley on the lifecycle; Marz/Kreps on Lambda/Kappa;
  Garlan & Shaw and POSA1 on pipe-and-filter; Kimball on warehousing).

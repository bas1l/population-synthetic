# Data-Pipeline & Analytics-Software Engineering Guides

A self-contained set of **pipeline-agnostic** reference notes on how to design,
build, and reason about software that ingests raw run/experiment artifacts,
transforms them, computes statistics, and produces reports and charts.

These documents describe a *class* of system — staged batch data-processing and
statistical-analysis pipelines — rather than any one implementation. They are
meant to be read by anyone building or reviewing this kind of software, and to
serve as an onboarding reading list and a design checklist.

## What this class of system is

The systems covered here share a recognizable shape:

```
raw inputs ─▶ parse ─▶ join / enrich ─▶ aggregate ─▶ statistical test ─▶ visualize / report
   (files)    (DTOs)     (DTOs)          (metrics)      (verdicts)        (PNG / JSON / CSV)
```

This is the **pipe-and-filter** architectural style applied to **batch**
(not streaming) data, in the service of **scientific / statistical analysis**.
It overlaps three established disciplines:

- **Data engineering** — ingestion, transformation, ETL/ELT, orchestration.
- **Software architecture** — pipe-and-filter, dataflow, separation of concerns.
- **Research software engineering** — reproducibility, provenance, correctness
  of statistical methods.

## Documents in this set

| File | What it covers |
|------|----------------|
| [`01-system-classification.md`](01-system-classification.md) | A taxonomy for placing a system: batch vs stream, ETL vs ELT, pipe-and-filter vs DAG orchestration, analytics vs warehousing. How to name what you are building. |
| [`02-architecture-principles-and-patterns.md`](02-architecture-principles-and-patterns.md) | The core design patterns and principles: pipe-and-filter, separation of concerns, idempotency, DTOs, layering, config handling, error boundaries, testing. A design checklist. |
| [`03-statistical-and-scientific-software.md`](03-statistical-and-scientific-software.md) | Concerns specific to statistical/analytics code: reproducibility, deterministic seeds, choice of statistical methods, multiple-comparison correction, numerical testing, provenance. |
| [`05-code-craftsmanship-and-maintainability.md`](05-code-craftsmanship-and-maintainability.md) | General software-craftsmanship principles for clear, precise, maintainable code: SOLID, cohesion/coupling, DRY/KISS/YAGNI, complexity, naming, refactoring, code smells, technical debt, tests. A maintainability checklist. |
| [`04-reading-list.md`](04-reading-list.md) | A curated, verified annotated bibliography: books, university courses, MOOCs, foundational papers, statistical-method, and software-craftsmanship references. |

## How to use these guides

- **Designing a new pipeline?** Read `01` to name the system, then use `02` as a
  checklist while you decompose it into stages.
- **Reviewing an existing one?** Use the checklists at the end of `02`, `03`,
  and `05`.
- **Caring about code quality / maintainability generally?** `05` covers the
  craftsmanship layer (SOLID, cohesion/coupling, DRY/KISS/YAGNI, refactoring,
  technical debt) independent of the pipeline domain.
- **Onboarding or upskilling?** Work through the reading list in `04`; the
  "start here" picks at the top of each section are the highest-leverage.
- **Doing statistics in code?** `03` plus the statistical-method references in
  `04` cover method selection and how to verify correctness.

> All external resources in `04` were verified to exist (publisher, journal,
> official docs, or hosting institution) at the time of writing. Editions and
> course offerings move over time — re-verify before citing formally.

## Related

- [`../code-standards/`](../code-standards/) — sibling, repository-agnostic
  reference for file and function *structure* (Google/PEP 8 rules, threshold
  table) plus a structural audit checklist. This set is about *system design*;
  that one is about *file and function structure*.

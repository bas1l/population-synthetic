# Code Standards & Structural Audit — Home

> **Wiki:** **Home** · [Standards](01-file-and-function-standards.md) ·
> [Audit Checklist](02-audit-checklist.md)

A **repository-agnostic** truth source for how source files and functions should
be structured, and a checklist for auditing any repository against those rules.

This area is organised as a small **wiki**: every page opens with a navigation
line, links to its siblings inline, and closes with a *See also* section. Start
here, then follow the links.

Nothing in this set is specific to one project. The rules are drawn from
authoritative, citable sources — the **Google Python Style Guide**, **PEP 8 /
PEP 20 / PEP 257**, the default thresholds of **Pylint** and **Ruff/Black**, and
**The Hitchhiker's Guide to Python** — and are deliberately separated into
*official rules*, *tool defaults*, and *book heuristics* so an auditor never
mistakes an opinion for a standard.

Point these documents at a codebase to answer one question: *does this repo's
file and function structure follow the standards, and where does it deviate?*

## Documents in this set

| File | What it covers |
|------|----------------|
| [`01-file-and-function-standards.md`](01-file-and-function-standards.md) | The reference standard. Language-agnostic principles (cohesion, single responsibility, splitting), then the concrete **Python (Google) profile**: function rules (length, docstrings, type hints, defaults, naming), file/module skeleton (docstring, imports, constants, `main()` guard), and a consolidated numeric-thresholds table tagged Hard / Soft / Tool / Opinion. |
| [`02-audit-checklist.md`](02-audit-checklist.md) | The rubric. A portable pass/fail checklist an auditor (human or agent) runs against any repository: file-level checks, function-level checks, a severity legend mapped to `01`, and a fill-in output template so audits are uniform and comparable across repos. |

## How to use these guides

- **Setting expectations for a new or existing codebase?** Read
  `01` — it is the single statement of what "well-structured" means here, with a
  citation for every rule.
- **Auditing a repository?** Work top-to-bottom through `02`, recording each
  finding in the output template at the end of that file. The thresholds in `02`
  are the same numbers as the table in `01` — if they ever disagree, `01` wins.
- **Adding another language?** `01` is structured as a language-agnostic shell
  plus one filled **Python (Google) profile**. A new language gets its own
  profile section under the same principles, and `02` gains parallel checks.

> The numeric thresholds split into three classes: **official rules** (e.g.
> PEP 8 line length), **tool defaults** (e.g. Pylint `max-module-lines = 1000`),
> and **book heuristics** (e.g. Clean Code's ≤20-line functions). Treat them
> differently — a tool default is configurable, a heuristic is an opinion, only
> an official rule is a standard. Re-verify source URLs before citing formally;
> style guides and tool defaults move over time.

## See also

- [Standards](01-file-and-function-standards.md) — the reference rules and
  threshold table.
- [Audit Checklist](02-audit-checklist.md) — the rubric to run against a repo.
- [`../data-pipeline-engineering/`](../data-pipeline-engineering/) — sibling
  engineering-standards set covering data-pipeline architecture, statistical
  software, and code craftsmanship (SOLID, DRY/KISS/YAGNI). That set is about
  *system design*; this set is about *file and function structure*.

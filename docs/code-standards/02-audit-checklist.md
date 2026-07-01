# Structural Audit Checklist

> **Wiki:** [Home](README.md) ·
> [Standards](01-file-and-function-standards.md) · **Audit Checklist**

A portable pass/fail rubric for auditing **any** repository's file and function
structure against the [Standards](01-file-and-function-standards.md). It is
designed to be run by a human reviewer or an agent. Every threshold here is taken
from the [numeric thresholds table](01-file-and-function-standards.md#4-numeric-thresholds-table)
in the Standards page — if a number ever disagrees, that table wins.

**Contents**

- [1. How to run an audit](#1-how-to-run-an-audit)
- [2. Severity legend](#2-severity-legend)
- [3. File-level checks](#3-file-level-checks)
- [4. Function-level checks](#4-function-level-checks)
- [5. Output template](#5-output-template)
- [See also](#see-also)

---

## 1. How to run an audit

1. **Enumerate source files.** List the language's source files, excluding
   generated artifacts, vendored/third-party code, and data files. (For Python:
   `*.py` under `src/`, `scripts/`, tests; skip caches and JSON data dumps.)
2. **Measure mechanically.** Collect line counts per file, and per function:
   statements, arguments, locals, branches, returns. Tool-assisted route for
   Python:
   - Line length, line counts, import sorting: **Ruff** (`E501`, `I`) /
     line-count of each file.
   - Module length, function complexity: **Pylint** (`C0302`, `R0915`, `R0913`,
     `R0914`, `R0912`, `R0911`).
3. **Review by hand what tools cannot see.** Cohesion ("one concern per file"),
   single responsibility, docstring *quality*, and naming *clarity* are manual
   judgements — tools only flag the mechanical proxies.
4. **Record every check** in the [output template](#5-output-template), one row
   per finding, with the measured value, the threshold, and a verdict.
5. **Classify, don't just count.** Tag each finding by
   [severity](#2-severity-legend) so a configurable tool default is never
   reported as a hard violation.

---

## 2. Severity legend

Mirrors the authority classes in the
[thresholds table](01-file-and-function-standards.md#4-numeric-thresholds-table).

| Severity | Meaning | Action |
|---|---|---|
| 🔴 **Hard** | Violates an official rule (Google / PEP 8). | Fix. |
| 🟡 **Soft** | Crosses an official advisory threshold (e.g. ~40-line function). | Reconsider; justify if kept. |
| 🔵 **Tool** | Crosses a configurable linter default (Pylint/Ruff). | Investigate; often a cohesion smell. |
| ⚪ **Opinion** | Crosses a book heuristic (Clean Code / Fowler). | Informational only. |

---

## 3. File-level checks

Run once per source file.

- [ ] **Module docstring present** — file opens with a module docstring
  (one-line summary + description). 🔴 *Google §3.8.2*
- [ ] **Import discipline** — packages/modules only (no importing individual
  symbols where the guide forbids it); **absolute** imports; grouped
  `__future__` → stdlib → third-party → local with blank lines; sorted within
  group; no wildcard imports. 🔴 *Google §2.2, §3.13 / PEP 8*
- [ ] **Constants named `CAPS_WITH_UNDER`** — module-level constants use
  CONSTANT_CASE; no mutable global state. 🔴 *Google §2.5 / PEP 8*
- [ ] **`main()` + `__name__` guard** — executable files put logic in `main()`
  behind `if __name__ == '__main__':`. 🔴 *Google §3.17*
- [ ] **License boilerplate** — present if the project requires it. 🔴 *Google
  §3.8.2* (skip if the project has no such policy)
- [ ] **Line length** — no line exceeds the project's configured limit
  (79 PEP 8 / 80 Google / 88 Black-Ruff; record which applies). 🔴 *PEP 8 §;
  Google §3.2*
- [ ] **Module length** — flag files over **1000 lines**. 🔵 *Pylint `C0302`* —
  not a standard; a prompt to check the next item.
- [ ] **Single-concern cohesion** *(manual)* — the file describes **one**
  responsibility; if distinct responsibilities can be named separately, flag for
  *Extract Module*. 🟡 *Principle §1; Fowler Large-Class smell*

---

## 4. Function-level checks

Run once per function/method.

- [ ] **Length** — flag functions over **~40 lines** (reconsider) 🟡 *Google
  §3.18*, and over **50 statements** 🔵 *Pylint `R0915`*. Optionally note the
  ≤20 / ~10-line ⚪ *opinions*.
- [ ] **Docstring presence** — present when the function is public, nontrivial,
  or has non-obvious logic; includes `Args:` / `Returns:`(or `Yields:`) /
  `Raises:` as applicable. 🔴 *Google §3.8.3*
- [ ] **Type annotations** — public-API functions annotate parameters and return.
  🟡 *Google §3.19.1*
- [ ] **No mutable default arguments** — no `[]`, `{}`, etc. as defaults. 🔴
  *Google §2.12*
- [ ] **Argument count** — flag over **5** args. 🔵 *Pylint `max-args`*
- [ ] **Local variables** — flag over **15**. 🔵 *Pylint `max-locals`*
- [ ] **Branches** — flag over **12**. 🔵 *Pylint `max-branches`*
- [ ] **Return statements** — flag over **6**; returns are consistent (all return
  a value or none do). 🔵 *Pylint `max-returns`* / 🔴 *consistency, Google*
- [ ] **Naming** — `lower_with_under()`; `_`-prefix for internal; no
  single-character names. 🔴 *Google §3.16 / PEP 8*
- [ ] **Nested functions** — used only to close over a local value. 🔴 *Google
  §2.6*
- [ ] **Single responsibility** *(manual)* — the function does one thing. 🟡
  *Principle §1; Fowler Long-Function smell*

---

## 5. Output template

Fill one of these per audited repository so results are uniform and comparable.
Keep rows for every finding; mark passing checks as ✅ or omit them per the
audit's verbosity.

```markdown
# Structural Audit — <repo name>

**Date:** YYYY-MM-DD
**Auditor:** <name / agent>
**Standard:** docs/code-standards/01-file-and-function-standards.md
**Line-length limit in effect:** <79 | 80 | 88>
**Files audited:** <count>  ·  **Functions audited:** <count>

## Summary

| Severity | Count |
|---|---|
| 🔴 Hard | 0 |
| 🟡 Soft | 0 |
| 🔵 Tool | 0 |
| ⚪ Opinion | 0 |

## Findings

| File:Line | Scope | Check | Measured | Threshold | Severity | Verdict |
|-----------|-------|-------|----------|-----------|----------|---------|
| path/to/file.py | module | module length | 2002 | 1000 | 🔵 Tool | split: multiple concerns |
| path/to/file.py:120 | function `foo` | length | 88 | ~40 / 50 | 🟡/🔵 | extract helpers |
| path/to/file.py:14 | module | docstring | missing | required | 🔴 Hard | add module docstring |

## Notes

- Cohesion / single-responsibility judgements and recommended splits.
```

---

## See also

- [Standards](01-file-and-function-standards.md) — the rules and threshold table
  this checklist enforces.
- [Home](README.md) — area overview and navigation.

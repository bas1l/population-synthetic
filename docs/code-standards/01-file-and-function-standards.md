# File & Function Standards

> **Wiki:** [Home](README.md) · **Standards** ·
> [Audit Checklist](02-audit-checklist.md)

The reference standard for how a source file and a function should be
structured. The rules are **language-agnostic principles** instantiated by one
concrete **Python (Google) profile**. Every Python rule carries a section
reference to its source; the consolidated thresholds live in
[§4](#4-numeric-thresholds-table) and are the numbers the
[Audit Checklist](02-audit-checklist.md) enforces.

**Contents**

- [1. Principles (language-agnostic)](#1-principles-language-agnostic)
- [2. Function standards — Python (Google) profile](#2-function-standards--python-google-profile)
- [3. File / module standards — Python (Google) profile](#3-file--module-standards--python-google-profile)
- [4. Numeric thresholds table](#4-numeric-thresholds-table)
- [5. Sources](#5-sources)
- [See also](#see-also)

---

## 1. Principles (language-agnostic)

These hold regardless of language; the Python profile below is one realisation.

1. **One module = one cohesive concern.** A file should describe a single
   responsibility. There is *no* "one class per file" rule (that is a
   Java/C# convention, not a universal one) — a module may hold several closely
   related classes and functions, as long as they serve one concern.
2. **Small, focused functions.** A function should do one thing. Prefer many
   small, well-named functions over one large one.
3. **Cohesion drives splitting, not raw line counts.** Split a file when it
   stops describing one concern or when distinct responsibilities can be named
   separately — *not* because it crossed an arbitrary line count. Line-count
   limits (see [§4](#4-numeric-thresholds-table)) are mechanical *nudges* that
   usually correlate with lost cohesion, not the rule itself.
4. **Explicit over implicit.** Prefer clear, named structure (namespaces,
   modules, typed signatures) to dense or clever code.

These principles trace to **PEP 20** ("Namespaces are one honking great idea";
"Flat is better than nested"; "Sparse is better than dense"), to Martin Fowler's
**Long Function** and **Large Class** code smells (the trigger is "too many
responsibilities", apply *Extract Function* / *Extract Class*), and to **The
Hitchhiker's Guide to Python** ("regroup all interfacing functionality in one
file, and all low-level operations in another"). See [§5](#5-sources).

> A profile for another language slots in beside §2/§3 under these same
> principles. Python (Google) is the first filled profile.

---

## 2. Function standards — Python (Google) profile

What a function should look like, per the **Google Python Style Guide** (with
corroboration noted). Section numbers are Google's.

- **Length (§3.18, soft).** *"We recognize that long functions are sometimes
  appropriate, so no hard limit is placed on function length. If a function
  exceeds about 40 lines, think about whether it can be broken up without harming
  the structure of the program."* The 40-line figure is an explicit soft trigger
  to reconsider, **not a cap**. Pylint/Ruff corroborate with a mechanical
  ceiling of **50 statements** (`R0915` / `PLR0915`).
- **Single responsibility (§3.18).** "Prefer small and focused functions." A
  function does one thing; if it is doing several, extract.
- **Docstrings (§3.8.3).** Mandatory when a function is *public API*, of
  *nontrivial size*, or has *non-obvious logic*. Required sections: **`Args:`**
  (each parameter), **`Returns:`** (or **`Yields:`** for generators), and
  **`Raises:`** (relevant exceptions). May be omitted for short, obvious
  functions; an override may point to the base method's docstring. (Format is
  PEP 257-compatible.)
- **Type annotations (§3.19.1).** *"At least annotate your public APIs."* Full
  coverage is encouraged but not mandatory.
- **Default argument values (§2.12).** *"Do not use mutable objects as default
  values."* Default to `None` and assign the mutable value inside the body.
- **Nested / inner functions (§2.6).** *"Avoid nested functions or classes except
  when closing over a local value other than `self` or `cls`."* Permitted only
  for genuine closures.
- **Lambdas (§2.10).** Allowed, but promote to a named `def` when a lambda spans
  multiple lines or grows long (~60–80 chars).
- **Naming (§3.16).** Functions and methods are `lower_with_under()`; a single
  leading underscore (`_lower_with_under`) marks internal/non-public. No
  single-character names (narrow exceptions only). Corroborated by PEP 8.
- **Returns.** Be consistent: either all `return` statements return an
  expression or none do (a bare `return` reads as returning `None`). Pylint caps
  return statements at **6** (`R0911`).

Where Google sets **no** number, the design-checker defaults in
[§4](#4-numeric-thresholds-table) (args, locals, branches) supply corroborating
thresholds — they are Pylint defaults, not Google rules.

---

## 3. File / module standards — Python (Google) profile

What a file should contain, top to bottom, per Google. Section numbers are
Google's.

1. **License / copyright boilerplate (§3.8.2).** *"Every file should contain
   license boilerplate."* Use the project's license.
2. **Module docstring (§3.8.2).** Mandatory; *"Files should start with a
   docstring describing the contents and usage of the module."* Format: one-line
   summary ending in a period, a blank line, an overall description, and
   optionally a `Typical usage example:` block.
3. **Imports (§2.2, §3.13).**
   - Import *packages and modules only*, not individual classes/functions.
   - Use **absolute** imports; do not use relative names.
   - Group, most-generic first, blank line between groups:
     `__future__` → standard library → third-party → repository sub-packages.
   - Sort lexicographically (case-insensitive) within each group.
   - `import y as z` only for standard abbreviations (e.g. `numpy as np`).
   - Corroborated by PEP 8's three-group ordering and "avoid wildcard imports".
4. **Module-level constants / globals (§2.5).** *"Avoid mutable global state."*
   Module-level constants are *"permitted and encouraged"* and **must be named
   `CAPS_WITH_UNDER`** (`_CAPS_WITH_UNDER` if internal). Corroborated by PEP 8
   ("constants … written in all capital letters with underscores").
5. **The code** — classes and functions (per [§2](#2-function-standards--python-google-profile)).
6. **`main()` + guard (§3.17).** For executables, put the main functionality in a
   `main()` function and gate execution with `if __name__ == '__main__':` so the
   module stays importable.

**Module length: there is no limit.** Neither Google nor PEP 8 defines a maximum
file length. The only concrete number is **Pylint's `max-module-lines = 1000`**
(`C0302`) — a *configurable tool default*, a soft mechanical flag that a file may
have accreted multiple concerns, not a standard. Splitting is governed by
cohesion ([§1](#1-principles-language-agnostic)), not the count.

---

## 4. Numeric thresholds table

Every concrete number in one place, tagged by authority. **Hard** = official
rule. **Soft** = official but advisory. **Tool** = configurable linter default.
**Opinion** = book heuristic, influential but not a standard. The
[Audit Checklist](02-audit-checklist.md) enforces exactly these numbers.

| Metric | Number | Source | Class |
|---|---|---|---|
| Line length (code) | **79** | PEP 8 | Hard |
| Line length (docstrings/comments) | **72** | PEP 8 | Hard |
| Line length (team opt-in) | **99** | PEP 8 | Soft |
| Line length | **80** | Google §3.2 | Hard |
| Line length | **88** | Black / Ruff defaults | Tool |
| Function length → reconsider | **~40 lines** | Google §3.18 | Soft |
| Function statements | **50** | Pylint `R0915` / Ruff `PLR0915` | Tool |
| Function arguments | **5** | Pylint `max-args` (`R0913`) | Tool |
| Local variables | **15** | Pylint `max-locals` (`R0914`) | Tool |
| Branches | **12** | Pylint `max-branches` (`R0912`) | Tool |
| Return statements | **6** | Pylint `max-returns` (`R0911`) | Tool |
| Module / file length | **none** | Google, PEP 8 | — |
| Module / file length | **1000** | Pylint `max-module-lines` (`C0302`) | Tool |
| Function length ideal | **≤20 lines** | Clean Code (Martin) | Opinion |
| Function length smell | **>~10 lines** | Refactoring (Fowler) | Opinion |
| Mutable default args | **forbidden** | Google §2.12 | Hard |
| Nested functions | **closures only** | Google §2.6 | Hard |
| Function/method naming | `lower_with_under()` | Google §3.16 / PEP 8 | Hard |
| Constant naming | `CAPS_WITH_UNDER` | Google §2.5 / PEP 8 | Hard |
| Module docstring | **required** | Google §3.8.2 | Hard |
| Function docstring | required if public/nontrivial/non-obvious | Google §3.8.3 | Hard |
| Type annotations | annotate public APIs | Google §3.19.1 | Soft |
| `main()` + `__name__` guard | required for executables | Google §3.17 | Hard |
| License boilerplate | required per file | Google §3.8.2 | Hard |

---

## 5. Sources

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
  — §2.2 Imports, §2.5 Global variables, §2.6 Nested functions, §2.10 Lambdas,
  §2.12 Default arguments, §3.2 Line length, §3.8.2 Modules, §3.8.3 Functions and
  methods, §3.13 Imports formatting, §3.16 Naming, §3.17 Main, §3.18 Function
  length, §3.19 Type annotations.
- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 20 — The Zen of Python](https://peps.python.org/pep-0020/)
- [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [Pylint — Standard Checkers / all options](https://pylint.readthedocs.io/en/stable/user_guide/configuration/all-options.html)
  · [too-many-lines (C0302)](https://pylint.readthedocs.io/en/latest/messages/convention/too-many-lines.html)
  · [too-many-statements (R0915)](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-statements.html)
- [Ruff — line-too-long (E501)](https://docs.astral.sh/ruff/rules/line-too-long/)
  · [too-many-statements (PLR0915)](https://docs.astral.sh/ruff/rules/too-many-statements/)
- [The Hitchhiker's Guide to Python — Structuring Your Project](https://docs.python-guide.org/writing/structure/)
  · [Code Style](https://docs.python-guide.org/writing/style/)
- [Robert C. Martin, *Clean Code* — summary](https://gist.github.com/wojteklu/73c6914cc446146b8b533c0988cf8d29)
- [Martin Fowler — Code Smell](https://martinfowler.com/bliki/CodeSmell.html)
  · [Refactoring: This class is too large](https://martinfowler.com/articles/class-too-large.html)

---

## See also

- [Audit Checklist](02-audit-checklist.md) — run these rules against a repo.
- [Home](README.md) — area overview and navigation.

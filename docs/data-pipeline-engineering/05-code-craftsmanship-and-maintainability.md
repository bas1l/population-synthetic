# 05 — Code Craftsmanship & Maintainability

`02` covers the *architecture* of a pipeline — how the stages fit together. This
document covers the *code inside the stages*: the general, language-and-domain-
agnostic principles that keep any codebase clear, precise, and maintainable.
These are the disciplines that decide whether a correct design stays correct and
changeable a year later.

Every principle below is traced to its primary source (see `04` and the inline
citations). The doc closes with a consolidated maintainability checklist.

---

## 1. SOLID — five principles for change-tolerant code

Robert C. Martin assembled these five object-oriented design principles
("Design Principles and Design Patterns", 2000; *Agile Software Development*,
2002); the SOLID acronym is due to Michael Feathers. They are tools against
three failure modes of aging code: **rigidity** (hard to change), **fragility**
(changes break unrelated things), and **immobility** (can't reuse a piece
without dragging the rest).

| Letter | Principle | One-line meaning | Primary source |
|---|---|---|---|
| **S** | Single Responsibility | A module should have one reason to change | Martin, *SRP* (1996) |
| **O** | Open/Closed | Open for extension, closed for modification | Martin, *OCP*; orig. Bertrand Meyer |
| **L** | Liskov Substitution | Subtypes must be usable wherever the base type is, preserving its contract | Liskov (1988); Liskov & Wing (1994) |
| **I** | Interface Segregation | Many small client-specific interfaces beat one fat one | Martin, *ISP* |
| **D** | Dependency Inversion | Depend on abstractions, not concretions; high-level policy shouldn't depend on low-level detail | Martin, *DIP* |

**Why it matters even in non-OO / pipeline code.** SOLID is usually taught with
classes, but each principle has a direct functional/module reading:

- **SRP** → a function/module does one job; a parser parses, an aggregator
  aggregates. The "one reason to change" test catches stages that secretly do
  two things (parse *and* reformat *and* validate).
- **OCP** → add a new input variant or chart type by *adding* code (a new
  adapter/plotter), not by editing a growing `if/elif` chain. This is the
  functional form of the normalization pattern in `02` §6.
- **LSP** → any two implementations behind the same contract must be truly
  interchangeable. If swapping one provider-adapter for another changes
  downstream behavior beyond the declared contract, LSP is violated. Liskov's
  formal "behavioral subtyping" (preserve invariants, honor pre/postconditions)
  is the precise statement.
- **ISP** → don't force a caller to depend on fields/methods it never uses. A
  DTO bloated with everything every stage might want is the data-shaped version
  of a fat interface.
- **DIP** → the computation layer should depend on a data *contract*, not on the
  concrete file format it came from. Inverting that dependency is what lets you
  swap the I/O layer without touching the statistics.

> **Note on dogma.** SOLID is a set of heuristics, not laws. Over-applied (an
> interface per class, indirection everywhere) it produces its own complexity.
> Apply it where change is actually likely. See §6 (YAGNI) and Ousterhout's
> *A Philosophy of Software Design* on avoiding shallow over-abstraction.

---

## 2. Cohesion and Coupling — the master metric of modularity

Introduced by Stevens, Myers & Constantine ("Structured Design", *IBM Systems
Journal*, 1974) and elaborated in Yourdon & Constantine's *Structured Design*
(1979). The single most durable predictor of maintainability:

> **Maximize cohesion within a module; minimize coupling between modules.**

**Cohesion** = how strongly the things inside a module belong together.
Constantine's scale, weakest to strongest:
coincidental → logical → temporal → procedural → communicational → sequential →
**functional** (the goal: everything in the module contributes to one
well-defined task).

**Coupling** = how much one module depends on the internals of another.
Spectrum, worst to best: content → common → external → control → stamp →
**data** (the goal: modules communicate only through simple, explicit data).

**How to apply.**

- A stage that does one task on one kind of data has *functional cohesion* —
  aim for it. A "utils" grab-bag of unrelated helpers has *coincidental
  cohesion* — split it.
- Passing a small, explicit record between stages is *data coupling* (good).
  Reaching into another module's globals (*common coupling*) or passing a flag
  that switches its behavior (*control coupling*) is worse — refactor it out.
- **Information hiding** (Parnas, "On the Criteria To Be Used in Decomposing
  Systems into Modules", *CACM* 1972) is the design rule that produces low
  coupling: hide the decisions *likely to change* behind a stable interface, so
  a change stays inside one module. Decompose around what varies, not around the
  processing steps.

**Connascence** (Meilir Page-Jones) is the modern refinement: two elements are
connascent if changing one forces a change in the other. Prefer weak, local
forms (connascence of name) over strong, distant ones (connascence of position,
meaning, or execution order). It gives you a finer vocabulary than "coupling"
for *which* dependency to attack first.

---

## 3. DRY and orthogonality

From Hunt & Thomas, *The Pragmatic Programmer* (1999; 20th-anniv. ed. 2019).

- **DRY — Don't Repeat Yourself:** "Every piece of knowledge must have a single,
  unambiguous, authoritative representation within a system." Duplication isn't
  just repeated text — it's repeated *knowledge* (a constant, a rule, a schema
  definition copied across stages). When it changes, you must find every copy;
  miss one and you have a bug.
- **Orthogonality:** unrelated things should be independent — changing one
  shouldn't ripple into another. Orthogonal components can be developed, tested,
  and reasoned about in isolation. This is coupling (§2) viewed from the design
  side.

**Caution:** DRY is about knowledge, not coincidental similarity. Two pieces of
code that look alike but change for different reasons are *not* duplication —
merging them couples two independent concerns (a violation of §2). "Don't
abstract until you see the third case" is the practical guard.

---

## 4. Simplicity, complexity, and cognitive load

- **KISS — Keep It Simple:** prefer the simplest design that works; complexity is
  a cost paid on every future read. (Origin attributed to Kelly Johnson,
  Lockheed; the punctuation and exact date vary across sources.)
- **A Philosophy of Software Design** (John Ousterhout, 2018/2021) frames the
  whole job as **managing complexity**. Its central tools: **deep modules**
  (simple interface hiding substantial implementation) over shallow ones,
  **information hiding**, and minimizing the **cognitive load** a reader must
  carry. A red flag it names: "change amplification" (one decision forces edits
  in many places) — the symptom of poor cohesion/coupling.
- **Cyclomatic complexity** (Thomas McCabe, "A Complexity Measure", *IEEE TSE*,
  1976): `V(G) = edges − nodes + 2`, the number of independent paths through a
  function. A language-independent proxy for how hard a function is to test and
  understand. High V(G) (rules of thumb often cite >10) means "split this." In
  Python, `radon` computes it and the Maintainability Index for CI gating.

---

## 5. Readable code: names, functions, comments

From Martin's *Clean Code* (2008, chs. 2–4), McConnell's *Code Complete* 2nd ed.
(2004), and PEP 8 / PEP 257 for Python specifics.

- **Names** should reveal intent. A name that needs a comment to explain it is
  the wrong name. Searchable, pronounceable, consistent. (Clean Code ch. 2;
  Google Python Style Guide.)
- **Functions** should be small and do one thing at one level of abstraction,
  with few parameters. A function you can't summarize in one sentence is doing
  too much. (Clean Code ch. 3.)
- **Comments** explain *why*, not *what*. Code says what; if you need a comment
  to say what, make the code clearer instead. Keep comments truthful — a stale
  comment is worse than none. (Clean Code ch. 4.)
- **Python specifics:** PEP 8 (style/layout/naming) — and crucially its "a
  foolish consistency is the hobgoblin of little minds": *project-internal
  consistency outranks the rulebook*. PEP 20 (Zen): "Explicit is better than
  implicit," "Readability counts." PEP 257 (docstring conventions). Enforce with
  a formatter (`black`/Ruff format) and a linter (Ruff/flake8/pylint) so reviews
  are about substance, not whitespace.

---

## 6. YAGNI — build for today's requirements

Martin Fowler, "Yagni" (2015); from Kent Beck's Extreme Programming.

> "You Aren't Gonna Need It" — don't build speculative capability for imagined
> future needs.

Premature generality carries four costs (Fowler): cost of *building* it, cost of
*delay* (it displaces work you do need), cost of *carry* (it complicates the code
that has to live around it), and cost of *repair* (when the guessed-at future
arrives different from the guess). YAGNI is the counterweight to over-applied
SOLID/abstraction. It only works *with* refactoring (§7): you keep the code
simple now because you trust yourself to evolve it later.

---

## 7. Refactoring, code smells, and technical debt

- **Refactoring** (Fowler, *Refactoring* 1st 1999 / 2nd 2018) is changing code's
  internal structure *without changing its behavior*, in small, test-backed
  steps (Extract Function, Rename, Inline, …). It's how a design stays clean
  while requirements move — the enabling discipline behind both YAGNI and
  continuous improvement. Catalog: refactoring.com.
- **Code smells** (Fowler & Beck, "Bad Smells in Code", *Refactoring* ch. 3) are
  surface signs of deeper problems — Long Function, Large Class, Long Parameter
  List, Duplicated Code, Feature Envy, Shotgun Surgery. They tell you *where* to
  refactor, not that something is provably wrong.
- **Technical debt** (Ward Cunningham's metaphor, OOPSLA '92; Fowler's "Technical
  Debt" and "Technical Debt Quadrant"): shipping not-quite-right code is like
  borrowing — fine if repaid promptly, crippling if the interest compounds.
  Fowler's quadrant (deliberate/inadvertent × prudent/reckless) makes the point
  that *some* debt is unavoidable even for good teams, because better designs
  emerge only after you've built once. The discipline is to make debt
  **deliberate and visible**, and pay it down opportunistically in code you're
  already touching.

---

## 8. Tests as the safety net for maintainability

Refactoring is only safe with tests; maintainability and a real test suite are
the same investment seen from two sides. (See `02` §10 and `03` §5 for the
pipeline/statistics specifics; this is the general discipline.)

- **The test pyramid** (Mike Cohn, popularized by Fowler's "TestPyramid"; Ham
  Vocke's "The Practical Test Pyramid"): many fast unit tests at the base, fewer
  integration/service tests, very few slow end-to-end tests at the top. Invert it
  (mostly slow E2E tests) and the suite becomes brittle and too slow to run —
  which means it stops being run.
- **Test observable behavior, not implementation**, so tests survive refactoring.
- **Property-based testing** (Hypothesis) complements example tests: state a
  property that should hold for all inputs and let the tool search for
  counter-examples and edge cases.
- **Legacy code is code without tests** (Michael Feathers, *Working Effectively
  with Legacy Code*, 2004): to change untested code safely, find a "seam," get a
  characterization test around it, *then* refactor.

---

## 9. The supporting disciplines

Maintainability is also a function of the practices *around* the code.

- **Dependency & environment hygiene:** declare dependencies and build config
  explicitly (`pyproject.toml`; PEP 517/518), isolate environments (`venv`), and
  pin for reproducibility. Undeclared/implicit dependencies are a maintainability
  tax. (See also `03` on reproducibility.)
- **Documentation that matches its purpose:** the **Diátaxis** framework (Daniele
  Procida) separates docs into tutorials, how-to guides, reference, and
  explanation — each serving a different need; conflating them produces docs that
  serve none. Generate API reference from docstrings (Sphinx + PEP 257).
- **Architecture Decision Records** (Michael Nygard, 2011): record each
  significant decision (context / decision / consequences) in a short,
  version-controlled file, so future maintainers know *why*, not just *what*.
- **Code review** (Google's Code Review Developer Guide): review for design,
  correctness, complexity, tests, naming, and comments — and keep changes small
  enough to review well.
- **Version-control discipline:** small, coherent commits; clear messages
  (e.g. Conventional Commits) and meaningful version bumps (Semantic Versioning)
  so history stays a usable record.

---

## Maintainability review checklist

**Design principles**
- [ ] Does each module/function have a single responsibility (one reason to
      change)?
- [ ] Can new variants be added by extension, not by editing existing branches
      (OCP)?
- [ ] Are implementations behind a shared contract truly substitutable (LSP)?
- [ ] Do consumers depend only on the data/interface they use (ISP), and on
      abstractions rather than concrete details (DIP)?

**Cohesion & coupling**
- [ ] Is each module functionally cohesive (no grab-bag "utils")?
- [ ] Do modules communicate via simple explicit data (data coupling), not
      shared globals or behavior flags?
- [ ] Are change-prone decisions hidden behind stable interfaces (information
      hiding)?

**Simplicity & readability**
- [ ] Is this the simplest design that works (KISS), without speculative
      generality (YAGNI)?
- [ ] Are functions small, single-level, few-parameter; complexity (V(G)) in
      check?
- [ ] Do names reveal intent; do comments explain *why*; are docstrings present?
- [ ] Is style enforced by formatter + linter rather than by hand?

**Knowledge & duplication**
- [ ] Is each piece of knowledge represented once (DRY) — and is apparent
      "duplication" actually the same knowledge, not coincidence?

**Sustaining the code**
- [ ] Is there a test suite shaped like a pyramid that makes refactoring safe?
- [ ] Are known smells/debt tracked and visible, and paid down opportunistically?
- [ ] Are dependencies/environment declared and reproducible?
- [ ] Are significant decisions recorded (ADRs); are commits/reviews disciplined?

---

## See also

- `02-architecture-principles-and-patterns.md` — the same ideas at the
  stage/pipeline level (separation of concerns, layering, contracts,
  normalization-as-OCP).
- `03-statistical-and-scientific-software.md` — the analytics-specific
  reliability concerns.
- `04-reading-list.md` — full citations for every source named here (Martin's
  SOLID papers; Liskov & Wing; Stevens/Myers/Constantine and Parnas on
  cohesion/coupling/information hiding; Page-Jones on connascence; McCabe on
  complexity; Hunt & Thomas; Ousterhout; Fowler on refactoring/smells/YAGNI/
  technical debt; Cunningham; Feathers; McConnell; the relevant PEPs and tooling).

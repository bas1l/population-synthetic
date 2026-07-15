# `employment_status` — the two-table merge derivation (a unique case)

> **⚠️ Read this before touching `employment_status` sourcing.** This attribute is the **only one in
> the entire generator** whose distribution is *derived by combining more than one real SCB table*
> under an explicit statistical assumption, rather than read from a single API response. It is a
> deliberate, documented exception and must never be mistaken for — or quietly turned into — a
> hardcoded/synthetic distribution. Every other attribute sources one table; this one does not, and
> the reasons are specific and load-bearing.

- **Status:** **implemented (opt-in), 2026-07-15** — shipped as Phase 6 of the SCB source-improvements
  plan. Default **OFF** (the single-table age×sex path of §2 remains the fallback); enabled via
  `generate_scb_population.py --merge-status-education` (or `FetchService.load_all(...,
  merge_status_education=True)`). Implementation: `fetch_employment_status` +
  `parse_employment_status_combined` (per-cell odds-multiplication, §5) in the Sweden generator; the
  no-3-way-interaction assumption is surfaced at the Step 3 call site and in provenance. This document
  remains the authoritative specification of the method.
- **Date:** 2026-07-15 · **Scope:** Sweden / SCB, public PxWeb API only.
- **Companions:** [`scb-source-audit.md`](./scb-source-audit.md) (attribute #9),
  [`scb-pxweb-data-model.md`](./scb-pxweb-data-model.md) (why the 3-way doesn't exist),
  `docs/architecture/design-principles.md` (the no-synthetic-distributions invariant this must honour).

---

## 1. Why this attribute is unique

Every other population attribute maps to **one** SCB table that already carries the cross-tab we
need (possibly after summing real cells — e.g. industry→12 sectors, Boendeform→3 tenures). Only
`employment_status` has an irreducible problem: the generator conditions status on **age,
education, and sex**, but **SCB never published a table crossing labour-force status × education ×
age** — confirmed by an exhaustive 968-table sweep of AM+UF (see the data-model doc). The three-way
lives only in SCB microdata (MONA/RTB), which is out of scope.

So the choice is:
- **(A) Drop a dimension** — condition status on age×sex *or* education×sex, discard the other. This
  is what the source-audit ships as the default (switch to the register status×age×sex table).
- **(B) Merge two real tables** — reconstruct P(status | age, education, sex) from real 2-way
  margins under an explicit "no three-way interaction" assumption. That is the method specified here.

(B) is what makes this attribute unique: it is the sole place the pipeline *combines* tables rather
than *reads* one.

## 2. The two ship states — keep both documented

| | **Default (A)** — ship now | **Merge (B)** — this document |
|---|---|---|
| Sources | `AM/AM0210/AM0210D/ArRegArbStatus` only | `ArRegArbStatus` **+** `AM/AM0210/AM0210A/ArbStatusUtbM` (+ baseline) |
| Conditions status on | age × sex | **age × education × sex** |
| Modeling assumption | none | no status×age×education interaction (explicit) |
| Loses | the status↔education link within age | nothing (recovers it) |
| Invariant posture | trivially compliant | compliant **with guardrails** (§6) |

The default is always the fallback. The merge is an **opt-in enhancement**, justified only if the
status↔education association is analytically material. **Do not silently switch** between them.

## 3. The exact tables and margins (ALL REGISTER — non-negotiable)

The merge consumes three real margins, **all from the register (RAMS/BAS) family** so that the word
"employed" means the *same thing* in every input. Mixing in the AKU *survey* table
(`NAKUBefUtbNivAr`) is **prohibited** — AKU's ILO "employed" is a different construct from the
register's administrative "employed"; a joint built across them corresponds to no real measurement.

| Role | Table | Provides | Notes |
|------|-------|----------|-------|
| **P(status \| education, sex)** | `AM/AM0210/AM0210A/ArbStatusUtbM` | status × education × sex, register full-count | Age present only as working-age **total 20–64** — that's fine, we use it *only* for the status↔education shape. |
| **P(status \| age, sex)** | `AM/AM0210/AM0210D/ArRegArbStatus` | status × 5-yr age (15–19…70–74) × sex, register | 6-cat status (see §4); `Region="00"`, `Fodelseregion="tot"`. |
| **Baseline P(status \| sex)** | `AM/AM0210/AM0210D/ArRegArbStatus` with `Alder="15-74"` aggregate | status × sex, register | Same table, all-ages selection. |
| *(seed, only for full-table IPF — see §7)* | `UF/UF0506/UF0506B/UtbBefRegionR` | education × age × sex | Not needed for per-persona sampling. |

Exact `ContentsCode` / value codes to pull at implementation time from the metadata dump
(`scb-am-uf-metadata.jsonl`) — the register status codes verified live in `ArRegArbStatus` are:
employed `000002NT`, unemployed `000002NM`, students `000002NR`, retirees `000002NP`, sick
`000002NQ`, others `000002NO`, total `000002NU`.

## 4. Two taxonomy reconciliations (structural label maps — allowed; sum real cells only)

**(a) Education — collapse the generator's 8-level ISCED onto the status table's coarser scheme.**
`UtbBefRegionR` (the `education_level` source) uses 8 ISCED97 levels (1–7 + US); `ArbStatusUtbM`
uses a coarser set (codes like `21 / 3 / 4 / 5 / 61 / US`). Build a **nesting** collapse map
(pre-upper-secondary → post-secondary → postgraduate) so each generator education level maps to
exactly one status-table education class. Confirm the exact source codes from the metadata dump; do
not guess them in code.

**(b) Status — collapse to a common category set to multiply, then re-expand.**
`ArbStatusUtbM` carries 3 categories (employed / unemployed / not-in-labour-force);
`ArRegArbStatus` carries 6 (employed / unemployed / students / retirees / sick / others). To combine,
reduce both to the common **3-cat** set: `NILF = students + retirees + sick + others`. Compute the
merged emp/unemp/NILF split, then — if the generator wants the finer 6-cat output — **re-expand NILF
into students/retirees/sick/others using the age-only proportions from `ArRegArbStatus`** (education
modulates only the top-level split). The register 6-cat labels already match the generator's target
status vocabulary better than AKU's 3-cat.

## 5. The estimator (per-persona, closed form)

At sampling time each persona already has (age band `a`, education level `e`, sex `s`). Compute, over
the common 3-cat status set:

```
w(status) = P(status | e, s) * P(status | a, s) / P(status | s)
P(status | a, e, s) = w(status) / sum_status w(status)      # normalise
```

then sample `status` from that vector; optionally re-expand NILF per §4(b).

- This is the closed-form solution of the log-linear model `[SA][SE]` (status↔age and
  status↔education terms; **no** status↔age↔education interaction).
- **Why no education×age seed is needed:** we compute a *conditional* per persona, not a whole
  population table. Each persona's own (age, education) already came from the real education
  distribution, so the true education×age correlation is carried by the sample itself and cancels out
  of the conditional. (The seed is only required for the materialised-table IPF variant, §7.)

## 6. Invariant compliance — why this is a DERIVATION, not a synthetic distribution

The hard rule (`design-principles.md`): *every probability must come from a real API response;
parametric approximations are prohibited; if no API provides a field, drop it.* This method is
compatible, and the reasoning must be recorded because it is the crux:

- **No external numbers, no distributional family.** The estimator introduces no fitted rate, no
  lognormal/logistic, no hand-chosen constant. It is a deterministic algebraic reconciliation of
  **real register margins** into the maximum-entropy joint consistent with them.
- **Strictly cleaner than an already-accepted precedent.** The `socioeconomic_class` derivation
  (`src/population_synthetic/generators/real/income_class.py`) takes real income-bracket counts and
  applies **external, non-API threshold constants** (Eurostat AROP 0.60, OECD/Pew 1.00 / 2.00). Those
  are exactly the kind of injected parameter this method does **not** contain. If that derivation
  clears the bar, this one clears it more easily.
- **Weaker assumption than the status quo.** The current sampler already draws several attributes
  from unconditional marginals and draws status from education×sex with **age silently marginalised
  away**. "No three-way interaction" is a *weaker, explicit* assumption than "discard a whole real
  dimension."

**Guardrails that make it compliant (all mandatory):**
1. **All-register sources** — never mix the AKU survey table (§3).
2. **The no-3-way-interaction assumption is documented** — here, and in code comments at the call
   site — and treated exactly like the generator's existing unconditional-marginal assumptions:
   visible, not hidden.
3. **Only real cells are combined** — no cell is invented; suppressed/null cells are handled per §8,
   never replaced with a fabricated value.

If any guardrail cannot be met, fall back to the default (A).

## 7. Optional variant — materialised population table via IPF

If a full population 3-way table is ever needed instead of per-persona sampling, use **iterative
proportional fitting** of the log-linear model `[SA][SE][AE]` (all three 2-way interactions, no
3-way): rescale `N(status, age, edu)` per sex to match, in turn, the status×edu margin
(`ArbStatusUtbM`), the status×age margin (`ArRegArbStatus`), and the **education×age seed**
(`UtbBefRegionR`), cycling to convergence. This *keeps* the education×age association. Because the
margins come from different tables, first **harmonise each to probabilities and a single population
total per sex**, or accept small residuals — IPF converges but cannot match mutually inconsistent
1-way totals exactly.

## 8. Caveats (carry into implementation and into the generated-data docs)

1. **Age cap 74.** Both register status tables end at 70–74. Ages **75+** have no labour-status
   source anywhere on the public API — model them as out-of-labour-force / retired (the register
   `retirees` category supports this). State this in the population's provenance notes.
2. **Confidentiality nulls.** Sparse cells (young × high-education × unemployed) are suppressed to
   null. **Tolerate nulls; never treat as certain-zero and never impute** — a null status×edu cell
   means that leg is unavailable for that combination; fall back to the age-only conditional for it.
3. **20–64 applicability of the education leg.** `ArbStatusUtbM`'s status↔education shape is measured
   on the 20–64 population; applying it to 15–19 and 65–74 personas is a mild extrapolation. Note it.
4. **Definition coherence across attributes.** This makes `employment_status` a **register** attribute
   while `employment_type` remains **AKU**. Flag the mixed provenance in the attribute-level docs.

## 9. Recommendation (unchanged from the audit)

**Land the default (A) — switch to `ArRegArbStatus` for status × age × sex — as the primary move.**
Adopt the merge (B) as an explicitly-documented, all-register follow-up, pursued only if downstream
analysis shows the status×education interaction is material. When (B) is implemented, this document is
its specification, and its assumption must be surfaced at the call site and in the generated-data
provenance — because it is the one place the generator reasons across tables.

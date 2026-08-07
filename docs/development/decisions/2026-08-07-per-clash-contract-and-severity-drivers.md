# ADR: a second contract file on the `persona_realism` → `realism_ranking` seam, carrying no denominator

**Date:** 2026-08-07
**Status:** Accepted
**Extends:** [`2026-08-07-persona-realism-per-combination-split.md`](2026-08-07-persona-realism-per-combination-split.md)
**Plan:** [`plans/active/severity-driver-attribution.md`](../plans/active/severity-driver-attribution.md)

Two decisions came out of this change. They are recorded together because the second only became
expressible once the first was made — the same shape as the ADR this one extends.

---

## Decision 1 — the per-clash detail crosses the seam as a second file, not as a second reader

### Context

The severity heatmaps report *how much* of each model × method cell carries a clash at a given
level. They cannot report *what* clashed, and the pipeline was throwing that away: the judge returns
`{"attributes": [a, b], "severity": S, "explanation": …}` per issue, the reduction collapsed it to a
`ClashKey` and dropped the explanation, and the per-persona contract row carried only counts. A
reader of `severity_heatmap_s3.png` could see that one cell was bad and had no way, short of opening
individual verdict caches by hand, to learn that it was almost entirely
`employment_status × employment_type`. That is the single most actionable fact the judge produces.

Every field needed was already on disk — the verdict caches hold the issues, and the persona's own
mapped `attributes` hold the category values — so the tempting route was to let the aggregator read
the caches. The governing ADR forbids exactly that: it would make `reduce.py` a shared dependency
(the aggregator reaching into judge internals), re-do the reduction on every run, and let the
aggregator see partial combination directories that have caches but no report, defeating the
staleness gate.

Three alternatives were live. Widening `{combo}_personas.csv` is wrong at the grain: a persona
carries 0..N clashes, which forces either a repeating group whose width depends on the data or a
lossy top-1 truncation. Reading `clash_taxonomy` from `{combo}.json` is combination-level with no
persona linkage and no category values, so no per-cell prevalence with a correct denominator can be
computed from it. Asking the judge to emit the values directly changes `prompt_template_sha256`,
which invalidates the homogeneity guard against every already-judged combination and forces a full
re-judge at full LLM cost — for data derivable for free.

### Decision

`persona_realism` writes a **second tidy CSV** on the same one-way file-backed seam:
`{combo}_clashes.csv`, one row per `(persona, round, sorted attribute pair, severity)`, carrying the
persona's own category values and an `unresolved` flag. It has its own `SCHEMA_VERSION`, its own
writer and strict reader (`analysis/utils/realism_clash_csv.py`), and its own provenance key
(`clash_csv_schema_version`) beside — never folded into — the per-persona one.

The attribute pair is stored **sorted**, matching `ClashKey` canonicalisation, because an
uncanonicalised pair splits one driver into two ranks. `value_a`/`value_b` are empty **iff**
`unresolved`, which covers all three ways the join can fail (the judge named an axis the persona
does not carry; the axis is present but null; its value renders empty). The alternative for the
second case is writing the literal `"None"` into a category column — a fabricated category that
would then be *ranked*, which the regeneration pass confirmed is not hypothetical.

A third file, `{combo}_clash_explanations.csv`, carries the judge's free text at the same key. It
lives in the producer package rather than in `analysis/utils/` and carries no schema version,
because nothing reads it: putting it beside the contract module would imply a promise to a consumer
it does not have.

### Consequences

- The regeneration is one command and structurally free: `--rewrite-artifacts` puts the runner in
  plan-only mode, so no client is constructed and no call is made. All 51 `swedish_02` combinations
  were regenerated this way — 2235 clash rows, 5 unresolved, 2 header-only — with the verdict caches
  unchanged in size and mtime across two passes.
- Every pre-existing output base is **skipped** by the ranking until regenerated, with a reason
  naming the flag. That is deliberate and matches the per-persona-CSV precedent: consuming a base
  without the file would report every severity cell as having no drivers at all, which is
  indistinguishable from a clean one.
- A combination with no clashes writes a **header-only** file, not no file. "No clashes" and "not
  processed" are different facts and the reader distinguishes them: absent raises, header-only
  returns `[]`.
- The producer enforces the invariants at the write boundary (sorted pair, known severity,
  unresolved-implies-empty, grain uniqueness), so a violation is caught before it reaches disk.

---

## Decision 2 — the per-clash row carries no denominator, and a reconciled join compensates

### Context

`realism_csv.py` states as one of its three properties that *the rows carry their own denominators*,
so no downstream rate is ever computed over an unreported base. The obvious move was to hold the new
file to the same rule.

It does not apply here, and applying it would have been worse than skipping it. The denominator of
any rate computed from a clash row is a count of **personas** — how many of the cell's personas
exhibit this clash — which is a property of the sibling per-persona file, not of a clash. Repeating a
per-combination constant across a variable number of rows would additionally let a reader compute a
prevalence from this file alone that silently disagrees with the sibling whenever the two are out of
step.

### Decision

The per-clash row carries **no** denominator. The consumer reads **both** files for a combination
and joins them on `persona_id`: the per-persona file supplies the base, the per-clash file the
numerator.

What makes that join safe is a reconciliation check the reader performs on every read: the number of
distinct `(persona_id, attr_a, attr_b, severity)` tuples at level *L* must equal the sum of the
sibling's `clash_count_s{L}` column. Both are counts of *distinct clashes per persona*, so they are
the same number computed two ways; a disagreement means the two files were written from different
states of the verdict cache, and every rate joined across them would be over the wrong base. That is
a hard error naming both files and the regeneration command — never a warning.

The divergence is recorded in the module docstring, next to the property it declines to satisfy, so
the next reader finds the reasoning where they would look for the rule.

### Consequences

- The severity-driver block's denominator is `len(record.personas)` — computed by the *same*
  function as the severity heatmap's, so a driver prevalence is always readable against the cell it
  explains. A test asserts the two agree cell by cell, because if they could differ a cell could
  report a driver prevalence above its own severity rate: arithmetically impossible for a subset,
  and a sure sign the numerator and denominator came from different persona sets.
- The counting unit is the **persona**, not the clash: a clash raised in three rounds of one persona
  counts that persona once. Rounds survive on the row (so round-level detail is not lost) and
  collapse at count time.
- The driver numbers are **not additive** and are not shares of a whole — one persona may carry
  several distinct clashes, each clash names two attributes, and the severity levels are not a
  partition. Both the unit and the non-additivity are **data fields** on the JSON block and columns
  on every emitted row, not prose in a docstring, because the tables travel without the code and the
  failure mode is a reader summing them or drawing them as a pie.
- The attribution is **reporting-only**, exactly as the prevalence grids are: it feeds no ranking, no
  contrast and no significance test, and changes no number already published. `severity_weights` /
  `impossibility_severities` remain declared-but-unwired. Comparing driver prevalences *across*
  cells would need a correction battery this block does not run, so it ranks only *within* a cell.
- `penalised` travels on every driver row for the same reason the S1 heatmap gets a neutral ramp: a
  table is read one row at a time, and an S1 row arriving without it is an unusual-but-possible
  pairing presented in the shape of a defect. On the current Swedish data the S1 drivers read plainly
  as tail-reach — SCB's own top S1 pairs are `Married × 1-person household` and
  `Owner-occupied villa × Poverty`.
- A driver below `--driver-min-count` is **suppressed and counted**, not published and not silently
  dropped: a rank-1 driver seen in two personas is an anecdote, and printing it at the top of a table
  asserts otherwise. What `--driver-top-n` leaves out is counted separately, since those are real
  drivers merely below the cut and the two exclusions must not be confusable.
- Ranks are positional with a total tie-break (`n_personas` desc → `attr_a` → `attr_b`, and → value
  names at the finer grain), so the emitted bytes are a function of the counts alone. Equal counts
  therefore share no rank; `n_personas` is the number to read, which the block says on every grid.

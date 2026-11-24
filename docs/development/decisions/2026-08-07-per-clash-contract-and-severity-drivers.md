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

---

## Amendment — one flat table per grain, not one per severity level

**Date:** 2026-08-07 (post-implementation, operator-requested)

The attribution first shipped as six flat tables, `severity_drivers_s{1,2,3}.csv` and
`severity_driver_values_s{1,2,3}.csv` — one file per grain per level, mirroring the heatmaps' file
layout. That mirroring was never itself a decision, only an inherited shape, and it does not survive
the difference between a figure and a table: a heatmap can show one grid at a time, so one file per
level is the only way to draw three; a table has columns, so the level is data. Splitting it across
files made the commonest reading — compare a competitor's S3 drivers against its S2 drivers — a
three-file diff over a column that could have been sorted on.

The tables are therefore consolidated into `severity_drivers.csv` and `severity_driver_values.csv`,
each covering all three levels with `severity` as an identity column. **The heatmaps are unchanged**
— one per level, as decided in the preceding commit.

Nothing computed changes: the JSON block keeps its `levels.{S3,S2,S1}` nesting (natural in a format
that has nesting, and consumers read it), no number moves, and the flattening is the only thing
touched.

Two properties become load-bearing that were previously merely present:

- **`penalised` is now the only thing on a row separating an S1 driver from a defect**, since S1 and
  S3 rows sit in the same file. It was already on every row for exactly this reason; the merge
  removes the filename as a redundant second signal, so the column carries the claim alone.
- **Ranks stay within `(competitor, severity)` and are not renumbered across the merged file.** A
  rank-1 S2 driver and a rank-1 S3 driver are both rank 1. Renumbering across levels would impose a
  single order on a hard contradiction and an unusual-but-possible pairing, which is precisely what
  the severity dimension exists to refuse. The row order is total —
  `slug` → severity by `SEVERITY_RANK` (S3, S2, S1, never alphabetical) → `rank` — so a competitor's
  three levels arrive contiguous and worst-first, and the repeated `1` is legible as a per-level
  rank rather than a duplicate.

---

## Amendment 2 — the country-wide pair summary reads the clash rows, not the published drivers

**Date:** 2026-08-07 (post-implementation, operator-requested)

Three figures were added beside the severity heatmaps, `severity_pair_summary_s{3,2,1}.png/.svg`:
per level, the attribute pairs that clashed, ranked descending, pooled across the country. The
heatmaps answer *which cells have a high rate*; the driver tables answer *what drove one cell*;
neither answers *at this level, what clashed, ranked* — which is the question a reader asks first and
the one the manuscript needs a figure for.

Two decisions inside it are worth recording, because both have a tempting wrong answer that would
have produced a plausible-looking figure.

**The figure is computed from the full per-clash rows, not from `severity_drivers.csv` or the
`severity_drivers` JSON block.** Those are the obvious source — they are already ranked, already
attached to the ranking document, and already in memory. They are also already *cut*: truncated per
cell by `--driver-top-n` and floored by `--driver-min-count`. Summing a per-cell top-5 into a country
total is biased twice over. It over-weights a pair that is mediocre everywhere but clears many
cells' cut, and it erases a pair that is broad across the sweep but never locally top-ranked — the
second being exactly the kind of finding a country-wide figure exists to surface. The summary
therefore reads `CompetitorRecord.clashes` directly, which is the untruncated series the loader
already holds, and the provenance sentence explaining this is printed **on the figure**, because the
two blocks answer neighbouring questions from the same rows and the difference is invisible in the
output.

**SCB is drawn as its own series and is never pooled into the bars.** It is an ordinary competitor
with no reference role, which is the argument *for* including it — but it is also one 100-persona
unit against ~50 synthetic ones, so an honest pooled bar would bury it, and a reader would then
attribute its contribution to the synthetic population. The contrast it supplies is the single most
useful thing these numbers produced: at S3 it raises **no** clash on any pair, while at S1 its own
rate exceeds the pooled synthetic rate on most pairs (`civil_status × household_size` 27% against
5%, `housing_tenure × socioeconomic_class` 24% against 0.9%) — the mode-collapse concern Axis B
exists for, seen from a second direction. It keeps the red-diamond encoding it already has on the
forest plot, so identity is carried by shape as well as hue and the mapping is learned once for the
whole folder.

Consequences and smaller choices that follow from those two:

- **Ranking is by pooled *synthetic* persona count**, with `n_personas` desc → `attr_a` → `attr_b`
  as a total tie-break. A pair only the real population raised therefore ranks at zero and is
  normally below the cut; it stays in the universe and is counted under `n_pairs_real_only` on the
  figure, rather than being dropped — excluding it would privilege-by-omission the competitor this
  analysis refuses to privilege.
- **The denominator is the summed `len(record.personas)` over the pooled competitors** — the same
  population the corresponding heatmap divides each of its cells by, so a bar is readable against
  that grid. It is stated numerically on the figure, as is the real population's separate base.
- **The name is `severity_pair_summary`, not `severity_driver_summary`.** "Driver" is pinned by the
  plan to a clash ranked *within* a `(competitor, severity)` cell; this ranking is across
  competitors and is deliberately not built from those tables, so borrowing the word would assert
  the provenance the figure exists to avoid.
- **A level with nothing to rank renders an explaining figure**, not a skip and not empty axes.
  "No pair clashed at this level anywhere" is a measurement, and the artifact set staying complete is
  what keeps it distinguishable from a crashed render.
- **Reporting-only, and computed outside `build_ranking`.** `severity_pair_summary(records, level,
  *, top_n)` is a standalone pure function the CLI calls at the edge; nothing is added to the ranking
  document, so `axis_a`, `axis_b`, `severity` and `factor_significance` are provably untouched
  (asserted by test). `--pair-summary-top-n` is resolved at the edge like the two driver bounds.

# ADR: a reference-free typicality statistic with a reference-dependent rendering

**Date:** 2026-08-12
**Status:** Accepted
**Extends:** [`2026-08-07-persona-realism-per-combination-split.md`](2026-08-07-persona-realism-per-combination-split.md)
**Plan:** [`plans/active/typicality-axis-metric.md`](../plans/active/typicality-axis-metric.md)

Two decisions came out of this change. They are recorded together because the second is what makes
the first affordable — without it the statistic would be reference-free and unreadable.

Neither decision moves Axis A or Axis B. The axis table in the ADR this one extends stands unamended:
`axis_b.dispersion_contrast` remains the *tested* contrast against the real population and one of the
four named guards against the mode-collapse inversion. What is added sits beside it, reporting-only,
exactly as the severity dimension does.

---

## Decision 1 — self-containment is claimed computationally and refused directionally

### Context

The governing ADR bought one property at some cost: a per-combination unit's output is a function of
that unit's own inputs and the config, and of nothing else. `realism_ranking` is the layer allowed to
break that, because cross-unit claims are its whole job — but every cross-unit claim it makes is also
a claim that cannot be checked by recomputing one cell.

Typicality was the one signal with no self-contained reading at all. The judge scores each persona
0–10, and the document published that score only as `axis_b.dispersion_contrast` =
`abs(measure - real_measure)`. The absolute value is deliberate (collapsing must be penalised exactly
as much as over-spreading) and it discards the **sign**, so a mode-collapsed competitor and an
over-dispersed one are indistinguishable in the published number. Meanwhile the severity and
impossibility dimensions each had a model × method heatmap and typicality had none.

The obvious fix — put `distance_to_scb` in a grid — reproduces the defect: the cell would still be
unreadable on its own, and every cell would still depend on a second unit having been judged.

So the statistic had to be reference-free. But a reference-free typicality number is not
self-interpreting, and this is where the two senses of "self-contained" come apart:

- **Computational self-containment** is a property of the arithmetic. It is testable: recompute the
  cell from that competitor's scores alone and the published value reproduces byte-for-byte.
- **Directional self-containment** would be the claim that the number carries its own better/worse
  reading. Typicality does not have one. A competitor scoring uniformly at the modal level has
  collapsed onto the modal Swede; a low-scoring one may be reaching the real population's tail or may
  simply be incoherent. **The optimum is interior**, and on the measured `swedish_02` data the real
  population is not even the ceiling — 16 of 50 synthetic competitors are more dispersed than it.

Conflating the two is the trap. A statistic that is computationally self-contained looks like a score,
and any monotone ramp drawn over it asserts a direction the arithmetic never had.

### Decision

The cell is computationally self-contained and **carries `"direction": null`**, with the reason as a
data field (`direction_reason`), not as a docstring. The default statistic is **Berry-Mielke's IOV**
(`analysis/utils/ordinal.py::iov`), a function of the interior CDF alone — so it is invariant to any
strictly increasing relabelling of the 11 levels, the property the mean fails — in the **dispersion**
orientation: 0 = all mass on one level, 1 = 50/50 at the extremes. It is the only shortlist member
that separates a `{0,10}` split (1.000) from a `{9,10}` split (0.100), which is precisely the
mode-collapse distinction the axis exists to draw; entropy, Simpson and Berger-Parker are identical on
both.

Because published implementations of this family disagree with one another on which way it points
(Blair & Lacy's `l²` is normed *concentration*; `agrmt::dsquared()` and Stata's `ordvar` disagree;
R's `wINEQ` publishes `1 - l²` under the Blair-Lacy name), the orientation is emitted **in the output**
and not only in a docstring: `statistic_label` states the endpoints, `orientation` is a field, and both
come from `ordinal.STATISTIC_LABELS` so the label can never drift from the definition it labels.

The mean level ships as a selectable alternative (`--typicality-metric mean`, registry key
`mean_level`). It measures **location**, not dispersion, and assumes the levels are equally spaced —
an interval claim about an ordinal judge scale on which only 4 of 11 levels carry verbal anchors. When
it is selected, `statistic_caveat` becomes non-empty and travels as a **column on every emitted row**,
because a caveat that lives only in the docs is a caveat the table travels without.

### Consequences

- **The denominator is the survivor subset and is never `n_personas`.** A cell is computed over the
  personas with a `can_exist` majority *and* a non-null mean typicality — the same
  `CompetitorRecord.typicality_means` base the Axis B contrast and the factor tests read, so the three
  readings cannot disagree about what was measured. Both counts travel on every row and in every cell,
  under distinct names (`denominator`, `n_personas`), because a denominator that must be guessed is
  guessed to be `n_personas`.
- **That base is confounded with the thing being ranked, and the gate bounds it rather than removing
  it.** On `swedish_02`, `Spearman(n, dispersion) = -0.576`: a dispersion cell partly re-renders the
  impossibility rate. `--typicality-min-n` (default 30) flags a thin cell `under_powered` and counts
  it in `excluded` — never drops it — and `n` is printed in every heatmap cell. The mechanism is
  plausibly survivorship; the correlation is measured, the mechanism is not, and `n_confound` says so
  on the block and on the figures.
- **Four states, never three.** A value; an `under_powered` value (measured, on too few personas to
  read); a judged competitor with no typicality-bearing persona (`status: no_typicality`, value
  `null` — never `0.0`, which is a real measurement meaning total collapse); and an unjudged
  `(model, method)` pair, which is the grid's `null`. Collapsing any two would publish a claim nobody
  made.
- **A degenerate interval is published flagged, not repaired.** A competitor whose personas all sit on
  one level yields a percentile bootstrap interval of exactly `[0, 0]`. That is honest
  computationally and has zero coverage whenever the true dispersion is above zero — at a
  parameter-space boundary the bootstrap is *inconsistent*, not merely inaccurate (Andrews 2000). The
  cell carries `boundary: true` rather than a smoothed, bias-corrected or reverse-percentile interval,
  each of which would replace a visibly degenerate interval with an invisibly wrong one.
- **Non-composite, permanently.** The statistic is never folded with the impossibility rate into a
  single realism score: the two have different denominators (this one is the survivor subset) and
  different directions (Axis A is monotone, this one interior), so a composite would be arithmetic
  over incommensurable quantities. `non_composite` is a field, not a convention.
- **Reporting-only in the tested sense.** Building the document with loose and with tight typicality
  bounds leaves `axis_a`, `axis_b`, `severity`, `severity_drivers` and `factor_significance`
  byte-identical (the mixed logit excluded — its variational fit is not bit-reproducible between
  calls). The same property the `severity_drivers` block is held to.

---

## Decision 2 — the reference enters at render time or not at all

### Context

Decision 1 leaves a number on `[0, 1]` with no direction. `0.328` is meaningless to a reader who does
not already know that the register population sits at `0.399`.

The reference is genuinely needed for reading, and genuinely destructive in the arithmetic: putting it
in the cell reintroduces exactly the cross-unit dependency the whole design removed, and it is the
step that turned Axis B's number into something that cannot be recomputed from one competitor.

The rendering layer had no third option available. `realism_ranking/charts.py` carried two ramps —
`_DEFECT_CMAP` (Reds, more is worse) and `_NEUTRAL_CMAP` (Blues, reported but never penalised, the S1
precedent). Both are sequential and anchored at a hard-coded `vmin = 0.0`, on a true-zero premise
stated in the module: "a pale cell always means 'few', never 'fewest in this particular sweep'". That
premise is correct for a defect rate and wrong for an interior-optimum statistic, where the pale end
must be the *reference*, not zero.

### Decision

**The statistic goes in the cell; the reference goes in the colormap.**

`plot_typicality_heatmap` adds the third ramp state, `_DIVERGING_CMAP = "PuOr"`, with limits
**symmetric about the midpoint** so equal departures in the two directions get equally saturated
colours. The midpoint is read from `block["reference_value"]` — the real population's own statistic,
computed exactly as every competitor's and entering no cell's computation — never from a literal. Low
end (orange) = more collapsed than the register population; high end (purple) = more dispersed. PuOr
rather than the familiar red–blue because red and blue are already spoken for by the sibling heatmaps
in the same folder, and reusing either hue would import their better/worse reading onto an axis that
has none.

Absence of the reference **degrades and records**, it does not default: with no real population in the
consumption set (or a real population carrying no typicality-bearing persona), the figure falls back
to the neutral sequential ramp anchored at the statistic's true zero and prints the block's own
`reference_note` explaining why. A zero-width range — every competitor exactly at the reference — is
the one case where a ramp cannot be built at all; the limits fall back to `reference ± 0.05` and the
figure states that it has no measured range rather than implying a spread the limits invented.

Every caveat printed on the figures — `reference_note`, `direction_reason`, `counting_unit`,
`under_powered_policy`, `n_confound` — is read from the block. Only the two words for *how this figure
draws a thing* belong to the chart, so a figure and the numbers it renders cannot disagree.

### Consequences

- **A dedicated renderer, not the existing one.** `_render_grid_heatmap` reads `cell["rate"]` and
  `cell["denominator"]` by literal key. This block's value key is `value` — it is not a rate, and
  renaming it to match would mislabel every number in the block — so reusing that renderer would have
  painted every cell grey and labelled it `n/a` **without raising**: a silent-wrong-output path that
  produces a plausible figure. A test asserts a populated cell is not rendered as missing.
- **One new idiom, deliberately scoped.** `plot_typicality_by_method` draws the real population as a
  horizontal reference line. Everywhere else in the analysis layer it is a series, bar or marker,
  because everywhere else it is *ranked* and a reference line would encode "closer is better" into a
  figure whose point is not to assume that. This axis ranks nothing: the line is the sibling heatmap's
  ramp midpoint, in a form that shows each method's spread around it, and it carries the real
  population's own colour and slug so it cannot read as a target or a threshold.
- **The reproducibility claim is bounded by the writer, not by this axis.** The JSON block, both CSVs
  and the PNGs are byte-reproducible across two writes and across competitor orderings. The SVG
  siblings are **not**, and no figure in this repository is: matplotlib stamps every SVG with a
  `dc:date` creation timestamp and salts per-save element ids. That is a property of the writer, and
  claiming SVG byte-stability anywhere would be claiming something no artifact here has.
- **The rollback is one branch, not a redesign.** If the diverging ramp proves unreadable, the neutral
  sequential ramp already required for the reference-absent case is the fallback.

---

## The two-axis assertion, and where it is asserted

The A/B table is stated in ten places. Nine are prose or config, one is machine-readable. They must
move together or a reader hits a document that says there are two dimensions and a figure folder that
holds three.

This commit is documentation-only, so the four in-source sites were **left for a follow-up** rather
than edited here: a docs commit that changes code destroys the review boundary. None of the four is
wrong today — each one already documents the typicality outputs — but none of the four states the
axis structure as anything other than two axes.

| # | Site | Kind | States the typicality axis? |
|---|------|------|------------------------------|
| 1 | [`2026-08-07-persona-realism-per-combination-split.md`](2026-08-07-persona-realism-per-combination-split.md) — Decision 2's axis table | ADR prose | **By extension.** The table is unamended by design (an accepted ADR is a record, not a living document); this ADR is the amendment and declares `Extends:` it |
| 2 | `docs/development/persona-realism-judge.md` | operator guide | **Yes** — a note under the axis table, plus its own "typicality axis" section |
| 3 | `config/analysis/analysis_registry.yaml` — `realism_ranking.description` | config | **Yes** |
| 4 | `docs/architecture/sub-packages.md` — the `realism_ranking/` bullet | wiki | **Yes** |
| 5 | `docs/architecture/commands.md` — "Persona realism: two tasks, one seam" | wiki | **Yes** |
| 6 | `CLAUDE.md` — the `realism_ranking` paragraph | hub | **Yes** |
| 7 | `scripts/analyze/rank_persona_realism.py` — module header, "Two axes, deliberately opposite in direction" | source | **No.** The outputs list and the flag list below it are complete; the two-axis preamble is not |
| 8 | `realism_ranking/builder.py` — the module docstring's ASCII axis table | source | **Partly.** The table itself lists A and B only; the paragraph beneath it already names the typicality axis as a dimension sitting beside them |
| 9 | `realism_ranking/builder.py` — the `axis_definitions` block in the emitted document | source, **the only machine-readable one** | **No.** Keys `A` and `B` only. A consumer reading the document programmatically learns of two axes and finds a third top-level block |
| 10 | `realism_ranking/charts.py` — module header | source | **Partly.** Both new figures are documented in full; the lede still reads "Three figures:" while listing seven, which predates this change |

Site 9 is the one that matters most and the one a prose pass cannot reach. Until it is extended, the
document's self-description is narrower than the document.

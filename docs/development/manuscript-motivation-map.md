# Manuscript motivation map — nine philosophy pillars vs. current text

**Created:** 2026-07-20
**Status:** Report only — no manuscript edits made. This file records *where the paper's
motivation currently stands* against the philosophy dictated by the author, so edits can be
planned deliberately.

## Scope & sources

- **Target manuscript (canonical):** the LaTeX build at
  `…/40_llm-population-fidelity-benchmark/2026-07-02_TMLR/sections/*.tex`
  (OneDrive, outside the code repo). `main.pdf` is the deliverable; edits go in `.tex`.
- **Line numbers** below refer to those `.tex` section files as of 2026-07-20.
- **Verified data** (Pillar 7) came from the analysis outputs:
  `…/02_Data/03_Analysis/model_ranking/swedish_performance.csv` (39 runs),
  `…/03_Analysis/method_significance/swedish_method_comparison.csv`,
  `…/03_Analysis/mapped/real_swedish.json` (N=10,000 reference).
- **SCB table catalog** (Pillar 8): `docs/reference/scb-pxweb-catalog/` (in this repo).

## One-line diagnosis

The manuscript currently tells a **benchmarking-gap** story ("no prior work unites live
official statistics + method-as-variable + no microdata seed"). The dictated philosophy is a
**practitioner-access-gap** story ("real population data is either segmented or gated behind a
~4-month approval, so there is no quick way to stand up a realistic population"). They overlap
only partially: of nine pillars, one is well-covered, one is partial, three are thin, two are
absent, and two are implemented-but-unjustified.

---

## Status summary

| # | Pillar | Status |
|---|--------|--------|
| 1 | One-shot persona has no population context | Thin |
| 2 | Accessible tables are segmented (rebuild the joint yourself) | Thin / missing as motivation |
| 3 | Controlled registers are gated (~4-month wait) | **Absent** |
| 4 | The gap: no quick, task-dedicated population standup | Partial |
| 5 | Bigger topic: eliciting probability from LLMs + context | Embryonic |
| 6 | LLM coherence advantage via shared-context cascade | Mechanism present, claim unproven |
| 7 | Argmax kills minorities; only code sampling recovers them | **Well-covered + data-verified** |
| 8 | ~968 tables → curated subset spanning biological→social | **Absent** as rationale |
| 9 | Semi-controlled generation + richness-vs-boxes mapping | Mechanism present, rationale/tension absent |

---

## Pillar 1 — one-shot persona has no population context

**Claim.** An LLM asked to "generate a persona" has no information about the population it is
drawn from — only the single individual. Fine for one persona; loses the joint/marginal
structure that makes a *population* realistic.

**Where it lives now.** intro L11–14 (homogenise / collapse subgroup heterogeneity);
related_work L3–12 and **L24–31** ("reproduce marginals while missing multivariate structure" —
closest in the paper); discussion L13–14.

**Verdict — Thin.** The *symptom* (mode collapse, missing multivariate structure) is well cited,
but always attributed to *poor prompting/elicitation*, never to the pillar's premise that a
per-persona prompt has *no information about the population*. The single-individual-vs-population
distinction is never stated outright.

**Decision / link.** Pairs with Pillar 5 as the two ends of one "context ↔ probability" thread:
"the model lacks population context" ↔ "supply context so it expresses the right distribution."

---

## Pillar 2 — accessible tabular data is segmented

**Claim.** Accessible national statistics are published as tables with, at best, a few filters
(one characteristic conditioned on another). To build a full population you must reconstruct the
joint distribution yourself, and cohesion between characteristics can be lost.

**Where it lives now.** methods L43–47 (no SCB table cross-tabulates status × education × age, so
the education cross is dropped); discussion L37–38 ("available only as marginals"); limitations
L40–45 (labour attributes cap at age 74); methods L20–26 (no-synthetic-distributions rule).

**Verdict — Thin / effectively missing as motivation.** Segmentation appears only as
reference-construction asides and limitations, never as front-matter motivation. The
"reconstruct the joint yourself / cohesion is lost" argument is absent from abstract, intro, and
related work.

**Supporting data.** Catalog: of 968 AM+UF tables, **0** combine status × education × a real age
band (see Pillar 8).

---

## Pillar 3 — controlled-access registers are gated

**Claim.** High-fidelity registers exist but are gated: you must submit a research plan /
justification, you can be refused, access is tuned to one specific project, and turnaround
averages ~4 months.

**Where it lives now.** Nowhere directly. Nearest: related_work L33–39 ("every such method needs
a real microdata seed"); privacy-as-*benefit* in discussion L50 and conclusion L25.

**Verdict — Absent.** The strongest divergence from the intended philosophy. No mention of
controlled-access registers, the approval process, refusal risk, project-specificity, or the
~4-month lead time. Privacy is invoked as a benefit of local synthesis, but the access barrier
that *motivates* it is missing.

**Decision.** The ~4-month figure needs a citable source before it can go in the manuscript.

---

## Pillar 4 — the gap: no quick, task-dedicated population standup

**Claim.** There is no clear methodology to quickly stand up a realistic population for a
dedicated task from purely artificial data. This paper measures LLM-vs-real fidelity and whether
some methodologies yield more realistic populations.

**Where it lives now.** intro L16–19 (the two research questions: fidelity vs official
statistics; model vs method); intro L47–61 (four contributions); related_work L13–14 (we change
the ground truth and make elicitation the variable) and L56–60 ("no prior work unites this").

**Verdict — Partial.** The fidelity question and the model-vs-method question are stated clearly,
and the literature gap is explicit. But the specific *practitioner* framing — *quickly* standing
up a realistic population *for a dedicated task* as an alternative to slow/gated real data — is
not articulated. The gap is framed as a benchmarking gap, not a practitioner-need gap.

---

## Pillar 5 — the bigger topic: eliciting probability from LLMs + context

**Claim.** The work opens a broader methodological question: how can we get LLMs to express
probability at all, and how does context engineering drive that? (The strategy-dominates-model
finding is the empirical seed.)

**Where it lives now.** discussion L3–14 ("Why sampling beats picking" — a concrete
probability-elicitation methodology); conclusion L6–13 (the recipe). The future-work list
(conclusion L15–27) does **not** include this as a direction.

**Verdict — Embryonic.** The mechanism is present but confined to one demographic task, never
lifted to the general open question. Two gaps: (a) it is not named as a future direction;
(b) the "context" lever is treated only as *output format* (enumerate/weight/sample vs pick),
never as *context provision* (feeding population-level context) — which is the flip side of
Pillar 1.

**Decision / link.** Fold with Pillar 1 into the "context ↔ probability" thread.

---

## Pillar 6 — LLM coherence advantage via a shared-context cascade

**Claim.** An LLM builds a persona as a *cascade of shared context* (each attribute conditioned
on everything already established for that individual), yielding cohesive, realistic
individuals. The tabular route can chain-sample too, but is capped by whatever cross-tabs the
statistical office exposes.

**Where the mechanism lives.** methods L64–66 ("each resolved value is accumulated and
serialised into a context block that is prepended to every subsequent prompt"); strategy ladder
L75–90 (step **1→2** literally isolates "adding context"); tabular limitation methods L43–45.

**Where the *claim* lives.** Absent. Coherence is a "secondary, tie-breaking metric" (methods
L136); discussion L52–53 says joint/rare-combination structure "needs dedicated evaluation."

**Verdict — Mechanism present, claim unproven.** Three problems block "LLMs give more cohesive
individuals" in the current design:

1. **The coherence yardstick is defined *by* the tabular reference** (methods L127–132). The
   tables are ground truth for cohesion, so "LLMs more cohesive than tables" is not measurable
   here.
2. **The current metric doesn't isolate a context effect.** `all_pick` (no context, step 1)
   already reaches coherence 1.00 (methods L131, discussion L40) — picking modal values is
   trivially plausible.
   - *Update (2026-07-22):* the `all_pick` context leak is fixed — `all_pick` now carries
     `context: none` and is genuinely context-free, restoring the clean no-context arm for the
     1→2 comparison. (Numbers above predate the fix; regenerate `all_pick` before re-comparing.)
3. **The headline is the sampling step (4→5), not the context step (1→2).** To foreground
   "context → coherent individuals" you need the **1→2 effect size**, which the paper measures
   but does not report.

**Decision.** Frame this pillar as **empirical** (report the 1→2 context effect size from
existing data) *or* **architectural** (qualitative: the LLM cascade can condition on the full
accumulated persona, unbounded by published cross-tabs — kept out of the empirical-coherence
claims). The "more cohesive individuals" wording cannot be backed by the current coherence
numbers.

*Update (2026-07-28) — a second arm exists: strategy **v2**.* Each of the five families now ships a
v2 alongside its v1, so the strategy ladder is 5 families × 2 versions. A v2 strategy generates
**14** categories instead of 17 (dropping `birth_location`, `ethnicity_broad_global_approx`,
`current_environment_type`) and schedules `birth_country_detail` after `age` + `biological_sex`,
mirroring the real SCB conditional chain. Three consequences for this pillar:

- **v1 and v2 are separate arms.** They are also separate *strategy ids*, so the analysis pipeline
  already treats them as distinct method levels — nothing pools them, and no version flag or filter
  exists (versioning is a selection-side concept only). The caveat is interpretive: a method axis
  holding both arms interleaves complexity with version, so an ordered-trend statistic over it is a
  trend across that ten-level ladder rather than a pure complexity effect. The 1→2 context
  comparison is *within* a version — restrict the run's `--strategy` selection to get that.
- **Comparison across versions is valid only over the 14 scored axes.** No mapping or fidelity
  config changed, so Sweden still scores the same 14 attributes for both arms. Anything denominated
  in the *generated* category count (completeness rates, LLM calls, tokens, cost) is not comparable
  across versions.
- **Pre-fix v1 personas are an archived baseline.** `_build_dag` was non-deterministic (Kahn's queue
  seeded from a `set`, hash-randomised per process), so under cumulative context a given category
  saw a varying set of already-resolved attributes. It is deterministic now, which means re-running
  v1 does not reproduce the existing v1 personas. Whether v1 is regenerated or cited as pre-fix is
  an open authoring decision — and it bears directly on the 1→2 numbers quoted above.

---

## Pillar 7 — argmax kills minorities; only code sampling recovers them  ✅ data-verified

**Claim.** The simplest methods argmax to the modal value. Even generate-and-evaluate, if the
*model* makes the final pick (even when told "pick randomly"), it still argmaxes → minorities
disappear. Only coupling generation with a *proper code-side randomization tool* sampling from
the elicited weights surfaces the tail. The LLM *knows* the minorities — it can enumerate and
weight them — it just won't *select* them.

**Where it lives now (well-covered — this is the paper's central thesis).** discussion L3–14
(argmax "discards the tail" → heterogeneity compression; code sampling "turns the same latent
knowledge into a distribution"); methods L83–90 (step 5: "code, not the model, samples");
discussion L13–14 ("the model's knowledge is better than its modal answer suggests"); conclusion
L6–13.

**Verified data (both author examples confirmed).**

*Age group.* SCB reference is flat-ish (not perfectly uniform):

| Band | 18-24 | 25-34 | 35-44 | 45-54 | 55-64 | 65-74 | 75-85 |
|------|-------|-------|-------|-------|-------|-------|-------|
| Prob | 0.106 | 0.171 | 0.172 | 0.156 | 0.155 | 0.125 | 0.115 |

mean = exactly 1/7, max/min = 1.63. Per-strategy mean TV-similarity for `age_group`:

| Strategy | mean tvsim | n |
|----------|-----------:|---|
| **all_generate_evaluate_random_pick** (code samples) | **0.862** | 8 |
| all_generate_evaluate_pick | 0.342 | 7 |
| all_generate_pick | 0.337 | 8 |
| all_pick_dag | 0.303 | 8 |
| all_pick | 0.298 | 8 |

The four pick strategies are mutually "ns"; only code-sampling separates (p = 0.003–0.026 in the
significance CSV). **~0.52 absolute jump.** A near-flat truth is exactly where argmax does the
most damage — the cleanest demonstration of the whole thesis.

*Industry sector.* Same shape, harder attribute:

| Strategy | mean tvsim |
|----------|-----------:|
| **all_generate_evaluate_random_pick** | **0.613** |
| all_generate_pick | 0.292 |
| all_generate_evaluate_pick | 0.287 |
| all_pick | 0.264 |
| all_pick_dag | 0.260 |

All four pick strategies fail (0.26–0.29); only code-sampling clears it (0.61). Caveat: 0.61 ≪
age's 0.86 — code-sampling *rescues* industry, it doesn't *solve* it (high cardinality + n=100
sampling noise).

**Sub-claim NOT tested.** "Even when explicitly told to pick randomly, the model still
argmaxes." The ladder tests model-selects (step 4) vs code-samples (step 5); there is **no**
"model instructed to self-sample from its own weights" arm. So this is a mechanistic assertion,
not an isolated result. To claim it: either frame it mechanistically (argmax is a decoding
property, so instructing it away is unreliable) or add a sixth ladder rung to isolate it.

**Framing choice.** The paper speaks statistically ("heterogeneity compression", "discards the
tail"). The "minorities disappear" reading layers an equity/representation framing on top —
legitimate and stronger, but a deliberate normative choice currently absent.

**Manuscript gap.** discussion L30–36 names age and industry as hard but never shows the
per-strategy split that proves code-sampling rescues them. **Figure F6 (significance box-plots)
is a placeholder** — the natural home for this age_group + industry_sector per-strategy view.

---

## Pillar 8 — ~968 tables → a curated subset spanning biological→social

**Claim.** SCB exposes a large number of tables. We deliberately use a small subset — some tables
are replicas, and we focus on persona-relevant characteristics chosen to span an individual's
aspects, from biological (age, sex) to social (education, employment, region, civil status, …).

**Catalog facts** (`docs/reference/scb-pxweb-catalog/`):

- **968 tables** — but only across **two subject areas**, AM (labour market) + UF (education).
  The full SCB catalog spans more areas (population, income, housing, …), so 968 is a floor.
  **Precision for the paper:** say "968 tables in the labour-market and education areas alone",
  not "SCB has 968 tables".
- Of those: 330 carry a real age breakdown, 177 education level, 134 labour-force status, and
  **0** combine status × education × a real age band (the documented reason employment status is
  conditioned on age+sex only — methods L43–45).
- The manuscript issues **15 queries over ~14 distinct tables** (methods L18–19). So
  "~1000 available → ~14 used" is quantitatively true and striking.

**Where it lives now.** The 15-attribute schema is *listed* (methods L103–106) but never
justified.

**Verdict — Absent as rationale.** Neither selection reason is in the paper: (a) the
replica-pruning / 968-vs-14 ratio, and (b) the deliberate span from biological → social axes.
Belongs in methods (schema subsection), previewable in the intro.

**Next step.** Pull the explicit biological→social grouping of the 15 attributes so that claim
is airtight before it goes in.

---

## Pillar 9 — semi-controlled generation + richness-vs-boxes mapping

**Claim.** The design forces the LLM's query to the database's category schema — "semi-controlled
generation" rather than free personas. The reason is partly comparability and partly that LLMs
emit *richer* values than the DB's fixed pool of categories, so constraining them makes the
downstream mapping tractable.

**Where the mechanism lives.** methods L58–60 (field-by-field generation "rather than a single
free-text completion"; schema with description, type, bounds); methods L107–111 (tiered matcher;
"the reference population defines the category space"; out-of-space values recorded as
"unmapped").

**Verdict — Mechanism present, rationale/framing absent.** The term "semi-controlled" is never
used; the richness-vs-boxes *reason* for the constraint is nowhere.

**Two precision points.**

1. **Many-to-one, not one-to-one.** The tiered matcher collapses *multiple* rich LLM values into
   *one* canonical box. "The reference fixes the target categories so each rich value resolves to
   a well-defined box" is accurate; "one-to-one" is not — and the many-to-one direction is the
   stronger version of the point.
2. **Unacknowledged tension.** Forcing outputs into the DB's boxes (and dropping unmapped values)
   *deliberately discards the very richness* cited as an LLM advantage in Pillars 6/8. The
   benchmark measures **within-schema fidelity** by design. The limitations section (candid about
   single-run, sample sizes, reference gaps, metric caveats, cost, coverage) does **not** mention
   this. Clean honesty gap: one sentence noting the trade-off (richness for comparability) and
   that the LLM's extra granularity is out of scope *because* it was constrained away.

---

## Cross-cutting notes for the eventual edit pass

- **Narrative shift.** Intro currently opens on "LLMs are used to stand in for people, but is it
  tested?" The dictated philosophy wants it to open on "why real population data is hard to get"
  (Pillars 1–3) → feeding the gap (Pillar 4). That is a reframing of the introduction, not an
  insertion.
- **Insertion points.** Intro opening (Pillars 1–4); related_work (Pillars 2–3); methods schema
  subsection (Pillars 8–9); discussion after "Why sampling beats picking" (Pillars 5–7);
  limitations (Pillar 9 trade-off); Figure F6 (Pillar 7 data); conclusion future-work (Pillar 5).
- **Internal tension to resolve before writing.** Pillars 6/8 assert LLM *richness/coherence*;
  Pillar 9 *constrains richness away* for comparability. The paper must state both sides
  explicitly or they will read as contradictory.
- **Two open experiments (not wording changes).** Pillar 6 "report the 1→2 context effect size";
  Pillar 7 "model-can't-self-randomize" ladder rung. Both require touching the analysis, not just
  the text.

---

## Change log

| Date | Change |
|------|--------|
| 2026-07-20 | Created. Consolidated nine motivation pillars (report-only) from the dictation session; Pillar 7 data verified against `swedish_performance.csv` / `swedish_method_comparison.csv`. No manuscript edits made. |
| 2026-07-28 | Pillar 6: recorded the strategy **v2** arm (5 families × 2 versions, 14 vs 17 generated categories, birth chain under age + sex), the never-pool rule, the 14-scored-axis comparability boundary, and the v1-reproducibility consequence of the `_build_dag` determinism fix. No manuscript edits made. |

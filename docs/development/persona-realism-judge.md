# Persona Realism Judge (LLM-as-judge)

A short operator's guide to the `persona_realism` analysis process. **Design record:**
[`brainstorms/individual-persona-realism-judge.md`](brainstorms/individual-persona-realism-judge.md).
**Implementation record:** [`plans/active/persona-realism-judge.md`](plans/active/persona-realism-judge.md)
and [`plans/completed/split-persona-realism-ranking.md`](plans/completed/split-persona-realism-ranking.md)
(the per-combination / cross-combination split).

## What it measures

The `fidelity/`, `multivariate_fidelity/`, and `model_ranking/` tasks measure **distributional**
realism — whether a combination's marginals and (fetched) joints match the real Swedish population.
They cannot measure **individual** realism: whether a *single* persona hangs together as a believable
human. The two can disagree — SCB is distributionally perfect by construction (sampled from real
tables) yet its chained sampling does not condition on every attribute pair, so it can emit
internally-incoherent individuals (a 19-year-old with a doctorate); an LLM generator may skew the
marginals but rarely emit an incoherent individual. This task fills that gap.

Per persona (the bare mapped demographic tuple; Sweden's deprecated `birth_location` is excluded to
match `ComparisonScheme.attributes`, and `age` is shown to the judge as the bracketed `age_group`
derived on demand from the raw integer via the canonical `attr_value` accessor, matching the analyzed
scheme), the judge is called **N cold rounds** and returns two orthogonal axes plus a structured
clash list:

- **`can_exist`** — binary: can this attribute set describe one real person? False **only** on a hard
  biological/legal/temporal contradiction (severity S3), never for merely-unusual-but-possible.
- **`typicality`** — integer 0–10 ordinal, judged only when `can_exist` is true. 10 = modal person,
  0 = highly unusual yet still possible. It measures **commonness, not quality** — a low score is not
  a defect.
- **`issues`** — attribute pairs in tension, tagged S3 (hard contradiction) / S2 (near-impossible) /
  S1 (unusual-but-possible, reported not penalized).

Rounds reduce to personas reduce to combinations. Each combination gets **its own** impossibility
rate (bootstrap CI), typicality dispersion, and judge self-reliability metric (ICC / Krippendorff's
α) -- and nothing else. Every comparison across combinations belongs to the separate
`realism_ranking` task.

## The two-task split

`persona_realism` is **strictly per-combination**: judging one combination reads no other, its
artifacts are byte-reproducible in isolation, and processing order changes nothing. The SCB real
population is enumerated as an **ordinary competitor** `real_{country}` -- same code path, no
reference role -- differing only in its `real_sample_size` first-N prefix draw.

`realism_ranking` (`scripts/analyze/rank_persona_realism.py`) consumes the per-combination artifacts
and owns every cross-combination claim. It performs **no LLM work**, so re-running it is free.

The seam is the on-disk contract, not an in-memory hand-off: the judge writes
`{combo}_personas.csv` (one row per judged persona; schema in `analysis/utils/realism_csv.py`) and
the ranking depends on that schema and on nothing inside the judge.

Two axes, deliberately opposite in direction -- conflating them inverts the interpretation:

| Axis | Quantity | SCB's role | Direction |
|------|----------|-----------|-----------|
| **A -- validity** | impossibility rate (`can_exist`) | ordinary ranked competitor | lower is better, **for everyone including SCB** |
| **B -- coverage** | typicality dispersion | **the target to match** | `distance_to_scb` near zero is better |

Axis A deliberately does **not** treat SCB as the origin. The open question is whether SCB-sampled
personas are themselves internally incoherent (conditional chained sampling never cross-references
attributes), and a metric measuring distance *from* SCB cannot answer a question *about* SCB. Axis B
keeps SCB as the target because the observed LLM failure mode is **mode collapse**: matching the real
spread is the goal, and a spread far below SCB's is as bad as one far above it.

Two dimensions sit **beside** those axes rather than on them, and both are reporting-only: the
**severity** blocks and the **typicality axis** (each competitor's own spread as one number, read
without a reference). Neither feeds a ranking, a contrast or a test, and neither changes a number the
axes publish — in particular the typicality axis does **not** replace Axis B, which remains the only
tested SCB contrast on typicality. See [the severity dimension](#the-severity-dimension-reporting-only)
and [the typicality axis](#the-typicality-axis-reporting-only) below.

## How to run it

Two-stage — the judge reads the **mapped** populations, so map first:

```bash
python scripts/analyze/map_populations.py
python scripts/analyze/analyze_persona_realism.py --country swedish
```

CLI flags (`--help` is authoritative):

| Flag | Meaning |
|------|---------|
| `--country ID` / `--model ID` / `--strategy ID` | Repeatable combo filters (default: all). |
| `--slug SLUG` | Exact combination filter (`{country}_{strategy}_{model}` or `real_{country}`). Repeatable. Selects **only** what it names -- the real competitor is never pulled in implicitly, which is what lets one slug be judged in complete isolation. |
| `--country-id` / `--model-id` / `--strategy-id` | GUI `per_combo` singular aliases; fold into the plural filters. |
| `--output-base DIR` | Analysis-stage parent (default: `experiment_defaults.yaml` `output_base`). |
| `--force` | **Re-judge from scratch**, truncating every verdict json + telemetry jsonl, and re-write artifacts. Costs the full LLM bill -- not the way to refresh artifacts. Default: resume -- the runner is always consulted; a persona is skipped only once it holds `>= n_rounds` cached rounds, else the shortfall is topped up. |
| `--rewrite-artifacts` | Rebuild the derived artifacts from the **existing** verdict cache. Zero LLM calls on a fully-cached combination; the supported way to regenerate after an output-schema change. |
| `--no-real` | Do not enumerate the `real_{country}` competitor (it is enumerated by default whenever `--slug` is not used). |
| `--workers N` | Override the config judge-call fan-out width. |
| `--sample N` | Override the config per-combo persona sample size (**synthetic combos**). |
| `--real-sample N` | Cap personas judged for the **real competitor** (`real_{country}`). Blank = config default (`real_sample_size`, currently 100). First-N prefix, not the seeded `--sample` draw. |
| `--rounds N` | Override the config judge rounds per persona (`n_rounds`; must be ≥ 1). |
| `--judge-model MODEL` | Override the config judge model (must be in `model_options`). |
| `--dpi N` | PNG resolution (default 200). |

Outputs land under `03_Analysis/persona_realism/` (resolved via
`analysis_output_dir("persona_realism", base)`), **nested one level per country**:
`persona_realism/<country>/<combo_label>/`. That country directory contains **combination directories
only** -- no country-level aggregate file is written here. Each combo directory holds, **at its root**
(no `raw/` subdir):

| File | What it is |
|------|------------|
| `persona_XXXXX.json` | one persona's verdict cache (resumable; the expensive artefact) |
| `persona_XXXXX.jsonl` | that persona's token/timing telemetry (1:1 with the verdict cache) |
| `{combo}.json` / `{combo}.csv` | this combination's own stats + cost + hard-rules validation |
| `{combo}_personas.csv` | the per-persona tidy rows -- the `realism_ranking` contract |
| `{combo}_clashes.csv` | the per-clash tidy rows (one per persona × round × sorted attribute pair × severity, with that persona's category values) -- the second `realism_ranking` contract file |
| `{combo}_clash_explanations.csv` | the judge's free text at the same key. A side file: nothing downstream reads it, and no count depends on it |
| `typicality.png/.svg`, `clash_taxonomy.png/.svg` | this combination's two figures |

The two CSV contracts sit at different grains on purpose. A persona carries 0..N clashes, so putting
them on the per-persona row would force either a repeating group whose width depends on the data or
a lossy top-1 truncation. The per-clash row carries **no denominator** -- the base of any rate
computed from it is a count of *personas*, which belongs to the sibling file -- and the loader reads
both and reconciles them: the distinct `(persona, attribute-pair)` clashes at level *L* must equal
the summed `clash_count_s{L}` of the per-persona file, or the run raises naming both files.

### Regenerating artifacts without re-judging

`--force` **re-judges from scratch**: it truncates every verdict cache and pays the full LLM bill.
That is almost never what you want after a code or schema change. Use `--rewrite-artifacts` instead --
it rebuilds `{combo}.json`, `{combo}.csv`, `{combo}_personas.csv`, `{combo}_clashes.csv`,
`{combo}_clash_explanations.csv` and the figures from the verdict cache already on disk, at **zero
LLM cost** on a fully-cached combination:

```bash
python scripts/analyze/analyze_persona_realism.py --rewrite-artifacts
```

The zero cost is **structural, not a matter of care**: under `--rewrite-artifacts` the runner is put
in plan-only mode — it resolves the persona roster (so `n_failed` still counts personas that left no
cache file) and then returns without constructing a client or making a call. That matters because
the trap is easy to walk into: the existing caches hold **1 round** while `judge.yaml` declares
`n_rounds: 3`, so an ordinary run would dutifully *top up* every persona by two rounds — a full
re-judge in all but name. Plan-only mode logs how many personas are below the target instead of
judging them.

A run without either flag still consults the runner (its per-persona resume gate is the authority, and
is cheap when everything is cached), and rewrites artifacts only if the cache changed or the report is
missing.

All five derived files are regenerated **as a set**, under one `force` gate, so an output base is
never left mixed-generation -- half its combinations carrying a per-clash file and half not would
make the ranking's consumption set depend on which combinations happened to be rewritten.

## Ranking the combinations -- `rank_persona_realism.py`

```bash
python scripts/analyze/rank_persona_realism.py --country swedish_02
```

Outputs per country under `03_Analysis/realism_ranking/<country>/`:

| File | What it is |
|------|------------|
| `realism_ranking.json` | both axes, the factor tests, and the honesty block |
| `realism_summary.csv` | one row per competitor in rank order |
| `scb_contrast.csv` | one row per synthetic competitor vs the real population, both axes |
| `headline_map.png/.svg` | Axis A x Axis B; the real population is a plotted competitor, **not** pinned to the origin |
| `impossibility_forest.png/.svg` | every competitor's rate + bootstrap CI, rank order |
| `impossibility_heatmap.png/.svg` | the rate as a model × method grid, with the real population as a separate band beneath it. Grey `n/a` = that pair was never judged, which is **not** a rate of zero |
| `severity_heatmap_s3/s2/s1.png/.svg` | the same grid layout, one per clash severity — see below |
| `severity_drivers.csv` | **what** clashed in each cell: the attribute pairs ranked by how many of that cell's personas exhibit them, all three levels in one table with `severity` as a column — see below |
| `severity_driver_values.csv` | the same one grain finer: the category pairs (e.g. `Student × Permanent Full-time`) under each ranked attribute pair, likewise one table for all three levels |
| `severity_pair_summary_s3/s2/s1.png/.svg` | the country-wide complement of the heatmap, one per level: which attribute pairs clashed, ranked descending, with the real population as its own series — see below |
| `typicality_summary.csv` | one row per competitor: the **self-contained** typicality statistic (a function of that competitor's own judge scores alone), its bootstrap CI, **both** persona counts under distinct names, the `under_powered`/`boundary` flags, and the secondary `P(typicality ≤ k0)` column with a Wilson interval — see below |
| `typicality_histogram.csv` | the same statistic's published object: one row per `(competitor, level)` over the full 0–10 scale, so the levels nobody scored are explicit zeros |
| `typicality_heatmap.png/.svg` | that statistic as a model × method grid on a **diverging** ramp whose midpoint is the real population's own value. Four distinct fills: a value, an under-powered value (hatched), a judged competitor with no typicality-bearing persona (white, cross-hatched), an unjudged pair (grey) |
| `typicality_by_method.png/.svg` | the same statistic with methods on x in complexity order, one mark per model, and the real population as a horizontal reference line — the only figure in this task that draws it as a reference rather than a series |

### The severity dimension (reporting only)

Three extra heatmaps, one per clash level, showing **the share of a combination's personas
carrying at least one clash at that level**. Purely descriptive: it feeds no ranking, no
contrast and no significance test, and the binary `can_exist` impossibility rate is
unchanged. `severity_weights` / `impossibility_severities` stay declared-but-unwired —
wiring them would move every impossibility rate already published.

The three levels are counted **independently, not as a partition**: a persona carrying both
an S3 and an S2 appears on both figures. That is why the tidy CSV needed
`clash_count_s1/_s2/_s3` — `max_severity` alone files each persona at its worst level only,
which would silently understate every S2 prevalence.

**Direction is not uniform, and the figures say so:**

| Level | Meaning | Direction |
|---|---|---|
| **S3** | hard contradiction | defect — lower is better, red ramp |
| **S2** | near-impossible | defect — lower is better, red ramp |
| **S1** | unusual but possible | **reported, never penalised** — neutral ramp; a higher value may mean healthy reach into the tails, not a problem |

Colouring S1 on a lower-is-better ramp would assert that unusual people are defects, which
the judge's own contract explicitly denies — the same class of error as treating SCB as the
origin on Axis A.

> **Schema versions.** The per-severity columns arrived with per-persona tidy-CSV schema
> **v2**; the per-clash file is its own contract at schema **v1**, versioned separately (both
> numbers are stamped into `{combo}.json`'s provenance as `persona_csv_schema_version` and
> `clash_csv_schema_version`, so a mismatch names the file it is about). An output base whose
> `{combo}_personas.csv` predates v2 **raises** on read; one with no `{combo}_clashes.csv` at
> all is **skipped** with a reason — an absent file is a pipeline-progress state, a
> stale-schema one is corruption. Both remedies are the same command, and regenerating costs
> **zero LLM calls** — the clashes are already in the verdict caches.

### The severity drivers (also reporting only)

The heatmaps size a cell; these tables say what is in it. Per `(model × method, level)` they rank
the attribute pairs by **how many of that cell's personas exhibit them**, and beneath each pair the
category pairs that carry it. Two grains, **two files** — one per grain, all three levels in each,
carrying `severity` as a column — and the same denominator as the heatmap cell, so
`employment_status × employment_type` at `prevalence = 0.12` in a cell whose S3 rate is `0.12` says
that pair accounts for the whole cell. (The *heatmaps* remain one file per level: a figure can show
one grid, a table can hold a column.)

Four properties worth knowing before reading one:

- **`rank` is within `(competitor, severity)`.** Levels are interleaved in one file but never
  renumbered across it: a rank-1 S2 driver and a rank-1 S3 driver are both rank 1, because ranking
  them against each other would put a hard contradiction on one scale with an unusual-but-possible
  pairing. Rows are ordered `slug` → severity (S3, S2, S1) → `rank`, so a competitor's three levels
  arrive as one contiguous block. Read `n_personas`, not `rank`, when comparing anything.

- **The unit is personas, not clashes.** A clash the judge raised in three rounds of one persona
  counts that persona once. Every row carries the unit as a column.
- **The numbers are not additive and are not shares of a whole.** One persona may carry several
  distinct clashes; each clash names two attributes; and the levels are not a partition. Never a
  pie, never a 100%-stacked bar. Also a column on every row.
- **S1 rows are not defects.** `penalised` travels on every row for the same reason the S1 heatmap
  gets a neutral ramp — and it is now the *only* thing on a row that distinguishes an
  unusual-but-possible pairing from a defect, since the two sit in the same file. On the current
  Swedish data the S1 drivers read plainly as tail-reach: SCB's
  own top S1 pairs are `Married × 1-person household` and `Owner-occupied villa × Poverty` —
  unusual people, not impossible ones.

`--driver-top-n` (default 5) bounds each cell's published tail; `--driver-min-count` (default 3) is
the floor below which a driver is **suppressed and counted** rather than ranked. Both exclusion
counts, plus unconsumable combinations, personas with no successful round, and clashes whose
category values could not be joined, are reported in the JSON block and printed at the end of a run.

### The pair summary figures (the same question, country-wide)

`severity_pair_summary_s3/s2/s1.png` answer at the country level what `severity_drivers.csv`
answers per cell: at this level, **what actually clashed, ranked**. Horizontal bars, sorted
descending, at the attribute-pair grain, pooled across the synthetic combinations.

Four things about them are load-bearing:

- **They are computed from every per-clash row, not from the driver tables.** Those are already cut
  per cell by `--driver-top-n` and floored by `--driver-min-count`; aggregating a per-cell top-N
  into a country total is biased twice over — it over-weights pairs that merely clear many cells'
  cut, and it erases pairs that are broad but never locally top-ranked.
- **The real population is a separate series, never pooled into the bars.** It is an ordinary
  competitor with no reference role, but it is also one 100-persona unit against ~50 synthetic ones,
  so pooling it would both bury it and let its contribution be read as the synthetic population's.
  It is drawn as a red diamond over its own denominator, the same encoding it already has on the
  forest plot, and both series' numbers sit in aligned columns beside the axes.
- **The bars do not sum to the level's overall rate**, for the same three reasons the driver tables
  do not. The caveat is printed on the figure, not only here.
- **S1 carries the never-a-defect caption**, taken from the same per-level `direction` the S1
  heatmap's neutral ramp is chosen from.

`--pair-summary-top-n` (default 15) bounds the bars; what falls below the cut is printed on the
figure, including how many of the hidden pairs were raised **only** by the real population (those
rank at zero synthetic personas and so almost never make the cut). A level with no clash at all
renders an explaining figure rather than empty axes — on the current Swedish data the real
population raises no S3 clash whatsoever, which the S3 figure states as a column of `0.0000 n=0`
rather than as an absent series.

### The typicality axis (reporting only)

**Decision record:** [`decisions/2026-08-12-self-contained-typicality-axis.md`](decisions/2026-08-12-self-contained-typicality-axis.md).

Typicality is the richest signal the judge produces, and until now the ranking published it only as a
*distance*: `axis_b.dispersion_contrast` is `abs(measure - real_measure)`, whose absolute value is
deliberate but discards the **sign**, so a mode-collapsed competitor and an over-dispersed one look
the same in it. This axis publishes each competitor's own spread as one number, computed from that
competitor's judge scores alone. It feeds no ranking, no contrast and no significance test, changes no
number already published, and **does not replace Axis B** — that remains the tested SCB contrast.

**Three things to know before reading the figure.** Each is a way to misread it, not a footnote.

- **The denominator is the survivor subset, never `n_personas`.** A cell is computed over the personas
  that carry a typicality — a `can_exist` majority *and* a non-null mean — so a competitor with a high
  impossibility rate is measured over fewer, and differently selected, personas than Axis A ranks. Both
  counts sit on every row under distinct names (`denominator`, `n_personas`) and `n` is printed in every
  heatmap cell. The confound is measured: on `swedish_02`, `Spearman(n, dispersion) = -0.576`, so a
  dispersion cell **partly re-renders the impossibility rate**. The three "most diverse" cells are the
  n=9, n=21 and n=10 cells. `--typicality-min-n` is a floor, not a fix; read every cell against its own
  denominator.
- **The direction is interior, not monotone — this is not a score.** The block carries
  `"direction": null` as a *data field*, with the reason beside it, because there is no better end. A
  competitor scoring uniformly at the modal level has collapsed onto the modal Swede; a low-scoring one
  may be reaching the real population's tail or may simply be incoherent. Nor is SCB the ceiling: 16 of
  50 synthetic competitors on `swedish_02` are **more** dispersed than it. Direction is supplied at
  render time by the diverging ramp centred on SCB's own value, and by nothing else.
- **The dispersion is a property of *this judge under this prompt*, not of the population alone.**
  `judge_prompt.md` emits `"reasoning"` **before** `"typicality"`, and chain-of-thought-before-score is
  documented to compress the judgment distribution (Wang, Zhang & Choi, EMNLP Findings 2025,
  [arXiv:2503.03064](https://arxiv.org/abs/2503.03064)) — the prompt format shrinks the very spread
  being measured. Only 4 of the 11 levels carry verbal anchors (9–10, 5, 1, 0), which invites
  round-number clustering (Stureborg et al., [arXiv:2405.01724](https://arxiv.org/abs/2405.01724)).
  Neither is fixable without moving `prompt_template_sha256` and forcing a full re-judge, so both are
  held constant across every judged combination and recorded here instead. Compare cells against each
  other; do not read an absolute dispersion as the population's.

**The statistic.** Default `iov` — Berry-Mielke's index of ordinal variation, in the **dispersion**
orientation: `0` = all mass on one level (total collapse), `1` = 50/50 at the two extremes, higher =
more dispersed. It reads only the interior CDF, so it is invariant to any strictly increasing
relabelling of the 11 levels, and it is the one candidate that separates a `{0,10}` split (1.000) from
a `{9,10}` split (0.100) — the mode-collapse distinction the axis exists to draw, on which entropy and
Simpson are identical. Because published implementations of this family point in opposite directions,
the orientation travels **in the output**: `statistic_label` states the endpoints on the block and on
every row.

`--typicality-metric mean` selects the mean level instead. It measures **location**, not dispersion,
and assumes the 0–10 levels are equally spaced — an interval claim about an ordinal scale. Selecting
it fills `statistic_caveat` on every emitted row; it is not a drop-in for the default.

| Flag | Meaning |
|------|---------|
| `--typicality-metric` | `iov` (default) or `mean`/`mean_level`. |
| `--typicality-min-n` | Typicality-bearing personas a cell needs to be read as powered. Default 30 (excludes 5 of the 50 `swedish_02` cells). Below it the cell is flagged `under_powered`, hatched on the heatmap, drawn hollow on the method figure, and counted in the block's `excluded` map — **never dropped**, and never confused with an unjudged pair. |
| `--typicality-tail-threshold` | `k0` of the secondary `P(typicality ≤ k0)` column, Wilson interval. Default 5 — deliberately not the per-combination chart's `reliability.tail_threshold` of 3.0, at which a sixth of the cells sit at exactly 0.000. |

**Reading a cell that looks degenerate.** A competitor whose personas all sit on one level gets a
percentile bootstrap interval of exactly `[0, 0]`, published with `boundary: true`. That is honest
computationally and has zero coverage whenever true dispersion is above zero — at a boundary the
bootstrap is *inconsistent*, not merely inaccurate (Andrews 2000). It is flagged rather than patched:
a smoothed interval would be invisibly wrong instead of visibly degenerate. A competitor with **no**
typicality-bearing persona is `null` with `status: no_typicality`, never `0.0`, which is a real
measurement.

The statistic is never folded with the impossibility rate into a composite realism score — different
denominators, different directions — and `non_composite` says so as a field.

> **Round-level caveat, and an `n_rounds` provenance drift worth knowing before you trust the number.**
> The statistic is computed over **per-persona mean** typicalities, rounded back to integer levels
> (`n_non_integer_means` counts the personas that rounding moved). At one successful round per persona
> every mean is already an integer and the rounding is a no-op — which is the state the current
> `swedish_02` base is essentially in, and it is why nothing here reports round-to-round reliability.
> The three `n_rounds` numbers on that base do **not** agree, and only one of them is evidence:
> `judge.yaml` declares `n_rounds: 3`; the *stamped* `provenance.n_rounds` reads **5** in 49 of the 51
> combinations and **2** in the other two; the cached rounds themselves are **1** for 4351 personas and
> **2** for 200. The stamp is written from config at artifact-rewrite time and is not a record of what
> was judged. Two consequences: no reliability figure (ICC / Krippendorff's α) can be read off this
> base, and because the ranking's homogeneity gate reads `n_rounds` from that same stamped provenance,
> a whole-country run over this base **raises** on the 5-vs-2 mismatch until it is reconciled. When a
> base is genuinely re-judged at N ≥ 2, the protocol is to compute the statistic **once per round**
> (each round is a complete, genuinely integer, n-persona ordinal sample), report the across-round mean
> and keep the round-to-round spread as a separate uncertainty component — pooling raw round integers
> inflates dispersion by 3–10% and the inflation does not shrink as N grows.

> **Reproducibility, stated honestly.** The JSON block, both CSVs and the **PNG** figures are
> byte-reproducible: two runs, and two different competitor orderings, emit identical bytes. The
> **SVG** siblings are not, and no figure in this repository is — matplotlib stamps every SVG with a
> `dc:date` creation timestamp and salts per-save element ids. That is a property of the writer, not of
> this axis.

Two gates run before any statistic, because both failure modes produce plausible-looking wrong
numbers:

- **Completeness.** A combination is consumed only if its report exists, its per-persona CSV exists,
  and the CSV's row count equals the report's `n_personas`. A partial directory (verdict caches but
  no report -- several exist on any real output base) is skipped with a machine-readable reason, or
  raises under `--strict`.
- **Homogeneity.** Every consumed combination must share one `judge_model`, `prompt_template_sha256`
  and `n_rounds`, read from the stamped provenance rather than from current config. A mismatch
  **raises**, naming the offending combination: ranking units judged by different judges measures the
  judges, not the units.

`realism_ranking.json` carries the mandatory honesty fields: the correction name (`holm`) on every
family of tests, a denominator beside every rate, `skipped_combinations` and `skipped_tests` with
reasons, the `pseudo_replication` and `single_run_per_combination` caveats, and the bootstrap seed
plus resolved library versions.

## Config knobs — `config/analysis/persona_realism/`

All judge behaviour is config-driven; a missing or malformed value **raises** (no silent default).
The whole `reliability:` block is read through `JudgeConfig.reliability_value()`, which has **no
default argument** -- each of those keys moves a published number, so an in-code fallback could let
the emitted artifacts disagree with the config that describes them.

`judge.yaml`:

| Key | Purpose |
|-----|---------|
| `judge_model` | Raw string passed to `claude -p ... --model`; must match a row in `model_pricing.yaml`. Default `claude-sonnet-5` (best coherence-judge tier + low latency + cost). |
| `model_options` | GUI dropdown (Claude family). `judge_model` must be one of these; Fable-5 is the slowest/most-expensive selectable option. |
| `n_rounds` | Independent judge calls per persona (default 3). N≥2 is required for any reliability or per-persona SD. |
| `temperature` | Judge sampling temperature (default 0.0 — cold, for reproducibility). |
| `severity_weights` | **Declared but not wired.** Validated and stamped into provenance, but no computation reads it -- impossibility is decided solely by the `can_exist` majority (`reduce.possible_majority`). Every report carries a `severity_config_status` note saying so. |
| `impossibility_severities` | **Declared but not wired** (same as above). Wiring severity gating into `reduce_persona` would change every existing impossibility rate and is a separate decision. |
| `sample_size` | Personas judged per **synthetic** combination (nullable → all). Caps judge cost via seeded sampling. |
| `real_sample_size` | Personas judged for the **real reference** combo (`real_{country}`) only (nullable → all; default 100). The real API-sourced population (~10,000) dwarfs the synthetic combos, so it is capped independently. Selected as a deterministic **first-N prefix** (indices 0..N-1, not seeded random): the SCB population is already an i.i.d. sample, so a prefix is a valid random subsample, is reproducible across runs, and reuses already-cached prefix personas. |
| `bootstrap` | `{iterations, seed, ci_level}` for the impossibility-rate CI (seed recorded in run metadata). |
| `reliability.typicality_level` | Krippendorff's-α measurement level for typicality: `ordinal` or `interval`. `can_exist` reliability is always nominal (not configurable). |
| `reliability.tail_threshold` | Mean typicality at or below which a persona counts toward `tail_coverage`, and below which the typicality chart shades its bars (3.0 on the 0-10 scale). |
| `reliability.variance_center` | Levene centring for the Axis-B variance-equality test: `median` (Brown-Forsythe, robust) or `mean` (classic Levene). Read by `realism_ranking`. |
| `workers` | Parallel judge-call fan-out (ThreadPool `max_workers`). |
| `timeout_seconds` | Per-call subprocess wall-clock timeout (default 600). Threaded into the `ClaudeCodeClient` the judge factory builds; 600 s is a generous ceiling that also covers the slowest *selectable* judge (a Fable/Opus single turn can run for minutes) if you select it — Sonnet, the default, finishes in seconds. The client's own 120 s default is too tight for the slow tiers and is raised only for the judge. |
| `prompt_template` | Path (relative to the config dir) to the system+user template. |

`judge_prompt.md` — the constraint-scaffolded system + user template (biological/legal/temporal
categories, anchored typicality exemplars, strict JSON output schema, explicit "unusual ≠ impossible"
guardrail).

`hard_rules.yaml` — config-driven deterministic `incompatible_pair` checks (see below).

## Reliability is self-consistency, not validity

The ICC / Krippendorff's α metric measures the judge's agreement **with itself** across the N rounds
— its precision/consistency, **not** its correctness. Internal validity is **not** established by it.
The only validity anchor is `hard_rules.yaml`: on a seeded subset the aggregation layer evaluates
those deterministic structural rules and compares their verdict to the judge's `can_exist`, reporting
a 2×2 confusion + agreement + recall-on-rule-impossibilities. Read the reliability number as "the
judge is repeatable", never as "the judge is right".

## Cost sizing

The judge issues roughly **N × personas × combinations** LLM calls (N = `n_rounds`, default 3), so a
full run over every combination is large. Controls:

- `sample_size` (or `--sample`) caps personas per combination via seeded sampling.
- `n_rounds` (or `--rounds`) is the N multiplier — lowering it cuts cost proportionally but N ≥ 2 is
  required for any reliability or per-persona SD number. `n_rounds` is a **target count of successful
  rounds**: resume is round-count-aware, so re-running a judged combo with a *higher* `--rounds` **tops
  up** each persona — it judges only the shortfall and appends the new rounds to both the verdict json
  and the telemetry jsonl (round numbering continues from the existing count). A persona is skipped
  only once its cache already holds `>= n_rounds` successful rounds; `--force` re-judges from scratch.
- `workers` (or `--workers`) sets the parallel fan-out width, and `timeout_seconds` bounds each call's
  wall clock; neither changes total cost, only wall-clock time and per-call failure behaviour.
- The per-persona combo-root cache makes runs **resumable**: a re-run without `--force` tops up
  under-target personas and skips those already at `>= n_rounds`. The per-persona gate is the sole
  authority — the CLI always consults the runner (cheap when everything is cached: file-existence +
  round-count reads, no LLM call), so a `--rounds 1` run can be topped up to `--rounds 2` even though
  the combo's report already exists. The combo's artifacts are re-written only when the runner actually
  wrote or topped up a persona, when the report is missing, or under `--force`; otherwise nothing
  changed on disk and the existing artifacts stand.
- Per-combo cost (tokens + USD) is priced from `config/analysis/model_pricing.yaml`; a missing
  pricing row for the judge model **raises** (fail-fast).
- **Cache tokens:** the judge prompt is prompt-cached, so the client sees `input_tokens ≈ 2` (the
  uncached remainder) while the bulk lands in cache. The cost chain additionally records
  `cache_read_tokens` / `cache_creation_tokens` and prices them against the base input rate via the
  `cache_multipliers: {read, write}` block in `model_pricing.yaml` (fail-fast if cache tokens are
  present but the block is absent).

**Cost-coverage on resume:** telemetry is now **per-persona** (`persona_XXXXX.jsonl`, one file per
persona, append-accumulated across top-up passes) and 1:1 with the verdict cache, so a resumed run's
cost report covers **every** cached persona — `cost_coverage.status` is reliably `complete` on resume
(it was chronically `partial` under the old single truncated `llm_interactions.jsonl`). The marker
still carries `judged_this_run` (number of `persona_*.jsonl` files) / `total_personas`; `partial` now
fires only on a genuine per-file gap (fewer telemetry files than cached personas) and `none` when no
telemetry is present. Because each persona's `.jsonl` accumulates all of its passes' calls, the summed
USD is the true cumulative cost even across a `rounds=1` → `rounds=2` top-up.

## Judge-model availability smoke-test

The default judge is `claude-sonnet-5` (best coherence-judge tier, low latency, low cost). Any judge
model's availability is **account-dependent** — smoke-test the one you intend to use before a large
run:

```bash
claude -p "ping" --model claude-sonnet-5 --output-format json
```

**If you select Fable** (`--judge-model claude-fable-5`, the slowest/most-expensive selectable
option) — smoke-test it too, since its availability is plan-dependent:

```bash
claude -p "ping" --model claude-fable-5 --output-format json
```

Fable/Opus single turns can run for **minutes** on hard personas, which is why `timeout_seconds`
defaults to 600 (a ceiling generous enough for the slow tiers if chosen; Sonnet finishes in seconds,
and the client's own 120 s default is raised only for the judge). A round that times out or errors
is recorded as a **failed** round — kept distinct from a judged "possible" verdict — and only failed
rounds are retried; the impossibility rate is gated on successful calls and the dropped count is
logged.

If a model does not resolve, pick another entry from `model_options` (`--judge-model
claude-opus-4-8` / `claude-haiku-4-5` / `claude-fable-5`); every dropdown model already has a
pricing row in `model_pricing.yaml`.

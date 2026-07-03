# Reading the C2ST: how the classifier two-sample test is built

The Classifier Two-Sample Test (C2ST) is the strongest single fidelity check in the stack.
Its logic: **if a classifier cannot tell real profiles from synthetic ones, the two are
statistically indistinguishable.** This note walks the four steps behind the two headline
numbers — `auc` and `p_value` — with a worked example and a visual for each, because several
non-obvious steps (class balancing, the rank-based AUC, the permutation p-value, the two
backends) determine what those numbers mean. It lives alongside the
[TV ½-factor](tv-distance-half-factor.md), [KL bits & log-ratio](kl-divergence-bits-and-log.md),
and [coherence-score](coherence-score-explained.md) notes. Code: `multivariate.py:c2st` and
`evaluator.py:_compute_c2st`.

## The running example

To make each step concrete, one example runs through the whole note:

- **Real A** = 10,000 people, **synthetic B** = 1,000 people (real vastly outnumbers synthetic —
  the usual case).
- Four illustrative attributes: `age_group` (4 categories), `sex` (2), `education_level` (3),
  `employment_status` (3) → a **12-column** one-hot space. (The real Swedish scheme has 15
  attributes and far more columns; four keeps the pictures legible.)
- The observed cross-validated AUC comes out **0.52**, and the permutation test returns
  **p ≈ 0.40** — a faithful synthetic population.

## Step 1 — encode the whole profile (one-hot)

Each individual becomes a fixed-width feature vector via `one_hot_encode`. Columns are laid
out block-by-block in `scheme.attributes` order; within a block, one column per category in
`scheme.categories[attr]` order, so the encoding is **identical across both populations**. A
value outside an attribute's category set — a synthetic-only value or a `None` — leaves that
attribute's whole block **all-zero** (an implicit "other"), rather than growing the matrix. So
the classifier sees complete joint profiles, not one attribute at a time.

**Example.** A real 35-year-old employed woman with a tertiary degree encodes to a 12-long
vector with exactly **four** 1s — one lit column per attribute block. A synthetic person whose
`employment_status` is `"student"` (not a scheme category) gets an **all-zero employment
block**: the classifier simply sees "none of the known employment categories."

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 210" role="img" aria-label="One profile encoded as a 12-column one-hot vector, one lit cell per attribute block">
  <text x="20" y="20" class="mono ax">ONE PROFILE &#8594; ONE FIXED-WIDTH VECTOR (4 attributes &#8594; 12 columns)</text>
  <!-- profile chips -->
  <g font-size="12">
    <rect x="20"  y="34" width="118" height="26" rx="6" fill="var(--surface)" stroke="var(--line)"/>
    <text x="30"  y="51">age: 30&#8211;39</text>
    <rect x="146" y="34" width="70"  height="26" rx="6" fill="var(--surface)" stroke="var(--line)"/>
    <text x="156" y="51">sex: F</text>
    <rect x="224" y="34" width="140" height="26" rx="6" fill="var(--surface)" stroke="var(--line)"/>
    <text x="234" y="51">edu: Tertiary</text>
    <rect x="372" y="34" width="150" height="26" rx="6" fill="var(--surface)" stroke="var(--line)"/>
    <text x="382" y="51">emp: Employed</text>
  </g>
  <!-- vector cells: 4 + 2 + 3 + 3 -->
  <g font-size="11" text-anchor="middle">
    <!-- age block: cells 30,64,98,132 ; lit = 2nd (64) -->
    <rect x="30"  y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="45"  y="124">0</text>
    <rect x="64"  y="104" width="30" height="30" rx="4" fill="var(--real)"/><text x="79" y="124" fill="#fff" class="hi">1</text>
    <rect x="98"  y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="113" y="124">0</text>
    <rect x="132" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="147" y="124">0</text>
    <!-- sex block: 176,210 ; lit = 2nd (210) -->
    <rect x="176" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="191" y="124">0</text>
    <rect x="210" y="104" width="30" height="30" rx="4" fill="var(--real)"/><text x="225" y="124" fill="#fff" class="hi">1</text>
    <!-- edu block: 254,288,322 ; lit = 3rd (322) -->
    <rect x="254" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="269" y="124">0</text>
    <rect x="288" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="303" y="124">0</text>
    <rect x="322" y="104" width="30" height="30" rx="4" fill="var(--real)"/><text x="337" y="124" fill="#fff" class="hi">1</text>
    <!-- emp block: 366,400,434 ; lit = 1st (366) -->
    <rect x="366" y="104" width="30" height="30" rx="4" fill="var(--real)"/><text x="381" y="124" fill="#fff" class="hi">1</text>
    <rect x="400" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="415" y="124">0</text>
    <rect x="434" y="104" width="30" height="30" rx="4" fill="var(--surface)" stroke="var(--line)"/><text x="449" y="124">0</text>
  </g>
  <!-- block braces / labels -->
  <g class="ax mono" font-size="11" text-anchor="middle">
    <text x="96"  y="152">age_group</text>
    <text x="208" y="152">sex</text>
    <text x="303" y="152">education</text>
    <text x="415" y="152">employment</text>
  </g>
  <!-- out-of-vocab illustration -->
  <text x="30" y="184" font-size="11.5" fill="var(--muted)">out-of-vocabulary value (e.g. emp = "student") &#8594; whole block stays</text>
  <g>
    <rect x="470" y="172" width="24" height="16" rx="3" fill="var(--surface)" stroke="var(--line)"/>
    <rect x="496" y="172" width="24" height="16" rx="3" fill="var(--surface)" stroke="var(--line)"/>
    <text x="470" y="200" font-size="10.5" fill="var(--muted)">0 0 0 (other)</text>
  </g>
</svg>
</div>
<figcaption>One person &#8594; a 12-long vector with one lit cell per attribute block. The same
column layout is used for <b>both</b> populations, so the classifier compares like with like.</figcaption>
</figure>

## Step 2 — balance the classes

Real usually vastly outnumbers synthetic, and a classifier can score a high AUC just by
exploiting that imbalance. So the classes are **balanced by subsampling the larger down** to:

```
balanced_n = min(n_real, n_syn)
```

drawn **without replacement**. This is repeated `n_repeats = 5` times (fresh subsample each
time) and the results averaged. If `balanced_n < 2` (a tiny or failed synthetic population)
both numbers degrade to `NaN` without error.

**Example.** With `n_real = 10,000` and `n_syn = 1,000`, `balanced_n = 1,000`: each repeat
draws 1,000 real rows to sit beside all 1,000 synthetic rows — a 50/50 mix the classifier
can't game by guessing "real." Five such balanced draws are averaged.

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 200" role="img" aria-label="Balancing: subsample 10000 real down to 1000 to match 1000 synthetic">
  <text x="20" y="22" class="mono ax">BEFORE &#183; imbalanced</text>
  <line x1="30" y1="165" x2="250" y2="165" stroke="var(--line-strong)"/>
  <rect x="60"  y="45"  width="54" height="120" rx="4" fill="var(--real)"/>
  <text x="87"  y="182" text-anchor="middle" font-size="11" fill="var(--muted)">real</text>
  <text x="87"  y="40"  text-anchor="middle" font-size="11" class="mono">10,000</text>
  <rect x="150" y="135" width="54" height="30"  rx="4" fill="var(--syn)"/>
  <text x="177" y="182" text-anchor="middle" font-size="11" fill="var(--muted)">syn</text>
  <text x="177" y="130" text-anchor="middle" font-size="11" class="mono">1,000</text>
  <text x="275" y="110" font-size="24" fill="var(--muted)">&#8594;</text>
  <text x="320" y="22" class="mono ax">AFTER &#183; balanced (&#215;5 repeats, averaged)</text>
  <line x1="330" y1="165" x2="540" y2="165" stroke="var(--line-strong)"/>
  <rect x="365" y="105" width="54" height="60" rx="4" fill="var(--real)"/>
  <text x="392" y="182" text-anchor="middle" font-size="11" fill="var(--muted)">real*</text>
  <text x="392" y="100" text-anchor="middle" font-size="11" class="mono">1,000</text>
  <rect x="455" y="105" width="54" height="60" rx="4" fill="var(--syn)"/>
  <text x="482" y="182" text-anchor="middle" font-size="11" fill="var(--muted)">syn</text>
  <text x="482" y="100" text-anchor="middle" font-size="11" class="mono">1,000</text>
</svg>
</div>
<figcaption>Subsample the larger class down to <b>balanced_n = min(n_real, n_syn) = 1,000</b>
(heights schematic). Repeated 5&#215; with fresh draws; the AUC and p-value are the means.</figcaption>
</figure>

## Step 3 — cross-validated AUC

Per repeat, real (label `0`) and synthetic (label `1`) are stacked and run through
**stratified k-fold cross-validation** (`eff_folds = max(2, min(folds, balanced_n))`, folds
from config, default 5). Every row is scored while held out, and the pooled out-of-fold scores
give one ROC-AUC. The AUC itself is computed by the **rank-based Mann–Whitney identity** (not a
threshold sweep):

```
AUC = ( Σ ranks(synthetic scores) − n_syn·(n_syn + 1)/2 ) / (n_syn · n_real)
```

with tie-aware average ranks (`scipy.rankdata`). A useful consequence: if the two populations
are identical the scores are effectively constant, ties dominate, and the AUC comes out
**exactly 0.5** — no spurious signal from a degenerate model.

**Example (the rank formula on 6 people).** Say the held-out "more synthetic" scores are, for
3 real and 3 synthetic people: real `{0.20, 0.40, 0.55}`, synthetic `{0.30, 0.60, 0.70}`.
Ranking all six low→high, the synthetic scores land at ranks 2, 5, 6 (sum = 13). Then
`AUC = (13 − 3·4/2) / (3·3) = (13 − 6)/9 = 0.78`. On our running example the classifier does
far worse than that — `AUC ≈ 0.52`, a whisker above chance.

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 220" role="img" aria-label="5-fold cross-validation grid and the resulting ROC curve near the diagonal">
  <!-- CV grid -->
  <text x="24" y="20" class="mono ax">5-FOLD CV &#183; each row scores 1 held-out fold</text>
  <g>
    <!-- 5 rows x 5 cols; diagonal = test -->
    <!-- row0 --><rect x="30"  y="34" width="26" height="20" rx="3" fill="var(--syn)"/><rect x="58" y="34" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="86" y="34" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="114" y="34" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="142" y="34" width="26" height="20" rx="3" fill="var(--real-soft)"/>
    <!-- row1 --><rect x="30"  y="58" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="58" y="58" width="26" height="20" rx="3" fill="var(--syn)"/><rect x="86" y="58" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="114" y="58" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="142" y="58" width="26" height="20" rx="3" fill="var(--real-soft)"/>
    <!-- row2 --><rect x="30"  y="82" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="58" y="82" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="86" y="82" width="26" height="20" rx="3" fill="var(--syn)"/><rect x="114" y="82" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="142" y="82" width="26" height="20" rx="3" fill="var(--real-soft)"/>
    <!-- row3 --><rect x="30"  y="106" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="58" y="106" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="86" y="106" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="114" y="106" width="26" height="20" rx="3" fill="var(--syn)"/><rect x="142" y="106" width="26" height="20" rx="3" fill="var(--real-soft)"/>
    <!-- row4 --><rect x="30"  y="130" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="58" y="130" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="86" y="130" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="114" y="130" width="26" height="20" rx="3" fill="var(--real-soft)"/><rect x="142" y="130" width="26" height="20" rx="3" fill="var(--syn)"/>
  </g>
  <g class="viz-legend" font-size="10.5"></g>
  <rect x="30" y="164" width="12" height="12" rx="3" fill="var(--syn)"/><text x="48" y="174" font-size="11" fill="var(--muted)">test fold</text>
  <rect x="110" y="164" width="12" height="12" rx="3" fill="var(--real-soft)"/><text x="128" y="174" font-size="11" fill="var(--muted)">train folds</text>
  <!-- ROC -->
  <text x="320" y="20" class="mono ax">POOLED ROC</text>
  <line x1="330" y1="196" x2="330" y2="40" stroke="var(--line-strong)"/>
  <line x1="330" y1="196" x2="510" y2="196" stroke="var(--line-strong)"/>
  <line x1="330" y1="196" x2="510" y2="40" stroke="var(--line-strong)" stroke-dasharray="5 4"/>
  <text x="455" y="132" transform="rotate(-45 455 132)" font-size="10.5" fill="var(--muted)">chance 0.5</text>
  <polyline points="330,196 375,178 420,150 465,104 510,40" fill="none" stroke="var(--real)" stroke-width="2.5"/>
  <circle cx="420" cy="150" r="3.5" fill="var(--real)"/>
  <text x="510" y="214" text-anchor="end" font-size="11" fill="var(--muted)">FPR &#8594;</text>
  <text x="332" y="36" font-size="11" fill="var(--muted)">TPR</text>
  <text x="360" y="80" font-size="12" class="mono hi" fill="var(--real)">AUC &#8776; 0.52</text>
</svg>
</div>
<figcaption>Left: 5-fold CV rotates which fold is held out; every row is scored exactly once,
out of fold. Right: pooling those scores gives one ROC — here it hugs the diagonal
(<b>AUC &#8776; 0.52</b>), the faithful-synthetic outcome.</figcaption>
</figure>

## Step 4 — the permutation p-value

An AUC slightly above 0.5 could be noise. To test that, the labels are **shuffled**
`n_permutations = 200` times; for each shuffle the whole CV-AUC is recomputed, and the test
counts how many permuted AUCs reach or exceed the observed one. The p-value uses the standard
**add-one** estimator:

```
p_value = (1 + #{ perm AUC ≥ observed AUC }) / (1 + n_permutations)
```

Adding 1 to numerator and denominator means the p-value is never exactly 0 and is bounded below
by `1/201 ≈ 0.005`. A **high p-value is good**: it says an AUC above 0.5 is not distinguishable
from chance.

**Example.** Across the 200 shuffles, suppose 79 produce a CV-AUC ≥ 0.52. Then
`p = (1 + 79) / (1 + 200) = 80/201 ≈ 0.40` — the observed 0.52 sits comfortably inside the
null, so we **cannot reject "indistinguishable"** (good). Had the AUC been 0.95, essentially no
shuffle would reach it: `p = (1 + 0)/201 ≈ 0.005`.

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 210" role="img" aria-label="Null distribution of permuted AUCs around 0.5 with the observed AUC marked">
  <line x1="60" y1="170" x2="520" y2="170" stroke="var(--line-strong)"/>
  <!-- null-distribution bars around 0.5 ; bars at/above observed 0.52 highlighted -->
  <g>
    <rect x="119" y="150" width="13" height="20"  fill="var(--real-soft)"/>
    <rect x="132" y="135" width="13" height="35"  fill="var(--real-soft)"/>
    <rect x="145" y="115" width="13" height="55"  fill="var(--real-soft)"/>
    <rect x="159" y="90"  width="13" height="80"  fill="var(--real-soft)"/>
    <rect x="172" y="70"  width="13" height="100" fill="var(--real-soft)"/>
    <rect x="185" y="60"  width="13" height="110" fill="var(--real-soft)"/>
    <!-- observed 0.52 and rightward = the ">= observed" tail -->
    <rect x="198" y="70"  width="13" height="100" fill="var(--syn-soft)"/>
    <rect x="211" y="90"  width="13" height="80"  fill="var(--syn-soft)"/>
    <rect x="224" y="115" width="13" height="55"  fill="var(--syn-soft)"/>
    <rect x="238" y="135" width="13" height="35"  fill="var(--syn-soft)"/>
    <rect x="251" y="150" width="13" height="20"  fill="var(--syn-soft)"/>
  </g>
  <!-- observed marker at x(0.52)=204.6 -->
  <line x1="205" y1="52" x2="205" y2="178" stroke="var(--good)" stroke-width="2"/>
  <text x="205" y="46" text-anchor="middle" font-size="11" class="mono hi" fill="var(--good)">observed 0.52</text>
  <text x="300" y="96" font-size="11.5" fill="var(--muted)">shaded area = perms &#8805; observed</text>
  <text x="300" y="114" font-size="11.5" class="mono" fill="var(--ink)">p = (1+79)/201 &#8776; 0.40  &#10003; good</text>
  <!-- 0.95 tail marker at x(0.95)=487 -->
  <line x1="487" y1="70" x2="487" y2="178" stroke="var(--bad)" stroke-width="2" stroke-dasharray="4 3"/>
  <text x="487" y="64" text-anchor="middle" font-size="11" class="mono" fill="var(--bad)">0.95</text>
  <text x="487" y="196" text-anchor="middle" font-size="10.5" fill="var(--bad)">p&#8776;0.005</text>
  <!-- axis ticks -->
  <text x="191" y="188" text-anchor="middle" class="ax mono">0.5</text>
  <text x="60"  y="188" class="ax mono">0.3</text>
  <text x="520" y="188" text-anchor="end" class="ax mono">1.0</text>
  <text x="290" y="208" text-anchor="middle" font-size="11" fill="var(--muted)">permuted AUC (null distribution)</text>
</svg>
</div>
<figcaption>The observed AUC (green) sits inside the bulk of AUCs from shuffled labels, so a
large fraction of permutations match or beat it &#8594; <b>high p</b> &#8594; indistinguishable.
An AUC out in the tail (0.95, red) is beaten by almost no shuffle &#8594; tiny p.</figcaption>
</figure>

## The two backends

`method` resolves to the backend actually used, reported in the `method` field:

| `method` config | Backend | What runs |
|-----------------|---------|-----------|
| `"sklearn"` / `"auto"` | **sklearn** if importable, else falls back to mmd | cross-validated **logistic regression** (`LogisticRegression(max_iter=1000)`, `predict_proba`) |
| `"mmd"` | **mmd** (numpy/scipy only) | nearest-centroid / **linear-MMD** surrogate: direction `μ_syn − μ_real` from the training rows, each held-out row scored by its projection onto it |

Any other value raises. The SCB scheme sets `method="sklearn"`, so with the `[analysis]` extra
installed you get logistic-regression AUCs; without scikit-learn the module still runs via the
MMD fallback. Config defaults when the `c2st` block is absent: `folds=5, method="auto",
seed=0`; the primitive's own defaults `n_repeats=5, n_permutations=200` are used because the
evaluator passes only method/folds/seed.

## How to read the pair of numbers

- **`auc` ≈ 0.5** → indistinguishable (best); `auc → 1.0` → trivially separable (the joint
  profile is clearly wrong). This is the direction that matters — lower is better.
- **`p_value` high** → cannot reject "indistinguishable" (good); low → the separability is
  real.
- **`balanced_n`** tells you how much data actually drove the test (the smaller population's
  size); a very small `balanced_n` means treat both numbers cautiously.
- Because AUC is bounded below at 0.5 in interpretation but the raw statistic can dip slightly
  under 0.5 on noise, read "≈ 0.5" as the target, not "exactly 0.5."

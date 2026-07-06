# k-fold cross-validation (inside the C2ST)

Step 3 of the [C2ST](c2st-explained.md) scores its classifier with **stratified k-fold
cross-validation** rather than training and testing on the same rows. This note explains what
that means, why it is essential for an honest AUC, and how the folds are built — with a worked
example and a visual. It is a sub-note of the C2ST explainer.

## The problem it solves

If you train a classifier and then measure its AUC **on the same rows it learned from**, the
score is optimistic: a flexible model can partly *memorise* the training data and look better
than it will on unseen people. For the C2ST that is fatal — an inflated AUC would read as "real
and synthetic are separable" when the classifier was really just recognising rows it had
already seen. Cross-validation fixes this by always scoring rows the model **did not train on**.

## How k-fold works

Split the balanced sample into `k` equal parts ("folds"). Then run `k` rounds; in each round:

1. **Hold out** one fold as the test set.
2. **Train** the classifier on the other `k − 1` folds.
3. **Score** the held-out fold (predict how "synthetic" each held-out row looks).

Every row is held out **exactly once**, so after `k` rounds every row has one **out-of-fold**
score. Those pooled scores — all genuinely out-of-sample — are what the ROC-AUC is computed
from. The pipeline uses `k = eff_folds = max(2, min(folds, balanced_n))` (config `folds`,
default 5); the `min` guards against asking for more folds than there are rows.

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 250" role="img" aria-label="Five rounds of 5-fold cross-validation; each fold is the held-out test set exactly once">
  <text x="20" y="18" class="mono ax">5 ROUNDS &#215; 5 FOLDS &#183; each fold is the test set exactly once</text>
  <!-- column headers -->
  <g class="ax mono" font-size="10.5" text-anchor="middle">
    <text x="142" y="42">fold 1</text><text x="190" y="42">fold 2</text><text x="238" y="42">fold 3</text><text x="286" y="42">fold 4</text><text x="334" y="42">fold 5</text>
  </g>
  <!-- rows: round r, test cell = diagonal -->
  <g font-size="10.5" text-anchor="middle">
    <!-- round 1 (test=fold1) -->
    <text x="70" y="72" class="mono ax" text-anchor="end">round 1</text>
    <rect x="120" y="54" width="44" height="28" rx="3" fill="var(--syn)"/><text x="142" y="72" fill="#fff" class="hi">test</text>
    <rect x="168" y="54" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="190" y="72" fill="var(--muted)">train</text>
    <rect x="216" y="54" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="238" y="72" fill="var(--muted)">train</text>
    <rect x="264" y="54" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="286" y="72" fill="var(--muted)">train</text>
    <rect x="312" y="54" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="334" y="72" fill="var(--muted)">train</text>
    <!-- round 2 -->
    <text x="70" y="108" class="mono ax" text-anchor="end">round 2</text>
    <rect x="120" y="90" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="142" y="108" fill="var(--muted)">train</text>
    <rect x="168" y="90" width="44" height="28" rx="3" fill="var(--syn)"/><text x="190" y="108" fill="#fff" class="hi">test</text>
    <rect x="216" y="90" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="238" y="108" fill="var(--muted)">train</text>
    <rect x="264" y="90" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="286" y="108" fill="var(--muted)">train</text>
    <rect x="312" y="90" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="334" y="108" fill="var(--muted)">train</text>
    <!-- round 3 -->
    <text x="70" y="144" class="mono ax" text-anchor="end">round 3</text>
    <rect x="120" y="126" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="142" y="144" fill="var(--muted)">train</text>
    <rect x="168" y="126" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="190" y="144" fill="var(--muted)">train</text>
    <rect x="216" y="126" width="44" height="28" rx="3" fill="var(--syn)"/><text x="238" y="144" fill="#fff" class="hi">test</text>
    <rect x="264" y="126" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="286" y="144" fill="var(--muted)">train</text>
    <rect x="312" y="126" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="334" y="144" fill="var(--muted)">train</text>
    <!-- round 4 -->
    <text x="70" y="180" class="mono ax" text-anchor="end">round 4</text>
    <rect x="120" y="162" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="142" y="180" fill="var(--muted)">train</text>
    <rect x="168" y="162" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="190" y="180" fill="var(--muted)">train</text>
    <rect x="216" y="162" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="238" y="180" fill="var(--muted)">train</text>
    <rect x="264" y="162" width="44" height="28" rx="3" fill="var(--syn)"/><text x="286" y="180" fill="#fff" class="hi">test</text>
    <rect x="312" y="162" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="334" y="180" fill="var(--muted)">train</text>
    <!-- round 5 -->
    <text x="70" y="216" class="mono ax" text-anchor="end">round 5</text>
    <rect x="120" y="198" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="142" y="216" fill="var(--muted)">train</text>
    <rect x="168" y="198" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="190" y="216" fill="var(--muted)">train</text>
    <rect x="216" y="198" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="238" y="216" fill="var(--muted)">train</text>
    <rect x="264" y="198" width="44" height="28" rx="3" fill="var(--real-soft)"/><text x="286" y="216" fill="var(--muted)">train</text>
    <rect x="312" y="198" width="44" height="28" rx="3" fill="var(--syn)"/><text x="334" y="216" fill="#fff" class="hi">test</text>
  </g>
  <!-- pooling arrow -->
  <text x="380" y="120" font-size="22" fill="var(--muted)">&#8594;</text>
  <text x="410" y="112" font-size="11.5" fill="var(--ink)">pool the 5 held-out</text>
  <text x="410" y="128" font-size="11.5" fill="var(--ink)">score-sets &#8594;</text>
  <text x="410" y="146" font-size="13" class="mono hi" fill="var(--real)">one ROC-AUC</text>
</svg>
</div>
<figcaption>Down the diagonal, each fold takes its turn as the held-out <b>test</b> set while the
model trains on the rest. Every row is scored exactly once, out of fold; the five held-out
score-sets pool into a single AUC.</figcaption>
</figure>

## "Stratified" — folds keep the class balance

A plain random split could, by chance, land nearly all synthetic rows in one fold. **Stratified**
k-fold splits **each class separately** and recombines, so every fold carries (almost) the same
real/synthetic ratio as the whole — here 50/50, because Step 2 already balanced the classes.
This keeps every training set and every test set well-posed (no fold is all-real or
all-synthetic).

<figure class="viz">
<div class="plot-wrap">
<svg viewBox="0 0 560 190" role="img" aria-label="Each of the five folds keeps an equal mix of real and synthetic rows">
  <text x="20" y="20" class="mono ax">STRATIFIED &#183; every fold keeps the 50/50 class mix</text>
  <g>
    <rect x="55"  y="40" width="70" height="55" fill="var(--real)"/><rect x="55"  y="95" width="70" height="55" fill="var(--syn)"/>
    <rect x="155" y="40" width="70" height="55" fill="var(--real)"/><rect x="155" y="95" width="70" height="55" fill="var(--syn)"/>
    <rect x="255" y="40" width="70" height="55" fill="var(--real)"/><rect x="255" y="95" width="70" height="55" fill="var(--syn)"/>
    <rect x="355" y="40" width="70" height="55" fill="var(--real)"/><rect x="355" y="95" width="70" height="55" fill="var(--syn)"/>
    <rect x="455" y="40" width="70" height="55" fill="var(--real)"/><rect x="455" y="95" width="70" height="55" fill="var(--syn)"/>
  </g>
  <g font-size="10.5" text-anchor="middle" fill="#fff">
    <text x="90" y="72">200 real</text><text x="90" y="127">200 syn</text>
    <text x="190" y="72">200 real</text><text x="190" y="127">200 syn</text>
    <text x="290" y="72">200 real</text><text x="290" y="127">200 syn</text>
    <text x="390" y="72">200 real</text><text x="390" y="127">200 syn</text>
    <text x="490" y="72">200 real</text><text x="490" y="127">200 syn</text>
  </g>
  <g class="ax mono" font-size="10.5" text-anchor="middle">
    <text x="90" y="168">fold 1</text><text x="190" y="168">fold 2</text><text x="290" y="168">fold 3</text><text x="390" y="168">fold 4</text><text x="490" y="168">fold 5</text>
  </g>
</svg>
</div>
<figcaption>Balanced sample = 1,000 real + 1,000 synthetic. Stratified 5-fold splitting puts
200 real and 200 synthetic in each fold, so no fold is lopsided.</figcaption>
</figure>

## Worked example

Balanced sample: 1,000 real + 1,000 synthetic = **2,000 rows**, `folds = 5`. Stratified
splitting makes 5 folds of **400 rows each** (200 real + 200 synthetic). Five rounds run: each
trains on 1,600 rows and scores the held-out 400. Pool all 2,000 out-of-fold scores → one
ROC-AUC (e.g. 0.52). Because the C2ST repeats the whole balance-and-CV procedure `n_repeats = 5`
times on fresh subsamples, this happens five times over and the AUCs are averaged.

## Where it sits in the C2ST

- The **permutation test** (Step 4) reruns this *entire* cross-validation on each of the 200
  label shuffles — so a permuted AUC is just as out-of-sample as the observed one.
- The **two backends** implement the split differently but identically in spirit: the sklearn
  path uses `StratifiedKFold`; the numpy/MMD fallback uses `_stratified_folds` (shuffle each
  class, `array_split` into `k`, recombine). Both feed the pooled out-of-fold scores to the
  same rank-based AUC.
- `eff_folds` never drops below 2 and never exceeds `balanced_n`, so cross-validation still runs
  (with fewer folds) for a small synthetic population instead of failing.

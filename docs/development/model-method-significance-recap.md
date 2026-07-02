# Recap: statistical significance of model / method impact (to continue later)

**Date:** 2026-07-02
**Context branch:** `feature/model-performance-comparison` (implemented, uncommitted at time of writing)

## Where the discussion stands

The new `analysis/performance/` process (`scripts/analyze/compare_model_performance.py`, GUI action
"Model Performance") ranks model × strategy combos per country against the real baseline and tests
factor impact statistically:

- **Overall impact — covered.** Per country, per factor (model / strategy): Kruskal-Wallis omnibus +
  Dunn post-hoc with Holm correction, on per-attribute TV-similarities pooled across the other
  factor (`stats.by_model` / `stats.by_strategy` in `{country}_performance.json`). First real run
  (Swedish, 35 combos): strategy impact highly significant (H=102.7, p≈3e-21;
  `all_generate_evaluate_random_pick` sweeps ranks 1–7), model impact not significant (p=0.199).
- **Per-category (per-attribute) impact — NOT covered.** Only descriptive scores exist per attribute
  (matrix/heatmap). Sketched next step: per attribute, KW + Dunn/Holm across models (samples = that
  model's scores across strategies) and across strategies (samples = across models), plus a
  multiplicity correction across the 15 attributes (Holm or BH). A Friedman test (attributes as
  blocks) would also be a cleaner overall test than the current pooling. All machinery already in
  `analysis/utils/stats_tests.py`.
- **Honesty caveats recorded in the JSON:** (a) pseudo-replication — the 15 attribute scores of one
  combo are correlated, p-values indicative; (b) one run per combo — no replicate generations, so
  model impact is confounded with run-to-run noise. Strict significance needs replicates.
- **"Seed" clarification:** only the real/database generators (`generate_scb/ssb/istat_population.py`)
  take a true RNG seed (`np.random.default_rng`). LLM synthetic generation has **no seed** — its
  stochasticity is LLM sampling; `seed_NNN`/`--seed-root` in that path is legacy naming for a run
  output directory. Replicating an LLM combo = simply re-running it (blocked today by the slug
  having no run index: a rerun overwrites `01_Raw/{slug}`, the mapped file, and the report).

## Thoughts to carry forward (Basil)

1. **Real-population seed sensitivity** — need to understand what changing the seed of the real
   population generation induces (the baseline is itself a finite N sample; how much of each combo's
   TV distance is baseline sampling noise?).
2. **LLM generation is population-agnostic** — each individual is generated unaware of the overall
   population distribution, so one population of 1000 individuals is equivalent to 10 populations of
   100. (Implication worth exploring: replicates for significance testing could be obtained by
   splitting or extending existing runs, without any per-run seed mechanics.)
3. **The biggest limitation is generation time** — running the local models (all except Claude)
   takes ages; a new strategy is needed to drastically speed up generation before replicate-based
   statistics are practical.

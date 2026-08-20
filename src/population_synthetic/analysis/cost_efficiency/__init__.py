"""cost_efficiency -- accuracy against generation cost, per country x model x method.

Cross-combination analysis process. It joins the fidelity ranking's accuracy with
the LLM-call cost of the runs that produced it, and emits a per-country scatter,
a tidy CSV and a JSON report under ``03_Analysis/cost_efficiency/``.

The one thing that makes this process more than a join is its **cost denominator**.
``generation_metadata`` measures its cost statistics on the capped mirror -- the
~100 personas each combination was subsampled down to -- so its per-persona cost
describes the survivors and not the run. Measured on disk that gap reaches 5.5x,
and it is largest exactly where retention is worst, so a cost figure built on it
would flatter the models that wasted the most tokens. Worse, an *excluded*
combination has no capped mirror at all, so the capped measurement is not merely
biased for the seven combinations the full-N rule withdrew, it is missing.

``raw_cost.py`` therefore totals cost over the **full generated pool** in ``01_Raw``,
which is the only population that contains every token the run actually paid for.
Nothing in this package reads the capped mirror, and ``generation_metadata`` is left
exactly as it is -- putting the reader here is what keeps that process's shipped read
contract untouched.

Module boundaries (see each module's docstring for the exact contract):
- ``raw_cost.py`` -- per-combination cost over the full ``01_Raw`` pool, priced
  through ``config/analysis/model_pricing.yaml``, with pricing provenance.
"""

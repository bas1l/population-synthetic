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
- ``loader.py`` -- reads the fidelity ranking, the validation-attrition contract and
  the generation-metadata summary, reconstructs the join key through
  ``manifest_loader.axis_slug``, reconciles the three row sets, and returns one typed
  record per joined combination plus the withdrawn ones.
- ``builder.py`` -- pure derivation of ``cost_per_usable_persona`` and the JSON/CSV
  documents. No composite score is computed here or anywhere else.
- ``charts.py`` -- the accuracy-vs-cost scatter, returning an unsaved ``Figure``.

The three inputs legitimately hold **different row sets**: the attrition CSV records
every combination the gate saw, withdrawals included, while a withdrawn combination
has neither a fidelity report nor a capped mirror and therefore appears in neither of
the other two. The output row set is the attrition set minus the withdrawals, the
withdrawals are reported (with the money they cost) rather than inner-joined away, and
any other difference between the three raises.
"""

"""validation_attrition -- what the validation gate discarded, and where.

The gate (``validate_raw`` -> ``mapping`` -> ``validate_mapped`` -> ``population_cap``)
drops personas at three points and withdraws whole combinations at a fourth, and until
this process existed none of it was reported. ``validate_raw`` and ``validate_mapped``
each compute a ``pass_rate_pct`` into a ``_summary.csv`` and stop; ``population_cap``
records its counts in ``_index.json`` and stops. Nothing joined the three, and nothing
rendered the chain -- so a combination that generated 549 personas to keep 100, or one
that was withdrawn outright, looked from the analysis layer exactly like one that
generated 110 and kept 100.

This package is that join. It is **read-only** over the gate's own persisted records:
it recomputes no gate decision, re-validates no persona, and writes nothing any other
process reads except its own tidy CSV.

Its row grain is every combination in ``population_cap/_index.json``, the withdrawn
ones included. That is the point of the artifact rather than an incidental property:
an excluded combination has no capped mirror, no capped mapped file and therefore no
``generation_metadata`` row, so this is the only place in ``03_Analysis/`` a withdrawal
is visible at all.

Module split, following the ``realism_ranking`` shape:

``loader``
    Read the ``_index.json`` + two ``_summary.csv`` triple, gate it for completeness,
    and type one record per combination.
``builder``
    Derive the two rates and assemble the JSON document and the CSV rows. Pure.
``charts``
    Render, and only render.

The tidy schema itself lives in
:mod:`population_synthetic.analysis.utils.attrition_csv`, because ``cost_efficiency``
reads it and must not import this package to do so.
"""

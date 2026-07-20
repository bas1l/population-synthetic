"""population_synthetic.analysis.consistency -- detection-only consistency scan.

Scans a *mapped* canonical population (the same analysis-stage mapping-folder input
contract as the other analysis processes) for internally-inconsistent attribute
combinations, against a small config-driven rule list (e.g. "retired implies
age >= 55"). This process does not touch the generator and does not correct
anything -- it only reports. Dataflow:

    load rules -> scan -> write / aggregate -> visualize

``rules.load_rules`` reads the country's rule list from
``config/analysis/consistency/{country}.yaml`` (fail-fast: missing file, unknown
attribute, malformed predicate, or an empty rule list all raise) and
``rules.evaluate``/``rules.is_violation`` match one individual against one rule's
predicates. ``builder.scan_population`` runs every rule over every individual in a
population and assembles a :class:`~population_synthetic.analysis.consistency.builder.ConsistencyReport`
(per-rule violation count, violation rate, a capped sample of offending records);
``builder.write_report_json``/``write_violations_csv`` persist it.
``charts.plot_violation_rates`` draws the per-rule violation-rate bar chart from
the aggregated rows, honouring a no-charts path from the caller.

Canonical attribute/label access (and the raw-``age`` -> ``age_group`` derivation)
reuses :func:`population_synthetic.analysis.fidelity.evaluator.attr_value` rather
than re-deriving it; attribute-name validation reuses
:func:`population_synthetic.analysis.fidelity.scheme.load_scheme`'s
``ComparisonScheme.attributes``. Nothing here re-implements those.
"""

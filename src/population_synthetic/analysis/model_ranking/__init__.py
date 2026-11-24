"""population_synthetic.analysis.model_ranking — cross-model performance comparison.

Sits after the compare stage (entry point: ``scripts/analyze/rank_models.py``):
consumes the per-combo comparison reports written by the compare stage
(``{output_base}/03_Analysis/fidelity/{slug}/{slug}.json``) and compares the
model × strategy combos **against each other** per country — per demographic
attribute and overall — on how well each matches the real baseline. Dataflow:

    load → build → visualize

``loader`` discovers and loads the reports into :class:`ComboPerformance`
records, ``builder`` assembles the per-country score matrix / ranking /
hypothesis tests (Kruskal-Wallis + Dunn from the shared
``analysis.utils.stats_tests``), and ``charts`` visualizes it. This package
never recomputes statistics from populations — the comparison reports are its
only data source.
"""

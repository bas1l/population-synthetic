"""population_synthetic.analysis.run_analytics.cross_run — the cross-run analytics pipeline.

Pipeline B (entry point: ``scripts/analyze/compare_run_analytics.py``): consume many runs'
``run_analytics.json`` and compare them. Dataflow:

    load → test → build → visualize

``comparison_loader`` loads the per-run analytics, the shared
``analysis.utils.stats_tests`` runs the non-parametric hypothesis tests,
``run_comparison`` builds the cross-run comparison structure, and
``comparison_charts`` visualizes it. Modules here may import ``analysis.utils``
but never ``run_analytics.per_run``.
"""

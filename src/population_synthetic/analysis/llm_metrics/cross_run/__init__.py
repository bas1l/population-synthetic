"""population_synthetic.analysis.llm_metrics.cross_run — the cross-run analytics pipeline.

Pipeline B (entry point: ``scripts/analyze/compare_runs.py``): consume many runs'
``run_analytics.json`` and compare them. Dataflow:

    load → test → build → visualize

``comparison_loader`` loads the per-run analytics, the shared
``analysis.utils.stats_tests`` runs the non-parametric hypothesis tests,
``run_comparison`` builds the cross-run comparison structure, and
``comparison_charts`` visualizes it. Modules here may import ``analysis.utils``
but never ``llm_metrics.per_run``.
"""

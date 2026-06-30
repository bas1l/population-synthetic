"""population_synth.analysis.cross_run — the cross-run analytics pipeline.

Pipeline B (entry point: ``scripts/analyze/compare_runs.py``): consume many runs'
``run_analytics.json`` and compare them. Dataflow:

    load → test → build → visualize

``comparison_loader`` loads the per-run analytics, ``comparison_stats`` runs the
non-parametric hypothesis tests, ``run_comparison`` builds the cross-run
comparison structure, and ``comparison_charts`` visualizes it. Modules here may
import ``analysis.shared`` but never ``analysis.per_run``.
"""

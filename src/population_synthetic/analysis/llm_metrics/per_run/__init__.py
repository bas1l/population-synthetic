"""population_synthetic.analysis.llm_metrics.per_run — the per-run analytics pipeline.

Pipeline A (entry point: ``scripts/analyze/analyze_run.py``): turn one identity
generation run into analytics plus a report. Dataflow:

    parse → join → aggregate → visualize/report

``interaction_parser`` / ``log_parser`` parse the run's JSONL and log files,
``joiner`` matches interaction records to log call records, ``aggregator``
computes per-persona metrics, and ``charts`` / ``console_report`` visualize and
report them (writing ``run_analytics.json``). Modules here may import
``analysis.utils`` but never ``llm_metrics.cross_run``.
"""

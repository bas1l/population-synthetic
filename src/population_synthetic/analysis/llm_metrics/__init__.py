"""population_synthetic.analysis.llm_metrics — two-level post-run analytics for identity runs.

The package is a two-level analytics pipeline whose two levels map 1:1 to the
two entry-point scripts. The folder layout mirrors that workflow:

    per_run/  (analyze_run.py)        one run -> analytics + report
        interaction_parser \\
        log_parser          } parse -> joiner (join) -> aggregator (aggregate)
                                       -> charts / console_report (visualize/report)
                                       -> run_analytics.json
                                              |
                                              v
    cross_run/ (compare_runs.py)      many run_analytics.json -> comparison
        comparison_loader (load) -> comparison_stats (test)
        -> run_comparison (build) -> comparison_charts (visualize)

    shared/   numeric primitives (median / percentile / Shannon entropy) used
              by both levels.

Cross-level rule: ``per_run`` and ``cross_run`` never import each other; both
may import ``shared``.
"""

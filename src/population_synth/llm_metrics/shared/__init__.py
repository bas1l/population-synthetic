"""population_synth.llm_metrics.shared — numeric primitives shared by both pipelines.

Stdlib-only helpers (median, percentile, Shannon entropy) used by both the
per-run and cross-run analytics pipelines. This subpackage carries no pipeline
state of its own; it is the common numeric floor both levels build on.
"""

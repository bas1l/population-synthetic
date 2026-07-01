"""population_synthetic.analysis — the three post-generation analysis processes.

Groups the post-generation tooling into one subpackage per process:

    mapping/      raw population data (national-statistics or LLM pipeline
                  identities) -> the canonical comparable schema.
    comparison/   statistically score and chart one population against a
                  real population.
    llm_metrics/  post-run analytics on identity-generation LLM calls.
    utils/        cross-process shared infrastructure.

The only cross-process dependency direction is ``comparison -> mapping``.
"""

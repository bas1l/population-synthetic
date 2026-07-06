"""population_synthetic.analysis — the post-generation analysis processes.

Groups the post-generation tooling into one subpackage per process, in two
families:

    Demographic fidelity (synthetic population vs real national baseline)
        mapping/                raw population data (national-statistics or LLM
                                pipeline identities) -> the canonical comparable
                                schema.
        fidelity/               statistically score and chart one population
                                against a real population (marginal, joint
                                chi-squared, coherence, and a multivariate block).
        multivariate_fidelity/  promoted multivariate view over the mapped
                                populations (C2ST, Cramer's-V association, k-way
                                combination plausibility).
        model_ranking/          cross-model/strategy leaderboard over the
                                fidelity reports.

    Run analytics (LLM operational metrics)
        run_analytics/          per-run and cross-run analytics on
                                identity-generation LLM calls.

    utils/                      cross-process shared infrastructure.

The only cross-process dependency direction is ``fidelity -> mapping``.
"""

"""population_synthetic.analysis.multivariate_fidelity — standalone multivariate fidelity.

Promotes the multivariate / joint-fidelity metric (C2ST, pairwise Cramer's-V
association, per-pair joint TV, k-way combination plausibility) into a first-class
analysis process with its own ``03_Analysis/multivariate_fidelity/`` output folder, separate
from the marginal comparison. Dataflow:

    build → write / aggregate → visualize

The metric itself is NOT re-implemented here: ``builder.build_multivariate_fidelity``
is a thin driver that instantiates the shared
:class:`~population_synthetic.analysis.fidelity.evaluator.StatisticalEvaluator` over the
mapped populations and calls only its ``compute_multivariate()`` -- so this process and
the comparison process compute the exact same block, they just persist it to different
folders. The fidelity evaluator, the model-ranking loader/leaderboard, and the paper path
are untouched (zero regression).
"""

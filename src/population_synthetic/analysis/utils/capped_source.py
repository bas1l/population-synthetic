"""capped_source.py -- READ resolvers for the capped population mirror.

The population-cap task materializes a capped mirror at
``{output_base}/03_Analysis/population_cap/`` (one ``{slug}/`` combo dir each). The two
raw-persona consumers -- ``mapping`` and ``generation_metadata`` -- start their
``persona_*`` globbing from a root path; these resolvers supply that root.

The capped mirror is a **hard prerequisite** (enforced upstream by the analysis DAG:
both consumers depend on ``population_cap``). There is deliberately **no fallback** to
``01_Raw``: if the mirror is absent, the resolver raises loudly, instructing the caller
to run the cap task first. This keeps N a single enforced invariant -- no task can
silently read the uncapped raw population.

The resolvers only compute/validate paths; they know nothing about how the cap selects
or copies personas.
"""

from __future__ import annotations

from pathlib import Path

from population_synthetic.analysis.utils.registry import analysis_output_dir

# The registered analysis-process id whose output folder holds the capped mirror.
_CAP_PROCESS_ID = "population_cap"


def resolve_combo_source(slug: str, output_base: str | Path) -> Path:
    """Return the capped-mirror read root for one combo: ``population_cap/{slug}/``.

    Args:
        slug: The combo slug (``{country_id}_{strategy_id}_{model_id}``).
        output_base: The run's output base (the parent of ``03_Analysis/``).

    Returns:
        The path ``{output_base}/03_Analysis/population_cap/{slug}/``, whose
        ``persona_*`` subdirectories are the capped population for that combo.

    Raises:
        FileNotFoundError: If the capped mirror for ``slug`` does not exist -- the
            population-cap task has not been run for this combo.
    """
    capped_dir = analysis_output_dir(_CAP_PROCESS_ID, output_base) / slug
    if not capped_dir.is_dir():
        raise FileNotFoundError(
            f"Capped population mirror not found for combo {slug!r}: {capped_dir}. "
            f"Run the population_cap task before mapping / generation_metadata."
        )
    return capped_dir


def resolve_stage_source(output_base: str | Path) -> Path:
    """Return the capped-mirror stage root containing every combo's ``{slug}/`` dir.

    Args:
        output_base: The run's output base (the parent of ``03_Analysis/``).

    Returns:
        The path ``{output_base}/03_Analysis/population_cap/``, whose immediate
        subdirectories are the per-combo capped mirrors.

    Raises:
        FileNotFoundError: If the capped stage dir does not exist -- the population-cap
            task has not been run for this output base.
    """
    capped_stage = analysis_output_dir(_CAP_PROCESS_ID, output_base)
    if not capped_stage.is_dir():
        raise FileNotFoundError(
            f"Capped population stage not found: {capped_stage}. "
            f"Run the population_cap task before generation_metadata / mapping."
        )
    return capped_stage

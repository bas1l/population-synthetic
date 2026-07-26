"""capped_source.py -- READ resolvers for the capped population outputs.

The population-cap task runs last of the validation gate (``validate_raw`` -> ``mapping``
-> ``validate_mapped`` -> ``population_cap``) and materializes two capped outputs under
``{output_base}/03_Analysis/population_cap/``:

- the **capped persona-dir mirror** -- one ``{slug}/`` combo dir of selected raw
  ``persona_*`` directories (identity + telemetry). Its sole consumer is
  ``generation_metadata``, which globs each combo's ``persona_*`` telemetry.
- the **capped mapped dir** ``_mapped/`` -- the capped ``{slug}.json`` mapped populations
  (plus the copied ``real_{country}.json`` and an ``_index.json``). Every mapped-file
  consumer (fidelity, multivariate, consistency, pairwise, real_population_stats,
  persona_realism) reads its synthetic populations from here, NOT from the full
  ``mapping/`` output.

Note ``mapping`` itself is NOT a consumer of these: it reads the full ``01_Raw`` pool
(it runs *before* the cap). The capped outputs are a **hard prerequisite** for their
consumers (enforced upstream by the analysis DAG: all of them depend on
``population_cap``). There is deliberately **no fallback** to ``01_Raw`` or to the full
``mapping/`` output: if a capped output is absent, the resolver raises loudly. This keeps
N a single enforced invariant -- no downstream task can silently read the uncapped
population.

The resolvers only compute/validate paths; they know nothing about how the cap selects
or copies personas.
"""

from __future__ import annotations

from pathlib import Path

from population_synthetic.analysis.utils.registry import analysis_output_dir

# The registered analysis-process id whose output folder holds the capped outputs.
_CAP_PROCESS_ID = "population_cap"

# Subfolder of the population_cap output dir holding the capped mapped files
# (``_mapped/{slug}.json`` + ``real_{country}.json`` + ``_index.json``).
MAPPED_SUBDIR = "_mapped"


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
            f"Run the population_cap task before generation_metadata."
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
            f"Run the population_cap task before generation_metadata."
        )
    return capped_stage


def resolve_mapped_dir(output_base: str | Path) -> Path:
    """Return the capped mapped read dir: ``population_cap/_mapped/``.

    Every consumer of the mapped populations (fidelity, multivariate_fidelity,
    consistency, pairwise_comparison, real_population_stats, persona_realism) reads its
    ``{slug}.json`` / ``real_{country}.json`` / ``_index.json`` from here -- the CAPPED
    mapped files written by ``population_cap`` -- rather than from the full ``mapping/``
    output, so no downstream analysis sees more than N (or an unmapped) persona.

    Args:
        output_base: The run's output base (the parent of ``03_Analysis/``).

    Returns:
        The path ``{output_base}/03_Analysis/population_cap/_mapped/``.

    Raises:
        FileNotFoundError: If the capped mapped dir does not exist -- population_cap has
            not run for this output base (fail-fast; no fallback to ``mapping/``).
    """
    mapped_dir = analysis_output_dir(_CAP_PROCESS_ID, output_base) / MAPPED_SUBDIR
    if not mapped_dir.is_dir():
        raise FileNotFoundError(
            f"Capped mapped population dir not found: {mapped_dir}. "
            f"Run the population_cap task before the downstream mapped-file consumers."
        )
    return mapped_dir

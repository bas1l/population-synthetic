"""Analysis registry accessor -- single source of truth for analysis output paths.

Loads ``config/analysis/analysis_registry.yaml`` (the authoritative id ->
{label, description, stage, folder, script, dispatch} table) and exposes the helpers
that every analysis consumer routes through:

- ``ANALYSIS_STAGE_DIR`` / ``FIGURES_STAGE_DIR`` -- the ``03_Analysis`` and
  ``04_Figures`` stage-folder literals, each defined in exactly ONE place in code
  (sourced from the registry's ``stage_dir`` / ``figures_stage_dir``).
- ``get_process(process_id)`` -- the ``AnalysisProcess`` for a canonical id.
- ``analysis_output_dir(process_id, output_base, *, for_read=False)`` --
  ``output_base / ANALYSIS_STAGE_DIR / process.folder``. When ``for_read=True`` and
  the process declares a ``legacy_folder``, the accessor falls back to the legacy
  folder (deprecation-logged) if the primary folder is absent but the legacy one
  exists -- the back-compat read path for the ``mapped`` -> ``mapping`` rename.
  Raises when handed a figures-stage id, which has no analysis-stage folder.
- ``figures_output_dir(output_base, *, country, set_name, naming)`` --
  ``output_base / FIGURES_STAGE_DIR / country / set_name / naming``, the layout of
  the figures stage, whose processes own the stage root instead of a subfolder.
- ``resolve_output_base(cli_value)`` -- the single home for the resolver previously
  copy-pasted across scripts (``--output-base`` else
  ``config/synthetic/experiment_defaults.yaml``).

The loader fails loudly (raises) on a missing file, missing top-level keys, or a
malformed process entry -- never silently defaults (project invariant: config is the
single source of truth).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_REGISTRY_PATH = PROJECT_ROOT / "config" / "analysis" / "analysis_registry.yaml"
_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"

# The two stages a process's outputs can live in. ``STAGE_ANALYSIS`` is the
# documented default for an entry that omits ``stage``; ``STAGE_FIGURES`` is the
# published-figures sibling stage. The mapping's values are the registry top-level
# keys holding each stage's folder literal -- the literals themselves stay in YAML.
STAGE_ANALYSIS = "analysis"
STAGE_FIGURES = "figures"
_STAGE_DIR_KEYS = {STAGE_ANALYSIS: "stage_dir", STAGE_FIGURES: "figures_stage_dir"}

# The metadata keys every process entry must declare whatever its stage (fail-fast if
# any is absent). ``folder`` is required per-stage, checked in ``_build_process``.
_REQUIRED_PROCESS_KEYS = ("label", "description", "script", "dispatch")


@dataclass(frozen=True)
class AnalysisProcess:
    """One analysis process's canonical metadata, as declared in the registry."""

    id: str
    label: str
    description: str
    script: str
    dispatch: str
    # Which stage folder the process writes into: ``STAGE_ANALYSIS`` (the documented
    # default when the entry omits ``stage``) or ``STAGE_FIGURES``.
    stage: str = STAGE_ANALYSIS
    # The process's subfolder under the analysis stage. Always set for an
    # analysis-stage process; ``None`` for a figures-stage one, which owns the
    # figures stage root itself and therefore declares no folder.
    folder: str | None = None
    # Optional pre-rename folder name. Present only for processes whose output
    # folder was renamed; READERS fall back to it (deprecation-logged) so existing
    # on-disk data under the old name keeps working. ``None`` when never renamed.
    legacy_folder: str | None = None


def _load_registry_raw() -> dict[str, Any]:
    """Read and minimally validate the registry YAML (fail-fast)."""
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Analysis registry not found: {_REGISTRY_PATH}")

    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Analysis registry must be a mapping, got {type(raw).__name__}: {_REGISTRY_PATH}")

    for stage_key in _STAGE_DIR_KEYS.values():
        if not raw.get(stage_key):
            raise ValueError(f"Analysis registry missing required top-level key {stage_key!r}: {_REGISTRY_PATH}")

    processes = raw.get("processes")
    if not isinstance(processes, dict) or not processes:
        raise ValueError(f"Analysis registry missing non-empty 'processes' mapping: {_REGISTRY_PATH}")

    return raw


def _build_process(process_id: str, entry: Any) -> AnalysisProcess:
    """Validate one registry entry and materialize it as an ``AnalysisProcess``."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Registry entry for {process_id!r} must be a mapping, got {type(entry).__name__}: {_REGISTRY_PATH}"
        )
    missing = [key for key in _REQUIRED_PROCESS_KEYS if not entry.get(key)]
    if missing:
        raise ValueError(f"Registry entry for {process_id!r} missing required key(s) {missing}: {_REGISTRY_PATH}")

    # ``stage`` is optional; its ABSENCE means the analysis stage (the documented
    # default). A present-but-blank value is not absent -- it falls through to the
    # unknown-stage raise below rather than being defaulted away.
    stage = STAGE_ANALYSIS if "stage" not in entry else str(entry["stage"])
    if stage not in _STAGE_DIR_KEYS:
        raise ValueError(
            f"Registry entry for {process_id!r} declares unknown stage {stage!r}: "
            f"known stages are {sorted(_STAGE_DIR_KEYS)}: {_REGISTRY_PATH}"
        )
    # ``folder`` is required by the analysis stage and forbidden in the figures stage,
    # whose processes own the stage root and have no per-process subfolder.
    folder = entry.get("folder")
    if stage == STAGE_ANALYSIS and not folder:
        raise ValueError(
            f"Registry entry for {process_id!r} missing required key(s) ['folder']: "
            f"every {STAGE_ANALYSIS!r}-stage process declares its subfolder: {_REGISTRY_PATH}"
        )
    if stage == STAGE_FIGURES and folder:
        raise ValueError(
            f"Registry entry for {process_id!r} is a {STAGE_FIGURES!r}-stage process and must not "
            f"declare 'folder' (got {folder!r}): it owns the {FIGURES_STAGE_DIR} stage root itself: "
            f"{_REGISTRY_PATH}"
        )

    legacy_folder = entry.get("legacy_folder")
    return AnalysisProcess(
        id=process_id,
        label=str(entry["label"]),
        description=str(entry["description"]).strip(),
        script=str(entry["script"]),
        dispatch=str(entry["dispatch"]),
        stage=stage,
        folder=str(folder) if folder else None,
        legacy_folder=str(legacy_folder) if legacy_folder else None,
    )


def load_registry() -> dict[str, AnalysisProcess]:
    """Load the full registry as ``{canonical_id: AnalysisProcess}`` (fail-fast)."""
    raw = _load_registry_raw()
    return {pid: _build_process(pid, entry) for pid, entry in raw["processes"].items()}


def _load_stage_dirs() -> dict[str, str]:
    """Read both stage-folder literals from the registry (the one code source)."""
    raw = _load_registry_raw()
    return {stage: str(raw[key]) for stage, key in _STAGE_DIR_KEYS.items()}


# The single definition of the "03_Analysis" / "04_Figures" stage-folder literals in code.
_STAGE_DIRS: dict[str, str] = _load_stage_dirs()
ANALYSIS_STAGE_DIR: str = _STAGE_DIRS[STAGE_ANALYSIS]
FIGURES_STAGE_DIR: str = _STAGE_DIRS[STAGE_FIGURES]


def get_process(process_id: str) -> AnalysisProcess:
    """Return the ``AnalysisProcess`` for a canonical id; raise on unknown id."""
    registry = load_registry()
    if process_id not in registry:
        raise KeyError(f"Unknown analysis process id {process_id!r}: known ids are {sorted(registry)}.")
    return registry[process_id]


def analysis_output_dir(process_id: str, output_base: str | Path, *, for_read: bool = False) -> Path:
    """Return the ``03_Analysis`` output dir for ``process_id`` under ``output_base``.

    The primary path is ``output_base / ANALYSIS_STAGE_DIR / process.folder`` -- this is
    always what WRITERS get (``for_read=False``, the default), so a fresh run writes to
    the canonical folder.

    READERS pass ``for_read=True``: if the process declares a ``legacy_folder`` and the
    primary folder does not exist on disk but the legacy one does, the legacy path is
    returned (with a deprecation log) so pre-rename on-disk data keeps working. When
    neither exists (or there is no legacy folder), the canonical primary path is returned
    so the caller fails on the canonical location.

    Raises when ``process_id`` names a figures-stage process: those write into the
    ``FIGURES_STAGE_DIR`` stage and are served by ``figures_output_dir``.
    """
    process = get_process(process_id)
    if process.stage != STAGE_ANALYSIS:
        raise ValueError(
            f"Analysis process {process_id!r} is a {process.stage!r}-stage process: its outputs live "
            f"under {FIGURES_STAGE_DIR}/, not {ANALYSIS_STAGE_DIR}/ -- call figures_output_dir()."
        )
    base = Path(output_base)
    primary = base / ANALYSIS_STAGE_DIR / process.folder
    if not for_read or process.legacy_folder is None:
        return primary
    if primary.exists():
        return primary
    legacy = base / ANALYSIS_STAGE_DIR / process.legacy_folder
    if legacy.exists():
        logger.warning(
            "Analysis process %r: canonical folder %s absent; reading legacy folder %s "
            "instead (deprecated -- re-run %s to migrate to the canonical folder).",
            process_id,
            primary,
            legacy,
            process.script,
        )
        return legacy
    return primary


def figures_output_dir(output_base: str | Path, *, country: str, set_name: str, naming: str) -> Path:
    """Return the ``04_Figures`` output dir for one country / figure set / naming.

    The figures stage has no per-process subfolder -- a figures-stage process owns
    ``output_base / FIGURES_STAGE_DIR`` and lays it out as
    ``{country}/{set_name}/{naming}``: country outermost because the analysis stage
    carries it in the directory for some processes and in the filename for others, so
    without it two countries' figures collide; the naming folders innermost so one
    set's figures stay together under every naming.

    Every component is required and must be non-empty -- a blank one would silently
    collapse the layout, so it raises instead.
    """
    for label, value in (("country", country), ("set_name", set_name), ("naming", naming)):
        if not value or not str(value).strip():
            raise ValueError(f"figures_output_dir requires a non-empty {label} (got {value!r}).")
    return Path(output_base) / FIGURES_STAGE_DIR / country / set_name / naming


def resolve_output_base(cli_value: str | None) -> Path:
    """Resolve output_base from the CLI flag, else ``experiment_defaults.yaml``.

    Fails loudly (raises) when neither a CLI value nor a configured
    ``parameters.output_base`` is available -- never silently defaults.
    """
    if cli_value:
        return Path(cli_value)
    if not _DEFAULTS_PATH.exists():
        raise FileNotFoundError(
            f"No --output-base given and experiment defaults not found: {_DEFAULTS_PATH}"
        )
    with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
        defaults = yaml.safe_load(f) or {}
    output_base = (defaults.get("parameters") or {}).get("output_base")
    if not output_base:
        raise ValueError(
            f"No output_base in {_DEFAULTS_PATH} and --output-base not given."
        )
    return Path(output_base)

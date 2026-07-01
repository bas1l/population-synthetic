"""Shared country configuration for the comparison pipeline.

Centralizes the country -> reference-population and country -> category-mappings
lookups plus ``infer_country``, which derives the country id from a
simulation-config path.

The lookups are **not** hard-coded here: they are read from the country axis
YAMLs under ``config/synthetic/axes/countries/`` (the same files consumed by
``manifest_loader.compose_manifest``). Each country YAML declares, under
``parameters``, a repo-root-relative ``reference`` path and ``mappings``
directory alongside its ``config`` entry. Adding a new country therefore needs
only a new YAML, no code change here.

Both the map stage and any comparison consumer share this single source so the
country axis ids (``swedish``/``italian``), reference paths, and mappings
directories stay consistent across the pipeline.
"""

from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.identity.manifest_loader import discover_axis_values


def _load_country_axes() -> dict[str, dict[str, Path]]:
    """Read the country axis YAMLs into ``{id: {"reference": Path, "mappings": Path}}``.

    Paths are repo-root-relative in the YAML and are resolved against
    ``PROJECT_ROOT`` (matching ``manifest_loader``'s ``_resolve_path``).
    """
    axes: dict[str, dict[str, Path]] = {}
    for data in discover_axis_values("countries"):
        country_id = data["id"]
        params = data.get("parameters", {}) or {}
        entry: dict[str, Path] = {}
        if "reference" in params:
            entry["reference"] = (PROJECT_ROOT / params["reference"]).resolve()
        if "mappings" in params:
            entry["mappings"] = (PROJECT_ROOT / params["mappings"]).resolve()
        axes[country_id] = entry
    return axes


def known_country_ids() -> tuple[str, ...]:
    """Return the country ids declared by the country axis YAMLs."""
    return tuple(_load_country_axes())


def reference_for_country(country_id: str) -> Path:
    """Resolve the reference-population path for ``country_id`` (fail-fast)."""
    axes = _load_country_axes()
    if country_id not in axes:
        raise ValueError(
            f"Unknown country id {country_id!r}: "
            f"known country ids are {sorted(axes)}."
        )
    reference = axes[country_id].get("reference")
    if reference is None:
        raise ValueError(
            f"Country axis YAML for {country_id!r} declares no "
            f"'parameters.reference' path."
        )
    return reference


def mappings_for_country(country_id: str) -> Path:
    """Resolve the category-mappings directory for ``country_id`` (fail-fast)."""
    axes = _load_country_axes()
    if country_id not in axes:
        raise ValueError(
            f"Unknown country id {country_id!r}: "
            f"known country ids are {sorted(axes)}."
        )
    mappings = axes[country_id].get("mappings")
    if mappings is None:
        raise ValueError(
            f"Country axis YAML for {country_id!r} declares no "
            f"'parameters.mappings' path."
        )
    return mappings


def infer_country(config_path: str | Path) -> str:
    """Infer the country id from a simulation-config path.

    Manifests carry no explicit country; it is implicit in the simulation-config
    filename (e.g. ``simulation_config_004_swedish_generative.json`` -> ``swedish``,
    ``simulation_config_005_italian_generative.json`` -> ``italian``). This matches
    the known country ids (derived from the country axis YAMLs) against the config
    stem.

    Fails loudly (fail-fast convention) when zero or more than one country token
    matches, so an unknown or ambiguous filename never silently resolves.
    """
    country_ids = known_country_ids()
    stem = Path(config_path).stem.lower()
    matches = [country_id for country_id in country_ids if country_id in stem]

    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise ValueError(
            f"Cannot infer country from config path {config_path!r}: "
            f"no known country token {list(country_ids)} found in stem {stem!r}."
        )

    raise ValueError(
        f"Ambiguous country for config path {config_path!r}: "
        f"multiple country tokens matched stem {stem!r}: {matches}."
    )

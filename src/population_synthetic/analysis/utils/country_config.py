"""Shared country configuration for the comparison pipeline.

Centralizes the country -> real-population and country -> category-mappings
lookups plus ``infer_country``, which derives the country id from a
simulation-config path.

The lookups are **not** hard-coded here: they are read from the country axis
YAMLs under ``config/synthetic/axes/countries/`` (the same files consumed by
``manifest_loader.compose_manifest``). Each country YAML declares, under
``parameters``, a repo-root-relative ``reference`` path (the YAML key itself is
unrenamed pending the config-layer rename) and ``mappings`` directory alongside
its ``config`` entry. Adding a new country therefore needs only a new YAML, no
code change here.

Both the map stage and any comparison consumer share this single source so the
country axis ids (``swedish``/``italian``), real-population paths, and mappings
directories stay consistent across the pipeline.
"""

from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

# Optional ``_index.json`` key listing attributes excluded from analysis; absent => none.
_DEPRECATED_INDEX_KEY = "deprecated_attributes"


def _load_country_axes() -> dict[str, dict[str, Path]]:
    """Read the country axis YAMLs into ``{id: {"real": Path, "mappings": Path}}``.

    Paths are repo-root-relative in the YAML and are resolved against
    ``PROJECT_ROOT`` (matching ``manifest_loader``'s ``_resolve_path``). The YAML
    key read here (``reference``) is unrenamed pending the config-layer rename;
    the internal ``entry`` dict already uses the ``real`` name.
    """
    axes: dict[str, dict[str, Path]] = {}
    for data in discover_axis_values("countries"):
        country_id = data["id"]
        params = data.get("parameters", {}) or {}
        entry: dict[str, Path] = {}
        if "reference" in params:
            entry["real"] = (PROJECT_ROOT / params["reference"]).resolve()
        if "mappings" in params:
            entry["mappings"] = (PROJECT_ROOT / params["mappings"]).resolve()
        axes[country_id] = entry
    return axes


def known_country_ids() -> tuple[str, ...]:
    """Return the country ids declared by the country axis YAMLs."""
    return tuple(_load_country_axes())


def real_for_country(country_id: str) -> Path:
    """Resolve the real-population path for ``country_id`` (fail-fast)."""
    axes = _load_country_axes()
    if country_id not in axes:
        raise ValueError(
            f"Unknown country id {country_id!r}: "
            f"known country ids are {sorted(axes)}."
        )
    real = axes[country_id].get("real")
    if real is None:
        raise ValueError(
            f"Country axis YAML for {country_id!r} declares no "
            f"'parameters.reference' path."
        )
    return real


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


def deprecated_attributes(index: dict, source: Path | str) -> list[str]:
    """Return the analysis-deprecated attributes declared by a mapping ``_index`` dict.

    Pure: the caller supplies the already-loaded index, so a consumer that needs the
    ``attributes`` order too (``validate_raw``) reads the file once. ``source`` is only
    used to name the offending directory in the error message.

    A deprecated axis is still mapped and emitted into population data but is excluded
    from every analysis, so no validity gate may fail a persona over its value. Both
    gates route through this one rule, keeping them from drifting apart from each other
    or from the scored axis set.

    Raises:
        ValueError: If ``deprecated_attributes`` names an attribute absent from the
            index's ``attributes`` map (a config error).
    """
    deprecated = list(index.get(_DEPRECATED_INDEX_KEY, []))
    unknown = [name for name in deprecated if name not in index["attributes"]]
    if unknown:
        raise ValueError(
            f"Mapping index {source} {_DEPRECATED_INDEX_KEY!r} names attribute(s) "
            f"{unknown} not present in 'attributes'"
        )
    return deprecated


def deprecated_attributes_for_country(country_id: str) -> list[str]:
    """Read ``country_id``'s mapping index and return its deprecated attributes.

    IO wrapper over :func:`deprecated_attributes` for consumers that need nothing else
    from the index.
    """
    # Lazy import: keep this shared helper free of a load-time dependency on the
    # mapper subpackages (matching ``assert_mapping_dir_consistency`` below).
    from population_synthetic.analysis.mapping.real_mapper.mappings import load_index

    directory = mappings_for_country(country_id)
    index = load_index(directory)  # validates deprecated_attributes is a list[str]
    return deprecated_attributes(index, directory)


def assert_mapping_dir_consistency(country_id: str) -> Path:
    """Fail loud if the country's mapping directory is selected inconsistently.

    The mapping directory (which ``values``/matchers score the within-country
    fidelity) is chosen in three places: the country axis YAML
    (``parameters.mappings`` -- the single source of truth), and the
    ``MAPPINGS_SUBDIR`` class default on both the real and the synthetic mapper
    (which also seeds the factory fallback and the scheme's default directory).
    They MUST resolve to the same directory, or the real population, the synthetic
    population, and the comparison scheme could be mapped/scored on different value
    axes silently. This asserts they agree and returns the agreed directory.

    Note: ``MAPPINGS_SUBDIR`` additionally seeds the analysis-tuning filename stem
    (see ``fidelity.scheme._analysis_path``); that concern is decoupled there by
    stripping the ``_native`` tier suffix, so the shared attribute-name-keyed
    ``config/analysis/fidelity/{base}.json`` is reused across tiers.
    """
    yaml_dir = mappings_for_country(country_id)
    # Lazy imports: keep this shared helper free of a load-time dependency on the
    # mapper subpackages (which import nothing from here, but stay defensive).
    from population_synthetic.analysis.mapping.real_mapper.factory import _mapper_class as _real_cls
    from population_synthetic.analysis.mapping.synthetic_mapper.factory import _mapper_class as _syn_cls

    class_dirs = {
        "real_mapper.MAPPINGS_SUBDIR": (_MAPPINGS_ROOT / _real_cls(country_id).MAPPINGS_SUBDIR).resolve(),
        "synthetic_mapper.MAPPINGS_SUBDIR": (_MAPPINGS_ROOT / _syn_cls(country_id).MAPPINGS_SUBDIR).resolve(),
    }
    disagreeing = {name: str(path) for name, path in class_dirs.items() if path != yaml_dir}
    if disagreeing:
        raise ValueError(
            f"Mapping-directory drift for country {country_id!r}: the country axis YAML "
            f"'parameters.mappings' resolves to {yaml_dir}, but these mapper class defaults "
            f"disagree: {disagreeing}. Bring MAPPINGS_SUBDIR into sync with the YAML "
            f"(the single source of truth) before mapping/scoring."
        )
    return yaml_dir


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

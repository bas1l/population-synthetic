"""Load and validate YAML identity generation manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.generators.synthetic.ollama_hosts import OllamaHost, resolve_host

VALID_AXES = {"models", "strategies", "countries"}

VALID_PROVIDERS = {"gemini", "claude", "ollama", "openai_compat", "openrouter"}
VALID_MODES = {"batch", "configurable"}


@dataclass
class ManifestConfig:
    """Parsed and validated identity generation manifest."""

    name: str
    provider: str
    model: str
    generation_config: dict[str, Any]
    mode: str
    config_path: Path
    strategy_path: Path | None
    log_llm: bool
    output: str
    parallel_n: int | None
    parallel_workers: int | None
    parallel_output_dir: Path | None
    comparison_output_dir: Path | None
    base_url: str | None = None
    api_key_env_var: str | None = None
    retry_until_success: bool = False
    structured_output: bool = False
    # The resolved Ollama host id (``provider: ollama`` composition only; ``None``
    # for every other provider and for the file-manifest path). It is part of the
    # composed configuration, not a runtime detail: ``base_url`` and
    # ``parallel_workers`` are both derived from it, so a snapshot that recorded
    # only the derived values could not be traced back to the machine that ran.
    ollama_host: str | None = None


def load_manifest(manifest_path: str | Path) -> ManifestConfig:
    """Load, validate, and resolve a YAML identity generation manifest."""
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Manifest must be a YAML mapping, got {type(raw).__name__}")

    name = raw.get("name", manifest_path.stem)

    model_cfg = raw.get("model_config", {})
    provider = model_cfg.get("provider")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"model_config.provider must be one of {VALID_PROVIDERS}, got {provider!r}")

    model = model_cfg.get("model")
    if not model:
        raise ValueError("model_config.model is required")

    base_url = model_cfg.get("base_url") or None
    api_key_env_var = model_cfg.get("api_key_env_var") or None

    raw_gen_config = model_cfg.get("generation_config", {}) or {}
    generation_config = {k: v for k, v in raw_gen_config.items() if v is not None}

    params = raw.get("parameters", {})
    mode = params.get("mode")
    if mode not in VALID_MODES:
        raise ValueError(f"parameters.mode must be one of {VALID_MODES}, got {mode!r}")

    config_rel = params.get("config")
    if not config_rel:
        raise ValueError("parameters.config is required")
    config_path = _resolve_path(config_rel)

    strategy_path = None
    strategy_rel = params.get("strategy")
    if mode == "configurable":
        if not strategy_rel:
            raise ValueError("parameters.strategy is required when mode is 'configurable'")
        strategy_path = _resolve_path(strategy_rel)
    elif strategy_rel:
        strategy_path = _resolve_path(strategy_rel)

    log_llm = params.get("log_llm", True)
    output = params.get("output", "identity.json")

    parallel = params.get("parallel", {}) or {}
    parallel_n = parallel.get("n")
    # Deliberately a scalar here, unlike the axis-composition path below.
    # This branch loads the frozen ``identity_manifest_0NN_*.yaml`` seed manifests,
    # which are historical records of runs that already happened on one machine --
    # a per-host worker map would be meaningless in a record of the past, and the
    # analysis side that consumes these files never reads ``workers`` at all. It is
    # not a fallback for the axis path: an axis file with a scalar ``workers`` is a
    # hard error (see ``_host_worker_map``).
    parallel_workers = parallel.get("workers")
    parallel_output_dir_rel = parallel.get("output_dir")
    parallel_output_dir = _resolve_path(parallel_output_dir_rel) if parallel_output_dir_rel else None
    retry_until_success = bool(parallel.get("retry_until_success", False))
    structured_output = bool(params.get("structured_output", False))

    comparison_output_dir_rel = params.get("comparison_output_dir")
    comparison_output_dir = _resolve_path(comparison_output_dir_rel) if comparison_output_dir_rel else None

    return ManifestConfig(
        name=name,
        provider=provider,
        model=model,
        generation_config=generation_config,
        mode=mode,
        config_path=config_path,
        strategy_path=strategy_path,
        log_llm=log_llm,
        output=output,
        parallel_n=parallel_n,
        parallel_workers=parallel_workers,
        parallel_output_dir=parallel_output_dir,
        comparison_output_dir=comparison_output_dir,
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        retry_until_success=retry_until_success,
        structured_output=structured_output,
    )


def _resolve_path(rel_path: str) -> Path:
    """Resolve a manifest-relative path against PROJECT_ROOT."""
    return (PROJECT_ROOT / rel_path).resolve()


def discover_axis_values(axis: str) -> list[dict]:
    """Return sorted list of parsed YAML dicts for all files in a config axis directory."""
    if axis not in VALID_AXES:
        raise ValueError(f"axis must be one of {VALID_AXES}, got {axis!r}")
    axis_dir = PROJECT_ROOT / "config" / "synthetic" / "axes" / axis
    # Files prefixed with "_" are co-located definitions that are not selectable
    # axis options (e.g. the debug-only and compared-only strategies); skip them.
    files = sorted(f for f in axis_dir.glob("*.yaml") if not f.name.startswith("_"))
    results = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Axis file must be a YAML mapping: {f}")
        results.append(data)
    return sorted(results, key=lambda d: d["id"])


def axis_slug(model_id: str, strategy_id: str, country_id: str) -> str:
    """Return the canonical axis slug ``{country}_{strategy}_{model}``.

    This is the single source of truth for the slug format joining an
    axis combo to its on-disk artifacts (raw runs, mapped populations,
    comparison outputs). ``compose_manifest`` and the batch GUI path both
    route through here so the format cannot drift.
    """
    return f"{country_id}_{strategy_id}_{model_id}"


def _host_worker_map(model_data: dict[str, Any]) -> dict[str, int]:
    """Return an Ollama model axis file's ``parameters.parallel.workers`` map.

    Worker capacity is a function of (model x GPU VRAM), so an Ollama axis file
    declares ``{host_id: n}`` rather than a scalar. A host id absent from the map
    **is** the "this host does not serve this model" signal -- there is no second
    availability list to drift out of sync with it.

    This is the single lookup shared by the raising composition path
    (:func:`_resolve_ollama_workers`) and the non-raising :func:`workers_for_host`
    query, so the two can never disagree about which pairs are supported.

    A scalar ``workers`` raises: it is the pre-registry shape, and accepting it
    would silently reintroduce a host-implicit worker count.
    """
    model_id = model_data["id"]
    workers = model_data["parameters"]["parallel"]["workers"]
    if not isinstance(workers, dict):
        raise ValueError(
            f"Model axis '{model_id}': parameters.parallel.workers must be a "
            f"{{host_id: n}} mapping keyed by host ids from config/synthetic/ollama_hosts.yaml, "
            f"got {workers!r}. The scalar form is no longer accepted -- it left the target "
            f"host implicit."
        )
    return workers


def workers_for_host(model_data: dict[str, Any], host_id: str) -> int | None:
    """Return the worker count *model_data* declares for *host_id*, or ``None``.

    The non-raising twin of the composition-time availability gate, for callers
    that must **display** an unsupported (host, model) pair rather than fail on it
    (the GUI summary panel renders an em dash for ``None``). A malformed
    ``workers`` shape still raises -- that is a config error, not an unsupported
    pair.
    """
    return _host_worker_map(model_data).get(host_id)


def _resolve_ollama_workers(model_data: dict[str, Any], host: OllamaHost) -> int:
    """Collapse the per-host worker map to the scalar count for *host* (fail-fast).

    Raises before any persona directory is created when the selected host does not
    serve the model, naming the hosts that do.
    """
    workers = _host_worker_map(model_data)
    if host.id not in workers:
        raise ValueError(
            f"Ollama host '{host.id}' ({host.label}) does not serve model "
            f"'{model_data['id']}': its parameters.parallel.workers declares no entry for "
            f"that host. Hosts that do serve it: {list(workers)}."
        )
    return workers[host.id]


def compose_manifest(
    model_id: str,
    strategy_id: str,
    country_id: str,
    ollama_host_id: str | None = None,
) -> ManifestConfig:
    """Compose a ManifestConfig from axis files and experiment defaults.

    *ollama_host_id* selects the Ollama endpoint for ``provider: ollama`` models
    (``None`` resolves the registry's ``default_host``). This function is the one
    normalization point for that choice: it resolves the host to its ``base_url``
    and collapses the axis file's ``{host_id: n}`` worker map to the scalar
    ``parallel_workers`` every downstream consumer sees. Nothing below this layer
    learns that hosts exist.

    The argument is inert for every other provider -- host resolution happens only
    inside the ``ollama`` branch, so a stray ``--ollama-host`` alongside
    ``gemini`` / ``claude`` / ``openai_compat`` / ``openrouter`` changes nothing.
    """
    defaults_path = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"
    model_path = PROJECT_ROOT / "config" / "synthetic" / "axes" / "models" / f"{model_id}.yaml"
    strategy_path_file = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies" / f"{strategy_id}.yaml"
    country_path = PROJECT_ROOT / "config" / "synthetic" / "axes" / "countries" / f"{country_id}.yaml"

    for label, path in (
        ("experiment_defaults", defaults_path),
        (f"model '{model_id}'", model_path),
        (f"strategy '{strategy_id}'", strategy_path_file),
        (f"country '{country_id}'", country_path),
    ):
        if not path.exists():
            raise FileNotFoundError(f"Axis file not found for {label}: {path}")

    with open(defaults_path, "r", encoding="utf-8") as f:
        defaults = yaml.safe_load(f)
    with open(model_path, "r", encoding="utf-8") as f:
        model_data = yaml.safe_load(f)
    with open(strategy_path_file, "r", encoding="utf-8") as f:
        strategy_data = yaml.safe_load(f)
    with open(country_path, "r", encoding="utf-8") as f:
        country_data = yaml.safe_load(f)

    model_label = model_data["label"]
    strategy_label = strategy_data["label"]
    country_label = country_data["label"]
    name = f"{model_label} — {strategy_label} ({country_label})"

    model_cfg = model_data["model_config"]
    provider = model_cfg["provider"]
    model = model_cfg["model"]
    base_url = model_cfg.get("base_url") or None
    api_key_env_var = model_cfg.get("api_key_env_var") or None

    raw_gen_config = model_cfg.get("generation_config", {}) or {}
    generation_config = {k: v for k, v in raw_gen_config.items() if v is not None}

    defaults_params = defaults["parameters"]
    mode = defaults_params["mode"]
    log_llm = defaults_params["log_llm"]
    output = defaults_params["output"]
    output_base = defaults_params["output_base"]
    parallel_n = defaults_params["parallel"]["n"]
    retry_until_success = bool(defaults_params["parallel"].get("retry_until_success", False))
    structured_output = bool(
        model_data["parameters"].get("structured_output")
        or defaults_params.get("structured_output", False)
    )

    ollama_host = None
    if provider == "ollama":
        # The endpoint is a property of the selected host, not of the model: the
        # axis files carry no base_url, and the worker count is read per host.
        host = resolve_host(ollama_host_id)
        # The *resolved* id, not the argument: when ``ollama_host_id`` is None the
        # registry's default_host applied, and provenance must name the machine
        # that actually ran rather than record "unspecified".
        ollama_host = host.id
        base_url = host.base_url
        parallel_workers = _resolve_ollama_workers(model_data, host)
    else:
        parallel_workers = model_data["parameters"]["parallel"]["workers"]

    config_path = _resolve_path(country_data["parameters"]["config"])
    # The axis strategy yaml IS the strategy definition (single source of truth):
    # it carries the `categories` dict the generator reads, so the file itself is
    # the strategy path -- there is no separate strategy_defs json to point at.
    strategy_path = strategy_path_file.resolve()

    slug = axis_slug(model_id, strategy_id, country_id)
    parallel_output_dir = _resolve_path(f"{output_base}/01_Raw/{slug}")
    # The fidelity output folder is owned by the analysis registry (single source of truth
    # for the 03_Analysis/ layout), not hardcoded here.
    comparison_output_dir = _resolve_path(str(analysis_output_dir("fidelity", output_base) / slug))

    return ManifestConfig(
        name=name,
        provider=provider,
        model=model,
        generation_config=generation_config,
        mode=mode,
        config_path=config_path,
        strategy_path=strategy_path,
        log_llm=log_llm,
        output=output,
        parallel_n=parallel_n,
        parallel_workers=parallel_workers,
        parallel_output_dir=parallel_output_dir,
        comparison_output_dir=comparison_output_dir,
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        retry_until_success=retry_until_success,
        structured_output=structured_output,
        ollama_host=ollama_host,
    )


def serialize_manifest(config: ManifestConfig) -> str:
    """Convert a ManifestConfig to a YAML string suitable for writing as a snapshot file."""
    def _path_str(p: Path) -> str:
        try:
            rel = p.relative_to(PROJECT_ROOT)
            return rel.as_posix()
        except ValueError:
            return p.as_posix()

    standard_gen_config_keys = ("temperature", "top_p", "top_k", "max_output_tokens")
    gen_config_full = {k: config.generation_config.get(k) for k in standard_gen_config_keys}

    parallel: dict[str, Any] = {}
    if config.parallel_n is not None:
        parallel["n"] = config.parallel_n
    if config.parallel_workers is not None:
        parallel["workers"] = config.parallel_workers
    if config.parallel_output_dir is not None:
        parallel["output_dir"] = _path_str(config.parallel_output_dir)
    if config.retry_until_success:
        parallel["retry_until_success"] = config.retry_until_success

    model_cfg: dict[str, Any] = {
        "provider": config.provider,
        "model": config.model,
    }
    # Emitted before base_url because it is what produced it: a snapshot read
    # months later must say which GPU the run targeted, not just which URL.
    if config.ollama_host is not None:
        model_cfg["ollama_host"] = config.ollama_host
    if config.base_url is not None:
        model_cfg["base_url"] = config.base_url
    if config.api_key_env_var is not None:
        model_cfg["api_key_env_var"] = config.api_key_env_var
    model_cfg["generation_config"] = gen_config_full

    parameters: dict[str, Any] = {
        "mode": config.mode,
        "config": _path_str(config.config_path),
        "log_llm": config.log_llm,
        "output": config.output,
    }
    if config.structured_output:
        parameters["structured_output"] = config.structured_output
    if config.strategy_path is not None:
        parameters["strategy"] = _path_str(config.strategy_path)
    if parallel:
        parameters["parallel"] = parallel
    if config.comparison_output_dir is not None:
        parameters["comparison_output_dir"] = _path_str(config.comparison_output_dir)

    doc: dict[str, Any] = {
        "name": config.name,
        "model_config": model_cfg,
        "parameters": parameters,
    }

    return yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False)

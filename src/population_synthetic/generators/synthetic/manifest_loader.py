"""Load and validate YAML identity generation manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT

VALID_AXES = {"models", "strategies", "countries"}

VALID_PROVIDERS = {"gemini", "claude", "ollama", "openai_compat"}
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


def compose_manifest(model_id: str, strategy_id: str, country_id: str) -> ManifestConfig:
    """Compose a ManifestConfig from axis files and experiment defaults."""
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

    parallel_workers = model_data["parameters"]["parallel"]["workers"]

    config_path = _resolve_path(country_data["parameters"]["config"])
    # The axis strategy yaml IS the strategy definition (single source of truth):
    # it carries the `categories` dict the generator reads, so the file itself is
    # the strategy path -- there is no separate strategy_defs json to point at.
    strategy_path = strategy_path_file.resolve()

    slug = axis_slug(model_id, strategy_id, country_id)
    parallel_output_dir = _resolve_path(f"{output_base}/01_Raw/{slug}")
    comparison_output_dir = _resolve_path(f"{output_base}/03_Analysis/fidelity/{slug}")

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

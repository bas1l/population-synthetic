"""Load and validate YAML identity generation manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import yaml

from population_synth._paths import PROJECT_ROOT

VALID_PROVIDERS = {"gemini", "claude"}
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


def load_manifest(manifest_path: Union[str, Path]) -> ManifestConfig:
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
    )


def _resolve_path(rel_path: str) -> Path:
    """Resolve a manifest-relative path against PROJECT_ROOT."""
    return (PROJECT_ROOT / rel_path).resolve()

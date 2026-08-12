"""config.py -- the persona-realism judge configuration DTO (``judge.yaml``).

Extracted from :mod:`~population_synthetic.analysis.persona_realism.runner` so the
config can be loaded **without** dragging in the LLM client layer: every module of
this subpackage (and any downstream reader that needs only the ``bootstrap`` block)
imports :class:`JudgeConfig` from here, and nothing here imports the judge, the
client, matplotlib, or the analysis registry.

Config is the single source of truth (project invariant): :meth:`JudgeConfig.load`
raises on any missing or malformed key, and the ``reliability`` block is read through
:meth:`JudgeConfig.reliability_value` -- a **fail-fast** accessor with no in-code
default, so a tunable can never silently differ from what ``judge.yaml`` declares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["JudgeConfig"]


@dataclass(frozen=True)
class JudgeConfig:
    """The persona-realism judge configuration, loaded once from ``judge.yaml``.

    All fields are required in the YAML; :meth:`load` raises on any missing or
    malformed key. ``prompt_template`` is resolved to an absolute path relative to
    the config directory.

    ``severity_weights`` and ``impossibility_severities`` are **declared but not
    wired**: they are validated and stamped into provenance, but impossibility is
    decided solely by the ``can_exist`` majority (see ``reduce.reduce_persona``).
    ``judge.yaml`` documents this and every report carries a ``severity_config_status``
    note saying so, so the stamp can never be mistaken for an active knob.
    """

    judge_model: str
    model_options: tuple[str, ...]
    n_rounds: int
    temperature: float
    severity_weights: dict[str, float]
    impossibility_severities: tuple[str, ...]
    sample_size: int | None
    real_sample_size: int | None
    bootstrap: dict[str, Any]
    workers: int
    timeout_seconds: int
    prompt_template: Path
    config_dir: Path
    reliability: dict[str, Any] = field(default_factory=dict)

    def reliability_value(self, key: str) -> Any:
        """Return ``reliability[key]``, raising when it is absent (fail-fast).

        There is deliberately **no default argument**. Every one of these keys
        (``typicality_level``, ``tail_threshold``, ``variance_center``) changes a
        published number -- the tail-coverage cut, the chart's shaded region, the
        Levene centring -- so an in-code fallback would let the emitted artifacts
        disagree with the config that is supposed to describe them.
        """
        if key not in self.reliability:
            raise KeyError(
                f"judge config {self.config_dir / 'judge.yaml'} is missing "
                f"'reliability.{key}'. Declare it there (config is the single source "
                "of truth; there is no in-code default)."
            )
        return self.reliability[key]

    @classmethod
    def load(cls, config_dir: str | Path) -> JudgeConfig:
        """Read ``<config_dir>/judge.yaml`` into a validated config (fail-fast)."""
        config_dir = Path(config_dir)
        judge_path = config_dir / "judge.yaml"
        if not judge_path.exists():
            raise FileNotFoundError(f"judge config not found: {judge_path}")
        data = yaml.safe_load(judge_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"judge config {judge_path} did not parse to a mapping")

        required = [
            "judge_model", "model_options", "n_rounds", "temperature",
            "severity_weights", "impossibility_severities", "sample_size",
            "real_sample_size", "bootstrap", "workers", "timeout_seconds",
            "prompt_template",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"judge config {judge_path} is missing required keys: {missing}")

        template_path = (config_dir / str(data["prompt_template"])).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"prompt template not found: {template_path}")

        n_rounds = int(data["n_rounds"])
        if n_rounds < 1:
            raise ValueError(f"judge config 'n_rounds' must be >= 1, got {n_rounds}")
        workers = int(data["workers"])
        if workers < 1:
            raise ValueError(f"judge config 'workers' must be >= 1, got {workers}")
        timeout_seconds = int(data["timeout_seconds"])
        if timeout_seconds < 1:
            raise ValueError(f"judge config 'timeout_seconds' must be >= 1, got {timeout_seconds}")

        sample_size = data["sample_size"]
        if sample_size is not None:
            sample_size = int(sample_size)
            if sample_size < 1:
                raise ValueError(f"judge config 'sample_size' must be >= 1 or null, got {sample_size}")

        real_sample_size = data["real_sample_size"]
        if real_sample_size is not None:
            real_sample_size = int(real_sample_size)
            if real_sample_size < 1:
                raise ValueError(
                    f"judge config 'real_sample_size' must be >= 1 or null, got {real_sample_size}"
                )

        # The reliability block is required as a whole (its individual keys are read
        # fail-fast on use via `reliability_value`, which names the missing key).
        reliability = data.get("reliability")
        if not isinstance(reliability, dict) or not reliability:
            raise ValueError(
                f"judge config {judge_path} is missing a non-empty 'reliability' mapping "
                "(typicality_level, tail_threshold, variance_center)."
            )

        return cls(
            judge_model=str(data["judge_model"]),
            model_options=tuple(str(m) for m in data["model_options"]),
            n_rounds=n_rounds,
            temperature=float(data["temperature"]),
            severity_weights=dict(data["severity_weights"]),
            impossibility_severities=tuple(str(s) for s in data["impossibility_severities"]),
            sample_size=sample_size,
            real_sample_size=real_sample_size,
            bootstrap=dict(data["bootstrap"]),
            workers=workers,
            timeout_seconds=timeout_seconds,
            prompt_template=template_path,
            config_dir=config_dir,
            reliability=dict(reliability),
        )

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

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["JudgeConfig", "PROMPT_IDENTITY_KEYS", "load_persona_rendering", "persona_rendering_sha256"]

#: The prompt-identity stamps every verdict cache and report carries. Together they
#: pin exactly what text the judge read: the template file, and the judge-facing
#: rendering of category values substituted into its persona lines. Both are judge-
#: identity keys downstream, so changing either invalidates earlier verdicts.
PROMPT_IDENTITY_KEYS: tuple[str, ...] = ("prompt_template_sha256", "persona_rendering_sha256")


def persona_rendering_sha256(rendering: dict[str, dict[str, str]]) -> str:
    """SHA-256 of a judge-facing rendering map, canonicalised (key order irrelevant)."""
    canonical = json.dumps(rendering, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_persona_rendering(block: Any, config_dir: Path, judge_path: Path) -> dict[str, dict[str, str]]:
    """Validate the ``persona_rendering`` block against its mapping tier (fail-fast).

    Per attribute, the label keys must be **exactly** the canonical ``values`` of the
    category file the tier's ``_index.json`` names for it: a missing category raises
    (a partial map would leave some values coded and others rendered, and a value
    falling through unrendered is an in-code fallback), and a foreign key raises (it
    is a typo or a label from another tier). Rendered labels must be non-empty strings
    and pairwise distinct, so rendering can never merge two categories.
    """
    if not isinstance(block, dict):
        raise ValueError(f"judge config {judge_path} 'persona_rendering' must be a mapping")
    for key in ("mapping_tier", "labels"):
        if key not in block:
            raise ValueError(f"judge config {judge_path} 'persona_rendering' is missing {key!r}")
    tier_dir = (config_dir / str(block["mapping_tier"])).resolve()
    index_path = tier_dir / "_index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"judge config {judge_path} 'persona_rendering.mapping_tier' resolves to {tier_dir}, "
            "which has no _index.json"
        )
    index_attrs = json.loads(index_path.read_text(encoding="utf-8")).get("attributes")
    if not isinstance(index_attrs, dict) or not index_attrs:
        raise ValueError(f"mapping index {index_path} has no 'attributes' mapping")
    labels = block["labels"]
    if not isinstance(labels, dict) or not labels:
        raise ValueError(f"judge config {judge_path} 'persona_rendering.labels' must be a non-empty mapping")

    rendering: dict[str, dict[str, str]] = {}
    for attr, attr_labels in labels.items():
        if attr not in index_attrs:
            raise ValueError(
                f"judge config {judge_path} renders attribute {attr!r}, which {index_path} does not declare"
            )
        if not isinstance(attr_labels, dict) or not attr_labels:
            raise ValueError(f"judge config {judge_path} 'persona_rendering.labels.{attr}' must be a non-empty mapping")
        category_path = tier_dir / str(index_attrs[attr])
        values = json.loads(category_path.read_text(encoding="utf-8")).get("values")
        if not isinstance(values, list) or not values:
            raise ValueError(f"category file {category_path} has no 'values' list")
        canonical = {str(v) for v in values}
        declared = {str(k) for k in attr_labels}
        missing = sorted(canonical - declared)
        foreign = sorted(declared - canonical)
        if missing or foreign:
            raise ValueError(
                f"judge config {judge_path} 'persona_rendering.labels.{attr}' must cover exactly the "
                f"canonical categories of {category_path}: missing {missing}, not canonical {foreign}"
            )
        rendered = {str(k): v for k, v in attr_labels.items()}
        empty = sorted(k for k, v in rendered.items() if not isinstance(v, str) or not v.strip())
        if empty:
            raise ValueError(f"judge config {judge_path} renders {attr!r} categories {empty} as an empty label")
        if len(set(rendered.values())) != len(rendered):
            raise ValueError(f"judge config {judge_path} renders two {attr!r} categories with the same label")
        rendering[str(attr)] = rendered
    return rendering


def _load_stage2(block: Any, config_dir: Path, judge_path: Path) -> tuple[bool, Path, tuple[str, ...]]:
    """Validate the ``stage2`` block (fail-fast): ``enabled``, ``prompt_template``, ``persona_class_order``.

    The template must exist and its system text must state the configured persona-class
    order verbatim (``a > b > ...``): the prompt tells the classifier the order and the
    pipeline recomputes the persona class with it, so the two can never disagree.
    """
    from population_synthetic.analysis.persona_realism.prompt import load_prompt_template
    from population_synthetic.analysis.utils.realism_stage2_csv import validate_class_order

    if not isinstance(block, dict):
        raise ValueError(f"judge config {judge_path} 'stage2' must be a mapping")
    missing = [k for k in ("enabled", "prompt_template", "persona_class_order") if k not in block]
    if missing:
        raise ValueError(f"judge config {judge_path} 'stage2' is missing {missing}")
    enabled = block["enabled"]
    if not isinstance(enabled, bool):
        raise ValueError(f"judge config {judge_path} 'stage2.enabled' must be true or false, got {enabled!r}")
    template = (config_dir / str(block["prompt_template"])).resolve()
    if not template.exists():
        raise FileNotFoundError(f"stage-2 prompt template not found: {template}")
    order = validate_class_order(block["persona_class_order"], where=f"{judge_path} stage2.persona_class_order")
    system_str, _ = load_prompt_template(template)
    if " > ".join(order) not in " ".join(system_str.split()):
        raise ValueError(
            f"stage-2 prompt {template} does not state the configured persona-class order "
            f"{' > '.join(order)!r}; the prompt and judge.yaml must agree."
        )
    return enabled, template, order


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

    There is deliberately **no** ``temperature`` field: the judge runs through the
    ``claude`` CLI, which has no sampling-temperature control, so :meth:`load` raises
    on a ``temperature`` key rather than carry a value that is never applied.

    ``persona_rendering`` maps attribute -> {canonical value -> judge-facing label},
    validated against its mapping tier by :func:`load_persona_rendering`. It changes
    only the persona lines the judge reads; stored values stay canonical.
    """

    judge_model: str
    model_options: tuple[str, ...]
    n_rounds: int
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
    persona_rendering: dict[str, dict[str, str]] = field(default_factory=dict)
    stage2_enabled: bool = False
    stage2_prompt_template: Path | None = None
    stage2_persona_class_order: tuple[str, ...] = ()

    def prompt_identity(self) -> dict[str, str]:
        """The :data:`PROMPT_IDENTITY_KEYS` stamps for the prompt as configured now.

        The template hash reads the file at call time, so a template edited mid-session
        is never stamped with a stale hash.
        """
        return {
            "prompt_template_sha256": hashlib.sha256(Path(self.prompt_template).read_bytes()).hexdigest(),
            "persona_rendering_sha256": persona_rendering_sha256(self.persona_rendering),
        }

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
            "judge_model", "model_options", "n_rounds",
            "severity_weights", "impossibility_severities", "sample_size",
            "real_sample_size", "bootstrap", "workers", "timeout_seconds",
            "prompt_template", "persona_rendering", "stage2",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"judge config {judge_path} is missing required keys: {missing}")

        # A declared parameter the provider cannot honour is refused, not carried: the
        # `claude` CLI (the only judge route) has no sampling-temperature control, and
        # a stamped-but-unapplied temperature once made every report's provenance false.
        if "temperature" in data:
            raise ValueError(
                f"judge config {judge_path} declares 'temperature', but the judge runs "
                "through the `claude` CLI, which exposes no sampling-temperature control "
                "(no flag, no settings key). Remove the key: it would be recorded in "
                "provenance yet never applied."
            )

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

        stage2_enabled, stage2_template, stage2_order = _load_stage2(data["stage2"], config_dir, judge_path)

        return cls(
            judge_model=str(data["judge_model"]),
            model_options=tuple(str(m) for m in data["model_options"]),
            n_rounds=n_rounds,
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
            persona_rendering=load_persona_rendering(data["persona_rendering"], config_dir, judge_path),
            stage2_enabled=stage2_enabled,
            stage2_prompt_template=stage2_template,
            stage2_persona_class_order=stage2_order,
        )

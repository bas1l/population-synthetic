"""View-model dataclasses backing the launcher's experiment selection.

``ExperimentSelection`` holds the checked model/strategy/country axis IDs and
enumerates their cartesian product. ``ManifestDisplayInfo`` resolves a single
axis combination (or a manifest file) into display fields, strategy DAG path,
and an existing-persona count for the overview table.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from population_synthetic.identity.manifest_loader import ManifestConfig, load_manifest


@dataclass
class ExperimentSelection:
    model_ids: list[str] = field(default_factory=list)
    strategy_ids: list[str] = field(default_factory=list)
    country_ids: list[str] = field(default_factory=list)

    def combinations(self) -> list[tuple[str, str, str]]:
        return list(itertools.product(self.model_ids, self.strategy_ids, self.country_ids))

    @property
    def is_single(self) -> bool:
        return len(self.model_ids) == 1 and len(self.strategy_ids) == 1 and len(self.country_ids) == 1

    def first_combo(self) -> tuple[str, str, str] | None:
        if not self.model_ids or not self.strategy_ids or not self.country_ids:
            return None
        return (self.model_ids[0], self.strategy_ids[0], self.country_ids[0])


@dataclass
class ManifestDisplayInfo:
    path: Path | None
    config: ManifestConfig
    model_id: str | None = None
    strategy_id: str | None = None
    country_id: str | None = None
    existing_persona_count: int | None = None

    @property
    def display_name(self) -> str:
        return self.config.name or (self.path.stem if self.path else "")

    @property
    def strategy_name(self) -> str | None:
        p = self.config.strategy_path
        if p is None:
            return None
        return p.stem

    @property
    def strategy_path(self) -> Path | None:
        return self.config.strategy_path

    @classmethod
    def load_all(cls, manifests_dir: Path) -> list["ManifestDisplayInfo"]:
        results = []
        for p in sorted(manifests_dir.glob("*.yaml")):
            try:
                cfg = load_manifest(p)
                results.append(cls(path=p, config=cfg))
            except Exception as e:
                print(f"[manifest_model] Skipping {p.name}: {e}")
        return results

    @classmethod
    def from_axis(cls, model_id: str, strategy_id: str, country_id: str) -> "ManifestDisplayInfo":
        from population_synthetic.identity.manifest_loader import compose_manifest
        config = compose_manifest(model_id, strategy_id, country_id)
        output_dir = config.parallel_output_dir
        count = None
        if output_dir is not None and output_dir.exists():
            count = len(list(output_dir.glob("persona_*/identity.json")))
        return cls(
            path=None,
            config=config,
            model_id=model_id,
            strategy_id=strategy_id,
            country_id=country_id,
            existing_persona_count=count,
        )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from population_synth.identity.manifest_loader import ManifestConfig, load_manifest


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
        from population_synth.identity.manifest_loader import compose_manifest
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

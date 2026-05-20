from dataclasses import dataclass
from pathlib import Path

from population_synth.identity.manifest_loader import ManifestConfig, load_manifest


@dataclass
class ManifestDisplayInfo:
    path: Path
    config: ManifestConfig

    @property
    def display_name(self) -> str:
        return self.config.name or self.path.stem

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

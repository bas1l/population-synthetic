from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from population_synth._paths import PROJECT_ROOT


@dataclass
class ActionParameter:
    key: str
    label: str
    type: str  # "int", "bool", "str", "file"
    default: Any = None
    default_from_manifest: str | None = None
    help: str = ""


@dataclass
class ActionEntry:
    id: str
    label: str
    script: Path
    requires_manifest: bool
    parameters: list[ActionParameter] = field(default_factory=list)


def parse_launcher_config(yaml_path: Path) -> list[ActionEntry]:
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    entries: list[ActionEntry] = []
    for action in raw.get("actions", []):
        script_path = PROJECT_ROOT / action["script"]
        if not script_path.exists():
            print(f"[launcher_config] Warning: script not found, skipping action '{action['id']}': {script_path}")
            continue

        parameters = [
            ActionParameter(
                key=p["key"],
                label=p["label"],
                type=p["type"],
                default=p.get("default"),
                default_from_manifest=p.get("default_from_manifest"),
                help=p.get("help", ""),
            )
            for p in action.get("parameters", [])
        ]

        entries.append(
            ActionEntry(
                id=action["id"],
                label=action["label"],
                script=script_path,
                requires_manifest=action["requires_manifest"],
                parameters=parameters,
            )
        )

    return entries

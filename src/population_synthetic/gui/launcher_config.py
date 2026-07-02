"""Launcher config dataclasses parsed from ``config/gui/launcher.yaml``.

Defines ``ActionGroup``, ``ActionEntry``, ``ActionParameter`` and the
``LauncherConfig`` container, plus ``parse_launcher_config`` which reads the
YAML into these dataclasses. Supplies the action groups, scripts, and
parameter definitions that the PyQt5 launcher renders.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT


@dataclass
class ActionParameter:
    key: str
    label: str
    type: str  # "int", "bool", "str", "file", "choice"
    default: Any = None
    default_from_manifest: str | None = None
    help: str = ""
    choices: list[str] | None = None


VALID_AXIS_MODES = {"none", "per_combo", "batch"}


@dataclass
class ActionEntry:
    id: str
    label: str
    script: Path
    requires_manifest: bool
    axis_mode: str  # normalised: "none" | "per_combo" | "batch"
    group: str = ""
    parameters: list[ActionParameter] = field(default_factory=list)
    min_combos: int | None = None
    max_combos: int | None = None


@dataclass
class ActionGroup:
    id: str
    label: str


@dataclass
class LauncherConfig:
    groups: list[ActionGroup]
    actions: list[ActionEntry]
    default_action_id: str | None = None

    def actions_by_group(self) -> dict[str, list[ActionEntry]]:
        """Return actions keyed by group id, in group definition order."""
        result: dict[str, list[ActionEntry]] = {g.id: [] for g in self.groups}
        for action in self.actions:
            if action.group not in result:
                raise ValueError(
                    f"Action '{action.id}' references unknown group '{action.group}'. "
                    f"Known groups: {[g.id for g in self.groups]}"
                )
            result[action.group].append(action)
        return result


def parse_launcher_config(yaml_path: Path) -> LauncherConfig:
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # -- Parse groups ----------------------------------------------------------
    groups: list[ActionGroup] = []
    for g in raw.get("groups", []):
        groups.append(ActionGroup(id=g["id"], label=g["label"]))

    # -- Parse actions ---------------------------------------------------------
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
                choices=p.get("choices"),
            )
            for p in action.get("parameters", [])
        ]

        requires_manifest = action["requires_manifest"]
        # Run-mode is explicit when declared; otherwise derive from the legacy
        # ``requires_manifest`` boolean so untouched (e.g. Generate) actions keep
        # their behaviour: true -> per_combo, false -> none.
        raw_axis_mode = action.get("axis_mode")
        if raw_axis_mode is None:
            axis_mode = "per_combo" if requires_manifest else "none"
        else:
            axis_mode = raw_axis_mode
            if axis_mode not in VALID_AXIS_MODES:
                raise ValueError(
                    f"Action '{action['id']}' has invalid axis_mode {axis_mode!r}; "
                    f"must be one of {sorted(VALID_AXIS_MODES)}"
                )

        min_combos = action.get("min_combos")
        max_combos = action.get("max_combos")

        entries.append(
            ActionEntry(
                id=action["id"],
                label=action["label"],
                script=script_path,
                requires_manifest=requires_manifest,
                axis_mode=axis_mode,
                group=action.get("group", ""),
                parameters=parameters,
                min_combos=min_combos,
                max_combos=max_combos,
            )
        )

    default_action = raw.get("default_action")

    return LauncherConfig(groups=groups, actions=entries, default_action_id=default_action)

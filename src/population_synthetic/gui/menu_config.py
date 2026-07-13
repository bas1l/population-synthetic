"""gui menu configuration — ``FlowEntry`` dataclass and ``menu.yaml`` parser.

Port of the reference AnalysisRunnerGUI ``runner_config.py``. A flow entry may
be a single-script flow (``kind: script``, the default) or a workflow flow
(``kind: workflow``) whose scripts live per task inside its config YAML.

Fail-fast on schema violations (unknown ``kind``, ``kind: workflow`` with a
``script`` key, ``kind: script`` without one). Missing script/config *files*
on disk are lenient: the entry is skipped with a warning so the GUI still
launches with the remaining valid entries (mirrors the reference).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import yaml

_VALID_KINDS = ("script", "workflow")


@dataclass
class FlowEntry:
    """A single flow declared in ``config/gui/menu.yaml``.

    Attributes:
        name: Display name shown on the flow button.
        kind: ``"script"`` (single-script flow) or ``"workflow"`` (DAG of tasks).
        script: Absolute path to the Python script (``None`` for workflows —
            their scripts live per task inside the workflow config YAML).
        config: Absolute path to the flow's editable YAML.
        category: Category header under which this flow is grouped.
        axis_mode: Axis-selection dispatch mode (e.g. ``"three_axis"``), or
            ``None`` when the menu entry does not declare one.
    """

    name: str
    kind: str
    script: Path | None
    config: Path
    category: str
    axis_mode: str | None


def parse_menu_config(yaml_path: Path, project_root: Path) -> list[FlowEntry]:
    """Load ``menu.yaml`` and return validated :class:`FlowEntry` instances.

    Schema violations raise (fail-fast); entries whose ``script``/``config``
    files are missing on disk are skipped with a :mod:`warnings` warning.

    Args:
        yaml_path: Path to the ``menu.yaml`` file.
        project_root: Project root; relative paths in the YAML resolve
            against this directory.

    Returns:
        List of valid :class:`FlowEntry` instances in declaration order.

    Raises:
        FileNotFoundError: If *yaml_path* doesn't exist.
        yaml.YAMLError: If *yaml_path* contains invalid YAML.
        ValueError: If the menu structure is malformed, a flow declares an
            unknown ``kind``, a ``kind: workflow`` flow declares a ``script``,
            or a ``kind: script`` flow omits its ``script``.
    """
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict) or "categories" not in data:
        raise ValueError(f"gui menu {yaml_path}: expected a top-level 'categories' mapping")

    entries: list[FlowEntry] = []
    for category_block in data["categories"]:
        if not isinstance(category_block, dict) or "name" not in category_block:
            raise ValueError(f"gui menu {yaml_path}: each category needs a 'name' key")
        category: str = category_block["name"]
        for flow in category_block.get("flows", []):
            entry = _parse_flow(flow, category, yaml_path, project_root)
            if entry is not None:
                entries.append(entry)

    return entries


def _parse_flow(
    flow: dict,
    category: str,
    yaml_path: Path,
    project_root: Path,
) -> FlowEntry | None:
    """Validate one flow mapping; return an entry or ``None`` (warn-and-skip)."""
    if not isinstance(flow, dict) or "name" not in flow:
        raise ValueError(f"gui menu {yaml_path}: each flow needs a 'name' key (category '{category}')")
    name: str = flow["name"]

    kind: str = flow.get("kind", "script")
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"gui menu {yaml_path}: flow '{name}' has unknown kind '{kind}' (expected one of {_VALID_KINDS})"
        )

    if kind == "workflow" and "script" in flow:
        raise ValueError(
            f"gui menu {yaml_path}: flow '{name}' is 'kind: workflow' but declares a top-level "
            f"'script' — workflow scripts live per task in its config YAML"
        )
    if kind == "script" and "script" not in flow:
        raise ValueError(f"gui menu {yaml_path}: flow '{name}' is 'kind: script' but has no 'script' key")

    if "config" not in flow:
        raise ValueError(f"gui menu {yaml_path}: flow '{name}' has no 'config' key")

    script = project_root / flow["script"] if kind == "script" else None
    config = project_root / flow["config"]

    if script is not None and not script.exists():
        warnings.warn(f"gui: skipping flow '{name}' — script not found: {script}", stacklevel=2)
        return None
    if not config.exists():
        warnings.warn(f"gui: skipping flow '{name}' — config not found: {config}", stacklevel=2)
        return None

    return FlowEntry(
        name=name,
        kind=kind,
        script=script,
        config=config,
        category=category,
        axis_mode=flow.get("axis_mode"),
    )

"""Pure CLI command builders shared by script flows and workflow tasks.

Execution contract: on Run the GUI TRANSLATES the flow's YAML into CLI
invocations of the existing scripts — the spawned scripts do NOT read the
flow YAML (there is no ``--flow-config`` argument; do not add one). Save is
persistence only.

Both builders are pure functions (no Qt, no I/O, no subprocess) returning arg
vectors that start with ``[sys.executable, str(script), ...]``, so combo
dispatch is unit-testable headlessly.

Option translation rules (identical to the legacy launcher's
``CombinationRunner`` / batch ``--slug`` path in ``gui/main_window.py``):

- ``bool`` ``True``  → ``--key`` (bare flag)
- ``bool`` ``False`` → omitted
- ``None`` or ``""`` → omitted (the script's own default applies)
- anything else     → ``--key str(value)``

Option keys are the CLI flag names in dash form (``no-charts`` →
``--no-charts``) — see the per-flow YAML headers under ``config/gui/flows/``.

Note: ``three_axis`` script flows currently execute through the reused
``CombinationRunner`` (imported from the legacy ``gui.main_window``), which
applies these same rules internally; these builders are the single reusable
implementation for the Phase 6/7 workflow tasks and for headless tests.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from population_synthetic.generators.synthetic.manifest_loader import axis_slug

Combo = tuple[str, str, str]  # (model_id, strategy_id, country_id)


def _option_args(options: Mapping[str, Any]) -> list[str]:
    """Translate an ``options:`` mapping into CLI args (rules in module docstring)."""
    args: list[str] = []
    for key, value in options.items():
        if isinstance(value, bool):
            if value:
                args.append(f"--{key}")
        elif value is not None and value != "":
            args += [f"--{key}", str(value)]
    return args


def build_per_combo_cmds(
    script: Path,
    combos: Sequence[Combo],
    options: Mapping[str, Any],
    force: bool,
) -> list[list[str]]:
    """One arg vector per combo: ``--model-id/--strategy-id/--country-id`` dispatch.

    Mirrors the command shape built inside the legacy ``CombinationRunner.run``:
    axis ids first, then ``--force`` (when requested), then the option args.

    Raises:
        ValueError: If *combos* is empty (an empty batch is a caller bug —
            the GUI guards empty selections before dispatch).
    """
    if not combos:
        raise ValueError(f"build_per_combo_cmds: no combos selected for {script}")
    cmds: list[list[str]] = []
    for model_id, strategy_id, country_id in combos:
        cmd = [
            sys.executable,
            str(script),
            "--model-id", model_id,
            "--strategy-id", strategy_id,
            "--country-id", country_id,
        ]
        if force:
            cmd.append("--force")
        cmd += _option_args(options)
        cmds.append(cmd)
    return cmds


def build_per_country_cmds(
    script: Path,
    combos: Sequence[Combo],
    force: bool,
    options: Mapping[str, Any],
) -> list[list[str]]:
    """One arg vector per DISTINCT country in *combos*: ``--country-id`` only.

    Collapses the checked model x strategy x country combos down to their
    distinct ``country_id`` values, in first-seen (stable) order, and emits one
    command per country -- model/strategy ticks are ignored, since the backing
    script operates on the real reference population only.

    Raises:
        ValueError: If *combos* is empty (an empty batch is a caller bug —
            the GUI guards empty selections before dispatch).
    """
    if not combos:
        raise ValueError(f"build_per_country_cmds: no combos selected for {script}")
    countries: list[str] = []
    seen: set[str] = set()
    for _model_id, _strategy_id, country_id in combos:
        if country_id not in seen:
            seen.add(country_id)
            countries.append(country_id)
    cmds: list[list[str]] = []
    for country_id in countries:
        cmd = [sys.executable, str(script), "--country-id", country_id]
        if force:
            cmd.append("--force")
        cmd += _option_args(options)
        cmds.append(cmd)
    return cmds


def build_slugs_cmd(
    script: Path,
    combos: Sequence[Combo],
    options: Mapping[str, Any],
    force: bool,
) -> list[str]:
    """ONE arg vector with one ``--slug {country}_{strategy}_{model}`` per combo.

    Slugs come from :func:`axis_slug` (the single source of truth for the slug
    format); ``--force`` (when requested) is inserted right after the script
    path — before the slug list — then option args follow the slugs, mirroring
    the legacy launcher's batch (``axis_mode: batch``) command shape.

    Raises:
        ValueError: If *combos* is empty (a ``--slug``-less invocation would
            silently fall back to the script's own discovery).
    """
    if not combos:
        raise ValueError(f"build_slugs_cmd: no combos selected for {script}")
    cmd = [sys.executable, str(script)]
    if force:
        cmd.append("--force")
    for model_id, strategy_id, country_id in combos:
        cmd += ["--slug", axis_slug(model_id, strategy_id, country_id)]
    cmd += _option_args(options)
    return cmd

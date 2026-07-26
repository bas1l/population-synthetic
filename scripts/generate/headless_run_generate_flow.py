#!/usr/bin/env python
"""Headless, zero-argument launcher for a *generate* flow.

Run this file directly (``python scripts/generate/headless_run_generate_flow.py``,
or F5 in an IDE) to execute a GUI *generate* flow without the PyQt Flow Runner.
It reproduces the GUI "RUN" button exactly by reusing the GUI's own pure command
builder (:func:`population_synthetic.gui.commands.build_per_combo_cmds`), so this
headless path can never drift from what the GUI does.

Everything is hardcoded via the CONFIG block below — no CLI arguments — so it runs
headlessly with a single launch. The *flow options / model selection / force*
still come from the flow YAML (config is the single source of truth); only the
launcher knobs (which YAML, which script, dry-run, run limits) are hardcoded here.

Contract reproduced (identical to ``CombinationRunner.run``):
  * combos = itertools.product(models, strategies, countries), each axis id list
    sorted ascending by id (the GUI's discovery/display order), model-major.
  * per-combo argv: --model-id/--strategy-id/--country-id, then --force (only if
    the YAML's top-level ``force: true``), then the option args in YAML key order
    (bool True -> bare flag; bool False / None / "" -> omitted; else --key value).
  * sequential: one subprocess at a time, stdout+stderr merged, inheriting env/cwd
    and the current interpreter (``sys.executable``).
"""
from __future__ import annotations

import itertools
import subprocess
import sys
import time
from pathlib import Path

from population_synthetic.gui.commands import build_per_combo_cmds

# --- Repo-relative paths (robust regardless of cwd / launch dir) --------------
# scripts/generate/<this file>  ->  parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# ============================== CONFIG (edit me) ==============================
# The generate flow YAML to run. Its options/selection/force are the source of
# truth — edit the YAML to change models, strategies, n, workers, retry, etc.
FLOW_YAML = REPO_ROOT / "config" / "gui" / "flows" / "generate_parallel.yaml"

# The per-combo script the GUI dispatches for a generate flow.
GENERATE_SCRIPT = REPO_ROOT / "scripts" / "generate" / "generate_identities_parallel.py"

# Run knobs -------------------------------------------------------------------
DRY_RUN = False          # True: print the plan + argv, run nothing.
MAX_COMBOS: int | None = None   # e.g. 1 to run only the first combo; None = all.
# Option overrides layered OVER the YAML options, for quick runs only
# (e.g. {"n": 5} for a fast pass). Leave empty {} to honor the YAML verbatim.
OPTION_OVERRIDES: dict[str, object] = {}
# =============================================================================


def _load_yaml(path: Path) -> dict:
    try:
        from ruamel.yaml import YAML

        with open(path, encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)
    except ModuleNotFoundError:
        import yaml  # PyYAML fallback

        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)


def _combos(selection: dict) -> list[tuple[str, str, str]]:
    """Model-major cartesian product, each axis sorted by id (GUI display order)."""
    models = sorted(selection.get("models", []))
    strategies = sorted(selection.get("strategies", []))
    countries = sorted(selection.get("countries", []))
    return list(itertools.product(models, strategies, countries))


def main() -> int:
    flow = _load_yaml(FLOW_YAML)
    options = dict(flow.get("options") or {})
    options.update(OPTION_OVERRIDES)
    selection = flow.get("selection") or {}
    force = bool(flow.get("force", False))

    combos = _combos(selection)
    if MAX_COMBOS is not None:
        combos = combos[:MAX_COMBOS]

    cmds = build_per_combo_cmds(GENERATE_SCRIPT, combos, options, force)

    print(f"[flow]   {FLOW_YAML}", flush=True)
    print(f"[script] {GENERATE_SCRIPT}", flush=True)
    print(f"[python] {sys.executable}", flush=True)
    print(f"[force]  {force}   [overrides] {OPTION_OVERRIDES or '-'}", flush=True)
    print(f"[combos] {len(combos)} (model-major, each axis sorted by id):", flush=True)
    for i, c in enumerate(combos, 1):
        print(f"         {i:>2}. {c[0]}  x  {c[1]}  x  {c[2]}", flush=True)

    if DRY_RUN:
        print("\n[dry-run] per-combo argv:", flush=True)
        for cmd in cmds:
            print("  " + " ".join(cmd), flush=True)
        return 0

    results: list[tuple[str, int, float]] = []
    t0 = time.time()
    for i, (combo, cmd) in enumerate(zip(combos, cmds), 1):
        header = f"{combo[0]} x {combo[1]} x {combo[2]}"
        print(f"\n{'=' * 78}\n[{i}/{len(cmds)}] {header}\n  {' '.join(cmd)}\n{'=' * 78}", flush=True)
        ct0 = time.time()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait()
        dt = time.time() - ct0
        results.append((header, proc.returncode, dt))
        print(f"\n[{i}/{len(cmds)}] {header} -> exit {proc.returncode} in {dt / 60:.1f} min", flush=True)

    total = time.time() - t0
    failed = sum(1 for _, rc, _ in results if rc != 0)
    print(f"\n{'#' * 78}\n[SUMMARY] {len(cmds)} combos in {total / 60:.1f} min "
          f"({len(cmds) - failed} ok / {failed} failed)\n{'#' * 78}", flush=True)
    for header, rc, dt in results:
        print(f"  {('OK ' if rc == 0 else f'FAIL({rc})'):>8}  {header}  [{dt / 60:.1f} min]", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

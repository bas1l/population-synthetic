"""Shared loader for the ``scripts/generate`` CLI drivers.

``scripts/`` is not an importable package, so a test that exercises a driver has
to load it by file path. Doing that per test file would import the same module
several times over, and each import attaches a console handler to the root
logger -- so the second copy would double every log line the whole session emits.
The loaded module is therefore cached in ``sys.modules`` under its own name and
shared by every caller.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

from population_synthetic._paths import PROJECT_ROOT

_PARALLEL_DRIVER = "generate_identities_parallel"


def load_parallel_driver() -> ModuleType:
    """Return ``scripts/generate/generate_identities_parallel.py`` as a module."""
    module = sys.modules.get(_PARALLEL_DRIVER)
    if module is None:
        path = PROJECT_ROOT / "scripts" / "generate" / f"{_PARALLEL_DRIVER}.py"
        spec = importlib.util.spec_from_file_location(_PARALLEL_DRIVER, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PARALLEL_DRIVER] = module
        spec.loader.exec_module(module)
    return module

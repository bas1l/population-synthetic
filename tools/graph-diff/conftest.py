"""Pytest bootstrap for the standalone graph-diff tool.

Puts this tool's root (the directory containing the ``graphdiff`` package) on
``sys.path`` so ``import graphdiff`` resolves when the suite is run from the
repository root (``pytest tools/graph-diff/tests/...``) without installing the
tool or touching the host project's packaging. Keeps the tool self-contained.
"""

import sys
from pathlib import Path

_TOOL_ROOT = Path(__file__).resolve().parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

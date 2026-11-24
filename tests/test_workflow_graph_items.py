"""Unit tests for the workflow graph node's run-state overlay table.

:meth:`WorkflowTaskNode.paint` looks the current status up in ``_STATUS_OVERLAY``
with a bare subscript, so a :class:`TaskStatus` member missing from the table is
a ``KeyError`` raised mid-paint — i.e. at run time, in the GUI, on the one status
nobody exercised. The table is module-level data, so the exhaustiveness check
needs no ``QApplication`` and no display; only the PyQt5 import at module load.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from population_synthetic.gui.widgets.workflow_graph_items import _STATUS_OVERLAY  # noqa: E402
from population_synthetic.gui.workflow_state import TaskStatus  # noqa: E402


def test_status_overlay_covers_every_task_status() -> None:
    """Every TaskStatus member has an overlay entry (guards the bare paint lookup)."""
    missing = [status.name for status in TaskStatus if status not in _STATUS_OVERLAY]
    assert not missing, f"TaskStatus members without a _STATUS_OVERLAY entry: {missing}"


def test_status_overlay_has_no_unknown_keys() -> None:
    """The overlay table carries no key that is not a TaskStatus member."""
    assert set(_STATUS_OVERLAY) <= set(TaskStatus)


def test_bypassed_overlay_is_undimmed_and_distinct() -> None:
    """BYPASSED paints violet, undimmed — accounted for, not skipped, not completed."""
    fill, border, width, dim, glyph = _STATUS_OVERLAY[TaskStatus.BYPASSED]

    assert fill is not None and fill.name() == "#e3e0f0"
    assert border.name() == "#5c4b99"
    assert width == 2.0
    assert dim is False
    assert glyph == "»"

    completed_fill, completed_border, _, _, completed_glyph = _STATUS_OVERLAY[TaskStatus.COMPLETED]
    assert (border.name(), glyph) != (completed_border.name(), completed_glyph)
    assert fill != completed_fill

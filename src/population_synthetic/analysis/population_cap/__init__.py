"""population_cap -- the validation gate's seeded cap of each combo's clean personas to N.

Package entry re-exporting the per-combo cap routine, the full-N rule's typed input and
its withdrawal counterpart, plus the summary type they share. Deliberately free of
GUI/CLI concerns: the CLI entrypoint (``scripts/analyze/cap_populations.py``) and the GUI
workflow build on this, not the other way round.
"""

from __future__ import annotations

from population_synthetic.analysis.population_cap.cap import (
    CapSummary,
    CleanSelection,
    cap_combo,
    clean_selection,
    withdraw_combo,
)

__all__ = [
    "CapSummary",
    "CleanSelection",
    "cap_combo",
    "clean_selection",
    "withdraw_combo",
]

"""population_cap -- the pre-mapping seeded cap of each combo's personas to N.

Package entry re-exporting the per-combo cap routine and its summary type. Deliberately
free of GUI/CLI concerns: the CLI entrypoint (``scripts/analyze/cap_populations.py``)
and the GUI workflow build on this, not the other way round.
"""

from __future__ import annotations

from population_synthetic.analysis.population_cap.cap import CapSummary, cap_combo

__all__ = ["CapSummary", "cap_combo"]

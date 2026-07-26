"""validate_mapped -- per-combo unmapped-value check for mapped personas.

Package entry re-exporting the check routine and its summary/row types. Free of GUI/CLI
concerns: the CLI entrypoint (``scripts/analyze/validate_mapped_personas.py``) and the
GUI workflow build on this. Runs between ``mapping`` and ``population_cap``.
"""

from __future__ import annotations

from population_synthetic.analysis.validate_mapped.validate import (
    SUMMARY_HEADER,
    MappedPersonaRow,
    ValidateMappedSummary,
    evaluate_individuals,
    summary_row,
    unmapped_fields,
    validate_mapped_combo,
)

__all__ = [
    "SUMMARY_HEADER",
    "MappedPersonaRow",
    "ValidateMappedSummary",
    "evaluate_individuals",
    "summary_row",
    "unmapped_fields",
    "validate_mapped_combo",
]

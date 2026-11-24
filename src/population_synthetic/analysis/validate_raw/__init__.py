"""validate_raw -- the analysis-DAG root: per-combo raw-persona completeness check.

Package entry re-exporting the completeness routine, its config-driven expected-key
resolver, and the summary/row types. Free of GUI/CLI concerns: the CLI entrypoint
(``scripts/analyze/validate_raw_personas.py``) and the GUI workflow build on this.
"""

from __future__ import annotations

from population_synthetic.analysis.validate_raw.validate import (
    SUMMARY_HEADER,
    RawPersonaRow,
    ValidateRawSummary,
    expected_raw_keys,
    summary_row,
    validate_raw_combo,
)

__all__ = [
    "SUMMARY_HEADER",
    "RawPersonaRow",
    "ValidateRawSummary",
    "expected_raw_keys",
    "summary_row",
    "validate_raw_combo",
]

"""Demographic-profile extraction helpers.

Contains only the generic text helpers used by the config-driven flat-path
engine: separator normalisation, UTF-8 double-encoding repair, and fuzzy
substring matching (``extract.mappings``).  The former narrative/batch
submodules (``normalizers_se``, ``normalizers_it``, ``prose_inference``,
``batch``, ``schema_labels``) have been retired.
"""

from __future__ import annotations

"""Demographic-profile extraction subpackage.

Splits the former monolithic ``extractor`` module into focused submodules:
schema label constants, mapping/lookup helpers, Swedish and Italian normalizers,
prose inference, and the batch / flat format extractors.  The public entry
points remain :func:`population_synth.comparison.extractor.extract_individual`
and :func:`population_synth.comparison.extractor.extract_population`.
"""

from __future__ import annotations

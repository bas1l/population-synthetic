"""Swedish (SCB) real mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synthetic.analysis.mapping.real_mapper.base import BaseRealMapper


class SwedishRealMapper(BaseRealMapper):
    """Normalize raw SCB real records to the canonical schema.

    Country divergence is entirely the mapping directory: every label, including the
    domestic-birth collapse, lives in ``config/mapping/scb_native/`` (the native
    high-fidelity tier). This ``MAPPINGS_SUBDIR`` must stay in sync with the
    ``parameters.mappings`` path in ``config/synthetic/axes/countries/swedish.yaml``
    (the single source of truth); ``country_config.assert_mapping_dir_consistency``
    fails loud at scheme-load time if they drift apart.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "scb_native"

"""Swedish (SCB) synthetic-population mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synthetic.analysis.mapping.synthetic_mapper.base import BaseSyntheticMapper


class SwedishSyntheticMapper(BaseSyntheticMapper):
    """Map Swedish (SCB) pipeline identities to the canonical schema.

    Country divergence is entirely the mapping directory
    (``config/mapping/scb_native/``): every label and keyword cascade lives there.
    This is the **native high-fidelity tier**; it must stay in sync with the
    ``parameters.mappings`` path in ``config/synthetic/axes/countries/swedish.yaml``
    (the single source of truth), which is asserted at scheme-load time by
    ``country_config.assert_mapping_dir_consistency``.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "scb_native"

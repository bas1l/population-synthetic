"""Per-persona estimated USD cost from a config-driven pricing table.

Given a persona's summed input/output tokens and its combo's model axis id, look
up the per-model rate in a :class:`~population_synthetic.analysis.generation_metadata.pricing.PricingTable`
and return the estimated cost. This module knows nothing about timestamps, file
layout, slugs, or charts -- it is pure token->dollars arithmetic over the pricing
table.

Gating and fail-fast policy (authoritative -- see the plan Definitions):
- **None (ungated)** when the persona has no token telemetry (both ``input_tokens``
  and ``output_tokens`` are ``None``) -- there is nothing to price, and ``None``
  (not ``0``) keeps "absent" distinct from a genuine zero cost.
- **Raises** (via :meth:`PricingTable.get`) when the persona *has* token telemetry
  but the model id is absent from the pricing table -- an unpriceable-but-costed
  run is a config gap that must surface, never be papered over with a default.
- A priced model with a genuine zero rate (``ollama_*``) returns ``0.0``.
"""

from __future__ import annotations

from population_synthetic.analysis.generation_metadata.pricing import PricingTable

__all__ = ["persona_cost"]

# USD-per-token divisor: pricing rates are quoted per 1,000,000 tokens.
_PER_MILLION = 1_000_000.0


def persona_cost(
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    pricing: PricingTable,
    *,
    cache_read_tokens: int | None = 0,
    cache_creation_tokens: int | None = 0,
) -> float | None:
    """Estimated USD cost for one persona; ``None`` when ungated, raises when unpriceable.

    Parameters
    ----------
    model_id:
        The model axis id of the persona's combo (the pricing-table join key).
    input_tokens, output_tokens:
        The persona's summed prompt / completion tokens (``None`` when the
        provider reported none for that side).
    pricing:
        The loaded :class:`PricingTable`.
    cache_read_tokens, cache_creation_tokens:
        Optional prompt-cache token sums. When either is > 0 the input component
        gains ``cache_read_tokens * price_in * read_mult / 1e6`` and
        ``cache_creation_tokens * price_in * write_mult / 1e6``, with the
        multipliers sourced from the pricing config's ``cache_multipliers`` block.
        Defaulting both to 0 keeps existing positional callers byte-for-byte
        identical -- the cache branch is never entered when they are absent.

    Returns
    -------
    float | None
        ``in_tok * price_in / 1e6 + out_tok * price_out / 1e6`` (plus the cache
        component when cache tokens are supplied), or ``None`` when the persona has
        no prompt/completion token telemetry at all.

    Raises
    ------
    KeyError
        When the persona has token telemetry but *model_id* is absent from the
        pricing table (delegated to :meth:`PricingTable.get`).
    ValueError
        When cache tokens are supplied but the pricing config omits the
        ``cache_multipliers`` block (delegated to :meth:`PricingTable.cache_mults`).
    """
    if input_tokens is None and output_tokens is None:
        return None
    price_in, price_out = pricing.get(model_id)  # raises loudly if the id is unknown
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    cost = in_tok * price_in / _PER_MILLION + out_tok * price_out / _PER_MILLION

    cache_read = cache_read_tokens or 0
    cache_creation = cache_creation_tokens or 0
    if cache_read or cache_creation:
        read_mult, write_mult = pricing.cache_mults()  # raises if the block is absent
        cost += cache_read * price_in * read_mult / _PER_MILLION
        cost += cache_creation * price_in * write_mult / _PER_MILLION
    return cost

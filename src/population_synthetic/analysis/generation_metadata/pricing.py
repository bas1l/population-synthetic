"""Parse and validate the per-model LLM pricing table.

Loads ``config/analysis/model_pricing.yaml`` (the single source of truth for
generation cost) into an immutable ``PricingTable``. Prices are USD per 1,000,000
tokens, keyed by the model **axis id** (the same id used in run slugs and
``discover_axis_values("models")``), so the join to a generation combo is exact.

The loader fails loudly (raises) on a missing file, a malformed structure, or a
malformed per-model rate entry -- it never silently defaults, per the project
invariant that config is the single source of truth. This module knows nothing
about personas, runs, timestamps, or charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT

_PRICING_PATH = PROJECT_ROOT / "config" / "analysis" / "model_pricing.yaml"

# Top-level keys the pricing config must declare (fail-fast if any is absent).
_REQUIRED_TOP_KEYS = ("observed_date", "source", "currency", "models")


@dataclass(frozen=True)
class PricingTable:
    """Immutable per-model pricing, USD per 1,000,000 tokens.

    ``rates`` maps a model axis id to ``(price_in, price_out)`` -- the input- and
    output-token rates in USD per 1M tokens. ``observed_date``/``source``/
    ``currency`` are the provenance stamps carried through to analysis output.
    """

    rates: dict[str, tuple[float, float]]
    observed_date: str
    source: str
    currency: str
    # Prompt-cache pricing multipliers relative to the base input rate, e.g.
    # ``{"read": 0.1, "write": 1.25}``. ``None`` when the config omits the block --
    # optional so callers that never supply cache tokens are unaffected.
    cache_multipliers: dict[str, float] | None = None

    def __contains__(self, model_id: str) -> bool:
        return model_id in self.rates

    def cache_mults(self) -> tuple[float, float]:
        """Return ``(read_mult, write_mult)``; raise if the config omitted the block.

        Fail-fast: cost pricing that needs cache multipliers but finds none is a
        configuration gap the caller must surface, never paper over with a default.
        """
        if self.cache_multipliers is None:
            raise ValueError(
                "Cache tokens supplied but the pricing table has no 'cache_multipliers' "
                f"block ({_PRICING_PATH}). Add a top-level 'cache_multipliers: {{read, write}}'."
            )
        return self.cache_multipliers["read"], self.cache_multipliers["write"]

    def get(self, model_id: str) -> tuple[float, float]:
        """Return ``(price_in, price_out)`` for *model_id*; raise if absent.

        Fail-fast: a model that has token telemetry but no pricing entry is a
        configuration gap the caller must surface, not paper over with a default.
        """
        if model_id not in self.rates:
            raise KeyError(
                f"Model id {model_id!r} has no entry in the pricing table "
                f"({_PRICING_PATH}). Known ids: {sorted(self.rates)}."
            )
        return self.rates[model_id]


def _coerce_rate(model_id: str, entry: Any) -> tuple[float, float]:
    """Validate one ``{in, out}`` rate entry and return ``(in, out)`` as floats."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Pricing entry for {model_id!r} must be a mapping with 'in'/'out', "
            f"got {type(entry).__name__}: {_PRICING_PATH}"
        )
    missing = [k for k in ("in", "out") if k not in entry]
    if missing:
        raise ValueError(
            f"Pricing entry for {model_id!r} missing required key(s) {missing}: {_PRICING_PATH}"
        )
    try:
        price_in = float(entry["in"])
        price_out = float(entry["out"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Pricing entry for {model_id!r} has non-numeric rate(s): {entry!r} ({_PRICING_PATH})"
        ) from exc
    if price_in < 0 or price_out < 0:
        raise ValueError(
            f"Pricing entry for {model_id!r} has a negative rate: {entry!r} ({_PRICING_PATH})"
        )
    return (price_in, price_out)


def _coerce_cache_multipliers(raw: Any, cfg_path: Path) -> dict[str, float] | None:
    """Validate the optional top-level ``cache_multipliers`` block, or return ``None``.

    Absent -> ``None`` (feature off; callers that pass no cache tokens are unaffected).
    Present -> must be a mapping with numeric, non-negative ``read`` and ``write``.
    """
    if "cache_multipliers" not in raw or raw["cache_multipliers"] in (None, ""):
        return None
    block = raw["cache_multipliers"]
    if not isinstance(block, dict):
        raise ValueError(
            f"'cache_multipliers' must be a mapping with 'read'/'write', "
            f"got {type(block).__name__}: {cfg_path}"
        )
    missing = [k for k in ("read", "write") if k not in block]
    if missing:
        raise ValueError(f"'cache_multipliers' missing required key(s) {missing}: {cfg_path}")
    try:
        read_mult = float(block["read"])
        write_mult = float(block["write"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"'cache_multipliers' has non-numeric value(s): {block!r} ({cfg_path})"
        ) from exc
    if read_mult < 0 or write_mult < 0:
        raise ValueError(f"'cache_multipliers' has a negative value: {block!r} ({cfg_path})")
    return {"read": read_mult, "write": write_mult}


def load_pricing_table(path: Path | str | None = None) -> PricingTable:
    """Load and validate the pricing table (fail-fast).

    Parameters
    ----------
    path:
        Optional override for the config path; defaults to
        ``config/analysis/model_pricing.yaml``.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    ValueError
        If the file is not a mapping, is missing a required top-level key, has an
        empty/malformed ``models`` block, or has a malformed per-model rate entry.
    """
    cfg_path = Path(path) if path is not None else _PRICING_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Model pricing config not found: {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Model pricing config must be a mapping, got {type(raw).__name__}: {cfg_path}")

    missing = [k for k in _REQUIRED_TOP_KEYS if k not in raw or raw[k] in (None, "")]
    if missing:
        raise ValueError(f"Model pricing config missing required top-level key(s) {missing}: {cfg_path}")

    models = raw["models"]
    if not isinstance(models, dict) or not models:
        raise ValueError(f"Model pricing config missing non-empty 'models' mapping: {cfg_path}")

    rates = {str(model_id): _coerce_rate(str(model_id), entry) for model_id, entry in models.items()}
    cache_multipliers = _coerce_cache_multipliers(raw, cfg_path)

    return PricingTable(
        rates=rates,
        observed_date=str(raw["observed_date"]),
        source=str(raw["source"]),
        currency=str(raw["currency"]),
        cache_multipliers=cache_multipliers,
    )

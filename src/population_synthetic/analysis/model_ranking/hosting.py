"""hosting.py -- Classify each model as local or hosted from config.

Turns the config-declared provider -> ``local``/``hosted`` grouping
(``config/analysis/model_ranking/provider_hosting.json``) into a per-model
provenance map keyed by model id, for the manuscript performance tables. The
rule ("a model is *local* iff its ``model_config.provider`` is grouped ``local``")
lives entirely in config: this module carries no baked-in provider list and no
``x or DEFAULT`` fallback.

Failure policy (fail-fast):

* a missing or malformed config file raises;
* a model whose ``model_config.provider`` is absent from the config map raises,
  naming the provider and model -- never silently defaulting to a class.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_VALID_CLASSES = {"local", "hosted"}


def load_hosting_config(path: str | Path) -> dict[str, str]:
    """Load and validate the provider -> hosting-class map from *path*.

    Returns the ``{provider: "local"|"hosted"}`` mapping (the config's
    ``providers`` block). Raises :class:`FileNotFoundError` when the file is
    missing and :class:`ValueError` when its shape or values are malformed.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Provider-hosting config not found: {path}. Expected "
            "config/analysis/model_ranking/provider_hosting.json."
        )

    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Provider-hosting config must be a JSON object, got {type(raw).__name__}: {path}")

    providers = raw.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError(
            f"Provider-hosting config {path} must have a non-empty 'providers' object "
            f"mapping each provider to a hosting class, got {providers!r}."
        )

    for provider, cls in providers.items():
        if cls not in _VALID_CLASSES:
            raise ValueError(
                f"Provider-hosting config {path} maps provider {provider!r} to invalid class "
                f"{cls!r}; must be one of {sorted(_VALID_CLASSES)}."
            )

    return dict(providers)


def classify_hosting(
    model_dicts: list[dict[str, Any]],
    hosting_config: dict[str, str],
) -> dict[str, str]:
    """Map each model id to its hosting class using *hosting_config*.

    *model_dicts* are the parsed model YAML dicts (as returned by
    ``discover_axis_values("models")``): each carries ``id`` and
    ``model_config.provider``. Raises :class:`KeyError` on a malformed model dict
    (missing ``id`` / ``model_config`` / ``provider``) and :class:`ValueError`
    when a model's provider is not present in *hosting_config* (fail-fast: no
    default class).
    """
    result: dict[str, str] = {}
    for model in model_dicts:
        if "id" not in model:
            raise KeyError(f"Model dict is missing 'id': {model!r}")
        model_id = model["id"]

        model_cfg = model.get("model_config")
        if not isinstance(model_cfg, dict) or "provider" not in model_cfg:
            raise KeyError(
                f"Model {model_id!r} is missing 'model_config.provider'."
            )
        provider = model_cfg["provider"]

        if provider not in hosting_config:
            raise ValueError(
                f"Model {model_id!r} has provider {provider!r} with no hosting class in the "
                f"provider-hosting config (known providers: {sorted(hosting_config)}). "
                "Add it to config/analysis/model_ranking/provider_hosting.json."
            )
        result[model_id] = hosting_config[provider]

    return result

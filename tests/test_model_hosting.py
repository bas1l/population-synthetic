"""Tests for the model-ranking hosting classifier.

Pins the config-sourced provider -> ``local``/``hosted`` grouping
(``load_hosting_config``) and the per-model classification
(``classify_hosting``), including the fail-fast behaviour on a missing config
file, a malformed config, and an unknown provider.
"""

from __future__ import annotations

import json

import pytest

from population_synthetic.analysis.model_ranking.hosting import (
    classify_hosting,
    load_hosting_config,
)

_HOSTING = {
    "ollama": "local",
    "claude": "hosted",
    "gemini": "hosted",
    "openrouter": "hosted",
    "openai_compat": "hosted",
}


def _model(model_id: str, provider: str) -> dict:
    return {"id": model_id, "model_config": {"provider": provider, "model": "x"}}


def test_classify_hosting_maps_providers():
    models = [
        _model("local_llama", "ollama"),
        _model("claude_sonnet", "claude"),
        _model("gemini_flash", "gemini"),
        _model("or_model", "openrouter"),
    ]
    assert classify_hosting(models, _HOSTING) == {
        "local_llama": "local",
        "claude_sonnet": "hosted",
        "gemini_flash": "hosted",
        "or_model": "hosted",
    }


def test_classify_hosting_unknown_provider_raises():
    with pytest.raises(ValueError, match="mystery"):
        classify_hosting([_model("weird", "mystery")], _HOSTING)


def test_classify_hosting_missing_provider_key_raises():
    with pytest.raises(KeyError, match="model_config.provider"):
        classify_hosting([{"id": "no_cfg"}], _HOSTING)


def test_load_hosting_config_roundtrip(tmp_path):
    path = tmp_path / "provider_hosting.json"
    path.write_text(
        json.dumps({"description": "x", "providers": _HOSTING}), encoding="utf-8"
    )
    assert load_hosting_config(path) == _HOSTING


def test_load_hosting_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_hosting_config(tmp_path / "does_not_exist.json")


def test_load_hosting_config_missing_providers_block_raises(tmp_path):
    path = tmp_path / "provider_hosting.json"
    path.write_text(json.dumps({"description": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="providers"):
        load_hosting_config(path)


def test_load_hosting_config_invalid_class_raises(tmp_path):
    path = tmp_path / "provider_hosting.json"
    path.write_text(
        json.dumps({"providers": {"claude": "cloud"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid class"):
        load_hosting_config(path)


def test_repo_provider_hosting_config_covers_valid_providers():
    """The shipped config must classify every VALID_PROVIDERS entry."""
    from population_synthetic._paths import PROJECT_ROOT
    from population_synthetic.generators.synthetic.manifest_loader import VALID_PROVIDERS

    config = load_hosting_config(
        PROJECT_ROOT / "config" / "analysis" / "model_ranking" / "provider_hosting.json"
    )
    assert set(config) == VALID_PROVIDERS
    assert config["ollama"] == "local"
    assert all(config[p] == "hosted" for p in VALID_PROVIDERS - {"ollama"})

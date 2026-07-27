"""Unit tests for ``OllamaClient``'s endpoint contract.

The client is configuration-free: it speaks HTTP to exactly the endpoint it is
handed. ``base_url`` is a required keyword argument, and the two former lower
tiers of the old precedence chain (explicit arg -> ``OLLAMA_BASE_URL`` env ->
hardcoded ``_DEFAULT_BASE_URL``) are gone. These tests pin that removal: both
would let the client choose a machine on its own, which sends a whole sweep to
the wrong GPU while every output looks perfectly normal.

No test here touches the network. Construction failures are asserted *before*
``_validate_server`` can run, and the unreachable-host case injects a
``requests`` transport error through a monkeypatched session.
"""

from __future__ import annotations

import ast

import pytest
import requests

from population_synthetic.clients.ollama_client import OllamaClient


def test_missing_base_url_raises_type_error() -> None:
    """``base_url`` is keyword-only and required -- omitting it is a TypeError.

    Enforced by the signature rather than by a runtime check, so the failure is
    visible to type checkers and cannot be reached at run time with a default.
    """
    with pytest.raises(TypeError, match="base_url"):
        OllamaClient(model_name="x")  # type: ignore[call-arg]


def test_env_var_does_not_supply_a_base_url(monkeypatch) -> None:
    """``OLLAMA_BASE_URL`` in the environment is not read: construction still fails.

    The env read was removed with the hardcoded default. A stage must not reach
    back out to the environment for its target machine.
    """
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.0.19:11434")
    with pytest.raises(TypeError, match="base_url"):
        OllamaClient(model_name="x")  # type: ignore[call-arg]


def test_no_hardcoded_endpoint_or_environment_read_survives() -> None:
    """Neither lower tier of the old precedence chain is left in the module.

    Asserted structurally rather than behaviourally because both were *silent*
    fallbacks: a behavioural test can only observe the tier that happens to win.
    """
    import population_synthetic.clients.ollama_client as module

    assert not hasattr(module, "_DEFAULT_BASE_URL")

    source = module.__file__
    assert source is not None
    with open(source, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    # Walk the AST rather than the raw text: the docstring documents the removal
    # by name, so a substring scan would match its own explanation.
    imported: set[str] = set()
    string_constants: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_constants.append(node.value)

    # No route to the environment at all (``os`` is the only one available here).
    assert "os" not in imported

    # No endpoint literal anywhere, including inside the docstrings.
    assert not [s for s in string_constants if "192.168.0.19" in s]


@pytest.mark.parametrize("value", [None, ""], ids=["none", "empty"])
def test_explicitly_empty_base_url_raises_value_error(value) -> None:
    """An explicitly blank endpoint raises before any request is attempted."""
    with pytest.raises(ValueError, match="requires an explicit base_url"):
        OllamaClient(model_name="x", base_url=value)


def test_unreachable_host_raises_connection_error_naming_the_endpoint(monkeypatch) -> None:
    """Startup validation names the exact probed endpoint, not just the base URL.

    With the host selectable per run, "which machine did this run talk to" must be
    answerable from the failure message alone.
    """
    def _refuse(self, url, **kwargs):  # noqa: ANN001, ARG001
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(requests.Session, "get", _refuse)

    with pytest.raises(ConnectionError) as excinfo:
        OllamaClient(model_name="x", base_url="http://unreachable.invalid:11434")

    assert "http://unreachable.invalid:11434/api/tags" in str(excinfo.value)

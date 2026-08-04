"""First coverage for ``BaseIdentityGenerator`` and ``FactoryIdentityGenerator``.

The ABC carries the state every generator shares -- the injected client, the
interaction collector, the persona writer and the two retry/decoding flags -- and
the factory is the single place a mode string becomes a concrete strategy. Both
were previously untested, which is how the writer slot could have been added to a
class with no guard that its defaults stay inert.
"""

from __future__ import annotations

from typing import Any

import pytest

from population_synthetic.generators.synthetic.base_identity_generator import BaseIdentityGenerator
from population_synthetic.generators.synthetic.factory_identity_generator import FactoryIdentityGenerator
from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
)


class _StubGenerator(BaseIdentityGenerator):
    """Minimal concrete subclass: the ABC's contract is two methods, nothing more."""

    def generate_identity(self, landscape_file: str) -> tuple[dict[str, Any], dict[str, str]]:
        return {}, {}

    def load_identity(self, filepath: str) -> tuple[dict[str, Any], dict[str, str]]:
        return {}, {}


def test_base_generator_defaults_are_inert():
    client = object()
    gen = _StubGenerator(client)
    assert gen.client is client
    # Every optional collaborator defaults to "absent", so a generator constructed
    # without wiring persists nothing and changes no behaviour.
    assert gen.interaction_collector is None
    assert gen.writer is None
    assert gen.retry_until_success is False
    assert gen.use_structured_output is False


def test_base_generator_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseIdentityGenerator(object())  # type: ignore[abstract]


def test_factory_returns_the_configurable_strategy():
    client = object()
    gen = FactoryIdentityGenerator.create_generator("configurable", client)
    assert isinstance(gen, IdentityGeneratorConfigurable)
    assert gen.client is client
    assert gen.writer is None


@pytest.mark.parametrize("mode", ["CONFIGURABLE", "  Configurable  "])
def test_factory_normalizes_the_mode_string(mode):
    assert isinstance(
        FactoryIdentityGenerator.create_generator(mode, object()), IdentityGeneratorConfigurable
    )


def test_factory_rejects_an_unknown_mode():
    with pytest.raises(ValueError, match="Unknown identity generator mode"):
        FactoryIdentityGenerator.create_generator("sequential", object())


def test_configurable_generator_starts_its_correlation_counter_at_zero():
    gen = IdentityGeneratorConfigurable(object())
    assert gen.persona_id is None
    assert gen._call_index == 0

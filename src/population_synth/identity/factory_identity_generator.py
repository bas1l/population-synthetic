"""Factory for selecting an identity generation strategy at runtime.

Defines ``FactoryIdentityGenerator``, which maps a mode string to a
concrete ``BaseIdentityGenerator`` subclass via a central registry:
``configurable`` -> ``IdentityGeneratorConfigurable``.
``create_generator`` instantiates the chosen strategy with an injected
``LLMClient``.
"""

from __future__ import annotations

from population_synth.clients.llm_protocol import LLMClient

from .base_identity_generator import BaseIdentityGenerator
from .identity_generator_configurable import IdentityGeneratorConfigurable


class FactoryIdentityGenerator:
    """
    Factory for instantiating concrete BaseIdentityGenerator implementations.
    The only registered strategy is ``configurable``, which drives generation
    via a simulation config JSON file and a strategy YAML.
    """

    # Central registry mapping identifiers to concrete class types.
    _STRATEGY_MAP: dict[str, type[BaseIdentityGenerator]] = {
        "configurable": IdentityGeneratorConfigurable,
    }

    @staticmethod
    def create_generator(mode: str, client: LLMClient) -> BaseIdentityGenerator:
        """
        Instantiates the appropriate identity generator class based on the provided mode string.

        Args:
            mode (str): The strategy identifier. Currently only ``'configurable'`` is supported.
            client (LLMClient): The API client dependency required by the generator constructors.

        Returns:
            BaseIdentityGenerator: An initialized instance of the requested strategy.

        Raises:
            ValueError: If the provided mode string matches no registered strategy.
        """
        # 1. Normalize the input string to ensure case-insensitivity
        normalized_mode = mode.lower().strip()

        # 2. Retrieve the concrete class type from the registry
        generator_class = FactoryIdentityGenerator._STRATEGY_MAP.get(normalized_mode)

        # 3. Validate existence
        if not generator_class:
            valid_options = list(FactoryIdentityGenerator._STRATEGY_MAP.keys())
            raise ValueError(
                f"Architecture Error: Unknown identity generator mode '{mode}'. "
                f"Available strategies: {valid_options}"
            )

        # 4. Instantiate and return the class with Dependency Injection
        return generator_class(client)

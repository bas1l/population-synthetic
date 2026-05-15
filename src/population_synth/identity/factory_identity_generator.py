from typing import Dict, Type

from population_synth.clients.gemini_client import GeminiClient

from .base_identity_generator import BaseIdentityGenerator
from .identity_generator_batch import NarrativeGeneratorBatch
from .identity_generator_configurable import IdentityGeneratorConfigurable
from .identity_generator_sequential import IdentityGeneratorSequential


class FactoryIdentityGenerator:
    """
    Factory architecture for instantiating concrete BaseIdentityGenerator implementations.
    Centralizes the logic for selecting between sequential (hierarchical) and batch (narrative)
    identity generation strategies.
    """

    # Central registry mapping identifiers to concrete class types.
    # Note: 'batch' maps to NarrativeGeneratorBatch as defined in identity_generator_batch.py
    _STRATEGY_MAP: Dict[str, Type[BaseIdentityGenerator]] = {
        "sequential": IdentityGeneratorSequential,
        "batch": NarrativeGeneratorBatch,
        "configurable": IdentityGeneratorConfigurable
    }

    @staticmethod
    def create_generator(mode: str, client: GeminiClient) -> BaseIdentityGenerator:
        """
        Instantiates the appropriate identity generator class based on the provided mode string.

        Args:
            mode (str): The strategy identifier (e.g., 'sequential', 'batch').
            client (GeminiClient): The API client dependency required by the generator constructors.

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

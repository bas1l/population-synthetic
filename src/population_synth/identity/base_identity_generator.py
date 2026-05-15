import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from population_synth.clients.gemini_client import GeminiClient


class BaseIdentityGenerator(ABC):
    """
    Abstract Base Class defining the contract for Identity Generators.
    Centralizes shared state (GeminiClient) and defines the contract for generation strategies.
    """

    def __init__(self, client: GeminiClient):
        """
        Initialize with a shared GeminiClient to enforce Dependency Injection.

        Args:
            client (GeminiClient): An initialized client for API calls.
        """
        self.client = client
        logging.info(f"{self.__class__.__name__} initialized.")

    @abstractmethod
    def generate_identity(self, landscape_file: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Generates a new identity based on a landscape schema.

        Args:
            landscape_file (str): Path to the JSON schema defining the identity landscape.

        Returns:
            Tuple[Dict[str, Any], Dict[str, str]]:
                1. The raw dictionary of the generated identity.
                2. A dictionary mapping level IDs to their formatted string representations.
        """
        pass

    @abstractmethod
    def load_identity(self, filepath: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Loads an existing identity from persistence.

        Args:
            filepath (str): Path to the saved identity JSON file.

        Returns:
            Tuple[Dict[str, Any], Dict[str, str]]:
                1. The loaded identity data.
                2. A dictionary mapping level IDs to their formatted string representations.
        """
        pass

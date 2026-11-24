"""Abstract base class for identity generation strategies.

Defines ``BaseIdentityGenerator``, the ABC that fixes the contract for
all identity generators. It centralizes shared state -- the injected
``LLMClient``, ``LLMInteractionCollector`` and ``PersonaWriter`` -- and
declares the ``generate_identity`` and ``load_identity`` abstract methods
that each concrete strategy must implement.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from population_synthetic.clients.llm_protocol import LLMClient

from .llm_interaction_log import LLMInteractionCollector
from .persona_writer import PersonaWriter


class BaseIdentityGenerator(ABC):
    """
    Abstract Base Class defining the contract for Identity Generators.
    Centralizes shared state (LLMClient) and defines the contract for generation strategies.
    """

    def __init__(self, client: LLMClient):
        """
        Initialize with a shared LLMClient to enforce Dependency Injection.

        Args:
            client (LLMClient): An initialized client for API calls.
        """
        self.client = client
        self.interaction_collector: LLMInteractionCollector | None = None
        # Injected by the orchestration layer when this generator's output is
        # durable. ``None`` means "generate in memory, persist nothing" -- the
        # generator never chooses a path or a filename of its own.
        self.writer: PersonaWriter | None = None
        self.retry_until_success: bool = False
        self.use_structured_output: bool = False
        logging.info(f"{self.__class__.__name__} initialized.")

    @abstractmethod
    def generate_identity(self, landscape_file: str) -> tuple[dict[str, Any], dict[str, str]]:
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
    def load_identity(self, filepath: str) -> tuple[dict[str, Any], dict[str, str]]:
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

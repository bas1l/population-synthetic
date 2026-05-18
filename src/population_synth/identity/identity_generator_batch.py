import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

from population_synth.clients.llm_protocol import LLMClient

from .base_identity_generator import BaseIdentityGenerator


class NarrativeGeneratorBatch(BaseIdentityGenerator):
    """
    Implements a flat, narrative-based identity generation strategy.
    Adapts the legacy prompt-based generation to the BaseIdentityGenerator contract.

    Attributes:
        client (LLMClient): Injected client for API interaction.
        last_identity (Optional[Dict[str, Any]]): Cache of the last generated identity.
    """

    def __init__(self, client: LLMClient):
        """
        Initialize the generator.

        Args:
            client (LLMClient): An initialized client for API calls.
        """
        super().__init__(client)
        self.last_identity: Optional[Dict[str, Any]] = None

    def _load_prompt_content(self, filepath: str) -> str:
        """Internal helper to read the prompt file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Prompt file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            raise ValueError(f"Prompt file is empty: {filepath}")
        return content

    def generate_identity(self, landscape_file: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Generates a monolithic identity narrative based on a text prompt file.

        Args:
            landscape_file (str): Path to the text file containing the prompt.

        Returns:
            Tuple[Dict[str, Any], Dict[str, str]]:
                1. Dictionary containing the raw narrative under key 'narrative'.
                2. Dictionary containing the formatted string (identical to raw in this case).
        """
        prompt_text = self._load_prompt_content(landscape_file)

        try:
            logging.info(f"Generating flat narrative from {landscape_file}...")
            # Utilizing the injected client instead of internal model instance
            response_text = self.client.generate_content(prompt_text)

            # Encapsulate string response to satisfy Dict return contract
            identity_data = {"narrative": response_text}
            formatted_data = {"narrative": response_text} # No specific formatting needed for raw text

            self.last_identity = identity_data
            logging.info("Narrative generation successful.")

            return identity_data, formatted_data

        except Exception as e:
            logging.error(f"Error during narrative generation: {e}")
            raise

    def load_identity(self, filepath: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Loads a previously generated narrative identity from a JSON file.

        Args:
            filepath (str): Path to the saved identity JSON file.

        Returns:
            Tuple[Dict[str, Any], Dict[str, str]]: The loaded identity data and formatted view.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Identity file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                self.last_identity = data

                # For flat narratives, the formatted view is likely just the text content
                formatted = {k: str(v) for k, v in data.items()}

                logging.info(f"Identity successfully loaded from {filepath}")
                return data, formatted
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in identity file: {e}")

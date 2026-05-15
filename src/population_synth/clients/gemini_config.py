import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml  # Requires: pip install PyYAML


class GeminiApiConfig:
    """
    Handles the loading and parsing of the Gemini configuration.
    Supports loading from a legacy YAML file or directly from a provided dictionary.
    """

    DEFAULT_MODEL_FALLBACK = 'gemini-2.5-flash'

    def __init__(self, source: Union[Path, str, Dict[str, Any]]):
        """
        Initialize the config loader.

        Args:
            source: Either a Path/str pointing to a YAML file, or a Dictionary containing config data.
        """
        self.logger = logging.getLogger(__name__)
        self._config_data: Dict[str, Any] = {}

        if isinstance(source, dict):
            self._config_data = source
        elif isinstance(source, (str, Path)):
            self.config_path = Path(source)
            self._config_data = self._load_from_file()
        else:
            self.logger.error(f"Invalid config source type: {type(source)}. Expected dict or path.")

        self._validate_mandatory_fields()

    def _load_from_file(self) -> Dict[str, Any]:
        """
        Loads the raw YAML data, returning an empty dict if missing or corrupt.
        """
        if not self.config_path.exists():
            self.logger.warning(f"Config file not found at {self.config_path}. Using internal defaults.")
            return {}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                # safe_load avoids arbitrary code execution vulnerabilities present in full load
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            self.logger.error(f"Failed to parse YAML {self.config_path}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error loading config: {e}")
            return {}

    def _validate_mandatory_fields(self) -> None:
        """
        Validates that mandatory fields are present in the loaded configuration.
        """
        if self._config_data and 'model_name' not in self._config_data:
            self.logger.warning("Key 'model_name' missing in configuration. Reverting to internal fallback.")

    @property
    def model_name(self) -> str:
        """
        Returns the configured model name.
        """
        return self._config_data.get('model_name', self.DEFAULT_MODEL_FALLBACK)

    @property
    def generation_config(self) -> Dict[str, Any]:
        """
        Returns the generation configuration dictionary.
        Attributes set to 'null' (None in Python) in the YAML are filtered out
        to allow API defaults to take over.
        """
        raw_config = self._config_data.get('generation_config', {})

        if not isinstance(raw_config, dict):
            # If the key is missing or not a dict, return empty to use defaults
            return {}

        # Filter out keys where value is None (null in YAML)
        return {k: v for k, v in raw_config.items() if v is not None}

    @property
    def safety_settings(self) -> Optional[Dict[str, Any]]:
        """Returns safety settings if defined."""
        return self._config_data.get('safety_settings')

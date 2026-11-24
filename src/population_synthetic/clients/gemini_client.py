"""GeminiClient — Google Gemini API wrapper with metadata tracking.

Defines ``GeminiClient``, a stateful wrapper around the google-genai SDK
that generates text completions, maintains persistent generation config,
and records per-call provenance metadata for the sidecar pattern.
"""
from __future__ import annotations

import copy
import logging
import os
import time
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types

from population_synthetic.clients.call_context import format_corr_token


class GeminiClient:
    """
    A unified, stateful interface for interacting with the Google Gemini API.

    This class manages a persistent configuration state for content generation,
    allowing for consistent parameter usage across calls and dynamic runtime updates.
    It now tracks the history of executions to allow for full provenance of multi-step generations.
    """

    def __init__(self, model_name: str = 'gemini-2.5-flash', default_config: dict[str, Any] | None = None):
        """
        Initialize the Gemini Gateway with a specific model and initial configuration.

        Args:
            model_name (str): The default Target Gemini model. Defaults to 'gemini-2.0-flash'.
            default_config (Optional[Dict[str, Any]]): Initial configuration parameters
                                                       (e.g., temperature, top_p).

        Raises:
            ValueError: If the GEMINI_API_KEY environment variable is not set.
            RuntimeError: If the genai.Client fails to initialize.
        """
        self.default_model_name = model_name

        # Enforce Environment Variable existence
        if not os.getenv("GEMINI_API_KEY"):
            logging.error("GEMINI_API_KEY environment variable missing.")
            raise ValueError("GEMINI_API_KEY not found. Set it in environment variables.")

        try:
            self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)

            # Initialize persistent configuration state
            self._config_state: dict[str, Any] = default_config if default_config else {}

            # Metadata tracking for the sidecar pattern
            self._last_execution_metadata: dict[str, Any] | None = None
            self._execution_history: list[dict[str, Any]] = []

            self.logger.info(
                "GeminiClient initialized. Model: %s. Config: %s",
                self.default_model_name,
                self._config_state,
            )

        except Exception as e:
            logging.error(f"Failed to configure Gemini API client: {e}")
            raise RuntimeError(f"Gemini Client Initialization Failed: {e}") from e

    def get_available_models(self) -> list[str]:
        """
        Retrieves a list of available Gemini model names that support content generation.

        Returns:
            List[str]: A list of model identifiers (e.g., 'gemini-2.0-flash').
        """
        try:
            # The SDK v2 models.list() returns an iterator of Model objects.
            # We iterate and filter for models likely to support text generation.
            model_names = []
            for m in self.client.models.list():
                if 'gemini' in m.name.lower() and 'embed' not in m.name.lower():
                    model_names.append(m.name)

            # Sort for UI consistency
            return sorted(model_names)
        except Exception as e:
            self.logger.error(f"Error listing models: {e}")
            return [self.default_model_name]

    def update_config(self, **kwargs: Any) -> None:
        """
        Persistently update the stored generation configuration.
        """
        self.logger.info(f"Updating persistent config with: {kwargs}")
        self._config_state.update(kwargs)

    def update_default_model(self, new_model_name: str) -> None:
        """
        Runtime update of the default model configuration.
        """
        self.logger.info(f"Updating default model from {self.default_model_name} to {new_model_name}")
        self.default_model_name = new_model_name

    def get_current_configuration(self) -> dict[str, Any]:
        """
        Retrieve the full current state of the client configuration.
        """
        state = {
            "model": self.default_model_name,
            "generation_config": copy.deepcopy(self._config_state)
        }
        return state

    @property
    def last_metadata(self) -> dict[str, Any]:
        """
        Returns the metadata (model, config, timestamp) used for the most recent API call.
        """
        return self._last_execution_metadata or {}

    @property
    def history(self) -> list[dict[str, Any]]:
        """
        Returns the list of metadata for all API calls since the last clear.
        Useful for saving complete audit trails of multi-step generations.
        """
        return self._execution_history

    def clear_history(self) -> None:
        """
        Clears the execution history. Call this before starting a new logical unit of work.
        """
        self._execution_history = []
        self._last_execution_metadata = None

    def generate_content(
        self,
        prompt: str,
        *,
        model: str | None = None,
        **kwargs: Any
    ) -> str:
        """
        Generate content using the stored configuration, optionally overridden by kwargs.

        Args:
            prompt (str): The input text to generate content from.
            model (Optional[str]): A specific model to use for this call.
                                   If None, uses the instance's default model.
            **kwargs: Temporary configuration overrides for this specific call
                      (e.g., system_instruction, temperature).

        Returns:
            str: The text content of the generated response.

        Raises:
            RuntimeError: If the API call fails.
        """
        # Determine effective model
        target_model = model if model else self.default_model_name

        # Merge persistent state with temporary overrides
        effective_config_params = self._config_state.copy()
        effective_config_params.update(kwargs)

        # Capture Metadata for Provenance/Sidecar files
        metadata: dict[str, Any] = {
            "provider": "gemini",
            "model": target_model,
            "model_name": target_model,
            "generation_config": effective_config_params,
            "timestamp": datetime.now().isoformat(),
            "request_sent_at": None,
            "response_received_at": None,
            "elapsed_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "status": None,
            "error_category": None,
            "error": None,
        }

        # Update state and history
        self._last_execution_metadata = metadata
        self._execution_history.append(metadata)

        self.logger.debug(f"Sending request to model: {target_model} with config: {effective_config_params}")

        def _fail(category: str, message: str) -> None:
            metadata["status"] = "error"
            metadata["error_category"] = category
            metadata["error"] = message

        try:
            # Create the Configuration Object
            generation_config = (
                types.GenerateContentConfig(**effective_config_params) if effective_config_params else None
            )

            metadata["request_sent_at"] = datetime.now().isoformat()
            t0 = time.perf_counter()

            # Call the API
            response = self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=generation_config
            )

            elapsed_ms = (time.perf_counter() - t0) * 1000
            metadata["response_received_at"] = datetime.now().isoformat()
            metadata["elapsed_ms"] = elapsed_ms

            text = getattr(response, 'text', None)
            if not isinstance(text, str) or not text.strip():
                # response.text is None when the completion is safety-blocked or
                # empty. Fail loudly rather than returning a repr of the SDK
                # object, which would surface downstream as a bogus JSON parse
                # error far from the real cause.
                _fail(
                    "model_limitation",
                    f"Gemini returned no usable text for model {target_model} "
                    f"(safety-blocked or empty response): {response!r}",
                )
                raise RuntimeError(
                    f"Gemini returned no usable text for model {target_model} "
                    f"(safety-blocked or empty response): {response!r}"
                )

            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = getattr(usage, "prompt_token_count", None) if usage is not None else None
            completion_tokens = getattr(usage, "candidates_token_count", None) if usage is not None else None
            total_tokens = getattr(usage, "total_token_count", None) if usage is not None else None
            if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                total_tokens = prompt_tokens + completion_tokens

            metadata["prompt_tokens"] = prompt_tokens
            metadata["completion_tokens"] = completion_tokens
            metadata["total_tokens"] = total_tokens
            metadata["status"] = "ok"
            metadata["error_category"] = None
            metadata["error"] = None

            self.logger.info(
                "gemini call: model=%s elapsed_ms=%.0f prompt_tokens=%s completion_tokens=%s%s",
                target_model, elapsed_ms, prompt_tokens, completion_tokens, format_corr_token(),
            )
            return text

        except RuntimeError:
            raise

        except Exception as e:
            exc_name = type(e).__name__.lower()
            exc_msg = str(e).lower()
            if any(kw in exc_name or kw in exc_msg for kw in ("connection", "network", "dns", "resolve")):
                category = "network"
            elif any(kw in exc_name or kw in exc_msg for kw in ("deadline", "timeout", "timed out")):
                category = "timeout"
            else:
                category = "unknown"
            _fail(category, str(e))
            self.logger.error(f"Generation failed for model {target_model}: {e}")
            raise RuntimeError(f"Gemini Generation Error: {e}") from e

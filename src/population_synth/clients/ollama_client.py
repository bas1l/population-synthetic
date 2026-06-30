"""OllamaClient — HTTP client for a self-hosted Ollama server.

Defines ``OllamaClient``, which targets the native POST /api/chat endpoint
of an Ollama REST server, satisfies the shared LLMClient protocol, and adds
startup validation, retry with backoff, and per-call provenance metadata.
"""
from __future__ import annotations

import copy
import logging
import os
import random
import time
from datetime import datetime
from typing import Any

import requests

from population_synth.clients.call_context import format_corr_token
from population_synth.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking

_DEFAULT_BASE_URL = "http://192.168.0.19:11434"


class OllamaClient:
    """
    HTTP client for the Ollama REST API satisfying the LLMClient Protocol.

    Targets the native POST /api/chat endpoint on a self-hosted Ollama server.
    Each generate_content() call is stateless from the server's perspective
    (no multi-turn conversation state is maintained across calls).
    """

    def __init__(
        self,
        model_name: str = "llama3.1",
        base_url: str | None = None,
        default_config: dict[str, Any] | None = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        timeout: int | None = None,
    ):
        self.default_model_name = model_name
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or _DEFAULT_BASE_URL
        ).rstrip("/")
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        self._config_state: dict[str, Any] = default_config if default_config else {}
        self._last_execution_metadata: dict[str, Any] | None = None
        self._execution_history: list[dict[str, Any]] = []

        self._session = requests.Session()

        self._validate_server()

        self.logger.info(
            "OllamaClient initialized. Model: %s. Base URL: %s. Config: %s",
            self.default_model_name,
            self.base_url,
            self._config_state,
        )

    def _validate_server(self) -> None:
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=10)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Ollama server unreachable at {self.base_url}. "
                f"Ensure the server is running and the URL is correct. Original error: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ConnectionError(
                f"Ollama server timed out at {self.base_url} during startup validation. "
                f"Original error: {e}"
            ) from e
        except requests.exceptions.HTTPError as e:
            raise ConnectionError(
                f"Ollama server at {self.base_url} returned HTTP {e.response.status_code} "
                f"during startup validation. Original error: {e}"
            ) from e

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def update_config(self, **kwargs: Any) -> None:
        self.logger.info("Updating persistent config with: %s", kwargs)
        self._config_state.update(kwargs)

    def update_default_model(self, new_model_name: str) -> None:
        self.logger.info(
            "Updating default model from %s to %s",
            self.default_model_name,
            new_model_name,
        )
        self.default_model_name = new_model_name

    def get_current_configuration(self) -> dict[str, Any]:
        return {
            "model": self.default_model_name,
            "base_url": self.base_url,
            "generation_config": copy.deepcopy(self._config_state),
        }

    @property
    def last_metadata(self) -> dict[str, Any]:
        return self._last_execution_metadata or {}

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._execution_history

    def clear_history(self) -> None:
        self._execution_history = []
        self._last_execution_metadata = None

    # ------------------------------------------------------------------
    # model_name alias (script compatibility)
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self.default_model_name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._session.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # generate_content
    # ------------------------------------------------------------------

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        effective_config = self._config_state.copy()
        effective_config.update(kwargs)

        target_model = effective_config.pop("model", self.default_model_name)
        system_instruction = effective_config.pop("system_instruction", None)
        response_schema = effective_config.pop("response_schema", None)

        options: dict[str, Any] = {}
        for src_key, ollama_key in (
            ("temperature", "temperature"),
            ("top_p", "top_p"),
            ("top_k", "top_k"),
            ("max_output_tokens", "num_predict"),
        ):
            if src_key in effective_config:
                options[ollama_key] = effective_config.pop(src_key)

        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "format": response_schema if response_schema is not None else "json",
        }
        if options:
            payload["options"] = options

        metadata: dict[str, Any] = {
            "provider": "ollama",
            "model": target_model,
            "base_url": self.base_url,
            "timestamp": datetime.now().isoformat(),
            "options": options,
        }
        self._last_execution_metadata = metadata
        self._execution_history.append(metadata)

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                t0 = time.perf_counter()
                resp = self._session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self._timeout,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

                if resp.status_code == 404:
                    body = _safe_json(resp)
                    err_msg = body.get("error", "") if isinstance(body, dict) else str(body)
                    if "model" in err_msg.lower() or "not found" in err_msg.lower():
                        raise RuntimeError(
                            f"Model '{target_model}' not found on Ollama server at {self.base_url}. "
                            f"Run 'ollama pull {target_model}' on the server."
                        )
                    raise RuntimeError(
                        f"Ollama returned 404: {err_msg}"
                    )

                if 400 <= resp.status_code < 500:
                    body = _safe_json(resp)
                    raise RuntimeError(
                        f"Ollama returned client error HTTP {resp.status_code}: {body}"
                    )

                resp.raise_for_status()

                data = resp.json()
                content = data["message"]["content"]
                if not isinstance(content, str):
                    raise RuntimeError(
                        f"Unexpected content type from Ollama: {type(content)!r}"
                    )

                prompt_tokens = data.get("prompt_eval_count")
                completion_tokens = data.get("eval_count")
                metadata["prompt_tokens"] = prompt_tokens
                metadata["completion_tokens"] = completion_tokens
                metadata["elapsed_ms"] = elapsed_ms

                self.logger.info(
                    "ollama call: model=%s base_url=%s elapsed_ms=%.0f "
                    "prompt_tokens=%s completion_tokens=%s%s",
                    target_model,
                    self.base_url,
                    elapsed_ms,
                    prompt_tokens,
                    completion_tokens,
                    format_corr_token(),
                )
                return content.strip()

            except RuntimeError:
                raise

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
            except requests.exceptions.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise RuntimeError(
                        f"Ollama returned client error HTTP {e.response.status_code}: {e}"
                    ) from e
                last_error = e

            if attempt < self._max_retries - 1:
                delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                delay *= random.uniform(0.75, 1.25)
                self.logger.warning(
                    "generate_content attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt + 1,
                    self._max_retries,
                    last_error,
                    delay,
                )
                time.sleep(delay)

        self.logger.error(
            "generate_content failed after %d attempts: %s", self._max_retries, last_error
        )
        raise RuntimeError(
            f"Ollama generation failed after {self._max_retries} attempts: {last_error}"
        )


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text

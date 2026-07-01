"""OpenAICompatClient — client for any OpenAI-compatible provider.

Defines ``OpenAICompatClient``, which calls /v1/chat/completions via the
OpenAI SDK for providers such as Mistral, OVHcloud, and Regolo.ai. Satisfies
the shared LLMClient protocol with strict JSON-schema support, retry with
backoff, and per-call provenance metadata.
"""
from __future__ import annotations

import copy
import logging
import os
import random
import time
from datetime import datetime
from typing import Any

import openai

from population_synthetic.clients.call_context import format_corr_token
from population_synthetic.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking

_FATAL_STATUS_CODES = {400, 401, 403, 404, 422}


class OpenAICompatClient:
    """
    OpenAI-SDK client for any OpenAI-compatible provider satisfying the LLMClient Protocol.

    Targets /v1/chat/completions. Works with Mistral, OVHcloud AI Endpoints, Regolo.ai,
    and any other provider exposing the OpenAI chat completions API shape.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key_env_var: str = "OPENAI_API_KEY",
        default_config: dict[str, Any] | None = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        timeout: int = 120,
    ):
        api_key = os.environ.get(api_key_env_var)
        if not api_key:
            raise ValueError(f"Environment variable {api_key_env_var!r} is not set")

        self.default_model_name = model_name
        self.base_url = base_url.rstrip("/")
        self._api_key_env_var = api_key_env_var
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

        self._client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,  # we handle retries ourselves
        )

        self.logger.info(
            "OpenAICompatClient initialized. Model: %s. Base URL: %s. Config: %s",
            self.default_model_name,
            self.base_url,
            self._config_state,
        )

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
            "api_key_env_var": self._api_key_env_var,
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
    # generate_content
    # ------------------------------------------------------------------

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        effective_config = self._config_state.copy()
        effective_config.update(kwargs)

        target_model = effective_config.pop("model", self.default_model_name)
        system_instruction = effective_config.pop("system_instruction", None)
        response_schema = effective_config.pop("response_schema", None)

        api_params: dict[str, Any] = {}
        for src_key, api_key in (
            ("temperature", "temperature"),
            ("top_p", "top_p"),
            ("max_output_tokens", "max_tokens"),
        ):
            if src_key in effective_config:
                api_params[api_key] = effective_config.pop(src_key)
            if api_key in effective_config:
                api_params[api_key] = effective_config.pop(api_key)

        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response_format_strict: dict[str, Any] | None = None
        if response_schema is not None:
            response_format_strict = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": response_schema, "strict": True},
            }

        metadata: dict[str, Any] = {
            "provider": "openai_compat",
            "model": target_model,
            "base_url": self.base_url,
            "timestamp": datetime.now().isoformat(),
            "api_params": api_params,
        }
        self._last_execution_metadata = metadata
        self._execution_history.append(metadata)

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response_format = response_format_strict

                t0 = time.perf_counter()
                try:
                    completion = self._client.chat.completions.create(
                        model=target_model,
                        messages=messages,  # type: ignore[arg-type]
                        **({"response_format": response_format} if response_format is not None else {}),
                        **api_params,
                    )
                except openai.BadRequestError as exc:
                    if response_format_strict is not None:
                        # Provider rejected the strict JSON schema; fall back to plain json_object mode.
                        self.logger.warning(
                            "Provider rejected response_format json_schema (%s) — retrying with json_object",
                            exc,
                        )
                        completion = self._client.chat.completions.create(
                            model=target_model,
                            messages=messages,  # type: ignore[arg-type]
                            response_format={"type": "json_object"},
                            **api_params,
                        )
                    else:
                        raise RuntimeError(
                            f"Provider returned 400 Bad Request: {exc}"
                        ) from exc

                elapsed_ms = (time.perf_counter() - t0) * 1000

                content = completion.choices[0].message.content
                if not isinstance(content, str):
                    raise RuntimeError(
                        f"Unexpected content type from provider: {type(content)!r}"
                    )

                usage = completion.usage
                prompt_tokens = usage.prompt_tokens if usage else None
                completion_tokens = usage.completion_tokens if usage else None
                metadata["prompt_tokens"] = prompt_tokens
                metadata["completion_tokens"] = completion_tokens
                metadata["elapsed_ms"] = elapsed_ms

                self.logger.info(
                    "openai_compat call: model=%s base_url=%s elapsed_ms=%.0f "
                    "prompt_tokens=%s completion_tokens=%s%s",
                    target_model,
                    self.base_url,
                    elapsed_ms,
                    prompt_tokens,
                    completion_tokens,
                    format_corr_token(),
                )
                return content.strip()

            except (
                openai.AuthenticationError,
                openai.PermissionDeniedError,
                openai.NotFoundError,
            ) as e:
                raise RuntimeError(
                    f"Fatal provider error (no retry): {type(e).__name__}: {e}"
                ) from e

            except RuntimeError:
                raise

            except (
                openai.RateLimitError,
                openai.APIConnectionError,
                openai.APITimeoutError,
                openai.InternalServerError,
            ) as e:
                last_error = e

            except openai.APIStatusError as e:
                # Catch-all for any remaining 4xx that aren't handled above.
                if e.status_code is not None and 400 <= e.status_code < 500:
                    raise RuntimeError(
                        f"Fatal provider error HTTP {e.status_code} (no retry): {e}"
                    ) from e
                last_error = e

            if attempt < self._max_retries - 1:
                delay = min(self._base_delay * (2**attempt), self._max_delay)
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
            f"OpenAI-compat generation failed after {self._max_retries} attempts: {last_error}"
        )

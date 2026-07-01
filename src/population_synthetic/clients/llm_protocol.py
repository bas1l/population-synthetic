"""LLMClient — structural protocol shared by all LLM client wrappers.

Defines the ``LLMClient`` runtime-checkable Protocol that GeminiClient,
ClaudeCodeClient, OllamaClient, and OpenAICompatClient satisfy, covering
content generation, config updates, and execution-history accessors.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Structural contract shared by GeminiClient and ClaudeCodeClient."""

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        ...

    def update_config(self, **kwargs: Any) -> None:
        ...

    def update_default_model(self, new_model_name: str) -> None:
        ...

    def get_current_configuration(self) -> dict[str, Any]:
        ...

    def clear_history(self) -> None:
        ...

    @property
    def last_metadata(self) -> dict[str, Any]:
        ...

    @property
    def history(self) -> list[dict[str, Any]]:
        ...

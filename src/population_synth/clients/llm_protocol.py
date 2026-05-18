from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Structural contract shared by GeminiClient and ClaudeCodeClient."""

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        ...

    def update_config(self, **kwargs: Any) -> None:
        ...

    def update_default_model(self, new_model_name: str) -> None:
        ...

    def get_current_configuration(self) -> Dict[str, Any]:
        ...

    def clear_history(self) -> None:
        ...

    @property
    def last_metadata(self) -> Dict[str, Any]:
        ...

    @property
    def history(self) -> List[Dict[str, Any]]:
        ...

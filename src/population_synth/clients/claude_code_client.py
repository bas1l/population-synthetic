import copy
import logging
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from population_synth.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking


class ClaudeCodeClient:
    """
    A subprocess wrapper around the `claude` CLI that satisfies the LLMClient protocol.

    Manages persistent configuration state and execution history identically to
    GeminiClient, but delegates generation to the local claude CLI process.
    """

    def __init__(self, model_name: str = "sonnet", default_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the ClaudeCodeClient.

        Args:
            model_name: Default Claude model identifier passed via --model. Defaults to 'sonnet'.
            default_config: Initial configuration parameters (e.g., system_instruction).

        Raises:
            RuntimeError: If the `claude` CLI executable is not found on PATH.
        """
        if shutil.which("claude") is None:
            raise RuntimeError(
                "claude CLI not found on PATH. Install Claude Code and ensure `claude` is executable."
            )

        self.default_model_name = model_name

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        self._config_state: Dict[str, Any] = default_config if default_config else {}

        self._last_execution_metadata: Optional[Dict[str, Any]] = None
        self._execution_history: List[Dict[str, Any]] = []

        self.logger.info(
            "ClaudeCodeClient initialized. Model: %s. Config: %s",
            self.default_model_name,
            self._config_state,
        )

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

    def get_current_configuration(self) -> Dict[str, Any]:
        """
        Retrieve the full current state of the client configuration.
        """
        return {
            "model": self.default_model_name,
            "generation_config": copy.deepcopy(self._config_state),
        }

    @property
    def last_metadata(self) -> Dict[str, Any]:
        """
        Returns the metadata (model, config, timestamp) used for the most recent CLI call.
        """
        return self._last_execution_metadata or {}

    @property
    def history(self) -> List[Dict[str, Any]]:
        """
        Returns the list of metadata for all CLI calls since the last clear.
        """
        return self._execution_history

    def clear_history(self) -> None:
        """
        Clears the execution history. Call this before starting a new logical unit of work.
        """
        self._execution_history = []
        self._last_execution_metadata = None

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        """
        Generate content by invoking the claude CLI as a subprocess.

        Args:
            prompt: The input text passed via stdin to the claude CLI.
            **kwargs: Temporary configuration overrides for this specific call
                      (e.g., system_instruction, model).

        Returns:
            str: The trimmed stdout from the claude CLI.

        Raises:
            RuntimeError: If the CLI process exits with a non-zero return code.
        """
        effective_config = self._config_state.copy()
        effective_config.update(kwargs)

        target_model = effective_config.pop("model", self.default_model_name)
        system_instruction = effective_config.pop("system_instruction", None)

        metadata = {
            "model": target_model,
            "config": effective_config,
            "timestamp": datetime.now().isoformat(),
        }
        self._last_execution_metadata = metadata
        self._execution_history.append(metadata)

        cmd = ["claude", "-p", "--model", target_model]
        if system_instruction:
            cmd += ["--append-system-prompt", system_instruction]

        self.logger.debug("Invoking claude CLI: %s", cmd)

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

        if result.returncode != 0:
            self.logger.error(
                "claude CLI exited with code %d: %s", result.returncode, result.stderr
            )
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr.strip()}"
            )

        return result.stdout.strip()

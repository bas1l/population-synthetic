import copy
import json
import logging
import random
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from population_synth.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking


class ClaudeCodeClient:
    """
    A subprocess wrapper around the `claude` CLI that satisfies the LLMClient protocol.

    Manages persistent configuration state and execution history identically to
    GeminiClient, but delegates generation to the local claude CLI process.
    """

    def __init__(
        self,
        model_name: str = "sonnet",
        default_config: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
    ):
        if shutil.which("claude") is None:
            raise RuntimeError(
                "claude CLI not found on PATH. Install Claude Code and ensure `claude` is executable."
            )

        self.default_model_name = model_name
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

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

    def _run_cli(self, cmd: List[str], prompt: str, timeout: int) -> str:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        # Parse JSON envelope from --output-format json
        parsed = None
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                pass

        if result.returncode != 0:
            if parsed and isinstance(parsed, dict):
                error_detail = parsed.get("error", {})
                if isinstance(error_detail, dict):
                    msg = error_detail.get("message", str(error_detail))
                else:
                    msg = str(error_detail)
            elif stderr:
                msg = stderr
            elif stdout:
                msg = stdout[:500]
            else:
                msg = "(no output)"
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {msg}"
            )

        if parsed and isinstance(parsed, dict) and "result" in parsed:
            return parsed["result"].strip()

        return stdout

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
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

        cmd = [
            "claude", "-p",
            "--model", target_model,
            "--no-session-persistence",
            "--output-format", "json",
            "--tools", "",
        ]
        if system_instruction:
            cmd += ["--system-prompt", system_instruction]

        self.logger.debug("Invoking claude CLI: %s", cmd)

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._run_cli(cmd, prompt, timeout=120)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                    delay *= random.uniform(0.75, 1.25)
                    self.logger.warning(
                        "CLI attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt + 1, self._max_retries, e, delay,
                    )
                    time.sleep(delay)

        self.logger.error("CLI failed after %d attempts: %s", self._max_retries, last_error)
        raise RuntimeError(
            f"claude CLI failed after {self._max_retries} attempts: {last_error}"
        )

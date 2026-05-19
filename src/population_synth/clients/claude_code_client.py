import copy
import json
import logging
import queue
import random
import shutil
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from population_synth.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking


class ClaudeCodeClient:
    """
    A subprocess wrapper around the `claude` CLI that satisfies the LLMClient protocol.

    Manages persistent configuration state and execution history identically to
    GeminiClient, but delegates generation to a persistent claude CLI process
    using the stream-json NDJSON protocol.
    """

    _INIT_TIMEOUT = 30
    _CLOSE_TIMEOUT = 5

    def __init__(
        self,
        model_name: str = "sonnet",
        default_config: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        timeout: int = 120,
    ):
        if shutil.which("claude") is None:
            raise RuntimeError(
                "claude CLI not found on PATH. Install Claude Code and ensure `claude` is executable."
            )

        self.default_model_name = model_name
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        self._config_state: Dict[str, Any] = default_config if default_config else {}

        self._last_execution_metadata: Optional[Dict[str, Any]] = None
        self._execution_history: List[Dict[str, Any]] = []

        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._stdout_queue: queue.Queue = queue.Queue()
        self._current_system_instruction: Optional[str] = None
        self._current_model: Optional[str] = None

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

    def _launch_process(self, model: str, system_instruction: Optional[str]) -> None:
        cmd = [
            "claude",
            "--model", model,
            "--no-session-persistence",
            "--tools", "",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--exclude-dynamic-system-prompt-sections",
            "--strict-mcp-config",
            "--mcp-config", "{}",
            "--disable-slash-commands",
            "--max-turns", "1",
        ]
        if system_instruction:
            cmd += ["--system-prompt", system_instruction]

        self.logger.debug("Launching persistent claude process: %s", cmd)

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._stdout_queue = queue.Queue()
        self._reader = threading.Thread(
            target=self._reader_thread,
            args=(self._process,),
            daemon=True,
        )
        self._reader.start()

    def _reader_thread(self, process: subprocess.Popen) -> None:
        try:
            for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    self._stdout_queue.put(line)
        finally:
            self._stdout_queue.put(None)

    def _read_until_result(self, timeout: int) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        seen: List[str] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(
                    cmd="claude (stream-json)",
                    timeout=timeout,
                )

            try:
                line = self._stdout_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(
                        cmd="claude (stream-json)",
                        timeout=timeout,
                    )
                continue

            if line is None:
                raise RuntimeError("claude process terminated unexpectedly")

            seen.append(line)

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(msg, dict):
                continue

            if msg.get("type") != "result":
                continue

            if msg.get("is_error"):
                error_detail = msg.get("result") or msg.get("error") or str(msg)
                raise RuntimeError(f"claude CLI returned an error result: {error_detail}")

            return msg

    def _send_prompt(self, prompt: str) -> None:
        payload = json.dumps({
            "type": "message",
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        })
        line = (payload + "\n").encode("utf-8")
        self._process.stdin.write(line)
        self._process.stdin.flush()

    def _ensure_process(self, model: str, system_instruction: Optional[str]) -> None:
        process_dead = self._process is None or self._process.poll() is not None
        system_changed = system_instruction != self._current_system_instruction
        model_changed = model != self._current_model

        if process_dead or system_changed or model_changed:
            self._close_process()
            self._launch_process(model, system_instruction)
            self._current_system_instruction = system_instruction
            self._current_model = model
            self._wait_for_init()

    def _wait_for_init(self) -> None:
        deadline = time.monotonic() + self._INIT_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"claude process did not send init signal within {self._INIT_TIMEOUT}s"
                )
            try:
                line = self._stdout_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"claude process did not send init signal within {self._INIT_TIMEOUT}s"
                    )
                continue

            if line is None:
                raise RuntimeError("claude process terminated before sending init signal")

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if (
                isinstance(msg, dict)
                and msg.get("type") == "system"
                and msg.get("subtype") == "init"
            ):
                self.logger.debug("claude process ready (init received)")
                return

    def _close_process(self) -> None:
        if self._process is not None:
            try:
                self._process.stdin.close()
            except Exception:
                pass

            try:
                self._process.wait(timeout=self._CLOSE_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=self._CLOSE_TIMEOUT)
                except Exception:
                    pass

        if self._reader is not None:
            self._reader.join(timeout=self._CLOSE_TIMEOUT)

        self._process = None
        self._reader = None
        self._stdout_queue = queue.Queue()

    def close(self) -> None:
        """
        Terminate the persistent claude process and clean up resources.
        """
        self._close_process()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

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

        self.logger.debug("generate_content called. Model: %s", target_model)

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                self._ensure_process(target_model, system_instruction)
                self._send_prompt(prompt)
                result_msg = self._read_until_result(timeout=self._timeout)
                text = result_msg.get("result", "")
                if isinstance(text, str):
                    text = text.strip()
                return text
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
                last_error = e
                self._close_process()
                if attempt < self._max_retries - 1:
                    delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                    delay *= random.uniform(0.75, 1.25)
                    self.logger.warning(
                        "generate_content attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt + 1, self._max_retries, e, delay,
                    )
                    time.sleep(delay)

        self.logger.error(
            "generate_content failed after %d attempts: %s", self._max_retries, last_error
        )
        raise RuntimeError(
            f"claude CLI failed after {self._max_retries} attempts: {last_error}"
        )

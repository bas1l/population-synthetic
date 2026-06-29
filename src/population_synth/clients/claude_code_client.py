from __future__ import annotations

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
from typing import Any

from population_synth.clients.call_context import format_corr_token
from population_synth.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking


class ClaudeCodeClient:
    """
    A persistent subprocess wrapper around the `claude` CLI that satisfies the LLMClient protocol.

    One `claude` process is kept alive per instance (lazily launched on first generate_content()
    call). Prompts are written as NDJSON to stdin; a daemon reader thread drains stdout into a
    queue.Queue; generate_content() blocks on the queue until {"type":"result"} arrives.

    The process is restarted automatically when the model or system_instruction changes, or after
    any unrecoverable error (the retry loop calls _close_process() before each retry).
    """

    def __init__(
        self,
        model_name: str = "sonnet",
        default_config: dict[str, Any] | None = None,
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

        self._config_state: dict[str, Any] = default_config if default_config else {}

        self._last_execution_metadata: dict[str, Any] | None = None
        self._execution_history: list[dict[str, Any]] = []

        # Persistent process state — all None until first _launch_process()
        self._proc: subprocess.Popen | None = None
        self._reader_thread_handle: threading.Thread | None = None
        self._stdout_queue: queue.Queue | None = None
        self._current_model: str | None = None
        self._current_system_prompt: str | None = None

        # Timing stash: _ensure_process() sets this; generate_content() reads and resets it
        self._last_launch_ms: float = 0.0

        self.logger.info(
            "ClaudeCodeClient initialized. Model: %s. Config: %s",
            self.default_model_name,
            self._config_state,
        )

    # ------------------------------------------------------------------
    # Public interface (unchanged)
    # ------------------------------------------------------------------

    def update_config(self, **kwargs: Any) -> None:
        self.logger.info(f"Updating persistent config with: {kwargs}")
        self._config_state.update(kwargs)

    def update_default_model(self, new_model_name: str) -> None:
        self.logger.info(f"Updating default model from {self.default_model_name} to {new_model_name}")
        self.default_model_name = new_model_name

    def get_current_configuration(self) -> dict[str, Any]:
        return {
            "model": self.default_model_name,
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

    def close(self) -> None:
        self._close_process()

    def __del__(self) -> None:
        try:
            self._close_process()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Persistent process lifecycle
    # ------------------------------------------------------------------

    def _launch_process(self, model: str, system_instruction: str | None) -> None:
        cmd = [
            "claude",
            "--model", model,
            "--no-session-persistence",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--max-turns", "1",
            # Lock the subprocess down to pure text generation: deny every built-in tool
            # (WebSearch/WebFetch are the actual internet-query tools; the rest are
            # defense-in-depth) and refuse to load any inherited MCP servers. Identity
            # generation never needs tools, and the host's user-level settings globally
            # auto-approve WebSearch, so the restriction must be imposed here.
            "--strict-mcp-config",
            "--disallowedTools",
            "Bash", "WebSearch", "WebFetch", "Read", "Write", "Edit",
            "Glob", "Grep", "Task", "NotebookEdit", "TodoWrite",
        ]
        if system_instruction:
            cmd += ["--system-prompt", system_instruction]

        self.logger.debug("Launching persistent claude process: %s", cmd)

        self._stdout_queue = queue.Queue()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._current_model = model
        self._current_system_prompt = system_instruction

        self._reader_thread_handle = threading.Thread(
            target=self._reader_thread,
            daemon=True,
            name="claude-stdout-reader",
        )
        self._reader_thread_handle.start()

    def _reader_thread(self) -> None:
        # Runs in a daemon thread; drains proc.stdout line-by-line into the queue.
        # The None sentinel signals EOF to _read_until_result().
        try:
            for line in iter(self._proc.stdout.readline, ""):
                self._stdout_queue.put(line)
        finally:
            self._stdout_queue.put(None)

    def _ensure_process(self, model: str, system_instruction: str | None) -> None:
        needs_launch = (
            self._proc is None
            or self._proc.poll() is not None
            or model != self._current_model
            or system_instruction != self._current_system_prompt
        )
        if needs_launch:
            self._close_process()
            t0 = time.perf_counter()
            self._launch_process(model, system_instruction)
            self._last_launch_ms = (time.perf_counter() - t0) * 1000
        else:
            self._last_launch_ms = 0.0

    def _close_process(self) -> None:
        if self._proc is None:
            return

        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        except Exception:
            pass

        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()

        if self._reader_thread_handle is not None:
            self._reader_thread_handle.join(timeout=2)

        self._proc = None
        self._reader_thread_handle = None
        self._stdout_queue = None
        self._current_model = None
        self._current_system_prompt = None

    # ------------------------------------------------------------------
    # Per-call I/O
    # ------------------------------------------------------------------

    def _send_prompt(self, prompt: str) -> None:
        msg = {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None,
        }
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _read_until_result(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        skip_types = {"system", "rate_limit_event", "assistant", "stream_event"}

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

            try:
                line = self._stdout_queue.get(timeout=remaining)
            except queue.Empty:
                raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

            if line is None:
                raise RuntimeError("claude process terminated unexpectedly")

            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(msg, dict) or "type" not in msg:
                continue

            msg_type = msg["type"]
            if msg_type in skip_types:
                continue

            if msg_type == "result":
                if msg.get("is_error"):
                    error_detail = msg.get("result") or msg.get("error") or str(msg)
                    raise RuntimeError(f"claude CLI returned an error result: {error_detail}")
                result = msg.get("result", "")
                return result.strip() if isinstance(result, str) else result

            # Unknown type — skip rather than raise so forward-compat is preserved
            self.logger.debug("Ignoring unknown claude message type: %s", msg_type)

    # ------------------------------------------------------------------
    # generate_content (public, retry-wrapped)
    # ------------------------------------------------------------------

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

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                self._ensure_process(target_model, system_instruction)
                launch_ms = self._last_launch_ms

                t_inf_start = time.perf_counter()
                self._send_prompt(prompt)
                result = self._read_until_result(self._timeout)
                t_inference_ms = (time.perf_counter() - t_inf_start) * 1000

                self.logger.info(
                    "claude call: model=%s t_launch_ms=%.0f t_inference_ms=%.0f%s",
                    target_model, launch_ms, t_inference_ms, format_corr_token(),
                )
                return result

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

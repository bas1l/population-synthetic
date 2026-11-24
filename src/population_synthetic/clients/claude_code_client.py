"""ClaudeCodeClient -- one independent `claude -p` subprocess per call.

Defines ``ClaudeCodeClient``, which satisfies the shared LLMClient protocol by
spawning a **fresh, minimal-context** ``claude -p`` process for every
``generate_content`` call, with retry, provenance metadata and tool lock-down.

Why a fresh process per call (and never a persistent one): the earlier design kept
one ``claude --input-format stream-json`` process alive per client and wrote every
call into it as the next user turn, so each call saw every earlier prompt and answer
on that client. The persona-realism judge reuses one client per worker thread, which
made its rounds neither cold nor independent. The CLI documents no in-band
conversation reset, so independence is guaranteed by construction instead: a call
is a process. See ``docs/development/plans/completed/fix-claude-cli-conversation-leak.md``.

The launch is also *minimal*: ``--tools ""`` (no tool), ``--setting-sources ""``
(no user/project settings, hooks or ``CLAUDE.md``), ``--strict-mcp-config`` (no
inherited MCP servers), ``--no-session-persistence`` and a working directory that is
an empty temporary directory, so the repository's own instructions can never reach
the model's context.

Sampling temperature: the ``claude`` CLI exposes **no** temperature control (no flag,
no settings key; ``--effort`` is not a sampling temperature). A ``temperature`` in
the client config is therefore never applied, and every call's metadata says so with
``temperature_applied: False`` rather than implying otherwise.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

from population_synthetic.clients.call_context import format_corr_token
from population_synthetic.clients.llm_protocol import LLMClient  # noqa: F401  # for type-checking
from population_synthetic.clients.retry_policy import max_attempts

__all__ = ["CONTEXT_ISOLATION", "ClaudeCodeClient", "build_claude_argv"]

#: The context regime every call of this client runs under, stamped into each call's
#: metadata. Consumers that cache LLM output (the persona-realism verdict cache)
#: persist it so output produced under the earlier shared-conversation regime -- which
#: carries no tag -- can never be silently mixed with output produced under this one.
#: Bump the suffix if the isolation guarantee ever changes.
CONTEXT_ISOLATION = "fresh_process_per_call_v1"

#: Seconds to wait for a killed process to be reaped before giving up on it.
_REAP_SECONDS = 10


def build_claude_argv(model: str, system_instruction: str | None) -> list[str]:
    """The minimal ``claude -p`` argv for one independent call.

    The prompt is NOT in the argv: it goes on stdin. No session flag (``--continue``,
    ``--resume``, ``--session-id``, ``--fork-session``) is ever passed, so every
    process starts a new conversation.
    """
    argv = [
        "claude",
        "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--max-turns", "1",
        # No tool at all (WebSearch/WebFetch would be live internet queries, and the
        # host's user settings auto-approve some), no inherited MCP server.
        "--tools", "",
        "--strict-mcp-config",
        # Load no user/project/local settings: no hooks, no CLAUDE.md, no memory.
        "--setting-sources", "",
        "--disable-slash-commands",
    ]
    if system_instruction:
        argv += ["--system-prompt", system_instruction]
    return argv


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill *proc* and every descendant if still running, then reap it. Never raises."""
    if proc.poll() is None:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                import signal

                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:  # noqa: BLE001 -- fall through to the direct kill below
            pass
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 -- already gone
            pass
    try:
        proc.wait(timeout=_REAP_SECONDS)
    except Exception:  # noqa: BLE001 -- never mask the caller's own error
        pass


def _parse_result(stdout: str) -> dict[str, Any]:
    """Return the CLI's ``result`` object from ``--output-format json`` stdout (fail-fast).

    The CLI prints one JSON object. A stray non-JSON line before it is tolerated by
    falling back to the last non-empty lines; anything else raises -- an unparsable
    stdout is never turned into an empty answer.
    """
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError("claude process terminated unexpectedly: empty stdout")
    candidates = [text] + [line.strip() for line in reversed(text.splitlines()) if line.strip()]
    for candidate in candidates:
        try:
            msg = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("type") == "result":
            return msg
    raise RuntimeError(f"claude CLI produced no parsable result object: {text[:500]!r}")


class ClaudeCodeClient:
    """A per-call subprocess wrapper around the `claude` CLI satisfying the LLMClient protocol.

    Every ``generate_content`` call (and every retry attempt of it) spawns one fresh
    ``claude -p`` process with :func:`build_claude_argv`, in an empty temporary working
    directory, writes the prompt to its stdin, reads the single JSON result and reaps
    the process (killing the whole tree on timeout or error). No state survives a
    call, so two calls on one client cannot see each other -- the client can be cached
    per thread or per persona without any context leaking between calls.
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
        # Lifted to the shared ceiling once the run turns on retry_until_success.
        # Assigned post-construction by the generation scripts, like the
        # generator's flag of the same name.
        self.retry_until_success: bool = False
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

        # The in-flight process of the current call, if any -- held only so close()
        # (called from an atexit drain on another thread) can kill it.
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()

        self.logger.info(
            "ClaudeCodeClient initialized. Model: %s. Config: %s",
            self.default_model_name,
            self._config_state,
        )

    # ------------------------------------------------------------------
    # Public interface
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
        """Kill the in-flight call's process tree, if any. A no-op between calls."""
        with self._proc_lock:
            proc = self._proc
        if proc is not None:
            _kill_tree(proc)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # One independent call
    # ------------------------------------------------------------------

    def _run_once(self, prompt: str, model: str, system_instruction: str | None) -> dict[str, Any]:
        """Spawn one minimal ``claude -p`` process and return its parsed result object.

        The process is always reaped before this returns or raises: on timeout or any
        exception its whole tree is killed in the ``finally``.
        """
        argv = build_claude_argv(model, system_instruction)
        popen_kwargs: dict[str, Any] = {}
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True  # own process group, for killpg
        with tempfile.TemporaryDirectory(prefix="claude_call_", ignore_cleanup_errors=True) as cwd:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                cwd=cwd,
                **popen_kwargs,
            )
            with self._proc_lock:
                self._proc = proc
            try:
                stdout, stderr = proc.communicate(input=prompt, timeout=self._timeout)
            finally:
                _kill_tree(proc)  # only reaps when the process already exited
                with self._proc_lock:
                    self._proc = None

        try:
            msg = _parse_result(stdout)
        except RuntimeError as exc:
            if proc.returncode not in (0, None):
                raise RuntimeError(
                    f"claude process terminated unexpectedly (exit {proc.returncode}): "
                    f"{(stderr or '').strip()[:500]}"
                ) from exc
            raise
        if msg.get("is_error"):
            error_detail = msg.get("result") or msg.get("error") or str(msg)
            raise RuntimeError(f"claude CLI returned an error result: {error_detail}")
        return msg

    # ------------------------------------------------------------------
    # generate_content (public, retry-wrapped)
    # ------------------------------------------------------------------

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        effective_config = self._config_state.copy()
        effective_config.update(kwargs)

        target_model = effective_config.pop("model", self.default_model_name)
        system_instruction = effective_config.pop("system_instruction", None)

        metadata: dict[str, Any] = {
            "provider": "claude",
            "model": target_model,
            "config": effective_config,
            # The CLI has no sampling-temperature control: a configured value is
            # recorded in `config` above but never reaches the model.
            "temperature_applied": False,
            "context_isolation": CONTEXT_ISOLATION,
            "session_id": None,
            "timestamp": datetime.now().isoformat(),
            "request_sent_at": None,
            "response_received_at": None,
            "elapsed_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            # Prompt-cache token telemetry (Anthropic). ``prompt_tokens`` remains the
            # UNCACHED input remainder; these are captured additively so cost can
            # price the cached portion. ``None`` when the CLI omits them.
            "cache_read_tokens": None,
            "cache_creation_tokens": None,
            "status": None,
            "error_category": None,
            "error": None,
        }
        self._last_execution_metadata = metadata
        self._execution_history.append(metadata)

        def _fail(category: str, message: str) -> None:
            metadata["status"] = "error"
            metadata["error_category"] = category
            metadata["error"] = message

        last_error: Exception | None = None
        last_error_category: str = "unknown"
        attempts = max_attempts(self.retry_until_success, self._max_retries)
        for attempt in range(attempts):
            try:
                metadata["request_sent_at"] = datetime.now().isoformat()
                t0 = time.perf_counter()
                msg = self._run_once(prompt, target_model, system_instruction)
                elapsed_ms = (time.perf_counter() - t0) * 1000  # launch + inference

                result = msg.get("result", "")
                usage = msg.get("usage") or {}
                if not isinstance(usage, dict):
                    usage = {}

                metadata["response_received_at"] = datetime.now().isoformat()
                metadata["elapsed_ms"] = elapsed_ms
                metadata["session_id"] = msg.get("session_id")

                prompt_tokens = usage.get("input_tokens")
                completion_tokens = usage.get("output_tokens")
                # Prompt-cache tokens are captured separately; `prompt_tokens` keeps its
                # "uncached input" semantics that other consumers rely on.
                cache_read_tokens = usage.get("cache_read_input_tokens")
                cache_creation_tokens = usage.get("cache_creation_input_tokens")
                total_tokens = (
                    prompt_tokens + completion_tokens
                    if prompt_tokens is not None and completion_tokens is not None
                    else None
                )
                metadata["prompt_tokens"] = prompt_tokens
                metadata["completion_tokens"] = completion_tokens
                metadata["total_tokens"] = total_tokens
                metadata["cache_read_tokens"] = cache_read_tokens
                metadata["cache_creation_tokens"] = cache_creation_tokens
                metadata["status"] = "ok"
                metadata["error_category"] = None
                metadata["error"] = None

                self.logger.info(
                    "claude call: model=%s elapsed_ms=%.0f "
                    "prompt_tokens=%s completion_tokens=%s "
                    "cache_read_tokens=%s cache_creation_tokens=%s%s",
                    target_model, elapsed_ms, prompt_tokens, completion_tokens,
                    cache_read_tokens, cache_creation_tokens, format_corr_token(),
                )
                return result.strip() if isinstance(result, str) else result

            except (RuntimeError, subprocess.TimeoutExpired, OSError, UnicodeDecodeError) as e:
                last_error = e
                if isinstance(e, subprocess.TimeoutExpired):
                    last_error_category = "timeout"
                elif isinstance(e, OSError) or "process terminated unexpectedly" in str(e):
                    last_error_category = "network"
                elif "returned an error result" in str(e):
                    last_error_category = "model_limitation"
                else:
                    last_error_category = "unknown"
                if attempt < attempts - 1:
                    delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                    delay *= random.uniform(0.75, 1.25)
                    self.logger.warning(
                        "generate_content attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt + 1, attempts, e, delay,
                    )
                    time.sleep(delay)

        self.logger.error(
            "generate_content failed after %d attempts: %s", attempts, last_error
        )
        _fail(
            last_error_category,
            f"claude CLI failed after {attempts} attempts: {last_error}",
        )
        raise RuntimeError(
            f"claude CLI failed after {attempts} attempts: {last_error}"
        )

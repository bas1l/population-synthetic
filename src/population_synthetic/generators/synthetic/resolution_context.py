"""One JSON-constrained LLM call: retry budget, correlation key, telemetry.

Defines :class:`ResolutionContext`, the seam that lets a :class:`~.category.Category`
resolve an attribute without ever seeing the client, the filesystem or the
telemetry log. A category hands over a rendered prompt and receives a parsed
value; everything between -- the JSON-extraction fallbacks, the attempt budget,
the fatal-error escape, the ``(persona_id, call_index)`` correlation key and the
``LLMInteractionEntry`` written for every attempt -- lives here.

The context also owns the correlation counter, which is what keeps that key
unique. One index is claimed per *client call*, not per :meth:`call_json`
invocation, so a category that retries three times spends three indices and the
joiner can attach token counts and latency to the exact attempt that produced
them.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from population_synthetic.clients.call_context import set_correlation
from population_synthetic.clients.llm_protocol import LLMClient
from population_synthetic.clients.retry_policy import FATAL_ERROR_CATEGORIES, max_attempts

from .llm_interaction_log import LLMInteractionCollector, LLMInteractionEntry

# Attempt budget for the JSON-parse retry layer WITHOUT ``retry_until_success``.
# With it, the budget rises to the shared MAX_RETRY_ATTEMPTS ceiling (see
# clients/retry_policy.py): a model that never returns usable output then fails
# loudly instead of hanging in a truly unbounded loop.
_DEFAULT_JSON_ATTEMPTS = 3


def _extract_json(text: str) -> dict | list:
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract content between markdown fences
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find first JSON object or array
    for pattern in (r"\{[^{}]*\}", r"\[.*?\]"):
        obj_match = re.search(pattern, text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def _extract_expected_key(parsed: dict | list, expected_key: str) -> Any:
    """
    Return parsed[expected_key], tolerating whitespace-corrupted keys
    (e.g. ' value' instead of 'value') that some models emit under Ollama's
    JSON-constrained decoding. Raises KeyError when the key is absent so the
    caller's retry loop treats it as a retriable parse failure.
    """
    if not isinstance(parsed, dict):
        raise KeyError(expected_key)
    if expected_key in parsed:
        return parsed[expected_key]
    target = expected_key.strip()
    for key, value in parsed.items():
        if isinstance(key, str) and key.strip() == target:
            return value
    raise KeyError(expected_key)


class ResolutionContext:
    """Everything a category needs to turn a prompt into a value, and nothing more."""

    def __init__(
        self,
        client: LLMClient,
        *,
        system_instruction: str,
        persona_id: str | None = None,
        call_index: int = 0,
        interaction_collector: LLMInteractionCollector | None = None,
        retry_until_success: bool = False,
        use_structured_output: bool = False,
    ) -> None:
        """Bind one persona's resolution run to one client.

        Args:
            client: The LLM client this run calls. One client per worker thread,
                so the context is never shared across threads.
            system_instruction: The run-level system prompt, identical for every
                category. Categories never see it -- they build the user prompt
                only, which is why it is held here rather than passed per call.
            persona_id: Correlation key half. ``None`` on the single-persona path,
                where there is nothing to disambiguate.
            call_index: The index already spent. Non-zero only when resuming, so
                the resumed run continues past the telemetry it inherited.
            interaction_collector: Sink for the per-attempt telemetry record, or
                ``None`` to record nothing.
            retry_until_success: Raise the attempt budget to the shared ceiling.
            use_structured_output: Pass the per-call ``response_schema`` to the
                client. Off for providers that cannot constrain decoding.
        """
        self._client = client
        self._system_instruction = system_instruction
        self._persona_id = persona_id
        self._call_index = call_index
        self._interaction_collector = interaction_collector
        self.retry_until_success = retry_until_success
        self.use_structured_output = use_structured_output

    # -- correlation ----------------------------------------------------------

    @property
    def call_index(self) -> int:
        """The highest correlation index spent so far. Checkpointed by the persona."""
        return self._call_index

    @property
    def persona_id(self) -> str | None:
        return self._persona_id

    @property
    def interaction_collector(self) -> LLMInteractionCollector | None:
        return self._interaction_collector

    def resume_from(self, call_index: int) -> None:
        """Continue the counter past indices a previous attempt already spent.

        Called once, before the first :meth:`call_json`, when a checkpoint is
        restored. Reusing a spent index would break the ``(persona_id, call_index)``
        join that every cost and latency figure is computed over.
        """
        self._call_index = call_index

    def _next_call_index(self) -> int:
        """Claim the next correlation index and publish it to the client's logger.

        One index per *client call*, not per :meth:`call_json`: the log line the
        client emits and the JSONL entry recorded here share it, so the joiner can
        attach token/latency to the exact persona+attempt.
        """
        self._call_index += 1
        set_correlation(self._persona_id, self._call_index)
        return self._call_index

    # -- the call -------------------------------------------------------------

    def call_json(
        self,
        prompt: str,
        *,
        expected_key: str | None = None,
        response_schema: dict | None = None,
        category: str = "",
        method: str = "",
        step: str = "",
    ) -> Any:
        """Send *prompt* and return the parsed JSON (or one key of it).

        Args:
            prompt: The rendered user prompt. Built by the category; never touched here.
            expected_key: Key to lift out of the parsed object, or ``None`` for the
                whole object. A missing key is a retriable parse failure.
            response_schema: JSON schema for constrained decoding, honoured only
                when ``use_structured_output`` is set.
            category: Which attribute this call serves. Doubles as the telemetry
                switch -- an empty string records nothing.
            method: Which generation method is resolving that attribute.
            step: Which step of that method this call is.

        Raises:
            ValueError: The budget was exhausted without a parseable response.
            RuntimeError: Re-raised unchanged for a fatal provider error.
        """
        extra = (
            {"response_schema": response_schema}
            if self.use_structured_output and response_schema is not None
            else {}
        )
        last_error: Exception | None = None
        attempts = max_attempts(self.retry_until_success, _DEFAULT_JSON_ATTEMPTS)
        for attempt in range(attempts):
            raw = ""
            call_index = self._next_call_index()
            try:
                raw = self._client.generate_content(
                    prompt, system_instruction=self._system_instruction, **extra
                )
                meta = getattr(self._client, "last_metadata", None) or {}
                parsed = _extract_json(raw)
                value = (
                    _extract_expected_key(parsed, expected_key)
                    if expected_key is not None
                    else parsed
                )
                if self._interaction_collector and category:
                    self._interaction_collector.record(LLMInteractionEntry(
                        category=category,
                        method=method,
                        step=step,
                        prompt=prompt,
                        raw_response=raw,
                        parsed_value=parsed,
                        attempt=attempt + 1,
                        persona_id=self._persona_id,
                        call_index=call_index,
                        provider=meta.get("provider"),
                        model=meta.get("model"),
                        request_sent_at=meta.get("request_sent_at"),
                        response_received_at=meta.get("response_received_at"),
                        elapsed_ms=meta.get("elapsed_ms"),
                        prompt_tokens=meta.get("prompt_tokens"),
                        completion_tokens=meta.get("completion_tokens"),
                        total_tokens=meta.get("total_tokens"),
                    ))
                return value
            except (json.JSONDecodeError, KeyError, RuntimeError) as e:
                meta = getattr(self._client, "last_metadata", None) or {}
                if isinstance(e, (json.JSONDecodeError, KeyError)):
                    error_category = "invalid_response"
                else:
                    error_category = meta.get("error_category") or "unknown"
                if self._interaction_collector and category:
                    self._interaction_collector.record(LLMInteractionEntry(
                        category=category,
                        method=method,
                        step=f"{step}_retry",
                        prompt=prompt,
                        raw_response=raw,
                        parsed_value=None,
                        error=f"{type(e).__name__}: {e}",
                        attempt=attempt + 1,
                        persona_id=self._persona_id,
                        call_index=call_index,
                        provider=meta.get("provider"),
                        model=meta.get("model"),
                        request_sent_at=meta.get("request_sent_at"),
                        response_received_at=meta.get("response_received_at"),
                        elapsed_ms=meta.get("elapsed_ms"),
                        prompt_tokens=meta.get("prompt_tokens"),
                        completion_tokens=meta.get("completion_tokens"),
                        total_tokens=meta.get("total_tokens"),
                        error_category=error_category,
                    ))
                # A fatal provider error (missing model, rejected credentials) is not
                # made truthy by repetition: it must escape the budget immediately,
                # or ``retry_until_success`` turns a misconfigured run into a
                # 100-attempt-per-call grind that still fails.
                if error_category in FATAL_ERROR_CATEGORIES:
                    raise
                last_error = e
                raw_snippet = raw[:500] if raw else "(no response)"
                logging.warning(
                    "LLM JSON parse attempt %d/%d failed (%s): %s\n--- RAW RESPONSE ---\n%s\n--- END ---",
                    attempt + 1, attempts, type(e).__name__, e, raw_snippet,
                )
        raise ValueError(
            f"LLM returned invalid or incomplete JSON after {attempts} attempts. Last error: {last_error}"
        )

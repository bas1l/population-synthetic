"""DAG-driven, per-category configurable identity generation.

Defines ``IdentityGeneratorConfigurable``, a ``BaseIdentityGenerator``
that resolves categories in topological order from an explicit dependency
graph (Kahn's algorithm). Each category is filled via its declared
method -- pick, generate_pick, generate_evaluate_pick, or
generate_evaluate_random_pick -- using JSON-constrained LLM calls with
retry, weight reconciliation, and incremental interaction logging.
"""

import json
import logging
import os
import random
import re
from collections import deque
from typing import Any

import numpy as np
import yaml

from population_synthetic.clients.call_context import set_correlation
from population_synthetic.clients.llm_protocol import LLMClient
from population_synthetic.clients.retry_policy import FATAL_ERROR_CATEGORIES, max_attempts

from .base_identity_generator import BaseIdentityGenerator
from .llm_interaction_log import LLMInteractionEntry

_WEIGHT_COUNT_TOLERANCE_RATIO = 0.1

# Attempt budgets for the two generator-level retry layers WITHOUT
# ``retry_until_success``. With it, both rise to the shared MAX_RETRY_ATTEMPTS
# ceiling (see clients/retry_policy.py): a model that never returns usable
# output then fails loudly instead of hanging in a truly unbounded loop.
_DEFAULT_JSON_ATTEMPTS = 3
_DEFAULT_WEIGHT_RECONCILE_ATTEMPTS = 3


class IdentityGeneratorConfigurable(BaseIdentityGenerator):
    """Identity generator using an explicit per-category dependency DAG."""

    def __init__(self, client: LLMClient):
        super().__init__(client)
        # Correlation context for exact log<->JSONL joining.  ``persona_id`` is
        # assigned externally by the parallel runner; ``_call_index`` increments
        # once per client call so each log line + JSONL entry share a unique key.
        self.persona_id: str | None = None
        self._call_index: int = 0

    def _load_flat_schema(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Flat schema file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in flat schema file: {e}")

    @staticmethod
    def _load_strategy(filepath: str) -> tuple[dict, str]:
        """Parse + validate a strategy YAML.

        Returns ``(categories, context_mode)`` where ``context_mode`` is the
        top-level ``context`` key (default ``"cumulative"`` when absent):
        ``"cumulative"`` serialises the full accumulated persona into every
        prompt (today's behavior); ``"none"`` passes no prior-attribute context
        at all (the context-free baseline). Any other value fails loudly.

        The ``family`` / ``version`` axis metadata is validated here too -- the same
        single seam as ``context`` -- so a malformed versioning key is caught at
        load rather than at chart time. It is not returned: nothing in generation
        reads it (the analysis ordering accessor reads the YAML itself), and
        widening the return tuple would ripple through every caller for no gain.

        Presence is required only for **selectable** axis strategies. A
        ``_``-prefixed stem is the project-wide marker for a co-located definition
        that is not an axis option (``discover_axis_values`` skips exactly those):
        the frozen ``_compared_only_*`` record and ``_debug_minimal`` never enter a
        strategy-ordered chart, so demanding a family rank of them would be
        ceremony. Whenever the keys *are* present, they are validated regardless.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Strategy file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in strategy file: {e}")
        categories = data.get("categories") if isinstance(data, dict) else None
        if not categories or not isinstance(categories, dict):
            raise ValueError(f"Strategy file must contain a 'categories' dict: {filepath}")
        context_mode = data.get("context", "cumulative")
        if context_mode not in ("cumulative", "none"):
            raise ValueError(
                f"Strategy file has invalid 'context' value {context_mode!r} "
                f"(expected 'cumulative' or 'none'): {filepath}"
            )
        IdentityGeneratorConfigurable._validate_axis_metadata(data, filepath)
        return categories, context_mode

    @staticmethod
    def _validate_axis_metadata(data: dict, filepath: str) -> None:
        """Fail loudly on a missing/malformed ``family`` or ``version`` key.

        ``family`` names which of the declared generation methods the strategy
        implements (the ranks live in ``strategies/_families.yaml``); ``version`` is
        the integer revision of that family's category set and dependency wiring.
        Together they are what lets two strategies coexist as distinct experimental
        arms, so neither may be silently defaulted.
        """
        selectable = not os.path.basename(filepath).startswith("_")

        family = data.get("family")
        if family is None:
            if selectable:
                raise ValueError(
                    f"Strategy file is missing the required 'family' key: {filepath}. "
                    "It must name one of the families declared in "
                    "config/synthetic/axes/strategies/_families.yaml."
                )
        elif not isinstance(family, str) or not family:
            raise ValueError(
                f"Strategy file has invalid 'family' value {family!r} "
                f"(expected a non-empty string): {filepath}"
            )

        version = data.get("version")
        if version is None:
            if selectable:
                raise ValueError(
                    f"Strategy file is missing the required 'version' key: {filepath}. "
                    "It must be an integer >= 1 identifying this revision of the family."
                )
        elif not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError(
                f"Strategy file has invalid 'version' value {version!r} "
                f"(expected an integer >= 1): {filepath}"
            )

    @staticmethod
    def _build_dag(category_config: dict) -> list[str]:
        """
        Validates the dependency graph and returns categories in topological order
        using Kahn's algorithm. Raises ValueError on undeclared references or cycles.

        The result is a pure function of ``category_config``. Kahn's algorithm leaves
        ties unconstrained -- several categories can hold in-degree 0 at once -- and
        the tie-break here is explicit: **ties resolve in ``category_config``
        declaration order, i.e. the order the categories appear in the strategy
        YAML**. Every structure below is therefore keyed/seeded from that order and
        never from a set, whose iteration order CPython varies per process via hash
        randomisation. That matters because ``depends_on`` schedules only: the prompt
        context block serialises every attribute resolved so far, so a hash-dependent
        tie-break silently changes prompt content between two runs of the same config.
        """
        declared = list(category_config)  # YAML declaration order; the tie-break key

        for cat, cfg in category_config.items():
            for dep in cfg.get("depends_on", []):
                if dep not in category_config:
                    raise ValueError(
                        f"Category '{cat}' declares dependency on '{dep}', "
                        f"which is not declared in category_config."
                    )

        # Both dicts are insertion-ordered by ``declared``, and each ``dependents``
        # list is appended to in declaration order, so the release order of a node's
        # dependents is stable too -- not only the seeding of the queue.
        in_degree: dict[str, int] = {cat: 0 for cat in declared}
        dependents: dict[str, list[str]] = {cat: [] for cat in declared}

        for cat, cfg in category_config.items():
            for dep in cfg.get("depends_on", []):
                dependents[dep].append(cat)
                in_degree[cat] += 1

        queue = deque(cat for cat in declared if in_degree[cat] == 0)
        ordered: list[str] = []

        while queue:
            node = queue.popleft()
            ordered.append(node)
            for dependent in dependents[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(declared):
            resolved = set(ordered)
            participants = [cat for cat in declared if cat not in resolved]
            raise ValueError(
                f"Cycle detected in category_config dependency graph. "
                f"Participants: {participants}"
            )

        return ordered

    @staticmethod
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

    @staticmethod
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

    def _call_llm_json(
        self,
        prompt: str,
        system_instruction: str,
        *,
        expected_key: str | None = None,
        response_schema: dict | None = None,
        log_category: str = "",
        log_method: str = "",
        log_step: str = "",
    ) -> Any:
        extra = (
            {"response_schema": response_schema}
            if self.use_structured_output and response_schema is not None
            else {}
        )
        last_error: Exception | None = None
        attempts = max_attempts(self.retry_until_success, _DEFAULT_JSON_ATTEMPTS)
        for attempt in range(attempts):
            raw = ""
            # One unique correlation key per client call (not per invocation): the
            # log line the client emits and the JSONL entry recorded below share it,
            # so the joiner can attach token/latency to the exact persona+call.
            self._call_index += 1
            call_index = self._call_index
            set_correlation(self.persona_id, call_index)
            try:
                raw = self.client.generate_content(
                    prompt, system_instruction=system_instruction, **extra
                )
                meta = getattr(self.client, "last_metadata", None) or {}
                parsed = self._extract_json(raw)
                value = (
                    self._extract_expected_key(parsed, expected_key)
                    if expected_key is not None
                    else parsed
                )
                if self.interaction_collector and log_category:
                    self.interaction_collector.record(LLMInteractionEntry(
                        category=log_category,
                        method=log_method,
                        step=log_step,
                        prompt=prompt,
                        raw_response=raw,
                        parsed_value=parsed,
                        attempt=attempt + 1,
                        persona_id=self.persona_id,
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
                meta = getattr(self.client, "last_metadata", None) or {}
                if isinstance(e, (json.JSONDecodeError, KeyError)):
                    error_category = "invalid_response"
                else:
                    error_category = meta.get("error_category") or "unknown"
                if self.interaction_collector and log_category:
                    self.interaction_collector.record(LLMInteractionEntry(
                        category=log_category,
                        method=log_method,
                        step=f"{log_step}_retry",
                        prompt=prompt,
                        raw_response=raw,
                        parsed_value=None,
                        error=f"{type(e).__name__}: {e}",
                        attempt=attempt + 1,
                        persona_id=self.persona_id,
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

    def _build_context_block(self, resolved: dict) -> str:
        if not resolved:
            return "This is the first category. Use the system instruction as context."
        return "\n".join(f"{k}: {v}" for k, v in resolved.items())

    def _is_numeric_category(self, category_schema: dict) -> bool:
        return isinstance(category_schema, dict) and "min" in category_schema and "max" in category_schema

    @staticmethod
    def _schema_value(category_schema: dict) -> dict:
        num_type = "integer" if category_schema.get("type") == "integer" else "number"
        value_type = num_type if ("min" in category_schema and "max" in category_schema) else "string"
        return {
            "type": "object",
            "properties": {"value": {"type": value_type}},
            "required": ["value"],
        }

    @staticmethod
    def _schema_candidates(category_schema: dict) -> dict:
        item_type = "number" if ("min" in category_schema and "max" in category_schema) else "string"
        return {
            "type": "object",
            "properties": {"candidates": {"type": "array", "items": {"type": item_type}}},
            "required": ["candidates"],
        }

    @staticmethod
    def _schema_weights() -> dict:
        return {
            "type": "object",
            "properties": {"weights": {"type": "array", "items": {"type": "number"}}},
            "required": ["weights"],
        }

    @staticmethod
    def _schema_distribution() -> dict:
        return {
            "type": "object",
            "properties": {
                "distribution": {"type": "string", "enum": ["normal", "uniform", "beta"]},
                "mean": {"type": "number"},
                "std": {"type": "number"},
            },
            "required": ["distribution"],
        }

    def _build_pick_prompt(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> str:
        context = self._build_context_block(resolved)
        description = category_schema.get("description", "")
        if self._is_numeric_category(category_schema):
            num_type = "integer" if category_schema.get("type") == "integer" else "number"
            return (
                f"Context:\n{context}\n\n"
                f"Given the context above, pick a single {num_type} for '{category_name}' "
                f"between {category_schema['min']} and {category_schema['max']}. "
                f"{description} "
                f'Return JSON: {{"value": <number>}}. No explanation.'
            )
        return (
            f"Context:\n{context}\n\n"
            f"Given the context above, pick a single appropriate value for '{category_name}'. "
            f"{description} "
            f'Return JSON: {{"value": "<your choice>"}}. No explanation.'
        )

    def _build_enumerate_prompt(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> str:
        context = self._build_context_block(resolved)
        description = category_schema.get("description", "")
        if self._is_numeric_category(category_schema):
            return (
                f"Context:\n{context}\n\n"
                f"Given the context above, list all plausible candidate numbers for '{category_name}' "
                f"between {category_schema['min']} and {category_schema['max']}. "
                f"{description} "
                f'Return JSON: {{"candidates": [n1, n2, ...]}}.'
            )
        return (
            f"Context:\n{context}\n\n"
            f"Given the context above, list up to 20 of the most plausible candidate values "
            f"for '{category_name}' given the context. "
            f"Prioritize the most realistic and likely options. "
            f"{description} "
            f'Return JSON: {{"candidates": ["value1", ...]}}. No duplicates.'
        )

    def _build_evaluate_prompt(
        self,
        category_name: str,
        candidates: list,
        resolved: dict,
        system_instruction: str,
    ) -> str:
        context = self._build_context_block(resolved)
        n = len(candidates)
        return (
            f"Context:\n{context}\n\n"
            f"Assign probability weights to these {n} candidates for '{category_name}' given the context. "
            f"Weights must sum to 1.0. "
            f"You MUST return exactly {n} weights. "
            f"Return JSON: {{\"weights\": [0.x, 0.y, ...]}} in the same order as candidates: {candidates}."
        )

    def _build_select_prompt(
        self,
        category_name: str,
        candidates: list,
        resolved: dict,
        system_instruction: str,
    ) -> str:
        context = self._build_context_block(resolved)
        return (
            f"Context:\n{context}\n\n"
            f"From the following candidates for '{category_name}', pick the single most appropriate value "
            f"given the context. "
            f'Return JSON: {{"value": "<chosen>"}}. '
            f"Candidates: {candidates}."
        )

    def _build_numeric_distribution_prompt(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> str:
        context = self._build_context_block(resolved)
        description = category_schema.get("description", "")
        return (
            f"Context:\n{context}\n\n"
            f"Specify a probability distribution for '{category_name}' between "
            f"{category_schema['min']} and {category_schema['max']} given the context. "
            f"{description} "
            f'Return JSON: {{"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>}} '
            f"(mean/std only for normal). Use 'uniform' for no preference."
        )

    def _normalize_weights(self, weights: list[float], category_name: str) -> list[float]:
        total = sum(weights)
        if abs(total) < 1e-9:
            logging.warning(
                f"Weights for '{category_name}' sum to zero — will retry."
            )
            return weights
        if abs(total - 1.0) > 1e-6:
            logging.warning(
                f"Weights for '{category_name}' sum to {total:.4f}, not 1.0 — normalizing."
            )
            weights = [w / total for w in weights]
        return weights

    def _reconcile_weight_count(
        self,
        weights: list[float],
        candidates: list,
        category_name: str,
    ) -> list[float] | None:
        n_weights, n_candidates = len(weights), len(candidates)
        if n_weights == n_candidates:
            return weights

        if not weights or any(w < 0 for w in weights) or all(w == 0 for w in weights):
            return None

        tolerance = int(n_candidates * _WEIGHT_COUNT_TOLERANCE_RATIO)
        diff = abs(n_weights - n_candidates)
        if diff > tolerance:
            return None

        if n_weights < n_candidates:
            pad_value = min(weights)
            weights = weights + [pad_value] * (n_candidates - n_weights)
            logging.warning(
                f"Padded {diff} missing weight(s) for '{category_name}' "
                f"({n_weights} -> {n_candidates}) with min-weight {pad_value:.4f}."
            )
        else:
            weights = weights[:n_candidates]
            logging.warning(
                f"Truncated {diff} excess weight(s) for '{category_name}' "
                f"({n_weights} -> {n_candidates})."
            )

        return self._normalize_weights(weights, category_name)

    def _process_pick(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> Any:
        prompt = self._build_pick_prompt(category_name, category_schema, resolved, system_instruction)
        value = self._call_llm_json(
            prompt, system_instruction,
            expected_key="value",
            response_schema=self._schema_value(category_schema),
            log_category=category_name, log_method="pick", log_step="pick",
        )
        if self._is_numeric_category(category_schema):
            value = max(category_schema["min"], min(category_schema["max"], float(value)))
            if category_schema.get("type") == "integer":
                value = int(round(value))
        return value

    def _process_generate_pick(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> Any:
        enum_prompt = self._build_enumerate_prompt(category_name, category_schema, resolved, system_instruction)
        candidates = self._call_llm_json(
            enum_prompt, system_instruction,
            expected_key="candidates",
            response_schema=self._schema_candidates(category_schema),
            log_category=category_name, log_method="generate_pick", log_step="enumerate",
        )

        sel_prompt = self._build_select_prompt(category_name, candidates, resolved, system_instruction)
        value = self._call_llm_json(
            sel_prompt, system_instruction,
            expected_key="value",
            response_schema=self._schema_value(category_schema),
            log_category=category_name, log_method="generate_pick", log_step="select",
        )

        if self._is_numeric_category(category_schema):
            value = max(category_schema["min"], min(category_schema["max"], float(value)))
            if category_schema.get("type") == "integer":
                value = int(round(value))
        return value

    def _process_generate_evaluate_pick(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> Any:
        enum_prompt = self._build_enumerate_prompt(category_name, category_schema, resolved, system_instruction)
        candidates = self._call_llm_json(
            enum_prompt, system_instruction,
            expected_key="candidates",
            response_schema=self._schema_candidates(category_schema),
            log_category=category_name, log_method="generate_evaluate_pick", log_step="enumerate",
        )
        if len(candidates) > 25:
            logging.warning(f"Truncating {len(candidates)} candidates to 25 for '{category_name}'.")
            candidates = candidates[:25]

        reconcile_attempts = max_attempts(self.retry_until_success, _DEFAULT_WEIGHT_RECONCILE_ATTEMPTS)
        attempt = 0
        while True:
            attempt += 1
            eval_prompt = self._build_evaluate_prompt(category_name, candidates, resolved, system_instruction)
            weights = self._call_llm_json(
                eval_prompt, system_instruction,
                expected_key="weights",
                response_schema=self._schema_weights(),
                log_category=category_name, log_method="generate_evaluate_pick", log_step="evaluate",
            )
            weights = self._normalize_weights(weights, category_name)
            reconciled = self._reconcile_weight_count(weights, candidates, category_name)
            if reconciled is not None:
                weights = reconciled
                break
            tolerance = int(len(candidates) * _WEIGHT_COUNT_TOLERANCE_RATIO)
            if attempt >= reconcile_attempts:
                raise ValueError(
                    f"Weight/candidate count mismatch for '{category_name}' after {attempt} attempts: "
                    f"{len(weights)} weights for {len(candidates)} candidates."
                )
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt}/{reconcile_attempts}): {len(weights)} weights for "
                f"{len(candidates)} candidates (exceeds tolerance of {tolerance}). Retrying."
            )

        sel_prompt = self._build_select_prompt(category_name, candidates, resolved, system_instruction)
        value = self._call_llm_json(
            sel_prompt, system_instruction,
            expected_key="value",
            response_schema=self._schema_value(category_schema),
            log_category=category_name, log_method="generate_evaluate_pick", log_step="select",
        )

        if self._is_numeric_category(category_schema):
            value = max(category_schema["min"], min(category_schema["max"], float(value)))
            if category_schema.get("type") == "integer":
                value = int(round(value))
        return value

    def _process_generate_evaluate_random_pick(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> Any:
        if self._is_numeric_category(category_schema):
            dist_prompt = self._build_numeric_distribution_prompt(
                category_name, category_schema, resolved, system_instruction
            )
            spec = self._call_llm_json(
                dist_prompt, system_instruction,
                response_schema=self._schema_distribution(),
                log_category=category_name, log_method="generate_evaluate_random_pick", log_step="distribution",
            )
            lo, hi = category_schema["min"], category_schema["max"]
            distribution = spec.get("distribution", "uniform")

            if distribution == "normal":
                mean = float(spec.get("mean", (lo + hi) / 2))
                std = float(spec.get("std", (hi - lo) / 6))
                raw = np.random.normal(mean, std)
            elif distribution == "beta":
                # Map beta(2,2) to [lo, hi] as a reasonable default when no alpha/beta given
                alpha = float(spec.get("alpha", 2))
                beta = float(spec.get("beta", 2))
                raw = lo + np.random.beta(alpha, beta) * (hi - lo)
            else:
                raw = np.random.uniform(lo, hi)

            value = max(lo, min(hi, float(raw)))
            if category_schema.get("type") == "integer":
                value = int(round(value))
            return value

        # Categorical path
        enum_prompt = self._build_enumerate_prompt(category_name, category_schema, resolved, system_instruction)
        candidates = self._call_llm_json(
            enum_prompt, system_instruction,
            expected_key="candidates",
            response_schema=self._schema_candidates(category_schema),
            log_category=category_name, log_method="generate_evaluate_random_pick", log_step="enumerate",
        )
        if len(candidates) > 25:
            logging.warning(f"Truncating {len(candidates)} candidates to 25 for '{category_name}'.")
            candidates = candidates[:25]

        reconcile_attempts = max_attempts(self.retry_until_success, _DEFAULT_WEIGHT_RECONCILE_ATTEMPTS)
        attempt = 0
        while True:
            attempt += 1
            eval_prompt = self._build_evaluate_prompt(category_name, candidates, resolved, system_instruction)
            weights = self._call_llm_json(
                eval_prompt, system_instruction,
                expected_key="weights",
                response_schema=self._schema_weights(),
                log_category=category_name, log_method="generate_evaluate_random_pick", log_step="evaluate",
            )
            weights = self._normalize_weights(weights, category_name)
            reconciled = self._reconcile_weight_count(weights, candidates, category_name)
            if reconciled is not None:
                weights = reconciled
                break
            tolerance = int(len(candidates) * _WEIGHT_COUNT_TOLERANCE_RATIO)
            if attempt >= reconcile_attempts:
                raise ValueError(
                    f"Weight/candidate count mismatch for '{category_name}' after {attempt} attempts: "
                    f"{len(weights)} weights for {len(candidates)} candidates."
                )
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt}/{reconcile_attempts}): {len(weights)} weights for "
                f"{len(candidates)} candidates (exceeds tolerance of {tolerance}). Retrying."
            )

        return random.choices(candidates, weights=weights, k=1)[0]

    def generate_identity(self, prompt_file: str, **kwargs) -> tuple[dict, dict]:
        """
        Loads the flat schema and strategy file, resolves the DAG, and processes
        each category in topological order according to its declared method.
        Returns a flat dict.
        """
        strategy_file: str = kwargs.get("strategy_file")
        if not strategy_file:
            raise ValueError("'strategy_file' must be provided as a kwarg.")

        category_config, context_mode = self._load_strategy(strategy_file)

        if any("mode" in cfg for cfg in category_config.values()):
            raise ValueError(
                "Strategy file uses deprecated 'mode' key. Please update to 'method' key "
                "with new method names: pick, generate_pick, generate_evaluate_pick, "
                "generate_evaluate_random_pick."
            )

        flat_schema = self._load_flat_schema(prompt_file)
        schema_categories: dict = flat_schema.get("categories", {})
        system_instruction: str = "\n".join(flat_schema.get("instruction", []))

        strategy_keys = set(category_config.keys())
        schema_keys = set(schema_categories.keys())
        missing_in_schema = strategy_keys - schema_keys
        if missing_in_schema:
            raise ValueError(f"Strategy declares categories not in schema: {missing_in_schema}")
        missing_in_strategy = schema_keys - strategy_keys
        if missing_in_strategy:
            logging.warning(
                f"Schema has categories not declared in strategy (will be skipped): {missing_in_strategy}"
            )

        ordered_categories = self._build_dag(category_config)

        resolved: dict = {}
        for category_name in ordered_categories:
            cfg = category_config[category_name]
            method: str = cfg.get("method", "")
            category_schema = schema_categories[category_name]

            # Under ``context: none`` the prompt sees no prior-attribute values;
            # ``resolved`` is still accumulated below (only what the prompt sees
            # changes, not DAG order, clamping, or the returned persona).
            context_view = {} if context_mode == "none" else resolved

            try:
                if method == "pick":
                    value = self._process_pick(
                        category_name, category_schema, context_view, system_instruction
                    )
                elif method == "generate_pick":
                    value = self._process_generate_pick(
                        category_name, category_schema, context_view, system_instruction
                    )
                elif method == "generate_evaluate_pick":
                    value = self._process_generate_evaluate_pick(
                        category_name, category_schema, context_view, system_instruction
                    )
                elif method == "generate_evaluate_random_pick":
                    value = self._process_generate_evaluate_random_pick(
                        category_name, category_schema, context_view, system_instruction
                    )
                else:
                    raise ValueError(
                        f"Unknown method '{method}' for category '{category_name}'. "
                        f"Valid: pick, generate_pick, generate_evaluate_pick, generate_evaluate_random_pick."
                    )
            except Exception as e:
                logging.error(
                    "Category '%s' (method=%s) failed after resolving %d/%d categories: %s",
                    category_name, method, len(resolved), len(ordered_categories), e,
                )
                raise

            resolved[category_name] = value
            logging.debug(f"{category_name} ({method}) -> {value}")

        logging.info(f"Configurable identity generation complete ({len(resolved)} categories).")
        return resolved, {}

    def load_identity(self, identity_path: str) -> tuple[dict, dict]:
        if not os.path.exists(identity_path):
            raise FileNotFoundError(f"Identity file not found: {identity_path}")
        with open(identity_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                logging.info(f"Flat identity loaded from {identity_path}")
                return data, {}
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in identity file: {e}")


def resolve_category_order(strategy_file: str) -> list[str]:
    """Return the category order a run of ``strategy_file`` will resolve in.

    The provenance accessor for callers that need the order without generating a
    persona (the parallel runner records it in ``run_metadata.json``). It reuses the
    generator's own loader and DAG builder, so the recorded order is the executed
    one by construction rather than by a second, drifting implementation. Raises the
    same ``ValueError``s as generation would, before any LLM call is made.
    """
    category_config, _ = IdentityGeneratorConfigurable._load_strategy(strategy_file)
    return IdentityGeneratorConfigurable._build_dag(category_config)

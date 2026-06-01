import json
import logging
import os
import random
import re
from collections import deque
from typing import Any

import numpy as np

from population_synth.clients.llm_protocol import LLMClient

from .base_identity_generator import BaseIdentityGenerator
from .llm_interaction_log import LLMInteractionEntry

_WEIGHT_COUNT_TOLERANCE_RATIO = 0.1


class IdentityGeneratorConfigurable(BaseIdentityGenerator):
    """Identity generator using an explicit per-category dependency DAG."""

    def __init__(self, client: LLMClient):
        super().__init__(client)

    def _load_flat_schema(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Flat schema file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in flat schema file: {e}")

    def _load_strategy(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Strategy file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in strategy file: {e}")
        categories = data.get("categories")
        if not categories or not isinstance(categories, dict):
            raise ValueError(f"Strategy file must contain a 'categories' dict: {filepath}")
        return categories

    def _build_dag(self, category_config: dict) -> list[str]:
        """
        Validates the dependency graph and returns categories in topological order
        using Kahn's algorithm. Raises ValueError on undeclared references or cycles.
        """
        declared = set(category_config.keys())

        for cat, cfg in category_config.items():
            for dep in cfg.get("depends_on", []):
                if dep not in declared:
                    raise ValueError(
                        f"Category '{cat}' declares dependency on '{dep}', "
                        f"which is not declared in category_config."
                    )

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
            participants = [cat for cat in declared if cat not in ordered]
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
        for attempt in range(3):
            raw = ""
            try:
                raw = self.client.generate_content(
                    prompt, system_instruction=system_instruction, **extra
                )
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
                    ))
                return value
            except (json.JSONDecodeError, KeyError, RuntimeError) as e:
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
                    ))
                last_error = e
                raw_snippet = raw[:500] if raw else "(no response)"
                logging.warning(
                    "LLM JSON parse attempt %d/3 failed (%s): %s\n--- RAW RESPONSE ---\n%s\n--- END ---",
                    attempt + 1, type(e).__name__, e, raw_snippet,
                )
        raise ValueError(f"LLM returned invalid or incomplete JSON after 3 retries. Last error: {last_error}")

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
            if not self.retry_until_success and attempt >= 3:
                raise ValueError(
                    f"Weight/candidate count mismatch for '{category_name}' after {attempt} attempts: "
                    f"{len(weights)} weights for {len(candidates)} candidates."
                )
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt}): {len(weights)} weights for {len(candidates)} candidates "
                f"(exceeds tolerance of {tolerance}). Retrying."
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
            if not self.retry_until_success and attempt >= 3:
                raise ValueError(
                    f"Weight/candidate count mismatch for '{category_name}' after {attempt} attempts: "
                    f"{len(weights)} weights for {len(candidates)} candidates."
                )
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt}): {len(weights)} weights for {len(candidates)} candidates "
                f"(exceeds tolerance of {tolerance}). Retrying."
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

        category_config = self._load_strategy(strategy_file)

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

            try:
                if method == "pick":
                    value = self._process_pick(
                        category_name, category_schema, resolved, system_instruction
                    )
                elif method == "generate_pick":
                    value = self._process_generate_pick(
                        category_name, category_schema, resolved, system_instruction
                    )
                elif method == "generate_evaluate_pick":
                    value = self._process_generate_evaluate_pick(
                        category_name, category_schema, resolved, system_instruction
                    )
                elif method == "generate_evaluate_random_pick":
                    value = self._process_generate_evaluate_random_pick(
                        category_name, category_schema, resolved, system_instruction
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

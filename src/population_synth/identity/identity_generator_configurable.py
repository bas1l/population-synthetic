import json
import logging
import os
import random
import re
from collections import deque
from typing import Any

import numpy as np

from population_synth.clients.gemini_client import GeminiClient

from .base_identity_generator import BaseIdentityGenerator


class IdentityGeneratorConfigurable(BaseIdentityGenerator):
    """Identity generator using an explicit per-category dependency DAG."""

    def __init__(self, client: GeminiClient):
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

    def _call_llm_json(self, prompt: str, system_instruction: str) -> dict | list:
        """Calls LLM, strips markdown fences, parses JSON. Retries up to 3 times."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                raw = self.client.generate_content(
                    prompt, system_instruction=system_instruction
                )
                text = raw.strip()
                # Strip markdown code fences if present
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                return json.loads(text)
            except (json.JSONDecodeError, RuntimeError) as e:
                last_error = e
                logging.warning(f"LLM JSON parse attempt {attempt + 1}/3 failed: {e}")
        raise ValueError(f"LLM returned invalid JSON after 3 retries. Last error: {last_error}")

    def _build_context_block(self, resolved: dict) -> str:
        if not resolved:
            return "No prior context."
        return "\n".join(f"{k}: {v}" for k, v in resolved.items())

    def _is_numeric_category(self, category_schema: dict) -> bool:
        return isinstance(category_schema, dict) and "min" in category_schema and "max" in category_schema

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
            f"Given the context above, list an exhaustive set of all plausible candidate values "
            f"for '{category_name}' given the context. "
            f"Include every realistic option — do not limit or truncate the list. "
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
        return (
            f"Context:\n{context}\n\n"
            f"Assign probability weights to these candidates for '{category_name}' given the context. "
            f"Weights must sum to 1.0. "
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
        if abs(total - 1.0) > 1e-6:
            logging.warning(
                f"Weights for '{category_name}' sum to {total:.4f}, not 1.0 — normalizing."
            )
            weights = [w / total for w in weights]
        return weights

    def _process_pick(
        self,
        category_name: str,
        category_schema: dict,
        resolved: dict,
        system_instruction: str,
    ) -> Any:
        prompt = self._build_pick_prompt(category_name, category_schema, resolved, system_instruction)
        result = self._call_llm_json(prompt, system_instruction)
        value = result["value"]
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
        candidates = self._call_llm_json(enum_prompt, system_instruction)["candidates"]

        sel_prompt = self._build_select_prompt(category_name, candidates, resolved, system_instruction)
        value = self._call_llm_json(sel_prompt, system_instruction)["value"]

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
        candidates = self._call_llm_json(enum_prompt, system_instruction)["candidates"]
        if len(candidates) > 50:
            logging.warning(f"Truncating {len(candidates)} candidates to 50 for '{category_name}'.")
            candidates = candidates[:50]

        for attempt in range(10):
            eval_prompt = self._build_evaluate_prompt(category_name, candidates, resolved, system_instruction)
            weights = self._call_llm_json(eval_prompt, system_instruction)["weights"]
            weights = self._normalize_weights(weights, category_name)
            if len(weights) == len(candidates):
                break
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt + 1}/10): {len(weights)} weights for {len(candidates)} candidates. Retrying."
            )
        else:
            raise ValueError(
                f"Weight/candidate count mismatch for '{category_name}' after 10 attempts: "
                f"{len(weights)} weights for {len(candidates)} candidates."
            )

        sel_prompt = self._build_select_prompt(category_name, candidates, resolved, system_instruction)
        value = self._call_llm_json(sel_prompt, system_instruction)["value"]

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
            spec = self._call_llm_json(dist_prompt, system_instruction)
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
        candidates = self._call_llm_json(enum_prompt, system_instruction)["candidates"]
        if len(candidates) > 50:
            logging.warning(f"Truncating {len(candidates)} candidates to 50 for '{category_name}'.")
            candidates = candidates[:50]

        for attempt in range(10):
            eval_prompt = self._build_evaluate_prompt(category_name, candidates, resolved, system_instruction)
            weights = self._call_llm_json(eval_prompt, system_instruction)["weights"]
            weights = self._normalize_weights(weights, category_name)
            if len(weights) == len(candidates):
                break
            logging.warning(
                f"Weight/candidate mismatch for '{category_name}' "
                f"(attempt {attempt + 1}/10): {len(weights)} weights for {len(candidates)} candidates. Retrying."
            )
        else:
            raise ValueError(
                f"Weight/candidate count mismatch for '{category_name}' after 10 attempts: "
                f"{len(weights)} weights for {len(candidates)} candidates."
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

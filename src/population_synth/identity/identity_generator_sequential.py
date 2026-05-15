import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, Optional, Tuple

from population_synth.clients.gemini_client import GeminiClient

from .base_identity_generator import BaseIdentityGenerator


class SchemaProbabilityRefiner:
    """
    Component Responsibility: Infrastructure & Networking.
    Handles the interaction with the LLM to dynamically update schema probabilities based on context.
    """
    def __init__(self, client: GeminiClient):
        self.client = client

    def _clean_json_response(self, response_text: str) -> str:
        """Cleans Markdown formatting (backticks) from LLM JSON responses."""
        cleaned = re.sub(r'^```json\s*', '', response_text, flags=re.MULTILINE | re.IGNORECASE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def update_probabilities(
        self, context: dict, target_schema: dict, level_name: str, system_instruction: str,
    ) -> dict:
        """
        Requests the LLM to update probability weights in the target schema based on the provided context.
        Includes retry logic for robustness.
        """
        prompt = (
            f"Current Persona Context:\n{json.dumps(context, indent=2)}\n\n"
            f"Target Schema to Update ({level_name}):\n{json.dumps(target_schema, indent=2)}"
        )

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                logging.info(f"Refining probabilities for {level_name} (Attempt {attempt + 1})...")
                response = self.client.generate_content(prompt, system_instruction=system_instruction)
                cleaned = self._clean_json_response(response)

                updated_schema = json.loads(cleaned)
                if not isinstance(updated_schema, dict):
                     raise ValueError("Response is not a valid JSON dictionary.")

                return updated_schema

            except (json.JSONDecodeError, ValueError, RuntimeError) as e:
                if attempt == max_retries:
                    logging.error(
                        "Failed to update probabilities for %s: %s. "
                        "Proceeding with default weights.", level_name, e,
                    )
                    return target_schema

                delay = (base_delay * (2 ** attempt)) + random.uniform(0, 0.5)
                time.sleep(delay)

        return target_schema

class RecursiveFormatter:
    """
    Component Responsibility: Presentation / View.
    Recursively converts dictionary structures into human-readable string formats.
    """
    @staticmethod
    def format(data: Any, indent_level: int = 0) -> str:
        indent = "  " * indent_level
        output = []

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    output.append(f"{indent}{key}:")
                    output.append(RecursiveFormatter.format(value, indent_level + 1))
                else:
                    output.append(f"{indent}{key}: {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    output.append(f"{indent}-")
                    output.append(RecursiveFormatter.format(item, indent_level + 1))
                else:
                    output.append(f"{indent}- {item}")
        else:
            return f"{indent}{data}"

        return "\n".join(output)

class IdentityGeneratorSequential(BaseIdentityGenerator):
    """
    Component Responsibility: Orchestration (Controller).
    Cohesion: High. Delegates specific logic to Refiner and Formatter helpers.
    Coupling: Low. Logic is loosely coupled via dependency injection and helpers.
    """

    def __init__(self, client: GeminiClient):
        super().__init__(client)
        self.refiner = SchemaProbabilityRefiner(client)
        self.formatter = RecursiveFormatter()
        self.last_identity: Optional[Dict[str, Any]] = None
        self.last_formatted_identity: Optional[Dict[str, str]] = None

    def _load_schema(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Schema file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in schema file: {e}")

    def _select_attributes(self, node: Any) -> Any:
        """
        Business Logic: Traverses the schema and selects values based on types or probability weights.
        """
        result = {}
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "description":
                    continue

                # Case 1: Numeric Range (Integer or Float)
                if isinstance(value, dict) and "min" in value and "max" in value:
                    if value.get("type") == "integer":
                        result[key] = random.randint(value["min"], value["max"])
                    else:
                        result[key] = random.uniform(value["min"], value["max"])

                # Case 2: Nested Dictionary
                elif isinstance(value, dict):
                    result[key] = self._select_attributes(value)

                # Case 3: Weighted List Selection
                elif isinstance(value, list):
                    try:
                        choices = [item.get('value') for item in value]
                        weights = [item.get('probability', 0) for item in value]

                        # Fallback for zero/invalid sums
                        if sum(weights) <= 0:
                             weights = [1] * len(choices)

                        result[key] = random.choices(choices, weights=weights, k=1)[0]
                    except (KeyError, IndexError) as e:
                        logging.warning(f"Selection error for '{key}': {e}. Random fallback.")
                        if value:
                             result[key] = random.choice(value).get('value')
                        else:
                             result[key] = None

                # Case 4: Static Value
                else:
                    result[key] = value
            return result
        return node

    def generate_identity(self, landscape_file: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Generates a new identity based on the landscape schema.
        Dynamically detects levels to satisfy OCP (Open/Closed Principle).
        """
        full_schema = self._load_schema(landscape_file)

        if "instruction" not in full_schema:
            raise ValueError(f"The landscape file '{landscape_file}' is missing 'instruction'.")

        system_instruction = "\n".join(full_schema["instruction"])

        identity_result = {}
        formatted_levels = {}

        # Determine root for iteration
        root = full_schema.get("persona_schema_hierarchical", full_schema)

        # Logic: Robust Sort
        # Extracts the integer suffix (e.g., "level_10" -> 10) to ensure correct numerical order
        level_keys = [k for k in root.keys() if k.startswith("level_")]
        sorted_levels = sorted(
            level_keys,
            key=lambda x: int(x.split('_')[-1]) if x.split('_')[-1].isdigit() else x
        )

        if not sorted_levels:
            logging.warning("No keys starting with 'level_' found. Processing root keys directly.")
            sorted_levels = list(root.keys())

        # Main Generation Loop
        for i, level_key in enumerate(sorted_levels):
            level_schema = root[level_key]

            # Step 1: Probability Refinement (if previous context exists)
            if i > 0:
                # Gather context from all previous levels
                context_so_far = {k: identity_result[k] for k in sorted_levels[:i] if k in identity_result}
                level_schema = self.refiner.update_probabilities(
                    context_so_far, level_schema, level_key, system_instruction
                )

            # Step 2: Attribute Selection
            selection = self._select_attributes(level_schema)
            identity_result[level_key] = selection

            # Step 3: Inject age_group after level_1 is sampled
            if level_key == "level_1":
                age = identity_result["level_1"].get("core_demographics", {}).get("age")
                if age is not None:
                    age_bins = [(18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74), (75, 85)]
                    age_group = next(
                        (f"{lo}-{hi}" for lo, hi in age_bins if lo <= age <= hi),
                        f"{age_bins[-1][0]}-{age_bins[-1][1]}",
                    )
                    identity_result["level_1"]["core_demographics"]["age_group"] = age_group

            # Step 4: Formatting
            formatted_levels[level_key] = self.formatter.format(selection)

        # Post-sampling conditional overrides
        l3 = identity_result.get("level_3", {}).get("professional_functional", {})
        if l3.get("employment_status") != "Employed":
            l3["industry_sector"] = "Not Applicable"
            l3["employment_type"] = "Not Applicable"
        else:
            # Employed persona: if LLM assigned "Not Applicable", resample from valid options
            l3_schema = root.get("level_3", {}).get("professional_functional", {})
            for field in ("industry_sector", "employment_type"):
                if l3.get(field) == "Not Applicable":
                    options = [
                        o for o in l3_schema.get(field, [])
                        if isinstance(o, dict) and o.get("value") != "Not Applicable"
                    ]
                    if options:
                        weights = [o.get("probability", 1) for o in options]
                        l3[field] = random.choices([o["value"] for o in options], weights=weights, k=1)[0]

        l1_origin = identity_result.get("level_1", {}).get("origin_geography", {})
        if l1_origin.get("birth_location") == "Native (Born in Sweden)":
            l1_origin["birth_country_detail"] = "Sweden"

        self.last_identity = identity_result
        self.last_formatted_identity = formatted_levels

        logging.info("Identity generation complete.")
        return identity_result, formatted_levels

    def load_identity(self, filepath: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Loads an identity from persistence and regenerates the formatted view.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Identity file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                self.last_identity = data

                # Re-run formatter logic on loaded data
                formatted_levels = {k: self.formatter.format(v) for k, v in data.items()}
                self.last_formatted_identity = formatted_levels

                logging.info(f"Identity loaded from {filepath}")
                return data, formatted_levels
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in identity file: {e}")

"""One class per generation method, each resolving one attribute.

Defines the :class:`Category` ABC and its four concrete methods -- ``pick``,
``generate_pick``, ``generate_evaluate_pick`` and ``generate_evaluate_random_pick``.
These five methods (counting the sequential family removed earlier) are the
primary comparison axis of the benchmark, so each is a class of its own: it can be
constructed, prompted and asserted on in isolation, which the previous ``if/elif``
chain over a ``method`` string made impossible.

A category knows its name, its schema fragment and the categories it waits for. It
does **not** know where the persona lives, how the persona is serialised, what the
other categories resolved, or which client is behind the prompt. It receives an
already-rendered context block and a :class:`~.resolution_context.ResolutionContext`,
and returns a scalar.

:data:`_METHOD_MAP` is a structural constant, in the same class as dataset ids and
label maps: it enumerates the methods this code implements, not a set of values a
user configures. :func:`build_categories` resolves every method through it **before
the walk starts**, so a typo in a strategy YAML fails on the first persona's first
instant rather than fifteen categories in -- where, under resume, it would fail
again on every retry round having re-paid nothing.
"""

from __future__ import annotations

import json
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Mapping, Sequence

import numpy as np

from population_synthetic.clients.retry_policy import max_attempts

from .resolution_context import ResolutionContext

# Structural constants of the generation methods themselves, not tunables:
# how far a returned weight vector may differ in length from the candidate list
# before the evaluate step is re-asked, how many times it is re-asked without
# ``retry_until_success``, and the ceiling on candidates carried into a weighting
# step (a longer list degrades weight quality faster than it adds coverage).
_WEIGHT_COUNT_TOLERANCE_RATIO = 0.1
_DEFAULT_WEIGHT_RECONCILE_ATTEMPTS = 3
_MAX_WEIGHTED_CANDIDATES = 25


def _normalize_weights(weights: list[float], category_name: str) -> list[float]:
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
    weights: list[float],
    candidates: list,
    category_name: str,
) -> list[float] | None:
    """Pad or truncate a near-miss weight vector, or ``None`` if it is too far off."""
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

    return _normalize_weights(weights, category_name)


def _candidate_probabilities(
    candidates: list,
    weights: list[float],
    category_name: str,
) -> dict[str, float]:
    """Pair each candidate with its probability, summing any duplicate candidates.

    The enumerate prompt asks for no duplicates but nothing enforces it, and a dict
    rendering would otherwise let a repeated candidate's weight vanish. Summing is
    the consistent reading -- the probability of a *value* being chosen is the total
    mass its entries carry, which is also what ``random.choices`` effectively does in
    the ``generate_evaluate_random_pick`` path.
    """
    probabilities: dict[str, float] = {}
    for candidate, weight in zip(candidates, weights):
        key = str(candidate)
        probabilities[key] = probabilities.get(key, 0.0) + float(weight)
    if len(probabilities) < len(candidates):
        logging.warning(
            f"Collapsed {len(candidates) - len(probabilities)} duplicate candidate(s) "
            f"for '{category_name}' when pairing with weights ({len(candidates)} -> "
            f"{len(probabilities)}); duplicate weights were summed."
        )
    # Rounded for prompt legibility only -- the stored weights are untouched.
    return {key: round(value, 4) for key, value in probabilities.items()}


class Category(ABC):
    """One attribute of a persona, resolved by one generation method."""

    #: The strategy YAML's ``method`` token this class implements. Also the
    #: ``method`` label written to the telemetry log for every call it makes.
    method: ClassVar[str]

    def __init__(self, name: str, schema: dict, depends_on: Sequence[str] = ()) -> None:
        """
        Args:
            name: The attribute this category resolves; the key it occupies in the
                persona and the ``category`` label in the telemetry log.
            schema: This attribute's fragment of the flat schema -- its
                ``description`` and, for a numeric attribute, ``min``/``max``/``type``.
            depends_on: The categories that must resolve first. Scheduling only:
                the walk has already applied it by the time :meth:`resolve` is called,
                and it is retained for provenance rather than re-checked here.
        """
        self.name = name
        self.schema = schema
        self.depends_on = tuple(depends_on)

    @abstractmethod
    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float:
        """Produce this category's value.

        Args:
            context: The already-rendered context block. A category never sees the
                dict it was rendered from, so it cannot read another category's value
                or accidentally reorder the block.
            ctx: The call seam. Every LLM interaction goes through it.
        """

    # -- schema-derived helpers ----------------------------------------------

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.schema, dict) and "min" in self.schema and "max" in self.schema

    @property
    def description(self) -> str:
        return self.schema.get("description", "")

    def _clamp(self, value: Any) -> Any:
        """Force a numeric answer back inside its declared bounds; pass others through.

        The model is asked for a bounded number but nothing enforces the bound, so
        an out-of-range answer is clamped rather than retried -- a value one year
        past a ceiling is a rounding disagreement, not a failed generation.
        """
        if not self.is_numeric:
            return value
        value = max(self.schema["min"], min(self.schema["max"], float(value)))
        if self.schema.get("type") == "integer":
            value = int(round(value))
        return value

    def _schema_value(self) -> dict:
        num_type = "integer" if self.schema.get("type") == "integer" else "number"
        value_type = num_type if ("min" in self.schema and "max" in self.schema) else "string"
        return {
            "type": "object",
            "properties": {"value": {"type": value_type}},
            "required": ["value"],
        }

    # -- prompts --------------------------------------------------------------

    def _pick_prompt(self, context: str) -> str:
        description = self.description
        if self.is_numeric:
            num_type = "integer" if self.schema.get("type") == "integer" else "number"
            return (
                f"Context:\n{context}\n\n"
                f"Given the context above, pick a single {num_type} for '{self.name}' "
                f"between {self.schema['min']} and {self.schema['max']}. "
                f"{description} "
                f'Return JSON: {{"value": <number>}}. No explanation.'
            )
        return (
            f"Context:\n{context}\n\n"
            f"Given the context above, pick a single appropriate value for '{self.name}'. "
            f"{description} "
            f'Return JSON: {{"value": "<your choice>"}}. No explanation.'
        )


class _CandidateCategory(Category):
    """Shared enumerate step for the three methods that propose before choosing."""

    def _schema_candidates(self) -> dict:
        item_type = "number" if ("min" in self.schema and "max" in self.schema) else "string"
        return {
            "type": "object",
            "properties": {"candidates": {"type": "array", "items": {"type": item_type}}},
            "required": ["candidates"],
        }

    def _enumerate_prompt(self, context: str) -> str:
        description = self.description
        if self.is_numeric:
            return (
                f"Context:\n{context}\n\n"
                f"Given the context above, list all plausible candidate numbers for '{self.name}' "
                f"between {self.schema['min']} and {self.schema['max']}. "
                f"{description} "
                f'Return JSON: {{"candidates": [n1, n2, ...]}}.'
            )
        return (
            f"Context:\n{context}\n\n"
            f"Given the context above, list up to 20 of the most plausible candidate values "
            f"for '{self.name}' given the context. "
            f"Prioritize the most realistic and likely options. "
            f"{description} "
            f'Return JSON: {{"candidates": ["value1", ...]}}. No duplicates.'
        )

    def _select_prompt(self, context: str, candidates: list, weights: list[float] | None = None) -> str:
        """Build the select-step prompt.

        With *weights* omitted (the ``generate_pick`` path, which computes none), the
        bare candidate list is offered. With *weights* supplied (the
        ``generate_evaluate_pick`` path), each candidate is shown paired with the
        probability the evaluate step assigned it, as a JSON ``value: probability``
        object -- so the weights that call produced actually inform the choice instead of
        being computed and discarded.
        """
        if weights is None:
            return (
                f"Context:\n{context}\n\n"
                f"From the following candidates for '{self.name}', pick the single most appropriate value "
                f"given the context. "
                f'Return JSON: {{"value": "<chosen>"}}. '
                f"Candidates: {candidates}."
            )

        probabilities = _candidate_probabilities(candidates, weights, self.name)
        return (
            f"Context:\n{context}\n\n"
            f"From the following candidates for '{self.name}' -- each paired with the probability "
            f"you assigned it -- pick the single most appropriate value given the context and those "
            f"probabilities. "
            f'Return JSON: {{"value": "<chosen>"}}. '
            f"Candidates: {json.dumps(probabilities, ensure_ascii=False)}."
        )

    def _enumerate(self, context: str, ctx: ResolutionContext) -> list:
        return ctx.call_json(
            self._enumerate_prompt(context),
            expected_key="candidates",
            response_schema=self._schema_candidates(),
            category=self.name, method=self.method, step="enumerate",
        )


class _WeightedCategory(_CandidateCategory):
    """Shared evaluate step for the two methods that weight their candidates."""

    @staticmethod
    def _schema_weights() -> dict:
        return {
            "type": "object",
            "properties": {"weights": {"type": "array", "items": {"type": "number"}}},
            "required": ["weights"],
        }

    def _evaluate_prompt(self, context: str, candidates: list) -> str:
        n = len(candidates)
        return (
            f"Context:\n{context}\n\n"
            f"Assign probability weights to these {n} candidates for '{self.name}' given the context. "
            f"Weights must sum to 1.0. "
            f"You MUST return exactly {n} weights. "
            f"Return JSON: {{\"weights\": [0.x, 0.y, ...]}} in the same order as candidates: {candidates}."
        )

    def _enumerate_capped(self, context: str, ctx: ResolutionContext) -> list:
        candidates = self._enumerate(context, ctx)
        if len(candidates) > _MAX_WEIGHTED_CANDIDATES:
            logging.warning(
                f"Truncating {len(candidates)} candidates to {_MAX_WEIGHTED_CANDIDATES} for '{self.name}'."
            )
            candidates = candidates[:_MAX_WEIGHTED_CANDIDATES]
        return candidates

    def _weigh(self, context: str, ctx: ResolutionContext, candidates: list) -> list[float]:
        """Ask for one weight per candidate, re-asking while the count is unusable."""
        reconcile_attempts = max_attempts(ctx.retry_until_success, _DEFAULT_WEIGHT_RECONCILE_ATTEMPTS)
        attempt = 0
        while True:
            attempt += 1
            weights = ctx.call_json(
                self._evaluate_prompt(context, candidates),
                expected_key="weights",
                response_schema=self._schema_weights(),
                category=self.name, method=self.method, step="evaluate",
            )
            weights = _normalize_weights(weights, self.name)
            reconciled = _reconcile_weight_count(weights, candidates, self.name)
            if reconciled is not None:
                return reconciled
            tolerance = int(len(candidates) * _WEIGHT_COUNT_TOLERANCE_RATIO)
            if attempt >= reconcile_attempts:
                raise ValueError(
                    f"Weight/candidate count mismatch for '{self.name}' after {attempt} attempts: "
                    f"{len(weights)} weights for {len(candidates)} candidates."
                )
            logging.warning(
                f"Weight/candidate mismatch for '{self.name}' "
                f"(attempt {attempt}/{reconcile_attempts}): {len(weights)} weights for "
                f"{len(candidates)} candidates (exceeds tolerance of {tolerance}). Retrying."
            )


class PickCategory(Category):
    """One call: the model names the value outright."""

    method: ClassVar[str] = "pick"

    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float:
        value = ctx.call_json(
            self._pick_prompt(context),
            expected_key="value",
            response_schema=self._schema_value(),
            category=self.name, method=self.method, step="pick",
        )
        return self._clamp(value)


class GeneratePickCategory(_CandidateCategory):
    """Two calls: enumerate plausible candidates, then choose among them."""

    method: ClassVar[str] = "generate_pick"

    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float:
        candidates = self._enumerate(context, ctx)
        value = ctx.call_json(
            self._select_prompt(context, candidates),
            expected_key="value",
            response_schema=self._schema_value(),
            category=self.name, method=self.method, step="select",
        )
        return self._clamp(value)


class GenerateEvaluatePickCategory(_WeightedCategory):
    """Three calls: enumerate, weight, then choose with the weights in view."""

    method: ClassVar[str] = "generate_evaluate_pick"

    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float:
        candidates = self._enumerate_capped(context, ctx)
        weights = self._weigh(context, ctx, candidates)
        value = ctx.call_json(
            self._select_prompt(context, candidates, weights=weights),
            expected_key="value",
            response_schema=self._schema_value(),
            category=self.name, method=self.method, step="select",
        )
        return self._clamp(value)


class GenerateEvaluateRandomPickCategory(_WeightedCategory):
    """Enumerate and weight, then sample -- the model never makes the final choice.

    The only method whose last step is arithmetic rather than a call, and therefore
    the only one that can express a distribution instead of a mode: a numeric
    attribute is drawn from a model-specified distribution, a categorical one from
    the weights as a categorical distribution.
    """

    method: ClassVar[str] = "generate_evaluate_random_pick"

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

    def _numeric_distribution_prompt(self, context: str) -> str:
        description = self.description
        return (
            f"Context:\n{context}\n\n"
            f"Specify a probability distribution for '{self.name}' between "
            f"{self.schema['min']} and {self.schema['max']} given the context. "
            f"{description} "
            f'Return JSON: {{"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>}} '
            f"(mean/std only for normal). Use 'uniform' for no preference."
        )

    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float:
        if self.is_numeric:
            spec = ctx.call_json(
                self._numeric_distribution_prompt(context),
                response_schema=self._schema_distribution(),
                category=self.name, method=self.method, step="distribution",
            )
            lo, hi = self.schema["min"], self.schema["max"]
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
            if self.schema.get("type") == "integer":
                value = int(round(value))
            return value

        # Categorical path
        candidates = self._enumerate_capped(context, ctx)
        weights = self._weigh(context, ctx, candidates)
        return random.choices(candidates, weights=weights, k=1)[0]


# Structural constant: the generation methods this module implements, keyed by the
# token a strategy YAML uses. Not config -- adding an entry means adding a class.
_METHOD_MAP: dict[str, type[Category]] = {
    PickCategory.method: PickCategory,
    GeneratePickCategory.method: GeneratePickCategory,
    GenerateEvaluatePickCategory.method: GenerateEvaluatePickCategory,
    GenerateEvaluateRandomPickCategory.method: GenerateEvaluateRandomPickCategory,
}


def build_category(name: str, config: Mapping[str, Any], schema: dict) -> Category:
    """Construct the class implementing *config*'s declared method.

    Raises:
        ValueError: The strategy declares a method this code does not implement.
    """
    method = config.get("method", "")
    category_class = _METHOD_MAP.get(method)
    if category_class is None:
        raise ValueError(
            f"Unknown method '{method}' for category '{name}'. "
            f"Valid: {', '.join(_METHOD_MAP)}."
        )
    return category_class(name, schema, depends_on=config.get("depends_on", []))


def build_categories(
    order: Sequence[str],
    category_config: Mapping[str, Mapping[str, Any]],
    schema_categories: Mapping[str, dict],
) -> list[Category]:
    """Build every category up front, in resolution order.

    Building the whole list before anything resolves is what makes an unknown
    method a *start-up* failure. The previous dispatch discovered it only when the
    walk reached the offending category, so a run paid for every category before it
    and -- once resume existed -- would have paid again on every retry round.
    """
    return [build_category(name, category_config[name], schema_categories[name]) for name in order]

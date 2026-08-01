"""DAG-driven, per-category configurable identity generation.

Defines ``IdentityGeneratorConfigurable``, a ``BaseIdentityGenerator`` that turns a
strategy YAML and a flat schema into a resolved persona. Its job is assembly, not
resolution: it loads and validates the two config files, builds the dependency
graph (Kahn's algorithm), constructs one ``Category`` per declared attribute, and
hands the result to a ``Persona`` to walk.

Per-category prompts live on ``Category``, the LLM call lives on
``ResolutionContext``, and the walk plus its checkpointing live on ``Persona`` --
so the generation methods that this project compares are each an independently
constructible class rather than a branch of one chain.
"""

import json
import logging
import os
from collections import deque

import yaml

from population_synthetic.clients.llm_protocol import LLMClient

from .base_identity_generator import BaseIdentityGenerator
from .category import build_categories
from .persona import CONTEXT_MODES, Persona
from .resolution_context import ResolutionContext


class IdentityGeneratorConfigurable(BaseIdentityGenerator):
    """Identity generator using an explicit per-category dependency DAG."""

    def __init__(self, client: LLMClient):
        super().__init__(client)
        # Correlation context for exact log<->JSONL joining.  ``persona_id`` is
        # assigned externally by the parallel runner; ``_call_index`` seeds the
        # resolution context's counter and is read back from it after a run, so a
        # generator reused for a second persona never replays an index.
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
        # The modes are enumerated once, on ``Persona``, which is what implements
        # them; validating against that list keeps a new mode from being accepted
        # here and then silently unhandled during the walk.
        if context_mode not in CONTEXT_MODES:
            raise ValueError(
                f"Strategy file has invalid 'context' value {context_mode!r} "
                f"(expected one of {', '.join(CONTEXT_MODES)}): {filepath}"
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

    def _build_resolution_context(self, system_instruction: str) -> ResolutionContext:
        """Bind this generator's client and run-level flags into one call seam.

        A separate method because it is the whole surface a test double needs to
        replace: substituting the context removes the client without touching a
        single prompt, a category or the walk.
        """
        return ResolutionContext(
            self.client,
            system_instruction=system_instruction,
            persona_id=self.persona_id,
            call_index=self._call_index,
            interaction_collector=self.interaction_collector,
            retry_until_success=self.retry_until_success,
            use_structured_output=self.use_structured_output,
        )

    def generate_identity(self, prompt_file: str, **kwargs) -> tuple[dict, dict]:
        """
        Loads the flat schema and strategy file, resolves the DAG, and processes
        each category in topological order according to its declared method.
        Returns a flat dict.

        When a ``PersonaWriter`` is injected, the walk is resumable: it starts from
        the categories the writer's checkpoint already covers and re-checkpoints
        after every category, so an aborted run re-pays for at most one category
        rather than all of them.
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
        # Every method is resolved to a class here, before the first prompt is sent:
        # an unimplemented method is a config error, and a config error must not cost
        # a single LLM call -- least of all on a resumed persona, which would re-pay
        # nothing and fail at the same category on every retry round.
        categories = build_categories(ordered_categories, category_config, schema_categories)

        ctx = self._build_resolution_context(system_instruction)
        persona = Persona(categories, context_mode=context_mode, writer=self.writer)
        try:
            resolved = persona.generate(ctx)
        finally:
            # Read back even when the walk raised: the indices this attempt spent are
            # already in the telemetry log, so a retry on the same generator must
            # continue past them rather than reuse them.
            self._call_index = ctx.call_index

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

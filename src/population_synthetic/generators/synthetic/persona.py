"""The walk over one persona's categories, and the state it accumulates.

Defines :class:`Persona`: an ordered list of :class:`~.category.Category` objects,
a context mode, and an optional :class:`~.persona_writer.PersonaWriter`. It walks
the categories in DAG order, renders the context block each one sees, records the
value it returns, and checkpoints after every category so an aborted run re-pays
for at most one.

**Resume-faithfulness** is the property the walk exists to protect: category K's
rendered prompt after a resume must be byte-identical to the prompt an
uninterrupted run would have produced. It holds because :meth:`_build_context_block`
is a pure function of the resolved dict's *contents and insertion order*, and both
are restored -- the prefix is rebuilt in DAG order and the checkpoint is never
written sorted. Any change that makes the block depend on anything else (a
timestamp, a set, a sorted view) breaks it silently.

The persona knows nothing about where it is stored. Paths, filenames and
serialisation belong to the writer; prompts belong to the categories.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .category import Category
from .persona_writer import PersonaWriter
from .resolution_context import ResolutionContext

# The two context modes a strategy may declare. ``cumulative`` shows every
# attribute resolved so far; ``none`` is the context-free baseline arm. Structural:
# each is implemented below, so a new mode means new code, not new config.
CONTEXT_MODES = ("cumulative", "none")

# Rendered in place of the context block when nothing has been resolved yet.
_EMPTY_CONTEXT = "This is the first category. Use the system instruction as context."


class Persona:
    """One synthetic individual, resolved one category at a time."""

    def __init__(
        self,
        categories: Sequence[Category],
        *,
        context_mode: str,
        writer: PersonaWriter | None = None,
    ) -> None:
        """
        Args:
            categories: The categories to resolve, already in DAG order. The order is
                load-bearing twice over -- it decides what each prompt sees, and it is
                the order the checkpoint's keys are replayed in.
            context_mode: One of :data:`CONTEXT_MODES`.
            writer: Where the checkpoint goes, or ``None`` to resolve in memory and
                persist nothing.

        Raises:
            ValueError: *context_mode* is not one this class implements.
        """
        if context_mode not in CONTEXT_MODES:
            raise ValueError(
                f"Unknown context mode {context_mode!r} (expected one of {', '.join(CONTEXT_MODES)})."
            )
        self._categories = list(categories)
        self._context_mode = context_mode
        self._writer = writer

    @property
    def category_names(self) -> list[str]:
        return [category.name for category in self._categories]

    @property
    def writer(self) -> PersonaWriter | None:
        """The writer this persona checkpoints through, or ``None`` if in-memory.

        Exposed read-only so a caller that obtained the persona from a
        :class:`~.synthetic_population.SyntheticPopulation` can publish and close
        the same files the walk checkpointed into, without a second lookup that
        could disagree about which directory this persona owns. The persona still
        knows nothing about those files -- it only hands back the object it was
        constructed with.
        """
        return self._writer

    def generate(self, ctx: ResolutionContext) -> dict[str, Any]:
        """Resolve every outstanding category and return the flat persona.

        Returns a single-level ``{category: value}`` dict in resolution order --
        never nested, because that shape is what every downstream reader of
        ``identity.json`` parses.
        """
        resolved = self._resume_prefix(ctx)
        pending = self._categories[len(resolved):]

        for category in pending:
            # Under ``context: none`` the prompt sees no prior-attribute values;
            # ``resolved`` is still accumulated below (only what the prompt sees
            # changes, not DAG order, clamping, or the returned persona).
            context_view = {} if self._context_mode == "none" else resolved
            context_block = self._build_context_block(context_view)

            try:
                value = category.resolve(context_block, ctx)
            except Exception as e:
                logging.error(
                    "Category '%s' (method=%s) failed after resolving %d/%d categories: %s",
                    category.name, category.method, len(resolved), len(self._categories), e,
                )
                raise

            resolved[category.name] = value
            # Checkpoint AFTER the value lands in ``resolved``, never before: the
            # checkpoint's contract is "these categories are paid for", and writing
            # it first would resume a persona past a category it never generated.
            # ``call_index`` travels with it so the telemetry log's correlation
            # keys continue rather than collide when this persona is resumed.
            if self._writer is not None:
                self._writer.checkpoint(resolved, ctx.call_index)
            logging.debug(f"{category.name} ({category.method}) -> {value}")

        return resolved

    @staticmethod
    def _build_context_block(resolved: dict) -> str:
        """Serialise the resolved attributes exactly as every prompt shows them.

        Pure in ``resolved``'s contents *and* insertion order -- the single property
        that makes a resumed persona's prompts byte-identical to an uninterrupted
        run's. Do not sort, filter or annotate here.
        """
        if not resolved:
            return _EMPTY_CONTEXT
        return "\n".join(f"{k}: {v}" for k, v in resolved.items())

    def _resume_prefix(self, ctx: ResolutionContext) -> dict:
        """Seed the resolved dict (and the call counter) from the writer's checkpoint.

        Returns the longest **prefix** of this persona's category order the checkpoint
        covers, rebuilt in that order rather than in the JSON file's key order. Two
        properties follow, and together they are what makes a resumed persona
        indistinguishable from an uninterrupted one:

        * the prompt context block is a pure function of the resolved dict's contents
          and insertion order, so replaying the order here reproduces it byte for byte;
        * stopping at the first gap means no category can ever see a context an
          uninterrupted run would not have shown it.

        Returns an empty dict when there is no writer or no valid checkpoint.
        """
        if self._writer is None:
            return {}
        state = self._writer.resume()
        if state is None:
            return {}

        resolved: dict = {}
        for category in self._categories:
            if category.name not in state.resolved:
                break
            resolved[category.name] = state.resolved[category.name]

        # The counter continues from the checkpoint even where the prefix is shorter
        # than the checkpoint's key set: indices already spent are in the telemetry
        # log, and reusing one would break the (persona_id, call_index) join.
        ctx.resume_from(state.call_index)
        logging.info(
            "Resuming generation after %d/%d categories (call index %d).",
            len(resolved), len(self._categories), ctx.call_index,
        )
        return resolved

"""The persona set of one generation run, and which of its members still need work.

Defines :class:`SyntheticPopulation`: the ``n`` persona slots a run is asked to
fill, the directory they live in, the generation regime they are produced under,
and the category blueprint every one of them is built from. Its two jobs are to
answer *which slots still need work* (:meth:`SyntheticPopulation.plan`) and to
hand back the objects that do that work (:meth:`SyntheticPopulation.persona`,
:meth:`SyntheticPopulation.writer`).

Before this existed, the resume decision was open-coded inside the parallel
runner's worker function: every worker re-derived "is this persona already
finished?" from a path it built itself, and the run had no way to say afterwards
how much of its output it had inherited rather than generated. Both facts now
have one home.

**Passive by design.** The population owns no thread pool, starts nothing, and
calls no client. That is a deliberate rejection of the tempting alternative in
which it drives the parallelism: the runner allocates one LLM client and one
generator per worker thread, and moving that inside here would make a single
generator instance span threads -- at which point the correlation counter and the
client's connection state stop being per-persona by construction, which is the
property the telemetry join depends on. The runner keeps its
``ThreadPoolExecutor``; this object only answers questions.

**Thread-safe by having no mutable state.** :meth:`writer` and :meth:`persona`
construct a fresh object per call and the categories are immutable, so two
workers asking for different slots share nothing. Nothing here is memoised: the
resume verdict is memoised on the individual :class:`~.persona_writer.PersonaWriter`,
which is per persona and never crosses a thread.

The population knows nothing about prompts, generation methods, LLM calls or file
formats. The categories are opaque objects it orders and hands on; the files are
the writer's business.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .category import Category
from .persona import CONTEXT_MODES, Persona
from .persona_writer import PersonaWriter

# Structural constant (the same class as dataset ids and label maps): the on-disk
# name of a persona slot. Zero-padded to five digits so a directory listing sorts
# in generation order, and matched by ``validate_raw``'s ``persona_*`` glob.
PERSONA_DIR_TEMPLATE = "persona_{index:05d}"


@dataclass(frozen=True)
class ResumePlan:
    """What a run found on disk before generating anything.

    Frozen and index-based rather than a mutable tally: it is computed once, at
    the orchestration edge, and then both drives the work queue and is recorded
    verbatim in ``run_metadata.json``. A record that could still change after it
    was written would describe a run that never happened.

    Attributes:
        pending: Slots this run must fill, in ascending order.
        complete: Slots skipped because they already hold a finished persona.
        checkpointed: The subset of *pending* that carries a checkpoint file, and
            therefore stands to re-pay for less than a full persona. Membership is
            decided by the file's *presence* only -- whether it is valid under this
            run's fingerprint is the writer's verdict, reached later, in the worker.
    """

    pending: tuple[int, ...]
    complete: tuple[int, ...]
    checkpointed: tuple[int, ...]

    @property
    def resumed(self) -> bool:
        """Whether this run inherited any work from an earlier attempt.

        True when anything at all was found on disk -- a finished persona to skip
        or a checkpoint to continue. False for a clean run and for ``--force``,
        which is what makes the two distinguishable in ``run_metadata.json``.
        """
        return bool(self.complete or self.checkpointed)


class SyntheticPopulation:
    """The ``n`` personas of one generation run, and their resume state."""

    def __init__(
        self,
        n: int,
        output_dir: Path | str,
        fingerprint: dict[str, Any],
        categories: Sequence[Category],
        *,
        context_mode: str,
    ) -> None:
        """Bind a run's persona set to one directory, regime and blueprint.

        Creates nothing on disk. Constructing a population is free; only
        :meth:`plan` reads and only the writers it hands out ever write.

        Args:
            n: How many personas this run is asked to produce.
            output_dir: The combo directory holding the ``persona_XXXXX/`` slots.
            fingerprint: The generation regime, passed to every writer and compared
                for equality against a checkpoint's stored copy. Never interpreted
                here.
            categories: The blueprint, already in DAG order. Shared by every
                persona -- they carry no per-persona state -- so the order is
                load-bearing for both the prompts and the checkpoint replay.
            context_mode: One of :data:`~.persona.CONTEXT_MODES`.

        Raises:
            ValueError: *n* is not a positive integer, *categories* is empty, or
                *context_mode* is not one the walk implements. All three are
                checked here rather than at the first persona, so a misconfigured
                run cannot cost an LLM call.
        """
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"A population needs a positive integer size, got {n!r}.")
        if not categories:
            raise ValueError(
                "A population needs at least one category: an empty blueprint would "
                "make every persona vacuously complete and the resume gate inert."
            )
        if context_mode not in CONTEXT_MODES:
            raise ValueError(
                f"Unknown context mode {context_mode!r} (expected one of {', '.join(CONTEXT_MODES)})."
            )
        self._n = n
        self._output_dir = Path(output_dir)
        self._fingerprint = fingerprint
        self._categories = tuple(categories)
        self._context_mode = context_mode

    def __len__(self) -> int:
        return self._n

    @property
    def n(self) -> int:
        """How many personas the run was asked for, complete or not."""
        return self._n

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def category_names(self) -> list[str]:
        """The categories every persona of this run resolves, in DAG order.

        Doubles as the completeness requirement: a persona is finished when its
        ``identity.json`` carries a non-empty value for each of these.
        """
        return [category.name for category in self._categories]

    # -- slots ----------------------------------------------------------------

    def persona_dir(self, index: int) -> Path:
        """Where slot *index* lives. The only place the layout is spelled out."""
        self._check_index(index)
        return self._output_dir / PERSONA_DIR_TEMPLATE.format(index=index)

    def writer(self, index: int, *, discard_checkpoint: bool = False) -> PersonaWriter:
        """A fresh writer for slot *index*.

        One writer per call, never cached: the writer memoises its resume verdict
        and holds the telemetry file handle, both of which belong to a single
        attempt on a single thread. Handing the same instance to two workers would
        put one persona's telemetry mode under two owners.

        Args:
            index: The slot.
            discard_checkpoint: Drop any checkpoint instead of resuming from it.
                Set only by ``--force``; a retry round deliberately keeps it.
        """
        return PersonaWriter(self.persona_dir(index), self._fingerprint, discard=discard_checkpoint)

    def persona(self, index: int, *, discard_checkpoint: bool = False) -> Persona:
        """The persona occupying slot *index*, bound to its own writer.

        The domain accessor: a caller that wants to *generate* slot *index* asks
        for it here rather than assembling a directory name, a writer and a
        category list itself. The returned object is self-contained -- it exposes
        the writer it was bound to, so publishing and closing need no second
        lookup that could disagree about which files belong to this slot.
        """
        return Persona(
            self._categories,
            context_mode=self._context_mode,
            writer=self.writer(index, discard_checkpoint=discard_checkpoint),
        )

    # -- resume policy --------------------------------------------------------

    def plan(self, *, force: bool = False) -> ResumePlan:
        """Classify every slot into pending / already complete / resumable.

        The single place the resume decision is made. It runs once, sequentially,
        at the orchestration edge -- before any worker starts -- for three reasons:
        the verdict is then recorded in ``run_metadata.json`` as one consistent
        snapshot; a fully-complete rerun starts no thread pool and constructs no
        LLM client at all; and no worker can reach a different conclusion than the
        queue it was scheduled from.

        Completeness is the writer's content-validating predicate, not an
        exists-check: the truncated remains of a killed ``json.dump`` parse as
        neither a finished persona nor a missing one, and the exists-check this
        replaces skipped such a file forever.

        The one write this method performs is a cleanup, not a decision: a kill
        between :meth:`~.persona_writer.PersonaWriter.finalize`'s identity write
        and its checkpoint unlink leaves both files, and the skip path is the only
        thing that ever passes that orphan again.

        Args:
            force: Treat every slot as pending. ``--force`` means "pretend this run
                never happened", so nothing is inspected, nothing is skipped, and
                the checkpoints are discarded later by the writers the workers ask
                for -- not here, where a discarded-then-unused checkpoint would be
                lost work if the run died between the two.

        Returns:
            A :class:`ResumePlan` partitioning ``range(n)``.
        """
        if force:
            return ResumePlan(pending=tuple(range(self._n)), complete=(), checkpointed=())

        required = self.category_names
        pending: list[int] = []
        complete: list[int] = []
        checkpointed: list[int] = []
        for index in range(self._n):
            writer = self.writer(index)
            if writer.has_complete_identity(required):
                writer.discard_stale_checkpoint()
                complete.append(index)
                continue
            pending.append(index)
            if writer.has_checkpoint:
                checkpointed.append(index)
        return ResumePlan(pending=tuple(pending), complete=tuple(complete), checkpointed=tuple(checkpointed))

    def pending_indices(self, *, force: bool = False) -> list[int]:
        """The slots this run must fill. Convenience view over :meth:`plan`."""
        return list(self.plan(force=force).pending)

    # -- internals ------------------------------------------------------------

    def _check_index(self, index: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < self._n:
            raise IndexError(f"Persona index {index!r} is outside this population's 0..{self._n - 1}.")

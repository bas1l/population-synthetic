"""Ownership of one persona's files and of their shared lifecycle.

Defines :class:`PersonaWriter`, the single object responsible for everything one
persona directory contains that generation produces: the finished
``identity.json``, the in-progress ``identity.partial.json`` checkpoint, and the
``llm_interactions.jsonl`` telemetry log. Before this existed the identity write
lived in the runner, the telemetry write lived in an injected collector, and
nothing owned the relationship between them -- which is why a killed run could
leave a truncated identity that the resume gate then trusted forever, and why a
retry round silently discarded the telemetry of the attempt it replaced.

**The shared lifecycle invariant.** ``llm_interactions.jsonl`` is truncated if
and only if the checkpoint is discarded:

* resumed  -> the JSONL is opened for append *and* ``call_index`` continues past
  every index already spent, so ``(persona_id, call_index)`` stays unique across
  the seam. "Already spent" is the larger of the checkpoint's counter and the
  highest index the log itself carries: a category that exhausted its retry budget
  spent indices *after* the last checkpoint, and only the log knows about them;
* fresh    -> the JSONL is truncated *and* ``call_index`` restarts at 0.

Nothing downstream has to dedupe, because the two decisions can never disagree:
both derive from the single memoised :meth:`PersonaWriter.resume` verdict.

The writer knows nothing about strategies, generation methods, prompts or the
category DAG. The fingerprint is an opaque dict it only ever compares for
equality, and the completeness check is driven by a key list handed in by the
caller.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from population_synthetic.utils.atomic_io import atomic_write_json

from .llm_interaction_log import LLMInteractionCollector

logger = logging.getLogger(__name__)

# Structural constants (the same category as dataset ids and label maps): the
# on-disk layout of a persona directory, not a tunable a user would ever change.
DEFAULT_IDENTITY_FILENAME = "identity.json"
TELEMETRY_FILENAME = "llm_interactions.jsonl"
_PARTIAL_SUFFIX = ".partial.json"

# Bumped whenever the checkpoint payload's shape changes. A checkpoint written by
# an older layout is discarded rather than migrated -- it is a cache of work in
# progress, never a durable artifact, so regenerating is always cheaper and safer
# than a migration path nobody exercises.
CHECKPOINT_SCHEMA_VERSION = 1

# Sentinel distinguishing "resume() has not run yet" from "resume() ran and found
# nothing". Without it the memo could not represent a negative verdict, and every
# telemetry access would re-read the checkpoint file.
_UNRESOLVED = object()


@dataclass(frozen=True)
class ResumeState:
    """What a valid checkpoint restores: the resolved prefix and the call counter.

    ``resolved`` preserves the key insertion order it was written with, which is
    the property that makes a resumed persona's prompts byte-identical to an
    uninterrupted run's. ``call_index`` is the highest correlation index already
    spent, so the resumed run continues past it instead of colliding with it.
    """

    resolved: dict[str, Any]
    call_index: int


def _is_empty(value: Any) -> bool:
    """Whether a generated value counts as absent.

    Mirrors ``analysis.validate_raw.validate._is_empty`` deliberately rather than
    importing it: generation must not depend on the downstream analysis half. The
    two predicates are kept in step by intent, and generation's gate is the
    stricter of the two by construction (see the plan's containment argument).
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


class PersonaWriter:
    """Every file belonging to one persona, and the lifecycle binding them together."""

    def __init__(
        self,
        persona_dir: Path | str,
        fingerprint: dict[str, Any],
        *,
        discard: bool = False,
        identity_filename: str = DEFAULT_IDENTITY_FILENAME,
    ) -> None:
        """Bind the writer to one directory. Creates nothing until something is written.

        Args:
            persona_dir: The directory holding this persona's three files.
            fingerprint: The generation regime this run is producing under. Compared
                for equality against a checkpoint's stored copy; never interpreted.
            discard: Drop any existing checkpoint instead of resuming from it. Set
                only by ``--force``; a retry round deliberately keeps the checkpoint.
            identity_filename: Name of the finished identity file. The checkpoint's
                name is derived from it, so the two always travel together.
        """
        self._dir = Path(persona_dir)
        self._fingerprint = fingerprint
        self._discard = discard
        self._identity_path = self._dir / identity_filename
        self._checkpoint_path = self._dir / f"{Path(identity_filename).stem}{_PARTIAL_SUFFIX}"
        self._telemetry_path = self._dir / TELEMETRY_FILENAME
        self._telemetry: LLMInteractionCollector | None = None
        self._resume_state: Any = _UNRESOLVED

    # -- resume ---------------------------------------------------------------

    def resume(self) -> ResumeState | None:
        """The state a valid checkpoint restores, or ``None`` to start fresh.

        Memoised: the verdict is reached once and then reused, because it also
        decides whether the telemetry log appends or truncates and the two must
        never disagree.

        Never raises on a damaged checkpoint. That is a deliberate exception to
        the project's fail-fast rule, scoped to this file alone: the checkpoint is
        the writer's own cache of work in progress, not user input, and the only
        sound response to an unreadable one is to discard it and regenerate. Every
        discard is logged at WARNING with the specific reason, so a systematic
        cause (an edited strategy, a full disk) is visible rather than silent.
        """
        if self._resume_state is _UNRESOLVED:
            self._resume_state = self._read_checkpoint()
        return self._resume_state

    @property
    def has_checkpoint(self) -> bool:
        """Whether a checkpoint file is present -- **not** whether it is usable.

        Deliberately a bare existence check, and deliberately separate from
        :meth:`resume`. A caller that only wants to *count* how much of a run was
        inherited (the run-metadata resume record) must not consume the checkpoint
        to find out: :meth:`resume` memoises its verdict, deletes what it rejects,
        and fixes the telemetry log's append/truncate mode, all of which belong to
        the attempt that actually generates the persona.
        """
        return self._checkpoint_path.exists()

    def _read_checkpoint(self) -> ResumeState | None:
        path = self._checkpoint_path
        if self._discard:
            if path.exists():
                logger.info("Discarding checkpoint %s: --force requested a full regeneration.", path)
                path.unlink(missing_ok=True)
            return None
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            # Distinct from the mismatch branch below on purpose: an unreadable
            # checkpoint means the process died mid-write (or the disk lied),
            # while a mismatch means the configuration moved under a healthy file.
            # They call for different investigations, so they read differently.
            logger.warning(
                "Checkpoint %s is unreadable (%s); discarding it and starting this persona fresh.", path, exc
            )
            path.unlink(missing_ok=True)
            return None

        if not isinstance(payload, dict):
            logger.warning("Checkpoint %s is not a JSON object; discarding it and starting this persona fresh.", path)
            path.unlink(missing_ok=True)
            return None

        version = payload.get("schema_version")
        if version != CHECKPOINT_SCHEMA_VERSION:
            logger.warning(
                "Checkpoint %s has schema_version %r, this build writes %r; discarding it and "
                "starting this persona fresh.",
                path, version, CHECKPOINT_SCHEMA_VERSION,
            )
            path.unlink(missing_ok=True)
            return None

        if payload.get("fingerprint") != self._fingerprint:
            logger.warning(
                "Checkpoint %s was written under a different generation regime (strategy, schema, "
                "model or category order changed); discarding it rather than splicing two regimes "
                "into one persona.",
                path,
            )
            path.unlink(missing_ok=True)
            return None

        resolved = payload.get("resolved")
        call_index = payload.get("call_index")
        if not isinstance(resolved, dict) or not isinstance(call_index, int) or isinstance(call_index, bool):
            logger.warning(
                "Checkpoint %s has a malformed payload (resolved=%s, call_index=%s); discarding it "
                "and starting this persona fresh.",
                path, type(resolved).__name__, type(call_index).__name__,
            )
            path.unlink(missing_ok=True)
            return None

        # The checkpoint records the counter as of the last *successful* category,
        # but the attempts that failed after it are already in the telemetry log --
        # a category exhausts its retry budget, and each of those attempts spent an
        # index. Resuming from the checkpoint's value alone would hand those indices
        # out a second time and break the (persona_id, call_index) join every cost
        # and latency figure is computed over. The log is therefore consulted for the
        # highest index actually spent, and the counter continues past whichever of
        # the two is larger.
        call_index = max(call_index, self._highest_recorded_call_index())
        logger.info(
            "Resuming %s from checkpoint: %d categor(ies) already resolved, continuing after call %d.",
            self._dir.name, len(resolved), call_index,
        )
        return ResumeState(resolved=resolved, call_index=call_index)

    def _highest_recorded_call_index(self) -> int:
        """The largest ``call_index`` the telemetry log already carries; 0 if none.

        Read line by line and lenient about damage: this is an append log, so a
        killed process can leave a torn trailing line, and one unparseable record
        must not cost the indices the readable ones establish. Safe to call here
        because :meth:`resume` is memoised and :attr:`telemetry` resolves it first,
        so this never runs while the writer's own append handle is open.
        """
        path = self._telemetry_path
        if not path.exists():
            return 0
        highest = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    index = record.get("call_index") if isinstance(record, dict) else None
                    if isinstance(index, int) and not isinstance(index, bool) and index > highest:
                        highest = index
        except (OSError, UnicodeDecodeError) as exc:
            # Not fatal -- the persona can still be generated -- but it does mean the
            # correlation keys of this persona may collide, so it is never silent.
            logger.warning(
                "Telemetry log %s could not be read (%s); resuming from the checkpoint's call "
                "index alone, which may repeat a correlation key.", path, exc,
            )
            return 0
        return highest

    # -- telemetry ------------------------------------------------------------

    @property
    def telemetry(self) -> LLMInteractionCollector:
        """The interaction log, opened in the mode the resume verdict implies.

        Accessing this resolves :meth:`resume` first if it has not run yet, which
        is what removes the ordering hazard structurally: there is no way to obtain
        a collector whose append/truncate mode was decided before the checkpoint
        was inspected, whichever order the caller happens to use.
        """
        if self._telemetry is None:
            resumed = self.resume() is not None
            self._telemetry = LLMInteractionCollector(self._telemetry_path, append=resumed)
        return self._telemetry

    # -- writes ---------------------------------------------------------------

    def checkpoint(self, resolved: dict[str, Any], call_index: int) -> None:
        """Atomically rewrite the checkpoint to the persona's state as of now.

        Called *after* the newly resolved value is in ``resolved``, never before:
        a checkpoint written first would claim a category the run has not paid for
        and the resumed persona would carry a hole.

        Never sorted: ``resolved``'s insertion order is the DAG order the prompts
        were built from, so sorting it would make a resumed persona's context block
        differ from an uninterrupted one's.
        """
        payload = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "fingerprint": self._fingerprint,
            "call_index": call_index,
            "resolved": resolved,
        }
        atomic_write_json(self._checkpoint_path, payload)

    def finalize(self, resolved: dict[str, Any]) -> None:
        """Publish the finished identity, then retire the checkpoint.

        The order is load-bearing. ``identity.json`` is the complete-output marker,
        so it must exist before the checkpoint that could rebuild it goes away. A
        kill between the two leaves both files: the next run's gate sees a complete
        identity, skips the persona, and clears the stale checkpoint. The reverse
        order would leave a window in which neither file describes the persona.
        """
        atomic_write_json(self._identity_path, resolved)
        self._checkpoint_path.unlink(missing_ok=True)

    def close(self) -> None:
        """Release the telemetry handle. Idempotent; safe when nothing was opened."""
        if self._telemetry is not None:
            self._telemetry.close()

    # -- gate -----------------------------------------------------------------

    def has_complete_identity(self, required_categories: Sequence[str]) -> bool:
        """Whether ``identity.json`` is a finished persona for this run.

        Replaces an exists-only check, which could not tell a finished persona from
        the truncated remains of a killed ``json.dump`` and therefore skipped the
        corrupt one forever. Complete means: parses as JSON, is a flat single-level
        object, and carries a non-empty value for every required category.

        Args:
            required_categories: The categories this run resolves. Must be non-empty
                -- an empty list would make every parseable file "complete", turning
                the gate back into the exists-only check it replaces.

        Raises:
            ValueError: If ``required_categories`` is empty.
        """
        if not required_categories:
            raise ValueError(
                "has_complete_identity requires the run's resolved category order; an empty "
                "requirement would accept any parseable file as a finished persona."
            )
        path = self._identity_path
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            logger.warning("%s is unreadable (%s); regenerating this persona.", path, exc)
            return False
        if not isinstance(data, dict):
            logger.warning("%s is not a flat JSON object; regenerating this persona.", path)
            return False
        if any(isinstance(value, (dict, list)) for value in data.values()):
            logger.warning("%s is nested rather than flat; regenerating this persona.", path)
            return False
        missing = [key for key in required_categories if key not in data or _is_empty(data[key])]
        if missing:
            logger.warning(
                "%s is incomplete (%d of %d categories missing or empty, e.g. %s); regenerating "
                "this persona.",
                path, len(missing), len(required_categories), missing[:5],
            )
            return False
        return True

    def discard_stale_checkpoint(self) -> None:
        """Remove a checkpoint left beside an already-complete identity.

        The one cleanup the writer performs for a persona it is not generating: a
        kill between :meth:`finalize`'s two steps leaves both files, and nothing
        else would ever collect the orphan.
        """
        if self._checkpoint_path.exists():
            logger.info(
                "Removing stale checkpoint %s left beside a complete identity.", self._checkpoint_path
            )
            self._checkpoint_path.unlink(missing_ok=True)

"""Durable, all-or-nothing overwrite of a single file.

Defines ``atomic_write_text`` and ``atomic_write_json``: both serialise into a
unique temporary file in the *target's own directory*, force it to stable
storage, and then ``os.replace`` it over the destination. A reader therefore
only ever observes the previous complete file or the new complete file -- never
a half-written one -- which is what makes a killed run recoverable instead of
silently corrupting its own outputs.

The module deliberately knows nothing about what it is writing: no JSON schema,
no persona, no pipeline stage. Its whole contract is "this path ends up holding
exactly these bytes, or it is left untouched".
"""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import IO, Any, Callable

logger = logging.getLogger(__name__)

# Windows only: ``os.replace`` raises PermissionError (WinError 5) when the
# destination is momentarily unavailable -- another process holds it open (an
# editor, a virus scanner, a stray reader), or a concurrent replace has left it
# delete-pending. Both windows are milliseconds wide, so a bounded retry converts
# a spurious crash into a short delay. Deliberately narrow: only PermissionError,
# only this many tries, so a genuine permission problem still surfaces instead of
# being ridden out silently.
_REPLACE_ATTEMPTS = 12
_REPLACE_BACKOFF_S = 0.05


def _replace_with_retry(source: Path, target: Path) -> None:
    """``os.replace`` the temp file over the target, riding out transient locks."""
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            # Jittered, not fixed: contending writers that failed together would
            # otherwise wake together and collide again on every retry.
            delay = _REPLACE_BACKOFF_S * attempt * random.uniform(0.5, 1.5)
            logger.warning(
                "Atomic replace of %s blocked (%s); retrying %d/%d in %.2fs. "
                "The destination is held open or delete-pending.",
                target, exc, attempt, _REPLACE_ATTEMPTS, delay,
            )
            time.sleep(delay)


def _atomic_write(path: Path | str, emit: Callable[[IO[str]], None], *, encoding: str) -> None:
    """Serialise via ``emit`` into a temp file, then atomically move it onto ``path``.

    ``emit`` receives an open text handle. Any exception it raises leaves the
    destination untouched and removes the temp file, so a serialiser that blows up
    halfway cannot leave residue behind.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # mkstemp in the *target's* directory, never a predictable "<name>.tmp":
    # the generation runner writes from a thread pool, and two workers racing on
    # one guessable temp name would interleave their bytes into one file. Same
    # directory because os.replace is only atomic within a filesystem.
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            emit(handle)
            # Order is load-bearing and must never be reordered: write -> flush
            # (out of Python's buffer into the OS) -> fsync (out of the OS cache
            # onto the disk) -> replace. Replacing before fsync would publish a
            # name that survives a power cut while its contents do not.
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_path, target)
    except BaseException:
        # BaseException, not Exception: a KeyboardInterrupt or SystemExit between
        # mkstemp and replace is exactly the case this module exists for, and it
        # must not leave a stray .tmp in a persona directory either.
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """Replace ``path`` with ``text``, atomically and durably."""
    _atomic_write(path, lambda handle: handle.write(text), encoding=encoding)


def atomic_write_json(
    path: Path | str,
    obj: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> None:
    """Replace ``path`` with ``obj`` serialised as JSON, atomically and durably.

    ``sort_keys`` defaults to False and callers persisting an *ordered* mapping
    must leave it so: key insertion order is meaningful for the generation
    checkpoint (it is what makes a resumed persona's prompts identical to an
    uninterrupted run's), and sorting would silently destroy it.
    """
    _atomic_write(
        path,
        lambda handle: json.dump(obj, handle, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys),
        encoding="utf-8",
    )

"""fs.py -- Filesystem helpers hardened for a OneDrive/SharePoint-synced output base.

The run output base normally lives on a synced drive, where two Windows behaviours break
the plain ``shutil`` calls:

* Files-On-Demand marks a dehydrated placeholder read-only (``ReadOnly | ReparsePoint``),
  and Windows' ``RemoveDirectory`` / ``DeleteFile`` refuse a read-only target with
  ``ERROR_ACCESS_DENIED`` (WinError 5) -- so ``shutil.rmtree`` dies on a tree that is
  merely *marked* read-only, even when nothing holds a handle on it.
* ``shutil.copytree`` / ``shutil.copy2`` propagate that read-only mode to the copy
  (``copystat`` -> ``os.chmod``), so a mirror written from a placeholder source is itself
  undeletable -- and un-overwritable -- on the next run.

:func:`rmtree_resilient` survives the first (it also rides out a transient sync-engine
lock); :func:`clear_readonly_tree` prevents the second by clearing the bit on a tree we
have just written. Both are no-ops in effect on POSIX, where the read-only attribute does
not exist and the owner write bit is normally already set.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from pathlib import Path

__all__ = ["clear_readonly_tree", "rmtree_resilient"]


def _add_write_bit(path: str | os.PathLike[str]) -> None:
    """Make *path* writable, preserving every other permission bit.

    On Windows this clears ``FILE_ATTRIBUTE_READONLY``; on POSIX it ORs in the owner write
    bit rather than replacing the mode, so a tree-wide call cannot strip permissions.
    """
    os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)


def _clear_readonly_and_retry(func, target, _exc) -> None:
    """rmtree error handler: clear the read-only bit and retry the failed unlink/rmdir.

    Accepts the three positional args of both ``shutil.rmtree(onerror=...)`` (<3.12) and
    ``onexc=...`` (>=3.12); the third arg (exc-info tuple vs exception) is ignored.

    The containing directory is made writable too: Windows refuses ``rmdir`` on a read-only
    directory (the entry itself is the blocker), while POSIX refuses to unlink a child of a
    non-writable directory (the *parent* is the blocker). Clearing both covers either
    platform's flavour of the same failure. We are deleting the whole tree regardless, so
    relaxing the parent is not a side effect that outlives the call.
    """
    parent = os.path.dirname(os.fspath(target))
    if parent and os.path.isdir(parent):
        _add_write_bit(parent)
    _add_write_bit(target)
    func(target)


def rmtree_resilient(path: Path, *, attempts: int = 5, base_delay: float = 0.5) -> None:
    """Recursively delete *path*, tolerating read-only entries and transient sync locks.

    A plain ``shutil.rmtree`` raises ``PermissionError`` (WinError 5) on Windows when an
    entry in the tree is read-only or momentarily locked -- the common case when the output
    lives in a OneDrive/SharePoint-synced folder the sync engine is mid-upload on. The
    per-entry handler clears the read-only bit and retries the offending removal; the outer
    loop retries the whole tree with exponential backoff to ride out a transient lock.
    Re-raises the last error if every attempt fails (fail-fast invariant).
    """
    for attempt in range(attempts):
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_clear_readonly_and_retry)
            else:
                shutil.rmtree(path, onerror=_clear_readonly_and_retry)
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt))


def clear_readonly_tree(root: Path) -> None:
    """Clear the read-only bit on *root* and everything below it.

    Call this on a tree we have just copied out of the synced source pool: ``copytree`` /
    ``copy2`` carry the source's read-only mode over, which would leave our own output
    undeletable (``rmtree``) and un-overwritable (a later ``copy2`` onto it) on the next
    run. A plain file root is cleared directly. Missing paths raise (fail-fast) -- the
    caller has just written what it passes in.
    """
    _add_write_bit(root)
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            _add_write_bit(os.path.join(dirpath, name))

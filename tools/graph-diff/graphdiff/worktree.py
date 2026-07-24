"""worktree — temporary detached git worktree for a single ref.

Responsibility
--------------
Materialise the code at an arbitrary git ref on disk, in a throwaway detached
``git worktree``, so a caller can read the tree at that revision without ever
touching the user's real working tree, index, or current branch. The worktree
is created on entry and *guaranteed* to be torn down on exit — on the success
path and the exception path alike.

Must NOT know about
-------------------
- package structure or how a package is laid out on disk,
- grimp or any import-graph extraction,
- rendering or artifact serialisation.

This module speaks only git and the filesystem. It hands back a path; what lives
under that path is entirely the caller's concern.

Design
------
The public surface is the :func:`worktree` context manager. It:

1. resolves the repository top-level (``git rev-parse --show-toplevel``),
2. verifies the ref actually resolves to a commit and raises loudly if not,
3. adds a detached worktree into a fresh ``tempfile`` directory,
4. yields the checked-out path,
5. in a ``finally`` block removes the worktree (``--force``), prunes stale
   administrative entries, and, as a Windows-safe last resort, deletes the temp
   directory outright.

Every git call uses an explicit argument list (never ``shell=True``) and checks
its return code, surfacing git's own stderr on failure.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path


class GitCommandError(RuntimeError):
    """A git subprocess exited non-zero; carries the command and its stderr."""


def _run_git(
    repo_root: Path | None,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``git [-C repo_root] <args>`` capturing text output.

    Raises :class:`GitCommandError` (including git's stderr) when ``check`` is
    True and the command fails. No shell is used; arguments are passed as an
    explicit list.
    """
    cmd = ["git"]
    if repo_root is not None:
        cmd += ["-C", str(repo_root)]
    cmd += args
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if check and completed.returncode != 0:
        raise GitCommandError(
            f"git command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stderr: {completed.stderr.strip()}"
        )
    return completed


def _resolve_repo_root(repo_root: Path | str | None) -> Path:
    """Return the git top-level for ``repo_root`` (or cwd when None).

    Raises :class:`GitCommandError` if the location is not inside a git repo.
    """
    start = Path(repo_root) if repo_root is not None else None
    completed = _run_git(start, ["rev-parse", "--show-toplevel"])
    return Path(completed.stdout.strip()).resolve()


def _verify_ref(repo_root: Path, ref: str) -> None:
    """Raise loudly if ``ref`` does not resolve to a commit in ``repo_root``.

    Uses ``git rev-parse --verify <ref>^{commit}`` so branches, tags, and raw
    SHAs are all accepted, but anything git cannot resolve fails fast with a
    clear message rather than degrading into an empty or partial graph later.
    """
    completed = _run_git(
        repo_root, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], check=False
    )
    if completed.returncode != 0:
        raise ValueError(
            f"Ref {ref!r} does not resolve to a commit in {repo_root}. "
            f"git stderr: {completed.stderr.strip() or '(none)'}"
        )


@contextlib.contextmanager
def worktree(ref: str, repo_root: Path | str | None = None) -> Iterator[Path]:
    """Yield the path to a detached worktree checked out at ``ref``.

    Parameters
    ----------
    ref:
        Any git-resolvable reference — branch, tag, or commit SHA.
    repo_root:
        The repository to operate on. Defaults to the git top-level of the
        current working directory.

    Yields
    ------
    Path
        The root of the checked-out tree for ``ref``.

    Guarantees
    ----------
    - The caller's working tree, index, and current branch are never mutated
      (a worktree is an independent checkout).
    - The worktree is removed on exit whether the ``with`` body succeeds or
      raises; stale administrative entries are pruned defensively.

    Raises
    ------
    GitCommandError
        If the location is not a git repo or ``git worktree add`` fails.
    ValueError
        If ``ref`` does not resolve to a commit.
    """
    resolved_root = _resolve_repo_root(repo_root)
    _verify_ref(resolved_root, ref)

    # mkdtemp creates the parent; the worktree itself goes in a not-yet-existing
    # child, because `git worktree add` refuses a path that already exists.
    tmp_parent = Path(tempfile.mkdtemp(prefix="graphdiff-wt-"))
    tree_path = tmp_parent / "tree"
    try:
        _run_git(
            resolved_root,
            ["worktree", "add", "--detach", str(tree_path), ref],
        )
        yield tree_path
    finally:
        # Best-effort teardown: never let cleanup raise and mask the body's
        # exception. `remove --force` handles a dirty tree; `prune` clears any
        # stale entry; rmtree is the Windows-safe last resort if the dir lingers.
        _run_git(
            resolved_root,
            ["worktree", "remove", "--force", str(tree_path)],
            check=False,
        )
        _run_git(resolved_root, ["worktree", "prune"], check=False)
        shutil.rmtree(tmp_parent, ignore_errors=True)

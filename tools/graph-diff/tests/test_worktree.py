"""Tests for the temporary git-worktree context manager.

These need a real git repository: they discover the enclosing repo via
``git rev-parse --show-toplevel`` and use ``HEAD`` (always resolvable). Each
test asserts the worktree is created, is torn down on exit, leaves no entry in
``git worktree list``, and does not perturb the real repo's working-tree state
(``git status --porcelain`` identical before and after). If the suite is not run
inside a git repo, every test skips cleanly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from graphdiff.worktree import GitCommandError, worktree


def _git(repo: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["git"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def _repo_root_or_skip() -> Path:
    result = _git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        pytest.skip("not inside a git repository")
    return Path(result.stdout.strip()).resolve()


@pytest.fixture
def repo_root() -> Path:
    return _repo_root_or_skip()


def _porcelain(repo: Path) -> str:
    return _git(repo, "status", "--porcelain").stdout


def _worktree_paths(repo: Path) -> set[Path]:
    """Absolute paths listed by ``git worktree list --porcelain``."""
    out = _git(repo, "worktree", "list", "--porcelain").stdout
    paths: set[Path] = set()
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.add(Path(line[len("worktree ") :].strip()).resolve())
    return paths


def test_worktree_created_and_populated(repo_root: Path):
    with worktree("HEAD", repo_root=repo_root) as tree:
        assert tree.exists() and tree.is_dir()
        # A checked-out tree of this repo contains its tracked files. Use a file
        # tracked at HEAD (this tool's own files may still be uncommitted).
        assert (tree / "pyproject.toml").is_file()
        assert tree.resolve() in _worktree_paths(repo_root)


def test_worktree_removed_on_success(repo_root: Path):
    with worktree("HEAD", repo_root=repo_root) as tree:
        captured = tree.resolve()
        assert captured.exists()
    assert not captured.exists()
    assert captured not in _worktree_paths(repo_root)


def test_worktree_removed_on_exception(repo_root: Path):
    captured: Path | None = None

    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom):
        with worktree("HEAD", repo_root=repo_root) as tree:
            captured = tree.resolve()
            assert captured.exists()
            raise _Boom("body failed")

    assert captured is not None
    assert not captured.exists()
    assert captured not in _worktree_paths(repo_root)


def test_working_tree_status_unchanged(repo_root: Path):
    before = _porcelain(repo_root)
    with worktree("HEAD", repo_root=repo_root):
        pass
    after = _porcelain(repo_root)
    assert before == after


def test_unresolvable_ref_raises_and_leaves_no_worktree(repo_root: Path):
    before = _worktree_paths(repo_root)
    with pytest.raises(ValueError, match="does not resolve to a commit"):
        with worktree("definitely-not-a-real-ref-xyz", repo_root=repo_root):
            pass
    assert _worktree_paths(repo_root) == before


def test_not_a_git_repo_raises(tmp_path: Path):
    with pytest.raises(GitCommandError):
        with worktree("HEAD", repo_root=tmp_path):
            pass

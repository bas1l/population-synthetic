"""Integration test for the graph_diff.py CLI wiring.

Builds a self-contained throwaway git repository (so the test is hermetic and
independent of the host repo's commit state), then drives the full
worktree -> extract -> diff -> render pipeline through the CLI entrypoint.

The ``identical refs`` case proves the delta is empty and the process exits 0;
a second case proves an unresolvable ref exits nonzero without crashing. Both
use json/md/dot formats only, so no Graphviz binary is required. Skips cleanly
if git or grimp is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("grimp")

import graph_diff  # noqa: E402 — tool root is on sys.path via conftest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def _make_repo_with_package(root: Path) -> None:
    """Create a git repo at ``root`` containing a tiny committed package."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    root.mkdir(parents=True, exist_ok=True)
    pkg = root / "src" / "tinypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "leaf.py").write_text("from tinypkg import core\n", encoding="utf-8")

    assert _git(root, "init").returncode == 0
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    assert _git(root, "commit", "-m", "init").returncode == 0


def test_identical_refs_empty_delta_exit_zero(tmp_path, capsys):
    repo = tmp_path / "repo"
    _make_repo_with_package(repo)
    out_dir = tmp_path / "out"

    code = graph_diff.main(
        [
            "--package-path", "src/tinypkg",
            "--base-ref", "HEAD",
            "--head-ref", "HEAD",
            "--repo-root", str(repo),
            "--output", str(out_dir),
            "--format", "json,md,dot",
        ]
    )
    assert code == 0

    captured = capsys.readouterr().out
    assert "no structural change" in captured

    assert (out_dir / "graph_delta.json").is_file()
    assert (out_dir / "graph_delta.md").is_file()
    assert (out_dir / "graph_delta.dot").is_file()
    assert not (out_dir / "graph_delta.svg").exists()

    # No worktrees should linger in the throwaway repo after the run.
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    assert listing.count("worktree ") == 1  # only the main working tree


def test_unresolvable_ref_returns_nonzero(tmp_path, capsys):
    repo = tmp_path / "repo"
    _make_repo_with_package(repo)

    code = graph_diff.main(
        [
            "--package-path", "src/tinypkg",
            "--base-ref", "definitely-not-a-real-ref-xyz",
            "--head-ref", "HEAD",
            "--repo-root", str(repo),
            "--output", str(tmp_path / "out"),
            "--format", "json",
        ]
    )
    assert code == 1
    assert "graph-diff error" in capsys.readouterr().err

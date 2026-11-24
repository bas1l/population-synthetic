"""Tests for the grimp-backed extractor against a committed fixture package.

The fixture ``tests/fixtures/samplepkg`` has a fixed, known set of intra-package
imports, so the exact ``(nodes, edges)`` graph — and the effect of ``--exclude``
and ``--depth`` — can be asserted precisely. grimp is required; if it is not
installed the whole module skips (rather than errors) via ``importorskip``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("grimp")

from graphdiff.diff import Graph  # noqa: E402 — after importorskip by design
from graphdiff.extract import extract_graph  # noqa: E402

# Repo root = four levels up from this file:
# tests/ -> graph-diff/ -> tools/ -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_REL_PATH = "tools/graph-diff/tests/fixtures/samplepkg"

# The complete, known graph of the fixture package.
_ALL_NODES = {
    "samplepkg",
    "samplepkg.core",
    "samplepkg.alpha",
    "samplepkg.beta",
}
_ALL_EDGES = {
    ("samplepkg.alpha", "samplepkg.core"),
    ("samplepkg.beta", "samplepkg.alpha"),
    ("samplepkg.beta", "samplepkg.core"),
}


def test_extract_exact_graph_from_repo_relative_path():
    """tree_root = repo root, package_path = a repo-relative filesystem path."""
    graph = extract_graph(_REPO_ROOT, _FIXTURE_REL_PATH)
    assert isinstance(graph, Graph)
    assert graph.nodes == frozenset(_ALL_NODES)
    assert graph.edges == frozenset(_ALL_EDGES)


def test_extract_exact_graph_from_bare_package_name():
    """tree_root = fixtures dir, package_path = the bare package directory name."""
    graph = extract_graph(_FIXTURES_DIR, "samplepkg")
    assert graph.nodes == frozenset(_ALL_NODES)
    assert graph.edges == frozenset(_ALL_EDGES)


def test_exclude_drops_matching_node_and_its_edges():
    """--exclude 'beta' removes the beta node and every edge touching it."""
    graph = extract_graph(_FIXTURES_DIR, "samplepkg", exclude=["beta"])
    assert graph.nodes == frozenset(
        {"samplepkg", "samplepkg.core", "samplepkg.alpha"}
    )
    assert graph.edges == frozenset({("samplepkg.alpha", "samplepkg.core")})


def test_exclude_multiple_substrings():
    """Multiple exclude substrings are OR-combined."""
    graph = extract_graph(_FIXTURES_DIR, "samplepkg", exclude=["alpha", "beta"])
    assert graph.nodes == frozenset({"samplepkg", "samplepkg.core"})
    assert graph.edges == frozenset()


def test_depth_one_collapses_to_root_and_drops_self_loops():
    """--depth 1 collapses every module to 'samplepkg'; all edges self-loop → dropped."""
    graph = extract_graph(_FIXTURES_DIR, "samplepkg", depth=1)
    assert graph.nodes == frozenset({"samplepkg"})
    assert graph.edges == frozenset()


def test_depth_two_keeps_leaf_modules_intact():
    """--depth 2 leaves the two-component module names (and their edges) unchanged."""
    graph = extract_graph(_FIXTURES_DIR, "samplepkg", depth=2)
    assert graph.nodes == frozenset(_ALL_NODES)
    assert graph.edges == frozenset(_ALL_EDGES)


def test_depth_must_be_positive():
    with pytest.raises(ValueError, match="positive integer"):
        extract_graph(_FIXTURES_DIR, "samplepkg", depth=0)


def test_missing_package_path_raises():
    with pytest.raises(FileNotFoundError, match="does not resolve"):
        extract_graph(_FIXTURES_DIR, "no_such_package_dir")

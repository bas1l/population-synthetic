"""Unit tests for the pure diff core and the JSON/Markdown emitters.

No git, no grimp — these operate entirely on in-memory graphs, as required by
the module contracts. The tool root is placed on sys.path by the sibling
``conftest.py`` so ``import graphdiff`` resolves from the repo root.
"""

from __future__ import annotations

import json

import pytest
from graphdiff.diff import Delta, Graph, compute_delta
from graphdiff.render import (
    JSON_FILENAME,
    MARKDOWN_FILENAME,
    write_json,
    write_markdown,
)

# --------------------------------------------------------------------------- #
# Graph construction / validation
# --------------------------------------------------------------------------- #


def test_graph_of_accepts_valid_nodes_and_edges():
    g = Graph.of({"a", "b"}, {("a", "b")})
    assert g.nodes == frozenset({"a", "b"})
    assert g.edges == frozenset({("a", "b")})


def test_graph_of_rejects_dangling_edge_endpoint():
    with pytest.raises(ValueError, match="absent from the node set"):
        Graph.of({"a"}, {("a", "b")})


def test_graph_of_rejects_malformed_edge():
    with pytest.raises(ValueError, match="tuple of two strings"):
        Graph.of({"a", "b"}, {("a", "b", "c")})


# --------------------------------------------------------------------------- #
# compute_delta — the five required cases
# --------------------------------------------------------------------------- #


def test_added_only():
    base = Graph.of({"a", "b"}, {("a", "b")})
    head = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    delta = compute_delta(base, head)

    assert delta.added_edges == frozenset({("b", "c")})
    assert delta.removed_edges == frozenset()
    assert delta.unchanged_edges == frozenset({("a", "b")})
    assert delta.added_nodes == frozenset({"c"})
    assert delta.removed_nodes == frozenset()
    assert delta.unchanged_nodes == frozenset({"a", "b"})
    assert not delta.is_empty


def test_removed_only():
    base = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    head = Graph.of({"a", "b"}, {("a", "b")})
    delta = compute_delta(base, head)

    assert delta.added_edges == frozenset()
    assert delta.removed_edges == frozenset({("b", "c")})
    assert delta.unchanged_edges == frozenset({("a", "b")})
    assert delta.added_nodes == frozenset()
    assert delta.removed_nodes == frozenset({"c"})
    assert delta.unchanged_nodes == frozenset({"a", "b"})
    assert not delta.is_empty


def test_mixed_added_and_removed():
    base = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    head = Graph.of({"a", "b", "d"}, {("a", "b"), ("a", "d")})
    delta = compute_delta(base, head)

    assert delta.added_edges == frozenset({("a", "d")})
    assert delta.removed_edges == frozenset({("b", "c")})
    assert delta.unchanged_edges == frozenset({("a", "b")})
    assert delta.added_nodes == frozenset({"d"})
    assert delta.removed_nodes == frozenset({"c"})
    assert delta.unchanged_nodes == frozenset({"a", "b"})
    assert not delta.is_empty


def test_identical_yields_empty_delta():
    graph = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    delta = compute_delta(graph, graph)

    assert delta.added_edges == frozenset()
    assert delta.removed_edges == frozenset()
    assert delta.added_nodes == frozenset()
    assert delta.removed_nodes == frozenset()
    assert delta.unchanged_edges == graph.edges
    assert delta.unchanged_nodes == graph.nodes
    assert delta.is_empty


def test_node_added_with_edges():
    # A brand-new node arrives together with edges connecting it in both
    # directions — every new element must show up as added.
    base = Graph.of({"a", "b"}, {("a", "b")})
    head = Graph.of(
        {"a", "b", "new"},
        {("a", "b"), ("a", "new"), ("new", "b")},
    )
    delta = compute_delta(base, head)

    assert delta.added_nodes == frozenset({"new"})
    assert delta.added_edges == frozenset({("a", "new"), ("new", "b")})
    assert delta.removed_nodes == frozenset()
    assert delta.removed_edges == frozenset()
    assert delta.unchanged_edges == frozenset({("a", "b")})


def test_compute_delta_rejects_non_graph_inputs():
    g = Graph.of({"a"}, set())
    with pytest.raises(TypeError):
        compute_delta(g, object())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Count properties
# --------------------------------------------------------------------------- #


def test_count_properties_match_sets():
    base = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    head = Graph.of({"a", "b", "d"}, {("a", "b"), ("a", "d")})
    delta = compute_delta(base, head)

    assert delta.added_edge_count == 1
    assert delta.removed_edge_count == 1
    assert delta.unchanged_edge_count == 1
    assert delta.added_node_count == 1
    assert delta.removed_node_count == 1
    assert delta.unchanged_node_count == 2


# --------------------------------------------------------------------------- #
# render — JSON and Markdown emitters
# --------------------------------------------------------------------------- #


def _sample_delta() -> Delta:
    base = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    head = Graph.of({"a", "b", "d"}, {("a", "b"), ("a", "d")})
    return compute_delta(base, head)


def test_write_json_matches_known_delta(tmp_path):
    delta = _sample_delta()
    path = write_json(delta, tmp_path, title="sample")

    assert path == tmp_path / JSON_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["title"] == "sample"
    assert payload["summary"] == {
        "added_nodes": 1,
        "removed_nodes": 1,
        "unchanged_nodes": 2,
        "added_edges": 1,
        "removed_edges": 1,
        "unchanged_edges": 1,
        "is_empty": False,
    }
    assert payload["edges"]["added"] == [["a", "d"]]
    assert payload["edges"]["removed"] == [["b", "c"]]
    assert payload["edges"]["unchanged"] == [["a", "b"]]
    assert payload["nodes"]["added"] == ["d"]
    assert payload["nodes"]["removed"] == ["c"]
    assert payload["nodes"]["unchanged"] == ["a", "b"]


def test_write_json_is_deterministic(tmp_path):
    delta = _sample_delta()
    first = write_json(delta, tmp_path / "a", title="t").read_text(encoding="utf-8")
    second = write_json(delta, tmp_path / "b", title="t").read_text(encoding="utf-8")
    assert first == second


def test_write_markdown_enumerates_edges_and_nodes(tmp_path):
    delta = _sample_delta()
    path = write_markdown(delta, tmp_path, title="sample run")

    assert path == tmp_path / MARKDOWN_FILENAME
    text = path.read_text(encoding="utf-8")

    assert "# Graph diff: sample run" in text
    # Counts in section headers.
    assert "## Added edges (1)" in text
    assert "## Removed edges (1)" in text
    assert "## Added nodes (1)" in text
    assert "## Removed nodes (1)" in text
    # Explicit enumerations.
    assert "`a` → `d`" in text  # added edge
    assert "`b` → `c`" in text  # removed edge
    assert "- `d`" in text  # added node
    assert "- `c`" in text  # removed node


def test_write_markdown_reports_empty_delta(tmp_path):
    graph = Graph.of({"a", "b"}, {("a", "b")})
    delta = compute_delta(graph, graph)
    text = write_markdown(delta, tmp_path, title="noop").read_text(encoding="utf-8")

    assert "**No structural change**" in text
    assert "## Added edges (0)" in text
    # Empty sections render an explicit placeholder, not a blank.
    assert "_none_" in text


def test_render_creates_missing_output_dir(tmp_path):
    delta = _sample_delta()
    target = tmp_path / "nested" / "out"
    assert not target.exists()
    write_json(delta, target, title="t")
    write_markdown(delta, target, title="t")
    assert (target / JSON_FILENAME).is_file()
    assert (target / MARKDOWN_FILENAME).is_file()

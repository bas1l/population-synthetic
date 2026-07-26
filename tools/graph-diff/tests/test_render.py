"""Tests for the Graphviz .dot emitter and the render_delta orchestrator.

The .dot-source assertions need no external binary — they inspect the generated
DOT text directly. Only the svg/png tests require the Graphviz ``dot``
executable and skip cleanly when it is absent.
"""

from __future__ import annotations

import shutil

import pytest
from graphdiff.diff import Graph, compute_delta
from graphdiff.render import (
    ALL_FORMATS,
    DOT_FILENAME,
    JSON_FILENAME,
    MARKDOWN_FILENAME,
    PNG_FILENAME,
    SVG_FILENAME,
    GraphvizNotFoundError,
    build_dot,
    render_delta,
    write_dot,
)

_HAS_DOT = shutil.which("dot") is not None


def _sample_delta():
    """added edge (a->d) + added node d; removed edge (b->c) + removed node c."""
    base = Graph.of({"a", "b", "c"}, {("a", "b"), ("b", "c")})
    head = Graph.of({"a", "b", "d"}, {("a", "b"), ("a", "d")})
    return compute_delta(base, head)


# --------------------------------------------------------------------------- #
# .dot source — colour/style encoding (no binary needed)
# --------------------------------------------------------------------------- #


def test_build_dot_is_valid_digraph_with_title():
    dot = build_dot(_sample_delta(), title="base -> head")
    assert dot.startswith("// Graph diff: base -> head")
    assert "digraph graph_delta {" in dot
    assert dot.rstrip().endswith("}")


def test_added_edge_is_green():
    dot = build_dot(_sample_delta(), title="t")
    # a -> d is the added edge; green (#2e7d32), solid.
    assert '"a" -> "d" [color="#2e7d32", penwidth=2.2];' in dot


def test_removed_edge_is_red_and_dashed():
    dot = build_dot(_sample_delta(), title="t")
    # b -> c is the removed edge; red (#c62828), dashed.
    assert '"b" -> "c" [color="#c62828", penwidth=2.2, style=dashed];' in dot


def test_unchanged_edge_is_grey_and_dimmed():
    dot = build_dot(_sample_delta(), title="t")
    # a -> b is unchanged; grey (#9aa7b0), thin.
    assert '"a" -> "b" [color="#9aa7b0", penwidth=0.9];' in dot


def test_added_node_has_green_outline():
    dot = build_dot(_sample_delta(), title="t")
    assert '"d" [fillcolor="#d6ecd6", color="#2e7d32"' in dot


def test_removed_node_has_red_dashed_outline():
    dot = build_dot(_sample_delta(), title="t")
    assert '"c" [fillcolor="#f6dcdc", color="#c62828"' in dot
    assert 'style="rounded,filled,dashed"' in dot


def test_build_dot_is_deterministic():
    delta = _sample_delta()
    assert build_dot(delta, "t") == build_dot(delta, "t")


def test_dotted_module_names_are_quoted():
    base = Graph.of({"pkg.a"}, set())
    head = Graph.of({"pkg.a", "pkg.b"}, {("pkg.a", "pkg.b")})
    dot = build_dot(compute_delta(base, head), title="t")
    assert '"pkg.a" -> "pkg.b"' in dot


def test_legend_is_present():
    dot = build_dot(_sample_delta(), title="t")
    assert "subgraph cluster_legend" in dot
    assert "added edge" in dot and "removed edge" in dot and "unchanged edge" in dot


# --------------------------------------------------------------------------- #
# write_dot / render_delta orchestration
# --------------------------------------------------------------------------- #


def test_write_dot_writes_file(tmp_path):
    path = write_dot(_sample_delta(), tmp_path, title="t")
    assert path == tmp_path / DOT_FILENAME
    assert path.read_text(encoding="utf-8").startswith("// Graph diff: t")


def test_render_delta_json_md_dot_without_binary(tmp_path):
    """dot/json/md need no external binary — always producible."""
    written = render_delta(
        _sample_delta(), tmp_path, title="t", formats=["dot", "json", "md"]
    )
    assert set(written) == {"dot", "json", "md"}
    assert (tmp_path / DOT_FILENAME).is_file()
    assert (tmp_path / JSON_FILENAME).is_file()
    assert (tmp_path / MARKDOWN_FILENAME).is_file()


def test_render_delta_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError, match="Unknown output format"):
        render_delta(_sample_delta(), tmp_path, title="t", formats=["json", "gif"])


def test_render_delta_rejects_empty_formats(tmp_path):
    with pytest.raises(ValueError, match="No output formats"):
        render_delta(_sample_delta(), tmp_path, title="t", formats=[])


def test_render_delta_default_is_all_formats(tmp_path):
    if not _HAS_DOT:
        # Without the binary, svg/png raise — assert that loudly instead.
        with pytest.raises(GraphvizNotFoundError):
            render_delta(_sample_delta(), tmp_path, title="t")
        return
    written = render_delta(_sample_delta(), tmp_path, title="t")
    assert set(written) == set(ALL_FORMATS)
    for name in (DOT_FILENAME, JSON_FILENAME, MARKDOWN_FILENAME, SVG_FILENAME, PNG_FILENAME):
        assert (tmp_path / name).is_file()


@pytest.mark.skipif(_HAS_DOT, reason="dot binary is present; missing-binary path not exercised")
def test_svg_without_binary_raises_actionable_error(tmp_path):
    with pytest.raises(GraphvizNotFoundError, match="choco install graphviz"):
        render_delta(_sample_delta(), tmp_path, title="t", formats=["svg"])
    # json/md still produced alongside would be, but here only svg requested.


@pytest.mark.skipif(not _HAS_DOT, reason="requires the Graphviz dot binary")
def test_svg_and_png_render_when_binary_present(tmp_path):
    written = render_delta(
        _sample_delta(), tmp_path, title="t", formats=["svg", "png"]
    )
    assert written["svg"].is_file() and written["svg"].suffix == ".svg"
    assert written["png"].is_file() and written["png"].suffix == ".png"
    # SVG is XML text; PNG carries the PNG magic bytes.
    assert written["svg"].read_text(encoding="utf-8").lstrip().startswith("<")
    assert written["png"].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------- #
# Empty delta renders cleanly
# --------------------------------------------------------------------------- #


def test_empty_delta_renders_dot(tmp_path):
    graph = Graph.of({"a", "b"}, {("a", "b")})
    delta = compute_delta(graph, graph)
    assert delta.is_empty
    written = render_delta(delta, tmp_path, title="noop", formats=["dot", "json", "md"])
    dot = written["dot"].read_text(encoding="utf-8")
    # The single unchanged edge is present, dimmed; no green/red edges exist.
    assert '"a" -> "b" [color="#9aa7b0"' in dot
    assert "#2e7d32" not in dot.split("subgraph cluster_legend")[0]  # no added edges/nodes

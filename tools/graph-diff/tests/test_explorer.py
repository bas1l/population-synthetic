"""Tests for the self-contained HTML explorer emitter.

No browser is needed: the assertions inspect the generated HTML text. They prove
the dataset is embedded, every node id and status class is present, the SVG +
panel scaffold exists, and — crucially — the file carries ZERO external
references (the self-contained/offline guarantee).
"""

from __future__ import annotations

import re

from graphdiff.diff import Delta
from graphdiff.explorer import HTML_FILENAME, render_html, write_html
from graphdiff.sources import ModuleSource


def _sample_delta() -> Delta:
    return Delta(
        added_nodes=frozenset({"pkg.new"}),
        removed_nodes=frozenset({"pkg.gone"}),
        unchanged_nodes=frozenset({"pkg", "pkg.core"}),
        added_edges=frozenset({("pkg.new", "pkg.core")}),
        removed_edges=frozenset({("pkg.gone", "pkg.core")}),
        unchanged_edges=frozenset({("pkg.core", "pkg")}),
    )


def _sources():
    head = {
        "pkg": ModuleSource("pkg", "src/pkg/__init__.py", "", [], 0),
        "pkg.core": ModuleSource(
            "pkg.core", "src/pkg/core.py", "VALUE = 2\n", ["def go() -> int"], 1
        ),
        "pkg.new": ModuleSource(
            "pkg.new", "src/pkg/new.py", "import x\nA = 1\n", ["class New"], 2
        ),
    }
    base = {
        "pkg": ModuleSource("pkg", "src/pkg/__init__.py", "", [], 0),
        "pkg.core": ModuleSource(
            "pkg.core", "src/pkg/core.py", "VALUE = 1\n", ["def go() -> int"], 1
        ),
        "pkg.gone": ModuleSource(
            "pkg.gone", "src/pkg/gone.py", "OLD = 1\n", ["def old()"], 1
        ),
    }
    return base, head


def test_render_html_contains_every_node_id():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "base -> head")
    for node in ["pkg", "pkg.core", "pkg.new", "pkg.gone"]:
        assert node in doc


def test_render_html_contains_status_classes():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "t")
    assert "status-added" in doc
    assert "status-removed" in doc
    assert "status-unchanged" in doc


def test_render_html_embeds_json_dataset():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "t")
    assert '<script type="application/json" id="graph-data">' in doc
    # The added module's precomputed diff and a signature must be embedded.
    assert "unified_diff" in doc
    assert "class New" in doc


def test_render_html_has_svg_and_panel_scaffold():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "t")
    assert "<svg" in doc
    assert 'id="panel"' in doc
    assert 'id="graph-data"' in doc


def test_render_html_is_self_contained_no_external_refs():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "t")
    # No absolute http(s) URLs anywhere in the file.
    assert "http://" not in doc
    assert "https://" not in doc
    # No src=/href= attributes pointing anywhere (we use none at all).
    assert re.search(r'\bsrc\s*=', doc) is None
    assert re.search(r'\bhref\s*=', doc) is None


def test_write_html_creates_file(tmp_path):
    base, head = _sources()
    path = write_html(_sample_delta(), base, head, tmp_path, "t")
    assert path.name == HTML_FILENAME
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_added_module_has_nonempty_diff():
    base, head = _sources()
    doc = render_html(_sample_delta(), base, head, "t")
    # pkg.new is absent at base → its diff must show the added source lines.
    assert "+import x" in doc or "+A = 1" in doc

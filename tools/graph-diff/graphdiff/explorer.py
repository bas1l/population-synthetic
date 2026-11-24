"""explorer — serialise a Delta + per-ref sources into ONE self-contained HTML.

Responsibility
--------------
Given a computed :class:`~graphdiff.diff.Delta` and the base/head source maps
(from :func:`graphdiff.sources.capture_sources`), build a single
``graph_explorer.html`` that embeds the whole dataset and an inlined vanilla-JS
force-directed renderer: pan the background, wheel-zoom, drag nodes, and click a
node to open a detail panel showing its signatures, full head source, and a
base→head unified diff. The full import graph is drawn with the delta
highlighted (added=green, removed=red, unchanged=grey).

Must NOT know about
-------------------
- git (refs, worktrees),
- grimp or any import-graph extraction,
- how the delta or the sources were captured.

Self-contained guarantee
------------------------
The emitted HTML embeds all data, CSS, and JS inline — no server, no CDN, no
vendored third-party library, and NO external ``src``/``href`` to any http(s)
host. It opens offline by double-click and is copyable to any repo. The SVG
skeleton is emitted statically (elements created in Python, animated by JS via
``setAttribute``), so the renderer never needs the SVG-namespace URL and the
file stays free of any external-looking reference in its own chrome.

Output is deterministic: nodes and edges are sorted before embedding.
"""

from __future__ import annotations

import difflib
import html
import json
from pathlib import Path

from graphdiff.diff import Delta
from graphdiff.sources import ModuleSource

HTML_FILENAME = "graph_explorer.html"

# Colour-blind-friendly palette, consistent with graphdiff.render's SVG output.
_ADDED_COLOR = "#2e7d32"
_REMOVED_COLOR = "#c62828"
_UNCHANGED_COLOR = "#9aa7b0"
_ADDED_FILL = "#d6ecd6"
_REMOVED_FILL = "#f6dcdc"
_UNCHANGED_FILL = "#eceff1"


# --------------------------------------------------------------------------- #
# Dataset assembly
# --------------------------------------------------------------------------- #


def _node_status(node: str, delta: Delta) -> str:
    if node in delta.added_nodes:
        return "added"
    if node in delta.removed_nodes:
        return "removed"
    return "unchanged"


def _edge_status(edge: tuple[str, str], delta: Delta) -> str:
    if edge in delta.added_edges:
        return "added"
    if edge in delta.removed_edges:
        return "removed"
    return "unchanged"


def _unified_diff(base_source: str | None, head_source: str | None, path: str) -> str:
    """Precompute a base→head unified diff; empty string when textually identical."""
    base_lines = base_source.splitlines() if base_source else []
    head_lines = head_source.splitlines() if head_source else []
    if base_lines == head_lines:
        return ""
    diff = difflib.unified_diff(
        base_lines,
        head_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff)


def build_dataset(
    delta: Delta,
    base_sources: dict[str, ModuleSource],
    head_sources: dict[str, ModuleSource],
) -> dict:
    """Assemble the deterministic JSON-serialisable dataset embedded in the HTML.

    Nodes = the union of every module name across both graphs (via the delta node
    sets) and both source maps. Each node carries its delta status, signatures,
    head/base source, and a precomputed unified diff. Edges = the union of the
    delta edge sets, each with its status. Everything is sorted.
    """
    node_ids = (
        set(delta.added_nodes)
        | set(delta.removed_nodes)
        | set(delta.unchanged_nodes)
        | set(base_sources)
        | set(head_sources)
    )

    nodes: list[dict] = []
    for node in sorted(node_ids):
        head = head_sources.get(node)
        base = base_sources.get(node)
        signatures = (head or base).signatures if (head or base) else []
        path = head.path if head else (base.path if base else node)
        head_source = head.source if head else None
        base_source = base.source if base else None
        nodes.append(
            {
                "id": node,
                "label": node.split(".")[-1],
                "status": _node_status(node, delta),
                "signatures": list(signatures),
                "path": path,
                "head_source": head_source,
                "base_source": base_source,
                "unified_diff": _unified_diff(base_source, head_source, path),
            }
        )

    all_edges = (
        set(delta.added_edges) | set(delta.removed_edges) | set(delta.unchanged_edges)
    )
    edges: list[dict] = []
    for src, dst in sorted(all_edges):
        edges.append({"src": src, "dst": dst, "status": _edge_status((src, dst), delta)})

    return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------- #
# Static SVG skeleton (elements created here, animated by JS via setAttribute)
# --------------------------------------------------------------------------- #


def _svg_skeleton(dataset: dict) -> str:
    """Emit the static SVG: one <line> per edge, one <g><circle><text></g> per node.

    Positions are assigned by the JS force simulation at load; here every element
    is created so the JS never needs ``createElementNS`` (and thus never embeds
    the SVG-namespace URL).
    """
    index = {node["id"]: i for i, node in enumerate(dataset["nodes"])}

    edge_lines: list[str] = []
    for edge in dataset["edges"]:
        s = index.get(edge["src"])
        t = index.get(edge["dst"])
        if s is None or t is None:
            continue
        edge_lines.append(
            f'<line class="edge status-{edge["status"]}" '
            f'data-s="{s}" data-t="{t}"></line>'
        )

    node_groups: list[str] = []
    for i, node in enumerate(dataset["nodes"]):
        label = html.escape(node["label"])
        node_id = html.escape(node["id"], quote=True)
        node_groups.append(
            f'<g class="node status-{node["status"]}" data-idx="{i}" '
            f'data-id="{node_id}">'
            f'<circle r="7"></circle>'
            f'<text x="10" y="4">{label}</text>'
            f"</g>"
        )

    return (
        '<svg id="graph" preserveAspectRatio="xMidYMid meet">'
        '<g id="viewport">'
        f'<g id="edge-layer">{"".join(edge_lines)}</g>'
        f'<g id="node-layer">{"".join(node_groups)}</g>'
        "</g>"
        "</svg>"
    )


# --------------------------------------------------------------------------- #
# Inlined CSS + JS (no external references)
# --------------------------------------------------------------------------- #

_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; }
#app { display: flex; height: 100vh; overflow: hidden; }
#graph-wrap { position: relative; flex: 1 1 auto; min-width: 0; background: #fafbfc; }
#graph { width: 100%; height: 100%; display: block; cursor: grab; }
#graph.panning { cursor: grabbing; }
#header { position: absolute; top: 10px; left: 14px; z-index: 5; font-size: 13px; color: #37474f;
          background: rgba(255,255,255,0.85); padding: 6px 10px; border-radius: 6px; max-width: 60%; }
#header b { color: #1b1b1b; }
#legend { position: absolute; bottom: 12px; left: 14px; z-index: 5; background: rgba(255,255,255,0.9);
          border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 10px; font-size: 12px; }
#legend div { display: flex; align-items: center; margin: 2px 0; }
#legend .swatch { width: 14px; height: 14px; border-radius: 3px; margin-right: 7px; border: 2px solid; }
.node text { font-size: 10px; fill: #1b1b1b; pointer-events: none; user-select: none; }
.node circle { cursor: pointer; stroke-width: 2px; }
.node.status-added circle    { fill: %ADDED_FILL%; stroke: %ADDED_COLOR%; }
.node.status-removed circle  { fill: %REMOVED_FILL%; stroke: %REMOVED_COLOR%; stroke-dasharray: 3 2; }
.node.status-unchanged circle{ fill: %UNCHANGED_FILL%; stroke: %UNCHANGED_COLOR%; }
.node.selected circle { stroke-width: 4px; }
.edge { stroke-width: 1.2px; }
.edge.status-added    { stroke: %ADDED_COLOR%; stroke-width: 2px; }
.edge.status-removed  { stroke: %REMOVED_COLOR%; stroke-width: 2px; stroke-dasharray: 5 3; }
.edge.status-unchanged{ stroke: %UNCHANGED_COLOR%; stroke-width: 0.9px; }
#panel { flex: 0 0 420px; max-width: 46%; border-left: 1px solid #e0e0e0; background: #fff;
         overflow-y: auto; padding: 16px 18px; }
#panel.hidden { display: none; }
#panel h2 { font-size: 15px; margin: 0 0 4px; word-break: break-all; }
#panel .path { color: #78909c; font-size: 12px; margin-bottom: 10px; }
.badge { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11px;
         font-weight: 600; color: #fff; margin-bottom: 10px; }
.badge.status-added { background: %ADDED_COLOR%; }
.badge.status-removed { background: %REMOVED_COLOR%; }
.badge.status-unchanged { background: %UNCHANGED_COLOR%; }
#panel section { margin-top: 14px; }
#panel h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: #546e7a;
            border-bottom: 1px solid #eceff1; padding-bottom: 4px; margin: 0 0 8px; }
#panel ul.sigs { margin: 0; padding: 0; list-style: none; }
#panel ul.sigs li { font-family: Consolas, Menlo, monospace; font-size: 12px; padding: 2px 0;
                    white-space: pre; color: #263238; }
#panel .empty { color: #90a4ae; font-style: italic; font-size: 12px; }
#panel details { margin: 0; }
#panel summary { cursor: pointer; font-size: 12px; color: #1565c0; }
#panel pre.src { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 5px; padding: 10px;
                 overflow-x: auto; font-family: Consolas, Menlo, monospace; font-size: 11px; line-height: 1.4;
                 max-height: 360px; }
#panel pre.diff { border-radius: 5px; padding: 0; overflow-x: auto; font-family: Consolas, Menlo, monospace;
                  font-size: 11px; line-height: 1.45; background: #f6f8fa; border: 1px solid #e1e4e8; }
#panel pre.diff .ln { display: block; padding: 0 8px; white-space: pre; }
#panel pre.diff .add { background: #e6ffed; color: #22863a; }
#panel pre.diff .del { background: #ffeef0; color: #b31d28; }
#panel pre.diff .hunk { background: #f1f8ff; color: #1b6fb3; }
"""

_JS = r"""
(function () {
  var DATA = JSON.parse(document.getElementById("graph-data").textContent);
  var nodes = DATA.nodes, edges = DATA.edges, N = nodes.length;
  var svg = document.getElementById("graph");
  var viewport = document.getElementById("viewport");
  var nodeEls = Array.prototype.slice.call(document.querySelectorAll("#node-layer > g.node"));
  var edgeEls = Array.prototype.slice.call(document.querySelectorAll("#edge-layer > line.edge"));
  var idIndex = {};
  nodes.forEach(function (n, i) { idIndex[n.id] = i; });

  var W = 1200, H = 800;
  var pos = new Array(N);
  for (var i = 0; i < N; i++) {
    var a = i * 2.399963229;                // golden angle → even, deterministic spread
    var r = 24 * Math.sqrt(i + 1);
    pos[i] = { x: W / 2 + r * Math.cos(a), y: H / 2 + r * Math.sin(a) };
  }

  // Fruchterman–Reingold spring/repulsion layout, fixed ticks.
  var k = Math.sqrt((W * H) / Math.max(N, 1));
  var iterations = Math.min(500, 150 + N * 3);
  var temp = W / 6;
  for (var it = 0; it < iterations; it++) {
    var disp = new Array(N);
    for (var i = 0; i < N; i++) disp[i] = { x: 0, y: 0 };
    for (var i = 0; i < N; i++) {
      for (var j = i + 1; j < N; j++) {
        var dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
        var d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        var f = (k * k) / d, ux = dx / d, uy = dy / d;
        disp[i].x += ux * f; disp[i].y += uy * f;
        disp[j].x -= ux * f; disp[j].y -= uy * f;
      }
    }
    for (var e = 0; e < edges.length; e++) {
      var s = idIndex[edges[e].src], t = idIndex[edges[e].dst];
      if (s === undefined || t === undefined || s === t) continue;
      var dx2 = pos[s].x - pos[t].x, dy2 = pos[s].y - pos[t].y;
      var d2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 0.01;
      var f2 = (d2 * d2) / k, ux2 = dx2 / d2, uy2 = dy2 / d2;
      disp[s].x -= ux2 * f2; disp[s].y -= uy2 * f2;
      disp[t].x += ux2 * f2; disp[t].y += uy2 * f2;
    }
    for (var i = 0; i < N; i++) {
      var dl = Math.sqrt(disp[i].x * disp[i].x + disp[i].y * disp[i].y) || 0.01;
      var lim = Math.min(dl, temp);
      pos[i].x += (disp[i].x / dl) * lim;
      pos[i].y += (disp[i].y / dl) * lim;
    }
    temp *= 0.95;
  }

  function applyPositions() {
    for (var i = 0; i < N; i++) {
      nodeEls[i].setAttribute("transform", "translate(" + pos[i].x + "," + pos[i].y + ")");
    }
    for (var e = 0; e < edgeEls.length; e++) {
      var s = +edgeEls[e].getAttribute("data-s"), t = +edgeEls[e].getAttribute("data-t");
      edgeEls[e].setAttribute("x1", pos[s].x); edgeEls[e].setAttribute("y1", pos[s].y);
      edgeEls[e].setAttribute("x2", pos[t].x); edgeEls[e].setAttribute("y2", pos[t].y);
    }
  }

  // Pan / zoom via a viewport transform, fitted to the laid-out graph on load.
  var view = { x: 0, y: 0, k: 1 };
  function updateView() {
    viewport.setAttribute("transform",
      "translate(" + view.x + "," + view.y + ") scale(" + view.k + ")");
  }
  function fit() {
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < N; i++) {
      if (pos[i].x < minX) minX = pos[i].x; if (pos[i].x > maxX) maxX = pos[i].x;
      if (pos[i].y < minY) minY = pos[i].y; if (pos[i].y > maxY) maxY = pos[i].y;
    }
    if (!isFinite(minX)) { minX = minY = 0; maxX = maxY = 1; }
    var rect = svg.getBoundingClientRect();
    var vw = rect.width || 800, vh = rect.height || 600;
    var gw = (maxX - minX) || 1, gh = (maxY - minY) || 1;
    view.k = Math.min(vw / (gw + 120), vh / (gh + 120), 1.4);
    view.x = vw / 2 - view.k * (minX + maxX) / 2;
    view.y = vh / 2 - view.k * (minY + maxY) / 2;
    updateView();
  }

  applyPositions();
  fit();

  // Interaction: background pan, wheel zoom, node drag, node click → panel.
  var dragNode = null, dragging = false, moved = 0;
  var last = { x: 0, y: 0 };

  svg.addEventListener("mousedown", function (ev) {
    var g = ev.target.closest ? ev.target.closest("g.node") : null;
    moved = 0;
    last = { x: ev.clientX, y: ev.clientY };
    if (g) {
      dragNode = +g.getAttribute("data-idx");
      ev.preventDefault();
    } else {
      dragging = true;
      svg.classList.add("panning");
    }
  });
  window.addEventListener("mousemove", function (ev) {
    var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
    if (dragNode === null && !dragging) return;
    moved += Math.abs(dx) + Math.abs(dy);
    last = { x: ev.clientX, y: ev.clientY };
    if (dragNode !== null) {
      pos[dragNode].x += dx / view.k;
      pos[dragNode].y += dy / view.k;
      applyPositions();
    } else if (dragging) {
      view.x += dx; view.y += dy; updateView();
    }
  });
  window.addEventListener("mouseup", function (ev) {
    if (dragNode !== null && moved < 4) selectNode(dragNode);
    dragNode = null; dragging = false; svg.classList.remove("panning");
  });
  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var rect = svg.getBoundingClientRect();
    var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    var factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
    var gx = (mx - view.x) / view.k, gy = (my - view.y) / view.k;
    view.k *= factor;
    view.x = mx - gx * view.k; view.y = my - gy * view.k;
    updateView();
  }, { passive: false });

  // Detail panel.
  var panel = document.getElementById("panel");
  var selectedEl = null;
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function renderDiff(text) {
    if (!text) return '<p class="empty">No textual change between refs.</p>';
    var out = ['<pre class="diff">'];
    text.split("\n").forEach(function (line) {
      var cls = "";
      if (line.indexOf("@@") === 0) cls = "hunk";
      else if (line.indexOf("+") === 0 && line.indexOf("+++") !== 0) cls = "add";
      else if (line.indexOf("-") === 0 && line.indexOf("---") !== 0) cls = "del";
      out.push('<span class="ln ' + cls + '">' + esc(line) + "</span>");
    });
    out.push("</pre>");
    return out.join("");
  }
  function selectNode(idx) {
    var n = nodes[idx];
    if (selectedEl) selectedEl.classList.remove("selected");
    selectedEl = nodeEls[idx]; selectedEl.classList.add("selected");

    var sigs = n.signatures.length
      ? '<ul class="sigs">' + n.signatures.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>"
      : '<p class="empty">No top-level functions or classes.</p>';
    var sourceBlock = (n.head_source != null)
      ? '<details><summary>Show head source (' + esc(n.path) +
        ')</summary><pre class="src">' + esc(n.head_source) + "</pre></details>"
      : '<p class="empty">No head-ref source (module removed).</p>';

    panel.innerHTML =
      '<h2>' + esc(n.id) + "</h2>" +
      '<div class="path">' + esc(n.path) + "</div>" +
      '<span class="badge status-' + n.status + '">' + n.status + "</span>" +
      '<section><h3>Signatures</h3>' + sigs + "</section>" +
      '<section><h3>Source</h3>' + sourceBlock + "</section>" +
      '<section><h3>Diff (base → head)</h3>' + renderDiff(n.unified_diff) + "</section>";
    panel.classList.remove("hidden");
  }

  window.addEventListener("resize", fit);
})();
"""


def _render_css() -> str:
    return (
        _CSS.replace("%ADDED_COLOR%", _ADDED_COLOR)
        .replace("%REMOVED_COLOR%", _REMOVED_COLOR)
        .replace("%UNCHANGED_COLOR%", _UNCHANGED_COLOR)
        .replace("%ADDED_FILL%", _ADDED_FILL)
        .replace("%REMOVED_FILL%", _REMOVED_FILL)
        .replace("%UNCHANGED_FILL%", _UNCHANGED_FILL)
    )


def _legend_html() -> str:
    def row(color: str, fill: str, label: str, dashed: bool = False) -> str:
        style = f"background:{fill};border-color:{color};"
        if dashed:
            style += "border-style:dashed;"
        return f'<div><span class="swatch" style="{style}"></span>{label}</div>'

    return (
        '<div id="legend">'
        + row(_ADDED_COLOR, _ADDED_FILL, "added")
        + row(_REMOVED_COLOR, _REMOVED_FILL, "removed", dashed=True)
        + row(_UNCHANGED_COLOR, _UNCHANGED_FILL, "unchanged")
        + "</div>"
    )


def render_html(
    delta: Delta,
    base_sources: dict[str, ModuleSource],
    head_sources: dict[str, ModuleSource],
    title: str,
) -> str:
    """Build the complete self-contained HTML document as a string."""
    dataset = build_dataset(delta, base_sources, head_sources)
    data_json = json.dumps(dataset, sort_keys=True, ensure_ascii=False)
    # Neutralise any literal "</" so an embedded source can never break out of
    # the <script> block; the browser un-escapes "<\/" back to "</" on parse.
    data_json = data_json.replace("</", "<\\/")

    safe_title = html.escape(title)
    header = (
        f'<div id="header"><b>graph-diff explorer</b><br>{safe_title} &mdash; '
        f"+{delta.added_node_count} / -{delta.removed_node_count} nodes, "
        f"+{delta.added_edge_count} / -{delta.removed_edge_count} edges</div>"
    )

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>graph-diff explorer: {safe_title}</title>",
        f"<style>{_render_css()}</style>",
        "</head>",
        "<body>",
        '<div id="app">',
        '<div id="graph-wrap">',
        header,
        _svg_skeleton(dataset),
        _legend_html(),
        "</div>",
        '<div id="panel" class="hidden"></div>',
        "</div>",
        f'<script type="application/json" id="graph-data">{data_json}</script>',
        f"<script>{_JS}</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def write_html(
    delta: Delta,
    base_sources: dict[str, ModuleSource],
    head_sources: dict[str, ModuleSource],
    out_dir: Path | str,
    title: str,
) -> Path:
    """Write ``graph_explorer.html`` into ``out_dir`` and return its path.

    Parameters
    ----------
    delta:
        The computed structural difference to visualise.
    base_sources / head_sources:
        ``{module -> ModuleSource}`` maps captured at the base and head refs.
    out_dir:
        Directory to write into (created if absent).
    title:
        Human-readable title embedded in the page.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / HTML_FILENAME
    path.write_text(render_html(delta, base_sources, head_sources, title), encoding="utf-8")
    return path

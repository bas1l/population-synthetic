"""render — serialise a computed Delta to on-disk artifacts.

Responsibility
--------------
Take a :class:`~graphdiff.diff.Delta` and write human- and machine-readable
representations of it: a JSON edge/node-set dump and a Markdown summary that
reports counts AND explicitly enumerates every added/removed edge and node.
Output is deterministic (everything sorted) so artifacts diff cleanly.

Must NOT know about
-------------------
- git (refs, worktrees),
- grimp or any import-graph extraction,
- how the delta was computed (it receives a finished ``Delta``).

This module is the terminal, side-effecting sink of the pipeline: it renders
finished data and writes files. It computes nothing about the graph itself.

Artifacts
---------
Five formats, any subset selectable via :func:`render_delta`:

- ``json`` — full node/edge sets (machine-readable),
- ``md``   — human summary with counts and full enumerations,
- ``dot``  — Graphviz source of the colour-coded delta (needs no external binary),
- ``svg`` / ``png`` — the ``dot`` source rendered by the Graphviz ``dot``
  executable (300 dpi for PNG). If ``dot`` is not on PATH and svg/png are
  requested, a clear, actionable :class:`GraphvizNotFoundError` is raised; the
  json/md/dot artifacts never need it.

Colour is reinforced with line style (added = solid, removed = dashed,
unchanged = thin/dimmed) so the diagram stays legible without relying on the
red/green distinction alone — a colour-blind-friendly redundant encoding in the
spirit of ``scripts/dev/draw_generation_dags.py``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from graphdiff.diff import Delta, Edge, Node

# Artifact filenames are fixed and deterministic per output directory.
JSON_FILENAME = "graph_delta.json"
MARKDOWN_FILENAME = "graph_delta.md"
DOT_FILENAME = "graph_delta.dot"
SVG_FILENAME = "graph_delta.svg"
PNG_FILENAME = "graph_delta.png"

# Every format this renderer can emit, in a stable, documented order.
ALL_FORMATS: tuple[str, ...] = ("dot", "svg", "png", "json", "md")

# PNG raster resolution (SVG is vector; dpi is a no-op there).
_RASTER_DPI = "300"

# --------------------------------------------------------------------------- #
# Delta palette — colour-blind-friendly, muted, style-reinforced.
# Kept local to this module (the tool is standalone) but chosen in the spirit of
# the palette in scripts/dev/draw_generation_dags.py.
# --------------------------------------------------------------------------- #
_ADDED_COLOR = "#2e7d32"      # green  — added edges / node outline
_REMOVED_COLOR = "#c62828"    # red    — removed edges / node outline
_UNCHANGED_COLOR = "#9aa7b0"  # grey   — unchanged edges / node outline (dimmed)

_ADDED_NODE_FILL = "#d6ecd6"      # light green
_REMOVED_NODE_FILL = "#f6dcdc"    # light red
_UNCHANGED_NODE_FILL = "#eceff1"  # light grey

_NODE_TEXT = "#1b1b1b"            # dark text on the light added/removed fills
_UNCHANGED_TEXT = "#37474f"       # slightly muted text on the grey fill


class GraphvizNotFoundError(RuntimeError):
    """Raised when SVG/PNG rendering is requested but the ``dot`` binary is absent."""


def _sorted_nodes(nodes: frozenset[Node]) -> list[Node]:
    return sorted(nodes)


def _sorted_edges(edges: frozenset[Edge]) -> list[list[str]]:
    """Sort edges deterministically and render each as a ``[src, dst]`` list."""
    return [[src, dst] for src, dst in sorted(edges)]


def _delta_to_dict(delta: Delta, title: str) -> dict:
    """Build the deterministic, JSON-serialisable view of a Delta."""
    return {
        "title": title,
        "summary": {
            "added_nodes": delta.added_node_count,
            "removed_nodes": delta.removed_node_count,
            "unchanged_nodes": delta.unchanged_node_count,
            "added_edges": delta.added_edge_count,
            "removed_edges": delta.removed_edge_count,
            "unchanged_edges": delta.unchanged_edge_count,
            "is_empty": delta.is_empty,
        },
        "nodes": {
            "added": _sorted_nodes(delta.added_nodes),
            "removed": _sorted_nodes(delta.removed_nodes),
            "unchanged": _sorted_nodes(delta.unchanged_nodes),
        },
        "edges": {
            "added": _sorted_edges(delta.added_edges),
            "removed": _sorted_edges(delta.removed_edges),
            "unchanged": _sorted_edges(delta.unchanged_edges),
        },
    }


def write_json(delta: Delta, out_dir: Path, title: str) -> Path:
    """Write the full node/edge sets of ``delta`` as a JSON artifact.

    Creates ``out_dir`` if needed. Returns the path written. UTF-8, sorted
    keys, trailing newline — deterministic byte output for a given delta.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / JSON_FILENAME
    payload = _delta_to_dict(delta, title)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _md_edge_lines(edges: frozenset[Edge]) -> list[str]:
    if not edges:
        return ["_none_"]
    return [f"- `{src}` → `{dst}`" for src, dst in sorted(edges)]


def _md_node_lines(nodes: frozenset[Node]) -> list[str]:
    if not nodes:
        return ["_none_"]
    return [f"- `{node}`" for node in sorted(nodes)]


def write_markdown(delta: Delta, out_dir: Path, title: str) -> Path:
    """Write a Markdown summary of ``delta`` with counts and full enumerations.

    Creates ``out_dir`` if needed. Returns the path written. Every added and
    removed edge and node is listed explicitly (deterministic, sorted). UTF-8.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MARKDOWN_FILENAME

    lines: list[str] = []
    lines.append(f"# Graph diff: {title}")
    lines.append("")
    if delta.is_empty:
        lines.append("**No structural change** — base and head graphs are identical.")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Added | Removed | Unchanged |")
    lines.append("|--------|------:|--------:|----------:|")
    lines.append(
        f"| Nodes | {delta.added_node_count} | "
        f"{delta.removed_node_count} | {delta.unchanged_node_count} |"
    )
    lines.append(
        f"| Edges | {delta.added_edge_count} | "
        f"{delta.removed_edge_count} | {delta.unchanged_edge_count} |"
    )
    lines.append("")

    lines.append(f"## Added edges ({delta.added_edge_count})")
    lines.append("")
    lines.extend(_md_edge_lines(delta.added_edges))
    lines.append("")

    lines.append(f"## Removed edges ({delta.removed_edge_count})")
    lines.append("")
    lines.extend(_md_edge_lines(delta.removed_edges))
    lines.append("")

    lines.append(f"## Added nodes ({delta.added_node_count})")
    lines.append("")
    lines.extend(_md_node_lines(delta.added_nodes))
    lines.append("")

    lines.append(f"## Removed nodes ({delta.removed_node_count})")
    lines.append("")
    lines.extend(_md_node_lines(delta.removed_nodes))
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Graphviz .dot source + SVG/PNG rendering
# --------------------------------------------------------------------------- #


def _dot_id(name: str) -> str:
    """Quote a node identifier for DOT (dotted module names are not bare ids)."""
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _legend_lines() -> list[str]:
    """A self-contained legend cluster documenting the node/edge encoding."""
    return [
        "  subgraph cluster_legend {",
        '    label="Legend"; fontname="Helvetica"; fontsize=12;',
        '    style=dotted; color="#b0b0b0";',
        f'    "legend_added_node" [label="added node", '
        f'fillcolor="{_ADDED_NODE_FILL}", color="{_ADDED_COLOR}", '
        f'penwidth=2.0, fontcolor="{_NODE_TEXT}", fontsize=9];',
        f'    "legend_removed_node" [label="removed node", '
        f'fillcolor="{_REMOVED_NODE_FILL}", color="{_REMOVED_COLOR}", '
        f'penwidth=2.0, style="rounded,filled,dashed", '
        f'fontcolor="{_NODE_TEXT}", fontsize=9];',
        f'    "legend_unchanged_node" [label="unchanged node", '
        f'fillcolor="{_UNCHANGED_NODE_FILL}", color="{_UNCHANGED_COLOR}", '
        f'fontcolor="{_UNCHANGED_TEXT}", fontsize=9];',
        f'    "legend_a1" [label="", shape=point, color="{_ADDED_COLOR}", width=0.02];',
        f'    "legend_a2" [label="", shape=point, color="{_ADDED_COLOR}", width=0.02];',
        f'    "legend_a1" -> "legend_a2" [color="{_ADDED_COLOR}", penwidth=2.2, '
        f'label="added edge", fontsize=9, fontcolor="{_ADDED_COLOR}"];',
        f'    "legend_r1" [label="", shape=point, color="{_REMOVED_COLOR}", width=0.02];',
        f'    "legend_r2" [label="", shape=point, color="{_REMOVED_COLOR}", width=0.02];',
        f'    "legend_r1" -> "legend_r2" [color="{_REMOVED_COLOR}", penwidth=2.2, '
        f'style=dashed, label="removed edge", fontsize=9, fontcolor="{_REMOVED_COLOR}"];',
        f'    "legend_u1" [label="", shape=point, color="{_UNCHANGED_COLOR}", width=0.02];',
        f'    "legend_u2" [label="", shape=point, color="{_UNCHANGED_COLOR}", width=0.02];',
        f'    "legend_u1" -> "legend_u2" [color="{_UNCHANGED_COLOR}", penwidth=0.9, '
        f'label="unchanged edge", fontsize=9, fontcolor="{_UNCHANGED_COLOR}"];',
        "  }",
    ]


def build_dot(delta: Delta, title: str) -> str:
    """Build the deterministic Graphviz ``.dot`` source for ``delta``.

    Edges are coloured green (added), red (removed), and grey/dimmed
    (unchanged), with line style reinforcing colour. Added and removed nodes are
    visually distinguished (green vs red outline/fill; removed nodes dashed).
    Nodes and edges are emitted in sorted order so the source is byte-stable.
    """
    label = f"Graph diff: {title}"
    lines: list[str] = [
        f"// {label}",
        "digraph graph_delta {",
        "  rankdir=LR;",
        '  labelloc="t";',
        f"  label={_dot_id(label)};",
        f'  graph [dpi={_RASTER_DPI}, fontname="Helvetica", fontsize=16];',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", '
        'fontsize=11, margin="0.12,0.07"];',
        '  edge [fontname="Helvetica"];',
        "",
    ]

    # Nodes — added, then removed, then unchanged; each group sorted.
    for node in sorted(delta.added_nodes):
        lines.append(
            f"  {_dot_id(node)} [fillcolor=\"{_ADDED_NODE_FILL}\", "
            f'color="{_ADDED_COLOR}", penwidth=2.0, fontcolor="{_NODE_TEXT}"];'
        )
    for node in sorted(delta.removed_nodes):
        lines.append(
            f"  {_dot_id(node)} [fillcolor=\"{_REMOVED_NODE_FILL}\", "
            f'color="{_REMOVED_COLOR}", penwidth=2.0, '
            f'style="rounded,filled,dashed", fontcolor="{_NODE_TEXT}"];'
        )
    for node in sorted(delta.unchanged_nodes):
        lines.append(
            f"  {_dot_id(node)} [fillcolor=\"{_UNCHANGED_NODE_FILL}\", "
            f'color="{_UNCHANGED_COLOR}", fontcolor="{_UNCHANGED_TEXT}"];'
        )
    lines.append("")

    # Edges — added (solid green), removed (dashed red), unchanged (thin grey).
    for src, dst in sorted(delta.added_edges):
        lines.append(
            f"  {_dot_id(src)} -> {_dot_id(dst)} "
            f'[color="{_ADDED_COLOR}", penwidth=2.2];'
        )
    for src, dst in sorted(delta.removed_edges):
        lines.append(
            f"  {_dot_id(src)} -> {_dot_id(dst)} "
            f'[color="{_REMOVED_COLOR}", penwidth=2.2, style=dashed];'
        )
    for src, dst in sorted(delta.unchanged_edges):
        lines.append(
            f"  {_dot_id(src)} -> {_dot_id(dst)} "
            f'[color="{_UNCHANGED_COLOR}", penwidth=0.9];'
        )
    lines.append("")
    lines.extend(_legend_lines())
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot(delta: Delta, out_dir: Path, title: str) -> Path:
    """Write the Graphviz ``.dot`` source of ``delta``. Needs no external binary."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / DOT_FILENAME
    path.write_text(build_dot(delta, title), encoding="utf-8")
    return path


def _require_dot_binary(fmt: str) -> None:
    """Raise a clear, actionable error if the Graphviz ``dot`` binary is absent."""
    if shutil.which("dot") is None:
        raise GraphvizNotFoundError(
            f"The Graphviz 'dot' executable was not found on PATH, so the "
            f"{fmt.upper()} diagram cannot be rendered. Install the Graphviz "
            "system package and make sure 'dot' is on PATH — "
            "Windows: `choco install graphviz`; macOS: `brew install graphviz`; "
            "Debian/Ubuntu: `apt-get install graphviz`. "
            "The .dot, JSON and Markdown artifacts do not require it."
        )


def _render_image(dot_source: str, out_dir: Path, fmt: str) -> Path:
    """Render ``dot_source`` to ``fmt`` (svg/png) via the Graphviz ``dot`` binary."""
    _require_dot_binary(fmt)
    # Imported lazily so json/md/dot-only runs never need the python binding.
    import graphviz  # noqa: PLC0415 — optional dependency, only for raster/vector

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = SVG_FILENAME if fmt == "svg" else PNG_FILENAME
    path = out_dir / filename
    source = graphviz.Source(dot_source)
    try:
        data = source.pipe(format=fmt)
        # Some Graphviz builds ship a broken default (cairo) PNG writer that
        # emits zero bytes without erroring; fall back to the gd raster device.
        if fmt == "png" and not data:
            data = source.pipe(format="png", renderer="gd", formatter="gd")
    except graphviz.ExecutableNotFound as exc:  # defensive: binary vanished mid-run
        _require_dot_binary(fmt)  # re-raise as our actionable error
        raise GraphvizNotFoundError(str(exc)) from exc  # pragma: no cover
    if not data:
        raise RuntimeError(
            f"Graphviz produced an empty {fmt.upper()} for the delta — the local "
            "Graphviz install may have a broken raster renderer. The .dot and SVG "
            "artifacts are unaffected; try reinstalling Graphviz."
        )
    path.write_bytes(data)
    return path


def _normalise_formats(formats: object) -> set[str]:
    """Validate and de-duplicate a requested-format collection; fail loudly on unknown."""
    requested = {str(f).strip().lower() for f in formats if str(f).strip()}
    unknown = requested - set(ALL_FORMATS)
    if unknown:
        raise ValueError(
            f"Unknown output format(s): {sorted(unknown)}. "
            f"Valid formats are: {list(ALL_FORMATS)}."
        )
    if not requested:
        raise ValueError(
            f"No output formats requested. Choose a subset of {list(ALL_FORMATS)}."
        )
    return requested


def render_delta(
    delta: Delta,
    out_dir: Path | str,
    title: str,
    formats: object = ALL_FORMATS,
) -> dict[str, Path]:
    """Write whichever of ``{dot, svg, png, json, md}`` are requested for ``delta``.

    Parameters
    ----------
    delta:
        The computed structural difference to serialise.
    out_dir:
        Directory to write artifacts into (created if absent).
    title:
        Human-readable title embedded in every artifact.
    formats:
        Iterable of format names (subset of :data:`ALL_FORMATS`). Defaults to all.

    Returns
    -------
    dict[str, Path]
        Mapping of each written format to the path produced.

    Raises
    ------
    ValueError
        If an unknown format is requested (fail-fast).
    GraphvizNotFoundError
        If svg/png are requested but the ``dot`` binary is not on PATH. The
        json/md/dot artifacts, if also requested, are still written first.
    """
    requested = _normalise_formats(formats)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    if "json" in requested:
        written["json"] = write_json(delta, out_dir, title)
    if "md" in requested:
        written["md"] = write_markdown(delta, out_dir, title)

    # Build the .dot source once if any Graphviz output is requested.
    dot_source: str | None = None
    if requested & {"dot", "svg", "png"}:
        dot_source = build_dot(delta, title)
    if "dot" in requested:
        path = out_dir / DOT_FILENAME
        path.write_text(dot_source or build_dot(delta, title), encoding="utf-8")
        written["dot"] = path
    for fmt in ("svg", "png"):
        if fmt in requested:
            assert dot_source is not None  # guaranteed by the branch above
            written[fmt] = _render_image(dot_source, out_dir, fmt)

    return written

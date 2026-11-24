#!/usr/bin/env python3
"""Render the claim DAG -- the logical skeleton of the study's published results.

The graph is authored in ``docs/claims/``: one ``leaves.yaml`` holding the shared
leaf layer (findings, assumptions, contexts) and one file per published result under
``results/`` holding that result's laws, derived claims and defeaters. Results share
leaves, so the object is a **multi-root DAG**, not a set of trees -- which is what
makes it possible to ask the question that matters most: *if this leaf is wrong,
which published claims must be withdrawn?*

For every root this emits into ``docs/claims/diagrams/``:

* ``claim_{short}.png`` / ``.svg`` -- the ancestor sub-DAG of that root, laid out in
  ranks with the leaves at the bottom and the claim on top (via ``save_figure``)
* ``claim_{short}.dot``            -- Graphviz source, for re-rendering at any size
* ``claim_{short}.mmd``            -- Mermaid source, for inline rendering in
                                     markdown, GitHub and HTML pages

and two indices covering all roots at once:

* ``_index/impact.csv``  -- every leaf and the roots that depend on it (the reverse
                            -dependency table; the global view is deliberately a
                            table, not a diagram -- see the note on legibility below)
* ``_index/ladder.csv``  -- every node with its rank, class, qualifier and premises

**Why the global view is a table.** Ghoniem, Fekete & Castagliola (InfoVis 2004)
found that above roughly twenty nodes an adjacency/matrix representation beats a
node-link diagram on every graph-reading task except path-finding. The whole claim
DAG is past that threshold; a single per-root sub-DAG is not, and path-tracing is
exactly what it is for. So the per-root view is drawn and the global view is tabulated.

This is a documentation renderer, not an analysis process: it consumes no run data
and produces no statistic, so it has no ``analysis_registry.yaml`` entry, no DAG node
and no GUI workflow task.

Run: ``python scripts/dev/render_claim_dag.py``
"""
from __future__ import annotations

import csv
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import yaml
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from population_synthetic.analysis.utils.figures import save_figure

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLAIMS_DIR = PROJECT_ROOT / "docs" / "claims"
OUT_DIR = CLAIMS_DIR / "diagrams"

#: Qualifier a leaf contributes when the weakest-link check walks through it. A
#: finding is as good as its artifact; an assumption is only ever as good as the
#: argument that was never made for it.
LEAF_QUALIFIER = {
    "finding": "established",
    "context": "established",
    "assumption:unargued": "weak",
    "assumption:addressed": "moderate",
    "assumption:unsupported": "weak",
    "assumption:conceded-false": "conjectural",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"claim-DAG source missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def load_graph() -> tuple[dict, list[dict], dict]:
    """Return ``(nodes, roots, style)`` for the whole multi-root DAG.

    ``nodes`` is one flat id -> record map across the leaf layer and every result
    file; a leaf cited by several results appears once. Ids must be globally unique
    except for law ids, which are namespaced per root, since ``L1`` in two different
    results is two different rules.
    """
    style = _read_yaml(CLAIMS_DIR / "_style.yaml")
    leaves = _read_yaml(CLAIMS_DIR / "leaves.yaml")

    nodes: dict[str, dict] = {}
    for nid, rec in (leaves.get("nodes") or {}).items():
        nodes[nid] = dict(rec, id=nid, source="leaves")

    result_files = sorted((CLAIMS_DIR / "results").glob("*.yaml"))
    if not result_files:
        raise FileNotFoundError(f"no result files under {CLAIMS_DIR / 'results'}")

    roots: list[dict] = []
    for path in result_files:
        doc = _read_yaml(path)
        root_id = doc.get("root")
        if not root_id:
            raise ValueError(f"{path} declares no `root`")
        meta = doc.get("meta") or {}
        short = meta.get("short") or path.stem
        roots.append({"id": root_id, "short": short, "meta": meta, "path": path})

        for nid, rec in (doc.get("nodes") or {}).items():
            if nid in nodes:
                raise ValueError(f"duplicate node id {nid!r} ({path} vs earlier source)")
            nodes[nid] = dict(rec, id=nid, source=short)

            law = rec.get("law")
            if law:
                law_id = f"{root_id}__{law['id']}"
                nodes[law_id] = dict(law, id=law_id, type="law", display=law["id"],
                                     source=short, licenses=nid)
    return nodes, roots, style


def build_edges(nodes: dict) -> list[tuple[str, str, str]]:
    """Derivation, context and attack edges.

    A derived node's premises feed its *law* node and the law feeds the node, so the
    rule sits visibly on the path rather than being an unlabelled arrow. An
    undercutting defeater attacks that law node -- it denies that the rule applies --
    while rebutting and undermining defeaters attack the claim or finding itself.
    """
    edges: list[tuple[str, str, str]] = []
    for nid, rec in nodes.items():
        law = rec.get("law")
        if law:
            law_id = f"{_root_of(rec, nodes)}__{law['id']}"
            for premise in rec.get("from") or []:
                if premise not in nodes:
                    raise ValueError(f"{nid} cites unknown premise {premise!r}")
                edges.append((premise, law_id, "premise"))
            edges.append((law_id, nid, "law_out"))
        for ctx in rec.get("context") or []:
            if ctx not in nodes:
                raise ValueError(f"{nid} cites unknown context {ctx!r}")
            edges.append((ctx, nid, "context"))
        if rec.get("type") == "defeater":
            target = rec.get("target")
            if target not in nodes:
                raise ValueError(f"defeater {nid} targets unknown node {target!r}")
            if rec.get("kind") == "undercutting":
                target_law = nodes[target].get("law")
                if not target_law:
                    raise ValueError(f"{nid} undercuts {target}, which declares no law")
                target = f"{_root_of(nodes[target], nodes)}__{target_law['id']}"
            edges.append((nid, target, "attack"))
            for ev in rec.get("evidence") or []:
                if ev not in nodes:
                    raise ValueError(f"defeater {nid} cites unknown evidence {ev!r}")
                edges.append((ev, nid, "evidence"))
    return edges


def _root_of(rec: dict, nodes: dict) -> str:
    """The root id owning *rec*, found from its source file's root node."""
    for nid, other in nodes.items():
        if other.get("source") == rec.get("source") and other.get("type") == "claim":
            return nid
    raise ValueError(f"no root claim found for source {rec.get('source')!r}")


# ---------------------------------------------------------------------------
# Sub-DAG extraction and layout
# ---------------------------------------------------------------------------
DERIV = {"premise", "law_out"}


def ancestors(root: str, edges: list) -> set[str]:
    """Every node reachable *backwards* from *root* along derivation edges.

    This is ``deps(root)`` in the build-system vocabulary -- the ancestor sub-DAG
    that answers "what does this claim rest on".
    """
    parents: dict[str, list[str]] = {}
    for src, dst, kind in edges:
        if kind in DERIV:
            parents.setdefault(dst, []).append(src)
    seen, stack = {root}, [root]
    while stack:
        for parent in parents.get(stack.pop(), []):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def sub_members(root: str, edges: list) -> set[str]:
    """The ancestor sub-DAG of *root*, plus the annotations hanging off it.

    Contexts and defeaters are not premises, so they are invisible to :func:`ancestors`
    -- but a scope restriction or an open doubt attached to a node inside the sub-DAG
    belongs to that result and must travel with it, both onto the diagram and into the
    impact table. Without this a context reads as depended-on by nothing at all.
    """
    members = ancestors(root, edges)
    annotations = {"context", "attack", "evidence"}
    changed = True
    while changed:
        changed = False
        for src, dst, kind in edges:
            # Only ever pull an annotation IN toward the sub-DAG: a context or a
            # defeater is included because it points at something already here. The
            # symmetric rule looks harmless and is not -- a context shared between two
            # results drags the other result's nodes in through their common leaf,
            # stripped of their own support, so they render as unsupported claims.
            if kind in annotations and dst in members and src not in members:
                members |= {src} | ancestors(src, edges)
                changed = True
    return members


def rank_nodes(members: set[str], edges: list, nodes: dict) -> dict[str, int]:
    """Longest-path rank from the leaves, so every edge points strictly upward.

    Contexts and defeaters are annotations rather than derivation steps, so they are
    pinned to the rank of what they annotate instead of floating to the bottom.
    """
    parents = {n: [] for n in members}
    for src, dst, kind in edges:
        if kind in DERIV and src in members and dst in members:
            parents[dst].append(src)

    rank: dict[str, int] = {}

    def resolve(n: str, trail: frozenset = frozenset()) -> int:
        if n in rank:
            return rank[n]
        if n in trail:
            raise ValueError(f"cycle in the claim DAG at {n!r}")
        ps = parents.get(n) or []
        rank[n] = 0 if not ps else 1 + max(resolve(p, trail | {n}) for p in ps)
        return rank[n]

    for n in members:
        if nodes[n].get("type") not in ("context", "defeater"):
            resolve(n)

    for src, dst, kind in edges:
        if kind == "context" and src in members:
            rank[src] = max(rank.get(dst, 0) - 1, 0)
        elif kind == "attack" and dst in members and src in members:
            rank[src] = rank.get(dst, 0)
    # A defeater carrying its own evidence must sit to the right of that evidence,
    # or its grounding edge points backwards across the whole figure.
    for src, dst, kind in edges:
        if kind == "evidence" and src in members and dst in members:
            rank[dst] = max(rank.get(dst, 0), rank.get(src, 0) + 1)
    return rank


def order_ranks(rank: dict[str, int], edges: list) -> dict[str, int]:
    """Barycentre ordering within each rank -- two passes up, two down.

    Crossing minimisation is NP-hard in general and irrelevant here: these sub-DAGs
    are ten to twenty nodes, where the barycentre heuristic is already at or near
    optimal and the remaining crossings are not what makes a diagram hard to read.
    """
    by_rank: dict[int, list[str]] = {}
    for n, r in rank.items():
        by_rank.setdefault(r, []).append(n)
    for r in by_rank:
        by_rank[r].sort()

    pos = {n: i for r in by_rank for i, n in enumerate(by_rank[r])}
    neighbours_up: dict[str, list[str]] = {}
    neighbours_down: dict[str, list[str]] = {}
    for src, dst, _kind in edges:
        if src in rank and dst in rank:
            neighbours_up.setdefault(dst, []).append(src)
            neighbours_down.setdefault(src, []).append(dst)

    def sweep(order: list[int], side: dict) -> None:
        for r in order:
            def key(n: str) -> tuple[float, str]:
                near = [pos[m] for m in side.get(n, []) if m in pos and rank[m] != r]
                return (sum(near) / len(near) if near else pos[n], n)
            by_rank[r].sort(key=key)
            for i, n in enumerate(by_rank[r]):
                pos[n] = i

    ranks_asc = sorted(by_rank)
    for _ in range(2):
        sweep(ranks_asc, neighbours_up)
        sweep(list(reversed(ranks_asc)), neighbours_down)
    return pos


# ---------------------------------------------------------------------------
# The Ladder Invariant
# ---------------------------------------------------------------------------
def check_grids(nodes: dict, roots: list, edges: list) -> None:
    """Raise if a result cites a leaf produced by a different grid.

    Two sweeps produced the numbers in ``leaves.yaml``. Sharing a leaf between them
    would put a dependency in the impact table that does not exist -- and the impact
    table's whole job is to answer "which published claims must be withdrawn", so a
    false edge there is worse than no table. Contexts are exempt: a scope restriction
    is not a measurement. This is malformed input, so it raises rather than reporting.
    """
    for root in roots:
        want = root["meta"].get("grid")
        if not want:
            raise ValueError(f"{root['path'].name} declares no `meta.grid`")
        for nid in sub_members(root["id"], edges):
            got = nodes[nid].get("grid")
            if got and got != want:
                raise ValueError(
                    f"{root['path'].name} (grid {want!r}) cites {nid!r} from grid {got!r}"
                )


def check_qualifiers(nodes: dict, style: dict) -> list[str]:
    """Report any node claiming more confidence than its weakest premise allows.

    Ascending a rung increases interpretive commitment and decreases certainty, so a
    derived node may never carry a qualifier stronger than the minimum over its own
    premises. A ladder whose confidence *grows* as it climbs is defective, and this
    turns that from a matter of taste into an arithmetic check.
    """
    order = style["qualifier_order"]
    findings = []
    for nid, rec in nodes.items():
        declared = rec.get("qualifier")
        if not declared or not rec.get("from"):
            continue
        if declared not in order:
            raise ValueError(f"{nid}: unknown qualifier {declared!r}")
        worst, worst_src = "established", None
        for premise in rec["from"]:
            p = nodes[premise]
            ptype = p.get("type")
            key = f"{ptype}:{p.get('status', 'unargued')}" if ptype == "assumption" else ptype
            q = p.get("qualifier") or LEAF_QUALIFIER.get(key, "weak")
            if order.index(q) > order.index(worst):
                worst, worst_src = q, premise
        if order.index(declared) < order.index(worst):
            findings.append(
                f"  {nid}: declares {declared!r} but its weakest premise "
                f"({worst_src}) supports at most {worst!r}"
            )
    return findings


# ---------------------------------------------------------------------------
# Matplotlib rendering
# ---------------------------------------------------------------------------
def _wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width)) if text else ""


def _body(rec: dict, lay: dict) -> str:
    width = lay["law_wrap_chars"] if rec.get("type") == "law" else lay["wrap_chars"]
    return _wrap(rec.get("text", ""), width)


def _box_size(rec: dict, lay: dict) -> tuple[float, float]:
    """Width by class, height by content -- so a long law is not clipped by its box.

    The first render sized every box alike and the multi-line laws overflowed theirs,
    which reads as a drawing bug and quietly hides the very sentence the rung turns on.
    """
    width = lay["law_w"] if rec.get("type") == "law" else lay["node_w"]
    lines = len(_body(rec, lay).splitlines()) or 1
    return width, max(lay["min_h"], lay["pad_h"] + lines * lay["line_h"])


def _decoration(rec: dict, style: dict) -> tuple[str, float, str | None, float, str]:
    """``(edgecolor, linewidth, hatch, alpha, label_suffix)`` for a node's status."""
    ntype = rec.get("type")
    if ntype == "assumption":
        d = style["assumption_status"][rec.get("status", "unargued")]
        return d["edge"], d["lw"], d["hatch"], 1.0, d["marker"]
    if ntype == "defeater":
        d = style["defeater_status"][rec.get("status", "uneliminated")]
        return d["edge"], d["lw"], d["hatch"], d["alpha"], d["marker"]
    return "#33333355", 1.1, None, 1.0, ""


def _anchor(cx, cy, w, h, ox, oy) -> tuple[float, float]:
    dx, dy = ox - cx, oy - cy
    if abs(dy) >= abs(dx):
        return (cx, cy + h / 2) if dy > 0 else (cx, cy - h / 2)
    return (cx + w / 2, cy) if dx > 0 else (cx - w / 2, cy)


def render_root(root: dict, nodes: dict, edges: list, style: dict) -> Path:
    import matplotlib.pyplot as plt

    lay, klass = style["layout"], style["node_class"]
    members = sub_members(root["id"], edges)
    sub = [(s, d, k) for s, d, k in edges if s in members and d in members]

    rank = rank_nodes(members, sub, nodes)
    pos = order_ranks(rank, sub)

    size = {n: _box_size(nodes[n], lay) for n in members}
    by_rank: dict[int, list[str]] = {}
    for n, r in rank.items():
        by_rank.setdefault(r, []).append(n)

    step_x = lay["node_w"] + lay["x_gap"]
    xy = {}
    for r, ns in sorted(by_rank.items()):
        ns.sort(key=lambda n: pos[n])
        span = sum(size[n][1] for n in ns) + lay["y_gap"] * (len(ns) - 1)
        cursor = span / 2
        for n in ns:
            h = size[n][1]
            xy[n] = (r * step_x, cursor - h / 2)
            cursor -= h + lay["y_gap"]

    half_h = max(abs(y) + size[n][1] / 2 for n, (_x, y) in xy.items())
    width = (max(by_rank) + 1) * step_x
    legend_rows = len({nodes[n]["type"] for n in members})
    fig, ax = plt.subplots(figsize=(max(width + 1.4, 12.0), max(2 * half_h + 3.4, 8.0)))
    ax.set_xlim(-lay["node_w"] / 2 - 0.7, width + 0.7)
    ax.set_ylim(-half_h - 1.1 - legend_rows * 0.30, half_h + 1.9)
    ax.axis("off")

    for src, dst, kind in sub:
        e = style["edge"][kind]
        p0 = _anchor(*xy[src], *size[src], *xy[dst])
        p1 = _anchor(*xy[dst], *size[dst], *xy[src])
        ls = e["style"] if isinstance(e["style"], str) else (e["style"][0], tuple(e["style"][1]))
        ax.add_patch(FancyArrowPatch(
            p0, p1, arrowstyle=e["arrow"], mutation_scale=12, shrinkA=1, shrinkB=1,
            connectionstyle="arc3,rad=0.03", color=e["color"], lw=e["lw"], ls=ls, zorder=2,
        ))

    for nid in members:
        rec = nodes[nid]
        ntype = rec.get("type")
        cls = klass[ntype]
        w, h = size[nid]
        x, y = xy[nid]
        ec, lw, hatch, alpha, suffix = _decoration(rec, style)
        box = dict(boxstyle="round,pad=0.02,rounding_size=0.10")
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h, linewidth=lw, edgecolor=ec,
            facecolor=cls["fill"], alpha=alpha, zorder=3, **box,
        ))
        if hatch:
            # Hatching goes on its own translucent layer under the text rather than
            # on the filled patch. Drawn on the fill it renders in the (dark) edge
            # colour straight through the label -- which made the conceded-false
            # assumptions and the open defeaters, the two node kinds a reader most
            # needs to read, the two least legible things in the figure.
            ax.add_patch(FancyBboxPatch(
                (x - w / 2, y - h / 2), w, h, linewidth=0, facecolor="none",
                edgecolor=ec, hatch=hatch, alpha=0.30 * alpha, zorder=3.5, **box,
            ))
        ax.text(x, y + h / 2 - 0.16, rec.get("display", nid) + suffix, ha="center",
                va="center", color=cls["text"], fontsize=8.4, fontweight="bold", zorder=4)
        ax.text(x, y - 0.10, _body(rec, lay), ha="center", va="center", color=cls["text"],
                fontsize=6.3, zorder=4, linespacing=1.3)
        if rec.get("qualifier"):
            ax.text(x + w / 2 - 0.07, y - h / 2 + 0.11, rec["qualifier"], ha="right",
                    va="center", color=cls["text"], fontsize=6.0, style="italic",
                    alpha=0.85, zorder=4)

    meta = root["meta"]
    mid = width / 2 - lay["node_w"] / 2
    ax.text(mid, half_h + 1.45, meta.get("title", root["id"]), ha="center", va="center",
            fontsize=15, fontweight="bold", color="#1b1b1b")
    ax.text(mid, half_h + 0.98, meta.get("statement", ""), ha="center", va="center",
            fontsize=9, color="#555555")

    legend = [(k, v) for k, v in klass.items()
              if any(nodes[n].get("type") == k for n in members)]
    left = -lay["node_w"] / 2 - 0.6
    for i, (_key, spec) in enumerate(legend):
        yy = -half_h - 0.55 - i * 0.30
        ax.add_patch(FancyBboxPatch((left, yy - 0.09), 0.30, 0.18,
                                    boxstyle="round,pad=0.01,rounding_size=0.04",
                                    facecolor=spec["fill"], edgecolor="#33333355", zorder=4))
        ax.text(left + 0.42, yy, spec["label"], ha="left", va="center",
                fontsize=7.2, color="#1b1b1b")

    ax.text(width + 0.6, -half_h - 0.55,
            "read left to right: leaves -> laws -> derived claims -> root",
            ha="right", va="center", fontsize=7.6, color="#777777", style="italic")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return save_figure(fig, OUT_DIR / f"claim_{root['short']}.png", dpi=lay["dpi"])


# ---------------------------------------------------------------------------
# Text emitters
# ---------------------------------------------------------------------------
def write_dot(root: dict, nodes: dict, edges: list, style: dict) -> Path:
    members = sub_members(root["id"], edges)
    klass = style["node_class"]
    shape = {"law": "note", "defeater": "octagon", "context": "folder"}

    lines = [f'// {root["meta"].get("title", root["id"])}',
             f'// {root["meta"].get("statement", "")}',
             "digraph claim {", "  rankdir=LR;", '  bgcolor="white";',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", '
             'fontsize=10, margin="0.14,0.08"];',
             '  edge [fontname="Helvetica", fontsize=8];', ""]
    for nid in sorted(members):
        rec = nodes[nid]
        cls = klass[rec["type"]]
        label = (rec.get("display", nid) + _decoration(rec, style)[4]
                 + "\\n" + _wrap(rec.get("text", ""), 40).replace("\n", "\\n"))
        extra = f', shape={shape[rec["type"]]}' if rec["type"] in shape else ""
        lines.append(f'  "{nid}" [label="{label}", fillcolor="{cls["fill"]}", '
                     f'fontcolor="{cls["text"]}"{extra}];')
    lines.append("")
    dot_edge = {"premise": "", "law_out": ' penwidth=1.5',
                "context": ' style=dashed, color="#8a9aa5", constraint=false',
                "attack": ' style=dotted, color="#8c3b4a", arrowhead=tee, constraint=false',
                "evidence": ' style=dashed, color="#8c3b4a", label="grounds", fontcolor="#8c3b4a"'}
    for src, dst, kind in edges:
        if src in members and dst in members:
            lines.append(f'  "{src}" -> "{dst}" [{dot_edge[kind].lstrip(", ")}];')
    lines.append("}")
    path = OUT_DIR / f"claim_{root['short']}.dot"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_mermaid(root: dict, nodes: dict, edges: list, style: dict) -> Path:
    """Mermaid source, deliberately without subgraphs.

    Mermaid cannot place one node in two subgraphs (open upstream since 2021), and a
    shared leaf feeding several results is exactly that operation. Classes carry the
    node vocabulary instead, so the same source stays correct when more roots are added.
    """
    members = sub_members(root["id"], edges)
    klass = style["node_class"]

    lines = ["%% " + root["meta"].get("title", root["id"]), "flowchart LR"]
    for nid in sorted(members):
        rec = nodes[nid]
        label = (rec.get("display", nid) + _decoration(rec, style)[4] + "<br/>"
                 + _wrap(rec.get("text", ""), 38).replace("\n", "<br/>"))
        open_, close = {"law": ("[/", "/]"), "defeater": ("{{", "}}"),
                        "context": ("[(", ")]")}.get(rec["type"], ("[\"", "\"]"))
        body = label if rec["type"] != "law" and rec["type"] not in ("defeater", "context") else f'"{label}"'
        lines.append(f'  {_mid(nid)}{open_}{body}{close}')
    lines.append("")
    for src, dst, kind in edges:
        if src in members and dst in members:
            arrow = {"premise": "-->", "law_out": "==>", "context": "-.->",
                     "attack": "-.->|attacks|", "evidence": "-.->|grounds|"}[kind]
            lines.append(f"  {_mid(src)} {arrow} {_mid(dst)}")
    lines.append("")
    for key, spec in klass.items():
        members_of = [_mid(n) for n in sorted(members) if nodes[n]["type"] == key]
        if members_of:
            lines.append(f'  classDef {key} fill:{spec["fill"]},color:{spec["text"]},stroke:#333;')
            lines.append(f'  class {",".join(members_of)} {key};')
    path = OUT_DIR / f"claim_{root['short']}.mmd"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mid(nid: str) -> str:
    """Mermaid-safe node id."""
    return nid.replace("__", "_").replace("-", "_").replace(":", "_")


# ---------------------------------------------------------------------------
# Indices
# ---------------------------------------------------------------------------
def write_indices(nodes: dict, roots: list, edges: list) -> tuple[Path, Path]:
    """The reverse-dependency table and the flat ladder listing.

    ``impact.csv`` is the one that earns its keep: given a leaf that turns out to be
    wrong, it names every published claim that has to be withdrawn. A per-root diagram
    cannot show this, because it only ever looks in one direction.
    """
    index_dir = OUT_DIR / "_index"
    index_dir.mkdir(parents=True, exist_ok=True)

    reach = {r["id"]: sub_members(r["id"], edges) for r in roots}
    impact = index_dir / "impact.csv"
    with impact.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["leaf", "type", "status", "n_roots", "roots", "text"])
        for nid, rec in sorted(nodes.items()):
            if rec.get("type") not in ("finding", "assumption", "context"):
                continue
            hits = [r["short"] for r in roots if nid in reach[r["id"]]]
            w.writerow([nid, rec["type"], rec.get("status", ""), len(hits),
                        ";".join(hits), rec.get("text", "")])

    ladder = index_dir / "ladder.csv"
    with ladder.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["node", "type", "root", "law", "subtype", "block", "backed",
                    "qualifier", "premises", "text"])
        for r in roots:
            rank = rank_nodes(reach[r["id"]], edges, nodes)
            for nid in sorted(reach[r["id"]], key=lambda n: (rank.get(n, 0), n)):
                rec = nodes[nid]
                law = rec.get("law") or {}
                w.writerow([nid, rec["type"], r["short"], law.get("id", ""),
                            law.get("subtype", ""), law.get("block", ""),
                            "no" if law and not law.get("backing") else ("yes" if law else ""),
                            rec.get("qualifier", ""), " ".join(rec.get("from") or []),
                            rec.get("text", "")])
    return impact, ladder


def descendants(node: str, edges: list) -> set[str]:
    """Everything downstream of *node* along derivation edges.

    The reverse of :func:`ancestors`, and the direction that costs you something:
    ``ancestors`` answers "what does this claim rest on", this answers **"if this is
    wrong, what has to be withdrawn"**. Build systems call it ``rdeps``; no
    downward-facing diagram can show it.
    """
    children: dict[str, list[str]] = {}
    for src, dst, kind in edges:
        if kind in DERIV:
            children.setdefault(src, []).append(dst)
    seen, stack = {node}, [node]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _figure_payload(spec: str, style: dict) -> dict:
    """Inline a node's figure as a data URI, with its intrinsic pixel dimensions.

    Inlined rather than linked because the viewer must stay self-contained -- it is
    published as a single HTML file under a CSP that blocks every external host, so a
    relative ``<img src>`` would render as a broken image with no error anywhere.

    Dimensions come from the PNG's own IHDR chunk rather than from Pillow: the caller
    only needs the aspect ratio to reserve space, and reading eight bytes beats making
    a documentation script depend on an imaging library.
    """
    import base64

    tried = []
    for base in style.get("figure_roots") or []:
        root = Path(base)
        path = (root if root.is_absolute() else PROJECT_ROOT / root) / spec
        tried.append(str(path))
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"figure {path} is not a PNG; only PNG is supported")
        return {
            "uri": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
            "w": int.from_bytes(raw[16:20], "big"),
            "h": int.from_bytes(raw[20:24], "big"),
            "src": spec,
        }
    raise FileNotFoundError(
        f"figure {spec!r} not found. Looked in:\n  " + "\n  ".join(tried)
    )


def export_web(nodes: dict, roots: list, edges: list, style: dict) -> Path | None:
    """Inline the whole graph into the standalone viewer and write it out.

    Layout is computed here rather than in the browser so the static figures and the
    interactive page cannot disagree about the shape of the argument -- one layout
    engine, two renderers.
    """
    import json

    template = CLAIMS_DIR / "_viewer.html"
    if not template.is_file():
        return None

    payload_roots = []
    for root in roots:
        members = sub_members(root["id"], edges)
        sub = [(s, d, k) for s, d, k in edges if s in members and d in members]
        rank = rank_nodes(members, sub, nodes)
        pos = order_ranks(rank, sub)

        # Only rank and order travel to the browser. Those ARE the layout decision --
        # which column a node sits in and in what order within it. Box geometry is a
        # rendering detail and must not: matplotlib sizes boxes in data units against a
        # points-based font, SVG sizes them in user units against a px font, and one
        # shared number cannot satisfy both. Exporting matplotlib's metrics produced a
        # page whose labels were ten times taller than the boxes containing them.
        by_rank: dict[int, list[str]] = {}
        for n, r in rank.items():
            by_rank.setdefault(r, []).append(n)
        placed = {}
        for r, ns in sorted(by_rank.items()):
            ns.sort(key=lambda n: pos[n])
            for i, n in enumerate(ns):
                placed[n] = {"rank": r, "order": i}

        payload_roots.append({
            "id": root["id"], "short": root["short"],
            "title": root["meta"].get("title", root["id"]),
            "statement": root["meta"].get("statement", ""),
            "grid": root["meta"].get("grid", ""),
            "nodes": placed,
            "edges": [{"s": s, "t": d, "k": k} for s, d, k in sub],
        })

    payload_nodes = {}
    for nid, rec in nodes.items():
        law = rec.get("law") or {}
        payload_nodes[nid] = {
            "id": nid, "display": rec.get("display", nid), "type": rec["type"],
            "text": rec.get("text", ""), "status": rec.get("status", ""),
            "kind": rec.get("kind", ""), "grid": rec.get("grid", ""),
            "artifact": rec.get("artifact", ""), "where": rec.get("where", ""),
            "note": rec.get("note", ""), "qualifier": rec.get("qualifier", ""),
            "premises": rec.get("from") or [],
            "figure": _figure_payload(rec["figure"], style) if rec.get("figure") else None,
            "figure_caption": rec.get("figure_caption", ""),
            "law": {k: law.get(k) for k in ("id", "subtype", "block", "text", "backing")} if law else None,
            "upstream": sorted(ancestors(nid, edges) - {nid}),
            "downstream": sorted(descendants(nid, edges) - {nid}),
            "roots": sorted(r["short"] for r in roots if nid in sub_members(r["id"], edges)),
        }

    payload = {"nodes": payload_nodes, "roots": payload_roots,
               "style": {"node_class": style["node_class"],
                         "assumption_status": style["assumption_status"],
                         "defeater_status": style["defeater_status"],
                         "qualifier_order": style["qualifier_order"]}}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "claims.html"
    html = template.read_text(encoding="utf-8").replace(
        "/*__GRAPH_DATA__*/null", json.dumps(payload, ensure_ascii=False))
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    nodes, roots, style = load_graph()
    edges = build_edges(nodes)
    check_grids(nodes, roots, edges)

    for root in roots:
        png = render_root(root, nodes, edges, style)
        dot = write_dot(root, nodes, edges, style)
        mmd = write_mermaid(root, nodes, edges, style)
        print(f"[{root['short']}] {png.name}, {png.with_suffix('.svg').name}, "
              f"{dot.name}, {mmd.name}")

    impact, ladder = write_indices(nodes, roots, edges)
    print(f"[index]  {impact.relative_to(OUT_DIR)}, {ladder.relative_to(OUT_DIR)}")

    web = export_web(nodes, roots, edges, style)
    print(f"[viewer] {web.name}" if web else "[viewer] skipped -- no _viewer.html template")

    violations = check_qualifiers(nodes, style)
    print("\nLadder Invariant -- a node may not out-claim its weakest premise:")
    print("\n".join(violations) if violations else "  no violations")

    reached = set().union(*(sub_members(r["id"], edges) for r in roots))
    orphans = sorted(n for n, r in nodes.items()
                     if n not in reached and r.get("type") in ("finding", "assumption", "context"))
    if orphans:
        print("\nOrphan leaves -- no root depends on them:")
        for nid in orphans:
            print(f"  {nid} -- {nodes[nid].get('text', '')[:72]}")
        print("  (either a claim is under-stated, or the leaf does not belong here)")

    unbacked = [n for n, r in nodes.items() if r.get("type") == "law" and not r.get("backing")]
    if unbacked:
        print("\nLaws with no stated backing (an assumption wearing a rule's clothes):")
        for nid in sorted(unbacked):
            print(f"  {nid} -- licenses {nodes[nid]['licenses']}")

    print(f"\nAll artefacts in: {OUT_DIR}")


if __name__ == "__main__":
    main()

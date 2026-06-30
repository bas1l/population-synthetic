#!/usr/bin/env python3
"""Render the synthetic-population generation workflow / conditional-sampling DAG
for each country (Sweden / Norway / Italy).

For every country this emits three artefacts into ``docs/architecture/diagrams/database/``:

* ``{country}_generation_dag.svg`` -- vectorised figure (scalable)
* ``{country}_generation_dag.png`` -- raster image (300 dpi)
* ``{country}_generation_dag.dot`` -- Graphviz source (the DAG in canonical text form)

The figure has two parts: a top ETL band (clients/APIs -> load_all -> parsers ->
PopulationDistributions -> sampler) and the conditional chained-sampling DAG below
it (the order in which ``sample_one`` draws each attribute and what each draw is
conditioned on). Data is hand-derived from the source modules under
``src/population_synth/population/{sweden,norway,italy}/``.

Run: ``python scripts/dev/draw_generation_dags.py``
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "docs" / "architecture" / "diagrams" / "database"

# ---------------------------------------------------------------------------
# Palette (colour-blind friendly, muted)
# ---------------------------------------------------------------------------
C_HUB = "#1f3a5f"        # root joint draw (age, sex)
C_CHAIN = "#2e6f95"      # multi-level causal chain (education -> employment -> ...)
C_COND = "#3aa6a0"       # one-hop conditional off (age, sex)
C_MARG = "#b8c4cc"       # independent marginal (no parents)
C_DROP = "#d9d2cb"       # dropped / not emitted
C_SRC = "#6c5b7b"        # ETL / data-source nodes
C_DIST = "#c06c3e"       # PopulationDistributions container
TEXT_LIGHT = "#ffffff"
TEXT_DARK = "#1b1b1b"

NODE_W = 1.9
NODE_H = 0.78

# ---------------------------------------------------------------------------
# Per-country specification
# ---------------------------------------------------------------------------
# DAG node: name -> dict(x, y, label, detail, kind)
#   kind in {hub, chain, cond, marg, marg_parent, dropped}
# DAG edge: (src, dst, kind) ; kind in {solid, cond, broadcast, employed, age}

COMMON_MARGINALS_Y = 0.7


def _base_dag():
    """Nodes / edges shared by all three countries (Sweden is the superset)."""
    nodes = {
        "agesex": dict(x=5.0, y=9.3, kind="hub",
                       label="(age, sex)", detail="joint draw - age_sex"),
        "education": dict(x=2.1, y=7.3, kind="chain",
                          label="education_level", detail="| age_group, sex"),
        "employment": dict(x=2.1, y=5.3, kind="chain",
                           label="employment_status", detail="| sex, education"),
        "industry": dict(x=0.55, y=3.0, kind="chain",
                         label="industry_sector", detail="if employed"),
        "emptype": dict(x=2.45, y=3.0, kind="chain",
                        label="employment_type", detail="if employed | age,sex"),
        "income_source": dict(x=4.35, y=3.0, kind="chain",
                              label="income_source", detail="| employment, age"),
        "socio": dict(x=5.4, y=7.3, kind="cond",
                      label="socioeconomic_class", detail="| age_group, sex"),
        "civil": dict(x=7.5, y=7.3, kind="cond",
                      label="civil_status", detail="| age_group, sex"),
        "birthloc": dict(x=8.9, y=9.3, kind="marg_parent",
                         label="birth_location", detail="marginal"),
        "birthdetail": dict(x=8.4, y=5.3, kind="cond",
                            label="birth_country_detail", detail="| birth_loc, age, sex"),
    }
    edges = [
        ("agesex", "education", "solid"),
        ("education", "employment", "solid"),
        ("employment", "industry", "employed"),
        ("employment", "emptype", "employed"),
        ("employment", "income_source", "solid"),
        ("agesex", "emptype", "age"),
        ("agesex", "income_source", "age"),
        ("agesex", "socio", "solid"),
        ("agesex", "civil", "solid"),
        ("agesex", "birthdetail", "age"),
        ("birthloc", "birthdetail", "solid"),
    ]
    # pure marginals (no parents) laid across the bottom
    marginals = ["region", "parental_structure", "housing_tenure", "household_size"]
    return nodes, edges, marginals


def sweden_spec():
    nodes, edges, marginals = _base_dag()
    return dict(
        key="sweden",
        title="Sweden  -  SCB synthetic population generation",
        subtitle="src/population_synth/population/sweden/  |  SampleService.sample_one  "
                 "(conditional chained sampling, ~14 draws)",
        etl=[
            ("SCBPxWebClient", "PxWeb\njson-stat2 (POST)", C_SRC),
            ("12 SCB tables", "BE / UF / AM\nHE / LE / BO", C_SRC),
            ("load_all", "single client\n14x fetch_*", C_SRC),
            ("parsers", "json-stat2\n-> prob dicts", C_SRC),
            ("PopulationDistributions", "all 16 fields\n(income_source real)", C_DIST),
            ("SampleService", "sample_population", C_HUB),
        ],
        nodes=nodes, edges=edges, marginals=marginals,
        notes="Most data-rich: only country with a real income_source conditional table "
              "and employment_type built from two tables (attachment x hours) at true (age,sex) cells.",
    )


def norway_spec():
    nodes, edges, marginals = _base_dag()
    # income_source is dropped (no SSB table) -> show as dropped, remove its edges
    nodes["income_source"] = dict(x=4.35, y=3.0, kind="dropped",
                                  label="income_source", detail="DROPPED (no API)")
    edges = [e for e in edges if e[1] != "income_source"]
    # employment_type & birth_country_detail are broadcast marginals (nominal conditioning)
    nodes["emptype"]["detail"] = "if employed (broadcast)"
    nodes["birthdetail"]["detail"] = "| birth_loc (broadcast)"
    edges = [(s, d, "broadcast" if d in ("emptype", "birthdetail") and k == "age" else k)
             for (s, d, k) in edges]
    return dict(
        key="norway",
        title="Norway  -  SSB synthetic population generation",
        subtitle="src/population_synth/population/norway/  |  SSBSampleService.sample_one  "
                 "(11-step chain, income_source omitted)",
        etl=[
            ("SSBPxWebClient", "PxWebApi v2\nGET (>=2.1s limit)", C_SRC),
            ("11 SSB tables", "07459, 08921\n13785, ...", C_SRC),
            ("load_all", "single client\n2-call birth_loc", C_SRC),
            ("parsers", "code -> label\nnormalise", C_SRC),
            ("PopulationDistributions", "income_source = {}\nemp_type broadcast", C_DIST),
            ("SSBSampleService", "sample_population", C_HUB),
        ],
        nodes=nodes, edges=edges, marginals=marginals,
        notes="income_source dropped (no SSB v2 table); employment_type & birth_country_detail are "
              "sex/age-agnostic marginals broadcast to every (age,sex) cell. birth_location derived as "
              "population minus immigrants (2 API calls).",
    )


def italy_spec():
    nodes, edges, marginals = _base_dag()
    # Italy has NO income_source node at all -> remove it entirely
    del nodes["income_source"]
    edges = [e for e in edges if e[1] != "income_source"]
    nodes["employment"]["detail"] = "| sex, education (binary)"
    nodes["emptype"]["detail"] = "if employed (broadcast)"
    nodes["birthdetail"]["detail"] = "| birth_loc (broadcast)"
    edges = [(s, d, "broadcast" if d in ("emptype", "birthdetail") and k == "age" else k)
             for (s, d, k) in edges]
    # re-centre the employment children now that income_source is gone
    nodes["industry"]["x"] = 0.9
    nodes["emptype"]["x"] = 3.1
    return dict(
        key="italy",
        title="Italy  -  ISTAT + Eurostat synthetic population generation",
        subtitle="src/population_synth/population/italy/  |  ISTATSampleService.sample_one  "
                 "(10-step chain, no income_source)",
        etl=[
            ("EurostatClient", "JSON-stat 2.0", C_SRC),
            ("ISTATSDMXClient", "SDMX CSV\n(12s limit)", C_SRC),
            ("load_all", "DUAL client\n6 EU + 6 ISTAT", C_DIST),
            ("parsers", "JSON-stat +\nSDMX CSV", C_SRC),
            ("PopulationDistributions", "binary employment\nNUTS2 regions", C_DIST),
            ("ISTATSampleService", "sample_population", C_HUB),
        ],
        nodes=nodes, edges=edges, marginals=marginals,
        notes="Dual-client: Eurostat (demographics) + ISTAT SDMX (labour/education/income). employment_status "
              "is binary (Employed / Not Employed, rate-derived); 20 NUTS2 regions with demo_r_d2jan fallback; "
              "civil-status fetch retries 3x. No income_source step at all.",
    )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
KIND_FACE = {
    "hub": C_HUB, "chain": C_CHAIN, "cond": C_COND,
    "marg": C_MARG, "marg_parent": C_MARG, "dropped": C_DROP,
}
KIND_TEXT = {
    "hub": TEXT_LIGHT, "chain": TEXT_LIGHT, "cond": TEXT_LIGHT,
    "marg": TEXT_DARK, "marg_parent": TEXT_DARK, "dropped": "#8a817c",
}

EDGE_STYLE = {
    "solid": dict(color="#2b2b2b", lw=1.7, ls="-", alpha=0.9),
    "cond": dict(color="#2b2b2b", lw=1.7, ls="-", alpha=0.9),
    "employed": dict(color="#5a8f3c", lw=1.5, ls="-", alpha=0.9),
    "age": dict(color="#888888", lw=1.2, ls=(0, (4, 3)), alpha=0.8),
    "broadcast": dict(color="#b06a3a", lw=1.2, ls=(0, (1, 2)), alpha=0.85),
}


def _draw_box(ax, x, y, w, h, label, detail, face, txt, fontsize=9.5, struck=False):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.10",
        linewidth=1.1, edgecolor="#33333355", facecolor=face, zorder=3,
    )
    ax.add_patch(box)
    lbl = label
    ax.text(x, y + 0.12, lbl, ha="center", va="center", color=txt,
            fontsize=fontsize, fontweight="bold", zorder=4)
    if detail:
        ax.text(x, y - 0.19, detail, ha="center", va="center", color=txt,
                fontsize=7.3, style="italic", alpha=0.92, zorder=4)
    if struck:
        ax.plot([x - w / 2 + 0.1, x + w / 2 - 0.1], [y, y],
                color="#8a817c", lw=1.4, zorder=5)


def _edge(ax, p0, p1, style):
    arr = FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=13,
        shrinkA=2, shrinkB=2, connectionstyle="arc3,rad=0.04",
        zorder=2, **EDGE_STYLE[style],
    )
    ax.add_patch(arr)


def _anchor(node, other):
    """Return the point on node's box border facing `other` (simple: edge midpoints)."""
    x, y = node["x"], node["y"]
    ox, oy = other["x"], other["y"]
    dx, dy = ox - x, oy - y
    if abs(dy) >= abs(dx):
        return (x, y - NODE_H / 2) if dy < 0 else (x, y + NODE_H / 2)
    return (x - NODE_W / 2, y) if dx < 0 else (x + NODE_W / 2, y)


def render(spec):
    fig, ax = plt.subplots(figsize=(15.5, 11.5))
    ax.set_xlim(-0.6, 10.6)
    ax.set_ylim(-0.4, 13.6)
    ax.axis("off")

    # ---- title ----
    ax.text(5.0, 13.25, spec["title"], ha="center", va="center",
            fontsize=17, fontweight="bold", color=TEXT_DARK)
    ax.text(5.0, 12.78, spec["subtitle"], ha="center", va="center",
            fontsize=9.5, color="#555555")

    # ---- ETL band ----
    band_y = 11.7
    n = len(spec["etl"])
    xs = [0.9 + i * (8.7 / (n - 1)) for i in range(n)]
    centers = []
    for (lbl, sub, face), x in zip(spec["etl"], xs):
        txt = TEXT_LIGHT if face in (C_SRC, C_HUB, C_DIST) else TEXT_DARK
        _draw_box(ax, x, band_y, 1.62, 0.92, lbl, sub, face, txt, fontsize=8.6)
        centers.append((x, band_y))
    for (x0, y0), (x1, y1) in zip(centers[:-1], centers[1:]):
        _edge(ax, (x0 + 0.81, y0), (x1 - 0.81, y1), "solid")
    ax.text(0.0, 12.32, "ETL  (fetch -> parse -> distributions)", ha="left",
            va="center", fontsize=9, fontweight="bold", color="#6c5b7b")

    # divider
    ax.plot([-0.4, 10.4], [10.85, 10.85], color="#cccccc", lw=1.0, ls="-")
    ax.text(0.0, 10.45, "Conditional chained sampling DAG  (per individual, sample_one)",
            ha="left", va="center", fontsize=9, fontweight="bold", color="#1f3a5f")

    nodes = spec["nodes"]

    # ---- pure marginals strip (bottom) ----
    margs = spec["marginals"]
    mxs = [1.3 + i * (7.6 / (len(margs) - 1)) for i in range(len(margs))]
    for name, mx in zip(margs, mxs):
        nd = dict(x=mx, y=COMMON_MARGINALS_Y, kind="marg", label=name, detail="marginal")
        nodes[name] = nd
    ax.text(0.0, 1.55, "Independent marginals (no conditioning)", ha="left",
            va="center", fontsize=8.2, color="#7a7a7a", style="italic")
    # faint enclosure for the marginals row
    ax.add_patch(FancyBboxPatch((0.15, 0.18), 10.1, 1.05,
                                boxstyle="round,pad=0.02,rounding_size=0.08",
                                linewidth=1.0, edgecolor="#cccccc",
                                facecolor="#f4f1ee", zorder=1))

    # ---- edges ----
    for src, dst, kind in spec["edges"]:
        _edge(ax, _anchor(nodes[src], nodes[dst]), _anchor(nodes[dst], nodes[src]), kind)

    # ---- nodes ----
    for name, nd in nodes.items():
        face = KIND_FACE[nd["kind"]]
        txt = KIND_TEXT[nd["kind"]]
        _draw_box(ax, nd["x"], nd["y"], NODE_W, NODE_H, nd["label"], nd["detail"],
                  face, txt, struck=(nd["kind"] == "dropped"))

    # ---- legend ----
    legend = [
        (C_HUB, "root joint draw (age, sex)"),
        (C_CHAIN, "causal chain (edu -> employment -> ...)"),
        (C_COND, "one-hop conditional on (age, sex)"),
        (C_MARG, "independent marginal"),
        (C_DROP, "dropped / not emitted"),
    ]
    lx, ly = 0.2, 9.8
    for i, (col, txt) in enumerate(legend):
        yy = ly - i * 0.42
        ax.add_patch(FancyBboxPatch((lx, yy - 0.13), 0.34, 0.26,
                                    boxstyle="round,pad=0.01,rounding_size=0.05",
                                    facecolor=col, edgecolor="#33333355", zorder=4))
        ax.text(lx + 0.46, yy, txt, ha="left", va="center", fontsize=7.8, color=TEXT_DARK)
    # edge legend -- only the edge kinds actually present in this DAG
    used_kinds = {k for _, _, k in spec["edges"]}
    el = [("solid", "conditioning edge"), ("employed", "only if employed"),
          ("age", "age/sex conditioning"), ("broadcast", "broadcast marginal")]
    el = [(k, t) for k, t in el if k in used_kinds]
    for i, (k, txt) in enumerate(el):
        yy = ly - (len(legend) + i) * 0.42 - 0.1
        ax.plot([lx, lx + 0.34], [yy, yy], **{kk: vv for kk, vv in EDGE_STYLE[k].items()})
        ax.text(lx + 0.46, yy, txt, ha="left", va="center", fontsize=7.8, color=TEXT_DARK)

    # ---- notes footer ----
    ax.text(5.0, -0.28, spec["notes"], ha="center", va="center", fontsize=8.0,
            color="#555555", wrap=True)

    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    svg = OUT_DIR / f"{spec['key']}_generation_dag.svg"
    png = OUT_DIR / f"{spec['key']}_generation_dag.png"
    fig.savefig(svg, format="svg")
    fig.savefig(png, format="png", dpi=300)
    plt.close(fig)
    return svg, png


# ---------------------------------------------------------------------------
# Graphviz .dot emitter (canonical DAG source)
# ---------------------------------------------------------------------------
DOT_COLOR = {
    "hub": C_HUB, "chain": C_CHAIN, "cond": C_COND,
    "marg": C_MARG, "marg_parent": C_MARG, "dropped": C_DROP,
}
DOT_FONT = {
    "hub": "white", "chain": "white", "cond": "white",
    "marg": "black", "marg_parent": "black", "dropped": "gray40",
}
DOT_EDGE = {
    "solid": 'color="#2b2b2b"',
    "cond": 'color="#2b2b2b"',
    "employed": 'color="#5a8f3c", label="if employed", fontsize=9, fontcolor="#5a8f3c"',
    "age": 'color="#888888", style=dashed, label="age,sex", fontsize=9, fontcolor="#888888"',
    "broadcast": 'color="#b06a3a", style=dotted, label="broadcast", fontsize=9, fontcolor="#b06a3a"',
}


def write_dot(spec):
    nodes = dict(spec["nodes"])
    for name in spec["marginals"]:
        nodes.setdefault(name, dict(kind="marg", label=name, detail="marginal"))
    lines = [
        f'// {spec["title"]}',
        f'// {spec["subtitle"]}',
        "digraph generation {",
        '  rankdir=TB;',
        '  bgcolor="white";',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", '
        'fontsize=11, margin="0.12,0.07"];',
        '  edge [fontname="Helvetica"];',
        "",
    ]
    for name, nd in nodes.items():
        detail = nd.get("detail", "")
        label = nd["label"] + (f"\\n({detail})" if detail else "")
        struck = ' style="rounded,filled,dashed"' if nd["kind"] == "dropped" else ""
        lines.append(
            f'  {name} [label="{label}", fillcolor="{DOT_COLOR[nd["kind"]]}", '
            f'fontcolor="{DOT_FONT[nd["kind"]]}"{struck}];'
        )
    lines.append("")
    for src, dst, kind in spec["edges"]:
        lines.append(f'  {src} -> {dst} [{DOT_EDGE[kind]}];')
    lines.append("")
    lines.append('  // independent marginals (no parents)')
    lines.append('  { rank=sink; ' + " ".join(spec["marginals"]) + " }")
    lines.append("}")
    dot = OUT_DIR / f"{spec['key']}_generation_dag.dot"
    dot.write_text("\n".join(lines), encoding="utf-8")
    return dot


def main():
    specs = [sweden_spec(), norway_spec(), italy_spec()]
    for spec in specs:
        svg, png = render(spec)
        dot = write_dot(spec)
        print(f"[{spec['key']:7s}] wrote {svg.name}, {png.name}, {dot.name}")
    print(f"\nAll artefacts in: {OUT_DIR}")


if __name__ == "__main__":
    main()

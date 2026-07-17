#!/usr/bin/env python3
"""Render one standalone SVG per generated persona: the Sweden conditional-sampling
DAG with that individual's sampled values overlaid.

This is the static, self-contained export of the **Individual mode** of the
``docs/architecture/sweden-generation-explorer`` page. The interactive page overlays
one loaded individual onto its conditional-chained-sampling DAG (a value chip under
each attribute node, gated nodes dimmed to "not applicable"); this tool bakes that
exact overlay into one ``.svg`` file per person so it can be viewed, embedded in a
paper, or diffed without a browser.

The geometry (node coords, box size, anchor logic), the node-kind colour vocabulary,
the edge kinds, and the value-chip idiom are ported VERBATIM from
``sweden-generation-explorer/js/dag-view.js`` + ``data.js`` + ``styles.css`` so the
output matches the page pixel-for-pixel. Colours are resolved to concrete values for
the chosen ``--theme`` and baked onto elements as presentation attributes (no CSS
custom properties / media queries), so the files render identically in browsers,
Inkscape, librsvg and Illustrator.

Input is a generated SCB population JSON (``{"metadata":..., "individuals":[...]}``),
the same file the page's "Load population..." picker consumes and the same one
``embed_population_in_explorer.py`` embeds. The default source is the Swedish dataset
path from the country axis YAML (config, not hardcoded).

Each persona is written as BOTH a ``.svg`` and a rasterized ``.png`` (same basename).
PNG rasterization uses ``resvg-py`` (a pure-wheel Rust SVG renderer, no native deps)::

    pip install resvg-py

Pass ``--no-png`` to emit SVG only; ``--png-scale`` controls the raster resolution
(default 2.0 -> a 2360x1716 PNG for the 1180x858 canvas).

Usage::

    python scripts/dev/render_persona_dags.py                       # all personas, svg + png, light theme
    python scripts/dev/render_persona_dags.py --theme dark
    python scripts/dev/render_persona_dags.py --ids 0,5,10-19       # a subset
    python scripts/dev/render_persona_dags.py --limit 50            # first 50
    python scripts/dev/render_persona_dags.py --no-png              # svg only
    python scripts/dev/render_persona_dags.py --png-scale 3         # higher-res png
    python scripts/dev/render_persona_dags.py --source data/scb_api/other.json --output-dir out/dags
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from population_synthetic.analysis.utils.country_config import real_for_country

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = real_for_country("swedish")
# When --output-dir is omitted, SVGs land in a "persona_dags" subfolder next to the
# source population (resolved in main once the source is known). This is a generated,
# potentially huge artifact folder, so the script drops a `.gitignore` (`*`) into it to
# keep it out of version control regardless of where it lives.
DEFAULT_OUTPUT_SUBDIR = "persona_dags"

# ---------------------------------------------------------------------------
#  Geometry — ported verbatim from dag-view.js
# ---------------------------------------------------------------------------
SVG_W, SVG_H = 1180, 858
NW, NH = 178, 62  # node box width / height


def VX(x: float) -> float:  # noqa: N802 — mirror the JS name
    return 100 + (x - 0.55) * 116


def VY(y: float) -> float:  # noqa: N802 — mirror the JS name
    return 74 + (9.3 - y) * 80


# ---------------------------------------------------------------------------
#  SPEC (nodes + edges) — the render-relevant fields, ported from data.js.
#  Only id/kind/x/y/step/label/caption matter for the diagram; the table/query/
#  category metadata lives in the page's side panel, not the SVG.
# ---------------------------------------------------------------------------
NODES = [
    {"id": "agesex", "kind": "hub", "x": 5.0, "y": 9.3, "step": "1",
     "label": "(age, sex)", "caption": "joint draw — root"},
    {"id": "education", "kind": "chain", "x": 2.1, "y": 7.3, "step": "2",
     "label": "education_level", "caption": "| age_group, sex"},
    {"id": "employment", "kind": "chain", "x": 2.1, "y": 5.3, "step": "3",
     "label": "employment_status", "caption": "| age_group, education, sex"},
    {"id": "industry", "kind": "chain", "x": 0.55, "y": 3.0, "step": "6",
     "label": "industry_sector", "caption": "if employed | age, sex"},
    {"id": "emptype", "kind": "chain", "x": 2.45, "y": 3.0, "step": "7",
     "label": "employment_type", "caption": "if employed | age, sex"},
    {"id": "income_source", "kind": "chain", "x": 4.35, "y": 3.0, "step": "9",
     "label": "income_source", "caption": "| employment, age"},
    {"id": "socio", "kind": "cond", "x": 5.4, "y": 7.3, "step": "4d",
     "label": "socioeconomic_class", "caption": "| age_group, sex"},
    {"id": "civil", "kind": "cond", "x": 7.5, "y": 7.3, "step": "5",
     "label": "civil_status", "caption": "| age_group, sex"},
    {"id": "birthloc", "kind": "cond", "x": 8.9, "y": 9.3, "step": "4a",
     "label": "birth_location", "caption": "| age_group, sex"},
    {"id": "birthdetail", "kind": "cond", "x": 8.4, "y": 5.3, "step": "11",
     "label": "birth_country_detail", "caption": "| birth_location, age, sex"},
    {"id": "region", "kind": "marginal", "x": 1.3, "y": 0.7, "step": "4b",
     "label": "region", "caption": "marginal"},
    {"id": "parental", "kind": "marginal", "x": 5.1, "y": 0.7, "step": "4c",
     "label": "parental_structure", "caption": "marginal"},
    {"id": "housing", "kind": "cond", "x": 6.4, "y": 3.0, "step": "8",
     "label": "housing_tenure", "caption": "| age_group, sex"},
    {"id": "household", "kind": "marginal", "x": 8.9, "y": 0.7, "step": "8",
     "label": "household_size", "caption": "marginal"},
]

EDGES = [
    ("agesex", "education", "solid"),
    ("agesex", "employment", "solid"),
    ("education", "employment", "solid"),
    ("employment", "industry", "employed"),
    ("agesex", "industry", "age"),
    ("employment", "emptype", "employed"),
    ("employment", "income_source", "solid"),
    ("agesex", "emptype", "age"),
    ("agesex", "income_source", "age"),
    ("agesex", "socio", "solid"),
    ("agesex", "civil", "solid"),
    ("agesex", "birthloc", "solid"),
    ("agesex", "housing", "solid"),
    ("agesex", "birthdetail", "age"),
    ("birthloc", "birthdetail", "solid"),
]

# industry_sector / employment_type are drawn only for the employed; a null value on
# these two means "not applicable" (dimmed node + muted chip + dimmed "if employed" edge).
GATED = {"industry", "emptype"}

# ---------------------------------------------------------------------------
#  Fonts (from styles.css)
# ---------------------------------------------------------------------------
FONT_BODY = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
FONT_MONO = "ui-monospace, 'Cascadia Code', 'SF Mono', 'Consolas', monospace"

# ---------------------------------------------------------------------------
#  Theme palettes — resolved from styles.css :root (light) and the dark override.
#  k-* node colours and e-employed are NOT overridden in dark mode (per styles.css),
#  so they carry through unchanged.
# ---------------------------------------------------------------------------
THEMES = {
    "light": {
        "surface": "#ffffff", "surface_2": "#eef2f0", "muted": "#5a6a66",
        "line_strong": "#c2cec9", "accent": "#1f6f78", "edge": "#3a4a46",
        "enclosure": "#e7ece9",
        "k_hub": "#1f3a5f", "k_chain": "#2e6f95", "k_cond": "#3aa6a0", "k_marg": "#b8c4cc",
        "e_employed": "#5a8f3c", "e_age": "#8a938f",
    },
    "dark": {
        "surface": "#151e1c", "surface_2": "#1b2523", "muted": "#97a7a2",
        "line_strong": "#33423e", "accent": "#4fb6c0", "edge": "#9fb0ab",
        "enclosure": "#172320",
        "k_hub": "#1f3a5f", "k_chain": "#2e6f95", "k_cond": "#3aa6a0", "k_marg": "#b8c4cc",
        "e_employed": "#5a8f3c", "e_age": "#7f8d88",
    },
}

# node-kind -> (body fill, label fill, caption fill, step fill)
NODE_INK = {
    "hub":      ("k_hub",   "#ffffff", "rgba(255,255,255,.85)", "rgba(255,255,255,.7)"),
    "chain":    ("k_chain", "#ffffff", "rgba(255,255,255,.85)", "rgba(255,255,255,.7)"),
    "cond":     ("k_cond",  "#ffffff", "rgba(255,255,255,.85)", "rgba(255,255,255,.7)"),
    "marginal": ("k_marg",  "#1a2a2e", "#40525a",               "#5a6a70"),
}

EDGE_STYLE = {  # kind -> (colour-key, stroke-width, dasharray-or-None)
    "solid":    ("edge",       2.1, None),
    "employed": ("e_employed", 2.0, None),
    "age":      ("e_age",      1.8, "6 5"),
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(fg: str, bg: str, ratio: float) -> str:
    """color-mix(in srgb, fg ratio, bg) — the value-chip fill in styles.css."""
    fr, fgn, fb = _hex_to_rgb(fg)
    br, bg_, bb = _hex_to_rgb(bg)
    r = round(fr * ratio + br * (1 - ratio))
    g = round(fgn * ratio + bg_ * (1 - ratio))
    b = round(fb * ratio + bb * (1 - ratio))
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
#  Value extraction — mirrors VALUE_EXTRACT in dag-view.js
# ---------------------------------------------------------------------------
def _label(ind: dict, field: str) -> str | None:
    """Return ``ind[field]['label']`` or None when the field is null (fail loud on a
    present-but-labelless node, matching embed_population_in_explorer.py)."""
    node = ind.get(field)
    if node is None:
        return None
    label = node.get("label")
    if label is None:
        raise ValueError(f"individual field {field!r} present but has no label: {node!r}")
    return label


def persona_value(node_id: str, ind: dict) -> str | None:
    """This individual's display value for a SPEC node (None -> "—" or "not applicable")."""
    if node_id == "agesex":
        sex = _label(ind, "biological_sex")
        return f"{ind['age']} · {sex if sex is not None else '?'}"
    if node_id == "emptype":
        et = ind.get("employment_type")
        if et is None:
            return None
        return f"{_label(et, 'attachment')} · {_label(et, 'hours')}"
    field = {
        "education": "education_level",
        "employment": "employment_status",
        "industry": "industry_sector",
        "income_source": "income_source",
        "socio": "socioeconomic_class",
        "civil": "civil_status",
        "birthloc": "birth_location",
        "birthdetail": "birth_country_detail",
        "region": "region",
        "parental": "parental_structure",
        "housing": "housing_tenure",
        "household": "household_size",
    }[node_id]
    return _label(ind, field)


# ---------------------------------------------------------------------------
#  SVG helpers
# ---------------------------------------------------------------------------
def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _anchor(a: dict, b: dict) -> tuple[float, float]:
    """Edge attach point on box ``a`` facing box ``b`` (ported from dag-view.js)."""
    dx, dy = b["cx"] - a["cx"], b["cy"] - a["cy"]
    if abs(dy) >= abs(dx):
        return a["cx"], (a["cy"] + NH / 2 if dy > 0 else a["cy"] - NH / 2)
    return (a["cx"] + NW / 2 if dx > 0 else a["cx"] - NW / 2), a["cy"]


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def render_svg(ind: dict, theme: str) -> str:
    T = THEMES[theme]
    chip_fill = _mix(T["accent"], T["surface"], 0.14)

    # resolve node geometry once
    by_id = {}
    for n in NODES:
        n = dict(n, cx=VX(n["x"]), cy=VY(n["y"]))
        by_id[n["id"]] = n

    # per-individual value + N/A state per node
    value = {nid: persona_value(nid, ind) for nid in by_id}
    is_na = {nid: (value[nid] is None and nid in GATED) for nid in by_id}

    out: list[str] = []
    ind_id = ind.get("id", "?")
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}" '
        f'font-family="{FONT_BODY}" role="img" '
        f'aria-label="Conditional chained sampling DAG for individual {_esc(ind_id)}, '
        f'with sampled values overlaid.">'
    )
    out.append(f'<title>Swedish individual #{_esc(ind_id)} — conditional sampling DAG</title>')

    # arrowhead markers (one per edge kind, concrete fill)
    out.append("<defs>")
    for mk_id, col in (("mk-solid", T["edge"]), ("mk-employed", T["e_employed"]), ("mk-age", T["e_age"])):
        out.append(
            f'<marker id="{mk_id}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
        )
    out.append("</defs>")

    # background
    out.append(f'<rect x="0" y="0" width="{SVG_W}" height="{SVG_H}" fill="{T["surface"]}"/>')

    # section label + individual id badge (top-right)
    out.append(
        f'<text x="18" y="28" fill="{T["muted"]}" font-family="{FONT_MONO}" '
        f'font-size="15" font-weight="600">sample_one — per individual, ~14 conditional draws</text>'
    )
    out.append(
        f'<text x="{SVG_W - 18}" y="28" text-anchor="end" fill="{T["muted"]}" '
        f'font-family="{FONT_MONO}" font-size="15" font-weight="700">#{_esc(ind_id)}</text>'
    )

    # marginal enclosure
    enc_y = VY(0.7) - 46
    out.append(
        f'<rect x="14" y="{_fmt(enc_y)}" width="1152" height="118" rx="12" '
        f'fill="{T["enclosure"]}" stroke="{T["line_strong"]}" stroke-width="1"/>'
    )
    out.append(
        f'<text x="22" y="{_fmt(enc_y - 8)}" fill="{T["muted"]}" font-size="12.5" '
        f'font-style="italic">Independent marginals — no conditioning</text>'
    )

    # edges (below nodes)
    for s, d, kind in EDGES:
        a, b = by_id[s], by_id[d]
        x0, y0 = _anchor(a, b)
        x1, y1 = _anchor(b, a)
        col_key, sw, dash = EDGE_STYLE[kind]
        mk = {"employed": "mk-employed", "age": "mk-age"}.get(kind, "mk-solid")
        na_dim = kind == "employed" and d in GATED and is_na[d]
        attrs = (
            f'x1="{_fmt(x0)}" y1="{_fmt(y0)}" x2="{_fmt(x1)}" y2="{_fmt(y1)}" '
            f'stroke="{T[col_key]}" stroke-width="{sw}" fill="none" '
            f'marker-end="url(#{mk})"'
        )
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if na_dim:
            attrs += ' opacity="0.12"'
        out.append(f"<line {attrs}/>")

    # nodes (above edges)
    for n in NODES:
        node = by_id[n["id"]]
        cx, cy = node["cx"], node["cy"]
        body_key, lab_fill, cap_fill, step_fill = NODE_INK[n["kind"]]
        g_open = '<g opacity="0.26">' if is_na[n["id"]] else "<g>"
        out.append(g_open)
        out.append(
            f'<rect x="{_fmt(cx - NW / 2)}" y="{_fmt(cy - NH / 2)}" width="{NW}" height="{NH}" '
            f'rx="12" fill="{T[body_key]}" stroke="rgba(0,0,0,.28)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{_fmt(cx - NW / 2 + 9)}" y="{_fmt(cy - NH / 2 + 17)}" '
            f'font-family="{FONT_MONO}" font-size="11" font-weight="700" '
            f'fill="{step_fill}">{_esc(n["step"])}</text>'
        )
        out.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(cy - 2)}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="{lab_fill}">{_esc(n["label"])}</text>'
        )
        out.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(cy + 17)}" text-anchor="middle" '
            f'font-size="12" font-style="italic" fill="{cap_fill}">{_esc(n["caption"])}</text>'
        )
        out.append("</g>")

    # value chips (below each node box) — always shown (Individual mode)
    for n in NODES:
        node = by_id[n["id"]]
        cx, cy = node["cx"], node["cy"]
        na = is_na[n["id"]]
        text = "not applicable" if na else (value[n["id"]] if value[n["id"]] is not None else "—")
        cw = max(48, 22 + len(text) * 7)
        gy = cy + NH / 2 + 8
        rect_fill = T["surface_2"] if na else chip_fill
        rect_stroke = T["line_strong"] if na else T["accent"]
        dash = ' stroke-dasharray="2.5 3"' if na else ""
        txt_fill = T["muted"] if na else T["accent"]
        txt_style = ' font-style="italic" font-weight="400"' if na else ' font-weight="700"'
        out.append(
            f'<rect x="{_fmt(cx - cw / 2)}" y="{_fmt(gy)}" width="{cw}" height="20" rx="10" '
            f'fill="{rect_fill}" stroke="{rect_stroke}" stroke-width="1.2"{dash}/>'
        )
        out.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(gy + 14)}" text-anchor="middle" '
            f'font-family="{FONT_MONO}" font-size="12"{txt_style} '
            f'fill="{txt_fill}">{_esc(text)}</text>'
        )

    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------
def _load_png_renderer():
    """Import the resvg rasterizer, failing loudly with an install hint if absent."""
    try:
        import resvg_py
    except ImportError as exc:  # fail-fast: PNG was explicitly requested
        raise SystemExit(
            "PNG output requires the 'resvg-py' package (pure-wheel SVG rasterizer).\n"
            "  pip install resvg-py\n"
            "Or pass --no-png to emit SVG only."
        ) from exc
    return resvg_py


def parse_ids(spec: str, n: int) -> list[int]:
    """Parse "0,5,10-19" into a sorted, de-duplicated, in-range id list."""
    ids: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            for i in range(int(lo), int(hi) + 1):
                ids.add(i)
        else:
            ids.add(int(part))
    out = sorted(i for i in ids if 0 <= i < n)
    if not out:
        raise ValueError(f"--ids {spec!r} selected no individuals in range 0..{n - 1}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="generated SCB population JSON (default: swedish dataset from config)")
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="directory for the per-persona SVGs "
                         "(default: a 'persona_dags' subfolder next to --source)")
    ap.add_argument("--theme", choices=("light", "dark"), default="light",
                    help="colour theme (default: light)")
    ap.add_argument("--ids", type=str, default=None,
                    help='subset of ids, e.g. "0,5,10-19" (default: all individuals)')
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of individuals rendered (applied after --ids)")
    ap.add_argument("--no-png", dest="png", action="store_false",
                    help="emit SVG only (default: also rasterize a PNG per persona)")
    ap.add_argument("--png-scale", type=float, default=2.0,
                    help="PNG raster scale relative to the 1180x858 canvas (default: 2.0)")
    args = ap.parse_args()

    data = json.loads(args.source.read_text(encoding="utf-8"))
    individuals = data.get("individuals")
    if not isinstance(individuals, list) or not individuals:
        raise ValueError(f"{args.source} has no non-empty 'individuals' array")
    n = len(individuals)

    selected = parse_ids(args.ids, n) if args.ids else list(range(n))
    if args.limit is not None:
        selected = selected[: args.limit]

    resvg = _load_png_renderer() if args.png else None

    output_dir = args.output_dir or (args.source.resolve().parent / DEFAULT_OUTPUT_SUBDIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Keep this generated artifact folder out of git no matter where it points.
    (output_dir / ".gitignore").write_text("# generated by render_persona_dags.py\n*\n", encoding="utf-8")
    width = max(1, len(str(n - 1)))

    for i in selected:
        ind = individuals[i]
        # rows are id-indexed; keep the filename tied to the individual's own id
        ind_id = ind.get("id", i)
        svg = render_svg(ind, args.theme)
        stem = output_dir / f"persona_{ind_id:0{width}d}"
        stem.with_suffix(".svg").write_text(svg, encoding="utf-8")
        if resvg is not None:
            png = resvg.svg_to_bytes(svg_string=svg, zoom=args.png_scale)
            stem.with_suffix(".png").write_bytes(png)

    kinds = "SVG + PNG" if args.png else "SVG"
    print(f"Rendered {len(selected):,} persona(s) as {kinds} [{args.theme}] from {args.source.name} "
          f"({n:,} individuals total)")
    print(f"  -> {output_dir}")


if __name__ == "__main__":
    main()

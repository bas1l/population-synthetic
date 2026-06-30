"""Render workflow/DAG diagrams for each configurable generation strategy.

For every strategy yaml under
``config/synthetic/axes/strategies/`` this script emits a
two-panel figure as both SVG (vector) and PNG (raster):

* Left panel  -- the category dependency DAG. Nodes are placed at the
  canonical coordinates stored in the matching ``*.layout.json`` file;
  edges are the ``depends_on`` relations (parent -> child). ``depends_on``
  fixes the topological *resolution order* (Kahn's algorithm in
  ``IdentityGeneratorConfigurable._build_dag``); the prompt context is
  cumulative (every already-resolved value is passed along), so the DAG
  shows which parents are *guaranteed* present when a child is filled.
* Right panel -- the per-category *method* pipeline (the inner sequence of
  LLM calls / Python sampling that fills one field), plus a stats box.

Run from the repo root:
``python docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py``
"""

from __future__ import annotations

import json
import textwrap

import yaml
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

PROJECT_ROOT = Path(__file__).resolve().parents[4]
STRATEGY_DIR = PROJECT_ROOT / "config/synthetic/axes/strategies"
LAYOUT_DIR = PROJECT_ROOT / "config/gui/layouts"
SIM_CONFIG = PROJECT_ROOT / "config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json"
OUT_DIR = Path(__file__).resolve().parent

# The five strategies the analysis targets (stem of the strategy JSON).
STRATEGIES = [
    "all_pick",
    "all_pick_dag",
    "all_generate_pick",
    "all_generate_evaluate_pick",
    "all_generate_evaluate_random_pick",
]

# One colour per per-category method. A strategy is single-method, so the DAG
# is drawn in that method's colour; the legend stays comparable across files.
METHOD_COLORS = {
    "pick": "#2563eb",                            # blue
    "generate_pick": "#059669",                   # green
    "generate_evaluate_pick": "#d97706",          # amber
    "generate_evaluate_random_pick": "#7c3aed",   # violet
}
KIND_COLORS = {
    "context": "#e5e7eb",   # light grey  -- assemble cumulative context
    "llm": None,            # filled with the method colour
    "python": "#9ca3af",    # mid grey    -- deterministic Python step
    "output": "#111827",    # near-black  -- resolved value written
    "loop": "#fca5a5",       # red-ish     -- bounded retry / reconcile loop
}

# Inner method pipelines. Each step: (label, kind). ``llm`` steps are LLM calls
# (each wrapped in a 3x JSON-parse retry); ``loop`` marks the weight/candidate
# reconcile retry loop; ``python`` marks deterministic sampling/clamping.
METHOD_PIPELINES = {
    "pick": [
        ("Assemble cumulative\ncontext (resolved so far)", "context"),
        ("LLM: pick one value\n{\"value\": ...}", "llm"),
        ("clamp/round\n(numeric only)", "python"),
        ("write resolved value", "output"),
    ],
    "generate_pick": [
        ("Assemble cumulative\ncontext (resolved so far)", "context"),
        ("LLM: enumerate candidates\n{\"candidates\": [...]}", "llm"),
        ("LLM: select one\n{\"value\": ...}", "llm"),
        ("clamp/round\n(numeric only)", "python"),
        ("write resolved value", "output"),
    ],
    "generate_evaluate_pick": [
        ("Assemble cumulative\ncontext (resolved so far)", "context"),
        ("LLM: enumerate candidates\n(truncate to 25)", "llm"),
        ("LLM: evaluate weights\n{\"weights\": [...]}", "llm"),
        ("normalize + reconcile\nweight count (retry loop)", "loop"),
        ("LLM: select argmax-ish\n{\"value\": ...}", "llm"),
        ("clamp/round\n(numeric only)", "python"),
        ("write resolved value", "output"),
    ],
    "generate_evaluate_random_pick": [
        ("Assemble cumulative\ncontext (resolved so far)", "context"),
        ("LLM: enumerate candidates\n(categorical path)", "llm"),
        ("LLM: evaluate weights\n{\"weights\": [...]}", "llm"),
        ("normalize + reconcile\nweight count (retry loop)", "loop"),
        ("Python: random.choices\n(weighted sample)", "python"),
        ("write resolved value", "output"),
    ],
}

# Numeric variant note for generate_evaluate_random_pick (only `age` here).
RANDOM_NUMERIC_NOTE = (
    "Numeric fields (e.g. age) take a shorter branch:\n"
    "  context -> LLM: specify distribution\n"
    "  {normal|uniform|beta, mean, std}\n"
    "  -> Python: numpy sample -> clamp -> write\n"
    "  (1 LLM call + Python sample)"
)

LLM_CALLS_PER_CATEGORY = {
    "pick": "1 LLM call",
    "generate_pick": "2 LLM calls",
    "generate_evaluate_pick": "3 LLM calls (+ eval retries)",
    "generate_evaluate_random_pick": "2 LLM calls + Python sample\n(numeric: 1 + sample)",
}


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def numeric_categories() -> set[str]:
    cats = load_json(SIM_CONFIG).get("categories", {})
    return {k for k, v in cats.items() if isinstance(v, dict) and "min" in v and "max" in v}


def short_label(name: str) -> str:
    """Wrap long category names onto two lines for compact node boxes."""
    if "_" in name and len(name) > 12:
        parts = name.split("_")
        mid = len(parts) // 2
        return "\n".join(["_".join(parts[:mid]), "_".join(parts[mid:])])
    return name


def draw_dag(ax, categories: dict, layout: dict, method: str, numeric: set[str]) -> None:
    color = METHOD_COLORS[method]
    # Layout y grows downward (GUI canvas); flip so the diagram reads naturally.
    pos = {name: (xy[0], -xy[1]) for name, xy in layout.items()}

    n_edges = 0
    for cat, cfg in categories.items():
        for dep in cfg.get("depends_on", []):
            if dep not in pos or cat not in pos:
                continue
            arrow = FancyArrowPatch(
                pos[dep], pos[cat],
                arrowstyle="-|>", mutation_scale=12,
                shrinkA=22, shrinkB=22,
                color="#6b7280", lw=1.2, alpha=0.8,
                connectionstyle="arc3,rad=0.08", zorder=1,
            )
            ax.add_patch(arrow)
            n_edges += 1

    bw, bh = 58, 34  # node half-extents in layout units (for text box sizing)
    for cat in categories:
        if cat not in pos:
            continue
        x, y = pos[cat]
        is_num = cat in numeric
        box = FancyBboxPatch(
            (x - bw, y - bh), 2 * bw, 2 * bh,
            boxstyle="round,pad=3,rounding_size=10",
            linewidth=2.0 if is_num else 1.4,
            edgecolor="#111827" if is_num else color,
            facecolor=color, alpha=0.18 if not is_num else 0.32,
            zorder=2,
        )
        ax.add_patch(box)
        ax.text(
            x, y, short_label(cat),
            ha="center", va="center", fontsize=6.6,
            color="#111827", zorder=3, fontweight="bold" if is_num else "normal",
        )

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    pad = 110
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    root_note = (
        "No declared dependencies: all 17 fields are roots.\n"
        "Kahn order is arbitrary; context still accumulates\nevery resolved value as it is filled."
        if n_edges == 0
        else "Arrows = depends_on (parent resolved before child).\n"
             "Sets the topological order; prompt context is\ncumulative over all resolved fields."
    )
    ax.set_title(
        f"Category dependency DAG  ({len(categories)} fields, {n_edges} edges)",
        fontsize=11, fontweight="bold", pad=10,
    )
    ax.text(
        0.5, -0.02, root_note, transform=ax.transAxes,
        ha="center", va="top", fontsize=8, color="#374151",
    )


def draw_pipeline(ax, method: str) -> None:
    steps = METHOD_PIPELINES[method]
    color = METHOD_COLORS[method]
    ax.set_xlim(0, 10)
    n = len(steps)
    ax.set_ylim(0, n + 1.5)
    ax.axis("off")
    ax.set_title("Per-field method pipeline", fontsize=11, fontweight="bold", pad=10)

    box_w, box_h = 7.2, 0.74
    cx = 5.0
    for i, (label, kind) in enumerate(steps):
        y = n - i
        face = color if kind == "llm" else KIND_COLORS[kind]
        text_color = "white" if kind in ("output", "llm") else "#111827"
        alpha = 0.92 if kind == "llm" else (1.0 if kind in ("output", "python", "loop") else 1.0)
        box = FancyBboxPatch(
            (cx - box_w / 2, y - box_h / 2), box_w, box_h,
            boxstyle="round,pad=0.06,rounding_size=0.12",
            linewidth=1.3, edgecolor="#374151",
            facecolor=face, alpha=alpha, zorder=2,
        )
        ax.add_patch(box)
        ax.text(cx, y, label, ha="center", va="center", fontsize=7.6,
                color=text_color, zorder=3)
        if kind == "llm":
            ax.text(cx + box_w / 2 + 0.15, y, "x3 JSON\nretry", ha="left", va="center",
                    fontsize=6.0, color="#6b7280", zorder=3)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch(
                (cx, y - box_h / 2), (cx, y - 1 + box_h / 2),
                arrowstyle="-|>", mutation_scale=12, color="#374151", lw=1.4, zorder=1,
            ))

    if method == "generate_evaluate_random_pick":
        ax.text(cx, 0.35, RANDOM_NUMERIC_NOTE, ha="center", va="center",
                fontsize=6.4, color="#374151", family="monospace",
                bbox=dict(boxstyle="round", fc="#f3f4f6", ec="#d1d5db"))


def render(strategy: str, numeric: set[str]) -> None:
    data = load_yaml(STRATEGY_DIR / f"{strategy}.yaml")
    layout = load_json(LAYOUT_DIR / f"{strategy}.layout.json")
    categories = data["categories"]
    description = data.get("description", "")
    method = next(iter(categories.values()))["method"]

    fig = plt.figure(figsize=(17, 9))
    gs = fig.add_gridspec(1, 2, width_ratios=[2.35, 1.0], wspace=0.04)
    ax_dag = fig.add_subplot(gs[0, 0])
    ax_pipe = fig.add_subplot(gs[0, 1])

    draw_dag(ax_dag, categories, layout, method, numeric)
    draw_pipeline(ax_pipe, method)

    fig.suptitle(
        f"Strategy: {strategy}   (method = {method})",
        fontsize=15, fontweight="bold", y=0.985,
    )
    # Description as a wrapped sub-title block (manual wrap so it never
    # overflows the figure width or collides with the panel titles).
    wrapped = "\n".join(textwrap.wrap(description, width=165))
    fig.text(0.5, 0.952, wrapped, ha="center", va="top", fontsize=8.5,
             color="#374151")

    # Stats / legend box bottom-right.
    stats = (
        f"LLM calls / field:  {LLM_CALLS_PER_CATEGORY[method]}\n"
        f"Fields:  {len(categories)}     "
        f"Numeric:  {sorted(set(categories) & numeric) or '—'}"
    )
    fig.text(0.985, 0.02, stats, ha="right", va="bottom", fontsize=8,
             color="#111827",
             bbox=dict(boxstyle="round", fc="#f9fafb", ec="#d1d5db"))

    legend_handles = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=METHOD_COLORS[method],
               markersize=12, label=f"field ({method})", alpha=0.5),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=METHOD_COLORS[method],
               markeredgecolor="#111827", markeredgewidth=2, markersize=12,
               label="numeric field (bold edge)", alpha=0.7),
        Line2D([0], [0], color="#6b7280", lw=1.4, label="depends_on edge"),
    ]
    ax_dag.legend(handles=legend_handles, loc="upper left", fontsize=7.5,
                  framealpha=0.9, borderpad=0.6)

    fig.subplots_adjust(top=0.85, bottom=0.06, left=0.01, right=0.99)

    svg_path = OUT_DIR / f"{strategy}.svg"
    png_path = OUT_DIR / f"{strategy}.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight")
    fig.savefig(png_path, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {svg_path.name} + {png_path.name}")


def main() -> None:
    numeric = numeric_categories()
    print(f"Rendering {len(STRATEGIES)} strategy diagrams to {OUT_DIR} ...")
    for strategy in STRATEGIES:
        render(strategy, numeric)
    print("done.")


if __name__ == "__main__":
    main()

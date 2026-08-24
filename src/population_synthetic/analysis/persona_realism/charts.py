"""charts.py -- pure rendering of ONE combination's realism structures into figures.

Two per-combination publication figures for the persona-realism judge:

* :func:`plot_typicality_distribution` -- one combination's per-persona mean
  typicality over its ``can_exist`` subset, as a 0-10 integer-bucket histogram
  with the unusual-tail region shaded (the "how far into the real tails does this
  combination reach" view).
* :func:`plot_clash_taxonomy` -- one combination's attribute-pair clash taxonomy
  (a horizontal bar per ``(pair, severity)`` clash, ranked by the number of
  personas exhibiting it).

Both take a single combination's structures and nothing else. The cross-combination
headline map now belongs to ``realism_ranking``'s chart module, where the real
population is plotted as an ordinary competitor rather than pinned to the origin.

Pure sink boundary (02-architecture guide sect. 9): this module never touches
disk, never knows a file path, a DPI, or which country produced the data -- it
only turns already-computed structures into a returned ``Figure``. The caller
(:mod:`artifacts`) saves (via ``analysis/utils/figures.py::save_figure``) and the
figure closes there. The non-interactive ``Agg`` backend is selected lazily
inside each function so importing this module never touches a display.
"""

from __future__ import annotations

from typing import Sequence

from population_synthetic.analysis.persona_realism.reduce import ClashKey
from population_synthetic.analysis.utils.palette import (
    CATEGORICAL_SERIES,
    HIGHLIGHT_ACCENT,
    NEUTRAL_GREY,
    SEVERITY_SERIES,
)
from population_synthetic.analysis.utils.realism_csv import SEVERITY_LEVELS, SEVERITY_RANK
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    AXIS_TITLE,
    FULL,
    LEGEND_LABEL,
    PANEL_TITLE,
    TICK_LABEL,
    figure_size,
    grow_height,
    house_style,
)

# Severity -> bar colour / legend caption for the clash taxonomy (S3 hard
# contradiction reddest). These are protocol-fixed severity labels (see judge.py),
# so the mappings are structural presentation constants, not tunables; the *order*
# they are drawn in comes from SEVERITY_LEVELS, the one definition of it.
_SEVERITY_COLORS: dict[str, str] = {
    "S3": SEVERITY_SERIES[0],
    "S2": SEVERITY_SERIES[1],
    "S1": SEVERITY_SERIES[2],
}
_SEVERITY_CAPTIONS: dict[str, str] = {"S3": "S3 (hard)", "S2": "S2 (near)", "S1": "S1 (unusual)"}
_TYPICALITY_COLOR = CATEGORICAL_SERIES[0]
_TAIL_COLOR = HIGHLIGHT_ACCENT

# The 0-10 ordinal typicality domain (prompt-schema constant, mirrors judge.py).
_TYPICALITY_MIN = 0
_TYPICALITY_MAX = 10


@house_style
def plot_typicality_distribution(
    typicality_means: Sequence[float],
    combo_label: str,
    *,
    tail_threshold: float | None = None,
):
    """Render one combination's can_exist typicality-mean distribution.

    ``typicality_means`` is the per-persona mean typicality over the combination's
    majority-possible personas (``ComboRealism.typicality_means``). An **empty**
    sample is the caller's cue to skip this chart (it is not special-cased here).
    Bars are the count per integer 0-10 bucket (each mean rounded to its nearest
    bucket); when *tail_threshold* is given, buckets at or below it are drawn in
    the tail colour to mark the unusual-but-possible reach. Returns the ``Figure``
    unsaved and open.
    """
    import matplotlib.pyplot as plt

    buckets = list(range(_TYPICALITY_MIN, _TYPICALITY_MAX + 1))
    counts = {b: 0 for b in buckets}
    for value in typicality_means:
        counts[int(round(value))] += 1

    colors = [
        _TAIL_COLOR if (tail_threshold is not None and b <= tail_threshold) else _TYPICALITY_COLOR
        for b in buckets
    ]

    fig, ax = plt.subplots(figsize=figure_size(FULL, 5))
    bars = ax.bar(buckets, [counts[b] for b in buckets], color=colors, edgecolor="white", linewidth=0.4)
    ax.bar_label(bars, fmt="%d", fontsize=ANNOTATION, padding=2)
    ax.set_xticks(buckets)
    ax.set_xlabel("Mean typicality (0 = unusual-but-possible, 10 = modal)", fontsize=AXIS_TITLE)
    ax.set_ylabel("Personas", fontsize=AXIS_TITLE)
    ax.set_title(
        f"{combo_label} -- typicality distribution (can_exist personas)",
        fontsize=PANEL_TITLE,
        fontweight="bold",
    )
    ax.tick_params(axis="both", labelsize=TICK_LABEL)
    if tail_threshold is not None:
        ax.axvline(tail_threshold + 0.5, color="gray", linestyle="--", linewidth=0.7, alpha=0.7)
    fig.tight_layout()
    return fig


def _clash_label(key: ClashKey) -> str:
    """Human-readable ``attr_a x attr_b (severity)`` label for one clash key."""
    a, b = key.pair
    return f"{a} x {b} ({key.severity})"


@house_style
def plot_clash_taxonomy(clash_taxonomy: dict[ClashKey, int], combo_label: str):
    """Render one combination's attribute-pair clash taxonomy as ranked bars.

    ``clash_taxonomy`` maps each :class:`ClashKey` to the number of personas that
    exhibited it in at least one round (``ComboRealism.clash_taxonomy``). An
    **empty** taxonomy is the caller's cue to skip this chart. Bars are sorted by
    persona count (descending), then severity, and coloured by severity. Returns
    the ``Figure`` unsaved and open.
    """
    import matplotlib.pyplot as plt

    # Rank by persona-count desc, then S3>S2>S1, then label for a stable order.
    items = sorted(
        clash_taxonomy.items(),
        key=lambda kv: (
            -kv[1], SEVERITY_RANK.get(kv[0].severity, len(SEVERITY_LEVELS)), _clash_label(kv[0])
        ),
    )
    labels = [_clash_label(k) for k, _ in items]
    counts = [v for _, v in items]
    colors = [_SEVERITY_COLORS.get(k.severity, NEUTRAL_GREY) for k, _ in items]

    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(items), per_item=0.4, padding=1.5, minimum=3.0)))
    y_pos = range(len(items))
    bars = ax.barh(list(y_pos), counts, color=colors, edgecolor="white", linewidth=0.4)
    ax.bar_label(bars, fmt="%d", fontsize=ANNOTATION, padding=3)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    ax.invert_yaxis()  # highest count at the top
    ax.set_xlabel("Personas exhibiting the clash (>=1 round)", fontsize=AXIS_TITLE)
    ax.set_title(f"{combo_label} -- attribute-clash taxonomy", fontsize=PANEL_TITLE, fontweight="bold")
    ax.tick_params(axis="x", labelsize=TICK_LABEL)

    handles = [plt.Rectangle((0, 0), 1, 1, color=_SEVERITY_COLORS[s]) for s in SEVERITY_LEVELS]
    ax.legend(handles, [_SEVERITY_CAPTIONS[s] for s in SEVERITY_LEVELS], fontsize=LEGEND_LABEL, loc="lower right")
    fig.tight_layout()
    return fig

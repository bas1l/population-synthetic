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

# Severity -> bar colour for the clash taxonomy (S3 hard contradiction reddest).
# These are protocol-fixed severity labels (see judge.py), so the mapping is a
# structural presentation constant, not a tunable.
_SEVERITY_COLORS: dict[str, str] = {"S3": "#C44E52", "S2": "#DD8452", "S1": "#8C8C8C"}
_TYPICALITY_COLOR = "#4878CF"
_TAIL_COLOR = "#C44E52"

# The 0-10 ordinal typicality domain (prompt-schema constant, mirrors judge.py).
_TYPICALITY_MIN = 0
_TYPICALITY_MAX = 10


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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buckets = list(range(_TYPICALITY_MIN, _TYPICALITY_MAX + 1))
    counts = {b: 0 for b in buckets}
    for value in typicality_means:
        counts[int(round(value))] += 1

    colors = [
        _TAIL_COLOR if (tail_threshold is not None and b <= tail_threshold) else _TYPICALITY_COLOR
        for b in buckets
    ]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(buckets, [counts[b] for b in buckets], color=colors, edgecolor="white", linewidth=0.4)
    ax.bar_label(bars, fmt="%d", fontsize=7, padding=2)
    ax.set_xticks(buckets)
    ax.set_xlabel("Mean typicality (0 = unusual-but-possible, 10 = modal)", fontsize=9)
    ax.set_ylabel("Personas", fontsize=9)
    ax.set_title(f"{combo_label} -- typicality distribution (can_exist personas)", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    if tail_threshold is not None:
        ax.axvline(tail_threshold + 0.5, color="gray", linestyle="--", linewidth=0.7, alpha=0.7)
    fig.tight_layout()
    return fig


def _clash_label(key: ClashKey) -> str:
    """Human-readable ``attr_a x attr_b (severity)`` label for one clash key."""
    a, b = key.pair
    return f"{a} x {b} ({key.severity})"


def plot_clash_taxonomy(clash_taxonomy: dict[ClashKey, int], combo_label: str):
    """Render one combination's attribute-pair clash taxonomy as ranked bars.

    ``clash_taxonomy`` maps each :class:`ClashKey` to the number of personas that
    exhibited it in at least one round (``ComboRealism.clash_taxonomy``). An
    **empty** taxonomy is the caller's cue to skip this chart. Bars are sorted by
    persona count (descending), then severity, and coloured by severity. Returns
    the ``Figure`` unsaved and open.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Rank by persona-count desc, then S3>S2>S1, then label for a stable order.
    severity_rank = {"S3": 0, "S2": 1, "S1": 2}
    items = sorted(
        clash_taxonomy.items(),
        key=lambda kv: (-kv[1], severity_rank.get(kv[0].severity, 9), _clash_label(kv[0])),
    )
    labels = [_clash_label(k) for k, _ in items]
    counts = [v for _, v in items]
    colors = [_SEVERITY_COLORS.get(k.severity, "#8C8C8C") for k, _ in items]

    fig, ax = plt.subplots(figsize=(9, max(3.0, len(items) * 0.4 + 1.5)))
    y_pos = range(len(items))
    bars = ax.barh(list(y_pos), counts, color=colors, edgecolor="white", linewidth=0.4)
    ax.bar_label(bars, fmt="%d", fontsize=7, padding=3)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()  # highest count at the top
    ax.set_xlabel("Personas exhibiting the clash (>=1 round)", fontsize=9)
    ax.set_title(f"{combo_label} -- attribute-clash taxonomy", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", labelsize=8)

    handles = [plt.Rectangle((0, 0), 1, 1, color=_SEVERITY_COLORS[s]) for s in ("S3", "S2", "S1")]
    ax.legend(handles, ["S3 (hard)", "S2 (near)", "S1 (unusual)"], fontsize=8, loc="lower right")
    fig.tight_layout()
    return fig

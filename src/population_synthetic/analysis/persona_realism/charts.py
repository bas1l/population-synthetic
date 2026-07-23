"""charts.py -- pure rendering of persona-realism structures into matplotlib figures.

Three publication figures for the persona-realism judge:

* :func:`plot_typicality_distribution` -- one combination's per-persona mean
  typicality over its ``can_exist`` subset, as a 0-10 integer-bucket histogram
  with the unusual-tail region shaded (the "how far into the real tails does this
  combination reach" view).
* :func:`plot_clash_taxonomy` -- one combination's attribute-pair clash taxonomy
  (a horizontal bar per ``(pair, severity)`` clash, ranked by the number of
  personas exhibiting it).
* :func:`plot_headline_map` -- the cross-combination 2-D map: x = impossibility
  rate, y = typicality-dispersion distance-to-SCB, with the SCB real population
  drawn as a distinct reference point at ``y == 0`` (it *is* the dispersion
  reference, so its distance to itself is zero).

Pure sink boundary (02-architecture guide sect. 9): this module never touches
disk, never knows a file path, a DPI, or which country produced the data -- it
only turns already-computed structures into a returned ``Figure``. The caller
(:mod:`artifacts`) saves (via ``analysis/utils/figures.py::save_figure``) and the
figure closes there. The non-interactive ``Agg`` backend is selected lazily
inside each function so importing this module never touches a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from population_synthetic.analysis.persona_realism.reduce import ClashKey

# Severity -> bar colour for the clash taxonomy (S3 hard contradiction reddest).
# These are protocol-fixed severity labels (see judge.py), so the mapping is a
# structural presentation constant, not a tunable.
_SEVERITY_COLORS: dict[str, str] = {"S3": "#C44E52", "S2": "#DD8452", "S1": "#8C8C8C"}
_TYPICALITY_COLOR = "#4878CF"
_TAIL_COLOR = "#C44E52"
_COMBO_COLOR = "#4878CF"
_REFERENCE_COLOR = "#C44E52"

# The 0-10 ordinal typicality domain (prompt-schema constant, mirrors judge.py).
_TYPICALITY_MIN = 0
_TYPICALITY_MAX = 10


@dataclass(frozen=True)
class HeadlinePoint:
    """One competitor's position on the headline map (a pure plot-input record).

    ``impossibility_rate`` is the x-coordinate (share of majority-impossible
    personas); ``dispersion_distance`` is the y-coordinate (this combination's
    typicality-dispersion distance to the SCB reference -- ``0`` for SCB itself).
    ``is_reference`` flags the SCB real population so the plotter draws it
    distinctly. ``n_personas`` is carried only to size/annotate the marker.
    """

    label: str
    impossibility_rate: float
    dispersion_distance: float
    is_reference: bool = False
    n_personas: int = 0


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


def plot_headline_map(points: Sequence[HeadlinePoint], *, measure_label: str = "variance"):
    """Render the cross-combination headline map.

    ``points`` are the competitors (synthetic combinations *and* the SCB real
    population); each carries its impossibility rate (x) and its typicality
    dispersion distance-to-SCB (y). The SCB reference (``is_reference``) is drawn
    as a distinct star at ``y == 0``. *measure_label* names which dispersion
    measure the y-axis distance uses (for the axis title). An **empty** *points*
    sequence raises (nothing to map). Returns the ``Figure`` unsaved and open.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not points:
        raise ValueError("plot_headline_map requires at least one competitor point (got none)")

    fig, ax = plt.subplots(figsize=(9, 7))
    for pt in points:
        if pt.is_reference:
            ax.scatter(
                pt.impossibility_rate, pt.dispersion_distance,
                marker="*", s=320, color=_REFERENCE_COLOR, edgecolor="black", linewidth=0.6,
                zorder=3, label="SCB reference",
            )
        else:
            ax.scatter(
                pt.impossibility_rate, pt.dispersion_distance,
                marker="o", s=90, color=_COMBO_COLOR, edgecolor="white", linewidth=0.5, zorder=2,
            )
        ax.annotate(
            pt.label, (pt.impossibility_rate, pt.dispersion_distance),
            textcoords="offset points", xytext=(6, 4), fontsize=7,
        )

    ax.set_xlabel("Impossibility rate (share of internally-contradictory personas)", fontsize=9)
    ax.set_ylabel(f"Typicality dispersion distance to SCB ({measure_label})", fontsize=9)
    ax.set_title("Persona realism -- coherence vs typicality-spectrum map", fontsize=12, fontweight="bold")
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.7, alpha=0.7, zorder=0)
    ax.tick_params(axis="both", labelsize=8)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=8, loc="best")
    fig.tight_layout()
    return fig

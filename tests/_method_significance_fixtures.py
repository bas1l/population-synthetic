"""Fixtures for the method x method pairwise-significance grid.

Builds the **serialised** block ``method_significance/builder.py`` emits rather than
running the builder, because the renderer under test is a pure consumer of that block:
handing it a dict is what lets a test state exactly which pairs were tested, which were
never tested, and which p sits on a threshold -- none of which a fitted grid can be made
to produce on demand.

Real axis ids throughout. Every id these figures print is resolved through
``analysis/utils/labels.py``, which raises on an id config does not declare, so a fixture
built from invented ids would only ever exercise the raise.

The star thresholds are read from the same config the renderer reads, never restated
here: a test that carried its own copy would keep passing after the cutoffs moved.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from population_synthetic.analysis.method_significance.builder import load_comparison_config
from population_synthetic.analysis.model_ranking.loader import scheme_attributes
from population_synthetic.analysis.utils.axes import strategy_complexity_order

#: The five v1 families in the config-derived complexity order -- the live Sweden axis.
FIVE_METHODS: list[str] = strategy_complexity_order([
    "all_generate_evaluate_random_pick",
    "all_generate_evaluate_pick",
    "all_generate_pick",
    "all_pick_dag",
    "all_pick",
])

#: Both versions of all five families: the widest method axis the sweep can produce, and
#: the one the canvas budget is tightest on.
TEN_METHODS: list[str] = strategy_complexity_order([
    f"{family}{suffix}"
    for family in (
        "all_generate_evaluate_random_pick",
        "all_generate_evaluate_pick",
        "all_generate_pick",
        "all_pick_dag",
        "all_pick",
    )
    for suffix in ("", "_v2")
])

#: Two attributes, both carrying a canonical display label.
ATTRIBUTES: list[str] = ["education_level", "housing_tenure"]

#: The live Swedish analysed axis, read from the same config accessor a run resolves it
#: through rather than transcribed: 14 categories, which with the pooled Overall panel is
#: the 15-column shape the reference-method grid is actually drawn at. A hardcoded copy
#: would keep passing after the analysed axis moved, which is the one thing a canvas
#: budget test must not do.
LIVE_ATTRIBUTES: list[str] = scheme_attributes("swedish_02")


def star_thresholds() -> list[dict[str, Any]]:
    """The config's own p-to-symbol cutoffs, as the block echoes them."""
    return load_comparison_config()["star_thresholds"]


def ns_symbol() -> str:
    """The config's own symbol for a pair tested and found non-significant."""
    return load_comparison_config()["ns_symbol"]


def pair_matrix(
    methods: Sequence[str],
    pairs: Mapping[tuple[int, int], tuple[float, float, int]],
) -> dict[str, Any]:
    """The builder's oriented ``k x k`` views, from an upper-triangle map of tested pairs.

    Args:
        methods: The index order of both axes.
        pairs: ``(i, j)`` with ``i < j`` -> ``(p_holm, mean_diff, n_blocks)``, where
            *mean_diff* is the row-minus-column difference **at** ``(i, j)``. Every pair
            the map omits is untested and stays ``None`` on both sides of the diagonal,
            which is exactly what the builder leaves for a pair it did not test.
    """
    k = len(methods)
    p_holm: list[list[float | None]] = [[None] * k for _ in range(k)]
    mean_diff: list[list[float | None]] = [[None] * k for _ in range(k)]
    n_blocks: list[list[int | None]] = [[None] * k for _ in range(k)]
    dz: list[list[float | None]] = [[None] * k for _ in range(k)]
    for (i, j), (p, difference, n) in pairs.items():
        p_holm[i][j] = p_holm[j][i] = float(p)
        n_blocks[i][j] = n_blocks[j][i] = int(n)
        mean_diff[i][j] = float(difference)
        mean_diff[j][i] = -float(difference)
        dz[i][j] = float(difference)
        dz[j][i] = -float(difference)
    return {
        "methods": list(methods),
        "p_holm": p_holm,
        "mean_diff": mean_diff,
        "n_blocks": n_blocks,
        "dz": dz,
    }


def panel(
    methods: Sequence[str],
    pairs: Mapping[tuple[int, int], tuple[float, float, int]],
    *,
    n_models: int = 6,
    insufficient_n: bool = False,
    note: str | None = None,
    omnibus_p: float | None = 1e-5,
    means: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """One serialised comparison panel, carrying only what the grid reads.

    *note* is the builder's own wording for a panel it recorded but did not chart; the
    renderer prints it verbatim and authors none of its own, so a test that wants the
    placeholder supplies both it and *insufficient_n*.

    *means* is the panel's per-method mean TV-similarity, which the grids do not read but
    which a test asserting the printed sign checks the cell against: the difference in a
    cell has to be one subtraction of these two numbers and not the other.
    """
    return {
        "n_models": n_models,
        "insufficient_n": insufficient_n,
        "note": note,
        "means": dict(means) if means is not None else {},
        "omnibus": {"test": "rm_anova", "p": omnibus_p, "p_bh": None},
        "pair_matrix": pair_matrix(methods, pairs),
    }


def result(
    methods: Sequence[str],
    panels: Mapping[str, dict[str, Any]],
    *,
    country: str = "swedish",
) -> dict[str, Any]:
    """The built analysis, reduced to the keys the pairwise grid consumes."""
    return {
        "metadata": {
            "country": country,
            "attributes": [key for key in panels if key != "overall"],
            "method_order": list(methods),
        },
        "method_comparison": {
            "methods": list(methods),
            "star_thresholds": star_thresholds(),
            "ns_symbol": ns_symbol(),
            "panels": dict(panels),
        },
    }


def significant_pairs(
    methods: Sequence[str],
    *,
    p: float = 1e-5,
    step: float = 0.05,
    n_blocks: int = 6,
) -> dict[tuple[int, int], tuple[float, float, int]]:
    """Every pair tested, at one p, with a difference that grows with the gap.

    The default for a fixture that is about the *figure* rather than about any one cell:
    a fully populated square whose text differs cell by cell and whose sign flips across
    the diagonal.
    """
    return {
        (i, j): (p, step * (j - i), n_blocks)
        for i in range(len(methods))
        for j in range(i + 1, len(methods))
    }


def pairs_from_means(
    methods: Sequence[str],
    means: Mapping[str, float],
    *,
    p: float = 1e-5,
    n_blocks: int = 6,
) -> dict[tuple[int, int], tuple[float, float, int]]:
    """Every pair tested, each difference taken from *means* in the builder's own order.

    ``mean_diff[i][j]`` is ``means[methods[i]] - means[methods[j]]`` -- row minus column,
    the convention ``builder._method_panel`` fixes. Pairing this with the panel's *means*
    is what lets a test check that a renderer printed the subtraction it claims to.
    """
    return {
        (i, j): (p, float(means[methods[i]]) - float(means[methods[j]]), n_blocks)
        for i in range(len(methods))
        for j in range(i + 1, len(methods))
    }


# --------------------------------------------------------------------------- #
# The reference-method gain forest                                            #
# --------------------------------------------------------------------------- #

#: One comparator's contrast against the reference:
#: ``(p_holm, gain, n_blocks, half_width)``, where *gain* is reference minus comparator
#: and *half_width* the half-width of its confidence interval. ``p_holm is None`` is an
#: undefined test and leaves the interval ``None`` too, as the builder does.
Contrast = tuple[float | None, float, int, float | None]


def forest_pair_matrix(
    methods: Sequence[str],
    contrasts: Mapping[int, Contrast],
) -> dict[str, Any]:
    """The builder's oriented pair matrix with only the reference contrasts filled in.

    *contrasts* maps a comparator's index in *methods* to its :data:`Contrast` against the
    reference, the last method. Both orientations are written the way
    ``builder._pair_matrices`` writes them: at ``(reference, comparator)`` the gain and its
    interval, at ``(comparator, reference)`` their negations with the bounds swapped.
    """
    k = len(methods)
    ref = k - 1
    square = {name: [[None] * k for _ in range(k)] for name in (
        "p_holm", "mean_diff", "n_blocks", "dz", "ci_low", "ci_high", "sd_diff",
    )}
    for c, (p, gain, n, half_width) in contrasts.items():
        square["p_holm"][ref][c] = square["p_holm"][c][ref] = p
        square["n_blocks"][ref][c] = square["n_blocks"][c][ref] = n
        square["mean_diff"][ref][c] = float(gain)
        square["mean_diff"][c][ref] = -float(gain)
        if p is not None:
            square["ci_low"][ref][c] = gain - half_width
            square["ci_high"][ref][c] = gain + half_width
            square["ci_low"][c][ref] = -(gain + half_width)
            square["ci_high"][c][ref] = -(gain - half_width)
            square["sd_diff"][ref][c] = square["sd_diff"][c][ref] = half_width
        else:
            square["sd_diff"][ref][c] = square["sd_diff"][c][ref] = 0.0
    square["methods"] = list(methods)
    return square


def forest_panel(
    methods: Sequence[str],
    contrasts: Mapping[int, Contrast],
    *,
    statistic: float = 42.0,
    df: tuple[int, int] = (4, 36),
    partial_eta_sq: float = 0.8,
    p_bh: float = 1e-9,
    insufficient_n: bool = False,
    note: str | None = None,
    identical_method_groups: list[list[str]] | None = None,
) -> dict[str, Any]:
    """One serialised panel carrying what the gain forest reads."""
    tested = sum(1 for p, *_ in contrasts.values() if p is not None)
    return {
        "n_models": 10,
        "insufficient_n": insufficient_n,
        "note": note,
        "omnibus": {
            "test": "rm_anova", "statistic": statistic, "p": p_bh / 2.0, "p_bh": p_bh,
            "df1": df[0], "df2": df[1], "partial_eta_sq": partial_eta_sq,
        },
        "pair_matrix": forest_pair_matrix(methods, contrasts),
        "correction": {"method": "holm", "scope": "all-pairs", "family_size": tested},
        "identical_method_groups": identical_method_groups or [],
    }


def forest_result(
    methods: Sequence[str],
    panels: Mapping[str, dict[str, Any]],
    *,
    country: str = "swedish_02",
) -> dict[str, Any]:
    """The built analysis, reduced to what the gain forest consumes."""
    out = result(methods, panels, country=country)
    out["method_comparison"]["confidence_level"] = load_comparison_config()["confidence_level"]
    out["method_comparison"]["identical_methods_note"] = "give identical TV-similarity"
    return out


def live_shape_forest_result(methods: Sequence[str] = FIVE_METHODS) -> dict[str, Any]:
    """The gain forest's live shape: fourteen categories, four comparators, varied evidence.

    Gains, interval widths and p values cycle through deterministic patterns spanning the
    live range (gains 0.05 to 0.62, half-widths 0.02 to 0.2, from ``****`` down to
    ``ns``), so labels land at every height and some neighbours have to be lifted.
    """
    ps = [1e-6, 3e-4, 4e-3, 0.03, 0.2]
    panels = {}
    for a, attr in enumerate(LIVE_ATTRIBUTES):
        base = 0.08 + 0.5 * ((a * 7) % 13) / 12.0
        contrasts = {
            c: (
                ps[(a + 2 * c) % len(ps)],
                round(base - 0.04 * c + 0.03 * ((a + c) % 3), 4),
                10,
                round(0.02 + 0.18 * (((a * 5 + c * 3) % 7) / 6.0), 4),
            )
            for c in range(len(methods) - 1)
        }
        panels[attr] = forest_panel(methods, contrasts, statistic=5.0 + 23.0 * a, p_bh=10.0 ** -(a + 3))
    panels["overall"] = forest_panel(
        methods, {c: (1e-6, 0.3, 10, 0.05) for c in range(len(methods) - 1)},
    )
    return forest_result(methods, panels)

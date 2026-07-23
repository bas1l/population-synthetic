"""comparison.py -- Cross-factor scientific comparison of generation-metadata analytics.

Compares per-combo metrics across the two experimental factors -- **model** and
**method/strategy** (country held fixed) -- entirely in memory over the country's
``list[ComboSummary]`` (whose ``.samples`` already hold each combo's per-persona
value lists, keyed by the eight ``combo_aggregator.METRIC_NAMES``).  No on-disk
analytics file is read.

Contents:
    * :func:`build_summary_comparison` -- group the pooled per-persona samples by
      model and by method, run a Kruskal-Wallis omnibus test plus Dunn/Holm
      post-hoc per factor, and build a model x method matrix for heatmaps.
    * :func:`significance_from_comparison` -- reduce that rich structure to the
      JSON/CSV significance view (KW ``{H,p,df}``, Dunn Holm p-matrix, per-group
      compact-letter-display labels) under a strict per-group ``n >= 2`` guard.
    * :func:`group_label` -- the CLD-letter lookup the report writer uses for the
      CSV group columns.

The hypothesis tests live in the shared
:mod:`population_synthetic.analysis.utils.stats_tests`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from population_synthetic.analysis.generation_metadata.combo_aggregator import METRIC_NAMES, ComboSummary
from population_synthetic.analysis.utils import _stats
from population_synthetic.analysis.utils.stats_tests import dunn_posthoc, kruskal_test

__all__ = [
    # Statistics (re-exported from analysis.utils.stats_tests)
    "dunn_posthoc",
    "kruskal_test",
    # In-memory ComboSummary significance path
    "SUMMARY_METRIC_SPECS",
    "DEFAULT_ALPHA",
    "build_summary_comparison",
    "significance_from_comparison",
    "group_label",
]


# ---------------------------------------------------------------------------
# Grouping / aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate(samples: list[float], how: str) -> float | None:
    if not samples:
        return None
    if how == "median":
        return float(_stats.median(samples))
    return float(np.mean(np.asarray(samples, dtype=float)))


def _group_samples(
    records: list[ComboSummary],
    key: Callable[[ComboSummary], str],
    metric_key: str,
) -> dict[str, list[float]]:
    """Concatenate per-persona samples across combos sharing the same group key."""
    groups: dict[str, list[float]] = {}
    for r in records:
        groups.setdefault(key(r), []).extend(r.samples.get(metric_key, []))
    return groups


def _order_by_median(groups: dict[str, list[float]]) -> list[str]:
    """Order group labels by ascending median (empty groups last, then by name)."""
    def sort_key(label: str) -> tuple[int, float, str]:
        vals = groups[label]
        if not vals:
            return (1, 0.0, label)
        return (0, float(_stats.median(vals)), label)

    return sorted(groups.keys(), key=sort_key)


# ===========================================================================
# In-memory ComboSummary significance path
#
# These functions consume the country's in-memory ``list[ComboSummary]`` (whose
# ``.samples`` already hold each combo's per-persona value list, keyed by the
# eight ``combo_aggregator.METRIC_NAMES``), so no file is re-read.
# ``build_summary_comparison`` produces a rich, chart-ready structure (raw grouped
# samples + KW/Dunn + a model x method matrix); ``significance_from_comparison``
# reduces that to the JSON/CSV significance view (per-group compact-letter-display
# labels + KW p + Dunn matrix) under a strict per-group ``n >= 2`` guard.
# ===========================================================================

# Default family-wise significance level for the compact-letter display.
DEFAULT_ALPHA: float = 0.05


@dataclass(frozen=True)
class _SummaryMetricSpec:
    """Presentation + gating for one in-memory comparison metric (keyed to METRIC_NAMES)."""

    key: str
    label: str
    unit: str
    token_gated: bool
    cell_agg: str  # "median" or "mean" -- summary for heatmap cells


# One spec per ``combo_aggregator.METRIC_NAMES`` entry, in the same order. Token
# families (input/output/total tokens, cost) are gated on token telemetry: a
# combo without token data contributes nothing to them, and a country with no
# token data at all skips them entirely.
SUMMARY_METRIC_SPECS: tuple[_SummaryMetricSpec, ...] = (
    _SummaryMetricSpec("time", "wall-clock time / persona", "s", False, "median"),
    _SummaryMetricSpec("input_tokens", "input tokens / persona", "tokens", True, "median"),
    _SummaryMetricSpec("output_tokens", "output tokens / persona", "tokens", True, "median"),
    _SummaryMetricSpec("total_tokens", "total tokens / persona", "tokens", True, "median"),
    _SummaryMetricSpec("calls", "LLM calls / persona", "calls", False, "median"),
    _SummaryMetricSpec("retry_rate", "retry rate / persona", "rate", False, "mean"),
    _SummaryMetricSpec("error_rate", "error rate / persona", "rate", False, "mean"),
    _SummaryMetricSpec("cost", "estimated USD cost / persona", "USD", True, "median"),
)

# Fail-fast on drift: the spec table must cover exactly METRIC_NAMES, in order.
if tuple(s.key for s in SUMMARY_METRIC_SPECS) != tuple(METRIC_NAMES):
    raise RuntimeError(
        "SUMMARY_METRIC_SPECS is out of sync with combo_aggregator.METRIC_NAMES: "
        f"{[s.key for s in SUMMARY_METRIC_SPECS]} != {list(METRIC_NAMES)}"
    )

_SUMMARY_SPECS_BY_KEY: dict[str, _SummaryMetricSpec] = {s.key: s for s in SUMMARY_METRIC_SPECS}

# Factor label -> the block key used throughout the comparison / significance
# structures (single source of truth for the two experimental factors).
FACTORS: tuple[tuple[str, str], ...] = (("model", "by_model"), ("method", "by_method"))


def build_summary_comparison(
    summaries: list[ComboSummary],
    metric_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Build the rich, chart-ready comparison structure from in-memory combos.

    Reads each combo's ``.samples`` (keyed by
    :data:`combo_aggregator.METRIC_NAMES`).  :class:`ComboSummary` exposes the
    ``model``/``strategy``/``samples``/``has_token_data`` attributes the shared
    grouping helpers need, so :func:`_group_samples` / :func:`_order_by_median` /
    :func:`_aggregate` operate over them directly.

    Per metric it groups the pooled per-persona samples by **model** (pooled across
    methods) and by **method** (pooled across models), runs a Kruskal-Wallis
    omnibus + Dunn/Holm post-hoc per factor, and fills a model x method cell
    matrix.  A token-gated metric drops combos without token telemetry first; a
    metric with no usable samples is marked ``skipped`` with a reason.
    """
    specs = [s for s in SUMMARY_METRIC_SPECS if metric_keys is None or s.key in metric_keys]
    models = sorted({s.model for s in summaries})
    methods = sorted({s.strategy for s in summaries})
    countries = sorted({s.country for s in summaries})

    metrics_out: dict[str, Any] = {}
    for spec in specs:
        recs = [s for s in summaries if (s.has_token_data or not spec.token_gated)]
        entry: dict[str, Any] = {
            "label": spec.label,
            "unit": spec.unit,
            "kind": "dist",
            "token_gated": spec.token_gated,
            "cell_agg": spec.cell_agg,
            "skipped": None,
            "by_model": None,
            "by_method": None,
            "matrix": None,
        }

        if not recs or all(not r.samples.get(spec.key) for r in recs):
            entry["skipped"] = (
                "no combo carries token/timing data"
                if spec.token_gated
                else "no samples available"
            )
            metrics_out[spec.key] = entry
            continue

        by_model = _group_samples(recs, lambda r: r.model, spec.key)
        by_method = _group_samples(recs, lambda r: r.strategy, spec.key)
        entry["by_model"] = {
            "order": _order_by_median(by_model),
            "groups": by_model,
            "kruskal": kruskal_test(by_model),
            "dunn": dunn_posthoc(by_model),
        }
        entry["by_method"] = {
            "order": _order_by_median(by_method),
            "groups": by_method,
            "kruskal": kruskal_test(by_method),
            "dunn": dunn_posthoc(by_method),
        }

        rec_models = sorted({r.model for r in recs})
        rec_methods = sorted({r.strategy for r in recs})
        values: list[list[float | None]] = []
        for model in rec_models:
            row: list[float | None] = []
            for method in rec_methods:
                cell_samples: list[float] = []
                for r in recs:
                    if r.model == model and r.strategy == method:
                        cell_samples.extend(r.samples.get(spec.key, []))
                row.append(_aggregate(cell_samples, spec.cell_agg))
            values.append(row)
        entry["matrix"] = {
            "models": rec_models,
            "methods": rec_methods,
            "cell_agg": spec.cell_agg,
            "values": values,
        }

        metrics_out[spec.key] = entry

    return {
        "metadata": {
            "n_combos": len(summaries),
            "models": models,
            "methods": methods,
            "countries": countries,
        },
        "metrics": metrics_out,
    }


# --------------------------------------------------------------------------- #
# Compact-letter display (CLD)
# --------------------------------------------------------------------------- #

def _cld_letter(index: int) -> str:
    """Bijective base-26 letter for *index* (0 -> 'a', 25 -> 'z', 26 -> 'aa')."""
    out = ""
    i = index + 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        out = chr(97 + rem) + out
    return out


def _maximal_cliques(nodes: list[str], adj: dict[str, set[str]]) -> list[set[str]]:
    """All maximal cliques of an undirected graph (Bron-Kerbosch, no pivot).

    *nodes* is small (a handful of models/methods), so the un-pivoted recursion is
    adequate.  Every node -- including one with no edges -- appears in at least one
    maximal clique (a singleton), so the caller's coverage is guaranteed.
    """
    cliques: list[set[str]] = []

    def expand(r: set[str], p: set[str], x: set[str]) -> None:
        if not p and not x:
            cliques.append(set(r))
            return
        for v in list(p):
            expand(r | {v}, p & adj[v], x & adj[v])
            p = p - {v}
            x = x | {v}

    expand(set(), set(nodes), set())
    return cliques


def _compact_letter_display(
    order: list[str],
    dunn: list[dict[str, Any]],
    alpha: float,
) -> dict[str, str]:
    """Map each group to its CLD letter string, given a Dunn/Holm pairwise result.

    Two groups that do NOT differ significantly (Holm-adjusted ``p >= alpha``, or
    that were never tested as a pair) may share a letter; groups that differ share
    none.  The display is the union of all maximal cliques of the
    "not-significantly-different" graph -- a valid CLD (a shared letter always
    implies non-significance, and every non-significant pair shares a letter),
    deterministic in *order*.  Letters run ``a, b, ...`` with clique ordering keyed
    to each clique's lowest-ranked member in *order* (so 'a' is anchored at the
    lowest-median group).  A group may carry several letters when it straddles more
    than one clique.
    """
    sig_different: set[frozenset[str]] = {
        frozenset((d["a"], d["b"]))
        for d in dunn
        if d.get("p_holm") is not None and d["p_holm"] < alpha
    }
    adj: dict[str, set[str]] = {g: set() for g in order}
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if frozenset((a, b)) not in sig_different:
                adj[a].add(b)
                adj[b].add(a)

    cliques = _maximal_cliques(order, adj)
    rank = {name: i for i, name in enumerate(order)}
    cliques.sort(key=lambda c: sorted(rank[n] for n in c))

    labels: dict[str, str] = {g: "" for g in order}
    for ci, clique in enumerate(cliques):
        letter = _cld_letter(ci)
        for name in clique:
            labels[name] += letter
    return labels


def _dunn_matrix(order: list[str], dunn: list[dict[str, Any]]) -> dict[str, Any]:
    """Symmetric Holm-adjusted Dunn p-matrix over *order* (diagonal ``1.0``)."""
    idx = {name: i for i, name in enumerate(order)}
    k = len(order)
    matrix: list[list[float | None]] = [
        [1.0 if i == j else None for j in range(k)] for i in range(k)
    ]
    for d in dunn:
        a, b = d["a"], d["b"]
        if a in idx and b in idx:
            matrix[idx[a]][idx[b]] = d["p_holm"]
            matrix[idx[b]][idx[a]] = d["p_holm"]
    return {"labels": list(order), "p_holm": matrix}


def _significance_for_factor(block: dict[str, Any] | None, alpha: float) -> dict[str, Any]:
    """Reduce one rich factor block to the letter-annotated significance view.

    Returns either ``{"skipped": reason}`` (fewer than two groups, or any group
    with ``n < 2`` -- undefined dispersion) or the computed view
    ``{"groups": [...], "kruskal": {...}, "dunn": {...}}`` with groups in ascending
    -median order, each carrying its CLD letter.
    """
    if block is None:
        return {"skipped": "metric skipped (no usable samples)"}

    groups: dict[str, list[float]] = block["groups"]
    present = {g: v for g, v in groups.items() if v}
    if len(present) < 2:
        return {"skipped": f"need >=2 groups with data, have {len(present)}"}
    undersized = sorted(g for g, v in present.items() if len(v) < 2)
    if undersized:
        return {"skipped": f"group(s) with n<2 (dispersion undefined): {undersized}"}

    order = [g for g in block["order"] if g in present]
    dunn = block["dunn"]
    letters = _compact_letter_display(order, dunn, alpha)
    groups_out = [
        {
            "name": g,
            "n": len(present[g]),
            "median": float(_stats.median(present[g])),
            "letter": letters[g],
        }
        for g in order
    ]
    kr = block["kruskal"]
    kruskal_out: dict[str, Any] = {
        "H": kr.get("H"),
        "p": kr.get("p"),
        "df": (kr["k"] - 1) if kr.get("k") else None,
    }
    if kr.get("note"):
        kruskal_out["note"] = kr["note"]
    return {"groups": groups_out, "kruskal": kruskal_out, "dunn": _dunn_matrix(order, dunn)}


def significance_from_comparison(
    comparison: dict[str, Any],
    *,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Reduce a :func:`build_summary_comparison` result to the significance view.

    Per metric and per factor (model, method) it emits either the computed
    significance (KW ``{H,p,df}``, Dunn Holm p-matrix, and per-group CLD letters
    ordered by ascending median) or a ``{"skipped": reason}`` marker.  Raw sample
    lists are dropped -- this view is what the JSON ``significance`` block and the
    CSV group-label columns are built from.
    """
    meta = comparison["metadata"]
    metrics_out: dict[str, Any] = {}
    for key, entry in comparison["metrics"].items():
        spec = _SUMMARY_SPECS_BY_KEY.get(key)
        metric_view: dict[str, Any] = {
            "label": entry.get("label", key),
            "unit": entry.get("unit", ""),
            "token_gated": spec.token_gated if spec else False,
        }
        if entry.get("skipped"):
            for _, block_key in FACTORS:
                metric_view[block_key] = {"skipped": entry["skipped"]}
        else:
            for _, block_key in FACTORS:
                metric_view[block_key] = _significance_for_factor(entry.get(block_key), alpha)
        metrics_out[key] = metric_view

    return {
        "metadata": {
            "n_combos": meta.get("n_combos"),
            "models": meta.get("models", []),
            "methods": meta.get("methods", []),
            "alpha": alpha,
            "metrics": list(comparison["metrics"].keys()),
        },
        "metrics": metrics_out,
    }


def group_label(
    significance: dict[str, Any] | None,
    metric: str,
    factor_block_key: str,
    name: str,
) -> str:
    """Return the CLD letter for group *name* under *metric*+factor, else ``""``.

    *factor_block_key* is ``"by_model"`` or ``"by_method"``.  Yields ``""`` when
    the significance block is absent, the metric/factor was skipped, or *name* has
    no group entry -- exactly the cases the CSV renders as an empty cell.  Lets the
    report writer stay ignorant of how significance was computed.
    """
    if not significance:
        return ""
    metric_view = significance.get("metrics", {}).get(metric)
    if not metric_view:
        return ""
    block = metric_view.get(factor_block_key)
    if not block or "groups" not in block:
        return ""
    for g in block["groups"]:
        if g["name"] == name:
            return g["letter"]
    return ""

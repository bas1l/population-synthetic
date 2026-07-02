"""stats_tests.py -- Non-parametric hypothesis tests shared across analysis processes.

Houses the statistical machinery used by the cross-run llm_metrics comparison and
the cross-model performance comparison: the Kruskal-Wallis omnibus test, an
inline Dunn post-hoc with Holm step-down correction, and the descriptive
:func:`summarize` of a sample list.

These carry the ``scipy``/``numpy`` dependency surface and are kept separate from
the stdlib-only numeric primitives in :mod:`population_synthetic.analysis.utils._stats`.
The Kruskal-Wallis H-test and Dunn post-hoc are chosen over parametric ANOVA
because per-group sample sizes are small and the metrics are not expected to be
normally distributed; Dunn's test is implemented here (rather than via
``scikit-posthocs``) to avoid adding a dependency.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from population_synthetic.analysis.utils import _stats


def _nonempty_groups(groups: dict[str, list[float]]) -> dict[str, list[float]]:
    return {g: v for g, v in groups.items() if len(v) >= 1}


def kruskal_test(groups: dict[str, list[float]]) -> dict[str, Any]:
    """Kruskal-Wallis H-test across groups.

    Returns ``{"H","p","k","n"}`` on success, or ``{"H":None,"p":None,"note":...}``
    when the test cannot be computed (fewer than 2 non-empty groups, or all values
    identical).
    """
    g = _nonempty_groups(groups)
    if len(g) < 2:
        return {"H": None, "p": None, "k": len(g), "n": sum(len(v) for v in g.values()),
                "note": "need >=2 non-empty groups"}
    try:
        h, p = stats.kruskal(*g.values())
    except ValueError as exc:
        return {"H": None, "p": None, "k": len(g),
                "n": sum(len(v) for v in g.values()), "note": str(exc)}
    return {"H": float(h), "p": float(p), "k": len(g), "n": sum(len(v) for v in g.values())}


def _holm(pvals: list[float]) -> list[float]:
    """Holm step-down adjustment of a list of p-values (order preserved)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])
        adj[idx] = min(1.0, running)
    return adj


def dunn_posthoc(groups: dict[str, list[float]]) -> list[dict[str, Any]]:
    """Dunn's post-hoc test (rank-based, tie-corrected) with Holm adjustment.

    Returns a list of ``{"a","b","z","p_raw","p_holm"}`` for every group pair.
    Empty when fewer than 2 non-empty groups.
    """
    g = _nonempty_groups(groups)
    labels = list(g.keys())
    if len(labels) < 2:
        return []

    data: list[float] = []
    grp_of: list[str] = []
    for label in labels:
        for v in g[label]:
            data.append(v)
            grp_of.append(label)

    n = len(data)
    if n < 2:
        return []

    arr = np.asarray(data, dtype=float)
    ranks = stats.rankdata(arr)
    grp_arr = np.asarray(grp_of)

    _, counts = np.unique(arr, return_counts=True)
    tie_sum = float(np.sum(counts.astype(float) ** 3 - counts))
    sigma2 = (n * (n + 1) / 12.0) - tie_sum / (12.0 * (n - 1)) if n > 1 else 0.0

    mean_rank: dict[str, float] = {}
    size: dict[str, int] = {}
    for label in labels:
        mask = grp_arr == label
        mean_rank[label] = float(np.mean(ranks[mask]))
        size[label] = int(np.sum(mask))

    pairs: list[tuple[str, str]] = []
    zs: list[float] = []
    raw: list[float] = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            denom = math.sqrt(sigma2 * (1.0 / size[a] + 1.0 / size[b])) if sigma2 > 0 else 0.0
            if denom == 0:
                z, p = 0.0, 1.0
            else:
                z = (mean_rank[a] - mean_rank[b]) / denom
                p = 2.0 * float(stats.norm.sf(abs(z)))
            pairs.append((a, b))
            zs.append(z)
            raw.append(p)

    p_holm = _holm(raw)
    return [
        {"a": a, "b": b, "z": z, "p_raw": pr, "p_holm": ph}
        for (a, b), z, pr, ph in zip(pairs, zs, raw, p_holm)
    ]


def summarize(samples: list[float]) -> dict[str, Any]:
    """Descriptive summary of a sample list (None fields when empty)."""
    if not samples:
        return {"n": 0, "median": None, "mean": None, "std": None,
                "q1": None, "q3": None, "min": None, "max": None}
    arr = np.asarray(samples, dtype=float)
    # Percentiles use the project-wide nearest-rank convention (analysis.utils._stats),
    # so a metric's q1/q3 here match its per-run chart.  Mean/std stay on numpy.
    return {
        "n": int(arr.size),
        "median": float(_stats.median(samples)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "q1": float(_stats.percentile(samples, 25)),
        "q3": float(_stats.percentile(samples, 75)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }

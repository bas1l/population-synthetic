"""stats_tests.py -- Non-parametric hypothesis tests shared across analysis processes.

Houses the statistical machinery used by the generation-metadata cross-factor
comparison and the cross-model performance comparison: the Kruskal-Wallis omnibus test, an
inline Dunn post-hoc with Holm step-down correction, and the descriptive
:func:`summarize` of a sample list.

These carry the ``scipy``/``numpy`` dependency surface and are kept separate from
the stdlib-only numeric primitives in :mod:`population_synthetic.analysis.utils._stats`.
The Kruskal-Wallis H-test and Dunn post-hoc are chosen over parametric ANOVA
because per-group sample sizes are small and the metrics are not expected to be
normally distributed; Dunn's test is implemented here (rather than via
``scikit-posthocs``) to avoid adding a dependency.

A second family of primitives -- Friedman (+Iman-Davenport, Kendall's W), Page's L
trend test, Nemenyi post-hoc, Benjamini-Hochberg FDR, Cliff's delta, and a
logit-linked mixed-model interaction fit -- supports the *method/model
significance* process, which compares generation methods across categories in the
repeated-measures / "classifiers over multiple datasets" shape (Demšar 2006).
Those that need ``scikit-posthocs`` or ``statsmodels`` import them lazily inside
the function and raise a clear ``install with: pip install -e .[analysis]`` error
when the optional extra is absent, matching the C2ST multivariate-fidelity pattern.
The same family carries :func:`complete_block_matrix` (the complete-case layout
every blocked test needs) and :func:`conover_friedman_pairwise`, a less conservative
post-hoc than Nemenyi for the Friedman design, Holm-corrected here.

A last family gives two independent samples a location effect size with an interval:
:func:`epsilon_squared` for a Kruskal-Wallis result, :func:`mann_whitney_test`,
:func:`cliffs_delta_from_histograms` (Cliff's delta through the Mann-Whitney identity,
vectorised over histograms) and :func:`bootstrap_cliffs_delta_ci`, plus
:func:`shapiro_wilk_test` as the normality check reported beside a parametric result.

Every re-implemented statistic (Page's L, Kendall's W, Cliff's delta) is validated
against a hand-computed value in ``tests/test_stats_tests_significance.py``; the
library-backed ones are pinned to the library's own output on fixtures.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy import stats

from population_synthetic.analysis.utils import _stats

# --------------------------------------------------------------------------- #
# Optional-dependency guards (the ``[analysis]`` extra: scikit-posthocs +      #
# statsmodels).  Imported lazily inside the functions that need them so the    #
# core install stays lean, mirroring the C2ST sklearn guard in                 #
# ``analysis/fidelity/multivariate.py``.                                       #
# --------------------------------------------------------------------------- #
_ANALYSIS_EXTRA_HINT = (
    "This statistic requires the optional analysis dependencies. "
    "Install with: pip install -e .[analysis]"
)


def _import_scikit_posthocs() -> Any:
    try:
        import scikit_posthocs as sp
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(f"scikit-posthocs is not installed. {_ANALYSIS_EXTRA_HINT}") from exc
    return sp


def _import_statsmodels() -> tuple[Any, Any]:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.multitest import multipletests
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(f"statsmodels is not installed. {_ANALYSIS_EXTRA_HINT}") from exc
    return sm, multipletests


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


# =========================================================================== #
# Repeated-measures / method-comparison primitives                            #
# (Friedman, Page's L, Nemenyi, Benjamini-Hochberg, Cliff's delta, mixed      #
#  logit interaction).  Blocks-x-treatments layout throughout: each *block*   #
# (row) is a matched observation set (e.g. one demographic category), each    #
# *treatment* (column) is one condition (e.g. one model, or one ordered       #
# method) measured once per block.                                            #
# =========================================================================== #


def _as_block_matrix(blocks: Sequence[Sequence[float]]) -> np.ndarray:
    """Coerce a blocks x treatments layout to a 2-D float array, failing loudly.

    Each row is a block; each column is a treatment, in a consistent column
    order across blocks.  Raises ``ValueError`` on ragged input or NaNs (a NaN
    is an *absent* cell -- the caller must drop or handle it before testing,
    never let it flow into a rank test silently).
    """
    arr = np.asarray(blocks, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"blocks must be a 2-D blocks x treatments layout, got shape {arr.shape}")
    if np.isnan(arr).any():
        raise ValueError("blocks contains NaN (absent cell); drop/handle absent cells before testing")
    return arr


def friedman_test(blocks: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Friedman test across treatments with matched blocks.

    Input: ``blocks`` is a ``blocks x treatments`` layout -- a sequence of blocks,
    each block a sequence of the ``k`` treatment values in a **consistent column
    order** (row = block, column = treatment).  Wraps
    :func:`scipy.stats.friedmanchisquare` and adds:

    - **Iman-Davenport F-correction** ``F = (N-1)*chi2 / (N*(k-1) - chi2)`` with
      ``df1 = k-1``, ``df2 = (k-1)*(N-1)`` -- less conservative than the chi2
      approximation for small ``N`` (García & Herrera 2008).
    - **Kendall's W** ``= chi2 / (N*(k-1))`` in ``[0, 1]`` as the effect size
      (coefficient of concordance).

    Returns ``{"chi2","p","k","n","kendalls_w","iman_davenport_f","df1","df2","p_f"}``
    on success.  Degenerate inputs (``<2`` treatments, ``<2`` blocks, or every
    block identical so there is zero rank variation) return the same keys with
    ``chi2``/``p``/``kendalls_w`` ``None`` and a ``"note"``.  When ``W == 1``
    (perfect concordance) the Iman-Davenport denominator is zero, so ``p_f`` is
    ``0.0`` and ``iman_davenport_f`` is ``inf`` -- reported explicitly, not NaN.
    """
    arr = _as_block_matrix(blocks)
    n, k = arr.shape
    if k < 2 or n < 2:
        return {"chi2": None, "p": None, "k": k, "n": n, "kendalls_w": None,
                "iman_davenport_f": None, "df1": None, "df2": None, "p_f": None,
                "note": "need >=2 treatments and >=2 blocks"}
    try:
        chi2, p = stats.friedmanchisquare(*arr.T)
    except ValueError as exc:
        return {"chi2": None, "p": None, "k": k, "n": n, "kendalls_w": None,
                "iman_davenport_f": None, "df1": None, "df2": None, "p_f": None,
                "note": str(exc)}
    chi2 = float(chi2)
    kendalls_w = chi2 / (n * (k - 1))
    df1 = k - 1
    df2 = (k - 1) * (n - 1)
    denom = n * (k - 1) - chi2
    if denom <= 0:
        # Perfect (or numerically perfect) concordance: F -> +inf, p_f -> 0.
        f_stat = math.inf
        p_f = 0.0
    else:
        f_stat = (n - 1) * chi2 / denom
        p_f = float(stats.f.sf(f_stat, df1, df2))
    return {"chi2": chi2, "p": float(p), "k": k, "n": n,
            "kendalls_w": float(kendalls_w), "iman_davenport_f": float(f_stat),
            "df1": df1, "df2": df2, "p_f": p_f}


def page_trend_test(blocks: Sequence[Sequence[float]], order: Sequence[int]) -> dict[str, Any]:
    """Page's L test for an *ordered* alternative across treatments (in-house).

    Page's L is not shipped by scipy / statsmodels / scikit-posthocs, so it is
    implemented here and validated against a hand-computed value in the tests.

    Input: ``blocks`` is a ``blocks x treatments`` layout (row = block, column =
    treatment, consistent column order).  ``order`` is the a-priori ordering of
    the treatments given as **column indices from predicted-smallest to
    predicted-largest** value (a permutation of ``range(k)``); e.g. ``[2, 0, 1]``
    means column 2 is predicted lowest, column 1 predicted highest.  Within each
    block values are ranked ``1..k`` (1 = smallest; ties get average ranks).

    ``L = sum_j predicted_position_j * R_j`` where ``R_j`` is the rank sum of the
    treatment placed at predicted position ``j`` (1-based).  The normal
    approximation uses ``mu = N*k*(k+1)^2 / 4`` and
    ``var = N*k^2*(k+1)*(k^2-1) / 144``, ``z = (L - mu)/sqrt(var)``, one-sided
    (large ``L`` => trend in the specified order), ``p = sf(z)``.

    **Caveat (documented deliberately):** Page's L is *not a pure trend test* --
    it accumulates any deviation consistent with the ordering and will fire on a
    single step-change as readily as on a smooth monotone ramp; pair it with an
    explicit linear/quadratic contrast before claiming monotonicity.

    Returns ``{"L","z","p","k","n","order"}`` on success; degenerate inputs
    (``<2`` treatments, ``<2`` blocks) return those keys with ``L``/``z``/``p``
    ``None`` and a ``"note"``.
    """
    arr = _as_block_matrix(blocks)
    n, k = arr.shape
    order = list(order)
    if k < 2 or n < 2:
        return {"L": None, "z": None, "p": None, "k": k, "n": n, "order": order,
                "note": "need >=2 treatments and >=2 blocks"}
    if sorted(order) != list(range(k)):
        raise ValueError(f"order must be a permutation of range({k}) column indices, got {order}")

    # Per-block ranks (1 = smallest), average ties -- matches scipy.stats.rankdata.
    ranks = np.vstack([stats.rankdata(row) for row in arr])  # shape (n, k)
    rank_sums = ranks.sum(axis=0)  # R_j per column
    # predicted position (1-based) of each column: position p+1 for order[p].
    predicted_position = np.empty(k, dtype=float)
    for pos, col in enumerate(order):
        predicted_position[col] = pos + 1
    L = float(np.dot(predicted_position, rank_sums))

    mu = n * k * (k + 1) ** 2 / 4.0
    var = n * k**2 * (k + 1) * (k**2 - 1) / 144.0
    if var <= 0:
        return {"L": L, "z": None, "p": None, "k": k, "n": n, "order": order,
                "note": "zero variance under H0 (k too small)"}
    z = (L - mu) / math.sqrt(var)
    p = float(stats.norm.sf(z))
    return {"L": L, "z": float(z), "p": p, "k": k, "n": n, "order": order}


def nemenyi_posthoc(matrix: Sequence[Sequence[float]], alpha: float = 0.05) -> dict[str, Any]:
    """Nemenyi post-hoc after Friedman, plus the critical-difference (CD) value.

    Input: ``matrix`` is a ``blocks x treatments`` layout (row = block, column =
    treatment).  Delegates the pairwise p-values to
    :func:`scikit_posthocs.posthoc_nemenyi_friedman` (lazily imported; raises a
    clear install error without the ``[analysis]`` extra).

    Also returns the critical difference for a CD diagram,
    ``CD = q_alpha * sqrt(k*(k+1) / (6*N))`` where ``q_alpha`` is the Studentized
    range critical value divided by ``sqrt(2)`` (Demšar 2006, eq. for Nemenyi):
    ``q_alpha = studentized_range.ppf(1-alpha, k, inf) / sqrt(2)``.

    Returns ``{"p_matrix","labels","cd","q_alpha","k","n","alpha"}`` where
    ``p_matrix`` is a ``k x k`` list-of-lists in column order and ``labels`` are
    the column indices.  Degenerate inputs (``<2`` treatments, ``<2`` blocks)
    return those keys with ``p_matrix``/``cd`` ``None`` and a ``"note"``.
    """
    arr = _as_block_matrix(matrix)
    n, k = arr.shape
    labels = list(range(k))
    if k < 2 or n < 2:
        return {"p_matrix": None, "labels": labels, "cd": None, "q_alpha": None,
                "k": k, "n": n, "alpha": alpha, "note": "need >=2 treatments and >=2 blocks"}
    sp = _import_scikit_posthocs()
    p_df = sp.posthoc_nemenyi_friedman(arr)
    p_matrix = p_df.to_numpy(dtype=float).tolist()
    q_alpha = float(stats.studentized_range.ppf(1.0 - alpha, k, np.inf) / math.sqrt(2.0))
    cd = q_alpha * math.sqrt(k * (k + 1) / (6.0 * n))
    return {"p_matrix": p_matrix, "labels": labels, "cd": float(cd),
            "q_alpha": q_alpha, "k": k, "n": n, "alpha": alpha}


def nemenyi_pairwise(
    matrix: Sequence[Sequence[float]],
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Labeled Nemenyi pairwise p-matrix over treatments (columns).

    A thin, label-aware wrapper over :func:`nemenyi_posthoc` for the
    method-comparison figure: given a ``blocks x treatments`` layout (here
    ``models x methods``) it returns the symmetric ``k x k`` Nemenyi p-matrix with
    **string treatment labels** attached, so a caller can read off the p-value for
    a named method pair without tracking column indices. The CD/critical-difference
    machinery of :func:`nemenyi_posthoc` is intentionally omitted -- this form is
    for annotating pairwise significance, not for a CD diagram.

    Input: ``matrix`` is ``blocks x treatments`` (row = block, column = treatment,
    consistent column order); ``labels`` names the ``k`` columns (defaults to
    ``["0", "1", ...]``). Reuses the same
    :func:`scikit_posthocs.posthoc_nemenyi_friedman` call (lazily imported; raises
    a clear install error without the ``[analysis]`` extra).

    Returns ``{"labels","p_matrix","k","n"}`` where ``p_matrix`` is a ``k x k``
    list-of-lists in ``labels`` order (symmetric, diagonal ``1.0``). Degenerate
    inputs (``<2`` treatments, ``<2`` blocks) return those keys with ``p_matrix``
    ``None`` and a ``"note"``. Raises ``ValueError`` if ``labels`` length does not
    match the treatment count.
    """
    arr = _as_block_matrix(matrix)
    n, k = arr.shape
    if labels is None:
        resolved = [str(i) for i in range(k)]
    else:
        resolved = [str(x) for x in labels]
        if len(resolved) != k:
            raise ValueError(
                f"labels length {len(resolved)} does not match treatment count {k}"
            )
    if k < 2 or n < 2:
        return {"labels": resolved, "p_matrix": None, "k": k, "n": n,
                "note": "need >=2 treatments and >=2 blocks"}
    sp = _import_scikit_posthocs()
    p_df = sp.posthoc_nemenyi_friedman(arr)
    p_matrix = p_df.to_numpy(dtype=float).tolist()
    return {"labels": resolved, "p_matrix": p_matrix, "k": k, "n": n}


def complete_block_matrix(
    cells: Mapping[str, Mapping[str, float | None]],
    blocks: Sequence[str],
    treatments: Sequence[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    """Build the complete-case ``blocks x treatments`` matrix for a blocked rank test.

    *cells* maps ``block -> {treatment -> value | None}``. A block is *complete* iff it
    has a non-``None`` value under **every** treatment in *treatments* (Friedman and its
    post-hocs require complete blocks); an incomplete block is dropped and returned
    separately, never imputed. A treatment key absent from a block's mapping counts as
    ``None`` -- an absent cell (e.g. a withdrawn combination) is the same fact as an
    explicit ``None``. Every name in *blocks* must be a key of *cells*.

    Returns ``(matrix, complete_blocks, dropped_blocks)`` with *matrix* shaped
    ``len(complete_blocks) x len(treatments)``, rows in *blocks* order and columns in
    *treatments* order.
    """
    complete = [b for b in blocks if all(cells[b].get(t) is not None for t in treatments)]
    dropped = [b for b in blocks if b not in complete]
    matrix = np.array(
        [[float(cells[b][t]) for t in treatments] for b in complete],
        dtype=float,
    ) if complete else np.empty((0, len(treatments)))
    return matrix, complete, dropped


def conover_friedman_pairwise(
    matrix: Sequence[Sequence[float]],
    *,
    labels: Sequence[str],
) -> dict[str, Any]:
    """Conover's post-hoc for the Friedman design, Holm-corrected across every pair.

    Input matches :func:`friedman_test` (row = block, column = treatment); *labels*
    names the columns and must match the column count. The raw two-sided p-values come
    from :func:`scikit_posthocs.posthoc_conover_friedman` (lazily imported; raises a
    clear install error without the ``[analysis]`` extra), which uses the
    t-distribution on the rank-sum differences (Conover 1999) and is therefore less
    conservative than Nemenyi with few blocks.

    The Holm step-down correction is this module's own :func:`holm_adjust`, applied to
    the ``k(k-1)/2`` unordered pairs -- the same implementation every other Holm family
    in the codebase uses, not the library's.

    Returns ``{"test","k","n","correction","pairs"}`` where ``pairs`` maps ``"a|b"``
    (``a`` listed before ``b`` in *labels*) to ``{"p_raw","p_holm"}``. Degenerate input
    (``<2`` treatments or blocks) returns an empty ``pairs`` map plus a ``"note"``. A
    pair whose raw p is not finite (every block perfectly concordant, so the statistic's
    residual variance is zero) gets ``p_raw``/``p_holm`` ``None`` with its own ``note``
    and is left out of the Holm family.

    Raises ``ValueError`` when *labels* does not match the treatment count.
    """
    arr = _as_block_matrix(matrix)
    n, k = arr.shape
    if len(labels) != k:
        raise ValueError(f"labels has {len(labels)} entries but the matrix has {k} columns")
    out: dict[str, Any] = {"test": "conover_friedman", "k": k, "n": n, "correction": "holm", "pairs": {}}
    if k < 2 or n < 2:
        out["note"] = f"need >=2 treatments and >=2 blocks, got {k} treatments / {n} blocks"
        return out
    sp = _import_scikit_posthocs()
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = sp.posthoc_conover_friedman(arr).to_numpy(dtype=float)
    records: dict[str, dict[str, Any]] = {}
    keys: list[str] = []
    raw_ps: list[float] = []
    for i in range(k):
        for j in range(i + 1, k):
            key = f"{labels[i]}|{labels[j]}"
            p = float(raw[i, j])
            if math.isfinite(p):
                records[key] = {"p_raw": p, "p_holm": None}
                keys.append(key)
                raw_ps.append(p)
            else:
                records[key] = {"p_raw": None, "p_holm": None,
                                "note": "Conover statistic undefined (zero residual rank variance)"}
    for key, p_adj in zip(keys, _holm(raw_ps)):
        records[key]["p_holm"] = p_adj
    out["pairs"] = records
    return out


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR adjustment of a list of p-values (order preserved).

    Delegates to :func:`statsmodels.stats.multitest.multipletests` with
    ``method="fdr_bh"`` (lazily imported; raises a clear install error without the
    ``[analysis]`` extra).  Mirrors :func:`_holm`: takes raw p-values, returns the
    adjusted p-values in the **same input order**.  An empty list returns ``[]``.
    """
    if not pvals:
        return []
    _, multipletests = _import_statsmodels()
    _, adjusted, _, _ = multipletests(pvals, method="fdr_bh")
    return [float(x) for x in adjusted]


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """Cliff's delta ordinal effect size (in-house) with a magnitude label.

    ``delta = P(X > Y) - P(X < Y)`` over all pairs ``(x in a, y in b)``, in
    ``[-1, 1]``.  Positive => values in ``a`` tend to exceed ``b``.  The magnitude
    label uses Romano et al.'s thresholds on ``|delta|``: negligible ``< 0.147``,
    small ``< 0.33``, medium ``< 0.474``, large ``>= 0.474``.

    Returns ``{"delta","magnitude","n_a","n_b"}``.  Raises ``ValueError`` if
    either sample is empty (a delta over an empty set is undefined -- fail loud).
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.size == 0 or y.size == 0:
        raise ValueError("cliffs_delta needs both samples non-empty")
    diff = np.sign(x[:, None] - y[None, :])
    delta = float(diff.sum() / (x.size * y.size))
    mag = abs(delta)
    if mag < 0.147:
        label = "negligible"
    elif mag < 0.33:
        label = "small"
    elif mag < 0.474:
        label = "medium"
    else:
        label = "large"
    return {"delta": delta, "magnitude": label, "n_a": int(x.size), "n_b": int(y.size)}


def mixed_logit_interaction(frame: Any) -> dict[str, Any]:
    """Fit ``logit(TV) ~ C(model) * method_rank`` with a random intercept by category.

    Input: ``frame`` is a :class:`pandas.DataFrame` with columns ``tv`` (Total
    Variation in ``[0, 1]``), ``model`` (categorical), ``method_rank`` (ordinal
    numeric, e.g. 1..5), and ``category`` (grouping / random-effect factor).  The
    category factor supplies the replication that makes the model x method
    interaction estimable despite one observation per (model, method, category)
    cell.

    TV is squeezed off the ``{0, 1}`` boundary before the logit link via the
    Smithson-Verkuilen (2006) transform ``y' = (y*(m-1) + 0.5) / m`` (``m`` = row
    count) so exact-0 / exact-1 TV do not produce infinite logits.  Fits with
    :class:`statsmodels.regression.mixed_linear_model.MixedLM` (lazily imported;
    raises a clear install error without the ``[analysis]`` extra).

    Returns:
    - ``"interaction"``: ``{"stat","p","df"}`` -- a joint Wald test on all
      ``model:method_rank`` interaction terms.
    - ``"eta_sq"``: an eta^2-style variance-share decomposition
      ``{"model","method","category","residual"}`` normalised to sum to 1.  Model
      share folds in the interaction columns (per-model method slopes); it is an
      approximate variance-share of the fitted linear predictor's factor
      contributions, **not** an exact orthogonal partition -- documented as such.
    - ``"converged"``: bool.  **On non-convergence the interaction ``p`` is
      ``None``** (a non-converged fit's p-value is not trustworthy) with a
      ``"note"``, rather than emitting a bogus value.

    Raises ``ValueError`` on missing columns or fewer than 2 models / 2 categories.
    """
    import pandas as pd  # core dependency
    from scipy.special import logit

    sm, _ = _import_statsmodels()

    if not isinstance(frame, pd.DataFrame):
        raise ValueError("mixed_logit_interaction expects a pandas DataFrame")
    required = {"tv", "model", "method_rank", "category"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"frame missing required columns: {sorted(missing)}")
    df = frame[["tv", "model", "method_rank", "category"]].dropna().copy()
    if df["model"].nunique() < 2 or df["category"].nunique() < 2:
        raise ValueError("need >=2 models and >=2 categories for the interaction fit")

    m = len(df)
    y = df["tv"].to_numpy(dtype=float)
    y_squeezed = (y * (m - 1) + 0.5) / m  # Smithson-Verkuilen boundary squeeze
    df["_y"] = logit(y_squeezed)

    md = sm.MixedLM.from_formula("_y ~ C(model) * method_rank", groups="category", data=df)
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = md.fit()
    except (ValueError, np.linalg.LinAlgError) as exc:
        return {"interaction": {"stat": None, "p": None, "df": None},
                "eta_sq": None, "converged": False, "note": f"fit failed: {exc}"}

    converged = bool(getattr(res, "converged", False))

    interaction_terms = [name for name in res.fe_params.index if ":" in name]
    if not interaction_terms:
        wald = {"stat": None, "p": None, "df": None}
    elif not converged:
        wald = {"stat": None, "p": None, "df": len(interaction_terms)}
    else:
        w = res.wald_test(interaction_terms, scalar=True)
        wald = {"stat": float(w.statistic), "p": float(w.pvalue), "df": int(w.df_denom)}

    # eta^2-style variance-share of the fixed-effect factor contributions.
    exog = np.asarray(res.model.exog, dtype=float)
    names = list(res.model.exog_names)
    beta = np.asarray(res.fe_params, dtype=float)
    contrib_model = np.zeros(m)
    contrib_method = np.zeros(m)
    for j, name in enumerate(names):
        if name == "Intercept":
            continue
        col = exog[:, j] * beta[j]
        if ":" in name or name.startswith("C(model)"):
            contrib_model += col  # model main effects + per-model method slopes
        elif "method_rank" in name:
            contrib_method += col
    var_model = float(np.var(contrib_model))
    var_method = float(np.var(contrib_method))
    var_category = float(res.cov_re.iloc[0, 0])
    var_residual = float(res.scale)
    total = var_model + var_method + var_category + var_residual
    if total <= 0:
        eta_sq = None
    else:
        eta_sq = {"model": var_model / total, "method": var_method / total,
                  "category": var_category / total, "residual": var_residual / total}

    out: dict[str, Any] = {"interaction": wald, "eta_sq": eta_sq, "converged": converged}
    if not converged:
        out["note"] = "MixedLM did not converge; interaction p suppressed"
    return out


# =========================================================================== #
# Reliability / dispersion / resampling primitives                            #
# (bootstrap CI, ICC(1,1), Krippendorff's alpha, Levene/Brown-Forsythe).      #
# Added for the persona-realism judge process: N judge rounds per persona are  #
# repeated measurements whose agreement (ICC / alpha) is the judge's           #
# self-consistency, and per-combination rates/dispersions need interval        #
# estimates and a variance-equality test vs the real reference.                #
#                                                                              #
# Degenerate-input policy (matches the rest of this module): a case that       #
# cannot be computed (empty / singleton / zero-variance / single round)        #
# returns a dict with the metric field ``None`` and an explicit ``"note"``     #
# skipped-reason -- never a bare ``NaN`` that flows downstream unnoticed.       #
# =========================================================================== #


def bootstrap_ci(
    values: Sequence[float],
    statistic: Any = None,
    *,
    iterations: int = 2000,
    ci_level: float = 0.95,
    seed: int | None = None,
) -> dict[str, Any]:
    """Percentile bootstrap confidence interval for a sample statistic.

    Resamples *values* with replacement ``iterations`` times, applies
    *statistic* (default :func:`numpy.mean` -- so a 0/1 sample gives the rate) to
    each resample, and returns the ``ci_level`` percentile interval of the
    resampled statistics. The sampling unit is one element of *values* (for the
    impossibility rate: one persona), so pass per-unit values, not pre-aggregated
    scalars.

    Randomness uses a local :func:`numpy.random.default_rng` seeded with *seed*
    (never the legacy global ``np.random.seed``), so the interval is byte-stable
    for a given ``(values, seed, iterations)`` and the seed can be recorded in run
    metadata. ``ci_level`` is the central mass (e.g. ``0.95`` -> the 2.5th/97.5th
    percentiles).

    Returns ``{"point","lo","hi","ci_level","iterations","n","method"}`` where
    ``point`` is the statistic on the observed sample and ``lo``/``hi`` are the
    percentile bounds. Degenerate input (empty sample) returns those keys with
    ``point``/``lo``/``hi`` ``None`` and a ``"note"``. A single-element or
    zero-variance sample is *not* degenerate here: the bootstrap is exact
    (``lo == hi == point``), which is the correct, honest interval.

    Raises
    ------
    ValueError
        If ``iterations < 1`` or ``ci_level`` is not in the open interval
        ``(0, 1)`` -- a malformed request, surfaced rather than defaulted.
    """
    if iterations < 1:
        raise ValueError(f"bootstrap iterations must be >= 1, got {iterations}")
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")

    stat_fn = statistic if statistic is not None else np.mean
    arr = np.asarray(values, dtype=float)
    n = int(arr.size)
    base = {"ci_level": ci_level, "iterations": iterations, "n": n, "method": "percentile"}
    if n == 0:
        return {"point": None, "lo": None, "hi": None, **base, "note": "empty sample"}

    point = float(stat_fn(arr))
    rng = np.random.default_rng(seed)
    resampled = np.empty(iterations, dtype=float)
    for i in range(iterations):
        sample = rng.choice(arr, size=n, replace=True)
        resampled[i] = float(stat_fn(sample))

    tail = (1.0 - ci_level) / 2.0
    lo = float(np.quantile(resampled, tail))
    hi = float(np.quantile(resampled, 1.0 - tail))
    return {"point": point, "lo": lo, "hi": hi, **base}


def bootstrap_difference_ci(
    values_a: Sequence[float],
    values_b: Sequence[float],
    *,
    iterations: int = 2000,
    ci_level: float = 0.95,
    seed: int | None = None,
) -> dict[str, Any]:
    """Percentile bootstrap CI for ``mean(a) - mean(b)`` on two independent samples.

    Each group is resampled with replacement at its own size from one seeded local
    :func:`numpy.random.default_rng`, so the interval reflects the uncertainty of both
    groups and is byte-stable for a given ``(a, b, seed, iterations)``. On 0/1 inputs
    this is the CI of a **rate difference**, which is how the realism ranking contrasts
    each synthetic competitor with the real population.

    Returns ``{"point","lo","hi","ci_level","iterations","n_a","n_b","method"}``. Either
    sample empty -> ``point``/``lo``/``hi`` ``None`` with a ``"note"`` (a difference
    against nothing is undefined, not zero).

    Raises
    ------
    ValueError
        If ``iterations < 1`` or ``ci_level`` is not in the open interval ``(0, 1)``.
    """
    if iterations < 1:
        raise ValueError(f"bootstrap iterations must be >= 1, got {iterations}")
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")

    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    base = {
        "ci_level": ci_level, "iterations": iterations,
        "n_a": int(a.size), "n_b": int(b.size), "method": "percentile",
    }
    if a.size == 0 or b.size == 0:
        return {"point": None, "lo": None, "hi": None, **base, "note": "empty sample"}

    point = float(np.mean(a) - np.mean(b))
    rng = np.random.default_rng(seed)
    resampled = np.empty(iterations, dtype=float)
    for i in range(iterations):
        resampled[i] = float(
            np.mean(rng.choice(a, size=a.size, replace=True))
            - np.mean(rng.choice(b, size=b.size, replace=True))
        )
    tail = (1.0 - ci_level) / 2.0
    return {
        "point": point,
        "lo": float(np.quantile(resampled, tail)),
        "hi": float(np.quantile(resampled, 1.0 - tail)),
        **base,
    }


def two_proportion_test(
    successes_a: int, n_a: int, successes_b: int, n_b: int
) -> dict[str, Any]:
    """Two-sided two-proportion z-test with a Cohen's h effect size.

    Tests ``p_a == p_b`` using the pooled-variance normal approximation, and reports
    the **effect** alongside the p-value: ``diff`` (the raw rate difference, on the
    scale readers care about) and ``h`` (Cohen's h, the arcsine-transformed
    standardised effect, which stays interpretable near 0 and 1 where the raw
    difference compresses). A p-value without an effect size cannot distinguish a
    large difference from a large sample.

    Returns ``{"p_a","p_b","diff","h","h_magnitude","z","p","n_a","n_b"}``. Degenerate
    inputs (a non-positive denominator, or a pooled rate of exactly 0 or 1 -- where the
    test statistic has no variance) return ``z``/``p`` ``None`` with a ``"note"``,
    never a ``NaN``.
    """
    if n_a <= 0 or n_b <= 0:
        return {"p_a": None, "p_b": None, "diff": None, "h": None, "h_magnitude": None,
                "z": None, "p": None, "n_a": n_a, "n_b": n_b,
                "note": "a group has no personas; proportion undefined"}

    p_a = successes_a / n_a
    p_b = successes_b / n_b
    diff = p_a - p_b
    # Cohen's h: the arcsine (variance-stabilising) transform, so a 0.01 -> 0.02 shift
    # is not treated as the same effect as 0.50 -> 0.51.
    h = 2.0 * math.asin(math.sqrt(p_a)) - 2.0 * math.asin(math.sqrt(p_b))
    magnitude = "negligible" if abs(h) < 0.2 else "small" if abs(h) < 0.5 else \
        "medium" if abs(h) < 0.8 else "large"

    pooled = (successes_a + successes_b) / (n_a + n_b)
    if pooled in (0.0, 1.0):
        return {"p_a": p_a, "p_b": p_b, "diff": diff, "h": h, "h_magnitude": magnitude,
                "z": None, "p": None, "n_a": n_a, "n_b": n_b,
                "note": "both groups are entirely one outcome; the z statistic has no variance"}

    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b))
    z = diff / se
    return {
        "p_a": p_a, "p_b": p_b, "diff": diff, "h": h, "h_magnitude": magnitude,
        "z": float(z), "p": float(2.0 * stats.norm.sf(abs(z))), "n_a": n_a, "n_b": n_b,
    }


def holm_adjust(pvals: list[float]) -> list[float]:
    """Holm step-down adjustment of a list of p-values (order preserved).

    The public name for the module-internal :func:`_holm`, exposed because a family of
    tests assembled outside this module (e.g. the realism ranking's contrasts against
    the real population) must be corrected with the *same* implementation the Dunn
    post-hoc uses -- two Holm implementations in one codebase is one too many.
    """
    return _holm(pvals)


def fisher_exact_test(successes_a: int, n_a: int, successes_b: int, n_b: int) -> dict[str, Any]:
    """Two-sided Fisher exact test of ``p_a == p_b`` on a 2 x 2 table of counts.

    Exact where :func:`two_proportion_test` is asymptotic, so it stays valid when a
    group has no successes at all. Returns ``{"p_a","p_b","diff","odds_ratio","p",
    "n_a","n_b"}`` (``odds_ratio`` the sample odds ratio, ``inf`` or ``nan`` exactly as
    scipy reports it, which a reader reads beside ``diff``).

    Raises ``ValueError`` on a non-positive denominator or a count outside ``0..n``.
    """
    for k, n, name in ((successes_a, n_a, "a"), (successes_b, n_b, "b")):
        if isinstance(n, bool) or int(n) != n or n <= 0:
            raise ValueError(f"fisher_exact_test: n_{name} must be a positive integer, got {n!r}")
        if isinstance(k, bool) or int(k) != k or not 0 <= k <= n:
            raise ValueError(f"fisher_exact_test: successes_{name} must lie in 0..{n}, got {k!r}")
    result = stats.fisher_exact([[successes_a, n_a - successes_a], [successes_b, n_b - successes_b]])
    return {
        "p_a": successes_a / n_a, "p_b": successes_b / n_b, "diff": successes_a / n_a - successes_b / n_b,
        "odds_ratio": float(result[0]), "p": float(result[1]), "n_a": int(n_a), "n_b": int(n_b),
    }


def clopper_pearson_interval(successes: int, n: int, *, ci_level: float) -> tuple[float, float]:
    """Exact (Clopper-Pearson) central interval of a binomial proportion.

    The beta-quantile form: ``lo = Beta(tail; k, n - k + 1)`` (0 when ``k = 0``) and
    ``hi = Beta(1 - tail; k + 1, n - k)`` (1 when ``k = n``), ``tail = (1 - ci_level) / 2``.

    Raises ``ValueError`` on a non-positive *n*, a count outside ``0..n`` or a
    ``ci_level`` outside ``(0, 1)``.
    """
    if isinstance(n, bool) or int(n) != n or n <= 0:
        raise ValueError(f"clopper_pearson_interval: n must be a positive integer, got {n!r}")
    if isinstance(successes, bool) or int(successes) != successes or not 0 <= successes <= n:
        raise ValueError(f"clopper_pearson_interval: successes must lie in 0..{n}, got {successes!r}")
    if not 0.0 < float(ci_level) < 1.0:
        raise ValueError(f"clopper_pearson_interval: ci_level must lie in (0, 1), got {ci_level!r}")
    tail = (1.0 - float(ci_level)) / 2.0
    lo = 0.0 if successes == 0 else float(stats.beta.ppf(tail, successes, n - successes + 1))
    hi = 1.0 if successes == n else float(stats.beta.ppf(1.0 - tail, successes + 1, n - successes))
    return lo, hi


def icc(ratings: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Intraclass correlation ICC(1,1) -- one-way random-effects, single measure.

    Input: ``ratings`` is a ``subjects x measurements`` layout -- one row per
    subject (persona), each row the ``k`` repeated measurements (judge rounds) in
    any order. The one-way model (Shrout & Fleiss 1979, ICC(1,1)) is the right
    form here because the ``k`` rounds are *interchangeable* repeated calls of the
    same judge, not ``k`` fixed distinct raters: each subject is measured by ``k``
    randomly-drawn rounds and the round index carries no identity across subjects.

    ``ICC(1,1) = (MSB - MSW) / (MSB + (k-1)*MSW)`` with ``MSB`` the between-subject
    mean square (``df = n-1``) and ``MSW`` the within-subject mean square
    (``df = n*(k-1)``). Requires a rectangular matrix (every subject the same
    ``k``); ragged input raises.

    Returns ``{"icc","n","k","msb","msw","model"}`` on success. Degenerate inputs
    return those keys with ``icc`` ``None`` and a ``"note"``: fewer than 2
    subjects, a single measurement (``k < 2`` -> MSW undefined, ``df_w = 0``), or
    zero total variance (all values identical -> ICC undefined, not ``0``).

    Raises
    ------
    ValueError
        On ragged rows (unequal measurement counts) -- an absent cell must be
        resolved by the caller, not silently rectangularized.
    """
    rows = [list(r) for r in ratings]
    n = len(rows)
    if n < 2:
        return {"icc": None, "n": n, "k": 0, "msb": None, "msw": None,
                "model": "ICC(1,1)", "note": "need >=2 subjects"}
    widths = {len(r) for r in rows}
    if len(widths) != 1:
        raise ValueError(f"icc requires a rectangular subjects x measurements matrix, got row widths {sorted(widths)}")
    k = widths.pop()
    if k < 2:
        return {"icc": None, "n": n, "k": k, "msb": None, "msw": None,
                "model": "ICC(1,1)", "note": "need >=2 measurements per subject (ICC undefined for a single round)"}

    arr = np.asarray(rows, dtype=float)
    grand = float(arr.mean())
    subject_means = arr.mean(axis=1)
    ss_between = k * float(np.sum((subject_means - grand) ** 2))
    ss_within = float(np.sum((arr - subject_means[:, None]) ** 2))
    if ss_between == 0.0 and ss_within == 0.0:
        return {"icc": None, "n": n, "k": k, "msb": 0.0, "msw": 0.0,
                "model": "ICC(1,1)", "note": "zero variance (all ratings identical); ICC undefined"}
    msb = ss_between / (n - 1)
    msw = ss_within / (n * (k - 1))
    denom = msb + (k - 1) * msw
    if denom == 0.0:
        return {"icc": None, "n": n, "k": k, "msb": msb, "msw": msw,
                "model": "ICC(1,1)", "note": "zero denominator; ICC undefined"}
    return {"icc": float((msb - msw) / denom), "n": n, "k": k,
            "msb": msb, "msw": msw, "model": "ICC(1,1)"}


def _krippendorff_delta_matrix(values: list[float], marginals: np.ndarray, level: str) -> np.ndarray:
    """Squared difference function ``delta^2(c, k)`` over the ordered value set.

    ``level`` selects the metric: ``nominal`` (0 if equal else 1), ``interval``
    (``(v_c - v_k)^2``), or ``ordinal`` (Krippendorff's rank metric, which folds
    the marginal counts ``marginals`` of the values *between* c and k). Values must
    be numeric for ``interval``/``ordinal``.
    """
    v = len(values)
    delta = np.zeros((v, v), dtype=float)
    if level == "nominal":
        for c in range(v):
            for kk in range(v):
                if c != kk:
                    delta[c, kk] = 1.0
        return delta
    if level == "interval":
        arr = np.asarray(values, dtype=float)
        return (arr[:, None] - arr[None, :]) ** 2
    if level == "ordinal":
        # delta(c,k) = ( sum_{g=c..k} n_g - (n_c + n_k)/2 )^2, values ordered ascending.
        for c in range(v):
            for kk in range(c + 1, v):
                between = float(np.sum(marginals[c:kk + 1]))
                d = between - (marginals[c] + marginals[kk]) / 2.0
                delta[c, kk] = d * d
                delta[kk, c] = delta[c, kk]
        return delta
    raise ValueError(f"unknown krippendorff level {level!r}; expected nominal|interval|ordinal")


def krippendorff_alpha(
    data: Sequence[Sequence[float | None]],
    *,
    level: str = "interval",
) -> dict[str, Any]:
    """Krippendorff's alpha reliability coefficient across repeated ratings.

    Input: ``data`` is a ``units x coders`` layout -- one row per unit (persona),
    each row the ratings assigned by each coder (judge round); ``None`` marks a
    missing rating (a failed round), handled natively. ``level`` is the
    measurement level of the ratings: ``nominal`` (e.g. the boolean ``can_exist``),
    ``interval`` (default; treat the 0-10 ``typicality`` as evenly spaced), or
    ``ordinal`` (Krippendorff's rank metric on ``typicality``).

    ``alpha = 1 - Do/De`` where ``Do`` is the observed disagreement and ``De`` the
    disagreement expected by chance, both built from the coincidence matrix over
    all within-unit rating pairs (each unit contributes its ``m(m-1)`` ordered
    pairs weighted ``1/(m-1)``). ``alpha = 1`` is perfect agreement; ``0`` is
    chance; negative values indicate systematic disagreement.

    Returns ``{"alpha","n_units","n_values","level"}`` on success. Degenerate
    inputs return those keys with ``alpha`` ``None`` and a ``"note"``: fewer than 2
    units with >=2 ratings each, or only a single distinct value used across all
    ratings (zero variance -> alpha undefined, reported as skipped, not ``NaN``).

    Raises
    ------
    ValueError
        If ``level`` is not one of ``nominal``/``interval``/``ordinal``.
    """
    if level not in ("nominal", "interval", "ordinal"):
        raise ValueError(f"unknown krippendorff level {level!r}; expected nominal|interval|ordinal")

    units = [[x for x in row if x is not None] for row in data]
    units = [u for u in units if len(u) >= 2]
    n_units = len(units)
    if n_units < 2:
        return {"alpha": None, "n_units": n_units, "n_values": 0, "level": level,
                "note": "need >=2 units with >=2 ratings each"}

    value_set = sorted({x for u in units for x in u})
    v = len(value_set)
    if v < 2:
        return {"alpha": None, "n_units": n_units, "n_values": v, "level": level,
                "note": "only one distinct value used; alpha undefined (zero variance)"}

    idx = {val: i for i, val in enumerate(value_set)}
    o = np.zeros((v, v), dtype=float)
    for u in units:
        m = len(u)
        w = 1.0 / (m - 1)
        for a in range(m):
            for b in range(m):
                if a != b:
                    o[idx[u[a]], idx[u[b]]] += w
    n_c = o.sum(axis=1)
    n_total = float(o.sum())

    delta = _krippendorff_delta_matrix(value_set, n_c, level)
    do = float(np.sum(o * delta)) / n_total
    de = float(np.sum(np.outer(n_c, n_c) * delta)) / (n_total * (n_total - 1.0))
    if de == 0.0:
        return {"alpha": None, "n_units": n_units, "n_values": v, "level": level,
                "note": "zero expected disagreement; alpha undefined"}
    return {"alpha": float(1.0 - do / de), "n_units": n_units, "n_values": v, "level": level}


def variance_equality_test(
    groups: dict[str, list[float]],
    *,
    center: str = "median",
) -> dict[str, Any]:
    """Levene / Brown-Forsythe test of equal variance (dispersion) across groups.

    Tests the null that every group has the same spread -- the dispersion-side
    complement to a location test, used here to ask whether a combination's
    typicality spread differs from the real (SCB) reference's. Delegates to
    :func:`scipy.stats.levene`; ``center="median"`` is the **Brown-Forsythe**
    variant (robust to non-normal, skewed data -- the safe default), ``center=
    "mean"`` is the original Levene test.

    Input ``groups`` maps a group label to its sample list. Returns
    ``{"statistic","p","k","center","n"}`` on success. Degenerate inputs return
    those keys with ``statistic``/``p`` ``None`` and a ``"note"``: fewer than 2
    groups with >=2 samples each, zero variance in *every* group (all values
    identical), or a non-finite statistic.

    The last case is the subtle one and must not be waved through. When *some* group
    has zero spread but not all of them do, Levene's within-group deviations for that
    group are all exactly zero, the pooled denominator collapses, and ``scipy`` returns
    ``statistic=inf, p=0.0`` -- which reads downstream as an overwhelmingly significant
    difference in spread rather than as an undefined test. It is reported here as
    skipped-with-a-reason, like every other degenerate input.

    Raises
    ------
    ValueError
        If ``center`` is not ``median`` or ``mean``.
    """
    if center not in ("median", "mean"):
        raise ValueError(f"center must be 'median' or 'mean', got {center!r}")

    usable = {g: v for g, v in groups.items() if len(v) >= 2}
    n_total = sum(len(v) for v in usable.values())
    base = {"statistic": None, "p": None, "k": len(usable), "center": center, "n": n_total}
    if len(usable) < 2:
        return {**base, "note": "need >=2 groups with >=2 samples each"}
    if all(float(np.var(v)) == 0.0 for v in usable.values()):
        return {**base, "note": "zero variance in every group; test undefined"}

    with np.errstate(divide="ignore", invalid="ignore"):
        stat, p = stats.levene(*usable.values(), center=center)
    if not math.isfinite(float(stat)):
        zero_spread = [g for g, v in usable.items() if float(np.var(v)) == 0.0]
        return {
            **base,
            "note": (
                "a group has zero spread ("
                + ", ".join(sorted(zero_spread))
                + "), so the Levene denominator collapses and the statistic is undefined "
                "(scipy returns inf/p=0, which is not a significant result)"
            ),
        }
    return {"statistic": float(stat), "p": float(p), "k": len(usable),
            "center": center, "n": n_total}


# A sum of squares at or below this is the zero it represents: floating-point
# subtraction leaves an exactly-additive residual at ~1e-17, not at 0.0. Shared by
# the RM ANOVA and its assumption checks so both call the same grid degenerate.
_ZERO_SS_TOL = 1e-12


def rm_anova_within(blocks: Sequence[Sequence[float]]) -> dict[str, Any]:
    """One-way repeated-measures ANOVA across treatments with matched blocks.

    Input: ``blocks`` is a ``blocks x treatments`` layout -- row = block (here a
    model), column = treatment (here a generation method), in a **consistent
    column order**.  Unlike :func:`friedman_test` this consumes the *values*, so
    the size of a difference counts and not merely its within-block rank.  That
    is the whole reason it exists alongside Friedman: a treatment that wins in
    every block by a wide margin is indistinguishable, to a rank test, from one
    that wins every block by a hair.

    Partitions the total sum of squares into treatment, block and residual, then
    reports ``F = (SS_treat/(k-1)) / (SS_err/((k-1)(n-1)))`` against
    ``F(k-1, (k-1)(n-1))``.  Effect size is partial eta-squared
    ``SS_treat / (SS_treat + SS_err)``.

    **Sphericity is assumed here, not tested here.**  With ``k = 2`` sphericity is
    automatic (there is a single difference score) and the result is then exactly
    the paired t-test, ``F = t**2``.  For ``k > 2`` a violation inflates the
    Type I error; :func:`rm_anova_assumptions` reports Mauchly's test and the
    epsilon-corrected p-values beside this uncorrected one, and the pairwise
    contrasts do not depend on sphericity.

    Returns ``{"test","F","p","df1","df2","k","n","partial_eta_sq"}``.  Degenerate
    inputs (``<2`` treatments, ``<2`` blocks, or zero residual variation) return
    the same keys with ``F``/``p``/``partial_eta_sq`` ``None`` and a ``"note"`` --
    never a NaN that flows downstream unnoticed.
    """
    arr = _as_block_matrix(blocks)
    n, k = arr.shape
    base: dict[str, Any] = {"test": "rm_anova", "F": None, "p": None,
                            "df1": max(k - 1, 0), "df2": max((k - 1) * (n - 1), 0),
                            "k": k, "n": n, "partial_eta_sq": None}
    if k < 2 or n < 2:
        base["note"] = f"need >=2 treatments and >=2 blocks, got {k} treatments / {n} blocks"
        return base

    grand = float(arr.mean())
    ss_treat = float(n * ((arr.mean(axis=0) - grand) ** 2).sum())
    ss_block = float(k * ((arr.mean(axis=1) - grand) ** 2).sum())
    ss_err = float(((arr - grand) ** 2).sum()) - ss_treat - ss_block
    df1, df2 = k - 1, (k - 1) * (n - 1)
    # Floating-point subtraction can drive an exactly-additive residual slightly
    # negative; treat that as the zero it is rather than propagating a nonsense F.
    if ss_err <= _ZERO_SS_TOL:
        if ss_treat <= _ZERO_SS_TOL:
            # No treatment signal and no residual: every cell is the same value.
            base["note"] = "no treatment or residual variation; F is undefined"
            return base
        # A perfectly additive grid -- every block separated by a constant, with
        # nothing left over. The ratio diverges rather than being unknown, so it
        # is reported as such, matching friedman_test's perfect-concordance case
        # (inf / 0.0 stated explicitly, never a NaN that flows on unnoticed).
        base["F"] = math.inf
        base["p"] = 0.0
        base["partial_eta_sq"] = 1.0
        base["note"] = "zero residual variation; F diverges (perfectly additive blocks)"
        return base

    f_stat = (ss_treat / df1) / (ss_err / df2)
    base["F"] = f_stat
    base["p"] = float(stats.f.sf(f_stat, df1, df2))
    base["partial_eta_sq"] = ss_treat / (ss_treat + ss_err) if (ss_treat + ss_err) > 0 else None
    return base


def paired_t_pairwise(
    blocks: Sequence[Sequence[float]],
    *,
    labels: Sequence[str],
    confidence_level: float,
) -> dict[str, Any]:
    """All pairwise paired t-tests across treatments, Holm-corrected.

    Input matches :func:`rm_anova_within` (row = block, column = treatment);
    *labels* names the columns and must match the column count.

    For every unordered pair this reports the **mean paired difference** (second
    minus first, so a positive value means the later-listed treatment scored
    higher), Cohen's ``dz`` on the differences, the raw two-sided ``scipy``
    ``ttest_rel`` p, the Holm-adjusted p, the number of blocks in which the
    second treatment won, and an assumption-free two-sided **sign-test** p on
    that count.

    The sign test is carried deliberately, not as decoration: the t-test assumes
    the differences are normally distributed, which ``n`` in the low tens cannot
    establish.  A conclusion that both agree on does not rest on that assumption.

    **Holm is applied across every pair**, not across whichever subset a figure
    later chooses to draw.  Correcting over the drawn subset would make the
    reported p depend on a rendering decision, and would invite the objection
    that the family was narrowed after seeing the results.

    Each pair also carries the **confidence interval of its mean difference**:
    ``mean_diff +/- t_{(1+L)/2, n-1} * sd_diff / sqrt(n)``, where *L* is
    *confidence_level* (required, no default -- the caller reads it from config) and
    ``sd_diff`` the ddof-1 standard deviation of the paired differences.  It rests on
    the same normality assumption as the t-test beside it.

    Returns ``{"test","n","k","pairs"}`` where ``pairs`` maps ``"a|b"`` to
    ``{"mean_diff","sd_diff","ci_low","ci_high","dz","p_raw","p_holm","wins",
    "n_blocks","p_sign"}``, every difference signed second minus first.
    Degenerate input (``<2`` treatments/blocks) returns an empty ``pairs`` map
    plus a ``"note"``.  A pair whose differences are all identical yields
    ``sd_diff == 0.0`` and ``dz``/``p_raw``/``p_holm``/``ci_low``/``ci_high``
    ``None`` with its own per-pair ``note`` rather than a NaN or a zero-width
    interval; it is left out of the Holm family.

    Raises ``ValueError`` when *confidence_level* is not strictly between 0 and 1.
    """
    if isinstance(confidence_level, bool) or not 0.0 < float(confidence_level) < 1.0:
        raise ValueError(
            f"confidence_level must lie strictly between 0 and 1, got {confidence_level!r}"
        )
    arr = _as_block_matrix(blocks)
    n, k = arr.shape
    if len(labels) != k:
        raise ValueError(f"labels has {len(labels)} entries but the matrix has {k} columns")
    out: dict[str, Any] = {"test": "paired_t", "n": n, "k": k, "pairs": {}}
    if k < 2 or n < 2:
        out["note"] = f"need >=2 treatments and >=2 blocks, got {k} treatments / {n} blocks"
        return out

    keys: list[str] = []
    raw_ps: list[float] = []
    records: dict[str, dict[str, Any]] = {}
    t_critical = stats.t.ppf((1.0 + float(confidence_level)) / 2.0, n - 1)
    for i in range(k):
        for j in range(i + 1, k):
            diff = arr[:, j] - arr[:, i]
            key = f"{labels[i]}|{labels[j]}"
            wins = int((diff > 0).sum())
            rec: dict[str, Any] = {
                "mean_diff": float(diff.mean()),
                "sd_diff": None,
                "ci_low": None,
                "ci_high": None,
                "wins": wins,
                "n_blocks": n,
                "p_sign": _two_sided_sign_p(wins, n),
                "dz": None,
                "p_raw": None,
                "p_holm": None,
            }
            sd = float(diff.std(ddof=1)) if n > 1 else 0.0
            rec["sd_diff"] = sd
            if sd <= 0:
                rec["note"] = "all paired differences identical; t is undefined"
            else:
                half_width = float(t_critical) * sd / math.sqrt(n)
                rec["ci_low"] = rec["mean_diff"] - half_width
                rec["ci_high"] = rec["mean_diff"] + half_width
                rec["dz"] = float(diff.mean() / sd)
                rec["p_raw"] = float(stats.ttest_rel(arr[:, j], arr[:, i]).pvalue)
                keys.append(key)
                raw_ps.append(rec["p_raw"])
            records[key] = rec

    for key, p_adj in zip(keys, _holm_adjust(raw_ps)):
        records[key]["p_holm"] = p_adj
    out["pairs"] = records
    return out


def _two_sided_sign_p(wins: int, n: int) -> float:
    """Exact two-sided sign-test p for *wins* successes out of *n* trials."""
    if n <= 0:
        return 1.0
    extreme = max(wins, n - wins)
    tail = sum(math.comb(n, i) for i in range(extreme, n + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def _holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, order-preserving and monotone.

    Returns a list aligned to *p_values*.  Monotonicity is enforced by carrying
    the running maximum down the sorted sequence, so an adjusted p can never fall
    below one that was already smaller before adjustment.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda idx: p_values[idx])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[idx]))
        adjusted[idx] = running
    return adjusted


# =========================================================================== #
# Location effect sizes for two independent samples                           #
# (epsilon^2 for Kruskal-Wallis, Mann-Whitney U, bootstrap CIs for Cliff's    #
#  delta).  Added for the realism ranking's typicality effects: every p-value  #
#  it publishes carries an effect size, and every effect size an interval.     #
# =========================================================================== #


def epsilon_squared(h: float, n: int) -> float:
    """Epsilon-squared effect size of a Kruskal-Wallis test, ``H / (n - 1)``.

    Algebraically equal to ``H (n + 1) / (n^2 - 1)`` (Tomczak & Tomczak 2014). It is
    computed from the ``H`` and ``n`` a :func:`kruskal_test` result already carries, so
    the effect size and the test can never describe different samples.

    Raises ``ValueError`` for ``n < 2`` (undefined), or a negative or non-finite ``H``.
    """
    if isinstance(n, bool) or int(n) != n or n < 2:
        raise ValueError(f"epsilon_squared needs an integer n >= 2, got {n!r}")
    h = float(h)
    if not math.isfinite(h) or h < 0.0:
        raise ValueError(f"epsilon_squared needs a finite H >= 0, got {h!r}")
    return h / (int(n) - 1)


def shapiro_wilk_test(values: Sequence[float]) -> dict[str, Any]:
    """Shapiro-Wilk test of normality, wrapping :func:`scipy.stats.shapiro`.

    Reported beside a parametric result (an F test, a paired t-test) as the check of the
    normality it assumes, never as a gate that switches tests.

    Returns ``{"W","p","n"}``. With fewer than 3 values, or when every value is identical
    (the statistic is undefined on zero variance), ``W``/``p`` are ``None`` with a
    ``"note"``.

    Raises ``ValueError`` when *values* is not 1-D or holds a NaN/inf.
    """
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"shapiro_wilk_test needs a 1-D sample, got shape {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("shapiro_wilk_test: the sample contains NaN or inf")
    if arr.size < 3:
        return {"W": None, "p": None, "n": int(arr.size), "note": "Shapiro-Wilk needs >= 3 values"}
    if np.ptp(arr) == 0.0:
        return {"W": None, "p": None, "n": int(arr.size),
                "note": "every value is identical; Shapiro-Wilk is undefined on zero variance"}
    res = stats.shapiro(arr)
    return {"W": float(res.statistic), "p": float(res.pvalue), "n": int(arr.size)}


def _finite_sample(values: Sequence[float], name: str) -> np.ndarray:
    """A non-empty 1-D float sample with no NaN/inf, or ``ValueError``."""
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    if arr.size == 0:
        raise ValueError(f"{name} is empty")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains NaN or inf")
    return arr


def mann_whitney_test(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """Two-sided Mann-Whitney U test of ``a`` against ``b``.

    Wraps :func:`scipy.stats.mannwhitneyu` with ``method="asymptotic"`` (normal
    approximation with the tie and continuity corrections): ties are pervasive on an
    integer rating scale, where the exact null distribution does not apply. ``U`` is the
    statistic of *a*, so ``U / (n_a n_b)`` is ``P(a > b) + P(a = b) / 2`` and
    ``2U / (n_a n_b) - 1`` is :func:`cliffs_delta` of ``(a, b)``.

    Returns ``{"U","p","n_a","n_b","alternative","method"}``. When every value in both
    samples is identical, scipy reports ``p = 1.0`` (no evidence of a difference), which
    is passed through.

    Raises ``ValueError`` when either sample is empty or holds a NaN/inf, as
    :func:`cliffs_delta` does for an empty sample.
    """
    x = _finite_sample(a, "a")
    y = _finite_sample(b, "b")
    res = stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic")
    return {"U": float(res.statistic), "p": float(res.pvalue), "n_a": int(x.size), "n_b": int(y.size),
            "alternative": "two-sided", "method": "asymptotic"}


def cliffs_delta_from_histograms(hist_a: np.ndarray, hist_b: np.ndarray) -> np.ndarray:
    """Cliff's delta of two samples given as histograms over one shared ordered level set.

    ``hist_a``/``hist_b`` have shape ``(..., K)`` (broadcastable): the non-negative
    weight of each of ``K`` levels, **ascending**, in sample *a* / *b*. Through the
    Mann-Whitney identity, ``U_a = sum_i h_a[i] * (weight of b below level i + weight
    of b at level i / 2)`` (mid-rank counting of ties) and
    ``delta = 2 U_a / (W_a W_b) - 1`` with ``W`` the total weights. For integer counts
    this is exactly :func:`cliffs_delta` of the underlying samples; for fractional
    weights (an individual spreading weight 1 over several scored rounds) it is
    ``P(X > Y) - P(X < Y)`` for ``X``, ``Y`` drawn from the two weighted distributions.
    It costs ``O(K)`` per pair of histograms instead of the ``O(n_a n_b)`` sign matrix,
    and is vectorised over the leading axes (bootstrap replicates, groups).

    The caller guarantees non-negative weights with a positive total on both sides
    (checked once where the histograms are built, not in this hot path).
    """
    hist_a = np.asarray(hist_a, dtype=float)
    hist_b = np.asarray(hist_b, dtype=float)
    w_a = hist_a.sum(axis=-1)
    w_b = hist_b.sum(axis=-1)
    below_b = np.cumsum(hist_b, axis=-1) - hist_b
    u_a = (hist_a * (below_b + 0.5 * hist_b)).sum(axis=-1)
    return 2.0 * u_a / (w_a * w_b) - 1.0


def _support_counts(sample: np.ndarray, support: np.ndarray) -> np.ndarray:
    """Occurrences of each *support* value (ascending, containing every sample value)."""
    return np.bincount(np.searchsorted(support, sample), minlength=support.size).astype(float)


def _resampled_counts(counts: np.ndarray, iterations: int, rng: np.random.Generator) -> np.ndarray:
    """``(iterations, K)`` counts of a with-replacement resample at the sample's own size.

    Drawing ``n`` elements with replacement from a sample is the multinomial
    ``Mult(n, counts / n)`` over its support values, so the count vector is drawn
    directly; Cliff's delta depends on a resample only through these counts.
    """
    n = int(counts.sum())
    return rng.multinomial(n, counts / n, size=iterations).astype(float)


def _check_bootstrap_request(iterations: int, ci_level: float | None) -> None:
    """Raise on a malformed resampling request (``ci_level`` ``None`` = not applicable)."""
    if isinstance(iterations, bool) or int(iterations) != iterations or iterations < 1:
        raise ValueError(f"bootstrap iterations must be an integer >= 1, got {iterations!r}")
    if ci_level is not None and not 0.0 < float(ci_level) < 1.0:
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")


def percentile_interval(replicates: Any, *, ci_level: float) -> tuple[Any, Any]:
    """Central percentile interval of bootstrap *replicates* along axis 0.

    ``ci_level`` is the central mass (``0.95`` -> the 2.5th/97.5th percentiles), with
    numpy's default linear interpolation -- the convention of :func:`bootstrap_ci` and
    :func:`bootstrap_difference_ci`. A 1-D input gives two floats; an
    ``(iterations, m)`` input gives two length-``m`` arrays, one interval per column.

    Raises ``ValueError`` on an empty input, a NaN/inf replicate (a degenerate replicate
    must be resolved by the caller, never folded into a bound), or a ``ci_level``
    outside ``(0, 1)``.
    """
    _check_bootstrap_request(1, ci_level)
    arr = np.asarray(replicates, dtype=float)
    if arr.ndim == 0 or arr.shape[0] == 0:
        raise ValueError("percentile_interval needs at least one replicate")
    if not np.isfinite(arr).all():
        raise ValueError("percentile_interval: replicates contain NaN or inf")
    tail = (1.0 - float(ci_level)) / 2.0
    lo = np.quantile(arr, tail, axis=0)
    hi = np.quantile(arr, 1.0 - tail, axis=0)
    if arr.ndim == 1:
        return float(lo), float(hi)
    return lo, hi


def _draws_first(x: np.ndarray, y: np.ndarray) -> bool:
    """Whether *x* draws before *y*: the sample whose sorted values compare lower first.

    Lexicographic on the sorted values, then on the size; identical samples keep the
    argument order (their draws are exchangeable).
    """
    sx, sy = np.sort(x), np.sort(y)
    for vx, vy in zip(sx, sy):
        if vx != vy:
            return bool(vx < vy)
    return bool(sx.size <= sy.size)


def bootstrap_cliffs_delta_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    iterations: int,
    ci_level: float,
    seed: int,
) -> dict[str, Any]:
    """Percentile bootstrap CI for Cliff's delta of two independent samples.

    Each sample is resampled with replacement at its own size, and each replicate's
    delta is computed through the Mann-Whitney identity (:func:`cliffs_delta_from_histograms`)
    rather than the sign matrix. ``point`` is :func:`cliffs_delta` on the observed
    samples; the identity gives the same value, which the tests assert.

    Randomness is one local :func:`numpy.random.default_rng` seeded with *seed*, so the
    interval depends only on ``(a, b, seed, iterations)`` and never on which other
    comparisons a caller runs, or in what order. The two samples draw in a canonical
    order (the one whose sorted values compare lower draws first), so swapping the
    arguments gives exactly the negated point and the mirrored interval.

    Returns ``{"point","lo","hi","ci_level","iterations","n_a","n_b","method"}``, the
    key set of :func:`bootstrap_difference_ci`.

    Raises ``ValueError`` when either sample is empty or holds a NaN/inf, when
    ``iterations < 1``, or when ``ci_level`` is outside ``(0, 1)``.
    """
    _check_bootstrap_request(iterations, ci_level)
    x = _finite_sample(a, "a")
    y = _finite_sample(b, "b")
    point = cliffs_delta(x, y)["delta"]

    support = np.unique(np.concatenate([x, y]))
    counts_x = _support_counts(x, support)
    counts_y = _support_counts(y, support)
    rng = np.random.default_rng(seed)
    if _draws_first(x, y):
        rep_x = _resampled_counts(counts_x, iterations, rng)
        rep_y = _resampled_counts(counts_y, iterations, rng)
    else:
        rep_y = _resampled_counts(counts_y, iterations, rng)
        rep_x = _resampled_counts(counts_x, iterations, rng)
    lo, hi = percentile_interval(cliffs_delta_from_histograms(rep_x, rep_y), ci_level=ci_level)
    return {"point": point, "lo": lo, "hi": hi, "ci_level": float(ci_level),
            "iterations": int(iterations), "n_a": int(x.size), "n_b": int(y.size),
            "method": "percentile"}


# --------------------------------------------------------------------------- #
# Repeated-measures ANOVA assumption checks                                    #
# --------------------------------------------------------------------------- #

# The Huynh-Feldt epsilon variant this module reports, named so the output says
# which one it is: Huynh & Feldt (1976), ``(n p eps_GG - 2) / (p (n - 1 - p eps_GG))``
# with ``p = k - 1``. Lecoutre's (1991) correction replaces the leading ``n`` by
# ``n + 1`` and is *not* what is computed here.
HUYNH_FELDT_FORMULA = "huynh_feldt_1976"


def _import_lilliefors() -> Any:
    try:
        from statsmodels.stats.diagnostic import lilliefors
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(f"statsmodels is not installed. {_ANALYSIS_EXTRA_HINT}") from exc
    return lilliefors


def _shapiro(values: np.ndarray) -> dict[str, Any]:
    """Shapiro-Wilk ``{"W","p"}``, or ``None``s plus a ``"note"`` when undefined.

    Guarded explicitly because ``scipy`` does not fail on the degenerate inputs:
    a zero-range sample returns ``W = p = 1.0`` with only a warning, which would
    read downstream as a perfect normal fit.
    """
    x = np.asarray(values, dtype=float)
    if x.size < 3:
        return {"W": None, "p": None, "note": f"Shapiro-Wilk needs >=3 values, got {x.size}"}
    if float(((x - x.mean()) ** 2).sum()) <= _ZERO_SS_TOL:
        return {"W": None, "p": None, "note": "zero spread; Shapiro-Wilk is undefined"}
    w, p = stats.shapiro(x)
    return {"W": float(w), "p": float(p)}


def _helmert_contrasts(k: int) -> np.ndarray:
    """Orthonormal Helmert contrasts, ``(k-1) x k``; each row sums to 0 with unit norm."""
    contrasts = np.zeros((k - 1, k))
    for row in range(k - 1):
        contrasts[row, : row + 1] = 1.0
        contrasts[row, row + 1] = -float(row + 1)
        contrasts[row] /= np.linalg.norm(contrasts[row])
    return contrasts


def _residual_normality(arr: np.ndarray, labels: Sequence[str]) -> dict[str, Any]:
    """Normality of the two-way additive-model residuals, pooled and per treatment."""
    residuals = arr - arr.mean(axis=1, keepdims=True) - arr.mean(axis=0, keepdims=True) + arr.mean()
    pooled = residuals.ravel()
    out: dict[str, Any] = {
        "residual_definition": "y_ij - block_mean_i - treatment_mean_j + grand_mean",
        "n_residuals": int(pooled.size),
        "shapiro_wilk": _shapiro(pooled),
        "lilliefors": {"D": None, "p": None, "pvalmethod": "table"},
        "per_method_shapiro_wilk": {},
        "worst_method": None,
    }
    if pooled.size < 4:
        out["lilliefors"]["note"] = f"Lilliefors needs >=4 residuals, got {pooled.size}"
    elif float((pooled ** 2).sum()) <= _ZERO_SS_TOL:
        out["lilliefors"]["note"] = "zero residual variation; Lilliefors is undefined"
    else:
        d_stat, p_val = _import_lilliefors()(pooled, dist="norm", pvalmethod="table")
        out["lilliefors"]["D"] = float(d_stat)
        out["lilliefors"]["p"] = float(p_val)

    worst: dict[str, Any] | None = None
    for j, label in enumerate(labels):
        rec = _shapiro(residuals[:, j])
        out["per_method_shapiro_wilk"][label] = rec
        if rec["p"] is not None and (worst is None or rec["p"] < worst["p"]):
            worst = {"method": label, "W": rec["W"], "p": rec["p"]}
    out["worst_method"] = worst
    return out


def _corrected_f(f_stat: float | None, df1: int, df2: int, epsilon: float | None) -> dict[str, Any]:
    """The omnibus F re-referred to ``F(eps*df1, eps*df2)``; ``None`` where undefined."""
    rec: dict[str, Any] = {"epsilon": epsilon, "df1": None, "df2": None, "p": None}
    if epsilon is None:
        return rec
    rec["df1"] = epsilon * df1
    rec["df2"] = epsilon * df2
    if f_stat is None:
        return rec
    # A diverging F (perfectly additive blocks) stays p = 0.0 under any correction,
    # matching rm_anova_within's own statement of that case.
    rec["p"] = 0.0 if math.isinf(f_stat) else float(stats.f.sf(f_stat, rec["df1"], rec["df2"]))
    return rec


def _sphericity(arr: np.ndarray, anova: dict[str, Any]) -> dict[str, Any]:
    """Mauchly's test and the GG / HF / lower-bound epsilon corrections of *anova*."""
    n, k = arr.shape
    p_dim = k - 1
    df1, df2 = int(anova["df1"]), int(anova["df2"])
    f_stat = anova.get("F")
    lower = 1.0 / p_dim
    mauchly: dict[str, Any] = {"W": None, "chi2": None, "df": p_dim * (p_dim + 1) // 2 - 1, "p": None}
    out: dict[str, Any] = {"mauchly": mauchly, "huynh_feldt_formula": HUYNH_FELDT_FORMULA}
    notes: list[str] = []

    gg: float | None
    hf: float | None
    if k == 2:
        # A single difference score has a 1x1 covariance: sphericity cannot fail and
        # every epsilon is exactly 1 (the lower bound 1/(k-1) is 1 as well).
        mauchly["W"] = 1.0
        mauchly["note"] = "k = 2: a single difference score, sphericity holds trivially; not tested"
        gg = hf = 1.0
    else:
        contrasts = _helmert_contrasts(k)
        cov = contrasts @ np.cov(arr, rowvar=False, ddof=1) @ contrasts.T
        trace = float(np.trace(cov))
        trace_sq = float(np.trace(cov @ cov))
        if trace <= _ZERO_SS_TOL or trace_sq <= 0.0:
            gg = hf = None
            mauchly["note"] = "zero variance in every treatment difference; sphericity is undefined"
            notes.append("epsilon undefined: zero variance in every treatment difference")
        else:
            gg = trace ** 2 / (p_dim * trace_sq)
            hf_denominator = p_dim * (n - 1 - p_dim * gg)
            if hf_denominator <= 0.0:
                hf = None
                notes.append(
                    f"Huynh-Feldt epsilon undefined: n - 1 - (k - 1) * eps_GG <= 0 (n = {n}, k = {k})"
                )
            else:
                hf = (n * p_dim * gg - 2.0) / hf_denominator
            _mauchly(mauchly, cov, trace, n, p_dim)

    hf_capped = None if hf is None else min(hf, 1.0)
    out["epsilon"] = {
        "greenhouse_geisser": gg,
        "huynh_feldt": hf,
        "huynh_feldt_capped": hf_capped,
        "lower_bound": lower,
    }
    out["corrected"] = {
        "greenhouse_geisser": _corrected_f(f_stat, df1, df2, gg),
        "huynh_feldt_capped": _corrected_f(f_stat, df1, df2, hf_capped),
        "lower_bound": _corrected_f(f_stat, df1, df2, lower),
    }
    if notes:
        out["note"] = "; ".join(notes)
    return out


def _mauchly(rec: dict[str, Any], cov: np.ndarray, trace: float, n: int, p_dim: int) -> None:
    """Fill Mauchly's ``W``/``chi2``/``p`` into *rec* in place, or a ``note`` when undefined."""
    if n - 1 < p_dim:
        rec["note"] = (
            f"n - 1 = {n - 1} < k - 1 = {p_dim}: the contrast covariance is singular; "
            "Mauchly's test is undefined"
        )
        return
    w_stat = float(np.linalg.det(cov)) / (trace / p_dim) ** p_dim
    if w_stat <= 0.0:
        rec["note"] = "the contrast covariance is numerically singular; Mauchly's test is undefined"
        return
    rec["W"] = w_stat
    factor = (n - 1) - (2 * p_dim ** 2 + p_dim + 2) / (6 * p_dim)
    if factor <= 0.0:
        rec["note"] = f"too few blocks (n = {n}) for the chi-squared approximation; Mauchly's p is undefined"
        return
    chi2 = -factor * math.log(w_stat)
    rec["chi2"] = chi2
    rec["p"] = float(stats.chi2.sf(chi2, rec["df"]))


def _pairwise_assumptions(arr: np.ndarray, labels: Sequence[str], alpha: float) -> dict[str, Any]:
    """Per treatment pair: difference variance + normality, and the Wilcoxon cross-check."""
    k = arr.shape[1]
    # Only mean_diff and the Holm p are read below; neither depends on the interval
    # level, so the (required) level is a fixed placeholder whose interval is discarded.
    paired = paired_t_pairwise(arr, labels=labels, confidence_level=0.95)["pairs"]
    records: dict[str, dict[str, Any]] = {}
    sw_keys: list[str] = []
    sw_ps: list[float] = []
    wx_keys: list[str] = []
    wx_ps: list[float] = []
    for i in range(k):
        for j in range(i + 1, k):
            key = f"{labels[i]}|{labels[j]}"
            # Second minus first, the orientation paired_t_pairwise uses for the same key.
            diff = arr[:, j] - arr[:, i]
            sw = _shapiro(diff)
            rec: dict[str, Any] = {
                "diff_variance": float(diff.var(ddof=1)),
                "diff_shapiro_wilk": {"W": sw["W"], "p": sw["p"], "p_holm": None},
                "wilcoxon": {"statistic": None, "p": None, "p_holm": None},
                "t_p_holm": paired[key]["p_holm"],
                "verdict_differs_from_t": None,
            }
            if "note" in sw:
                rec["diff_shapiro_wilk"]["note"] = sw["note"]
            else:
                sw_keys.append(key)
                sw_ps.append(sw["p"])
            if bool(np.all(diff == 0.0)):
                # scipy returns p = 1.0 here instead of failing; the test has no data.
                rec["wilcoxon"]["note"] = "all paired differences are zero; Wilcoxon is undefined"
            else:
                w_stat, w_p = stats.wilcoxon(arr[:, j], arr[:, i], method="auto")
                rec["wilcoxon"]["statistic"] = float(w_stat)
                rec["wilcoxon"]["p"] = float(w_p)
                wx_keys.append(key)
                wx_ps.append(float(w_p))
            records[key] = rec

    for key, p_adj in zip(sw_keys, _holm_adjust(sw_ps)):
        records[key]["diff_shapiro_wilk"]["p_holm"] = p_adj
    for key, p_adj in zip(wx_keys, _holm_adjust(wx_ps)):
        records[key]["wilcoxon"]["p_holm"] = p_adj
    for rec in records.values():
        w_holm, t_holm = rec["wilcoxon"]["p_holm"], rec["t_p_holm"]
        if w_holm is not None and t_holm is not None:
            rec["verdict_differs_from_t"] = (w_holm <= alpha) != (t_holm <= alpha)
    return records


def rm_anova_assumptions(
    blocks: Sequence[Sequence[float]],
    *,
    labels: Sequence[str],
    alpha: float,
) -> dict[str, Any]:
    """Assumption diagnostics for :func:`rm_anova_within` and :func:`paired_t_pairwise`.

    Input matches both (row = block, column = treatment); *labels* names the
    columns. *alpha* is the significance cutoff the ``verdict_differs_from_t``
    flags are judged at; it has no default -- the caller sources it from config.
    Every p-value is reported and none is acted on: nothing here switches the
    headline test.

    ``residual_normality``
        The additive-model residuals ``e_ij = y_ij - row mean - column mean +
        grand mean`` (the error term the F uses): Shapiro-Wilk on all of them,
        the Lilliefors-corrected Kolmogorov-Smirnov (``statsmodels``, table
        p-values; the plain KS with estimated parameters is anti-conservative
        and is not reported), Shapiro-Wilk per treatment column, and the
        ``worst_method`` (smallest per-column p).
    ``sphericity``
        Mauchly's ``W`` / ``chi2`` / ``df`` / ``p`` on orthonormal Helmert
        contrasts; ``epsilon`` for Greenhouse-Geisser, Huynh-Feldt
        (:data:`HUYNH_FELDT_FORMULA`, uncapped and capped at 1) and the lower
        bound ``1/(k-1)``; ``corrected`` re-refers the F to ``F(eps*df1,
        eps*df2)`` for GG, capped HF and the lower bound. ``k = 2`` is stated
        explicitly: sphericity holds trivially, every epsilon is 1, Mauchly is
        not run.
    ``pairs``
        Per ``"a|b"`` (the key :func:`paired_t_pairwise` uses): the ddof-1
        variance of the ``b - a`` differences; their Shapiro-Wilk ``W``/``p``
        with Holm across pairs; the Wilcoxon signed-rank ``statistic``/``p``
        (``scipy``'s ``method="auto"``: the exact distribution for small n
        without zero differences, the normal approximation otherwise) with Holm
        across pairs; the paired t ``t_p_holm``; and ``verdict_differs_from_t``,
        true when exactly one of the two Holm p-values is ``<= alpha``.

    Degenerate input never yields a NaN: fewer than 2 treatments or blocks
    returns the skeleton with ``None`` sub-blocks and a ``"note"``; an undefined
    individual statistic (too few values, zero spread, singular covariance) is
    ``None`` with its own ``"note"``. Malformed input raises: NaN cells (via the
    block-matrix guard), a *labels* length that does not match the columns, or an
    *alpha* outside ``(0, 1)``.
    """
    arr = _as_block_matrix(blocks)
    n, k = arr.shape
    if len(labels) != k:
        raise ValueError(f"labels has {len(labels)} entries but the matrix has {k} columns")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0.0 < float(alpha) < 1.0:
        raise ValueError(f"alpha must be a number in (0, 1), got {alpha!r}")
    out: dict[str, Any] = {
        "n": n,
        "k": k,
        "alpha": float(alpha),
        "residual_normality": None,
        "sphericity": None,
        "pairs": {},
        "correction": {"method": "holm", "scope": "all-pairs"},
    }
    if k < 2 or n < 2:
        out["note"] = f"need >=2 treatments and >=2 blocks, got {k} treatments / {n} blocks"
        return out
    anova = rm_anova_within(arr)
    out["residual_normality"] = _residual_normality(arr, labels)
    out["sphericity"] = _sphericity(arr, anova)
    out["pairs"] = _pairwise_assumptions(arr, labels, float(alpha))
    return out

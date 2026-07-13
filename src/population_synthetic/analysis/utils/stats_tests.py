"""stats_tests.py -- Non-parametric hypothesis tests shared across analysis processes.

Houses the statistical machinery used by the cross-run run_analytics comparison and
the cross-model performance comparison: the Kruskal-Wallis omnibus test, an
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
Every re-implemented statistic (Page's L, Kendall's W, Cliff's delta) is validated
against a hand-computed value in ``tests/test_stats_tests_significance.py``; the
library-backed ones are pinned to the library's own output on fixtures.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
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

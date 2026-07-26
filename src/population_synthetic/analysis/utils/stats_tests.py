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
    groups with >=2 samples each, or zero variance in *every* group (all values
    identical -> the statistic is undefined rather than a meaningful ``NaN``).

    Raises
    ------
    ValueError
        If ``center`` is not ``median`` or ``mean``.
    """
    if center not in ("median", "mean"):
        raise ValueError(f"center must be 'median' or 'mean', got {center!r}")

    usable = {g: v for g, v in groups.items() if len(v) >= 2}
    n_total = sum(len(v) for v in usable.values())
    if len(usable) < 2:
        return {"statistic": None, "p": None, "k": len(usable), "center": center,
                "n": n_total, "note": "need >=2 groups with >=2 samples each"}
    if all(float(np.var(v)) == 0.0 for v in usable.values()):
        return {"statistic": None, "p": None, "k": len(usable), "center": center,
                "n": n_total, "note": "zero variance in every group; test undefined"}

    stat, p = stats.levene(*usable.values(), center=center)
    return {"statistic": float(stat), "p": float(p), "k": len(usable),
            "center": center, "n": n_total}

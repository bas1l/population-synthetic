"""multivariate.py -- Pure metric primitives for joint / multivariate fidelity.

These are dependency-light, unit-testable functions that operate on lists of
canonical individuals plus a :class:`ComparisonScheme` (the single source of truth
for the scored attributes and their DB-grounded category sets). The evaluator
(Phase 3) calls them; they hold no population/scheme plumbing of their own.

Value derivation is *not* reinvented here: every function reads attribute values
through :func:`population_synthetic.analysis.comparison.evaluator.attr_value`, the
same accessor the marginal/joint/coherence code uses (it derives ``age_group`` from
the raw integer ``age``). This keeps a single source of truth for age binning and
legacy fallbacks. Because ``evaluator`` does not import this module at module load
time, importing ``attr_value`` here is cycle-free; Phase 3 must import
``multivariate`` *lazily* (inside the calling method) to keep it that way.

Functions
---------
- ``one_hot_encode(individuals, scheme)`` -- stable one-hot matrix over the scheme's
  attributes; categories fixed by ``scheme.categories`` so encoding is identical
  across populations. Values outside an attribute's category set (synthetic-only or
  missing) become an all-zero block for that attribute (the implicit "other").
- ``cramers_v(counts_table)`` -- bias-corrected (Bergsma) Cramer's V for a 2D counts
  table; degenerate/single-category tables return 0.0 with no divide-by-zero.
- ``association_matrix(individuals, attrs, scheme)`` -- pairwise Cramer's V over the
  attribute pairs, keyed by ``(attr_x, attr_y)`` with ``attr_x`` before ``attr_y`` in
  *attrs* order.
- ``joint_tv(individuals_a, individuals_b, attr_x, attr_y, scheme)`` -- joint
  total-variation distance between two populations' (x, y) cross-tabs.
- ``c2st(X_real, X_syn, ...)`` -- classifier two-sample test (scikit-learn backend if
  available, else a numpy/scipy MMD-style nearest-centroid fallback), returning
  ``{auc, p_value, method, balanced_n}`` with real/synthetic balanced by subsampling.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import rankdata

from population_synthetic.analysis.comparison.evaluator import attr_value
from population_synthetic.analysis.comparison.scheme import ComparisonScheme

# ------------------------------------------------------------------
# One-hot encoding
# ------------------------------------------------------------------


def one_hot_encode(individuals: list[dict], scheme: ComparisonScheme) -> np.ndarray:
    """One-hot encode *individuals* over the scheme's attributes.

    Columns are laid out block-by-block in ``scheme.attributes`` order; within each
    block the columns follow that attribute's ``scheme.categories`` order, so the
    encoding is stable and comparable across populations. A value not in an
    attribute's category set (a synthetic-only value, or ``None``) leaves that
    attribute's whole block zero -- the implicit "other" column -- rather than
    growing the matrix.

    Returns a ``float`` array of shape ``(len(individuals), total_columns)`` where
    ``total_columns`` is the summed category count over all attributes. Raises
    ``KeyError`` if the scheme declares an attribute without a category list.
    """
    blocks: list[tuple[str, dict[Any, int], int]] = []
    offset = 0
    offsets: list[int] = []
    for attr in scheme.attributes:
        if attr not in scheme.categories:
            raise KeyError(f"Scheme attribute {attr!r} has no category list; cannot one-hot encode.")
        cats = list(scheme.categories[attr])
        blocks.append((attr, {c: i for i, c in enumerate(cats)}, len(cats)))
        offsets.append(offset)
        offset += len(cats)

    total_columns = offset
    matrix = np.zeros((len(individuals), total_columns), dtype=float)
    for row, ind in enumerate(individuals):
        for (attr, index_of, _width), base in zip(blocks, offsets):
            col = index_of.get(attr_value(ind, attr))
            if col is not None:
                matrix[row, base + col] = 1.0
    return matrix


# ------------------------------------------------------------------
# Cramer's V (bias-corrected)
# ------------------------------------------------------------------


def cramers_v(counts_table: Any) -> float:
    """Bias-corrected (Bergsma) Cramer's V for a 2D contingency table of counts.

    ``V = sqrt(phi2_corr / min(r_corr - 1, c_corr - 1))`` where the phi-squared and
    the effective row/column counts carry Bergsma's small-sample bias correction:

    - ``phi2 = chi2 / n``
    - ``phi2_corr = max(0, phi2 - (r-1)(c-1)/(n-1))``
    - ``r_corr = r - (r-1)**2/(n-1)``, ``c_corr = c - (c-1)**2/(n-1)``

    All-zero rows and columns are trimmed first so ``r`` / ``c`` reflect observed
    categories. Degenerate tables -- empty, single effective row or column, or a
    zero correction denominator -- return ``0.0`` (no association, no divide-by-zero).
    """
    table = np.asarray(counts_table, dtype=float)
    if table.ndim != 2:
        raise ValueError(f"cramers_v expects a 2D counts table, got ndim={table.ndim}.")

    # Trim all-zero rows/columns so r, c count observed categories only.
    if table.size:
        table = table[table.sum(axis=1) > 0][:, table.sum(axis=0) > 0]

    n = float(table.sum())
    if n <= 1.0:
        return 0.0

    r, c = table.shape
    if r < 2 or c < 2:
        return 0.0

    row_sums = table.sum(axis=1, keepdims=True)
    col_sums = table.sum(axis=0, keepdims=True)
    expected = row_sums @ col_sums / n
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2_cells = np.where(expected > 0, (table - expected) ** 2 / expected, 0.0)
    chi2 = float(chi2_cells.sum())

    phi2 = chi2 / n
    phi2_corr = max(0.0, phi2 - (r - 1) * (c - 1) / (n - 1))
    r_corr = r - (r - 1) ** 2 / (n - 1)
    c_corr = c - (c - 1) ** 2 / (n - 1)
    denom = min(r_corr - 1, c_corr - 1)
    if denom <= 0:
        return 0.0
    return float(np.sqrt(phi2_corr / denom))


# ------------------------------------------------------------------
# Cross-tabulation helpers (scheme-driven grid)
# ------------------------------------------------------------------


def _grid_crosstab(
    individuals: list[dict], attr_x: str, attr_y: str, scheme: ComparisonScheme
) -> np.ndarray:
    """Counts cross-tab of (*attr_x*, *attr_y*) over the scheme's fixed category grid.

    Rows follow ``scheme.categories[attr_x]``, columns ``scheme.categories[attr_y]``,
    so the grid is identical for any population (values outside the grid, including
    ``None``, are dropped -- mirroring the marginal evaluator's scheme-driven axis).
    Raises ``KeyError`` for an attribute the scheme declares no categories for.
    """
    cats_x = list(scheme.categories[attr_x])
    cats_y = list(scheme.categories[attr_y])
    x_index = {v: i for i, v in enumerate(cats_x)}
    y_index = {v: i for i, v in enumerate(cats_y)}
    table = np.zeros((len(cats_x), len(cats_y)), dtype=float)
    for ind in individuals:
        i = x_index.get(attr_value(ind, attr_x))
        j = y_index.get(attr_value(ind, attr_y))
        if i is not None and j is not None:
            table[i, j] += 1.0
    return table


def association_matrix(
    individuals: list[dict], attrs: list[str], scheme: ComparisonScheme
) -> dict[tuple[str, str], float]:
    """Pairwise (bias-corrected) Cramer's V for every unordered pair in *attrs*.

    Returns a dict keyed by ``(attr_x, attr_y)`` -- ``attr_x`` before ``attr_y`` in
    *attrs* order -- to the Cramer's V of that pair's cross-tab in *individuals*.
    Phase 3 computes per-pair ``|V_real - V_syn|`` by calling this on each population
    and differencing the shared keys.
    """
    result: dict[tuple[str, str], float] = {}
    for i in range(len(attrs)):
        for j in range(i + 1, len(attrs)):
            attr_x, attr_y = attrs[i], attrs[j]
            table = _grid_crosstab(individuals, attr_x, attr_y, scheme)
            result[(attr_x, attr_y)] = cramers_v(table)
    return result


def joint_tv(
    individuals_a: list[dict],
    individuals_b: list[dict],
    attr_x: str,
    attr_y: str,
    scheme: ComparisonScheme,
) -> float:
    """Joint total-variation distance between two populations' (x, y) distributions.

    ``TV = 0.5 * sum_cells |p_a(x, y) - p_b(x, y)|`` over the scheme's fixed
    ``attr_x`` x ``attr_y`` grid. Each population's cell probabilities are normalised
    over its own in-grid mass (matching the marginal evaluator's zero-filled,
    in-axis normalisation). Returns ``0.0`` for identical joints, ``1.0`` for disjoint
    supports, and ``nan`` when either population has no in-grid observations.
    """
    table_a = _grid_crosstab(individuals_a, attr_x, attr_y, scheme)
    table_b = _grid_crosstab(individuals_b, attr_x, attr_y, scheme)
    total_a = table_a.sum()
    total_b = table_b.sum()
    if total_a == 0 or total_b == 0:
        return float("nan")
    p_a = table_a / total_a
    p_b = table_b / total_b
    return float(0.5 * np.abs(p_a - p_b).sum())


# ------------------------------------------------------------------
# Classifier two-sample test (C2ST)
# ------------------------------------------------------------------


def _sklearn_available() -> bool:
    try:
        import sklearn.linear_model  # noqa: F401
        import sklearn.metrics  # noqa: F401
        import sklearn.model_selection  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_method(method: str) -> str:
    """Resolve the requested C2ST *method* to the backend actually used.

    ``"mmd"`` forces the numpy/scipy fallback; ``"auto"``/``"sklearn"`` use
    scikit-learn if importable and otherwise fall back to ``"mmd"`` (so the module
    works without scikit-learn installed). Any other value fails loudly.
    """
    if method == "mmd":
        return "mmd"
    if method in ("auto", "sklearn"):
        return "sklearn" if _sklearn_available() else "mmd"
    raise ValueError(f"Unknown c2st method {method!r}; expected 'auto', 'sklearn', or 'mmd'.")


def _auc_from_scores(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC-AUC of real(0)/synthetic(1) *labels* from continuous *scores* (rank-based).

    Uses the Mann-Whitney identity with tie-aware average ranks (``scipy.rankdata``),
    so constant scores (identical distributions) give exactly 0.5.
    """
    labels = np.asarray(labels)
    pos = labels == 1
    n_pos = int(pos.sum())
    n_neg = int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(scores)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _stratified_folds(labels: np.ndarray, folds: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Return *folds* test-index arrays, each stratified across the two classes."""
    idx0 = np.where(labels == 0)[0]
    idx1 = np.where(labels == 1)[0]
    rng.shuffle(idx0)
    rng.shuffle(idx1)
    parts0 = np.array_split(idx0, folds)
    parts1 = np.array_split(idx1, folds)
    return [np.concatenate([parts0[k], parts1[k]]) for k in range(folds)]


def _cv_centroid_auc(X: np.ndarray, labels: np.ndarray, folds: int, seed: int) -> float:
    """Cross-validated ROC-AUC of a nearest-centroid (linear-MMD) classifier.

    Per fold, the direction ``mu_syn - mu_real`` is estimated on the training rows and
    each held-out row is scored by its projection onto it; the pooled held-out scores
    give the AUC. This is the numpy-only surrogate for a trained C2ST classifier and
    the linear-kernel MMD statistic underlies it.
    """
    splits = _stratified_folds(labels, folds, np.random.default_rng(seed))
    scores = np.full(len(labels), np.nan)
    for test_idx in splits:
        train_mask = np.ones(len(labels), dtype=bool)
        train_mask[test_idx] = False
        y_train = labels[train_mask]
        x_train = X[train_mask]
        real = x_train[y_train == 0]
        syn = x_train[y_train == 1]
        if len(real) == 0 or len(syn) == 0:
            continue
        direction = syn.mean(axis=0) - real.mean(axis=0)
        scores[test_idx] = X[test_idx] @ direction
    return _auc_from_scores(scores, labels)


def _c2st_mmd(X: np.ndarray, labels: np.ndarray, folds: int, seed: int, n_permutations: int) -> tuple[float, float]:
    """Nearest-centroid C2ST AUC plus a label-permutation p-value (numpy/scipy only)."""
    auc = _cv_centroid_auc(X, labels, folds, seed)
    if np.isnan(auc) or n_permutations <= 0:
        return auc, float("nan")
    perm_rng = np.random.default_rng(seed)
    at_least = 0
    for _ in range(n_permutations):
        permuted = perm_rng.permutation(labels)
        if _cv_centroid_auc(X, permuted, folds, seed) >= auc:
            at_least += 1
    p_value = (1 + at_least) / (1 + n_permutations)
    return auc, p_value


def _c2st_sklearn(X: np.ndarray, labels: np.ndarray, folds: int, seed: int, n_permutations: int) -> tuple[float, float]:
    """scikit-learn C2ST: CV logistic-regression AUC plus a label-permutation p-value."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    def _cv_auc(y: np.ndarray) -> float:
        skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        scores = np.full(len(y), np.nan)
        for train_idx, test_idx in skf.split(X, y):
            clf = LogisticRegression(max_iter=1000)
            clf.fit(X[train_idx], y[train_idx])
            scores[test_idx] = clf.predict_proba(X[test_idx])[:, 1]
        return float(roc_auc_score(y, scores))

    auc = _cv_auc(labels)
    if n_permutations <= 0:
        return auc, float("nan")
    perm_rng = np.random.default_rng(seed)
    at_least = sum(_cv_auc(perm_rng.permutation(labels)) >= auc for _ in range(n_permutations))
    p_value = (1 + at_least) / (1 + n_permutations)
    return auc, p_value


def c2st(
    X_real: Any,
    X_syn: Any,
    method: str = "auto",
    folds: int = 5,
    seed: int = 0,
    n_repeats: int = 5,
    n_permutations: int = 200,
) -> dict[str, Any]:
    """Classifier two-sample test between real and synthetic feature matrices.

    *X_real* / *X_syn* are ``(n, d)`` arrays (e.g. from :func:`one_hot_encode`).
    Labels are real=0, synthetic=1. Because real ``n`` typically far exceeds
    synthetic ``n``, the classes are **balanced** by subsampling the larger down to
    ``balanced_n = min(n_real, n_syn)`` per repeat (repeated *n_repeats* times and
    averaged) so the AUC is not inflated by class imbalance.

    Returns ``{"auc", "p_value", "method", "balanced_n"}``. ``method`` is the backend
    actually used (``"sklearn"`` or ``"mmd"``). For a balanced size below 2 (a tiny or
    failed synthetic population) the AUC and p-value degrade to ``nan`` without error.
    An AUC near 0.5 means the joint distributions are indistinguishable; near 1.0
    means trivially separable.
    """
    real = np.asarray(X_real, dtype=float)
    syn = np.asarray(X_syn, dtype=float)
    resolved = _resolve_method(method)
    balanced_n = int(min(len(real), len(syn)))

    if balanced_n < 2:
        return {"auc": float("nan"), "p_value": float("nan"), "method": resolved, "balanced_n": balanced_n}

    eff_folds = max(2, min(folds, balanced_n))
    rng = np.random.default_rng(seed)
    backend = _c2st_sklearn if resolved == "sklearn" else _c2st_mmd

    aucs: list[float] = []
    p_values: list[float] = []
    for repeat in range(n_repeats):
        real_sub = _subsample(real, balanced_n, rng)
        syn_sub = _subsample(syn, balanced_n, rng)
        features = np.vstack([real_sub, syn_sub])
        labels = np.concatenate([np.zeros(balanced_n), np.ones(balanced_n)])
        auc, p_value = backend(features, labels, eff_folds, seed + repeat, n_permutations)
        aucs.append(auc)
        p_values.append(p_value)

    return {
        "auc": float(np.nanmean(aucs)),
        "p_value": float(np.nanmean(p_values)),
        "method": resolved,
        "balanced_n": balanced_n,
    }


def _subsample(X: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Return *n* rows of *X* without replacement (all rows, shuffled, when ``len==n``)."""
    if len(X) == n:
        return X
    chosen = rng.choice(len(X), size=n, replace=False)
    return X[chosen]

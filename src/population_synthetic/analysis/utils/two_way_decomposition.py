"""two_way_decomposition.py -- Additive two-way decomposition of one value per cell.

The design this serves is a crossed grid of two factors (e.g. model x strategy) holding
**one** value per cell, some cells possibly absent (a withdrawn combination). With one
value per cell there is no within-cell replicate, so the model is additive,
``y ~ A + B``, and the residual holds the ``A x B`` interaction together with the
sampling noise -- they cannot be separated. The functions here partition that fit and
test each factor; they know nothing about what the factors or the value are.

* :func:`additive_two_way_anova` -- type II sums of squares (``SS(A | B)`` and
  ``SS(B | A)``), which for an additive model with no interaction term coincide with
  type III, so an unbalanced or incomplete grid is handled without choosing an order.
  Per factor: the F test, partial eta^2, partial omega^2, omega^2 and the share of the
  total SS. Because the design may be unbalanced, the two type II SS plus the residual
  need not add up to the total; the remainder is reported as ``share_overlap``, never
  hidden.
* :func:`additive_two_way_residuals` -- the per-value residuals of that fit, for the
  normality check reported beside its F test.
* :func:`additive_two_way_effect_sizes` -- the same quantities, vectorised over a
  stack of replicate value vectors (bootstrap replicates), for interval estimates.
* :func:`within_block_permutation_test` -- a permutation test of one factor's type II
  F that permutes the values **within each level of the other factor**, so the other
  factor's effect is held fixed and no normality assumption is needed.

The F ``p`` reported by :func:`additive_two_way_anova` is the parametric reference
value; the permutation p is the assumption-free one. Both share one fit
(:func:`_additive_fit`), so they can never describe different models.

Degenerate-input policy (matches :mod:`population_synthetic.analysis.utils.stats_tests`):
malformed input (ragged, NaN, not exactly two factors) raises; a well-formed design on
which a statistic is undefined (no residual degrees of freedom, a factor with one
level, zero total variation) returns that statistic ``None`` with a ``"note"``.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Any

import numpy as np
from scipy import stats

#: The factor statistics both the one-shot fit and the replicate fit report.
_FACTOR_STATS = ("ss", "F", "partial_eta_sq", "partial_omega_sq", "omega_sq", "share")

#: Residual SS at or below this fraction of the total SS is treated as exactly zero: the
#: projection leaves rounding residue (~1e-30) where an additive grid has none.
_ZERO_RESIDUAL_FRACTION = 1e-12

#: Relative tolerance under which a permuted F counts as "at least as extreme" as the
#: observed one. The identity permutation reproduces the observed F only up to
#: floating-point rounding of the projection, and must count.
_F_TIE_TOLERANCE = 1e-9


def _level_codes(labels: Sequence[Hashable], name: str, n: int) -> tuple[np.ndarray, list[Hashable]]:
    """Integer codes of *labels* in order of first appearance, plus the level list."""
    if len(labels) != n:
        raise ValueError(f"factor {name!r} has {len(labels)} labels but there are {n} values")
    levels = list(dict.fromkeys(labels))
    index = {level: i for i, level in enumerate(levels)}
    return np.array([index[label] for label in labels], dtype=int), levels


def _validated(values: Any, factors: Mapping[str, Sequence[Hashable]]) -> tuple[np.ndarray, list[str]]:
    """The value array (last axis = cells) and the two factor names, or ``ValueError``."""
    if len(factors) != 2:
        raise ValueError(f"an additive two-way decomposition needs exactly two factors, got {list(factors)}")
    arr = np.asarray(values, dtype=float)
    if arr.ndim not in (1, 2) or arr.shape[-1] == 0:
        raise ValueError(f"values must be a non-empty (n,) or (replicates, n) array, got shape {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("values contain NaN or inf (an absent cell must be left out, not passed as NaN)")
    return arr, list(factors)


def _residual_projector(design: np.ndarray) -> np.ndarray:
    """``I - X X^+``: maps a value vector to its least-squares residual under *design*."""
    return np.eye(design.shape[0]) - design @ np.linalg.pinv(design)


def _rss(y: np.ndarray, projector: np.ndarray) -> np.ndarray:
    """Residual sum of squares of every row of *y* (shape ``(r, n)``) under one design."""
    return np.einsum("ri,ij,rj->r", y, projector, y)


def _additive_fit(y: np.ndarray, codes: dict[str, np.ndarray]) -> dict[str, Any]:
    """Type II partition of every row of *y* (``(r, n)``) under ``y ~ A + B``.

    Returns degrees of freedom (scalars) and SS / effect-size arrays of shape ``(r,)``.
    A statistic that is undefined for the design is ``None``; one that is undefined for
    a particular row is NaN (the public wrappers decide what to do with it).
    """
    names = list(codes)
    n = y.shape[1]
    one = np.ones((n, 1))
    dummies = {f: np.eye(int(c.max()) + 1)[c][:, 1:] for f, c in codes.items()}
    designs = {
        "null": one,
        names[0]: np.hstack([one, dummies[names[0]]]),
        names[1]: np.hstack([one, dummies[names[1]]]),
        "full": np.hstack([one, dummies[names[0]], dummies[names[1]]]),
    }
    rank = {k: int(np.linalg.matrix_rank(x)) for k, x in designs.items()}
    rss = {k: _rss(y, _residual_projector(x)) for k, x in designs.items()}
    df_resid = n - rank["full"]
    # The total SS is taken directly (exactly 0 for a constant row), not via a projector.
    ss_total = ((y - y.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
    ss_resid = np.maximum(rss["full"], 0.0)
    fit: dict[str, Any] = {"n": n, "df_residual": df_resid, "ss_total": ss_total, "ss_residual": ss_resid}
    with np.errstate(divide="ignore", invalid="ignore"):
        ms_resid = ss_resid / df_resid if df_resid > 0 else None
        fit["ms_residual"] = ms_resid
        fit["share_residual"] = ss_resid / ss_total
        shares = []
        for f, other in ((names[0], names[1]), (names[1], names[0])):
            df = rank["full"] - rank[other]
            ss = np.maximum(rss[other] - rss["full"], 0.0)   # SS(f | other), type II
            row: dict[str, Any] = {"levels": int(codes[f].max()) + 1, "df": df, "ss": ss,
                                   "ss_type1_first": np.maximum(ss_total - rss[f], 0.0),
                                   "share": ss / ss_total}
            if df > 0 and ms_resid is not None:
                row["F"] = (ss / df) / ms_resid
                row["partial_eta_sq"] = ss / (ss + ss_resid)
                row["partial_omega_sq"] = (ss - df * ms_resid) / (ss + (n - df) * ms_resid)
                row["omega_sq"] = (ss - df * ms_resid) / (ss_total + ms_resid)
            else:
                row.update({"F": None, "partial_eta_sq": None, "partial_omega_sq": None, "omega_sq": None})
            fit[f] = row
            shares.append(row["share"])
        fit["share_overlap"] = 1.0 - shares[0] - shares[1] - fit["share_residual"]
    return fit


def _codes(factors: Mapping[str, Sequence[Hashable]], n: int) -> tuple[dict[str, np.ndarray], dict[str, list]]:
    codes: dict[str, np.ndarray] = {}
    levels: dict[str, list] = {}
    for name, labels in factors.items():
        codes[name], levels[name] = _level_codes(labels, name, n)
    return codes, levels


def _as_float(x: Any) -> float | None:
    return None if x is None else float(np.asarray(x).reshape(-1)[0])


def additive_two_way_anova(values: Sequence[float], factors: Mapping[str, Sequence[Hashable]]) -> dict[str, Any]:
    """Type II decomposition of one value per cell under ``y ~ A + B`` (no interaction).

    *values* holds one value per present cell; *factors* maps each of exactly two factor
    names to the per-value level labels (same length as *values*). Absent cells are
    simply not listed, which makes the design unbalanced; the type II partition handles
    that without an order choice.

    For each factor ``f`` with ``df_f`` degrees of freedom and ``SS_f = SS(f | other)``,
    with ``MS_res = SS_res / df_res`` and ``N`` the number of values:

    * ``F = (SS_f / df_f) / MS_res`` and its parametric ``p`` from ``F(df_f, df_res)``;
    * ``partial_eta_sq = SS_f / (SS_f + SS_res)``;
    * ``partial_omega_sq = (SS_f - df_f MS_res) / (SS_f + (N - df_f) MS_res)``, which,
      unlike eta^2, charges each factor for its degrees of freedom, so a factor with
      more levels is not favoured by construction;
    * ``omega_sq = (SS_f - df_f MS_res) / (SS_total + MS_res)``;
    * ``share = SS_f / SS_total``; plus ``ss_type1_first`` (the factor's SS when entered
      first), for reading how much of it overlaps the other factor.

    Returns ``{"n","design","factor_names","df_residual","ss_total","ss_residual",
    "ms_residual","share_residual","share_overlap","factors"}`` where ``factors`` maps
    each name to ``{"levels","df","ss","ss_type1_first","F","p","partial_eta_sq",
    "partial_omega_sq","omega_sq","share"}``. With no residual degrees of freedom, a
    factor with a single level, or zero residual variation, the undefined statistics are
    ``None`` and a ``"note"`` says why; zero total variation leaves every share and
    effect size ``None``.

    Raises ``ValueError`` unless there are exactly two factors, each with one label per
    value, and the values are finite.
    """
    y, names = _validated(values, factors)
    if y.ndim != 1:
        raise ValueError(f"additive_two_way_anova takes one value vector, got shape {y.shape}")
    codes, _ = _codes(factors, y.size)
    fit = _additive_fit(y[None, :], codes)
    notes: list[str] = []
    out: dict[str, Any] = {
        "n": fit["n"],
        "design": "additive two-way (no interaction term); type II sums of squares",
        "factor_names": names,
        "df_residual": fit["df_residual"],
        "ss_total": _as_float(fit["ss_total"]),
        "ss_residual": _as_float(fit["ss_residual"]),
        "ms_residual": _as_float(fit["ms_residual"]),
        "share_residual": None,
        "share_overlap": None,
        "factors": {},
    }
    total_zero = out["ss_total"] == 0.0
    resid_zero = out["df_residual"] > 0 and out["ss_residual"] <= _ZERO_RESIDUAL_FRACTION * out["ss_total"]
    if fit["df_residual"] <= 0:
        notes.append("no residual degrees of freedom; F and effect sizes are undefined")
    if total_zero:
        notes.append("zero total variation; shares and effect sizes are undefined")
    elif resid_zero:
        notes.append("zero residual variation; F diverges and the effect sizes are 1")
    if not total_zero:
        out["share_residual"] = _as_float(fit["share_residual"])
        out["share_overlap"] = _as_float(fit["share_overlap"])
    for name in names:
        row = fit[name]
        entry: dict[str, Any] = {"levels": row["levels"], "df": row["df"], "ss": _as_float(row["ss"]),
                                 "ss_type1_first": _as_float(row["ss_type1_first"]), "F": None, "p": None,
                                 "partial_eta_sq": None, "partial_omega_sq": None, "omega_sq": None,
                                 "share": None if total_zero else _as_float(row["share"])}
        if row["df"] <= 0:
            notes.append(f"factor {name!r} has no degrees of freedom given the other factor")
        elif row["F"] is not None and not total_zero:
            if resid_zero:
                entry.update({"F": float("inf"), "p": 0.0, "partial_eta_sq": 1.0, "partial_omega_sq": 1.0,
                              "omega_sq": entry["share"]})
            else:
                f_stat = _as_float(row["F"])
                entry.update({"F": f_stat, "p": float(stats.f.sf(f_stat, row["df"], fit["df_residual"])),
                              "partial_eta_sq": _as_float(row["partial_eta_sq"]),
                              "partial_omega_sq": _as_float(row["partial_omega_sq"]),
                              "omega_sq": _as_float(row["omega_sq"])})
        out["factors"][name] = entry
    if notes:
        out["note"] = "; ".join(notes)
    return out


def additive_two_way_residuals(values: Sequence[float], factors: Mapping[str, Sequence[Hashable]]) -> np.ndarray:
    """Least-squares residuals of one value vector under ``y ~ A + B`` (no interaction).

    The same design :func:`additive_two_way_anova` fits, returned per value (in input
    order) so a caller can check the normality its F test assumes. With one value per
    cell the residual holds the interaction and the sampling noise together.

    Raises ``ValueError`` on the malformed inputs :func:`additive_two_way_anova` rejects.
    """
    y, names = _validated(values, factors)
    if y.ndim != 1:
        raise ValueError(f"additive_two_way_residuals takes one value vector, got shape {y.shape}")
    codes, _ = _codes(factors, y.size)
    one = np.ones((y.size, 1))
    design = np.hstack([one] + [np.eye(int(codes[f].max()) + 1)[codes[f]][:, 1:] for f in names])
    return _residual_projector(design) @ y


def additive_two_way_effect_sizes(
    replicates: Any,
    factors: Mapping[str, Sequence[Hashable]],
) -> dict[str, Any]:
    """The decomposition of :func:`additive_two_way_anova` for a stack of value vectors.

    *replicates* has shape ``(r, n)``: one value vector per replicate (e.g. per bootstrap
    draw), every row over the same *factors* design. Returns
    ``{"ss_total","ss_residual","share_residual","share_overlap","factors"}`` with each
    value an array of shape ``(r,)`` and ``factors`` mapping each name to arrays for
    ``ss``, ``F``, ``partial_eta_sq``, ``partial_omega_sq``, ``omega_sq`` and ``share``.
    Differences and ratios of these (e.g. strategy minus model partial omega^2) are the
    caller's, row by row. No p-value is computed.

    Raises ``ValueError`` on the malformed inputs :func:`additive_two_way_anova` rejects,
    when the design has no residual degrees of freedom or a factor has none, and when
    any replicate has zero total or zero residual variation -- a replicate whose effect
    sizes are undefined must be resolved by the caller, not folded into an interval.
    """
    y, names = _validated(replicates, factors)
    if y.ndim != 2:
        raise ValueError(f"additive_two_way_effect_sizes takes a (replicates, n) array, got shape {y.shape}")
    codes, _ = _codes(factors, y.shape[1])
    fit = _additive_fit(y, codes)
    if fit["df_residual"] <= 0:
        raise ValueError("the design has no residual degrees of freedom; effect sizes are undefined")
    for name in names:
        if fit[name]["df"] <= 0:
            raise ValueError(f"factor {name!r} has no degrees of freedom given the other factor")
    degenerate = int(np.sum((fit["ss_total"] <= 0.0)
                            | (fit["ss_residual"] <= _ZERO_RESIDUAL_FRACTION * fit["ss_total"])))
    if degenerate:
        raise ValueError(f"{degenerate} replicate(s) have zero total or residual variation; effect sizes undefined")
    return {
        "ss_total": fit["ss_total"],
        "ss_residual": fit["ss_residual"],
        "share_residual": fit["share_residual"],
        "share_overlap": fit["share_overlap"],
        "factors": {name: {k: fit[name][k] for k in _FACTOR_STATS} for name in names},
    }


def within_block_permutation_test(
    values: Sequence[float],
    factors: Mapping[str, Sequence[Hashable]],
    *,
    factor: str,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    """Permutation test of one factor's type II F, permuting within the other factor.

    The statistic is ``F`` of *factor* in the additive fit of
    :func:`additive_two_way_anova`. Under the null that *factor* has no effect given the
    other factor, the values are exchangeable **within each level of the other factor**
    (the block), so each permutation shuffles the values inside every block and keeps
    the design fixed. A block holding fewer levels of *factor* than others (an absent
    cell) simply permutes among the cells it has.

    ``p = (1 + #{F* >= F_obs}) / (iterations + 1)`` (the observed arrangement counts as
    one permutation, so ``p`` is never 0), with a relative tolerance of
    :data:`_F_TIE_TOLERANCE` on the comparison.

    Randomness is one local :func:`numpy.random.default_rng` seeded with *seed*; blocks
    are visited in order of first appearance, so the result depends on the row order of
    the input, which a caller keeps deterministic.

    Returns ``{"factor","block","F","df_effect","df_residual","p","n_at_least_as_extreme",
    "iterations","method"}``. When the observed F is undefined (see
    :func:`additive_two_way_anova`), ``F``/``p`` are ``None`` with a ``"note"``.

    Raises ``ValueError`` on the malformed inputs :func:`additive_two_way_anova` rejects,
    an unknown *factor*, or ``iterations < 1``.
    """
    if factor not in factors:
        raise ValueError(f"factor {factor!r} is not one of {list(factors)}")
    if isinstance(iterations, bool) or int(iterations) != iterations or iterations < 1:
        raise ValueError(f"permutation iterations must be an integer >= 1, got {iterations!r}")
    observed = additive_two_way_anova(values, factors)
    block = next(name for name in factors if name != factor)
    base: dict[str, Any] = {"factor": factor, "block": block, "F": None,
                            "df_effect": observed["factors"][factor]["df"],
                            "df_residual": observed["df_residual"], "p": None, "n_at_least_as_extreme": None,
                            "iterations": int(iterations),
                            "method": f"values permuted within levels of {block!r}; statistic = type II F"}
    f_obs = observed["factors"][factor]["F"]
    if f_obs is None or not np.isfinite(f_obs):
        base["note"] = observed.get("note", "observed F is undefined") if f_obs is None else \
            "observed F diverges (zero residual variation); the permutation p is undefined"
        return base

    y = np.asarray(values, dtype=float)
    codes, _ = _codes(factors, y.size)
    rng = np.random.default_rng(seed)
    permuted = np.broadcast_to(y, (int(iterations), y.size)).copy()
    for level in dict.fromkeys(codes[block].tolist()):
        idx = np.flatnonzero(codes[block] == level)
        order = rng.permuted(np.broadcast_to(np.arange(idx.size), (int(iterations), idx.size)), axis=1)
        permuted[:, idx] = y[idx][order]
    with np.errstate(divide="ignore", invalid="ignore"):
        f_perm = _additive_fit(permuted, codes)[factor]["F"]
    # A permutation with zero residual variation has an infinite F, which is at least as
    # extreme as any finite observed F; NaN cannot arise (ss_resid >= 0, df_resid > 0).
    extreme = int(np.sum(f_perm >= f_obs * (1.0 - _F_TIE_TOLERANCE)))
    base.update({"F": float(f_obs), "p": (1 + extreme) / (int(iterations) + 1),
                 "n_at_least_as_extreme": extreme})
    return base

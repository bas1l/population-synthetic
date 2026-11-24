"""Model vs strategy: weight and significance on closeness of typicality to SCB (swedish_02).

Scratch analysis. Unit = combination (model x strategy), n = 58 (60 cells, 2 withdrawn at the
population cap: DeepSeek-R1 14B / E, Gemma4 E4B / E). PRIMARY per-individual typicality = the FIRST judge
round (integer 0-10; manuscript precedent); the mean over rounds (pipeline default, differs only
where a second round exists) is a sensitivity basis. can_exist-majority survivors only; same load
as ../effects.py.

Outcomes per combination (all computed from the 21-bin 0.5-grid histograms):
  delta : Cliff's delta(combination vs SCB) = P(X>Y) - P(X<Y)            (primary)
  le4   : SCB share(typicality <= 4) - combination share(<= 4)
  cdf   : mean |F_comb(c) - F_SCB(c)| over the continuum [0, 10] = W1 / 10
Writes CSVs + results inputs here only.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from population_synthetic.analysis.method_significance.builder import (
    _orthogonal_contrasts, _polynomial_contrast,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.labels import method_letters, model_labels
from population_synthetic.analysis.utils.stats_tests import (
    friedman_test, holm_adjust, nemenyi_pairwise, nemenyi_posthoc, page_trend_test,
    paired_t_pairwise, rm_anova_within,
)

HERE = Path(__file__).resolve().parent
UP = HERE.parent
BASE = Path("<project-data>/02_Data")
meta = json.load(open(UP / "meta.json"))
SEED = 20260921
B = 5000          # bootstrap replicates
P = 10000         # permutations
NBIN = 21         # 0, 0.5, ..., 10

# ---------------------------------------------------------------- load (as ../effects.py)
df = pd.concat([pd.read_csv(f) for f in meta["files"]], ignore_index=True)
df["first"] = df.typicality_rounds.astype(str).str.split("|").map(
    lambda x: float(x[0]) if x[0] not in ("", "nan") else np.nan)
surv = df[df.can_exist_majority == True]  # noqa: E712
syn = surv[surv.is_real_reference == False].copy()  # noqa: E712
real = surv[surv.is_real_reference == True].copy()  # noqa: E712
assert len(syn) == meta["n_syn"] == 5760 and len(real) == meta["n_real"] == 100

MODELS = meta["model_order"]                       # model_ranking order
STRATS = strategy_complexity_order(meta["strategies"])
LETTER = method_letters(STRATS)
assert STRATS == meta["strategies"] and LETTER == meta["letters"]
MLAB = model_labels(MODELS)

cap = json.load(open(BASE / "03_Analysis/population_cap/_index.json"))
excluded = {e["slug"] for e in cap if e["excluded"]}


def hist(values) -> np.ndarray:
    v = np.asarray(values, float) * 2
    assert np.allclose(v, np.round(v)) and v.min() >= 0 and v.max() <= 20
    return np.bincount(np.round(v).astype(int), minlength=NBIN)


cells, withdrawn = [], []
for m in MODELS:
    for s in STRATS:
        sub = syn[(syn.model == m) & (syn.strategy == s)]
        if f"swedish_02_{s}_{m}" in excluded:
            assert sub.empty
            withdrawn.append((m, s))
            continue
        assert not sub.empty
        cells.append(dict(model=m, strategy=s, method=LETTER[s], n=len(sub),
                          h=hist(sub.typicality_mean), h1=hist(sub["first"])))
assert len(cells) == 58 and sorted(withdrawn) == sorted(
    [("ollama_deepseek_r1_14b", STRATS[-1]), ("ollama_gemma4_e4b", STRATS[-1])]), withdrawn
C = pd.DataFrame([{k: v for k, v in c.items() if k not in ("h", "h1")} for c in cells])
HC = np.stack([c["h"] for c in cells])        # (58, 21)
HC1 = np.stack([c["h1"] for c in cells])
HS = hist(real.typicality_mean)
HS1 = hist(real["first"])
mi = C.model.map({m: i for i, m in enumerate(MODELS)}).to_numpy()
si = C.strategy.map({s: j for j, s in enumerate(STRATS)}).to_numpy()
N = len(C)

# ---------------------------------------------------------------- outcomes
SIGN = np.sign(np.arange(NBIN)[:, None] - np.arange(NBIN)[None, :])
LE4 = np.arange(NBIN) <= 8          # typicality <= 4.0


def outcomes(hc, hs) -> dict[str, np.ndarray]:
    """hc (..., 58, 21) counts, hs (..., 21) counts -> dict of (..., 58) outcomes."""
    pc = hc / hc.sum(-1, keepdims=True)
    ps = (hs / hs.sum(-1, keepdims=True))[..., None, :]
    delta = np.einsum("...ci,ij,...cj->...c", pc, SIGN, np.broadcast_to(ps, pc.shape))
    le4 = (ps * LE4).sum(-1) - (pc * LE4).sum(-1)
    # F on the 20 cut points between grid values; each step is 0.5 wide on [0, 10] -> W1;
    # divide by the range 10 -> mean CDF gap over the continuum.
    cdf = np.abs(np.cumsum(pc, -1) - np.cumsum(ps, -1))[..., :-1].sum(-1) * 0.5 / 10.0
    return dict(delta=delta, le4=le4, cdf=cdf)


OUTS = ("delta", "le4", "cdf")
obs = outcomes(HC1, HS1)        # PRIMARY: first round
obs1 = outcomes(HC, HS)         # sensitivity: mean over rounds
for k in OUTS:
    C[k] = obs[k]
    C[k + "_meanrounds"] = obs1[k]
# cross-check delta against ../combo_vs_scb.csv
prev = pd.read_csv(UP / "combo_vs_scb.csv").set_index(["model", "strategy"])
chk = prev.loc[list(zip(C.model, C.strategy)), "delta_vs_scb_r1"].to_numpy()
assert np.allclose(chk, C.delta, atol=1e-12)
assert (C.delta > 0).all()
SCB_LE4 = float((HS1 / HS1.sum() * LE4).sum())

# ---------------------------------------------------------------- additive two-way decomposition
def onehot(idx, k, drop_first=True):
    X = np.eye(k)[idx]
    return X[:, 1:] if drop_first else X


one = np.ones((N, 1))
XM, XS = onehot(mi, len(MODELS)), onehot(si, len(STRATS))
DESIGNS = {"null": one, "model": np.hstack([one, XM]), "strategy": np.hstack([one, XS]),
           "full": np.hstack([one, XM, XS])}


def resid_maker(X):
    return np.eye(N) - X @ np.linalg.pinv(X)


RM = {k: resid_maker(X) for k, X in DESIGNS.items()}
RANK = {k: np.linalg.matrix_rank(X) for k, X in DESIGNS.items()}
DF_M, DF_S = RANK["full"] - RANK["strategy"], RANK["full"] - RANK["model"]
DF_R = N - RANK["full"]
assert (DF_M, DF_S, DF_R) == (11, 4, 42)


def rss(y, k):
    """y (..., N) -> residual SS under design k."""
    return np.einsum("...i,ij,...j->...", y, RM[k], y)


def decompose(y) -> dict[str, np.ndarray]:
    """Type II (= type III, no interaction term) SS and effect sizes; vectorised over leading dims."""
    r_full, r_m, r_s, r_0 = rss(y, "full"), rss(y, "model"), rss(y, "strategy"), rss(y, "null")
    ss_m = r_s - r_full          # model | strategy
    ss_s = r_m - r_full          # strategy | model
    ms_r = r_full / DF_R
    out = dict(ss_total=r_0, ss_model=ss_m, ss_strategy=ss_s, ss_resid=r_full,
               ss_model_typeI_first=r_0 - r_m, ss_strategy_typeI_first=r_0 - r_s,
               F_model=(ss_m / DF_M) / ms_r, F_strategy=(ss_s / DF_S) / ms_r)
    for f, ss, d in (("model", ss_m, DF_M), ("strategy", ss_s, DF_S)):
        out[f"peta2_{f}"] = ss / (ss + r_full)
        out[f"pomega2_{f}"] = (ss - d * ms_r) / (ss + (N - d) * ms_r)
        out[f"omega2_{f}"] = (ss - d * ms_r) / (r_0 + ms_r)
        out[f"share_{f}"] = ss / r_0
    out["share_resid"] = r_full / r_0
    out["share_overlap"] = 1 - out["share_model"] - out["share_strategy"] - out["share_resid"]
    out["ratio_ss_strategy_over_model"] = ss_s / ss_m
    out["ratio_pomega2_strategy_minus_model"] = out["pomega2_strategy"] - out["pomega2_model"]
    return out


# least-squares (estimated marginal) means from the additive fit
def ls_means(y) -> tuple[np.ndarray, np.ndarray]:
    """y (..., N) -> strategy LS means (..., 5) averaged over all 12 models, model LS means (..., 12)."""
    Xf = np.hstack([one, onehot(mi, len(MODELS)), onehot(si, len(STRATS))])
    beta = y @ np.linalg.pinv(Xf).T                       # (..., 16)
    a = np.concatenate([np.zeros(y.shape[:-1] + (1,)), beta[..., 1:12]], -1)   # model effects
    b = np.concatenate([np.zeros(y.shape[:-1] + (1,)), beta[..., 12:]], -1)    # strategy effects
    mu = beta[..., :1]
    return mu + a.mean(-1, keepdims=True) + b, mu + b.mean(-1, keepdims=True) + a


# ---------------------------------------------------------------- bootstrap (individuals)
def draw(h, size, rng):
    return rng.multinomial(h.sum(), h / h.sum(), size=size)


def boot_outcomes(rng, resample_combos=True, resample_scb=True, hc=HC1, hs=HS1):
    bc = (np.stack([draw(h, B, rng) for h in hc], axis=1) if resample_combos
          else np.broadcast_to(hc, (B,) + hc.shape))
    bs = draw(hs, B, rng) if resample_scb else np.broadcast_to(hs, (B, NBIN))
    return outcomes(bc, bs)


rng = np.random.default_rng(SEED)
BOOT = {"joint": boot_outcomes(rng),
        "combos_only": boot_outcomes(rng, resample_scb=False),
        "scb_only": boot_outcomes(rng, resample_combos=False)}


def ci(x):
    lo, hi = np.percentile(x, [2.5, 97.5], axis=0)
    return lo, hi


rows = []
for basis, o in (("first_round", obs), ("mean_over_rounds", obs1)):
    for k in OUTS:
        d = decompose(o[k])
        bd = {name: decompose(bo[k]) for name, bo in BOOT.items()} if basis == "first_round" else {}
        for stat, v in d.items():
            r = dict(basis=basis, outcome=k, stat=stat, estimate=float(v))
            for name, bdd in bd.items():
                lo, hi = ci(bdd[stat])
                r[f"ci_lo_{name}"], r[f"ci_hi_{name}"] = float(lo), float(hi)
            if bd:
                r["boot_mean_joint"] = float(np.mean(bd["joint"][stat]))
            rows.append(r)
DEC = pd.DataFrame(rows)
DEC.to_csv(HERE / "decomposition.csv", index=False)

# parametric F p (reference only)
for k in OUTS:
    d = decompose(obs[k])
    for f, dfe in (("model", DF_M), ("strategy", DF_S)):
        DEC.loc[(DEC.basis == "first_round") & (DEC.outcome == k) & (DEC.stat == f"F_{f}"),
                "p_parametric"] = float(stats.f.sf(d[f"F_{f}"], dfe, DF_R))
DEC.to_csv(HERE / "decomposition.csv", index=False)

# ---------------------------------------------------------------- permutation tests
def perm_within(y, blocks, rng, P):
    """(P, N) array: y permuted within each level of *blocks*."""
    out = np.broadcast_to(y, (P, N)).copy()
    for b in np.unique(blocks):
        idx = np.flatnonzero(blocks == b)
        order = rng.permuted(np.broadcast_to(np.arange(len(idx)), (P, len(idx))), axis=1)
        out[:, idx] = y[idx][order]
    return out


prng = np.random.default_rng(SEED + 7)
PERM = []
for basis, o in (("first_round", obs), ("mean_over_rounds", obs1)):
    for k in OUTS:
        y = o[k]
        d = decompose(y)
        ys = perm_within(y, mi, prng, P)      # strategy labels permuted within model blocks
        ym = perm_within(y, si, prng, P)      # model labels permuted within strategy blocks
        Fs = decompose(ys)["F_strategy"]
        Fm = decompose(ym)["F_model"]
        PERM.append(dict(basis=basis, outcome=k,
                         F_strategy=float(d["F_strategy"]),
                         p_perm_strategy=float((1 + (Fs >= d["F_strategy"] - 1e-12).sum()) / (P + 1)),
                         F_model=float(d["F_model"]),
                         p_perm_model=float((1 + (Fm >= d["F_model"] - 1e-12).sum()) / (P + 1)),
                         p_F_strategy=float(stats.f.sf(d["F_strategy"], DF_S, DF_R)),
                         p_F_model=float(stats.f.sf(d["F_model"], DF_M, DF_R)),
                         n_perm=P))
PERM = pd.DataFrame(PERM)
PERM.to_csv(HERE / "permutation_tests.csv", index=False)

# ---------------------------------------------------------------- complete-block rank tests
COMPLETE = [m for m in MODELS if C[C.model == m].shape[0] == len(STRATS)]
assert len(COMPLETE) == 10
BLOCK = {}
POST = []
for k in OUTS:
    grid = C.pivot(index="model", columns="strategy", values=k).loc[COMPLETE, STRATS].to_numpy()
    fr_s = friedman_test(grid)                  # blocks = models, treatments = strategies
    fr_m = friedman_test(grid.T)                # blocks = strategies, treatments = models
    page = page_trend_test(grid, list(range(len(STRATS))))
    page["p_two_sided"] = float(2 * min(page["p"], 1 - page["p"]))
    lin, quad = _orthogonal_contrasts(len(STRATS))
    rm = rm_anova_within(grid)
    rm_m = rm_anova_within(grid.T)
    ne_s = nemenyi_posthoc(grid)
    ne_m = nemenyi_posthoc(grid.T)
    BLOCK[k] = dict(
        n_blocks_models=len(COMPLETE), dropped_models=[m for m in MODELS if m not in COMPLETE],
        friedman_strategy=fr_s, friedman_model=fr_m, page_strategy_simplest_first=page,
        linear_contrast=_polynomial_contrast(grid, lin), quadratic_contrast=_polynomial_contrast(grid, quad),
        rm_anova_strategy=rm, rm_anova_model=rm_m,
        nemenyi_cd_strategy=ne_s["cd"], nemenyi_cd_model=ne_m["cd"],
        avg_rank_strategy=dict(zip([LETTER[s] for s in STRATS],
                                   np.mean([stats.rankdata(r) for r in grid], 0).tolist())),
        avg_rank_model=dict(zip(COMPLETE, np.mean([stats.rankdata(r) for r in grid.T], 0).tolist())),
    )
    # bootstrap CIs for Kendall's W (joint individual-level resampling, same replicates as above)
    cols = {(m, s): i for i, (m, s) in enumerate(zip(C.model, C.strategy))}
    idx = np.array([[cols[(m, s)] for s in STRATS] for m in COMPLETE])
    bg = BOOT["joint"][k][:, idx]                                  # (B, 10, 5)

    def kendall_w(g3, blocks_axis, treat_axis):
        """Kendall's W = tie-corrected Friedman chi2 / (n (k-1)), as friedman_test reports it.

        g3 (..., 10, 5); blocks_axis / treat_axis index the last two axes.
        """
        g3 = np.moveaxis(np.asarray(g3, float), (blocks_axis, treat_axis), (-2, -1))
        r = stats.rankdata(g3, axis=-1)
        n, kk = g3.shape[-2], g3.shape[-1]
        Rj = r.sum(axis=-2)
        chi2 = 12.0 / (n * kk * (kk + 1)) * (Rj ** 2).sum(-1) - 3.0 * n * (kk + 1)
        srt = np.sort(g3, axis=-1)
        ties = np.zeros(g3.shape[:-1])
        run = np.ones(g3.shape[:-1])
        for j in range(1, kk):                       # tie-run lengths along the treatment axis
            same = srt[..., j] == srt[..., j - 1]          # exact, as scipy.stats.rankdata
            ties += np.where(same, 0.0, run ** 3 - run)
            run = np.where(same, run + 1, 1.0)
        ties += run ** 3 - run
        corr = 1.0 - ties.sum(-1) / (n * (kk ** 3 - kk))
        return chi2 / corr / (n * (kk - 1))
    BLOCK[k]["kendall_w_strategy_ci"] = [float(x) for x in ci(kendall_w(bg, -2, -1))]
    BLOCK[k]["kendall_w_model_ci"] = [float(x) for x in ci(kendall_w(bg, -1, -2))]
    BLOCK[k]["kendall_w_strategy_point_check"] = float(kendall_w(grid, 0, 1))
    BLOCK[k]["kendall_w_model_point_check"] = float(kendall_w(grid, 1, 0))
    import scikit_posthocs as sp
    for fac, g, labs in (("strategy", grid, [LETTER[s] for s in STRATS]), ("model", grid.T, COMPLETE)):
        pn = np.asarray(nemenyi_pairwise(g, labels=labs)["p_matrix"])
        pc = sp.posthoc_conover_friedman(g, p_adjust="holm").to_numpy()
        pc_raw = sp.posthoc_conover_friedman(g).to_numpy()
        pt = ({tuple(key.split("|")): r for key, r in
               paired_t_pairwise(g, labels=labs, confidence_level=0.95)["pairs"].items()}
              if fac == "strategy" else {})
        for i, j in combinations(range(len(labs)), 2):
            diff = g[:, j] - g[:, i]
            wins = int((diff > 0).sum())
            r = dict(outcome=k, factor=fac, a=labs[i], b=labs[j],
                     mean_b_minus_a=float(diff.mean()), median_b_minus_a=float(np.median(diff)),
                     b_higher_in_blocks=wins, n_blocks=len(diff),
                     p_nemenyi=float(pn[i, j]), p_conover_raw=float(pc_raw[i, j]),
                     p_conover_holm=float(pc[i, j]))
            t = pt.get((labs[i], labs[j]))
            if t:
                r.update(p_paired_t_holm=t.get("p_holm"), p_sign=t.get("p_sign"), dz=t.get("dz"))
            POST.append(r)
POST = pd.DataFrame(POST)
POST.to_csv(HERE / "posthoc_pairs.csv", index=False)
json.dump(BLOCK, open(HERE / "complete_block_tests.json", "w"), indent=1, default=float)

# ---------------------------------------------------------------- LS means with CIs (delta, figure)
MEANS = []
for k in OUTS:
    sm, mm = ls_means(obs[k])
    bsm, bmm = ls_means(BOOT["joint"][k])
    slo, shi = ci(bsm)
    mlo, mhi = ci(bmm)
    raw_s = C.groupby("strategy")[k].mean()
    raw_m = C.groupby("model")[k].mean()
    for j, s in enumerate(STRATS):
        MEANS.append(dict(outcome=k, factor="strategy", level=s, label=LETTER[s], ls_mean=sm[j],
                          ci_lo=slo[j], ci_hi=shi[j], raw_mean=raw_s[s], n_cells=int((C.strategy == s).sum())))
    for i, m in enumerate(MODELS):
        MEANS.append(dict(outcome=k, factor="model", level=m, label=MLAB[m], ls_mean=mm[i],
                          ci_lo=mlo[i], ci_hi=mhi[i], raw_mean=raw_m[m], n_cells=int((C.model == m).sum())))
MEANS = pd.DataFrame(MEANS)
MEANS.to_csv(HERE / "ls_means.csv", index=False)

# per-combination outcomes (with individual-level bootstrap CIs, joint)
for k in OUTS:
    lo, hi = ci(BOOT["joint"][k])
    C[k + "_ci_lo"], C[k + "_ci_hi"] = lo, hi
C["model_label"] = C.model.map(MLAB)
C.to_csv(HERE / "combination_outcomes.csv", index=False)

# ---------------------------------------------------------------- sensitivity: drop the judge's own model
SENS = []
keep = C.model != "claude_sonnet"
for k in OUTS:
    y = obs[k][keep.to_numpy()]
    m2 = C.model[keep].map({m: i for i, m in enumerate([x for x in MODELS if x != "claude_sonnet"])}).to_numpy()
    s2 = si[keep.to_numpy()]
    n2 = len(y)
    o2 = np.ones((n2, 1))
    Xf = np.hstack([o2, onehot(m2, 11), onehot(s2, 5)])
    Xm = np.hstack([o2, onehot(m2, 11)])
    Xs = np.hstack([o2, onehot(s2, 5)])

    def r(X):
        e = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
        return float(e @ e)
    rf, rm_, rs_ = r(Xf), r(Xm), r(Xs)
    dfr = n2 - np.linalg.matrix_rank(Xf)
    msr = rf / dfr
    ssm, sss = rs_ - rf, rm_ - rf
    SENS.append(dict(outcome=k, n=n2, pomega2_model=(ssm - 10 * msr) / (ssm + (n2 - 10) * msr),
                     pomega2_strategy=(sss - 4 * msr) / (sss + (n2 - 4) * msr),
                     peta2_model=ssm / (ssm + rf), peta2_strategy=sss / (sss + rf)))
pd.DataFrame(SENS).to_csv(HERE / "sensitivity_without_claude_sonnet.csv", index=False)

json.dump(dict(scb_share_le4=SCB_LE4, n_boot=B, n_perm=P, seed=SEED, complete_models=COMPLETE,
               withdrawn=withdrawn, df=dict(model=DF_M, strategy=DF_S, resid=DF_R),
               outcome_corr_spearman={f"{a}~{b}": float(stats.spearmanr(C[a], C[b])[0])
                                      for a, b in combinations(OUTS, 2)}),
          open(HERE / "closeness_meta.json", "w"), indent=1, default=float)

pd.set_option("display.width", 250)
print(DEC[(DEC.basis == "first_round") & DEC.stat.isin(
    ["peta2_model", "peta2_strategy", "pomega2_model", "pomega2_strategy", "share_model", "share_strategy",
     "share_resid", "share_overlap", "F_model", "F_strategy", "omega2_model", "omega2_strategy"])].round(3).to_string())
print(PERM.to_string())
print(json.dumps(BLOCK, indent=1, default=float)[:6000])
print(POST[POST.factor == "strategy"].round(4).to_string())
print(MEANS.round(3).to_string())
print(pd.DataFrame(SENS).round(3))
print("SCB le4", SCB_LE4)

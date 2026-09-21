"""Model vs strategy on closeness to SCB, with closeness measured as a distribution-SHAPE distance.

Scratch. Same data, unit (58 combinations), basis (first judge round, integer 0-10, can_exist-majority
survivors), decomposition, bootstrap, permutation and complete-block machinery as ../closeness/closeness.py
(logic copied, not imported, because importing that module re-runs it and rewrites its outputs).

Outcomes (11-bin histograms of integer first-round scores; p = combination, q = SCB):
  tv     : total variation      0.5 * sum |p - q|                          (nominal; order-blind)
  js     : Jensen-Shannon DISTANCE sqrt(JSD), base 2, in [0, 1]           (nominal; order-blind)
  cramer : L2 CDF distance      sqrt( sum_{c=0..9} (F_p(c) - F_q(c))^2 )   (order-aware)
  delta  : Cliff's delta        P(X>Y) - P(X<Y)                            (location; reference)
Null floor: two independent n-draws from SCB's empirical distribution, distance between them.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import scikit_posthocs as sp
from scipy import stats

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.labels import method_letters, model_labels
from population_synthetic.analysis.utils.stats_tests import friedman_test, paired_t_pairwise

HERE = Path(__file__).resolve().parent
UP = HERE.parent
BASE = Path("<project-data>/02_Data")
meta = json.load(open(UP / "meta.json"))
SEED = 20260921
B, P, NB = 5000, 10000, 11

df = pd.concat([pd.read_csv(f) for f in meta["files"]], ignore_index=True)
df["first"] = df.typicality_rounds.astype(str).str.split("|").map(
    lambda x: float(x[0]) if x[0] not in ("", "nan") else np.nan)
surv = df[df.can_exist_majority == True]  # noqa: E712
assert surv["first"].notna().all() and np.allclose(surv["first"], surv["first"].round())
syn = surv[surv.is_real_reference == False]  # noqa: E712
real = surv[surv.is_real_reference == True]  # noqa: E712
assert len(syn) == 5760 and len(real) == 100

MODELS = meta["model_order"]
STRATS = strategy_complexity_order(meta["strategies"])
LETTER = method_letters(STRATS)
MLAB = model_labels(MODELS)
excluded = {e["slug"] for e in json.load(open(BASE / "03_Analysis/population_cap/_index.json")) if e["excluded"]}


def hist(v):
    return np.bincount(np.asarray(v, int), minlength=NB)


cells = []
for m in MODELS:
    for s in STRATS:
        sub = syn[(syn.model == m) & (syn.strategy == s)]
        if f"swedish_02_{s}_{m}" in excluded:
            assert sub.empty
            continue
        cells.append(dict(model=m, strategy=s, method=LETTER[s], n=len(sub), h=hist(sub["first"])))
assert len(cells) == 58
C = pd.DataFrame([{k: v for k, v in c.items() if k != "h"} for c in cells])
HC = np.stack([c["h"] for c in cells])
HS = hist(real["first"])
mi = C.model.map({m: i for i, m in enumerate(MODELS)}).to_numpy()
si = C.strategy.map({s: j for j, s in enumerate(STRATS)}).to_numpy()
N = len(C)

SIGN = np.sign(np.arange(NB)[:, None] - np.arange(NB)[None, :])


def outcomes(hc, hs):
    """hc (..., c, 11), hs (..., 11) counts -> dict of (..., c)."""
    pc = hc / hc.sum(-1, keepdims=True)
    ps = np.broadcast_to((hs / hs.sum(-1, keepdims=True))[..., None, :], pc.shape)
    tv = 0.5 * np.abs(pc - ps).sum(-1)
    mix = 0.5 * (pc + ps)
    with np.errstate(divide="ignore", invalid="ignore"):
        kl = lambda a: np.where(a > 0, a * np.log2(a / mix), 0.0).sum(-1)  # noqa: E731
        jsd = 0.5 * kl(pc) + 0.5 * kl(ps)
    js = np.sqrt(np.clip(jsd, 0, None))
    cramer = np.sqrt(((np.cumsum(pc, -1) - np.cumsum(ps, -1))[..., :-1] ** 2).sum(-1))
    delta = np.einsum("...ci,ij,...cj->...c", pc, SIGN, ps)
    return dict(tv=tv, js=js, cramer=cramer, delta=delta)


OUTS = ("tv", "js", "cramer", "delta")
obs = outcomes(HC, HS)
for k in OUTS:
    C[k] = obs[k]
# cross-checks: delta vs stored closeness outcome; tv/js vs scipy on one cell
prev = pd.read_csv(UP / "closeness/combination_outcomes.csv").set_index(["model", "strategy"])
assert np.allclose(prev.loc[list(zip(C.model, C.strategy)), "delta"].to_numpy(), C.delta, atol=1e-12)
from scipy.spatial.distance import jensenshannon  # noqa: E402
assert np.isclose(jensenshannon(HC[0] / HC[0].sum(), HS / 100, base=2), C.js[0])

# ---------------------------------------------------------------- null floor (SCB vs itself)
rng0 = np.random.default_rng(SEED + 99)
R = 20000
qS = HS / HS.sum()
NULL = {}
for n_a in (100, int(C.n.min()), int(round(C.n.mean()))):
    a = rng0.multinomial(n_a, qS, size=R)
    b = rng0.multinomial(100, qS, size=R)
    o = outcomes(a[:, None, :], b)
    NULL[f"{n_a}_vs_100"] = {k: dict(mean=float(o[k].mean()), median=float(np.median(o[k])),
                                     q95=float(np.percentile(o[k], 95)),
                                     mean_abs=float(np.abs(o[k]).mean())) for k in OUTS}
# closeness floor for each combination given its own n (null mean at n_c vs 100)
floor_by_n = {}
for n_a in sorted(C.n.unique()):
    a = rng0.multinomial(n_a, qS, size=5000)
    b = rng0.multinomial(100, qS, size=5000)
    o = outcomes(a[:, None, :], b)
    floor_by_n[int(n_a)] = {k: float(np.abs(o[k]).mean()) for k in OUTS}
for k in OUTS:
    C[k + "_null_mean"] = C.n.map(lambda n: floor_by_n[int(n)][k])
    C[k + "_over_floor"] = C[k].abs() / C[k + "_null_mean"]

# ---------------------------------------------------------------- additive two-way decomposition
def onehot(idx, k):
    return np.eye(k)[idx][:, 1:]


one = np.ones((N, 1))
XM, XS = onehot(mi, len(MODELS)), onehot(si, len(STRATS))
DES = {"null": one, "model": np.hstack([one, XM]), "strategy": np.hstack([one, XS]),
       "full": np.hstack([one, XM, XS])}
RM = {k: np.eye(N) - X @ np.linalg.pinv(X) for k, X in DES.items()}
RK = {k: np.linalg.matrix_rank(X) for k, X in DES.items()}
DF_M, DF_S, DF_R = RK["full"] - RK["strategy"], RK["full"] - RK["model"], N - RK["full"]
assert (DF_M, DF_S, DF_R) == (11, 4, 42)


def rss(y, k):
    return np.einsum("...i,ij,...j->...", y, RM[k], y)


def decompose(y):
    rf, rm, rs, r0 = rss(y, "full"), rss(y, "model"), rss(y, "strategy"), rss(y, "null")
    ssm, sss, msr = rs - rf, rm - rf, rf / DF_R
    o = dict(share_strategy=sss / r0, share_model=ssm / r0, share_resid=rf / r0,
             F_strategy=(sss / DF_S) / msr, F_model=(ssm / DF_M) / msr)
    for f, ss, d in (("strategy", sss, DF_S), ("model", ssm, DF_M)):
        o[f"peta2_{f}"] = ss / (ss + rf)
        o[f"pomega2_{f}"] = (ss - d * msr) / (ss + (N - d) * msr)
    o["share_overlap"] = 1 - o["share_strategy"] - o["share_model"] - o["share_resid"]
    o["ratio_ss_strategy_over_model"] = sss / ssm
    o["pomega2_diff_strategy_minus_model"] = o["pomega2_strategy"] - o["pomega2_model"]
    return o


def ls_means_strategy(y):
    Xf = DES["full"]
    beta = y @ np.linalg.pinv(Xf).T
    a = np.concatenate([np.zeros(y.shape[:-1] + (1,)), beta[..., 1:12]], -1)
    b = np.concatenate([np.zeros(y.shape[:-1] + (1,)), beta[..., 12:]], -1)
    return beta[..., :1] + a.mean(-1, keepdims=True) + b


rng = np.random.default_rng(SEED)
bc = np.stack([rng.multinomial(h.sum(), h / h.sum(), size=B) for h in HC], axis=1)
bs = rng.multinomial(100, qS, size=B)
BOOT = outcomes(bc, bs)


def ci(x):
    return np.percentile(x, [2.5, 97.5], axis=0)


DEC = []
for k in OUTS:
    d, bd = decompose(obs[k]), decompose(BOOT[k])
    for st, v in d.items():
        lo, hi = ci(bd[st])
        DEC.append(dict(outcome=k, stat=st, estimate=float(v), ci_lo=float(lo), ci_hi=float(hi),
                        boot_mean=float(np.mean(bd[st]))))
DEC = pd.DataFrame(DEC)
DEC.to_csv(HERE / "decomposition.csv", index=False)

# ---------------------------------------------------------------- permutation tests
def perm_within(y, blocks, rng, P):
    out = np.broadcast_to(y, (P, N)).copy()
    for b in np.unique(blocks):
        idx = np.flatnonzero(blocks == b)
        order = rng.permuted(np.broadcast_to(np.arange(len(idx)), (P, len(idx))), axis=1)
        out[:, idx] = y[idx][order]
    return out


prng = np.random.default_rng(SEED + 7)
PERM = []
for k in OUTS:
    y, d = obs[k], decompose(obs[k])
    Fs = decompose(perm_within(y, mi, prng, P))["F_strategy"]
    Fm = decompose(perm_within(y, si, prng, P))["F_model"]
    PERM.append(dict(outcome=k, F_strategy=float(d["F_strategy"]),
                     p_perm_strategy=float((1 + (Fs >= d["F_strategy"] - 1e-12).sum()) / (P + 1)),
                     F_model=float(d["F_model"]),
                     p_perm_model=float((1 + (Fm >= d["F_model"] - 1e-12).sum()) / (P + 1)),
                     p_F_strategy=float(stats.f.sf(d["F_strategy"], DF_S, DF_R)),
                     p_F_model=float(stats.f.sf(d["F_model"], DF_M, DF_R))))
PERM = pd.DataFrame(PERM)
PERM.to_csv(HERE / "permutation_tests.csv", index=False)

# ---------------------------------------------------------------- complete blocks
COMPLETE = [m for m in MODELS if (C.model == m).sum() == len(STRATS)]
assert len(COMPLETE) == 10
cols = {(m, s): i for i, (m, s) in enumerate(zip(C.model, C.strategy))}
IDX = np.array([[cols[(m, s)] for s in STRATS] for m in COMPLETE])


def kendall_w(g3, bax, tax):
    g3 = np.moveaxis(np.asarray(g3, float), (bax, tax), (-2, -1))
    r = stats.rankdata(g3, axis=-1)
    n, kk = g3.shape[-2], g3.shape[-1]
    chi2 = 12.0 / (n * kk * (kk + 1)) * (r.sum(-2) ** 2).sum(-1) - 3.0 * n * (kk + 1)
    srt = np.sort(g3, axis=-1)
    ties, run = np.zeros(g3.shape[:-1]), np.ones(g3.shape[:-1])
    for j in range(1, kk):
        same = srt[..., j] == srt[..., j - 1]
        ties += np.where(same, 0.0, run ** 3 - run)
        run = np.where(same, run + 1, 1.0)
    ties += run ** 3 - run
    return chi2 / (1.0 - ties.sum(-1) / (n * (kk ** 3 - kk))) / (n * (kk - 1))


BLOCK, POST = {}, []
labs = [LETTER[s] for s in STRATS]
for k in OUTS:
    grid = np.abs(obs[k][IDX])                 # (10, 5); |delta| = delta here (all > 0)
    fs, fm = friedman_test(grid), friedman_test(grid.T)
    bg = np.abs(BOOT[k][:, IDX])
    BLOCK[k] = dict(friedman_strategy=fs, friedman_model=fm,
                    W_strategy_ci=ci(kendall_w(bg, -2, -1)).tolist(),
                    W_model_ci=ci(kendall_w(bg, -1, -2)).tolist(),
                    avg_rank_strategy=dict(zip(labs, np.mean([stats.rankdata(r) for r in grid], 0).tolist())),
                    E_closer_than_D=int((grid[:, 4] < grid[:, 3]).sum()),
                    E_closest_of_5=int((grid.argmin(1) == 4).sum()))
    pc = sp.posthoc_conover_friedman(grid, p_adjust="holm").to_numpy()
    pt = {tuple(key.split("|")): r for key, r in
          paired_t_pairwise(grid, labels=labs, confidence_level=0.95)["pairs"].items()}
    for i, j in combinations(range(5), 2):
        diff = grid[:, j] - grid[:, i]
        t = pt[(labs[i], labs[j])]
        POST.append(dict(outcome=k, a=labs[i], b=labs[j], mean_b_minus_a=float(diff.mean()),
                         b_closer_in=int((diff < 0).sum()), a_closer_in=int((diff > 0).sum()),
                         p_paired_t_holm=t.get("p_holm"), dz=t.get("dz"), p_conover_holm=float(pc[i, j])))
POST = pd.DataFrame(POST)
POST.to_csv(HERE / "posthoc_pairs.csv", index=False)
json.dump(BLOCK, open(HERE / "complete_block_tests.json", "w"), indent=1, default=float)

# ---------------------------------------------------------------- strategy LS means + CIs
MEANS = []
for k in OUTS:
    sm, bsm = ls_means_strategy(obs[k]), ls_means_strategy(BOOT[k])
    lo, hi = ci(bsm)
    for j, s in enumerate(STRATS):
        MEANS.append(dict(outcome=k, method=LETTER[s], strategy=s, ls_mean=sm[j], ci_lo=lo[j], ci_hi=hi[j],
                          raw_mean=float(C[C.strategy == s][k].mean())))
MEANS = pd.DataFrame(MEANS)
MEANS.to_csv(HERE / "strategy_ls_means.csv", index=False)

for k in OUTS:
    lo, hi = ci(BOOT[k])
    C[k + "_ci_lo"], C[k + "_ci_hi"] = lo, hi
    C[k + "_rank"] = C[k].abs().rank(method="min").astype(int)   # 1 = closest
C["model_label"] = C.model.map(MLAB)
C.to_csv(HERE / "combination_outcomes.csv", index=False)
CORR = {f"{a}~{b}": float(stats.spearmanr(C[a], C[b])[0]) for a, b in combinations(OUTS, 2)}
json.dump(dict(null_floor=NULL, spearman=CORR, n_boot=B, n_perm=P, seed=SEED, complete_models=COMPLETE,
               n_range=[int(C.n.min()), int(C.n.max())]), open(HERE / "shape_meta.json", "w"), indent=1)

# ---------------------------------------------------------------- print
pd.set_option("display.width", 250)
print(json.dumps(NULL, indent=1))
print(DEC[DEC.stat.isin(["share_strategy", "share_model", "share_resid", "pomega2_strategy", "pomega2_model",
                         "pomega2_diff_strategy_minus_model", "ratio_ss_strategy_over_model",
                         "F_strategy", "F_model"])].round(3).to_string())
print(PERM.to_string())
for k in OUTS:
    b = BLOCK[k]
    print(k, "Fr strat chi2=%.2f p=%.2g W=%.3f %s | Fr model chi2=%.2f p=%.2g W=%.3f %s | ranks %s | E<D %d/10, E best %d/10" % (
        b["friedman_strategy"]["chi2"], b["friedman_strategy"]["p"], b["friedman_strategy"]["kendalls_w"],
        np.round(b["W_strategy_ci"], 2), b["friedman_model"]["chi2"], b["friedman_model"]["p"],
        b["friedman_model"]["kendalls_w"], np.round(b["W_model_ci"], 2),
        {x: round(v, 1) for x, v in b["avg_rank_strategy"].items()}, b["E_closer_than_D"], b["E_closest_of_5"]))
print(POST.round(4).to_string())
print(MEANS.round(3).to_string())
print(CORR)
for k in OUTS:
    srt = C.sort_values(k, key=abs)
    f = lambda r: f"{r.model_label}/{r.method} {r[k]:.3f} (x{r[k + '_over_floor']:.1f} floor)"  # noqa: E731
    print(k, "CLOSEST:", "; ".join(f(r) for _, r in srt.head(5).iterrows()))
    print(k, "FURTHEST:", "; ".join(f(r) for _, r in srt.tail(5).iterrows()))
    print(k, "min over-floor ratio", C[k + "_over_floor"].min().round(2),
          "n combos within null q95(100v100):", int((C[k].abs() <= NULL["100_vs_100"][k]["q95"]).sum()))

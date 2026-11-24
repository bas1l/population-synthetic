"""Typicality effect sizes + comparison to the SCB reference population (swedish_02).

Scratch analysis; reads persona_realism outputs, writes CSVs and figures here only.
Data: one value per persona = mean judge typicality over that persona's rounds
(pipeline default), can_exist-majority survivors only. Secondary basis: first round only
(equivalent to --rounds 1 on this data; see results.md).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from population_synthetic.analysis.utils.stats_tests import (
    kruskal_test, dunn_posthoc, cliffs_delta, holm_adjust,
)
from population_synthetic.analysis.model_ranking.charts import (
    _model_method_rows, _tier1_sort_key, _tier2_sort_key, _ordered_strategies,
)
from population_synthetic.analysis.utils.cap_index import load_cap_index
from population_synthetic.analysis.utils.labels import method_letters

OUT = Path(__file__).resolve().parent
BASE = Path("<project-data>/02_Data")
PR = BASE / "03_Analysis/persona_realism/swedish_02"
PERF = BASE / "03_Analysis/model_ranking/swedish_02_performance.json"
REAL = "real_swedish_02"
SEED = 20260921
B = 2000

# ---------------------------------------------------------------- load
files = sorted(glob.glob(str(PR / "*" / "*_personas.csv")))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
df["first"] = df.typicality_rounds.astype(str).str.split("|").map(
    lambda x: float(x[0]) if x[0] not in ("", "nan") else np.nan)
surv = df[df.can_exist_majority == True].copy()  # noqa: E712
syn = surv[surv.is_real_reference == False].copy()  # noqa: E712
real = surv[surv.is_real_reference == True].copy()  # noqa: E712
assert len(syn) == 5760 and len(real) == 100, (len(syn), len(real))
assert real.n_rounds_successful.eq(1).all()
# values live on a 0.5 grid (mean of 1 or 2 integer rounds) -> histogram on 21 bins
for c in ("typicality_mean", "first"):
    v = surv[c].to_numpy() * 2
    assert np.allclose(v, np.round(v)) and v.min() >= 0 and v.max() <= 20

perf = json.load(open(PERF))
strategies = _ordered_strategies(perf["metadata"]["strategies"])
rows = _model_method_rows(perf, load_cap_index(BASE), perf["metadata"]["models"], strategies)
MODEL_ORDER = [r.model for r in sorted([r for r in rows if r.tier == 1], key=_tier1_sort_key)
               + sorted([r for r in rows if r.tier == 2], key=_tier2_sort_key)]
assert set(MODEL_ORDER) == set(syn.model), (MODEL_ORDER, set(syn.model))
LETTERS = method_letters(strategies)
assert set(syn.strategy) == set(strategies)

# ---------------------------------------------------------------- helpers
SIGN = np.sign(np.arange(21)[:, None] - np.arange(21)[None, :])  # sign(i - j)


def hist(values) -> np.ndarray:
    idx = np.round(np.asarray(values, float) * 2).astype(int)
    return np.bincount(idx, minlength=21)


def delta_from_hist(ha, hb) -> np.ndarray:
    """Cliff's delta P(a>b)-P(a<b); ha/hb may be (21,) or (R,21) count arrays."""
    pa = ha / ha.sum(axis=-1, keepdims=True)
    pb = hb / hb.sum(axis=-1, keepdims=True)
    return np.einsum("...i,ij,...j->...", pa, SIGN, pb)


def boot_delta(a, b, rng) -> tuple[float, float, float]:
    """Point delta + percentile 95% CI, resampling units within each group.

    A with-replacement resample of n units from the empirical distribution is exactly a
    multinomial(n, p_hat) draw of its histogram, which is what is drawn here.
    """
    ha, hb = hist(a), hist(b)
    d = float(delta_from_hist(ha, hb))
    ra = rng.multinomial(ha.sum(), ha / ha.sum(), size=B)
    rb = rng.multinomial(hb.sum(), hb / hb.sum(), size=B)
    bd = delta_from_hist(ra, rb)
    lo, hi = np.percentile(bd, [2.5, 97.5])
    return d, float(lo), float(hi)


def eps2(H, n):
    return H * (n + 1) / (n ** 2 - 1)


def desc(v):
    v = np.asarray(v, float)
    return dict(n=len(v), median=float(np.median(v)), mean=float(v.mean()))


# ---------------------------------------------------------------- 1. omnibus
omni = []
for basis in ("typicality_mean", "first"):
    for factor in ("model", "strategy"):
        g = {k: v[basis].dropna().tolist() for k, v in sorted(syn.groupby(factor))}
        k = kruskal_test(g)
        d = dunn_posthoc(g)
        omni.append(dict(basis=basis, factor=factor, k=k["k"], N=k["n"], H=k["H"], p=k["p"],
                         epsilon2=eps2(k["H"], k["n"]),
                         dunn_pairs=len(d), dunn_holm_sig=sum(r["p_holm"] < 0.05 for r in d)))
omni = pd.DataFrame(omni)
omni.to_csv(OUT / "omnibus_kruskal_epsilon2.csv", index=False)
print(omni.to_string())

# ---------------------------------------------------------------- 2. pairwise models
rng = np.random.default_rng(SEED)
g = {m: syn.loc[syn.model == m, "typicality_mean"].to_numpy() for m in MODEL_ORDER}
dunn = {frozenset((r["a"], r["b"])): r for r in dunn_posthoc(
    {k: list(v) for k, v in sorted(g.items())})}
pw = []
for i, a in enumerate(MODEL_ORDER):
    for b in MODEL_ORDER[i + 1:]:
        d, lo, hi = boot_delta(g[a], g[b], rng)
        chk = cliffs_delta(g[a], g[b])["delta"]
        assert abs(chk - d) < 1e-9, (a, b, chk, d)
        r = dunn[frozenset((a, b))]
        z = r["z"] if r["a"] == a else -r["z"]  # orient z as a minus b
        pw.append(dict(model_a=a, model_b=b, n_a=len(g[a]), n_b=len(g[b]),
                       cliffs_delta=d, ci_lo=lo, ci_hi=hi, vd_A=(d + 1) / 2,
                       magnitude=cliffs_delta(g[a], g[b])["magnitude"],
                       dunn_z=z, p_raw=r["p_raw"], p_holm=r["p_holm"],
                       holm_sig=r["p_holm"] < 0.05))
pw = pd.DataFrame(pw)
pw.to_csv(OUT / "pairwise_models_cliffs_delta.csv", index=False)

# ---------------------------------------------------------------- 3. vs SCB
def vs_real(units: list[tuple[dict, pd.DataFrame]], rng) -> pd.DataFrame:
    out = []
    for key, sub in units:
        row = dict(key)
        for basis, sfx in (("typicality_mean", ""), ("first", "_r1")):
            a = sub[basis].to_numpy()
            ref = real[basis].to_numpy()
            dsc = desc(a)
            d, lo, hi = boot_delta(a, ref, rng)
            U, p = stats.mannwhitneyu(a, ref, alternative="two-sided", method="asymptotic")
            row.update({f"n{sfx}": dsc["n"], f"median{sfx}": dsc["median"], f"mean{sfx}": dsc["mean"],
                        f"delta_vs_scb{sfx}": d, f"ci_lo{sfx}": lo, f"ci_hi{sfx}": hi,
                        f"vd_A{sfx}": (d + 1) / 2, f"U{sfx}": float(U), f"p_mwu{sfx}": float(p)})
        out.append(row)
    t = pd.DataFrame(out)
    for sfx in ("", "_r1"):
        t[f"p_holm{sfx}"] = holm_adjust(t[f"p_mwu{sfx}"].tolist())
        t[f"holm_sig{sfx}"] = t[f"p_holm{sfx}"] < 0.05
    return t


combos = [(dict(model=m, strategy=s, method=LETTERS[s]), syn[(syn.model == m) & (syn.strategy == s)])
          for m in MODEL_ORDER for s in strategies
          if ((syn.model == m) & (syn.strategy == s)).any()]
vc = vs_real(combos, np.random.default_rng(SEED + 1))
vm = vs_real([(dict(model=m), syn[syn.model == m]) for m in MODEL_ORDER], np.random.default_rng(SEED + 2))
vc.to_csv(OUT / "combo_vs_scb.csv", index=False)
vm.to_csv(OUT / "model_vs_scb.csv", index=False)
scb = {b: desc(real[b]) for b in ("typicality_mean", "first")}
pd.DataFrame([dict(basis=b, **v) for b, v in scb.items()]).to_csv(OUT / "scb_reference.csv", index=False)

# distributions for figure c (first-round integer scores; SCB is single-round)
dist = []
for m in MODEL_ORDER:
    h = hist(syn.loc[syn.model == m, "first"])[::2]
    dist.append(dict(unit=m, n=int(h.sum()), **{f"p{k}": h[k] / h.sum() for k in range(11)}))
h = hist(real["first"])[::2]
dist.append(dict(unit=REAL, n=int(h.sum()), **{f"p{k}": h[k] / h.sum() for k in range(11)}))
assert all(abs(sum(r[f"p{k}"] for k in range(11)) - 1) < 1e-12 for r in dist)
pd.DataFrame(dist).to_csv(OUT / "distribution_first_round_by_model.csv", index=False)

json.dump(dict(model_order=MODEL_ORDER, strategies=strategies, letters=LETTERS,
               files=files, n_syn=len(syn), n_real=len(real),
               n_syn_two_rounds=int((syn.n_rounds_successful == 2).sum()),
               excluded_can_exist_false=int((df.can_exist_majority == False).sum()),  # noqa: E712
               scb=scb, seed=SEED, B=B), open(OUT / "meta.json", "w"), indent=1)
print(vm.to_string())
print(vc[["model", "method", "n", "median", "mean", "delta_vs_scb", "ci_lo", "ci_hi", "p_holm",
          "delta_vs_scb_r1", "p_holm_r1"]].to_string())
print(pw.sort_values("cliffs_delta", key=abs, ascending=False).head(10).to_string())
print("SCB", scb)

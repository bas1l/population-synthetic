"""Individual-level cross-check: cumulative-link (proportional-odds logit) model of first-round
typicality on the 5,760 synthetic individuals, model + strategy fixed effects.

Also re-checks the combination-level type II table against statsmodels.anova_lm.
Writes clm_lr_tests.csv, clm_predicted_vs_observed.csv, anova_lm_check.csv.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.anova import anova_lm

HERE = Path(__file__).resolve().parent
meta = json.load(open(HERE.parent / "meta.json"))

# ---- combination-level check
COMB = pd.read_csv(HERE / "combination_outcomes.csv")
chk = []
for k in ("delta", "le4", "cdf"):
    fit = smf.ols(f"{k} ~ C(model, Sum) + C(strategy, Sum)", data=COMB).fit()
    a2 = anova_lm(fit, typ=2)
    a3 = anova_lm(fit, typ=3)
    for typ, a in (("II", a2), ("III", a3)):
        for term in ("C(model, Sum)", "C(strategy, Sum)", "Residual"):
            chk.append(dict(outcome=k, typ=typ, term=term, ss=a.loc[term, "sum_sq"],
                            df=a.loc[term, "df"], F=a.loc[term].get("F"), p=a.loc[term].get("PR(>F)")))
pd.DataFrame(chk).to_csv(HERE / "anova_lm_check.csv", index=False)
print(pd.DataFrame(chk).to_string())

# ---- individual level
df = pd.concat([pd.read_csv(f) for f in meta["files"]], ignore_index=True)
df["first"] = df.typicality_rounds.astype(str).str.split("|").map(
    lambda x: float(x[0]) if x[0] not in ("", "nan") else np.nan)
surv = df[df.can_exist_majority == True]  # noqa: E712
syn = surv[surv.is_real_reference == False].copy()  # noqa: E712
real = surv[surv.is_real_reference == True].copy()  # noqa: E712
assert len(syn) == 5760
y = syn["first"].astype(int)
levels = sorted(y.unique())
syn["y"] = pd.Categorical(y, categories=levels, ordered=True)
syn["cell"] = syn.model + "|" + syn.strategy
MODELS, STRATS = meta["model_order"], meta["strategies"]


def dummies(cols):
    parts = []
    for c, ref in cols:
        d = pd.get_dummies(syn[c], prefix=c, dtype=float)
        parts.append(d.drop(columns=f"{c}_{ref}"))
    return pd.concat(parts, axis=1) if parts else None


def fit(cols):
    X = dummies(cols)
    if X is None:  # thresholds only: fit with a zero column is not allowed; use analytic LL
        p = syn.y.value_counts(normalize=True)
        return float((syn.y.map(p).astype(float).apply(np.log)).sum()), 0, None
    m = OrderedModel(syn.y, X, distr="logit")
    r = m.fit(method="bfgs", maxiter=5000, disp=False)
    assert r.mle_retvals["converged"], cols
    return float(r.llf), X.shape[1], r


ll0, _, _ = fit([])
llM, kM, _ = fit([("model", MODELS[0])])
llS, kS, _ = fit([("strategy", STRATS[0])])
llMS, kMS, rMS = fit([("model", MODELS[0]), ("strategy", STRATS[0])])
llC, kC, _ = fit([("cell", f"{MODELS[0]}|{STRATS[0]}")])
rows = []
for name, llr, llf, dfree in (
        ("model | strategy", llS, llMS, kMS - kS),
        ("strategy | model", llM, llMS, kMS - kM),
        ("model (alone)", ll0, llM, kM),
        ("strategy (alone)", ll0, llS, kS),
        ("interaction | additive", llMS, llC, kC - kMS)):
    lr = 2 * (llf - llr)
    rows.append(dict(term=name, LR_chi2=lr, df=dfree, p=float(stats.chi2.sf(lr, dfree)),
                     delta_mcfadden_R2=(llf - llr) / (-ll0)))
rows.append(dict(term="additive model+strategy vs null", LR_chi2=2 * (llMS - ll0), df=kMS,
                 p=float(stats.chi2.sf(2 * (llMS - ll0), kMS)), delta_mcfadden_R2=1 - llMS / ll0))
rows.append(dict(term="saturated cell model vs null", LR_chi2=2 * (llC - ll0), df=kC,
                 p=float(stats.chi2.sf(2 * (llC - ll0), kC)), delta_mcfadden_R2=1 - llC / ll0))
LR = pd.DataFrame(rows)
LR.to_csv(HERE / "clm_lr_tests.csv", index=False)
print(LR.to_string())

# predicted distribution per combination from the additive CLM -> Cliff's delta vs SCB
cells = COMB[["model", "strategy"]].copy()
Xc = pd.concat([pd.get_dummies(cells.model, prefix="model", dtype=float).drop(columns=f"model_{MODELS[0]}"),
                pd.get_dummies(cells.strategy, prefix="strategy", dtype=float).drop(columns=f"strategy_{STRATS[0]}")],
               axis=1)
Xc = Xc[[c for c in rMS.model.exog_names if c in Xc.columns]]
assert Xc.shape[1] == kMS
pred = rMS.model.predict(rMS.params, exog=Xc.to_numpy())          # (58, L)
ref = real["first"].astype(int).value_counts(normalize=True).reindex(levels, fill_value=0).to_numpy()
missing_in_syn = set(real["first"].astype(int)) - set(levels)
assert not missing_in_syn, missing_in_syn
S = np.sign(np.subtract.outer(np.array(levels), np.array(levels)))
cells["delta_clm_pred"] = pred @ S @ ref
cells["delta_obs"] = COMB["delta"]
r = stats.pearsonr(cells.delta_clm_pred, cells.delta_obs)[0]
rho = stats.spearmanr(cells.delta_clm_pred, cells.delta_obs)[0]
cells.to_csv(HERE / "clm_predicted_vs_observed.csv", index=False)
print("pred vs obs delta: pearson", r, "spearman", rho, "RMSE",
      float(np.sqrt(((cells.delta_clm_pred - cells.delta_obs) ** 2).mean())))
json.dump(dict(pearson=r, spearman=rho, levels=[int(x) for x in levels], ll0=ll0, llM=llM, llS=llS, llMS=llMS,
               llCell=llC),
          open(HERE / "clm_meta.json", "w"), indent=1)

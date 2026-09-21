"""Does the judge's clash severity (S1/S2/S3) track its typicality score? swedish_02.

Scratch analysis. Loading mirrors ../effects.py (same persona CSVs, same model order).
Per persona: typicality = typicality_mean (mean over rounds, pipeline default), severity
indicators from clash_count_s{1,2,3} (distinct clashes, union over rounds; worst = max_severity).
Round-count control: SCB has 1 round per persona, 486 synthetic personas have 2, and the
union over rounds can only add clashes, so every prevalence is also computed on round 0 only
from the *_clashes.csv files (suffix _r1).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from population_synthetic.analysis.utils.stats_tests import cliffs_delta

OUT = Path(__file__).resolve().parent
META = json.load(open(OUT.parent / "meta.json"))
BASE = Path("<project-data>/02_Data")
PR = BASE / "03_Analysis/persona_realism/swedish_02"
REAL = "real_swedish_02"
LEVELS = ("S1", "S2", "S3")
MODEL_ORDER, STRATS, LETTERS = META["model_order"], META["strategies"], META["letters"]

# ---------------------------------------------------------------- load
df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(PR / "*" / "*_personas.csv")))],
               ignore_index=True)
cl = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(PR / "*" / "*_clashes.csv")))],
               ignore_index=True)
assert len(df) == 5900 and (df.is_real_reference == True).sum() == 100  # noqa: E712
df["key"] = df.slug + "/" + df.persona_id
cl["key"] = cl.slug + "/" + cl.persona_id
assert set(cl.key) <= set(df.key)
assert (df[[f"clash_count_s{i}" for i in (1, 2, 3)]].sum(axis=1) == df.clash_count).all()

for lv in LEVELS:
    c = f"clash_count_s{lv[1]}"
    df[f"any_{lv}"] = df[c] > 0
    # round-0-only distinct pairs at this level
    r0 = cl[(cl.round_index == 0) & (cl.severity == lv)].drop_duplicates(["key", "attr_a", "attr_b"])
    df[f"n_{lv}_r1"] = df.key.map(r0.groupby("key").size()).fillna(0).astype(int)
    df[f"any_{lv}_r1"] = df[f"n_{lv}_r1"] > 0
    # the union over rounds must contain round 0
    assert (df[f"n_{lv}_r1"] <= df[c]).all(), lv
df["n_clash_r1"] = df[[f"n_{lv}_r1" for lv in LEVELS]].sum(axis=1)
df["worst"] = df.max_severity.fillna("none").replace("", "none")
df["group"] = np.where(df.is_real_reference == True, REAL, df.model)  # noqa: E712
df["method"] = df.strategy.map(LETTERS)
df["excluded"] = df.can_exist_majority != True  # noqa: E712
surv = df[~df.excluded].copy()
assert len(surv) == 5860 and surv.typicality_mean.notna().all()

# consistency of the judge contract ("If can_exist is false, at least one issue must be S3")
contract = dict(
    excluded_total=int(df.excluded.sum()),
    excluded_without_any_S3=int((df.excluded & ~df.any_S3).sum()),
    survivors_with_any_S3=int((~df.excluded & df.any_S3).sum()),
    survivors_with_S3_all_rounds_possible=int((~df.excluded & df.any_S3
                                               & (df.can_exist_true_votes == df.n_rounds_successful)).sum()),
)


# ---------------------------------------------------------------- per-group table
def summarise(sub: pd.DataFrame) -> dict:
    s = sub[~sub.excluded]
    t = s.typicality_mean
    row = dict(n_all=len(sub), n_excluded=int(sub.excluded.sum()),
               excl_rate=sub.excluded.mean(),
               excluded_any_S3=int((sub.excluded & sub.any_S3).sum()),
               n_surv=len(s), typ_median=t.median(), typ_mean=t.mean(),
               # worst-case survivor-bias bound: excluded personas scored 0 (lowest possible)
               typ_median_excl_as0=float(np.median(np.r_[t.to_numpy(), np.zeros(int(sub.excluded.sum()))])),
               typ_mean_excl_as0=float(np.mean(np.r_[t.to_numpy(), np.zeros(int(sub.excluded.sum()))])),
               share_no_clash=(sub.clash_count == 0).mean(),
               share_no_clash_r1=(sub.n_clash_r1 == 0).mean())
    for w in ("none", "S1", "S2", "S3"):
        row[f"worst_{w}"] = (sub.worst == w).mean()
    for lv in LEVELS:
        row[f"any_{lv}"] = sub[f"any_{lv}"].mean()          # all personas incl. excluded
        row[f"any_{lv}_r1"] = sub[f"any_{lv}_r1"].mean()
        row[f"any_{lv}_surv"] = s[f"any_{lv}"].mean()
        w, wo = t[s[f"any_{lv}"]], t[~s[f"any_{lv}"]]
        row.update({f"n_with_{lv}": len(w), f"typ_med_with_{lv}": w.median() if len(w) else np.nan,
                    f"typ_mean_with_{lv}": w.mean() if len(w) else np.nan,
                    f"typ_med_without_{lv}": wo.median(), f"typ_mean_without_{lv}": wo.mean(),
                    f"delta_with_vs_without_{lv}": cliffs_delta(list(w), list(wo))["delta"]
                    if len(w) and len(wo) else np.nan})
        cnt = s[f"clash_count_s{lv[1]}"]
        rho, p = stats.spearmanr(t, cnt) if cnt.nunique() > 1 else (np.nan, np.nan)
        row[f"rho_typ_count_{lv}"], row[f"p_rho_{lv}"] = rho, p
    rho, p = stats.spearmanr(t, s.clash_count) if s.clash_count.nunique() > 1 else (np.nan, np.nan)
    row["rho_typ_count_all"], row["p_rho_all"] = rho, p
    # clash-free survivors only: typicality with no clash of any level raised
    cf = t[s.clash_count == 0]
    row.update(n_clash_free=len(cf), typ_med_clash_free=cf.median(), typ_mean_clash_free=cf.mean())
    return row


groups = [(dict(level="scb", group=REAL), df[df.group == REAL]),
          (dict(level="all_synthetic", group="all_synthetic"), df[df.group != REAL])]
groups += [(dict(level="model", group=m), df[df.group == m]) for m in MODEL_ORDER]
groups += [(dict(level="combo", group=m, method=LETTERS[s]), df[(df.model == m) & (df.strategy == s)])
           for m in MODEL_ORDER for s in STRATS if ((df.model == m) & (df.strategy == s)).any()]
tab = pd.DataFrame([{**k, **summarise(v)} for k, v in groups])
assert (tab.level == "combo").sum() == 58
tab.to_csv(OUT / "severity_typicality_by_group.csv", index=False)

# ---------------------------------------------------------------- SCB vs synthetic within strata
real_s = surv[surv.group == REAL]
syn_s = surv[surv.group != REAL]
strata = {"all survivors": lambda d: d.index == d.index,
          "no clash at all": lambda d: d.clash_count == 0,
          "no clash (round 0)": lambda d: d.n_clash_r1 == 0,
          "any S1": lambda d: d.any_S1,
          "S1 only (worst=S1)": lambda d: d.worst == "S1",
          "exactly 1 S1, nothing else": lambda d: (d.clash_count_s1 == 1) & (d.clash_count == 1),
          "exactly 2 S1, nothing else": lambda d: (d.clash_count_s1 == 2) & (d.clash_count == 2)}
st = []
for name, f in strata.items():
    a, b = syn_s.typicality_mean[f(syn_s)], real_s.typicality_mean[f(real_s)]
    st.append(dict(stratum=name, n_syn=len(a), syn_median=a.median(), syn_mean=a.mean(),
                   n_scb=len(b), scb_median=b.median(), scb_mean=b.mean(),
                   cliffs_delta_syn_vs_scb=cliffs_delta(list(a), list(b))["delta"] if len(a) and len(b) else np.nan))
st = pd.DataFrame(st)
st.to_csv(OUT / "scb_vs_synthetic_within_clash_strata.csv", index=False)

# ---------------------------------------------------------------- how much of the gap do clash counts explain?
d = surv.assign(scb=(surv.group == REAL).astype(int), s1=surv.clash_count_s1, s2=surv.clash_count_s2,
                s3=surv.clash_count_s3, typ=surv.typicality_mean)
fits = []
for form in ("typ ~ scb", "typ ~ scb + s1 + s2 + s3", "typ ~ s1 + s2 + s3"):
    m = smf.ols(form, d).fit(cov_type="HC3")
    fits.append(dict(formula=form, n=int(m.nobs), r2=m.rsquared,
                     **{f"b_{k}": v for k, v in m.params.items()},
                     **{f"se_{k}": v for k, v in m.bse.items()}))
# same, SCB only / synthetic only: within-population slope of typicality on S1 count
for lab, sub in (("scb_only", d[d.scb == 1]), ("synthetic_only", d[d.scb == 0])):
    m = smf.ols("typ ~ s1 + s2 + s3", sub).fit(cov_type="HC3")
    fits.append(dict(formula=f"typ ~ s1 + s2 + s3 [{lab}]", n=int(m.nobs), r2=m.rsquared,
                     **{f"b_{k}": v for k, v in m.params.items()},
                     **{f"se_{k}": v for k, v in m.bse.items()}))
fits = pd.DataFrame(fits)
fits.to_csv(OUT / "ols_typicality_on_clash_counts.csv", index=False)

# ---------------------------------------------------------------- ecological: across the 59 units
units = tab[tab.level.isin(["combo", "scb"])]
eco = []
for x in ("any_S1", "any_S1_r1", "any_S2", "any_S3", "share_no_clash"):
    for with_scb in (True, False):
        u = units if with_scb else units[units.level == "combo"]
        rho, p = stats.spearmanr(u[x], u.typ_median)
        rho2, p2 = stats.spearmanr(u[x], u.typ_mean)
        eco.append(dict(x=x, units="58 combos + SCB" if with_scb else "58 combos", n=len(u),
                        rho_vs_typ_median=rho, p_median=p, rho_vs_typ_mean=rho2, p_mean=p2))
eco = pd.DataFrame(eco)
eco.to_csv(OUT / "ecological_spearman_combo_level.csv", index=False)

# typicality distribution by number of S1 clashes (clean-S1 personas), SCB vs synthetic
s1only = surv[surv.clash_count == surv.clash_count_s1]
dist = (s1only.assign(pop=np.where(s1only.group == REAL, "scb", "synthetic"),
                n_s1=lambda x: x.clash_count_s1.clip(upper=3))
        .groupby(["pop", "n_s1"]).typicality_mean.agg(["size", "median", "mean"]).reset_index())
dist.to_csv(OUT / "typicality_by_s1_count.csv", index=False)

json.dump(contract, open(OUT / "contract_checks.json", "w"), indent=1)
pd.set_option("display.width", 250)
print(contract)
cols = ["group", "method", "n_all", "n_excluded", "excluded_any_S3", "typ_median", "typ_median_excl_as0",
        "any_S1", "any_S1_r1", "any_S2", "any_S3", "worst_none",
        "typ_med_with_S1", "typ_med_without_S1", "delta_with_vs_without_S1", "rho_typ_count_S1", "p_rho_S1",
        "typ_med_clash_free"]
print(tab[tab.level != "combo"][cols].round(3).to_string())
print(tab[tab.level != "combo"][["group", "typ_med_with_S2", "typ_med_without_S2", "n_with_S2", "rho_typ_count_S2",
                                 "n_with_S3", "typ_med_with_S3", "rho_typ_count_all", "p_rho_all"]].round(3).to_string())
print(st.round(3).to_string())
print(fits.round(3).to_string())
print(eco.round(3).to_string())
print(dist.round(2).to_string())
c = tab[tab.level == "combo"]
print("combo any_S1 range", c.any_S1.min(), c.any_S1.max(), "median", c.any_S1.median())
print("combo excl counts", c.n_excluded.value_counts().sort_index().to_dict())
print(c.sort_values("n_excluded", ascending=False)[["group", "method", "n_all", "n_excluded", "typ_median",
                                                   "typ_median_excl_as0"]].head(8).to_string())
print("combos where median changes under excl-as-0:", int((c.typ_median != c.typ_median_excl_as0).sum()))

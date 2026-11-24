"""Attribute bootstrap CI widths to SCB (n=100) vs combination resampling; writes ci_width_attribution.csv."""
import runpy
import numpy as np
import pandas as pd

g = runpy.run_path("closeness.py", run_name="closeness_import")
BOOT, ls_means, decompose, ci, STRATS, MODELS, LETTER, MLAB = (g[k] for k in (
    "BOOT", "ls_means", "decompose", "ci", "STRATS", "MODELS", "LETTER", "MLAB"))
rows = []
for name, bo in BOOT.items():
    y = bo["delta"]
    sm, mm = ls_means(y)
    d = decompose(y)
    q = {"grand mean delta": y.mean(-1), "E minus mean(A-D) LS": sm[:, 4] - sm[:, :4].mean(-1),
         "B minus A LS": sm[:, 1] - sm[:, 0],
         "max-min model LS": mm.max(-1) - mm.min(-1),
         "pomega2 strategy": d["pomega2_strategy"], "pomega2 model": d["pomega2_model"],
         "share strategy": d["share_strategy"], "share model": d["share_model"]}
    for j, s in enumerate(STRATS):
        q[f"LS mean {LETTER[s]}"] = sm[:, j]
    for i, m in enumerate(MODELS):
        q[f"LS mean {MLAB[m]}"] = mm[:, i]
    for k, v in q.items():
        lo, hi = ci(v)
        rows.append(dict(quantity=k, resampling=name, ci_lo=lo, ci_hi=hi, width=hi - lo))
t = pd.DataFrame(rows).pivot(index="quantity", columns="resampling", values="width")
t["scb_share_of_var_approx"] = t.scb_only ** 2 / (t.scb_only ** 2 + t.combos_only ** 2)
t.to_csv("ci_width_attribution.csv")
print(t.round(3).to_string())

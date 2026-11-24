"""Headline manuscript numbers from the per-slug fidelity CSVs of one ref-v3 base.
Usage: python headline_numbers.py <base> <out_json_or_dash>
Uses the statistics code of the worktree reference-v3-corrections (read, never written)."""
import sys,csv,json,glob,os
import numpy as np
from scipy import stats
W=os.environ['POPSYNTH_REPO']
sys.path.insert(0,W+'/src')
from population_synthetic.analysis.utils.stats_tests import rm_anova_within,rm_anova_assumptions
base=sys.argv[1]; fid=os.path.join(base,'03_Analysis','fidelity')
S=["all_pick_v2","all_pick_dag_v2","all_generate_pick_v2","all_generate_evaluate_pick_v2","all_generate_evaluate_random_pick_v2"]
ov={}
for d in sorted(glob.glob(fid+'/swedish_02_*/')):
    slug=os.path.basename(d.rstrip('/'+chr(92))); f=os.path.join(d,slug+'.csv')
    if not os.path.exists(f): continue
    st=[s for s in S if slug.startswith('swedish_02_'+s)]
    if not st: continue
    st=st[0]; m=slug[len('swedish_02_'+st)+1:]
    rows=list(csv.DictReader(open(f,encoding='utf-8')))
    ov[(m,st)]={r['attribute']:1-float(r['tv_distance']) for r in rows}
models=sorted({m for m,_ in ov}); cm=[m for m in models if all((m,s) in ov for s in S)]
means={k:float(np.mean(list(v.values()))) for k,v in ov.items()}
M=np.array([[means[(m,s)] for s in S] for m in cm])
res={'n_combos':len(ov),'complete_models':cm,'strategy_means':[round(float(x),4) for x in M.mean(0)]}
a0=rm_anova_within(M); an=rm_anova_assumptions(M,labels='ABCDE',alpha=0.05); gg=an['sphericity']['corrected']['greenhouse_geisser']
res['rm_anova']={'F':a0['F'],'partial_eta2':a0['partial_eta_sq'],'gg_df':(gg['df1'],gg['df2']),'gg_p':gg['p']}
n,k=M.shape; g=M.mean(); ssT=((M-g)**2).sum(); ssS=n*((M.mean(0)-g)**2).sum(); ssM=k*((M.mean(1)-g)**2).sum(); ssE=ssT-ssS-ssM
Fm=(ssM/(n-1))/(ssE/((n-1)*(k-1)))
res['shares']={'strategy':ssS/ssT,'llm':ssM/ssT,'resid':ssE/ssT,'F_llm':Fm,'df':(n-1,(n-1)*(k-1)),'p_llm':float(stats.f.sf(Fm,n-1,(n-1)*(k-1)))}
best=max(means,key=means.get); res['best_combo']=[best,round(means[best],4)]
E=S[4]; res['E_best_in_each_model']=bool(all(M[:,4]>M[:,:4].max(1)))
res['E_min']=[cm[int(M[:,4].argmin())],round(float(M[:,4].min()),4)]; res['ABCD_max_10models']=round(float(M[:,:4].max()),4)
ad=[v for (m,s),v in means.items() if s!=E]; res['ABCD_max_all_models']=round(max(ad),4)
res['E_minus_D']=round(float((M[:,4]-M[:,3]).mean()),4)
res['order_ok']=bool(np.all(np.diff(M.mean(0))>0))
print(json.dumps(res,indent=1,default=float))
if sys.argv[2]!='-': json.dump(res,open(sys.argv[2],'w'),indent=1,default=float)

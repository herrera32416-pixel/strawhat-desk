import pandas as pd,numpy as np
from scipy.optimize import minimize_scalar,minimize
D='/workspace/strawhat-desk/research/trends-2026-10/data/'
lg=lambda p:np.log(np.clip(p,1e-4,1-1e-4)/(1-np.clip(p,1e-4,1-1e-4)));sg=lambda x:1/(1+np.exp(-x))
def ev(name,df,feats=()):
    df=df.dropna(subset=['y','q','m']+list(feats)).copy();df=df[(df.q>0)&(df.q<1)]
    seasons=sorted(df.season.unique());rows=[]
    for s in seasons[1:]:
        tr,te=df[df.season<s],df[df.season==s]
        def X(d,th): 
            z=lg(d.q)+th[0]*(lg(d.m)-lg(d.q))
            for i,f in enumerate(feats): z=z+th[1+i]*d[f]
            return sg(z)
        nll=lambda th:-np.mean(tr.y*np.log(X(tr,th))+(1-tr.y)*np.log(1-X(tr,th)))
        th=minimize(nll,np.zeros(1+len(feats))).x
        p=X(te,th);rows.append(pd.DataFrame({'y':te.y,'q':te.q,'m':te.m,'p':p,'a':th[0]}))
    r=pd.concat(rows)
    out={}
    for c in ['q','m','p']:
        pp=r[c];ll=-np.mean(r.y*np.log(pp)+(1-r.y)*np.log(1-pp));br=np.mean((pp-r.y)**2)
        hit=np.mean((pp>.5)==(r.y==1))
        out[c]=(round(ll,4),round(br,4),round(hit,4))
    print(f"{name}: n={len(r)} fitted a≈{r.a.mean():.2f}  [logloss,brier,hit]  market {out['q']}  raw model {out['m']}  shrunk {out['p']}")
    for t in (.55,.60,.65):
        for c in ('m','p'):
            conf=np.maximum(r[c],1-r[c]);sel=conf>=t
            print(f"    {c} conf>={t}: n={sel.sum()} ({sel.mean():.0%}) hit {np.mean(((r[c]>.5)==(r.y==1))[sel]):.3f}")
    return r
nhl=pd.read_csv(D+'nhl_features.csv');mp=pd.read_csv(D+'nhl_model_preds.csv')
nhl=nhl.drop(columns=['m']).merge(mp,on=['date','home','away'],how='inner')
ev('NHL ML xG',nhl);ev('NHL ML xG+n7',nhl,('n7',))
mlb=pd.read_csv(D+'mlb_features.csv');mlb['m']=mlb.m.where(mlb.m!=0.5);ev('MLB ML ESPN-pred',mlb)
cfb=pd.read_csv(D+'cfb_features.csv');ev('CFB ML FPI',cfb)

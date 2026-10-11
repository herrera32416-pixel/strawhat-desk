"""Shared evaluation: market no-vig, metrics, blend, ROI."""
import numpy as np, pandas as pd
def am2p(a): a=np.asarray(a,float); return np.where(a<0,-a/(-a+100),100/(a+100))
def am2dec(a): a=np.asarray(a,float); return np.where(a<0,1+100/-a,1+a/100)
def novig(a,b): pa,pb=am2p(a),am2p(b); return pa/(pa+pb)
def ll(p,y): p=np.clip(p,1e-4,1-1e-4); return float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))
def brier(p,y): return float(np.mean((p-y)**2))
def lg(p): p=np.clip(p,1e-4,1-1e-4); return np.log(p/(1-p))
def blend(ps,pm,w): return 1/(1+np.exp(-(w*lg(ps)+(1-w)*lg(pm))))
def roi(ps,pm,y,price_yes,price_no,edges=(0.02,0.04,0.06,0.08),unit=20):
    """Bet yes if ps-pm>=e, no if pm-ps>=e. y: 1 yes,0 no, nan push."""
    out={}
    for e in edges:
        yes=(ps-pm)>=e; no=(pm-ps)>=e
        pnl=[];n=0
        for b,side,pr in ((yes,1,price_yes),(no,0,price_no)):
            idx=b&~np.isnan(pr)
            d=am2dec(pr[idx]); yy=y[idx]
            r=np.where(np.isnan(yy),0,np.where(yy==side,(d-1)*unit,-unit)); pnl+=list(r); n+=idx.sum()
        pnl=np.array(pnl); out[f'edge>={e:.2f}']={'bets':int(n),'pnl_usd':round(float(pnl.sum()),2),'roi_pct':round(100*float(pnl.sum())/(unit*max(n,1)),2)}
    return out

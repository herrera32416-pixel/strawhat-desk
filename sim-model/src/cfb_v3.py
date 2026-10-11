"""CFB v3: walk-forward line-error models using sim gap + step-2 environment (Open-Meteo archive kickoff weather, travel, altitude, indoor, returning production)."""
import pandas as pd, numpy as np
from sklearn.linear_model import Ridge
from scipy.stats import norm
from evalx import *
P=pd.read_parquet('out/cfb_sim_preds.parquet'); E=pd.read_csv('data/cfb_games_env.csv')
D=P.merge(E[['game_id','wx_temp','wx_wind','wx_precip','indoor','elev','travel_mi','home_ret_off','away_ret_off','neutral']],on='game_id',how='left')
D['indoor']=D.indoor.astype(str).eq('True').astype(int)
for c in ('wx_wind','wx_temp','wx_precip'): D[c]=np.where(D.indoor==1,{'wx_wind':0,'wx_temp':70,'wx_precip':0}[c],D[c])
D['wind15']=(D.wx_wind>=15).astype(int); D['cold']=(50-D.wx_temp).clip(0); D['hot']=(D.wx_temp-85).clip(0); D['rain']=(D.wx_precip>0.05).astype(int)
D['elev_k']=D.elev.fillna(D.elev.median())/1000; D['trav_k']=D.travel_mi.fillna(D.travel_mi.median())/1000
D['ret_sum']=(D.home_ret_off.fillna(.43)+D.away_ret_off.fillna(.43)); D['ret_diff']=D.home_ret_off.fillna(.43)-D.away_ret_off.fillna(.43)
D['early']=(D.week<=4).astype(int); D['ret_early']=D.ret_sum*D.early; D['retd_early']=D.ret_diff*D.early
D['gap_t']=D.sim_total-D.total_line; D['gap_m']=D.sim_margin-D.spread_line
VARS={'tot_full':(['gap_t','wx_wind','wind15','cold','hot','rain','indoor','elev_k','ret_early'],'total','total_line'),
      'tot_env_only':(['wx_wind','wind15','cold','hot','rain','indoor','elev_k','ret_early'],'total','total_line'),
      'tot_gap_only':(['gap_t'],'total','total_line'),
      'sp_full':(['gap_m','trav_k','elev_k','retd_early','neutral'],'result','spread_line')}
res={}
for name,(X,act,line) in VARS.items():
    out=[]
    for S in (2024,2025,2026):
        tr=D[(D.season<S)].dropna(subset=[act]); te=D[D.season==S].dropna(subset=[act]).copy()
        y=tr[act]-tr[line]; m=Ridge(alpha=50).fit(tr[X].fillna(0),y); sd=np.std(y-m.predict(tr[X].fillna(0)))
        te['p']=1-norm.cdf(-m.predict(te[X].fillna(0))/sd); te['pred']=m.predict(te[X].fillna(0)); out.append(te)
    R=pd.concat(out); R=R[R[act]!=R[line]]; y=(R[act]>R[line]).values*1.
    if act=='total': pm=np.full(len(R),0.5); py=np.full(len(R),-110.); pn=py
    else: pm=novig(R.home_sp_odds.fillna(-110),R.away_sp_odds.fillna(-110)); py=R.home_sp_odds.fillna(-110).values; pn=R.away_sp_odds.fillna(-110).values
    bys={}
    for s in (2024,2025,2026):
        k=(R.season==s).values; bys[s]={'ll_minus_mkt':round(ll(R.p.values[k],y[k])-ll(pm[k],y[k]),4),**roi(R.p.values[k],pm[k],y[k],py[k],pn[k],edges=(0.04,))['edge>=0.04']}
    res[name]={'ll':round(ll(R.p.values,y),5),'mkt_ll':round(ll(pm,y),5),'mae_model':round(float((R[act]-R[line]-R.pred).abs().mean()),3),'mae_close':round(float((R[act]-R[line]).abs().mean()),3),
               'roi':roi(R.p.values,pm,y,py,pn,edges=(0.02,0.04,0.06)),'by_season':bys}
    print(name,res[name])
import json; json.dump(res,open('out/cfb_v3_results.json','w'),indent=1,default=float)

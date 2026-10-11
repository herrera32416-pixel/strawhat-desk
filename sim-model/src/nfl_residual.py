"""v3 NFL: predict the closing-line ERROR directly (walk-forward). y = result - spread_line, total - total_line.
Features: sim-vs-close gaps (v2), QB-change adj, wind/cold/dome, rest diff, divisional, neutral + news-style flags.
Heavy ridge; P(cover)=Normal(pred/sd) with sd from prior residuals; evaluate vs market no-vig."""
import pandas as pd, numpy as np, json
from sklearn.linear_model import Ridge
from scipy.stats import norm
from evalx import *
P=pd.read_parquet('out/nfl_v2_preds.parquet'); F=pd.read_parquet('out/nfl_features_v2.parquet')
D=P.merge(F[['game_id','h_qbadj','a_qbadj','h_rest_d','wind_f','cold','dome','div','neutral','turf']].rename(columns={'h_qbadj':'hq','a_qbadj':'aq'}),on='game_id')
D['gap_m']=D.sim_margin-D.spread_line; D['gap_t']=D.sim_total-D.total_line
D['qbdiff']=D.hq-D.aq; D['qbchg']=((D.hq.abs()>.02)|(D.aq.abs()>.02)).astype(int)
D['wind15']=(D.wind_f>=15).astype(int); D['big_fav']=(D.spread_line.abs()>=7).astype(int)
XM=['gap_m','qbdiff','qbchg','h_rest_d','div','neutral','big_fav','dome']; XT=['gap_t','wind_f','wind15','cold','dome','turf','qbchg']
rows=[]
for S in range(2017,2027):
    tr=D[(D.season<S)&D.result.notna()]; te=D[D.season==S].copy()
    for tgt,X,line,act in (('m',XM,'spread_line','result'),('t',XT,'total_line','total')):
        y=tr[act]-tr[line]; m=Ridge(alpha=50).fit(tr[X],y); sd=np.std(y-m.predict(tr[X]))
        te['r_'+tgt]=m.predict(te[X]); te['sd_'+tgt]=sd; te['coef_'+tgt]=json.dumps(dict(zip(X,np.round(m.coef_,3))))
    rows.append(te)
R=pd.concat(rows); R['sim_cover']=1-norm.cdf(-R.r_m/R.sd_m); R['sim_over']=1-norm.cdf(-R.r_t/R.sd_t)
R['sim_margin']=R.spread_line+R.r_m; R['sim_total']=R.total_line+R.r_t
R.to_parquet('out/nfl_v3resid_preds.parquet')
print(R[R.season==2026].coef_m.iloc[0]); print(R[R.season==2026].coef_t.iloc[0])
pl=R[R.result.notna()]
for s,g in pl.groupby('season'):
    c=g.result!=g.spread_line; t=g.total!=g.total_line
    print(s,'SP',round(ll(g.sim_cover[c].values,(g.result[c]>g.spread_line[c]).values*1.)-ll(novig(g.home_sp_odds[c].fillna(-110),g.away_sp_odds[c].fillna(-110)),(g.result[c]>g.spread_line[c]).values*1.),4),
      'TOT',round(ll(g.sim_over[t].values,(g.total[t]>g.total_line[t]).values*1.)-ll(novig(g.over_odds[t].fillna(-110),g.under_odds[t].fillna(-110)),(g.total[t]>g.total_line[t]).values*1.),4))

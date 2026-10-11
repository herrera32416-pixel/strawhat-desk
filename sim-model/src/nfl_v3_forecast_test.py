"""Re-test v3 NFL totals line-error model with archived pregame FORECAST weather for 2022+ (walk-forward; test 2022-2025)."""
import pandas as pd,numpy as np,json
from sklearn.linear_model import Ridge
from scipy.stats import norm
from evalx import *
P=pd.read_parquet('out/nfl_v2_preds.parquet'); F=pd.read_parquet('out/nfl_features_v2.parquet')
W=pd.read_parquet('data/nfl_hist_forecast.parquet')
D=P.merge(F[['game_id','h_qbadj','a_qbadj','wind_f','cold','dome','turf','temp']],on='game_id').merge(W[['game_id','fc_wind','fc_temp']],on='game_id',how='left')
D['gap_t']=D.sim_total-D.total_line; D['qbchg']=((D.h_qbadj.abs()>.02)|(D.a_qbadj.abs()>.02)).astype(int)
med_w=D.wind_f.median()
# forecast-weather columns: 2022+ open-air -> forecast; dome -> 0; 2022+ outdoor without forecast (neutral sites) -> median; <2022 -> recorded (only data available)
fw=np.where(D.dome==1,0,np.where(D.season>=2022,D.fc_wind.fillna(med_w),D.wind_f))
ft=np.where(D.season>=2022,D.fc_temp.fillna(60),D.temp.fillna(60))
D['wind_fc']=fw; D['cold_fc']=np.where(D.dome==1,0,(50-ft).clip(0,None))
for p,wcol,ccol in (('rec','wind_f','cold'),('fc','wind_fc','cold_fc')):
    D[f'w15_{p}']=(D[wcol]>=15).astype(int)
VAR={'recorded_weather':['gap_t','wind_f','w15_rec','cold','dome','turf','qbchg'],
     'forecast_weather':['gap_t','wind_fc','w15_fc','cold_fc','dome','turf','qbchg'],
     'forecast_env_only':['wind_fc','w15_fc','cold_fc','dome','turf','qbchg'],
     'no_weather':['gap_t','dome','turf','qbchg']}
res={}
for name,X in VAR.items():
    out=[]
    for S in (2022,2023,2024,2025):
        tr=D[(D.season<S)&D.result.notna()]; te=D[(D.season==S)&D.result.notna()].copy()
        y=tr.total-tr.total_line; m=Ridge(alpha=50).fit(tr[X],y); sd=np.std(y-m.predict(tr[X]))
        te['po']=1-norm.cdf(-m.predict(te[X])/sd); out.append(te)
    R=pd.concat(out); R=R[R.total!=R.total_line]; y=(R.total>R.total_line).values*1.
    pm=novig(R.over_odds.fillna(-110),R.under_odds.fillna(-110))
    bys={}
    for s,g in R.groupby('season'):
        k=(R.season==s).values
        bys[int(s)]={'ll_minus_mkt':round(ll(R.po.values[k],y[k])-ll(pm[k],y[k]),4),**roi(R.po.values[k],pm[k],y[k],R.over_odds.values[k],R.under_odds.values[k],edges=(0.04,))['edge>=0.04']}
    res[name]={'ll':round(ll(R.po.values,y),5),'mkt_ll':round(ll(pm,y),5),'roi':roi(R.po.values,pm,y,R.over_odds.values,R.under_odds.values,edges=(0.02,0.04,0.06)),'by_season':bys}
    print(name,'LL',res[name]['ll'],'mkt',res[name]['mkt_ll'],{e:(v['bets'],v['roi_pct']) for e,v in res[name]['roi'].items()});print('   ',{s:(v['ll_minus_mkt'],v['bets'],v['roi_pct']) for s,v in bys.items()})
json.dump(res,open('out/nfl_v3_forecast_test.json','w'),indent=1,default=float)

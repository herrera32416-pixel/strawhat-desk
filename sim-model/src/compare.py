"""Same-subset table: sim vs close log loss, MAE, ROI by season (edge>=4)."""
import pandas as pd, numpy as np, sys, json
from report import report
rows=[]
for tag,f in [a.split('=') for a in sys.argv[2:]]:
    P=pd.read_parquet(f); keep=set(pd.read_parquet(sys.argv[1]).game_id)  # common subset
    P=P[P.game_id.isin(keep)]; r=report(P,tag)
    for k in ('ml','spread','total'):
        rs=r[k]['roi_sim_by_season_edge>=0.04']
        rows.append({'model':tag,'mkt':k,'n':r[k]['n'],'sim_ll':round(r[k]['sim_logloss'],4),'mkt_ll':round(r[k]['market_logloss'],4),
         'best_blend':min(r[k]['blend_logloss'].items(),key=lambda x:x[1]),'roi4_all':r[k]['roi_sim_all']['edge>=0.04']['roi_pct'],
         'roi4_by_season':{s:v['roi_pct'] for s,v in rs.items()},
         'seasons_sim_beats_close':None})
    rows.append({'model':tag,'mae':{k:round(v,2) for k,v in r['mae'].items() if k in('margin_sim','margin_close','total_sim','total_close')},'beyond':(r['beyond_close_margin'],r['beyond_close_total'])})
for x in rows: print(x)

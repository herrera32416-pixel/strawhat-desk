"""Turn sim output into one pick per market (ML, spread, total) per game, with model %, market %, and a tier.
SIM_LIVE gate: picks are tagged 'paper' unless config/gate.json says the market passed walk-forward.
Usage: python src/picks.py out/<league>_sim_preds.parquet <league> [season] [week] -> out/picks/<league>_<season>_w<week>.json"""
import pandas as pd, numpy as np, json, sys, os
from evalx import novig
GATE=json.load(open('config/gate.json'))
def tier(edge):
    e=abs(edge); return 'A' if e>=0.08 else 'B' if e>=0.05 else 'C' if e>=0.02 else 'none'
def picks(P,league):
    out=[]
    for _,r in P.iterrows():
        g={'game_id':str(r.game_id),'away':r.away,'home':r.home,'sim':{'home_pts':round(r.sim_h_pts,1),'away_pts':round(r.sim_a_pts,1),'margin':round(r.sim_margin,1),'total':round(r.sim_total,1)},'markets':[]}
        mkts=[]
        if pd.notna(r.home_ml) and pd.notna(r.away_ml): mkts.append(('ml',r.sim_wp,float(novig(r.home_ml,r.away_ml)),(r.home+' ML',r.home_ml),(r.away+' ML',r.away_ml)))
        mkts.append(('spread',r.sim_cover,float(novig(r.home_sp_odds if pd.notna(r.home_sp_odds) else -110,r.away_sp_odds if pd.notna(r.away_sp_odds) else -110)),(f'{r.home} {-r.spread_line:+g}',r.home_sp_odds),(f'{r.away} {r.spread_line:+g}',r.away_sp_odds)))
        mkts.append(('total',r.sim_over,float(novig(r.over_odds if pd.notna(r.over_odds) else -110,r.under_odds if pd.notna(r.under_odds) else -110)),(f'Over {r.total_line:g}',r.over_odds),(f'Under {r.total_line:g}',r.under_odds)))
        for k,ps,pm,yes,no in mkts:
            w=GATE[league][k]['blend_w_sim']; pb=1/(1+np.exp(-(w*np.log(ps/(1-ps))+(1-w)*np.log(pm/(1-pm))))) if 0<ps<1 else ps
            side=yes if ps>=pm else no; mp=ps if ps>=pm else 1-ps; mk=pm if ps>=pm else 1-pm
            live=GATE[league][k]['passed'] and GATE['SIM_LIVE']
            g['markets'].append({'market':k,'pick':side[0],'price':None if pd.isna(side[1]) else float(side[1]),'model_pct':round(100*mp,1),'market_pct':round(100*mk,1),
              'blend_pct':round(100*(pb if ps>=pm else 1-pb),1),'edge_pts':round(100*(mp-mk),1),'tier':tier(mp-mk),'status':'live' if live else 'paper'})
        out.append(g)
    return out
if __name__=='__main__':
    P=pd.read_parquet(sys.argv[1]); L=sys.argv[2]
    s=int(sys.argv[3]) if len(sys.argv)>3 else int(P.season.max()); P=P[P.season==s]
    w=int(sys.argv[4]) if len(sys.argv)>4 else int(P.week.max()); P=P[P.week==w]
    os.makedirs('out/picks',exist_ok=True); f=f'out/picks/{L}_{s}_w{w}.json'
    json.dump({'league':L,'season':s,'week':w,'sim_live':GATE['SIM_LIVE'],'note':'PAPER: sim has not beaten the closing line in walk-forward tests. Tier = size of sim-vs-market disagreement, not proven edge.','games':picks(P,L)},open(f,'w'),indent=1)
    print(f,len(P))

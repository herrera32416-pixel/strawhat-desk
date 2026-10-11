import pandas as pd, numpy as np, json, sys
from evalx import *
def report(P,name):
    P=P.dropna(subset=['spread_line','total_line']).copy()
    out={'league':name,'n_games':len(P),'seasons':sorted(P.season.unique().tolist())}
    mk={}
    m=P.home_ml.notna()&P.away_ml.notna()&(P.result!=0)
    mk['ml']=(P.sim_wp[m].values,novig(P.home_ml[m],P.away_ml[m]),(P.result[m]>0).astype(float).values,P.home_ml[m].values,P.away_ml[m].values,P.season[m].values)
    hs=P.home_sp_odds.fillna(-110);as_=P.away_sp_odds.fillna(-110);m=P.result!=P.spread_line
    mk['spread']=(P.sim_cover[m].values,novig(hs[m],as_[m]),(P.result[m]>P.spread_line[m]).astype(float).values,hs[m].values,as_[m].values,P.season[m].values)
    oo=P.over_odds.fillna(-110);uo=P.under_odds.fillna(-110);m=P.total!=P.total_line
    mk['total']=(P.sim_over[m].values,novig(oo[m],uo[m]),(P.total[m]>P.total_line[m]).astype(float).values,oo[m].values,uo[m].values,P.season[m].values)
    for k,(ps,pm,y,py,pn,ss) in mk.items():
        d={'n':len(y),'sim_logloss':ll(ps,y),'market_logloss':ll(pm,y),'sim_brier':brier(ps,y),'market_brier':brier(pm,y)}
        d['blend_logloss']={f'w_sim={w}':round(ll(blend(ps,pm,w),y),5) for w in (0,.1,.2,.3,.5,.7,1)}
        d['roi_sim_all']=roi(ps,pm,y,py,pn)
        d['roi_blend30_all']=roi(blend(ps,pm,.3),pm,y,py,pn,edges=(0.01,0.02,0.03))
        d['roi_sim_by_season_edge>=0.04']={int(s):roi(ps[ss==s],pm[ss==s],y[ss==s],py[ss==s],pn[ss==s],edges=(0.04,))['edge>=0.04'] for s in np.unique(ss)}
        out[k]=d
    out['mae']={'margin_sim':float((P.result-P.sim_margin).abs().mean()),'margin_close':float((P.result-P.spread_line).abs().mean()),
                'total_sim':float((P.total-P.sim_total).abs().mean()),'total_close':float((P.total-P.total_line).abs().mean()),
                'sim_vs_close_margin_mae':float((P.sim_margin-P.spread_line).abs().mean()),'sim_vs_close_total_mae':float((P.sim_total-P.total_line).abs().mean()),
                'corr_sim_close_margin':float(np.corrcoef(P.sim_margin,P.spread_line)[0,1]),'corr_sim_close_total':float(np.corrcoef(P.sim_total,P.total_line)[0,1])}
    # information-beyond-close test: regress (actual - close) on (sim - close)
    for a,s,c in (('margin','sim_margin','spread_line'),('total','sim_total','total_line')):
        act='result' if a=='margin' else 'total'
        x=(P[s]-P[c]).values; yv=(P[act]-P[c]).values; x0=x-x.mean()
        b=(x0*(yv-yv.mean())).sum()/(x0**2).sum(); res=yv-yv.mean()-b*x0; se=np.sqrt((res**2).sum()/(len(x)-2)/(x0**2).sum())
        out[f'beyond_close_{a}']={'slope':round(float(b),4),'t':round(float(b/se),2),'note':'slope>0 with t>2 would mean the sim knows something the close does not'}
    # mixing margin: best linear combination of close and sim (fit on all - descriptive)
    return out
if __name__=='__main__':
    P=pd.read_parquet(sys.argv[1]); r=report(P,sys.argv[2]); json.dump(r,open(sys.argv[3],'w'),indent=1,default=float)
    print(json.dumps({k:r[k] for k in ('n_games','mae','beyond_close_margin','beyond_close_total')},indent=1))
    for k in ('ml','spread','total'): print(k,{x:r[k][x] for x in ('sim_logloss','market_logloss','sim_brier','market_brier')}, r[k]['blend_logloss'], r[k]['roi_sim_all'])

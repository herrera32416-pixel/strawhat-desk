import pandas as pd, numpy as np, json
from sklearn.linear_model import Ridge
from sim import sim_game
from evalx import *
rng=np.random.default_rng(11); NS=10000
F=pd.read_parquet('out/nfl_features.parquet')
tg=pd.read_parquet('data/nfl_team_games.parquet')
tg['td_r']=tg.td/tg.drives; tg['fg_r']=tg.fg/tg.drives; tg['tov_r']=tg.tov/tg.drives
M=['epa','sr','expl','td_r','fg_r','tov_r','rz_r','drives','pass_rate']
def side_rows(F,s,o):
    X=pd.DataFrame({**{'o_'+m:F[f'{s}_o_{m}'] for m in M},**{'d_'+m:F[f'{o}_d_{m}'] for m in M},
      'home':(1-F.neutral)*(1 if s=='h' else -1),'qbadj':F[f'{s}_qbadj'],'oqbadj':F[f'{o}_qbadj'],
      'rest':F.h_rest_d*(1 if s=='h' else -1),'wind':F.wind_f,'cold':F.cold,'dome':F.dome,'turf':F.turf,
      'alt_vis':F.alt*(1 if s=='a' else 0),'go':F[f'{s}_go'],'fgp':F[f'{s}_fgp'],
      'wind_pass':F.wind_f*F[f'{s}_o_pass_rate']})
    X['team']=F.home_team if s=='h' else F.away_team
    return X
H=side_rows(F,'h','a');A=side_rows(F,'a','h')
def targets(X,F):
    t=pd.DataFrame({'game_id':F.game_id,'posteam':X.team}).merge(tg[['game_id','posteam','td_r','fg_r','tov_r','drives']],on=['game_id','posteam'],how='left')
    return t
TH=targets(H,F);TA=targets(A,F)
feat=[c for c in H.columns if c!='team']
TGT=['td_r','fg_r','tov_r','drives']
res=[];SDS={}
for S in range(2014,2026):
    tr=(F.season<S)&(F.season>=2013); te=F.season==S
    Xtr=pd.concat([H[tr],A[tr]])[feat]; Ytr=pd.concat([TH[tr],TA[tr]])
    ok=Ytr.drives.notna().values
    preds={}
    for t in TGT:
        m=Ridge(alpha=5.0).fit(Xtr[ok],Ytr[t][ok]); preds[t]=(m.predict(H[te][feat]),m.predict(A[te][feat]))
    if S==2014:
        # calibrate per-sim noise on 2014 (training-only season, not reported) to match margin sd
        sub=F[te].reset_index(drop=True); best=None
        for sd in (0.0,0.2,0.35,0.5):
            lls=[]
            for i in range(0,len(sub),3):
                ph={'td':preds['td_r'][0][i],'fg':preds['fg_r'][0][i],'tov':preds['tov_r'][0][i]}
                pa={'td':preds['td_r'][1][i],'fg':preds['fg_r'][1][i],'tov':preds['tov_r'][1][i]}
                h,a=sim_game(rng,4000,(preds['drives'][0][i]+preds['drives'][1][i])/2,ph,pa,sd,0.5)
                p=np.clip((h>a).mean()+0.5*(h==a).mean(),1e-3,1-1e-3); y=float(sub.result[i]>0)
                lls.append(-(y*np.log(p)+(1-y)*np.log(1-p)))
            if best is None or np.mean(lls)<best[1]: best=(sd,np.mean(lls))
            print('cal sd',sd,np.mean(lls))
        SD=best[0]; continue
    sub=F[te].reset_index(drop=True)
    for i,r in sub.iterrows():
        ph={k:float(np.clip(preds[k+'_r'][0][i],.02,.6)) for k in ('td','fg','tov')}
        pa={k:float(np.clip(preds[k+'_r'][1][i],.02,.6)) for k in ('td','fg','tov')}
        dmu=(preds['drives'][0][i]+preds['drives'][1][i])/2
        h,a=sim_game(rng,NS,dmu,ph,pa,SD,0.5)
        mg=h-a; tot=h+a; sp=r.spread_line; tl=r.total_line
        pw=(mg>0).mean()+0.5*(mg==0).mean()
        cov=(mg>sp).mean(); push=(mg==sp).mean(); pc=cov/max(1-push,1e-9)
        ov=(tot>tl).mean(); pu=(tot==tl).mean(); po=ov/max(1-pu,1e-9)
        res.append(dict(game_id=r.game_id,season=S,week=r.week,home=r.home_team,away=r.away_team,
          sim_wp=pw,sim_cover=pc,sim_over=po,sim_margin=mg.mean(),sim_med_margin=np.median(mg),sim_total=tot.mean(),
          sim_h_pts=h.mean(),sim_a_pts=a.mean(),sim_margin_sd=mg.std(),sim_total_sd=tot.std(),
          spread_line=sp,total_line=tl,result=r.result,total=r.total,home_ml=r.home_moneyline,away_ml=r.away_moneyline,
          home_sp_odds=r.home_spread_odds,away_sp_odds=r.away_spread_odds,over_odds=r.over_odds,under_odds=r.under_odds,
          home_qbadj=r.h_qbadj,away_qbadj=r.a_qbadj,wind=r.wind_f))
    print(S,len(sub),flush=True)
P=pd.DataFrame(res); P.to_parquet('out/nfl_sim_preds.parquet'); json.dump({'game_sd':SD},open('out/nfl_cal.json','w'))

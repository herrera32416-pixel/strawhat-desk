import pandas as pd, numpy as np, json, os
L=os.environ.get('LEAGUE','nfl')
from sklearn.linear_model import Ridge
from sim import sim_game
from evalx import *
rng=np.random.default_rng(11); NS=10000
F=pd.read_parquet(f'out/{L}_features{os.environ.get("TAG","")}.parquet')
tg=pd.read_parquet(f'data/{L}_team_games.parquet')
tg['td_r']=tg.td/tg.drives; tg['fg_r']=tg.fg/tg.drives; tg['tov_r']=tg.tov/tg.drives
M=['epa','sr','expl','td_r','fg_r','tov_r','rz_r','drives','pass_rate']
MATCH=os.environ.get('MATCHUP')=='1' and L=='nfl'
MU=['proe','ed_pass','deep','sack_r','run_sr','pass_sr','run_expl','pass_expl','press','blitz','man']
if MATCH: M=M+MU
def side_rows(F,s,o):
    X=pd.DataFrame({**{'o_'+m:F[f'{s}_o_{m}'] for m in M},**{'d_'+m:F[f'{o}_d_{m}'] for m in M},
      'home':(1-F.neutral)*(1 if s=='h' else -1),'qbadj':F[f'{s}_qbadj'],'oqbadj':F[f'{o}_qbadj'],
      'rest':F.h_rest_d*(1 if s=='h' else -1),'wind':F.wind_f,'cold':F.cold,'dome':F.dome,'turf':F.turf,
      'alt_vis':F.alt*(1 if s=='a' else 0),'go':F[f'{s}_go'],'fgp':F[f'{s}_fgp'],
      'wind_pass':F.wind_f*F[f'{s}_o_pass_rate']})
    if MATCH:
        dv=lambda c:(X[c]-X[c].mean())
        # matchup interactions: offense tendency x defense tendency (deviations from league)
        X['mx_press']=dv('o_press')*dv('d_press'); X['mx_sack']=dv('o_sack_r')*dv('d_sack_r')
        X['mx_blitz_pass']=dv('d_blitz')*dv('o_pass_sr'); X['mx_man_deep']=dv('d_man')*dv('o_deep')
        X['mx_run']=dv('o_run_sr')*dv('d_run_sr'); X['mx_pass']=dv('o_pass_sr')*dv('d_pass_sr')
        X['mx_deep_expl']=dv('o_deep')*dv('d_pass_expl'); X['mx_proe_split']=dv('o_proe')*(dv('d_pass_sr')-dv('d_run_sr'))
        X['mx_ed_split']=dv('o_ed_pass')*(dv('d_pass_sr')-dv('d_run_sr'))
    X['team']=F.home_team if s=='h' else F.away_team
    return X
F[['h_qbadj','a_qbadj']]=F[['h_qbadj','a_qbadj']].fillna(0);F['neutral']=F.neutral.fillna(0);F['h_rest_d']=F.h_rest_d.fillna(0)
H=side_rows(F,'h','a');A=side_rows(F,'a','h')
def targets(X,F):
    t=pd.DataFrame({'game_id':F.game_id,'posteam':X.team}).merge(tg[['game_id','posteam','td_r','fg_r','tov_r','drives']],on=['game_id','posteam'],how='left')
    return t
TH=targets(H,F);TA=targets(A,F)
feat=[c for c in H.columns if c!='team']
TGT=['td_r','fg_r','tov_r','drives']
res=[];SDS={}
S0,S1,TR0=(2014,2027,2013) if L=='nfl' else (2022,2027,2021)
for S in range(S0,S1):
    tr=(F.season<S)&(F.season>=TR0); te=F.season==S
    Xtr=pd.concat([H[tr],A[tr]])[feat]; Ytr=pd.concat([TH[tr],TA[tr]])
    ok=Ytr.drives.notna().values
    preds={}
    for t in TGT:
        m=Ridge(alpha=float(os.environ.get('ALPHA',5.0))).fit(Xtr[ok],Ytr[t][ok]); preds[t]=(m.predict(H[te][feat]),m.predict(A[te][feat]))
    if S==S0:
        # calibrate per-sim noise on 2014 (training-only season, not reported) to match margin sd
        sub=F[te].reset_index(drop=True); best=None
        sub_ok=sub.result.notna().values
        for sd in (0.0,0.2,0.35,0.5):
            lls=[]
            for i in range(0,len(sub),3):
                ph={'td':preds['td_r'][0][i],'fg':preds['fg_r'][0][i],'tov':preds['tov_r'][0][i]}
                pa={'td':preds['td_r'][1][i],'fg':preds['fg_r'][1][i],'tov':preds['tov_r'][1][i]}
                h,a=sim_game(rng,4000,(preds['drives'][0][i]+preds['drives'][1][i])/2,ph,pa,sd,0.5)
                if not sub_ok[i]: continue
                p=np.clip((h>a).mean()+0.5*(h==a).mean(),1e-3,1-1e-3); y=float(sub.result[i]>0)
                lls.append(-(y*np.log(p)+(1-y)*np.log(1-p)))
            if best is None or np.mean(lls)<best[1]: best=(sd,np.mean(lls))
            print('cal sd',sd,np.mean(lls))
        SD=best[0]; continue
    sub=F[te].reset_index(drop=True)
    for i,r in sub.iterrows():
        if pd.isna(r.spread_line) or (pd.isna(r.result) and L!='nfl'): continue
        ph={k:float(np.clip(preds[k+'_r'][0][i],.02,.6)) for k in ('td','fg','tov')}
        pa={k:float(np.clip(preds[k+'_r'][1][i],.02,.6)) for k in ('td','fg','tov')}
        dmu=(preds['drives'][0][i]+preds['drives'][1][i])/2
        h,a=sim_game(rng,NS,dmu,ph,pa,SD,0.5,ties=(L=='nfl'))
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
P=pd.DataFrame(res); TAG=os.environ.get('TAG','');P.to_parquet(f'out/{L}_sim_preds{TAG}.parquet'); json.dump({'game_sd':SD},open(f'out/{L}_cal{TAG}.json','w'))

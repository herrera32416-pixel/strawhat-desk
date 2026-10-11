import pandas as pd, numpy as np, json, sys, os
L=os.environ.get('LEAGUE','nfl')
from ratings import Ratings
from sim import sim_game
from sklearn.linear_model import Ridge
rng=np.random.default_rng(7); NS=10000
tg=pd.read_parquet(f'data/{L}_team_games.parquet'); qb=pd.read_parquet(f'data/{L}_qb_games.parquet')
G=pd.read_csv('data/nfl/games.csv') if L=='nfl' else pd.read_csv('data/cfb_games.csv')
G=G[(G.season>=2012)&(G.season<=2025)&G.result.notna()].copy() if L=='nfl' else G[G.game_id.isin(tg.game_id)].copy()
G['gt']=G.game_type.map(lambda t:0 if t=='REG' else 1); G=G.sort_values(['season','gameday','gametime'])
G['wk']=G.season*100+G.week
tg['td_r']=tg.td/tg.drives; tg['fg_r']=tg.fg/tg.drives; tg['tov_r']=tg.tov/tg.drives
tg['rz_r']=(tg.rz_td+1.2)/(tg.rz_trips+2); tg['go_r']=(tg.fd_go+.5)/(tg.fd_n+1.5); tg['fg_pct']=(tg.fgm+4)/(tg.fga+5)
M=['epa','sr','expl','td_r','fg_r','tov_r','rz_r','drives','pass_rate']
opp=tg[['game_id','posteam']+M].rename(columns={'posteam':'defteam',**{m:'d_'+m for m in M}})
tg=tg.merge(opp,on=['game_id','defteam'])
obs=pd.DataFrame({'game_id':tg.game_id,'team':tg.posteam,'opp':tg.defteam,
   **{'off_'+m:tg[m] for m in M},**{'def_'+m:tg['d_'+m] for m in M}})
obs=obs.merge(G[['game_id','wk','season']],on='game_id')
R=Ratings(M,decay=0.93,prior_k=3.0,carry=0.7)
ST=Ratings(['go_r','fg_pct'],decay=0.95,prior_k=6,carry=0.8)
st_obs=pd.DataFrame({'game_id':tg.game_id,'team':tg.posteam,'opp':tg.defteam,'off_go_r':tg.go_r,'def_go_r':tg.go_r,'off_fg_pct':tg.fg_pct,'def_fg_pct':tg.fg_pct}).merge(G[['game_id','wk']],on='game_id')
# QB ratings: shrunk dropback EPA, decayed
qb=qb.merge(G[['game_id','wk']],on='game_id')
qsum={};qn={};team_qb={}
QPRI=-0.05; QK=120
def qrate(q): return (qsum.get(q,0)+QK*QPRI)/(qn.get(q,0)+QK)
feats=[];last=None
for wk,g in G.groupby('wk',sort=True):
    s=wk//100
    if last is not None and s!=last//100:
        R.new_season(); ST.new_season()
        for q in qsum: qsum[q]*=.6; qn[q]*=.6
    for _,r in g.iterrows():
        row={'game_id':r.game_id}
        for side,t,o,qid in (('h',r.home_team,r.away_team,r.home_qb_id),('a',r.away_team,r.home_team,r.away_qb_id)):
            off,w=R.get(t,'off'); de,_=R.get(t,'def')
            for m in M: row[f'{side}_o_{m}']=off[m]; row[f'{side}_d_{m}']=de[m]
            st,_=ST.get(t,'off'); row[f'{side}_go']=st['go_r']; row[f'{side}_fgp']=st['fg_pct']
            base=team_qb.get(t); row[f'{side}_qbadj']=(qrate(qid)-qrate(base)) if (base is not None and isinstance(qid,str)) else 0.0
            row[f'{side}_n']=w
        feats.append(row)
    R.update_week(obs[obs.wk==wk]); ST.update_week(st_obs[st_obs.wk==wk])
    for _,q in qb[qb.wk==wk].iterrows():
        qsum[q.passer_player_id]=qsum.get(q.passer_player_id,0)+q.qepa*q.db; qn[q.passer_player_id]=qn.get(q.passer_player_id,0)+q.db
    lead=qb[qb.wk==wk].sort_values('db').groupby('posteam').tail(1)
    for _,q in lead.iterrows():
        # team's "baseline" QB = who it has had: blend toward current starter
        team_qb[q.posteam]=q.passer_player_id
    last=wk
F=pd.DataFrame(feats).merge(G,on='game_id')
F['h_rest_d']=F.home_rest-F.away_rest; F['dome']=F.roof.isin(['dome','closed']).astype(int)
F['wind_f']=np.where(F.dome==1,0,F.wind.fillna(F.wind.median())); F['cold']=np.where(F.dome==1,0,(50-F.temp.fillna(60)).clip(0,None))
F['alt']=F.home_team.isin(['DEN','Air Force','Wyoming','Colorado','Colorado State','New Mexico','Utah','BYU','Utah State','UNLV','Nevada']).astype(int) if L=='cfb' else (F.home_team=='DEN').astype(int); F['turf']=F.surface.fillna('').str.contains('turf|astro|sport|field',case=False).astype(int)
F['neutral']=(F.location=='Neutral').astype(int); F['div']=F.div_game
F['wind_f']=F.wind_f.fillna(0);F['cold']=F.cold.fillna(0)
F.to_parquet(f'out/{L}_features.parquet'); print('features',F.shape)

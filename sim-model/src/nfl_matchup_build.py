"""Per team-game offensive tendencies (and, via the opponent row, defensive tendencies) for the matchup layer.
PBP 2012-2026: pass rate over expected, early-down pass rate, deep-pass rate (air>=20), sack rate, run/pass success, run/pass explosive.
Participation 2016+ (nflverse/FTN-NGS): pressure rate, blitz rate (5+ rushers), man-coverage rate. Missing seasons -> NaN (league mean in ratings).
Play-action is not in the free data, so it is not modeled."""
import pandas as pd, numpy as np, os
out=[]
for y in range(2012,2027):
    d=pd.read_parquet(f'data/nfl/pbp_{y}.parquet',columns=['game_id','play_id','posteam','season_type','play_type','pass_oe','down','qb_dropback','air_yards','sack','success','yards_gained','rush','pass_attempt'])
    d=d[d.play_type.isin(['pass','run'])&d.posteam.notna()]
    d['early']=d.down.isin([1,2]); d['deep']=(d.air_yards>=20).astype(float).where(d.pass_attempt==1)
    d['expl']=(d.yards_gained>=20).astype(float)
    f=f'data/nfl/part_{y}.parquet'
    if os.path.exists(f):
        p=pd.read_parquet(f,columns=['nflverse_game_id','play_id','was_pressure','number_of_pass_rushers','defense_man_zone_type'])
        p=p.rename(columns={'nflverse_game_id':'game_id'})
        d=d.merge(p,on=['game_id','play_id'],how='left')
        db=d.qb_dropback==1
        d['press']=d.was_pressure.astype(float).where(db&d.was_pressure.notna())
        d['blitz']=(d.number_of_pass_rushers>=5).astype(float).where(db&(d.number_of_pass_rushers>0))
        d['man']=(d.defense_man_zone_type.astype(str).str.upper().str.contains('MAN')).astype(float).where(db&d.defense_man_zone_type.astype(str).str.len().gt(0)&d.defense_man_zone_type.notna())
    else: d['press']=np.nan; d['blitz']=np.nan; d['man']=np.nan
    g=d.groupby(['game_id','posteam'])
    t=pd.DataFrame({'proe':g.pass_oe.mean()/100,'ed_pass':d[d.early].groupby(['game_id','posteam']).qb_dropback.mean(),
       'deep':g.deep.mean(),'sack_r':d[d.qb_dropback==1].groupby(['game_id','posteam']).sack.mean(),
       'run_sr':d[d.rush==1].groupby(['game_id','posteam']).success.mean(),'pass_sr':d[d.qb_dropback==1].groupby(['game_id','posteam']).success.mean(),
       'run_expl':d[d.rush==1].groupby(['game_id','posteam']).expl.mean(),'pass_expl':d[d.qb_dropback==1].groupby(['game_id','posteam']).expl.mean(),
       'press':g.press.mean(),'blitz':g.blitz.mean(),'man':g.man.mean()}).reset_index()
    out.append(t)
T=pd.concat(out); T.to_parquet('data/nfl_matchup_games.parquet')
print(T.describe().T[['count','mean']])

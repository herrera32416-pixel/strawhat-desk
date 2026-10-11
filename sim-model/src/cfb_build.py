"""CFB team-game drive/play features from cfbfastR-style pbp (/workspace/cfbpbp 2021-2026) + ESPN BET closing lines (eval/oct10/bt_games)."""
import pandas as pd, numpy as np
C=['game_id','season','week','season_type','start_date','home','away','pos_team','def_pos_team','drive_id','drive_result','passer_player_name','pass','rush','EPA','success','yards_gained','yards_to_goal','down','distance','play_type','home_wp_before','home_team_division','away_team_division']
rows=[];qbs=[];gms=[]
for y in range(2021,2027):
    d=pd.read_parquet(f'/workspace/cfbpbp/pbp_{y}.parquet',columns=C)
    d=d[d.pos_team.notna()]
    gms.append(d.groupby('game_id').agg(season=('season','first'),week=('week','first'),stype=('season_type','first'),start=('start_date','first'),home_team=('home','first'),away_team=('away','first'),hd=('home_team_division','first'),ad=('away_team_division','first')).reset_index())
    sc=d[(d['pass']==1)|(d.rush==1)]
    sc=sc.assign(expl=(sc.yards_gained>=20).astype(float))
    pl=sc.groupby(['game_id','pos_team','def_pos_team']).agg(plays=('EPA','size'),epa=('EPA','mean'),sr=('success','mean'),expl=('expl','mean'),pass_rate=('pass','mean')).reset_index()
    dr=d.groupby(['game_id','pos_team','drive_id']).drive_result.first().reset_index()
    r=dr.drive_result.fillna('')
    dr['td']=r.eq('TD'); dr['fg']=r.eq('FG'); dr['tov']=r.isin(['INT','FUMBLE','INT TD','FUMBLE RETURN TD','FUMBLE TD'])
    dr=dr[~r.isin(['END OF GAME','END OF 4TH QUARTER','Uncategorized','KICKOFF'])]
    ds=dr.groupby(['game_id','pos_team']).agg(drives=('td','size'),td=('td','sum'),fg=('fg','sum'),tov=('tov','sum')).reset_index()
    rz=sc[sc.yards_to_goal<=20].groupby(['game_id','pos_team','drive_id']).size().reset_index()[['game_id','pos_team','drive_id']].merge(dr[['game_id','pos_team','drive_id','td']])
    rz=rz.groupby(['game_id','pos_team']).agg(rz_trips=('td','size'),rz_td=('td','sum')).reset_index()
    f=d[(d.down==4)&(d.distance<=2)&d.yards_to_goal.between(30,60)]
    f=f.assign(go=((f['pass']==1)|(f.rush==1))).groupby(['game_id','pos_team']).agg(fd_n=('go','size'),fd_go=('go','sum')).reset_index()
    t=pl.merge(ds,on=['game_id','pos_team'],how='left').merge(rz,on=['game_id','pos_team'],how='left').merge(f,on=['game_id','pos_team'],how='left').fillna(0)
    t['fga']=0;t['fgm']=0;rows.append(t)
    q=sc[sc['pass']==1].groupby(['game_id','pos_team','passer_player_name']).agg(db=('EPA','size'),qepa=('EPA','mean')).reset_index(); qbs.append(q)
tg=pd.concat(rows).rename(columns={'pos_team':'posteam','def_pos_team':'defteam'})
tg=tg[tg.drives>=5]
qb=pd.concat(qbs).rename(columns={'pos_team':'posteam','passer_player_name':'passer_player_id'})
g=pd.concat(gms).drop_duplicates('game_id')
g['gameday']=pd.to_datetime(g.start,utc=True).dt.tz_convert('America/Chicago')
# QB starter per game (most dropbacks) - assumes starter is known at kickoff
st=qb.sort_values('db').groupby(['game_id','posteam']).tail(1)
g=g.merge(st.rename(columns={'posteam':'home_team','passer_player_id':'home_qb_id'})[['game_id','home_team','home_qb_id']],on=['game_id','home_team'],how='left')
g=g.merge(st.rename(columns={'posteam':'away_team','passer_player_id':'away_qb_id'})[['game_id','away_team','away_qb_id']],on=['game_id','away_team'],how='left')
bt=pd.read_parquet('/workspace/eval/oct10/bt_games.parquet')
bt=bt.drop(columns=['game_id']).rename(columns={'espn_id':'game_id'}); bt['game_id']=bt.game_id.astype(int); bt=bt.drop_duplicates('game_id')
g['game_id']=g.game_id.astype(int)
g=g.merge(bt[['game_id','neutral','home_score','away_score','close_spread','close_total','close_h_sp_price','close_a_sp_price','close_h_ml','close_a_ml','open_spread','open_total']],on='game_id',how='left')
g['result']=g.home_score-g.away_score; g['total']=g.home_score+g.away_score
g['spread_line']=-g.close_spread; g['total_line']=g.close_total
g=g.rename(columns={'close_h_ml':'home_moneyline','close_a_ml':'away_moneyline','close_h_sp_price':'home_spread_odds','close_a_sp_price':'away_spread_odds'})
g['over_odds']=np.nan;g['under_odds']=np.nan
g['location']=np.where(g.neutral==1,'Neutral','Home'); g['div_game']=0; g['roof']='';g['surface']='';g['temp']=np.nan;g['wind']=np.nan
g=g.sort_values('gameday')
for side in ('home','away'):
    pass
# rest days
long=pd.concat([g[['game_id','gameday','home_team']].rename(columns={'home_team':'t'}),g[['game_id','gameday','away_team']].rename(columns={'away_team':'t'})]).sort_values('gameday')
long['rest']=long.groupby('t').gameday.diff().dt.days.fillna(14).clip(upper=14)
g=g.merge(long.rename(columns={'t':'home_team','rest':'home_rest'})[['game_id','home_team','home_rest']],on=['game_id','home_team']).merge(long.rename(columns={'t':'away_team','rest':'away_rest'})[['game_id','away_team','away_rest']],on=['game_id','away_team'])
# week key: ISO week of game date (keeps bowls in order)
g['gametime']='';g['game_type']=np.where(g.stype=='postseason','POST','REG')
iso=g.gameday.dt.isocalendar(); g['week']=((g.gameday-g.groupby('season').gameday.transform('min')).dt.days//7)+1
fbs_games=set(g.game_id[(g.hd=='fbs')|(g.ad=='fbs')]); tg['game_id']=tg.game_id.astype(int); qb['game_id']=qb.game_id.astype(int)
tg=tg[tg.game_id.isin(fbs_games)]; qb=qb[qb.game_id.isin(fbs_games)]; g=g[g.game_id.isin(fbs_games)]  # FCS-only games have no drive results in source
tg.to_parquet('data/cfb_team_games.parquet'); qb.to_parquet('data/cfb_qb_games.parquet'); g.to_csv('data/cfb_games.csv',index=False)
print(tg.shape,qb.shape,g.shape,g.spread_line.notna().sum()); print(tg[['drives','td','fg','tov','epa']].mean())

"""Build NFL team-game drive/play features from nflverse pbp (2012-2025) + games.csv lines."""
import pandas as pd, numpy as np
cols=['game_id','season','week','season_type','posteam','defteam','fixed_drive','fixed_drive_result','epa','success','play_type',
'qb_dropback','passer_player_id','passer_player_name','yards_gained','down','fourth_down_converted','fourth_down_failed','ydstogo','yardline_100',
'field_goal_result','kick_distance','interception','fumble_lost','wp','half_seconds_remaining','drive_start_yard_line','penalty']
rows=[];qbrows=[]
for y in range(2012,2026):
    d=pd.read_parquet(f'data/nfl/pbp_{y}.parquet',columns=cols)
    d=d[d.season_type.isin(['REG','POST'])&d.posteam.notna()]
    sc=d[d.play_type.isin(['pass','run'])]
    g=sc.groupby(['game_id','posteam','defteam'])
    pl=g.agg(plays=('epa','size'),epa=('epa','mean'),sr=('success','mean'),
             expl=('yards_gained',lambda s:(s>=20).mean()),pass_rate=('qb_dropback','mean'),
             to=('interception','sum')).reset_index()
    fl=sc.groupby(['game_id','posteam']).fumble_lost.sum().rename('fum').reset_index()
    pl=pl.merge(fl,on=['game_id','posteam']); pl['to']=pl['to']+pl['fum']
    # drives
    dr=d.groupby(['game_id','posteam','fixed_drive']).fixed_drive_result.first().reset_index()
    dr['td']=dr.fixed_drive_result.eq('Touchdown'); dr['fg']=dr.fixed_drive_result.eq('Field goal')
    dr['tov']=dr.fixed_drive_result.isin(['Turnover','Opp touchdown']); dr['eoh']=dr.fixed_drive_result.eq('End of half')
    ds=dr.groupby(['game_id','posteam']).agg(drives=('td','size'),td=('td','sum'),fg=('fg','sum'),tov=('tov','sum'),eoh=('eoh','sum')).reset_index()
    # red zone: drives reaching yardline<=20 and TD
    rz=d[d.yardline_100<=20].groupby(['game_id','posteam','fixed_drive']).fixed_drive_result.first().reset_index()
    rz=rz.groupby(['game_id','posteam']).agg(rz_trips=('fixed_drive_result','size'),rz_td=('fixed_drive_result',lambda s:(s=='Touchdown').sum())).reset_index()
    # 4th down aggressiveness: go rate on 4th & <=3 between own 40 and opp 30? simple: 4th&<=2 outside FG-only zone, wp 0.2-0.8
    f=d[(d.down==4)&(d.ydstogo<=2)&(d.wp.between(.2,.8))&(d.yardline_100.between(30,60))]
    f=f.assign(go=f.play_type.isin(['pass','run'])&(f.penalty!=1)).groupby(['game_id','posteam']).agg(fd_n=('go','size'),fd_go=('go','sum')).reset_index()
    # FG accuracy (special teams)
    fgk=d[d.play_type=='field_goal'].assign(m=lambda x:x.field_goal_result.eq('made')).groupby(['game_id','posteam']).agg(fga=('m','size'),fgm=('m','sum')).reset_index()
    t=pl.merge(ds,on=['game_id','posteam'],how='left').merge(rz,on=['game_id','posteam'],how='left').merge(f,on=['game_id','posteam'],how='left').merge(fgk,on=['game_id','posteam'],how='left')
    t['season']=y; rows.append(t)
    # QB per game: dropback EPA by passer
    q=sc[sc.qb_dropback==1].groupby(['game_id','posteam','passer_player_id']).agg(db=('epa','size'),qepa=('epa','mean')).reset_index()
    q['season']=y; qbrows.append(q)
tg=pd.concat(rows).fillna(0); qb=pd.concat(qbrows)
tg.to_parquet('data/nfl_team_games.parquet'); qb.to_parquet('data/nfl_qb_games.parquet')
print(tg.shape, tg.describe().T[['mean']])

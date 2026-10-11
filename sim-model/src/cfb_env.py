"""CFB environment: venue (ESPN core API: city/state/zip, grass, indoor) -> Open-Meteo geocode (lat/lon/elev)
-> Open-Meteo historical archive hourly weather at kickoff; travel distance for the away team; altitude.
Venue known from cfbfastR schedules 2023-26; 2021-22 games use the home team's usual venue (neutral sites wrong there)."""
import pandas as pd, numpy as np, requests, json, glob, os, time
from concurrent.futures import ThreadPoolExecutor
D='data/cfb_env'
s=pd.concat([pd.read_parquet(f) for f in sorted(glob.glob('/workspace/cfb_raw/cfb_schedules_20*.parquet'))])
g=pd.read_csv('data/cfb_games.csv'); g['gameday']=pd.to_datetime(g.gameday,utc=True)
s['game_id']=s.game_id.astype(int)
g=g.merge(s[['game_id','venue_id']],on='game_id',how='left')
home_venue=g.dropna(subset=['venue_id'])[g.neutral!=1].groupby('home_team').venue_id.agg(lambda x:x.mode().iloc[0])
g['venue_id']=g.venue_id.fillna(g.home_team.map(home_venue))
vids=sorted(set(g.venue_id.dropna().astype(int)))
vf=f'{D}/venues.json'; V=json.load(open(vf)) if os.path.exists(vf) else {}
def getv(v):
    if str(v) in V: return
    for _ in range(3):
        try:
            j=requests.get(f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{v}',timeout=20).json()
            a=j.get('address',{}); V[str(v)]={'name':j.get('fullName'),'city':a.get('city'),'state':a.get('state'),'zip':a.get('zipCode'),'grass':j.get('grass'),'indoor':j.get('indoor')}; return
        except Exception: time.sleep(1)
with ThreadPoolExecutor(8) as ex: list(ex.map(getv,vids))
for v,x in V.items():
    if 'lat' in x or not x.get('city'): continue
    try:
        r=requests.get('https://geocoding-api.open-meteo.com/v1/search',params={'name':x['city'],'count':10,'country_code':'US'},timeout=20).json().get('results',[])
        best=[c for c in r if x.get('zip') and x['zip'][:5] in (c.get('postcodes') or [])] or r
        if best: x.update(lat=best[0]['latitude'],lon=best[0]['longitude'],elev=best[0].get('elevation'))
    except Exception as e: pass
json.dump(V,open(vf,'w'))
print('venues',len(vids),'geocoded',sum('lat' in x for x in V.values()))
g['vlat']=g.venue_id.map(lambda v:V.get(str(int(v)),{}).get('lat') if pd.notna(v) else None)
g['vlon']=g.venue_id.map(lambda v:V.get(str(int(v)),{}).get('lon') if pd.notna(v) else None)
g['elev']=g.venue_id.map(lambda v:V.get(str(int(v)),{}).get('elev') if pd.notna(v) else None)
g['indoor']=g.venue_id.map(lambda v:V.get(str(int(v)),{}).get('indoor') if pd.notna(v) else None)
g['grass']=g.venue_id.map(lambda v:V.get(str(int(v)),{}).get('grass') if pd.notna(v) else None)
# travel: away team's home venue -> game venue (great circle miles)
hv=home_venue.map(lambda v:(V.get(str(int(v)),{}).get('lat'),V.get(str(int(v)),{}).get('lon')))
def hav(a,b,c,d):
    a,b,c,d=map(np.radians,[a,b,c,d]); return 3959*2*np.arcsin(np.sqrt(np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2))
al=g.away_team.map(lambda t:hv.get(t,(None,None))[0]); ao=g.away_team.map(lambda t:hv.get(t,(None,None))[1])
g['travel_mi']=hav(al.astype(float),ao.astype(float),g.vlat.astype(float),g.vlon.astype(float))
# weather: one archive call per venue per season covering all its game dates, hourly, UTC
wf=f'{D}/weather.parquet'
W=pd.read_parquet(wf) if os.path.exists(wf) else pd.DataFrame(columns=['game_id'])
todo=g[g.vlat.notna()&~g.game_id.isin(W.game_id)&(g.gameday<pd.Timestamp('2026-10-09',tz='UTC'))]
rows=[]
def wx(key):
    (lat,lon),grp=key
    d0=grp.gameday.min().strftime('%Y-%m-%d'); d1=(grp.gameday.max()+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for _ in range(4):
        try:
            j=requests.get('https://archive-api.open-meteo.com/v1/archive',params={'latitude':lat,'longitude':lon,'start_date':d0,'end_date':d1,
               'hourly':'temperature_2m,wind_speed_10m,precipitation','temperature_unit':'fahrenheit','wind_speed_unit':'mph','precipitation_unit':'inch','timezone':'GMT'},timeout=60)
            if j.status_code==429: time.sleep(20); continue
            h=pd.DataFrame(j.json()['hourly']); h['time']=pd.to_datetime(h.time,utc=True); h=h.set_index('time')
            out=[]
            for _,r in grp.iterrows():
                t=r.gameday.floor('h'); w=h.loc[t:t+pd.Timedelta(hours=3)]
                if len(w): out.append({'game_id':r.game_id,'wx_temp':w.temperature_2m.mean(),'wx_wind':w.wind_speed_10m.mean(),'wx_precip':w.precipitation.sum()})
            return out
        except Exception: time.sleep(5)
    return []
keys=list(todo.groupby([todo.vlat.round(4).astype(str)+'_'+todo.vlon.round(4).astype(str),todo.season]))
keys=[((float(k[0].split('_')[0]),float(k[0].split('_')[1])),grp) for k,grp in keys]
with ThreadPoolExecutor(4) as ex:
    for r in ex.map(wx,keys): rows+=r
W=pd.concat([W,pd.DataFrame(rows)]); W.to_parquet(wf)
g=g.merge(W,on='game_id',how='left')
# returning production: share of team's prior-season pass+rush+rec yards by players on this season's roster (2024+ only; needs prior-season stats)
rp=[]
for y in range(2024,2027):
    st=pd.read_parquet(f'/workspace/cfb_raw/player_stats_{y-1}.parquet',columns=['team','completion_player_id','completion_yds','rush_player_id','rush_yds','reception_player_id','reception_yds'])
    parts=[st[['team',f'{a}_player_id',f'{a}_yds']].rename(columns={f'{a}_player_id':'pid',f'{a}_yds':'yds'}) for a in ('completion','rush','reception')]
    p=pd.concat(parts).dropna(); p['pid']=p.pid.astype(str).str.replace(r'\.0$','',regex=True)
    tot=p.groupby('team').yds.sum(); pp=p.groupby(['team','pid']).yds.sum().reset_index()
    ro=pd.read_parquet(f'/workspace/cfb_raw/rosters_{y}.parquet',columns=['athlete_id','team']); ro['pid']=ro.athlete_id.astype(str)
    pp['ret']=pp.set_index(['team','pid']).index.isin(ro.set_index(['team','pid']).index)
    r=(pp[pp.ret].groupby('team').yds.sum()/tot).rename('ret_off').reset_index(); r['season']=y; rp.append(r)
RP=pd.concat(rp)
for side in ('home','away'):
    g=g.merge(RP.rename(columns={'team':f'{side}_team','ret_off':f'{side}_ret_off'}),on=[f'{side}_team','season'],how='left')
g.to_csv('data/cfb_games_env.csv',index=False)
print(g[['travel_mi','elev','wx_temp','wx_wind','wx_precip','home_ret_off','away_ret_off']].describe().T[['count','mean']])

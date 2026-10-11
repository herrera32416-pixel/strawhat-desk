"""Archived Open-Meteo forecasts (historical-forecast API: stored weather-model forecast runs) at kickoff, NFL open-air home games 2022-2026.
Neutral-site games and closed/dome/retractable roofs get no forecast (dome=0 wind). Stadium coords = public venue locations."""
import pandas as pd, numpy as np, requests, time
C={'BUF':(42.774,-78.787),'MIA':(25.958,-80.239),'NE':(42.091,-71.264),'NYJ':(40.813,-74.074),'NYG':(40.813,-74.074),'BAL':(39.278,-76.623),
'CIN':(39.095,-84.516),'CLE':(41.506,-81.700),'PIT':(40.447,-80.016),'JAX':(30.324,-81.637),'TEN':(36.166,-86.771),'DEN':(39.744,-105.020),
'KC':(39.049,-94.484),'PHI':(39.901,-75.168),'WAS':(38.908,-76.864),'CHI':(41.862,-87.617),'GB':(44.501,-88.062),'CAR':(35.226,-80.853),
'TB':(27.976,-82.503),'SF':(37.403,-121.970),'SEA':(47.595,-122.332),'LV':(36.091,-115.184),'LAC':(33.953,-118.339),'LA':(33.953,-118.339),
'ARI':(33.528,-112.263),'DAL':(32.748,-97.093),'HOU':(29.685,-95.411),'IND':(39.760,-86.164),'ATL':(33.755,-84.401),'DET':(42.340,-83.046),'MIN':(44.974,-93.258),'NO':(29.951,-90.081)}
G=pd.read_csv('data/nfl/games.csv'); G=G[(G.season>=2022)&(G.roof=='outdoors')&(G.location!='Neutral')].copy()
G['kick']=pd.to_datetime(G.gameday+' '+G.gametime).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
rows=[]
for (t,s),grp in G.groupby(['home_team','season']):
    lat,lon=C[t]; d0=grp.kick.min().strftime('%Y-%m-%d'); d1=(grp.kick.max()+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for _ in range(4):
        r=requests.get('https://historical-forecast-api.open-meteo.com/v1/forecast',params={'latitude':lat,'longitude':lon,'start_date':d0,'end_date':min(d1,'2026-10-10'),
            'hourly':'wind_speed_10m,temperature_2m','wind_speed_unit':'mph','temperature_unit':'fahrenheit','timezone':'GMT'},timeout=60)
        if r.status_code==200: break
        time.sleep(15)
    h=pd.DataFrame(r.json()['hourly']); h['time']=pd.to_datetime(h.time,utc=True); h=h.set_index('time')
    for _,g in grp.iterrows():
        w=h.loc[g.kick.floor('h'):g.kick+pd.Timedelta(hours=3)]
        rows.append({'game_id':g.game_id,'fc_wind':w.wind_speed_10m.mean(),'fc_temp':w.temperature_2m.mean(),'rec_wind':g.wind,'rec_temp':g.temp})
W=pd.DataFrame(rows); W.to_parquet('data/nfl_hist_forecast.parquet')
print(len(W),W.describe().T[['count','mean']]); print('corr wind fc vs recorded',W[['fc_wind','rec_wind']].corr().iloc[0,1])

"""Paper picks for an upcoming NFL slate: sim v2 (less shrinkage + walk-forward stretch) vs current DK lines (desk Odds API pull),
Open-Meteo kickoff forecast for open-air stadiums, ESPN QB status, news-delta flags, one-line matchup note."""
import pandas as pd, numpy as np, json, gzip, requests, sys
from scipy.stats import norm
from evalx import novig
ODDS=sys.argv[1]; WEEK=int(sys.argv[2]); OUT=sys.argv[3]
P=pd.read_parquet('out/nfl_v2_preds.parquet'); P=P[(P.season==2026)&(P.week==WEEK)]
hist=P0=pd.read_parquet('out/nfl_v2_preds.parquet'); tr=hist[(hist.season<2026)&hist.result.notna()]
sdm=float(np.std(tr.result-tr.sim_margin)); sdt=float(np.std(tr.total-tr.sim_total))
import os
FX=pd.read_parquet('out/nfl_features_v2mx.parquet').set_index('game_id') if os.path.exists('out/nfl_features_v2mx.parquet') else None
G=pd.read_csv('data/nfl/games.csv').set_index('game_id')
od=json.load(gzip.open(ODDS)); TEAM={'ARI':'Arizona Cardinals','ATL':'Atlanta Falcons','BAL':'Baltimore Ravens','BUF':'Buffalo Bills','CAR':'Carolina Panthers','CHI':'Chicago Bears','CIN':'Cincinnati Bengals','CLE':'Cleveland Browns','DAL':'Dallas Cowboys','DEN':'Denver Broncos','DET':'Detroit Lions','GB':'Green Bay Packers','HOU':'Houston Texans','IND':'Indianapolis Colts','JAX':'Jacksonville Jaguars','KC':'Kansas City Chiefs','LV':'Las Vegas Raiders','LAC':'Los Angeles Chargers','LA':'Los Angeles Rams','MIA':'Miami Dolphins','MIN':'Minnesota Vikings','NE':'New England Patriots','NO':'New Orleans Saints','NYG':'New York Giants','NYJ':'New York Jets','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers','SF':'San Francisco 49ers','SEA':'Seattle Seahawks','TB':'Tampa Bay Buccaneers','TEN':'Tennessee Titans','WAS':'Washington Commanders'}
# open-air stadium coordinates (public venue locations); domes/closed roofs get no wind flag
OPEN={'JAX':(30.324,-81.637),'GB':(44.501,-88.062),'MIA':(25.958,-80.239),'NE':(42.091,-71.264),'NYJ':(40.813,-74.074),'PIT':(40.447,-80.016),'TEN':(36.166,-86.771),'WAS':(38.908,-76.864),'SEA':(47.595,-122.332),'DAL':None,'ARI':None,'ATL':None,'NO':None,'LAC':None,'LA':None}
inj=json.load(open(sys.argv[4] if len(sys.argv)>4 else 'data/espn_nfl_injuries_20261010.json'))
qbnote={}
for t in inj.get('injuries',[]):
    for i in t.get('injuries',[]):
        a=i.get('athlete',{})
        if a.get('position',{}).get('abbreviation')=='QB' and i.get('status')!='Active': qbnote.setdefault(t['displayName'],[]).append(f"{a.get('displayName')} {i.get('status')}")
def tier(e): e=abs(e); return 'A' if e>=8 else 'B' if e>=5 else 'C' if e>=2 else 'none'
def mnote(gid,home,away):
    if FX is None or gid not in FX.index: return 'matchup note unavailable (tendency features not built in this run)'
    f=FX.loc[gid]; notes=[]
    for o,d,ot,dt in (('h','a',home,away),('a','h',away,home)):
        sp=f[f'{o}_o_sack_r']-FX[f'{o}_o_sack_r'].mean(); pr=f[f'{d}_d_press']-FX[f'{d}_d_press'].mean()
        notes.append((abs(sp)+abs(pr), f"{ot} sack rate {100*f[f'{o}_o_sack_r']:.1f}% vs {dt} pressure {100*f[f'{d}_d_press']:.0f}%"))
        rs=f[f'{o}_o_run_sr']-FX[f'{o}_o_run_sr'].mean(); dr=f[f'{d}_d_run_sr']-FX[f'{d}_d_run_sr'].mean()
        notes.append((abs(rs)+abs(dr), f"{ot} run success {100*f[f'{o}_o_run_sr']:.0f}% vs {dt} run D allowing {100*f[f'{d}_d_run_sr']:.0f}%"))
        de=f[f'{o}_o_deep']-FX[f'{o}_o_deep'].mean(); dx=f[f'{d}_d_pass_expl']-FX[f'{d}_d_pass_expl'].mean()
        notes.append((abs(de)*2+abs(dx)*2, f"{ot} deep-pass rate {100*f[f'{o}_o_deep']:.0f}% vs {dt} explosive-pass allowed {100*f[f'{d}_d_pass_expl']:.1f}%"))
    return max(notes)[1]+' (descriptive; matchup layer did not improve backtests, so it is not in the numbers)'
# v3 line-error totals model (research; fit on all played games <2026): total - close ~ env features
from sklearn.linear_model import Ridge
FV=pd.read_parquet('out/nfl_features_v2.parquet')[['game_id','h_qbadj','a_qbadj','wind_f','cold','dome','turf']]
TD=hist.merge(FV,on='game_id').merge(pd.read_parquet('data/nfl_hist_forecast.parquet')[['game_id','fc_wind','fc_temp']],on='game_id',how='left')
_mw=TD.wind_f.median()
TD['wind_f']=np.where(TD.dome==1,0,np.where(TD.season>=2022,TD.fc_wind.fillna(_mw),TD.wind_f))   # archived forecasts for 2022+ (v3.1)
TD['cold']=np.where(TD.dome==1,0,np.where(TD.season>=2022,(50-TD.fc_temp.fillna(60)).clip(0,None),TD.cold))
TD['gap_t']=TD.sim_total-TD.total_line; TD['qbchg']=((TD.h_qbadj.abs()>.02)|(TD.a_qbadj.abs()>.02)).astype(int); TD['wind15']=(TD.wind_f>=15).astype(int)
XT=['gap_t','wind_f','wind15','cold','dome','turf','qbchg']; TT=TD[(TD.season<2026)&TD.result.notna()]
RT=Ridge(alpha=50).fit(TT[XT],TT.total-TT.total_line); RSD=float(np.std(TT.total-TT.total_line-RT.predict(TT[XT])))
games=[]
for _,r in P.sort_values(['game_id']).iterrows():
    g=G.loc[r.game_id]; H,A=TEAM[r.home],TEAM[r.away]
    ev=[e for e in od['data'] if e['home_team']==H and e['away_team']==A]
    if not ev: continue
    ev=ev[0]; bk={b['key']:b for b in ev['bookmakers']}; book='bovada' if 'bovada' in bk else 'draftkings'
    mk={m['key']:m for m in bk[book]['markets']}
    def oc(m,name): return [o for o in mk[m]['outcomes'] if o['name']==name][0]
    hml,aml=oc('h2h',H)['price'],oc('h2h',A)['price']; hs=oc('spreads',H); as_=oc('spreads',A); ov=oc('totals','Over'); un=oc('totals','Under')
    m2,t2=r.sim_margin,r.sim_total
    p_home=1-norm.cdf(-m2/sdm); p_hcov=1-norm.cdf((-hs['point']-m2)/sdm); p_over=1-norm.cdf((ov['point']-t2)/sdt)
    mk_home=float(novig(hml,aml)); mk_hcov=float(novig(hs['price'],as_['price'])); mk_over=float(novig(ov['price'],un['price']))
    out=[]
    for name,ps,pm,yes,no in (('ml',p_home,mk_home,(f'{r.home} ML',hml),(f'{r.away} ML',aml)),('spread',p_hcov,mk_hcov,(f"{r.home} {hs['point']:+g}",hs['price']),(f"{r.away} {as_['point']:+g}",as_['price'])),('total',p_over,mk_over,(f"Over {ov['point']:g}",ov['price']),(f"Under {un['point']:g}",un['price']))):
        y=ps>=pm; s=yes if y else no; sp_=ps if y else 1-ps; mp=pm if y else 1-pm
        out.append({'market':name,'pick':s[0],'price':s[1],'sim_pct':round(100*sp_,1),'market_pct':round(100*mp,1),'gap_pts':round(100*(sp_-mp),1),'tier':tier(100*(sp_-mp)),'status':'paper'})
    # weather forecast at kickoff for open-air venues
    wx=None; flags=[]
    ll_=OPEN.get(r.home)
    if ll_:
        kt=pd.Timestamp(ev['commence_time'])
        j=requests.get('https://api.open-meteo.com/v1/forecast',params={'latitude':ll_[0],'longitude':ll_[1],'hourly':'wind_speed_10m,wind_gusts_10m,temperature_2m,precipitation_probability','wind_speed_unit':'mph','temperature_unit':'fahrenheit','timezone':'GMT','start_date':kt.strftime('%Y-%m-%d'),'end_date':kt.strftime('%Y-%m-%d')},timeout=30).json()
        h=pd.DataFrame(j['hourly']); h['time']=pd.to_datetime(h.time,utc=True); w=h[(h.time>=kt.floor('h'))&(h.time<=kt+pd.Timedelta(hours=3))]
        wx={'wind_mph':round(w.wind_speed_10m.mean(),1),'gust_mph':round(w.wind_gusts_10m.max(),1),'temp_f':round(w.temperature_2m.mean()),'precip_prob':int(w.precipitation_probability.max())}
        if wx['wind_mph']>=15: flags.append(f"WIND-UNDER: forecast {wx['wind_mph']} mph (15+ mph unders hit 57% in our 2015-25 sample; paper only)")
    fr=FV.set_index('game_id').loc[r.game_id]; wind=(wx or {}).get('wind_mph',0.0) if fr.dome==0 else 0.0
    xv=pd.DataFrame([{'gap_t':t2-ov['point'],'wind_f':wind,'wind15':int(wind>=15),'cold':max(0,50-(wx or {}).get('temp_f',60)) if fr.dome==0 else 0,'dome':fr.dome,'turf':fr.turf,'qbchg':int(abs(r.home_qbadj)>.02 or abs(r.away_qbadj)>.02)}])
    pe=float(RT.predict(xv[XT])[0]); po3=float(1-norm.cdf((-pe)/RSD))
    out[2]['v3_line_error_model']={'over_price':ov['price'],'under_price':un['price'],'pred_total_minus_line':round(pe,2),'over_pct':round(100*po3,1),'note':'v3.1 research model (trained with archived forecasts 2022+; forecast-weather walk-forward 2022-25: LL 0.6905 vs close 0.6932, +4.2% ROI at 4+ pts) - paper'}
    for t,full,qa in ((r.home,H,r.home_qbadj),(r.away,A,r.away_qbadj)):
        if abs(qa)>0.02:
            gap=(m2-(-hs['point'])) if t==r.home else ((-hs['point'])-m2)
            flags.append(f"QB-CHANGE {t}: starter {g.home_qb_name if t==r.home else g.away_qb_name} vs recent starter (QB adj {qa:+.2f} EPA/db). Sim vs line on {t}'s side: {gap:+.1f} pts" + (' -> line may not fully reflect it' if gap<-2 else ''))
    games.append({'game_id':r.game_id,'kickoff_utc':ev['commence_time'],'away':r.away,'home':r.home,'book':book,
      'qbs':{'away':g.away_qb_name,'home':g.home_qb_name,'espn_qb_injuries':{t:qbnote.get(TEAM[t],[]) for t in (r.away,r.home)}},
      'sim':{'home_pts':round((t2+m2)/2,1),'away_pts':round((t2-m2)/2,1),'margin':round(m2,1),'total':round(t2,1)},
      'markets':out,'weather':wx,'news_delta_flags':flags,'matchup_note':mnote(r.game_id,r.home,r.away)})
doc={'league':'nfl','slate':'Sun Oct 11 + Mon Oct 12 2026 (nflverse week 5)','sim_version':'v2 (less shrinkage, walk-forward margin/total stretch; Normal probs)','sim_live':False,
 'lines':f"{od['pulled_ct']} desk Odds API pull (no new credits spent); Bovada not in that pull, DraftKings used",
 'note':'PAPER. v2 still loses to the closing line in walk-forward tests; tier = size of sim-vs-market gap, NOT proven edge.','games':games}
json.dump(doc,open(OUT,'w'),indent=1,default=float); print(len(games))

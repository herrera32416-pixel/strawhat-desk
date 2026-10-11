"""Forward paper tracking for v3.1 NFL totals line-error picks. PAPER ONLY - nothing is bet.
  log   <picks.json> : append each game's v3.1 totals pick (edge >= 2 pts vs no-vig) to out/paper/v3_totals_log.csv (first log per game is kept = pregame snapshot)
  grade              : fill finals from nflverse games.csv, grade at the logged price, $20 flat; write out/paper/v3_totals_summary.md"""
import pandas as pd, numpy as np, json, sys, os, datetime as dt, io, requests
from evalx import am2dec
LOG='out/paper/v3_totals_log.csv'
def log(f):
    d=json.load(open(f)); now=dt.datetime.now().isoformat(timespec='minutes'); rows=[]
    for g in d['games']:
        t=[m for m in g['markets'] if m['market']=='total'][0]; v=t.get('v3_line_error_model')
        if not v: continue
        if pd.Timestamp(g['kickoff_utc'])<=pd.Timestamp.now(tz='UTC'): continue   # never log after kickoff
        line=float(t['pick'].split()[-1]); po=v['over_pct']/100
        # market no-vig over% at the logged prices
        mk_over=t['market_pct']/100 if t['pick'].startswith('Over') else 1-t['market_pct']/100
        edge=po-mk_over; side='Over' if edge>0 else 'Under'
        price=v['over_price'] if side=='Over' else v['under_price']
        rows.append({'logged_ct':now,'game_id':g['game_id'],'kickoff_utc':g['kickoff_utc'],'away':g['away'],'home':g['home'],'book':g['book'],'line':line,'side':side,
                     'price':price,'model_over_pct':round(100*po,1),'market_over_pct':round(100*mk_over,1),'edge_pts':round(100*abs(edge),1),'bet':abs(edge)>=0.02,
                     'wind_mph':(g.get('weather') or {}).get('wind_mph'),'final_total':np.nan,'result':'','pnl_usd':np.nan})
    new=pd.DataFrame(rows)
    if os.path.exists(LOG):
        old=pd.read_csv(LOG); old=old[~old.game_id.isin(new.game_id)]; new=pd.concat([old,new])  # latest PRE-kickoff snapshot wins; post-kickoff rows are never touched
    new.to_csv(LOG,index=False); print('logged',len(rows),'->',LOG)
def grade():
    L=pd.read_csv(LOG); G=pd.read_csv(io.StringIO(requests.get('https://github.com/nflverse/nfldata/raw/master/data/games.csv',timeout=60).text)).set_index('game_id')
    for i,r in L.iterrows():
        if isinstance(r.result,str) and r.result in ('win','loss','push'): continue
        if r.game_id not in G.index or pd.isna(G.loc[r.game_id,'total']): continue
        tot=G.loc[r.game_id,'total']; L.at[i,'final_total']=tot
        if tot==r.line: res='push'
        else: res='win' if (tot>r.line)==(r.side=='Over') else 'loss'
        L.at[i,'result']=res
        if r.bet:
            pr=r.price if pd.notna(r.price) else -110
            L.at[i,'pnl_usd']=0 if res=='push' else (20*(float(am2dec(pr))-1) if res=='win' else -20)
    L.to_csv(LOG,index=False)
    b=L[(L.bet==True)&L.result.fillna('').ne('')]
    md=[f"# v3.1 NFL totals: forward paper record (updated {dt.datetime.now():%Y-%m-%d %H:%M} CT)","",
        f"Bets (edge >= 2 pts, $20 flat, PAPER): {len(b)} graded, {int((b.result=='win').sum())}-{int((b.result=='loss').sum())}-{int((b.result=='push').sum())}, P&L ${b.pnl_usd.sum():.2f}, ROI {100*b.pnl_usd.sum()/max(20*len(b),1):.1f}%",
        f"All logged picks (incl. <2 pt leans): {int((L.result=='win').sum())}-{int((L.result=='loss').sum())}","","Gate stays OFF until Luis approves; target = 4+ weeks forward with ROI > 0."]
    open('out/paper/v3_totals_summary.md','w').write('\n'.join(md)); print('\n'.join(md))
if __name__=='__main__':
    log(sys.argv[2]) if sys.argv[1]=='log' else grade()

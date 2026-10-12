"""Grade Oct 11 2026 paper picks (sides/totals + props) vs ESPN finals & box scores. $20 flat at listed prices."""
import json, re, requests, pandas as pd, numpy as np
from evalx import am2dec
SB=json.load(open('data/espn_sb_final_1011.json'))
AB={'WSH':'WAS','LAR':'LA'}
fin={}
for e in SB['events']:
    c=e['competitions'][0]
    if c['status']['type']['name']!='STATUS_FINAL': continue
    s={AB.get(t['team']['abbreviation'],t['team']['abbreviation']):int(t['score']) for t in c['competitors']}
    h=AB.get([t for t in c['competitors'] if t['homeAway']=='home'][0]['team']['abbreviation'],None) or [t for t in c['competitors'] if t['homeAway']=='home'][0]['team']['abbreviation']
    fin[frozenset(s)]={'eid':e['id'],'s':s}
def pnl(res,price): return 0.0 if res=='P' else (20*(float(am2dec(price))-1) if res=='W' else -20.0)
rows=[]
R=json.load(open('out/picks/nfl_2026_w6_rerun.json')); E=json.load(open('out/picks/nfl_2026_w6_0805.json'))
games={g['game_id']:('rerun',g) for g in R['games']}
for g in E['games']:
    if g['game_id'] not in games: games[g['game_id']]=('0805',g)
for gid,(src,g) in games.items():
    f=fin.get(frozenset({g['home'],g['away']}))
    if not f: continue
    hs,as_=f['s'][g['home']],f['s'][g['away']]; margin=hs-as_; tot=hs+as_
    for m in g['markets']:
        p=m['pick']; price=m['price']
        if m['market']=='ml':
            t=p.split()[0]; r='P' if margin==0 else ('W' if (margin>0)==(t==g['home']) else 'L')
        elif m['market']=='spread':
            t,ln=p.split()[0],float(p.split()[1]); my=margin if t==g['home'] else -margin; v=my+ln; r='P' if v==0 else ('W' if v>0 else 'L')
        else:
            side,ln=p.split()[0],float(p.split()[1]); r='P' if tot==ln else ('W' if (tot>ln)==(side=='Over') else 'L')
        rows.append({'game':f"{g['away']}@{g['home']}",'src':src,'final':f"{g['away']} {as_}-{hs} {g['home']}",'market':m['market'],'pick':p,'price':price,'sim_pct':m['sim_pct'],'mkt_pct':m['market_pct'],'tier':m['tier'],'result':r,'pnl':round(pnl(r,price),2),
                     'v3_over':(m.get('v3_line_error_model') or {}).get('over_pct'),'total':tot,'line':float(p.split()[-1]) if m['market']=='total' else None})
S=pd.DataFrame(rows); S.to_csv('out/paper/sides_2026-10-11.csv',index=False)
# v3 totals read: side = over if over_pct>50
V=S[S.market=='total'].copy(); V['v3_side']=np.where(V.v3_over>50,'Over','Under')
V['v3_res']=[('P' if r.total==r.line else ('W' if (r.total>r.line)==(r.v3_side=='Over') else 'L')) for r in V.itertuples()]
V['v3_edge']=(V.v3_over-50).abs()
# props from rerun md (+ PHI@JAX from 8:02 file)
P=[];cur=None
for l in open('out/picks/nfl_2026_w6_rerun.md'):
    m=re.match(r'## (\w+) @ (\w+),',l)
    if m: cur=f"{m.group(1)}@{m.group(2)}"
    m=re.match(r"\s+- (.+?) \((\w+)\) (Anytime TD|Pass Yds|Rush Yds|Rec Yds|Receptions) (Over|Under|Yes) ?([\d.]*) ([+-]\d+) (DK|Bovada): model ([\d.]+)% vs market ([\d.]+)%(.*)",l)
    if m and cur: P.append({'game':cur,'player':m.group(1),'team':m.group(2),'mkt':m.group(3),'side':m.group(4),'line':float(m.group(5)) if m.group(5) else None,'price':int(m.group(6)),'book':m.group(7),'model':float(m.group(8)),'market':float(m.group(9)),'flag':m.group(10).strip()})
pj=json.load(open('data/props_0802.json'))
for g in pj['games']:
    if g['game'].startswith('Philadelphia'):
        for t in g['top'][:5]:
            if len([x for x in P if x['game']=='PHI@JAX'])>=4: break
            if sum(1 for x in P if x['player']==t['player'])>=2: continue
            P.append({'game':'PHI@JAX','player':t['player'],'team':t['team'],'mkt':t['market'],'side':t['side'],'line':t['line'],'price':t['price'],'book':t['book'],'model':round(100*t['model_pct'],1),'market':round(100*t['market_pct'],1),'flag':'8:02 list'})
box={}
def stats(eid):
    if eid in box: return box[eid]
    d=requests.get(f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}',timeout=30).json(); st={}
    for team in d['boxscore']['players']:
        for cat in team['statistics']:
            keys=cat['keys']
            for a in cat['athletes']:
                n=a['athlete']['displayName']; v=dict(zip(keys,a['stats'])); st.setdefault(n,{})[cat['name']]=v
    box[eid]=st; return st
def num(x):
    try: return float(str(x).split('/')[0])
    except: return None
for p in P:
    a,h=p['game'].split('@'); f=fin.get(frozenset({a,h}))
    if not f: p['actual']=None; p['res']='open'; continue
    st=stats(f['eid']); s=st.get(p['player'])
    if s is None: p['actual']=None; p['res']='VOID (DNP/not in box)'; p['pnl']=0.0; continue
    ps,ru,re_=s.get('passing',{}),s.get('rushing',{}),s.get('receiving',{})
    if p['mkt']=='Pass Yds': act=num(ps.get('passingYards'))
    elif p['mkt']=='Rush Yds': act=num(ru.get('rushingYards',0)) if ru else 0.0
    elif p['mkt']=='Rec Yds': act=num(re_.get('receivingYards',0)) if re_ else 0.0
    elif p['mkt']=='Receptions': act=num(re_.get('receptions',0)) if re_ else 0.0
    else: act=(num(ru.get('rushingTouchdowns',0)) if ru else 0)+(num(re_.get('receivingTouchdowns',0)) if re_ else 0)
    p['actual']=act
    if p['mkt']=='Anytime TD': r='W' if act>=1 else 'L'
    else: r='P' if act==p['line'] else ('W' if (act>p['line'])==(p['side']=='Over') else 'L')
    p['res']=r; p['pnl']=round(pnl(r,p['price']),2)
PR=pd.DataFrame(P); PR.to_csv('out/paper/props_2026-10-11.csv',index=False)
def rec(df,col='result'): return f"{(df[col]=='W').sum()}-{(df[col]=='L').sum()}-{(df[col]=='P').sum()}"
print(S[['final','market','pick','price','sim_pct','mkt_pct','tier','result','pnl','src']].to_string())
for m in ('ml','spread','total'): x=S[S.market==m]; print(m,rec(x),round(x.pnl.sum(),2))
for t in ('A','B','C','none'): x=S[S.tier==t]; print('tier',t,rec(x),round(x.pnl.sum(),2))
print('ALL',rec(S),round(S.pnl.sum(),2))
print(V[['final','line','total','v3_over','v3_side','v3_res']].to_string()); print('v3',rec(V,'v3_res'),'| edge>=2pts:',rec(V[V.v3_edge>=2],'v3_res'))
print(PR[['game','player','mkt','side','line','price','book','model','market','actual','res','pnl','flag']].to_string())
g=PR[PR.res.isin(['W','L','P'])]; print('PROPS',rec(g,'res'),round(g.pnl.sum(),2),'| non-ATD',rec(g[g.mkt!='Anytime TD'],'res'),round(g[g.mkt!='Anytime TD'].pnl.sum(),2),'| ATD',rec(g[g.mkt=='Anytime TD'],'res'),round(g[g.mkt=='Anytime TD'].pnl.sum(),2))
print('exp wins non-ATD model',round(g[g.mkt!='Anytime TD'].model.sum()/100,1),'market',round(g[g.mkt!='Anytime TD'].market.sum()/100,1))

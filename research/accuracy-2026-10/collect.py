import json,subprocess,re
from datetime import datetime,timezone
R='/workspace/strawhat-desk'
def git(*a): return subprocess.run(['git','-C',R,*a],capture_output=True,text=True).stdout
snaps={}
def add(sport,eid,kick,mk,sides,gen,matchup,src):
    if not eid or not kick or not sides or len(sides)!=2: return
    if any(s.get('model_pct') is None for s in sides): return
    k=datetime.fromisoformat(kick.replace('Z','+00:00'))
    if gen>=k: return
    key=(sport,str(eid),mk)
    if key not in snaps or snaps[key]['gen']<=gen:
        snaps[key]=dict(sport=sport,eid=str(eid),mk=mk,kick=kick,gen=gen,matchup=matchup,src=src,
          sides=[{x:s.get(x) for x in('side','label','line','price_american','novig_pct','model_pct')} for s in sides])
def from_paper(d,src):
    gen=datetime.fromisoformat(d['generated_at_ct'])
    for g in d.get('board',[]):
        for mk,me in (g.get('market_edge') or {}).items():
            add(g['sport'],g.get('espn_event_id'),g.get('kick_utc'),mk,me.get('sides') or [],gen,g.get('matchup'),src)
def from_day(d,src):
    t=d.get('generated_at_ct') or d.get('built_at_ct') or d.get('updated_at_ct')
    if not t: return
    gen=datetime.fromisoformat(t)
    rows=[r for k in('clears','fills','holds','passes') for r in (d.get('card') or {}).get(k) or []]
    rows+=d.get('rows') or []
    for r in rows:
        for mk,m in ((r.get('paper') or {}).get('markets') or {}).items():
            add(r.get('sport'),r.get('espn_event_id'),r.get('kick_utc'),mk,m.get('sides') or [],gen,r.get('matchup'),src)
paths=['v1/data/paper.json','docs/data/v1/paper.json','v1/data/today.json','docs/data/v1/today.json']
for p in paths:
    for h in git('log','--format=%h','--',p).split():
        try: d=json.loads(git('show',f'{h}:{p}'))
        except Exception: continue
        (from_paper if 'paper' in p else from_day)(d,f'{h}:{p}')
import glob
for f in glob.glob(R+'/v1/data/2026*.json'):
    try: from_day(json.load(open(f)),f)
    except Exception as e: pass
out=[dict(v,gen=v['gen'].isoformat()) for v in snaps.values()]
json.dump(out,open('/workspace/acc/board_preds.json','w'),indent=0)
from collections import Counter
print(len(out),Counter((o['sport'],o['mk']) for o in out))
print(Counter(o['kick'][:10] for o in out))

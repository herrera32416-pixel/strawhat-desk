import json,urllib.request,os
from datetime import datetime,timedelta
P=json.load(open('/workspace/acc/board_preds.json'))
L={'NFL':'football/nfl','CFB':'football/college-football','NHL':'hockey/nhl','MLB':'baseball/mlb'}
cache='/workspace/acc/sb';os.makedirs(cache,exist_ok=True)
def sb(sp,d):
    f=f'{cache}/{sp}{d}.json'
    if not os.path.exists(f):
        u=f'https://site.api.espn.com/apis/site/v2/sports/{L[sp]}/scoreboard?dates={d}&limit=500'+('&groups=80' if sp=='CFB' else '')
        open(f,'w').write(urllib.request.urlopen(u,timeout=30).read().decode())
    return json.load(open(f))
ev={}
need={(p['sport'],(datetime.fromisoformat(p['kick'].replace('Z','+00:00'))-timedelta(hours=5)+timedelta(days=j)).strftime('%Y%m%d')) for p in P for j in(0,-1)}
for sp,d in need:
    for e in sb(sp,d).get('events',[]):
        c=e['competitions'][0];t=e['status']['type']
        cs={x['homeAway']:x for x in c['competitors']}
        ev[(sp,e['id'])]=dict(done=t['completed'],det=t.get('shortDetail'),h=float(cs['home'].get('score') or 0),a=float(cs['away'].get('score') or 0),hn=cs['home']['team']['displayName'],an=cs['away']['team']['displayName'])
out=[]
for p in P:
    e=ev.get((p['sport'],p['eid']))
    if not e or not e['done']: p['res']='open';out.append(p);continue
    s={x['side']:x for x in p['sides']}
    h,a=e['h'],e['a']
    def win(side):
        x=s[side];ln=x.get('line')
        if p['mk']=='ml': v=(a-h) if side=='away' else (h-a)
        elif p['mk']=='spread': v=((a-h) if side=='away' else (h-a))+float(ln)
        else: v=(h+a-float(ln)) if side=='over' else (float(ln)-h-a)
        return 1 if v>0 else (0 if v<0 else .5)
    ks=list(s)
    if set(ks) not in ({'home','away'},{'over','under'}): p['res']='bad';out.append(p);continue
    for k in ks: s[k]['won']=win(k)
    play=max(ks,key=lambda k:s[k]['model_pct'])
    p['play']=play;p['tie']=s[ks[0]]['model_pct']==s[ks[1]]['model_pct']
    p['res']={1:'W',0:'L',.5:'P'}[s[play]['won']];p['score']=f"{e['an']} {a:g} @ {e['hn']} {h:g} {e['det']}"
    out.append(p)
json.dump(out,open('/workspace/acc/graded.json','w'),indent=0)
from collections import Counter
print(Counter((p['sport'],p['res']) for p in out))

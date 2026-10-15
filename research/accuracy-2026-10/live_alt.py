import json
from collections import defaultdict
G=[p for p in json.load(open('/workspace/acc/graded.json')) if p['res'] in('W','L','P')]
def run(name,key,thr=None):
    d=defaultdict(lambda:[0,0,0,0])
    for p in G:
        s=p['sides'];a,b=s
        if key(a) is None or key(b) is None: continue
        pk=a if key(a)>key(b) else b
        if thr and max(key(a),key(b))<thr: d[p['sport']][3]+=1;continue
        r=pk['won'];d[p['sport']][0 if r==1 else 1 if r==0 else 2]+=1
    tw=sum(v[0] for v in d.values());tl=sum(v[1] for v in d.values())
    print(f"{name:40s} "+'  '.join(f"{k} {v[0]}-{v[1]}-{v[2]} ({v[0]/max(1,v[0]+v[1]):.3f}) skip{v[3]}" for k,v in sorted(d.items()))+f"  ALL {tw}-{tl} {tw/(tw+tl):.3f}")
run('current: higher model%',lambda s:s['model_pct'])
run('higher market no-vig%',lambda s:s['novig_pct'])
for t in(52,55):
    run(f'higher model%, no play <{t}',lambda s:s['model_pct'],t)
    run(f'higher no-vig%, no play <{t}',lambda s:s['novig_pct'],t)

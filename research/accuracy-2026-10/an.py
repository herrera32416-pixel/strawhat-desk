import json,math
from collections import defaultdict
G=[p for p in json.load(open('/workspace/acc/graded.json')) if p['res'] in('W','L','P')]
def row(name,ps):
    w=sum(p['res']=='W' for p in ps);l=sum(p['res']=='L' for p in ps);pu=len(ps)-w-l
    # brier on play side
    bm=bq=n=0
    for p in ps:
        if p['res']=='P':continue
        s={x['side']:x for x in p['sides']}[p['play']];y=1 if p['res']=='W' else 0
        bm+=(s['model_pct']/100-y)**2;bq+=(s['novig_pct']/100-y)**2;n+=1
    mp=sum({x['side']:x for x in p['sides']}[p['play']]['model_pct'] for p in ps)/max(1,len(ps))
    print(f"{name:34s} {w}-{l}-{pu}  hit {w/max(1,w+l):.3f}  avg model% {mp:.1f}  BrierModel {bm/max(1,n):.4f} Mkt {bq/max(1,n):.4f}")
def by(f,ps,title):
    print('--',title);d=defaultdict(list)
    for p in ps:d[f(p)].append(p)
    for k in sorted(d,key=str):row(str(k),d[k])
pl=lambda p:{x['side']:x for x in p['sides']}[p['play']]
row('ALL',G)
by(lambda p:p['sport'],G,'sport')
by(lambda p:(p['sport'],p['mk']),G,'sport x market')
bk=lambda v:'50-55' if v<55 else '55-60' if v<60 else '60+'
by(lambda p:(p['sport'],bk(pl(p)['model_pct'])),G,'sport x model% bucket')
by(lambda p:(p['sport'],p['mk'],'fav' if pl(p)['novig_pct']>50 else 'dog') ,[p for p in G if p['mk']!='total'],'fav/dog (market) of play')
by(lambda p:(p['sport'],p['mk'],p['play']),G,'side of play')
gap=lambda p:pl(p)['model_pct']-pl(p)['novig_pct']
by(lambda p:(p['sport'],'agree' if gap(p)>=0 and pl(p)['novig_pct']>=50 else 'model>mkt but mkt<50' if gap(p)>0 else 'model<mkt'),G,'model vs market on play')
by(lambda p:(p['sport'],'gap<2' if abs(gap(p))<2 else 'gap2-5' if abs(gap(p))<5 else 'gap5+'),G,'|gap| size')
by(lambda p:(p['sport'],pl(p)['line']),[p for p in G if p['mk']=='total'],'total line')

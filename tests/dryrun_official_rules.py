import os;R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys,json; sys.path.insert(0,R); sys.path.insert(0,os.path.join(R,'v1','scripts'))
from datetime import datetime; from zoneinfo import ZoneInfo
import paper_model as pm
from desk import official_rules as o
cfg=o.load()
C=[dict(id='a',sport='CFB',market='spread',side='away',line=14.5,price_american=-110,model_pct=58,edge_pp=6),
 dict(id='b',sport='CFB',market='spread',side='home',line=-7,price_american=-110,model_pct=75,edge_pp=9),
 dict(id='c',sport='CFB',market='spread',side='home',line=-13.5,price_american=-110,model_pct=60,edge_pp=6),
 dict(id='d',sport='MLB',market='f5_ml',side='home',line=None,price_american=-225,model_pct=72,edge_pp=5),
 dict(id='e',sport='MLB',market='ml',side='away',line=None,price_american=120,model_pct=55,edge_pp=9),
 dict(id='f',sport='MLB',market='total',side='under',line=8.5,price_american=-110,model_pct=60,edge_pp=4),
 dict(id='g',sport='NFL',market='spread',side='away',line=3.5,price_american=-110,model_pct=60,edge_pp=4,source='nfl_sim'),
 dict(id='h',sport='NFL',market='teaser',side='x',line=None,price_american=600,model_pct=80,edge_pp=10),
 dict(id='i',sport='NFL',market='anytime_td',side='x',line=None,price_american=150,model_pct=50,edge_pp=10),
 dict(id='j',sport='NFL',market='ml',side='away',line=None,price_american=285,model_pct=40,edge_pp=14),
 dict(id='k',sport='MLB',market='f5_ml',side='home',line=None,price_american=108,model_pct=70,edge_pp=9),
]+[dict(id=f'dog{n}',sport='CFB',market='spread',side='away',line=10+n,price_american=-110,model_pct=56,edge_pp=4+n/10) for n in range(6)]
k,r=o.apply_day(C,cfg)
print('KEPT',[(c['id'],c['edge_pp']) for c in k])
for c,w in r: print('REJ',c['id'],'-',w)
# ledger-level: cap respects already-stamped
led={'picks':[{'slate_date_ct':'2026-10-12','units':1,'status':'open'}]*4}
now=datetime(2026,10,12,9,15,tzinfo=ZoneInfo('America/Chicago'))
print('with 4 stamped today ->',[c['id'] for c in pm.gate_official(led,C,now,cfg)])
print('clv', o.clv_pp(-110,-125), o.clv_pp(+150,+130))

print("\n=== A/B/C grades (cap applies to A only) ===")
import copy
G = o.grade_day(copy.deepcopy(C), cfg)
for g in "ABC":
    print(g, [(c["id"], "; ".join(c["grade_reasons"]) or "all pass") for c in G if c["grade"] == g])

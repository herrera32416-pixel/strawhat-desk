#!/usr/bin/env python3
"""New DESK staging builder (local only). Real feed if present, else labeled mock."""
import json,os,re,html,math,datetime as dt
from zoneinfo import ZoneInfo
H=os.path.dirname(os.path.abspath(__file__))
REAL="/workspace/betsim/desk2/data/games.json"; MOCK=os.path.join(H,"data/mock_games.json")
CT=ZoneInfo("America/Chicago"); E=html.escape
def num(v):
    if isinstance(v,bool) or v is None: return None
    try: v=float(v)
    except (TypeError,ValueError): return None
    return None if math.isnan(v) else v
def pct(v):
    v=num(v); return None if v is None else (v*100 if abs(v)<=1 else v)
def be(o): return 100*(-o/(-o+100) if o<0 else 100/(o+100))
def am(o):
    o=num(o); return "—" if o is None else (f"+{o:g}" if o>0 else f"{o:g}")
def norm(r):
    if "away" not in r and " @ " in (r.get("game") or ""): r["away"],r["home"]=r["game"].split(" @ ",1)
    r.setdefault("away","?"); r.setdefault("home","?")
    if not isinstance(r.get("prices"),dict):
        bk=str(r.get("book") or "").lower(); k="bovada" if "bovada" in bk else "dk" if "draft" in bk else "betr" if "betr" in bk else None
        r["prices"]={k:r.get("best_price")} if k else {}
    r["prices"]={k:num(v) for k,v in r["prices"].items()}
    for k in ("pinnacle_novig_pct","betsim_pct","strawhat_pct","blend_pct"): r[k]=pct(r.get(k))
    a=r.get("agree"); r["agree"]=a.upper()=="AGREE" if isinstance(a,str) else bool(a) if a is not None else None
    if not r.get("game_id"): r["game_id"]=f'{r["away"]}@{r["home"]}|{r.get("kickoff_ct")}'
    return r
def pick(r):
    s=str(r.get("side") or "").strip(); m=r["market"]; ln=num(r.get("line"))
    if s.lower() in ("home","away"): s=r[s.lower()]
    elif s.lower() in ("over","under"): s=s.title()
    if s.lower()=="nan": s=""
    has=bool(re.search(r"[+-]?\d+(\.\d+)?\s*$",s))   # side already carries its line -> don't repeat
    if m!="ml" and ln is not None and not has: s+=f" {ln:+g}" if m=="spread" else f" {ln:g}"
    if m=="ml": s=re.sub(r"\s*\bml\b\s*","",s,flags=re.I).strip()
    return s or "—"
def edge(r):
    b=r["prices"].get("bovada"); f=r["pinnacle_novig_pct"]
    return None if b is None or f is None else f-be(b)
def stars(e): return "★★" if e is not None and e>=3 else "★" if e is not None and e>=1 else ""
def kick(r):
    try: return dt.datetime.fromisoformat(r["kickoff_ct"]).astimezone(CT)
    except Exception: return None
def col(r):
    m=r["market"]; e=edge(r); s=stars(e); f=r["pinnacle_novig_pct"]; pr=r["prices"]
    fair=f'<div class="f">{f:.1f}%</div><div class="fs">fair · {E(str(r.get("novig_source") or "no-vig"))}</div>' if f is not None else '<div class="f na">fair n/a</div><div class="fs">&nbsp;</div>'
    tag=f'<div class="tag s">{s} <small>{e:+.1f}pp</small></div>' if s else '<div class="tag pass">no edge, pass</div>'
    res=f' <span class="r{r["result"]}">{r["result"]}</span>' if r.get("result") in ("W","L","P") else ""
    def p(k): v=r.get(k); return "—" if v is None else f"{v:.0f}%"
    ag="✓ agree" if r["agree"] else "✗ split" if r["agree"] is False else ""
    return f'''<div class="col{' star' if s else ''}"><div class="mk">{ {"ml":"MONEYLINE","spread":"SPREAD","total":"TOTAL"}[m]}{res}</div>
<div class="pk">{E(pick(r))}</div>{fair}{tag}
<div class="px">Bovada <b>{am(pr.get("bovada"))}</b></div><div class="ref">ref DK {am(pr.get("dk"))} · Betr {am(pr.get("betr"))}</div>
<div class="mo"><div class="mg"><div><b>{p("strawhat_pct")}</b><span>Strawhat</span></div><div><b>{p("betsim_pct")}</b><span>Sim Bot</span></div></div>blend {p("blend_pct")} · {ag} · <i>unproven</i></div></div>'''
def main():
    mock=not os.path.exists(REAL); rows=json.load(open(MOCK if mock else REAL))
    if isinstance(rows,dict): rows=rows.get("games",rows.get("rows",[]))
    rows=[norm(r) for r in rows if r.get("market") in ("ml","spread","total")]  # straight bets only
    w=l=p=0
    for r in rows:
        if stars(edge(r)): res=r.get("result"); w+=res=="W"; l+=res=="L"; p+=res=="P"
    today=dt.datetime.now(CT).date(); games={}
    for r in rows:
        k=kick(r)
        if k is None or k.date()<today: continue
        games.setdefault(r["game_id"],[]).append(r)
    cards=[]
    for gid,rs in sorted(games.items(),key=lambda kv:min(kick(r) for r in kv[1])):
        r0=rs[0]; t=kick(r0).strftime("%a %-I:%M %p CT")
        bym={}
        for r in rs:   # one row per market: prefer the starred / higher-edge side
            c=bym.get(r["market"])
            if c is None or (edge(r) or -99)>(edge(c) or -99): bym[r["market"]]=r
        cols="".join(col(bym[m]) if m in bym else '<div class="col empty"><div class="mk">'+m.upper()+'</div><div class="pass">no line</div></div>' for m in ("ml","spread","total"))
        hot=any(stars(edge(r)) for r in bym.values())
        notes=" · ".join(dict.fromkeys(r["notes"] for r in rs if r.get("notes")))
        cards.append(f'''<div class="c{' hot' if hot else ''}"><div class="h">{E(str(r0.get("sport","")))} · {t}</div>
<div class="m">{E(r0["away"])} <span>@</span> {E(r0["home"])}</div><div class="cols">{cols}</div>
{f'<div class="n">{E(notes)}</div>' if notes else ''}</div>''')
    banner='<div class="mock">MOCK DATA — real feed not yet available</div>' if mock else ''
    now=dt.datetime.now(CT).strftime("%b %-d %-I:%M %p CT")
    page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>New DESK</title><style>
*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e8e8e8}}
.top{{padding:12px 14px;background:#1a1d24;position:sticky;top:0;z-index:2;border-bottom:1px solid #2a2e38}}
.t{{font-size:22px;font-weight:800}}.rec{{font-size:18px;font-weight:700;color:#f5c518;margin:2px 0}}
.h{{font-size:11px;color:#9aa}}.mock{{background:#b00;color:#fff;padding:8px;text-align:center;font-weight:700}}
.c{{margin:10px 8px;padding:10px;border-radius:10px;background:#1a1d24;border-left:4px solid #3a3f4a}}.hot{{border-left-color:#f5c518}}
.m{{font-weight:700;font-size:15px;margin:3px 0 8px}}.m span{{color:#778;font-weight:400}}
.cols{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}}
@media(max-width:340px){{.cols{{grid-template-columns:1fr}}}}
.col{{background:#232731;border-radius:8px;padding:7px 6px;min-width:0;overflow-wrap:anywhere}}.col.star{{outline:1px solid #f5c518}}
.mk{{font-size:9px;letter-spacing:.06em;color:#9aa;font-weight:700}}.pk{{font-size:12px;font-weight:600;margin:3px 0;line-height:1.2;min-height:2.4em}}
.f{{font-size:22px;font-weight:800;line-height:1.1}}.f.na{{font-size:14px;color:#778;padding:4px 0}}.fs{{font-size:9px;color:#889}}
.tag{{font-size:12px;margin:4px 0;font-weight:700}}.s{{color:#f5c518}}.s small{{font-size:10px;font-weight:400}}.pass{{color:#777;font-weight:400;font-size:11px}}
.px{{font-size:12px}}.ref{{font-size:9px;color:#889}}.mo{{font-size:9px;color:#889;margin-top:4px;line-height:1.3}}.mg{{display:flex;gap:6px;margin:2px 0 3px}}.mg div{{flex:1;background:#1c2430;border-radius:4px;padding:3px 0;text-align:center}}.mg b{{display:block;font-size:17px;color:#7cc4ff;font-weight:800}}.mg span{{font-size:8px;color:#9aa}}
.n{{font-size:11px;color:#aa9;margin-top:6px}}.rW{{color:#3c3}}.rL{{color:#e44}}.rP{{color:#aaa}}</style></head><body>{banner}
<div class="top"><div class="t">New DESK</div><div class="rec">★ plays: {w}-{l}-{p}</div>
<div class="h">STAGING · not live · built {now} · flat $20 · big = no-vig fair % · ★ ≥1pp / ★★ ≥3pp vs Bovada · straight bets only</div></div>
{"".join(cards) or '<p style="padding:14px">No games today.</p>'}</body></html>'''
    open(os.path.join(H,"index.html"),"w").write(page); print("built","MOCK" if mock else "REAL",len(rows),"rows",len(cards),"games")
main()

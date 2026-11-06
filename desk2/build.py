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
    for k in ("pinnacle_novig_pct","betsim_pct","betsim_model_pct"): r[k]=pct(r.get(k))
    for k in ("strawhat_pct","strawhat_src","blend_pct","agree"): r.pop(k,None)   # Strawhat model dropped Oct 17
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
def stars(e,r=None):
    if r is not None and r.get("playable") is False: return ""
    if r is not None and r.get("market") == "ml":  # 2026-10-21 D (Luis OK): never star ML at -200 or shorter
        _p = r["prices"].get("bovada")
        if _p is not None and _p <= -200: return ""
    if r is not None and r.get("prop_market") in ("points", "rebounds"): return ""  # 2026-10-21 D   # 2026-10-19 rec #3: CFB spread/total skip days
    return _stars(e)
def _stars(e): return "★★" if e is not None and e>=3 else "★" if e is not None and e>=1 else ""
def kick(r):
    try: return dt.datetime.fromisoformat(r["kickoff_ct"]).astimezone(CT)
    except Exception: return None
def col(r):
    m=r["market"]; e=edge(r); s=stars(e,r); f=r["pinnacle_novig_pct"]; pr=r["prices"]
    fair=f'<div class="f">{f:.1f}%</div><div class="fs">fair · {E(str(r.get("novig_source") or "no-vig"))}</div>' if f is not None else '<div class="f na">fair n/a</div><div class="fs">&nbsp;</div>'
    tag=f'<div class="tag s">{s} <small>{e:+.1f}pp</small></div>' if s else (f'<div class="tag pass">{E(r["skip_reason"])}</div>' if r.get("skip_reason") else '<div class="tag pass">no edge, pass</div>')
    res=f' <span class="r{r["result"]}">{r["result"]}</span>' if r.get("result") in ("W","L","P") else ""
    def p(k): v=r.get(k); return "—" if v is None else f"{v:.0f}%"
    return f'''<div class="col{' star' if s else ''}"><div class="mk">{ {"ml":"MONEYLINE","spread":"SPREAD","total":"TOTAL"}[m]}{res}</div>
<div class="pk">{E(pick(r))}</div>{tag}
<div class="px">Bovada <b>{am(pr.get("bovada"))}</b></div><div class="ref">ref DK {am(pr.get("dk"))} · Betr {am(pr.get("betr"))}</div>
<div class="mo"><div class="mg"><div><b>{p("betsim_model_pct") if r.get("pct_label") else p("betsim_pct")}</b><span>Sim Bot model</span></div>{f'<div><b>{p("strawhat_pct")}</b><span>Strawhat model</span></div>' if r.get("strawhat_pct") is not None else ""}</div></div></div>'''
def load_picks_panel():
    """Picks Desk panels for LIVE CARD / RECORD tabs. Empty live is fine before ~11 AM CT."""
    for path in (os.path.join(os.path.dirname(REAL),"picks_panel.json"),
                 "/workspace/betsim/desk2/data/picks_panel.json"):
        try:
            return json.load(open(path))
        except Exception:
            continue
    return {}
def _tbl(cols, rows):
    if not rows: return '<p class="pass" style="padding:4px 0">None yet.</p>'
    h=''.join(f'<th>{E(c)}</th>' for c in cols)
    body=[]
    for r in rows:
        cells=''.join(f'<td>{E(str(x if x is not None else ""))}</td>' for x in r)
        body.append(f'<tr>{cells}</tr>')
    return f'<table><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table>'
def picks_panels(P):
    """HTML cards for LIVE CARD + RECORD tabs (desk2 style). data-sp must match tab labels."""
    if not P: return []
    out=[]
    live=P.get('live') or {}
    rows=live.get('rows') or []
    frec=live.get('filtered_rec') or ['','']
    a3=live.get('agree3_rec') or ['','']
    note=E(live.get('note') or '')
    upd=E(P.get('upd') or '')
    head=f'<div class="c panel" data-sp="LIVE CARD"><div class="h">LIVE CARD · Filtered + agree3 · updated {upd}</div>'
    head+=f'<div class="m">Filtered {E(" ".join(frec))} · Agree3 {E(" ".join(a3))}</div>'
    head+=f'<div class="warn">{note}</div>'
    if rows:
        head+=_tbl(live.get('cols') or [], rows)
    else:
        head+='<p class="pass" style="padding:6px 0">No live bets today. Empty until the ~11 AM CT Filtered run fills the card.</p>'
    head+='</div>'
    out.append(head)
    # RECORD / PAPER
    sc=P.get('score') or []
    sc_rows=[[s.get('label',''), s.get('rec',''), s.get('usd','')] for s in sc]
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">SCOREBOARD · since Oct 28 · $20 flat</div>'
               +_tbl(['Column','W-L-P','$'], sc_rows)+'</div>')
    desk=P.get('desk') or {}
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">DESK CARD · lean / fade</div>'
               f'<div class="warn">{E(desk.get("note") or "")}</div>'
               +_tbl(desk.get('cols') or [], desk.get('rows') or [])+'</div>')
    watch=P.get('watch') or {}
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">WATCHLIST · n≥50</div>'
               +_tbl(watch.get('cols') or [], watch.get('rows') or [])
               +f'<div class="n">pick_log {E(str(P.get("nlog") or 0))} lines · desk {E(P.get("desk_upd") or "")}</div></div>')
    rt=P.get('research') or {}
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">RESEARCH / FIX-IT TRACK · not bets</div>'
               f'<div class="warn">Promotion needs 50+ unseen graded games with positive $ at $20. See FIXIT_TRACK.md.</div>'
               +_tbl(rt.get('cols') or [], rt.get('rows') or [])+'</div>')
    fx=P.get('fixit') or []
    fx_rows=[[f.get('segment',''), f.get('baseline',''), f.get('status','')] for f in fx]
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">FIX-IT STATUSES</div>'
               +_tbl(['Segment','Baseline','Status'], fx_rows)+'</div>')
    sh=P.get('shared') or {}
    sh_rows=[[s.get('label',''), s.get('rec',''), s.get('usd','')] for s in (sh.get('rows') or [])]
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">THREE-WAY · shared picks only</div>'
               +_tbl(['Column','W-L-P','$'], sh_rows)
               +f'<div class="n">Only the {E(str(sh.get("n") or ""))} graded picks all three made.</div></div>')
    # BOARD AGREE · every game/market (Luis OK Nov 6 2026 11:17 AM CT)
    bd=P.get('board') or {}
    bd_note=E(bd.get('note') or '')
    bd_fade=E(bd.get('fade_note') or '')
    bd_gap=E(bd.get('gap') or '')
    bd_upd=E(bd.get('upd') or '')
    cnt=bd.get('counts') or {}
    cnt_s=' · '.join(f'{E(str(k))} {v}' for k,v in cnt.items()) if cnt else ''
    out.append(
        f'<div class="c panel" data-sp="BOARD AGREE"><div class="h">BOARD AGREE · every market · updated {bd_upd}</div>'
        f'<div class="m">{E(str(bd.get("n") or 0))} markets · {cnt_s}</div>'
        f'<div class="warn">{bd_note}</div>'
        f'<div class="warn">Fade lean source: {bd_fade}</div>'
        +(f'<div class="n">{bd_gap}</div>' if bd_gap else '')
        +_tbl(bd.get('cols') or [], bd.get('rows') or [])
        +'</div>'
    )
    return out

def main():
    mock=not os.path.exists(REAL); rows=json.load(open(MOCK if mock else REAL))
    if isinstance(rows,dict): rows=rows.get("games",rows.get("rows",[]))
    rows=[norm(r) for r in rows if r.get("market") in ("ml","spread","total")]  # straight bets only
    w=l=p=0; usd=0.0
    for r in rows:
        if stars(edge(r),r):
            res=r.get("result"); w+=res=="W"; l+=res=="L"; p+=res=="P"; o=r["prices"].get("bovada")
            if res=="W" and o: usd+=20*(o/100 if o>0 else 100/-o)
            elif res=="L": usd-=20
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
            if c is None or ((edge(r) or -99) if r.get("playable") is not False else -99)>((edge(c) or -99) if c.get("playable") is not False else -99): bym[r["market"]]=r
        cols="".join(col(bym[m]) if m in bym else '<div class="col empty"><div class="mk">'+m.upper()+'</div><div class="pass">no line</div></div>' for m in ("ml","spread","total"))
        hot=any(stars(edge(r),r) for r in bym.values())
        notes=" · ".join(dict.fromkeys(r["notes"] for r in rs if r.get("notes")))
        sp=str(r0.get("sport","")).upper()
        cards.append(f'''<div class="c{' hot' if hot else ''}" data-sp="{E(sp)}"><div class="h">{E(str(r0.get("sport","")))} · {t}</div>
<div class="m">{E(r0["away"])} <span>@</span> {E(r0["home"])}</div><div class="cols">{cols}</div>
{f'<div class="n">{E(notes)}</div>' if notes else ''}</div>''')
    sports=sorted({c.split('data-sp="')[1].split('"')[0] for c in cards})
    # 2026-10-19 (Luis via Strawhat): NBA Props tab, today's CT date only, PAPER / UNPROVEN
    NP=os.path.join(os.path.dirname(REAL),"nba_props.json"); NL=os.path.join(os.path.dirname(REAL),"nba_props_ledger.json")
    try: npd=json.load(open(NP))
    except Exception: npd={"props":[],"date":str(today)}
    props=[x for x in npd.get("props",[]) if x.get("date")==str(today)]
    try: led=json.load(open(NL))["items"]
    except Exception: led=[]
    gl=[i for i in led if i.get("result") in ("W","L","P")]; pw=sum(i["result"]=="W" for i in gl); pl=sum(i["result"]=="L" for i in gl); pp=sum(i["result"]=="P" for i in gl); pu=sum(i["units"] for i in gl)*20
    def pcard(x):
        b=x["prices"].get("bovada"); d=x["prices"].get("dk"); e=x.get("edge_pct"); e=None if e is None else e*100; st=stars(e,{"prop_market":x.get("market"),"prices":x["prices"]})
        px=f'Bovada <b>{am(b)}</b>' if b is not None else (f'DK <b>{am(d)}</b> <span class="fs">(fallback, no Bovada)</span>' if d is not None else '<span class="pass">no price yet</span>')
        tag=f'<div class="tag s">{st} <small>{e:+.1f}pp</small></div>' if st else '<div class="tag pass">no star</div>'
        k=kick({"kickoff_ct":x.get("kickoff_ct")}); t=k.strftime("%-I:%M %p CT") if k else ""
        return f'''<div class="c pc" data-sp="NBA PROPS"><div class="h">NBA PROP · {E(t)} · {E(x["game"])}</div>
<div class="m">{E(x["player"])} <span>{E(str(x.get("team") or ""))}</span></div><div class="cols"><div class="col{' star' if st else ''}"><div class="mk">{E(x["market"].upper())}</div>
<div class="pk">{E(str(x["side"]).title())} {x["line"]:g}</div>{tag}<div class="px">{px}</div></div>
<div class="col"><div class="mk">MODEL</div><div class="mg"><div><b>{x["model_pct"]*100:.0f}%</b><span>Sim Bot props model</span></div></div></div></div></div>'''
    props.sort(key=lambda x:(x.get("kickoff_ct") or "", -x["model_pct"]))
    pcards=[pcard(x) for x in props]
    phead=f'<div class="c pc" data-sp="NBA PROPS"><div class="h">NBA PROPS · {E(str(today))} only · PAPER / UNPROVEN — NBA props have no graded history; not plays</div><div class="m">Paper record: {pw}-{pl}-{pp} · {"+" if pu>=0 else "−"}${abs(pu):.0f} at $20 flat</div></div>'
    if not pcards: pcards=['<div class="c pc" data-sp="NBA PROPS"><p>No NBA props today.</p></div>']
    cards=cards+[phead]+pcards
    P=load_picks_panel()
    cards=cards+picks_panels(P)
    tabs='<div class="tabs"><button class="on" data-t="ALL">All</button>'+"".join(f'<button data-t="{E(x)}">{E(x)} ({sum(("data-sp=\""+x+"\"") in c for c in cards)})</button>' for x in sports)+f'<button data-t="NBA PROPS" id="nba-props">NBA Props ({len(props)})</button><button data-t="LIVE CARD">Live Card ({len((P.get("live") or {}).get("rows") or [])})</button><button data-t="BOARD AGREE">Board Agree ({len((P.get("board") or {}).get("rows") or [])})</button><button data-t="RECORD">Record / Paper</button></div>'
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
.tabs{{display:flex;gap:6px;overflow-x:auto;margin-top:8px}}.tabs button{{background:#232731;color:#cfd;border:0;border-radius:14px;padding:5px 11px;font-size:12px;font-weight:700;white-space:nowrap}}.tabs button.on{{background:#f5c518;color:#111}}
.n{{font-size:11px;color:#aa9;margin-top:6px}}.rW{{color:#3c3}}.rL{{color:#e44}}.rP{{color:#aaa}}.panel table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}}.panel th,.panel td{{text-align:left;padding:4px 6px;border-bottom:1px solid #2a2e38;vertical-align:top}}.panel th{{color:#9aa;font-size:10px;letter-spacing:.04em}}.warn{{color:#f5c518;font-size:11px;margin:4px 0;line-height:1.35}}</style></head><body>{banner}
<div class="top"><div class="t">New DESK</div><div class="rec">★ plays: {w}-{l}-{p} · {"+" if usd>=0 else "−"}${abs(usd):.0f} at $20 flat</div>
<div class="h">STAGING · not live · built {now} · flat $20 · big = Sim Bot model % · ★ ≥1pp / ★★ ≥3pp vs Bovada · straight bets only</div>{tabs}</div>
{"".join(cards) or '<p style="padding:14px">No games today.</p>'}<script>document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));const t=b.dataset.t;document.querySelectorAll('.c').forEach(c=>c.style.display=((t==='ALL'&&!c.classList.contains('pc')&&!c.classList.contains('panel'))||c.dataset.sp===t)?'':'none');scrollTo(0,0)}});document.querySelectorAll('.pc,.panel').forEach(c=>c.style.display='none');if(location.hash==='#nba-props')document.getElementById('nba-props').click()</script></body></html>'''
    open(os.path.join(H,"index.html"),"w").write(page); print("built","MOCK" if mock else "REAL",len(rows),"rows",len(cards),"games")
main()

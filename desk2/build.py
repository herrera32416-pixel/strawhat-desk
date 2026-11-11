#!/usr/bin/env python3
"""Grand Line Picks desk2 builder. Look is SportsLine-inspired; pick logic unchanged."""
import json,os,re,html,math,datetime as dt
from zoneinfo import ZoneInfo
H=os.path.dirname(os.path.abspath(__file__))
REAL="/workspace/betsim/desk2/data/games.json"; MOCK=os.path.join(H,"data/mock_games.json")
LOGO_PATH=os.path.join(H,"data/espn_logos.json")
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

def nick(name):
    """Short team label for proj line (Flyers, Flames, Leafs, …)."""
    n=(name or "").strip()
    if not n: return "?"
    # multi-word nicknames that shouldn't be truncated to the last token alone
    specials=(
        ("Maple Leafs","Leafs"),("Blue Jackets","Jackets"),("Golden Knights","Knights"),
        ("Red Wings","Wings"),("Blue Jays","Jays"),("White Sox","Sox"),
        ("Trail Blazers","Blazers"),("Timberwolves","Wolves"),("SuperSonics","Sonics"),
        ("76ers","76ers"),("Football Team","WFT"),
    )
    nu=n
    for full,short in specials:
        if nu.endswith(full): return short
    # city + nick: take last word (Bears, Flyers, Celtics, …)
    parts=nu.split()
    return parts[-1] if parts else n

def _namekey(s):
    s=(s or "").lower()
    s=s.replace("’","'").replace("‘","'").replace("é","e").replace("í","i").replace("ó","o").replace("á","a").replace("ú","u").replace("ñ","n")
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

_LOGO_IDX=None
_SPORT_LOGO={"NFL":"nfl","NBA":"nba","NHL":"nhl","CFB":"cfb","CBB":"cbb","NCAAF":"cfb","NCAAB":"cbb"}
def _logos():
    """Load ESPN CDN logo index (build-time cache). Fail soft."""
    global _LOGO_IDX
    if _LOGO_IDX is not None: return _LOGO_IDX
    idx={}
    try:
        data=json.load(open(LOGO_PATH))
        for sp, teams in (data.get("by_sport") or {}).items():
            lu={}; recs=[]
            for t in teams:
                recs.append(t)
                for k in t.get("keys") or []:
                    lu.setdefault(k,t)
            idx[sp]={"lu":lu,"recs":recs}
    except Exception:
        pass
    _LOGO_IDX=idx
    return _LOGO_IDX

def logo_info(sport, name):
    """Return (logo_url, abbr) for a team name, or ('', fallback abbr)."""
    sp=_SPORT_LOGO.get(str(sport or "").upper())
    fb=(nick(name) or "?")[:4].upper()
    if not sp: return "", fb
    pack=_logos().get(sp) or {}
    lu=pack.get("lu") or {}; recs=pack.get("recs") or []
    n=_namekey(name)
    if not n: return "", fb
    hit=lu.get(n)
    if not hit:
        parts=n.split()
        for i in range(0,len(parts)):
            cand=" ".join(parts[i:])
            if cand in lu and (len(cand.split())>=2 or sp in ("nfl","nba","nhl")):
                hit=lu[cand]; break
        if not hit and parts:
            last=parts[-1]
            if last in lu:
                t=lu[last]
                if sp in ("nfl","nba","nhl") or (_namekey(t.get("loc")) and _namekey(t.get("loc")) in n):
                    hit=t
        if not hit:
            for t in recs:
                loc=_namekey(t.get("loc")); full=_namekey(t.get("name"))
                if loc and parts and (n.startswith(loc) or loc.startswith(parts[0])):
                    if full in n or n in full or _namekey(t.get("nick")) in n:
                        hit=t; break
    if not hit: return "", fb
    abbr=(hit.get("abbr") or fb).upper()
    return hit.get("logo") or "", abbr

def logo_html(sport, name):
    url,abbr=logo_info(sport,name)
    fb=E(abbr or nick(name)[:3] or "?")
    if url:
        return (f'<span class="lgwrap"><img class="lg" src="{E(url)}" alt="" width="36" height="36" loading="lazy" '
                f"onerror=\"this.classList.add('off');this.nextElementSibling.classList.add('on')\">"
                f'<span class="lgfb">{fb}</span></span>')
    return f'<span class="lgwrap"><span class="lgfb on">{fb}</span></span>'

def proj_bits(rs):
    """Projected scores for the card: (away_score, home_score, summary_html). Always a proj slot."""
    r0=rs[0] if rs else {}
    ph=pa=None
    for r in rs:
        ph=num(r.get("proj_home_score")); pa=num(r.get("proj_away_score"))
        if ph is not None and pa is not None: break
    def s(x):
        return "—" if x is None else f"{x:.1f}"
    if ph is None or pa is None:
        return "—","—",'<div class="proj">Proj n/a</div>'
    ha,aa=r0.get("home") or "?", r0.get("away") or "?"
    hn,an=nick(ha),nick(aa)
    tot=ph+pa; marg=ph-pa
    if marg>0.05:
        by=f"{hn} by {s(marg)}"
    elif marg<-0.05:
        by=f"{an} by {s(-marg)}"
    else:
        by="pick'em"
    line=(f'<div class="proj">Sim: {E(an)} {s(pa)} – {E(hn)} {s(ph)}'
          f' · total {s(tot)} · {E(by)}</div>')
    return s(pa),s(ph),line


def proj_line(rs):
    """One Sim Bot projected-score line from feed proj_* fields. Omit if missing."""
    r0=rs[0] if rs else {}
    # prefer any row that actually carries projections
    ph=pa=None
    for r in rs:
        ph=num(r.get("proj_home_score")); pa=num(r.get("proj_away_score"))
        if ph is not None and pa is not None: break
    if ph is None or pa is None: return ""
    ha,aa=r0.get("home") or "?", r0.get("away") or "?"
    hn,an=nick(ha),nick(aa)
    tot=ph+pa; marg=ph-pa  # home minus away
    # one decimal for hockey-ish totals (<20), one for others too (matches board)
    def s(x):
        return f"{x:.1f}"
    if marg>0.05:
        by=f"{hn} by {s(marg)}"
    elif marg<-0.05:
        by=f"{an} by {s(-marg)}"
    else:
        by="pick'em"
    return (f'<div class="proj">Sim: {E(an)} {s(pa)} – {E(hn)} {s(ph)}'
            f' · total {s(tot)} · {E(by)}</div>')

def col(r):
    m=r["market"]; e=edge(r); s=stars(e,r); pr=r["prices"]
    # fair / no-vig % is used only for the Bovada-vs-fair star; it is never shown (model % only)
    _sr=str(r.get("skip_reason") or "")
    if "NBA totals" in _sr: _sr="SKIP: paper"
    elif "NHL totals" in _sr: _sr="SKIP: paper"
    elif len(_sr)>28: _sr=_sr[:26]+"…"
    star=f'<span class="star" title="{e:+.1f}pp vs Bovada">{s}</span>' if s else ""
    tag=f'<div class="tag s">{s} <small>{e:+.1f}pp</small></div>' if s else (f'<div class="tag pass">{E(_sr)}</div>' if r.get("skip_reason") else "")
    res=f' <span class="r{r["result"]}">{r["result"]}</span>' if r.get("result") in ("W","L","P") else ""
    def p(k): v=r.get(k); return "—" if v is None else f"{v:.0f}%"
    mk={"ml":"MONEYLINE","spread":"SPREAD","total":"TOTAL"}[m]
    return (
        f'<div class="col{" star" if s else ""}"><div class="mk">{mk}{res}{star}</div>'
        f'<div class="pk">{E(pick(r))}</div>'
        f'<div class="px">Bovada <b>{am(pr.get("bovada"))}</b></div><div class="ref">ref DK {am(pr.get("dk"))} · Betr {am(pr.get("betr"))}</div>'
        f'<div class="mo"><div class="mg"><div><b>{p("betsim_model_pct") if r.get("pct_label") else p("betsim_pct")}</b><span>Sim Bot model</span></div></div>{tag}</div></div>'
    )
def tier_pill(tag, reason="", under_pct=False):
    """Always render a tag slot under model % (Luis Nov 8 10:55 PM CT). Empty -> muted PASS."""
    t = (str(tag).upper() if tag else "PASS")
    tip = E(reason) if reason else t
    extra = ""
    if t == "FADE":
        extra = '<div class="paper">paper</div>'
    elif t == "LEAN":
        extra = '<div class="paper">unproven</div>'
    elif t == "PASS":
        tip = tip if reason else "no tag"
    cls = "tier-under" if under_pct else "tag"
    return f'<div class="{cls}"><span class="pill {t.lower()}" title="{tip}">{t}</span>{extra}</div>'


def lookup_tier(P, away, home, market):
    by=(P.get("tiers") or {}).get("by_game") or {}
    if not by: return "", ""
    mk=str(market or "").upper()
    NFL={"Cardinals":"ARI","Falcons":"ATL","Ravens":"BAL","Bills":"BUF","Panthers":"CAR","Bears":"CHI","Bengals":"CIN","Browns":"CLE","Cowboys":"DAL","Broncos":"DEN","Lions":"DET","Packers":"GB","Texans":"HOU","Colts":"IND","Jaguars":"JAX","Chiefs":"KC","Raiders":"LV","Chargers":"LAC","Rams":"LAR","Dolphins":"MIA","Vikings":"MIN","Patriots":"NE","Saints":"NO","Giants":"NYG","Jets":"NYJ","Eagles":"PHI","Steelers":"PIT","49ers":"SF","Seahawks":"SEA","Buccaneers":"TB","Titans":"TEN","Commanders":"WSH"}
    NBA={"Hawks":"ATL","Celtics":"BOS","Nets":"BKN","Hornets":"CHA","Bulls":"CHI","Cavaliers":"CLE","Mavericks":"DAL","Nuggets":"DEN","Pistons":"DET","Warriors":"GSW","Rockets":"HOU","Pacers":"IND","Clippers":"LAC","Lakers":"LAL","Grizzlies":"MEM","Heat":"MIA","Bucks":"MIL","Timberwolves":"MIN","Pelicans":"NOP","Knicks":"NYK","Thunder":"OKC","Magic":"ORL","76ers":"PHI","Suns":"PHX","Blazers":"POR","Kings":"SAC","Spurs":"SAS","Raptors":"TOR","Jazz":"UTA","Wizards":"WSH"}
    NHL={"Ducks":"ANA","Bruins":"BOS","Sabres":"BUF","Flames":"CGY","Hurricanes":"CAR","Blackhawks":"CHI","Avalanche":"COL","Stars":"DAL","Wings":"DET","Oilers":"EDM","Panthers":"FLA","Kings":"LA","Wild":"MIN","Canadiens":"MTL","Predators":"NSH","Devils":"NJ","Islanders":"NYI","Rangers":"NYR","Senators":"OTT","Flyers":"PHI","Penguins":"PIT","Kraken":"SEA","Blues":"STL","Lightning":"TB","Leafs":"TOR","Canucks":"VAN","Knights":"VGK","Capitals":"WSH","Jets":"WPG","Sharks":"SJ"}
    def ab(n):
        n=(n or "").strip()
        if not n: return ""
        if " " not in n and len(n)<=4: return n.upper()
        nu=n.upper()
        for M in (NFL,NBA,NHL):
            for nick,a in sorted(M.items(), key=lambda kv:-len(kv[0])):
                if nu.endswith(nick.upper()): return a
        return n.split()[-1].upper()[:4]
    cands=[
        f"{ab(away)}@{ab(home)}|{mk}",
        f"{(away or '').replace(' ','').upper()}@{(home or '').replace(' ','').upper()}|{mk}",
        f"{(away or '').split()[-1].upper() if away else ''}@{(home or '').split()[-1].upper() if home else ''}|{mk}",
    ]
    for c in cands:
        if c in by:
            return by[c].get("tag") or "", by[c].get("reason") or ""
    au,hu=(away or "").upper(),(home or "").upper()
    for k,v in by.items():
        if not k.endswith("|"+mk) or "@" not in k: continue
        g=k.split("|",1)[0]; a,h=g.split("@",1)
        if (a in au.replace(" ","") or au.endswith(a)) and (h in hu.replace(" ","") or hu.endswith(h)):
            return v.get("tag") or "", v.get("reason") or ""
    return "", ""

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
    # Standing rule: leave expert consensus out of the desk/report display (data stays in the feed).
    rows=[r for r in (rows or []) if not any("expert consensus" in str(x).lower() for x in (r or ()))]
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
    _T=P.get('tiers') or {}; _br=( _T.get('records') or {}).get('BET') or {}
    if _br:
        head+=f'<div class="recstrip"><span class="pill bet">BET</span> {E(str(_br.get("rec") or ""))} {E(str(_br.get("usd") or ""))} · $20 flat</div>'
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
    out.append('<div class="c panel" data-sp="RECORD" id="fixit"><div class="h">FIX-IT STATUSES</div>'
               +_tbl(['Segment','Baseline','Status'], fx_rows)+'</div>')
    sh=P.get('shared') or {}
    sh_rows=[[s.get('label',''), s.get('rec',''), s.get('usd','')] for s in (sh.get('rows') or [])]
    out.append('<div class="c panel" data-sp="RECORD"><div class="h">THREE-WAY · shared picks only</div>'
               +_tbl(['Column','W-L-P','$'], sh_rows)
               +f'<div class="n">Only the {E(str(sh.get("n") or ""))} graded picks all three made.</div></div>')
    # BOARD AGREE panel removed from the desk (Luis Nov 9 2026). Data still lives in picks_panel.json.

    # BET / LEAN / FADE (Luis Nov 8 2026)
    T=P.get('tiers') or {}
    defs=T.get('defs') or {}
    recs=T.get('records') or {}
    counts=T.get('today_counts') or {}
    since=T.get('since') or {}
    bf=E(str(T.get('backfill_start') or '2026-11-01'))
    def _tier_rec(tag):
        r=recs.get(tag) or {}
        return f'{E(tag)} {E(str(r.get("rec") or "—"))} {E(str(r.get("usd") or ""))}'
    strip=' · '.join(_tier_rec(t) for t in ('BET','LEAN','FADE'))
    today_c=' · '.join(f'{E(k)} {v}' for k,v in counts.items()) if counts else 'none yet'
    def_lines=''.join(
        f'<div class="n"><span class="pill {E(k.lower())}">{E(k)}</span> {E(v)}</div>'
        for k,v in defs.items()
    )
    tcols=T.get('cols') or []
    trows=[]
    for row in (T.get('rows') or []):
        row=list(row)
        if row:
            tag=str(row[0]).upper()
            row[0]=f'<span class="pill {tag.lower()}">{E(tag)}</span>'
        trows.append(row)
    if trows:
        h=''.join(f'<th>{E(c)}</th>' for c in tcols)
        body=[]
        for r in trows:
            cells=[]
            for i,x in enumerate(r):
                if i==0: cells.append(f'<td>{x}</td>')
                else: cells.append(f'<td>{E(str(x if x is not None else ""))}</td>')
            body.append(f'<tr>{"".join(cells)}</tr>')
        ttbl=f'<table><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table>'
    else:
        ttbl='<p class="pass" style="padding:4px 0">No tagged markets today.</p>'
    out.append(
        f'<div class="c panel" data-sp="BET LEAN FADE"><div class="h">BET · LEAN · FADE · updated {E(T.get("upd") or "")}</div>'
        f'<div class="m">Today: {today_c}</div>'
        f'<div class="recstrip">{strip}</div>'
        f'<div class="n">Records at $20 flat · backfill from {bf}'
        f' · BET since {E(str(since.get("BET") or bf))} · LEAN since {E(str(since.get("LEAN") or bf))} · FADE since {E(str(since.get("FADE") or bf))}</div>'
        + def_lines
        + f'<div class="warn">{E(T.get("note") or "")}</div>'
        + ttbl
        + '</div>'
    )

    return out

CSS=r''':root{--bg:#07101c;--navy:#0a1628;--navy2:#10203a;--card:#152238;--box:#1b2b45;--gold:#f0c14b;--line:#243552;--text:#eef2f8;--muted:#8b97ad;--model:#7ec2ff;--pos:#3ddc97;--neg:#ff6b6b}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:"Segoe UI",system-ui,-apple-system,sans-serif}
body{min-height:100%}
.top{background:var(--navy);border-bottom:1px solid var(--line)}
.top-inner,.nav-inner,.board{max-width:1100px;margin:0 auto;padding:0 14px}
.top-inner{padding:12px 14px 10px}
.brandrow{display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand img{width:48px;height:48px;border-radius:10px;object-fit:cover;background:#081018;border:1px solid var(--line);flex-shrink:0}
.brand .t{font-size:22px;font-weight:800;line-height:1.1;letter-spacing:.01em}
.brand .sub{font-size:12px;color:var(--muted);font-weight:600;margin-top:2px}
.recstrip-top{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 6px}
.rec-item{background:var(--navy2);border:1px solid var(--line);border-radius:10px;padding:7px 10px;font-size:14px;font-weight:800;display:flex;align-items:center;gap:6px;line-height:1.2}
.rec-item .rlab{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:700}
.rec-item .usd.pos{color:var(--pos)}
.rec-item .usd.neg{color:var(--neg)}
.rec-item.live{border-color:#1e6b4a}
.rec-note{font-size:11px;color:var(--muted);margin:2px 0 8px;line-height:1.4}
.fixit-strip{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding:0 0 8px;scrollbar-width:thin}
.fixit-strip a{text-decoration:none;color:inherit}
.fx-lab{flex-shrink:0;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);padding:6px 0;position:sticky;left:0;background:var(--navy)}
.fx-chip{flex-shrink:0;font-size:10px;font-weight:700;background:var(--navy2);border:1px solid var(--line);border-radius:999px;padding:5px 8px;color:var(--muted);white-space:nowrap}
.fx-chip.paper{color:#d8c48a}
.navstick{position:sticky;top:0;z-index:5;background:var(--navy);border-bottom:1px solid var(--line)}
.nav-inner{padding:8px 14px 10px}
.dates{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 8px;scrollbar-width:thin}
.dates button,.tabs button{appearance:none;border:0;cursor:pointer;white-space:nowrap;font-weight:700}
.dates button{background:var(--navy2);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:7px 12px;font-size:13px}
.dates button.on{background:var(--gold);color:#111;border-color:var(--gold)}
.tabs{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin}
.tabs button{background:var(--navy2);color:#d5deea;border-radius:999px;padding:8px 14px;font-size:14px;font-weight:700}
.tabs button.on{background:var(--gold);color:#111}
.mock{background:#b00;color:#fff;padding:8px;text-align:center;font-weight:700}
.board{padding:12px 10px 40px}
.c{margin:0 0 10px;padding:12px;border-radius:12px;background:var(--card);border:1px solid var(--line);border-left:4px solid #3a4a63}
.c.hot{border-left-color:var(--gold)}
.ghead{display:flex;align-items:stretch;justify-content:space-between;gap:10px;margin-bottom:6px}
.teams{flex:1;min-width:0}
.tm{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:36px}
.tm + .tm{margin-top:4px}
.lgwrap{width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;background:#f4f7fb;border-radius:50%;overflow:hidden}
.lg{width:30px;height:30px;object-fit:contain;display:block}
.lg.off{display:none}
.lgfb{display:none;width:36px;height:36px;border-radius:50%;background:#0d1a2e;border:0;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:var(--gold)}
.lgfb.on{display:flex}
.tn{font-weight:800;font-size:15px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tn .at{color:var(--muted);font-weight:600;font-size:12px;margin-right:2px}
.ps{font-weight:800;font-size:18px;color:#fff;font-variant-numeric:tabular-nums;min-width:3.2em;text-align:right}
.meta{display:flex;flex-direction:column;align-items:flex-end;justify-content:center;flex-shrink:0;text-align:right}
.when{font-size:12px;font-weight:700;color:var(--text)}
.meta .sp{font-size:11px;font-weight:800;letter-spacing:.06em;color:var(--gold);margin-top:2px}
.proj{font-size:12px;color:#9ec1e6;margin:0 0 8px;font-weight:600;letter-spacing:.01em;line-height:1.35}
.h{font-size:11px;color:var(--muted);font-weight:700}
.m{font-weight:700;font-size:15px;margin:3px 0 8px}
.m span{color:var(--muted);font-weight:400}
.cols{display:grid!important;grid-template-columns:1fr 1fr 1fr!important;grid-template-rows:auto;gap:6px;align-items:stretch;width:100%;box-sizing:border-box}
.cols>.col{min-width:0!important;width:auto;max-width:100%;overflow:hidden}
.col{background:var(--box);border-radius:10px;padding:7px 6px 6px;min-width:0;overflow:hidden;display:flex;flex-direction:column;box-sizing:border-box;border:1px solid transparent}
.col.star{outline:none;border-color:var(--gold);box-shadow:inset 0 0 0 1px var(--gold)}
.col.empty{justify-content:flex-start;opacity:.85}
.mk{font-size:9px;letter-spacing:.08em;color:var(--muted);font-weight:800;display:flex;align-items:center;gap:4px}
.pk{font-size:12px;font-weight:700;margin:3px 0 2px;line-height:1.2;min-height:2.3em;max-height:2.4em;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word;overflow-wrap:anywhere}
.f{font-size:22px;font-weight:800;line-height:1.1}.f.na{font-size:14px;color:var(--muted);padding:4px 0}.fs{font-size:9px;color:var(--muted)}
.tag{font-size:9px;margin:2px 0 0;font-weight:700;line-height:1.2;max-height:2.4em;overflow:hidden}
.s{color:var(--gold)}.s small{font-size:9px;font-weight:400}
.pass{color:#8893a6;font-weight:400;font-size:9px}
.star{color:var(--gold);font-size:11px;line-height:1;margin-left:auto}
.px{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#c9d3e0}
.ref{font-size:9px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mo{font-size:8px;color:var(--muted);margin-top:auto;padding-top:4px;line-height:1.2}
.mg{display:flex;gap:3px;margin:1px 0 2px}
.mg div{flex:1;background:#121c2e;border-radius:6px;padding:4px 0 3px;text-align:center;min-width:0}
.mg b{display:block;font-size:20px;color:var(--model);font-weight:800;letter-spacing:-.02em;line-height:1.05}
.mg span{font-size:8px;color:var(--muted);letter-spacing:.02em}
.n{font-size:11px;color:#aa9;margin-top:6px}
.rW{color:#3c3}.rL{color:#e44}.rP{color:#aaa}
.panel{overflow-x:auto}
.panel table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
.panel th,.panel td{text-align:left;padding:6px 7px;border-bottom:1px solid var(--line);vertical-align:top}
.panel th{color:var(--muted);font-size:10px;letter-spacing:.04em;text-transform:uppercase}
.warn{color:var(--gold);font-size:11px;margin:4px 0;line-height:1.35}
.pill{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.04em;padding:2px 7px;border-radius:999px;margin:0 4px 0 0;vertical-align:middle;color:#111}
.pill.bet{background:#3ddc97;color:#062}
.pill.lean{background:var(--gold);color:#221}
.pill.fade{background:#ff6b6b;color:#400}
.pill.pass{background:#3a3f4a;color:#9aa}
.recstrip{font-size:13px;font-weight:700;margin:4px 0 6px;color:var(--text)}
.tier-under{margin-top:4px;text-align:center;line-height:1.15;flex-shrink:0}
.tier-under .pill{margin:0;font-size:10px;padding:3px 8px;max-width:100%;box-sizing:border-box}
.tier-under .paper{display:block;font-size:8px;color:var(--muted);font-weight:600;letter-spacing:.02em;margin-top:2px}
@media (max-width:640px){
  .brand img{width:40px;height:40px}
  .brand .t{font-size:18px}
  .recstrip-top{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px;scrollbar-width:thin}
  .rec-item{flex-shrink:0}
  .tm{grid-template-columns:28px minmax(0,1fr) auto;gap:6px}
  .lgwrap,.lgfb{width:28px;height:28px}
  .lg{width:22px;height:22px}
  .tn{font-size:13px}
  .ps{font-size:16px;min-width:2.8em}
  .when{font-size:11px}
  .pk{font-size:11px}
  .mg b{font-size:17px}
  .cols{gap:4px}
  .col{padding:6px 4px 5px}
  .board{padding:8px 6px 32px}
  .c{padding:10px 8px;margin-bottom:8px;border-radius:10px}
  .rec-item{font-size:13px;padding:6px 8px}
  .top-inner,.nav-inner{padding-left:10px;padding-right:10px}
}
'''

JS=r'''(function(){
  var sport="ALL", date=(function(){
    var on=document.querySelector(".dates button.on");
    return (on && on.getAttribute("data-d")) || new Intl.DateTimeFormat("en-CA",{timeZone:"America/Chicago"}).format(new Date());
  })();
  function isPanel(c){return c.classList.contains("panel")||c.classList.contains("pc")}
  function apply(){
    document.querySelectorAll(".tabs button").forEach(function(x){x.classList.toggle("on", x.getAttribute("data-t")===sport)});
    document.querySelectorAll(".dates button").forEach(function(x){x.classList.toggle("on", x.getAttribute("data-d")===date)});
    document.querySelectorAll(".c").forEach(function(c){
      var sp=c.getAttribute("data-sp")||"", dd=c.getAttribute("data-date")||"";
      var show;
      if(sport==="ALL") show=!isPanel(c) && (!dd || dd===date);
      else if(sport==="LIVE CARD"||sport==="BET LEAN FADE"||sport==="RECORD") show=isPanel(c) && sp===sport;
      else show=!isPanel(c) && sp===sport && (!dd || dd===date);
      c.style.display=show?"":"none";
    });
  }
  document.querySelectorAll(".tabs button").forEach(function(b){
    b.addEventListener("click", function(){ sport=b.getAttribute("data-t"); apply(); window.scrollTo(0,0); });
  });
  document.querySelectorAll(".dates button").forEach(function(b){
    b.addEventListener("click", function(){
      date=b.getAttribute("data-d");
      if(sport==="LIVE CARD"||sport==="BET LEAN FADE"||sport==="RECORD") sport="ALL";
      apply(); window.scrollTo(0,0);
    });
  });
  document.querySelectorAll("[data-open]").forEach(function(a){
    a.addEventListener("click", function(ev){
      ev.preventDefault();
      sport=a.getAttribute("data-open")||"RECORD";
      apply();
      var t=document.getElementById("fixit");
      if(t) t.scrollIntoView({behavior:"smooth",block:"start"});
      else window.scrollTo(0,0);
    });
  });
  document.querySelectorAll(".pc,.panel").forEach(function(c){c.style.display="none"});
  apply();
})();
'''

def _usd_class(s):
    t=str(s or "")
    return "neg" if t.startswith("-") or t.startswith("−") else ("pos" if t.strip().startswith("+") or (t and t[0].isdigit()) else "")

def _rec_item(label, rec, usd, cls=""):
    rec=rec or "—"; usd=usd or ""
    uc=_usd_class(usd)
    return (f'<div class="rec-item {E(cls)}"><span class="rlab">{E(label)}</span> '
            f'{E(str(rec))} <span class="usd {uc}">{E(str(usd))}</span></div>')

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
        if k is None or k.date()<today: continue  # today + upcoming (date chips); past days stay off
        games.setdefault(r["game_id"],[]).append(r)
    P=load_picks_panel()
    cards=[]
    dates=sorted({kick(rs[0]).date() for rs in games.values() if kick(rs[0])})
    for gid,rs in sorted(games.items(),key=lambda kv:min(kick(r) for r in kv[1])):
        r0=rs[0]; kt=kick(r0); t=kt.strftime("%a %-I:%M %p CT"); dstr=kt.date().isoformat()
        bym={}
        for r in rs:   # one row per market: prefer the starred / higher-edge side
            c=bym.get(r["market"])
            if c is None or ((edge(r) or -99) if r.get("playable") is not False else -99)>((edge(c) or -99) if c.get("playable") is not False else -99): bym[r["market"]]=r
        def _col_with_tier(m):
            mk={"ml":"ML","spread":"SPREAD","total":"TOTAL"}[m]
            label={"ml":"MONEYLINE","spread":"SPREAD","total":"TOTAL"}[m]
            tag,reason=lookup_tier(P, r0.get("away"), r0.get("home"), mk)
            pill=tier_pill(tag, reason, under_pct=True)  # PASS if none
            if m not in bym:
                # same-size empty box with PASS under a dashed %
                return (
                    f'<div class="col empty"><div class="mk">{label}</div>'
                    f'<div class="pk">—</div><div class="tag pass">no line</div>'
                    f'<div class="px">Bovada <b>—</b></div><div class="ref">&nbsp;</div>'
                    f'<div class="mo"><div class="mg"><div><b>—</b><span>Sim Bot model</span></div></div>'
                    f'{pill}</div></div>'
                )
            base=col(bym[m])
            # Ensure exactly one tier-under under .mo (replace if injection already partial)
            if 'tier-under' in base:
                base=re.sub(r'<div class="tier-under">[\s\S]*?</div>', pill, base, count=1)
            else:
                i=base.find('<div class="mo">')
                if i!=-1:
                    j=base.find('</div></div>', i)
                    if j!=-1:
                        j+=len('</div></div>')
                        base=base[:j]+pill+base[j:]
                    else:
                        base=base+pill
                else:
                    base=base+pill
            return base
        cols="".join(_col_with_tier(m) for m in ("ml","spread","total"))
        hot=any(stars(edge(r),r) for r in bym.values())
        notes=" · ".join(dict.fromkeys(r["notes"] for r in rs if r.get("notes")))
        sp=str(r0.get("sport","")).upper()
        pa_s,ph_s,pl=proj_bits(rs)
        away,home=r0.get("away") or "?", r0.get("home") or "?"
        note_html=f'<div class="n">{E(notes)}</div>' if notes else ""
        cards.append(
            f'<div class="c{" hot" if hot else ""}" data-sp="{E(sp)}" data-date="{dstr}">'
            f'<div class="ghead"><div class="teams">'
            f'<div class="tm">{logo_html(sp,away)}<div class="tn">{E(away)}</div><div class="ps">{pa_s}</div></div>'
            f'<div class="tm">{logo_html(sp,home)}<div class="tn"><span class="at">@</span> {E(home)}</div><div class="ps">{ph_s}</div></div>'
            f'</div><div class="meta"><div class="when">{E(t)}</div><div class="sp">{E(sp)}</div></div></div>'
            f'{pl}<div class="cols">{cols}</div>{note_html}</div>'
        )
    # sport tab order: NFL, CFB, NBA, NHL, CBB, then any others
    present=sorted({(c.split('data-sp="')[1].split('"')[0] if 'data-sp="' in c else "") for c in cards})
    present=[x for x in present if x]
    order=["NFL","CFB","NBA","NHL","CBB"]
    sports=[s for s in order if s in present]+[s for s in present if s not in order]
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
        return (
            f'<div class="c pc" data-sp="NBA PROPS"><div class="h">NBA PROP · {E(t)} · {E(x["game"])}</div>'
            f'<div class="m">{E(x["player"])} <span>{E(str(x.get("team") or ""))}</span></div><div class="cols"><div class="col{" star" if st else ""}"><div class="mk">{E(x["market"].upper())}</div>'
            f'<div class="pk">{E(str(x["side"]).title())} {x["line"]:g}</div>{tag}<div class="px">{px}</div></div>'
            f'<div class="col"><div class="mk">MODEL</div><div class="mg"><div><b>{x["model_pct"]*100:.0f}%</b><span>Sim Bot props model</span></div></div></div></div></div>'
        )
    props.sort(key=lambda x:(x.get("kickoff_ct") or "", -x["model_pct"]))
    pcards=[pcard(x) for x in props]
    phead=f'<div class="c pc" data-sp="NBA PROPS"><div class="h">NBA PROPS · {E(str(today))} only · PAPER / UNPROVEN — NBA props have no graded history; not plays</div><div class="m">Paper record: {pw}-{pl}-{pp} · {"+" if pu>=0 else "−"}${abs(pu):.0f} at $20 flat</div></div>'
    if not pcards: pcards=['<div class="c pc" data-sp="NBA PROPS"><p>No NBA props today.</p></div>']
    # NBA Props tab removed from the desk (Luis Nov 9 2026); do not append prop cards.
    if not P: P=load_picks_panel()
    cards=cards+picks_panels(P)
    sport_btns="".join(f'<button type="button" data-t="{E(x)}">{E(x)}</button>' for x in sports)
    live_n=len((P.get("live") or {}).get("rows") or [])
    blf_n=len((P.get("tiers") or {}).get("rows") or [])
    tabs=('<div class="tabs"><button type="button" class="on" data-t="ALL">All</button>'
          +sport_btns
          +f'<button type="button" data-t="LIVE CARD">Live Card ({live_n})</button>'
          f'<button type="button" data-t="BET LEAN FADE">Bet / Lean / Fade ({blf_n})</button>'
          '<button type="button" data-t="RECORD">Record / Paper</button></div>')
    date_btns=[]
    for d in dates:
        lab=d.strftime("%a %-d")
        on=' class="on"' if d==today else ""
        date_btns.append(f'<button type="button" data-d="{d.isoformat()}"{on}>{E(lab)}</button>')
    dates_html='<div class="dates" id="datechips">'+("".join(date_btns) or f'<button type="button" class="on" data-d="{today.isoformat()}">{E(today.strftime("%a %-d"))}</button>')+'</div>'
    banner='<div class="mock">MOCK DATA — real feed not yet available</div>' if mock else ''
    now=dt.datetime.now(CT)
    now_s=now.strftime("%b %-d %-I:%M %p CT")
    date_label=now.strftime("%a %b %-d, %Y")
    live=P.get("live") or {}
    frec=live.get("filtered_rec") or ["",""]
    recs=(P.get("tiers") or {}).get("records") or {}
    lean=recs.get("LEAN") or {}
    fade=recs.get("FADE") or {}
    rec_html=(_rec_item("Live Card", frec[0] if len(frec)>0 else "—", frec[1] if len(frec)>1 else "", "live")
              +_rec_item("Lean", lean.get("rec"), lean.get("usd"), "lean")
              +_rec_item("Fade", fade.get("rec"), fade.get("usd"), "fade"))
    fx_chips=[]
    for f in (P.get("fixit") or []):
        seg=str(f.get("segment") or "").replace("FIX-IT","").strip()
        seg=re.sub(r"^\d+\.\s*","",seg)
        if len(seg)>28: seg=seg[:27]+"…"
        st=str(f.get("status") or "")
        paper=" paper" if "paper" in st.lower() or "not ready" in st.lower() else ""
        short="paper" if "paper" in st.lower() else (st[:18]+"…" if len(st)>18 else st)
        fx_chips.append(f'<a class="fx-chip{paper}" href="#fixit" data-open="RECORD">{E(seg)} · {E(short)}</a>')
    fixit_html='<div class="fixit-strip"><span class="fx-lab">Fix-it</span>'+("".join(fx_chips) or '<span class="fx-chip">none listed</span>')+'</div>'
    star_usd=("+" if usd>=0 else "−")+f"${abs(usd):.0f}"
    body_cards="".join(cards) or '<p style="padding:14px">No games today.</p>'
    page=(
        '<!doctype html><html lang="en" data-skin="glp-sl-20261110"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Grand Line Picks</title>'
        '<link rel="icon" type="image/png" sizes="32x32" href="assets/favicon-32.png">'
        '<link rel="icon" type="image/png" sizes="48x48" href="assets/favicon-48.png">'
        '<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">'
        '<meta property="og:title" content="Grand Line Picks">'
        '<meta property="og:image" content="assets/og-image.jpg">'
        '<meta name="twitter:card" content="summary">'
        '<meta name="twitter:title" content="Grand Line Picks">'
        '<meta name="twitter:image" content="assets/og-image.jpg">'
        '<!-- glp-restyle 2026-11-10 -->'
        '<style>\n'+CSS+'\n</style></head><body>'+banner+
        '<div class="top"><div class="top-inner">'
        '<div class="brandrow"><div class="brand">'
        '<img src="assets/glp_logo_256.png" width="48" height="48" alt="Grand Line Picks logo">'
        f'<div><div class="t">Grand Line Picks</div><div class="sub">{E(date_label)} · model % only · $20 flat</div></div>'
        '</div></div>'
        f'<div class="recstrip-top">{rec_html}</div>'
        f'<div class="rec-note">★ plays: {w}-{l}-{p} · {star_usd} at $20 flat · built {E(now_s)} · ★ ≥1pp / ★★ ≥3pp vs Bovada · straight bets only</div>'
        f'{fixit_html}'
        '</div></div>'
        f'<div class="navstick"><div class="nav-inner">{dates_html}{tabs}</div></div>'
        f'<main class="board">{body_cards}</main>'
        '<script>\n'+JS+'\n</script></body></html>'
    )
    # Nov 6 2026 (Luis): page-side rollover at midnight CT: hide stale day's games/card/board until the next rebuild
    _bd=str(today)
    _roll=('<script>(function(){var bd="'+_bd+'";function td(){return new Intl.DateTimeFormat("en-CA",{timeZone:"America/Chicago"}).format(new Date())}'
      'function chk(){if(td()===bd)return;var today=td();'
      'document.querySelectorAll(".c").forEach(function(c){var sp=c.dataset.sp||"", dd=c.dataset.date||"";'
      'if(sp==="RECORD"||sp==="BET LEAN FADE")return;'
      'if(dd&&dd>=today)return;'
      'if(sp==="LIVE CARD"||sp==="BOARD AGREE"||sp==="NBA PROPS"||!c.classList.contains("panel")){'
      'c.querySelectorAll("table,.cols,.mo,.ghead,.proj").forEach(function(t){t.remove()});if(!c.querySelector(".stale")){var p=document.createElement("p");p.className="pass stale";'
      'p.textContent="New CT day: yesterday\u2019s games hidden. Today\u2019s board fills on the next refresh.";c.appendChild(p)}}});'
      'var chip=document.querySelector(".dates button[data-d=\'"+today+"\']")||document.querySelector(".dates button:not([data-d=\'"+bd+"\'])");'
      'if(chip){chip.click()}}'
      'chk();setInterval(chk,60000)})();</script>')
    page=page.replace("</body>",_roll+"</body>") if "</body>" in page else page+_roll
    open(os.path.join(H,"index.html"),"w").write(page); print("built","MOCK" if mock else "REAL",len(rows),"rows",sum(1 for c in cards if "data-date=" in c),"games")
main()

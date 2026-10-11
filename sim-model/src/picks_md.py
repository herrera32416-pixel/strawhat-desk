import json, sys, pandas as pd
d=json.load(open(sys.argv[1]))
L=[f"# NFL paper picks: {d['slate']}","",f"**PAPER ONLY.** {d['note']}",f"Lines: {d['lines']}. Weather: Open-Meteo kickoff forecast. QB status: ESPN injury feed.","",
"| Game (CT kick) | QBs | ML: pick, sim% vs mkt% (tier) | Spread | Total | Flags / matchup |","|---|---|---|---|---|---|"]
for g in sorted(d['games'],key=lambda g:g['kickoff_utc']):
    k=pd.Timestamp(g['kickoff_utc']).tz_convert('America/Chicago').strftime('%a %-I:%M%p')
    m={x['market']:x for x in g['markets']}
    f=lambda x:f"{x['pick']} ({x['price']:+d}) {x['sim_pct']} vs {x['market_pct']} ({x['tier']})"
    w=g['weather']; ws=f"wind {w['wind_mph']} mph (gust {w['gust_mph']}), {w['temp_f']}F. " if w else ''
    L.append(f"| {g['away']} @ {g['home']} ({k}) | {g['qbs']['away']} / {g['qbs']['home']} | {f(m['ml'])} | {f(m['spread'])} | {f(m['total'])} | {ws}{'; '.join(g['news_delta_flags']) or ''} {g['matchup_note'].split(' (')[0]} |")
L+=["","Tier = size of the sim-vs-market gap (A 8+, B 5+, C 2+), not a proven edge. The sim leans Over/underdog, so be skeptical of totals tiers."]
open(sys.argv[1].replace('.json','.md'),'w').write('\n'.join(L)); print('wrote',sys.argv[1].replace('.json','.md'))

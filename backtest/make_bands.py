"""Write data/teaser_bands.json: band win counts (non-push) on closing lines, NFL 2006-2025, CFB 2023-2025."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teasers_bt as tb
out = {}
for sport, G in (("nfl", tb.nfl_games()), ("cfb", tb.cfb_games())):
    G = [g for g in G if g["season"] <= 2025]
    L = tb.legs_for(G, sport)
    st = collections.defaultdict(lambda: {"w": 0, "n": 0})
    for l in L:
        if l["res"] == "P": continue
        b = tb.band(l); st[b]["w"] += l["res"] == "W"; st[b]["n"] += 1
    out[sport] = dict(st)
out["_source"] = "nflverse games.csv closes 2006-2025 (NFL); ESPN close 2023-2025 (CFB, desk-v1 history). Non-push legs, teased 6 pts."
json.dump(out, open("data/teaser_bands.json", "w"), indent=1)
print(json.dumps(out, indent=1)[:1500])

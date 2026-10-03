# LINES SOP
**Purpose:** get today's prices. Never invent a price.
1. Call `/v4/sports/{nfl,ncaaf}/events`. This is free (0 credits).
2. NFL: if any game is within 8 days, pull `/odds` with regions `us,eu` and markets `h2h,spreads,totals`, American odds (6 credits). NCAAF: pull only if a game kicks within 36h (6 credits).
3. Save the raw response gzipped as `data/raw/odds/<sport>_<YYYYMMDD_HHMM>.json.gz`, with the CT pull time and the credit headers.
4. `market.parse_event` makes two-sided per-book markets. A total is kept only when Over and Under share a point.
5. Targets are `draftkings` and `bovada`. Betr is not carried by The Odds API, so it is never shown with a made-up price.
6. If a pull is refused by BUDGET, the desk falls back to the latest saved file. The site shows its "odds as of" time.

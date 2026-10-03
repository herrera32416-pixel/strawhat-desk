# Strawhat Desk team roster

Each role is one deterministic module. `desk/run.py` runs them in order in GitHub Actions at 9:00am CT. None of them is a chat bot. They never place bets, touch Robinhood, or message anyone.

| Role | Module | SOP | Output |
|---|---|---|---|
| LINES | `desk/lines.py`, `desk/market.py` | [LINES.md](LINES.md) | `data/raw/odds/*.json.gz` |
| KEYS | `desk/keys.py` | [KEYS.md](KEYS.md) | outcome pmfs and fair centers (in memory) |
| SHOPPER (Board) | `desk/board.py` | [SHOPPER.md](SHOPPER.md) | `docs/data/board.json` |
| PROPS | `desk/props.py`, `desk/props_run.py` | [PROPS.md](PROPS.md) | `data/raw/props/*.json`, `docs/data/props.json` |
| TEASERS | `desk/teasers.py`, `desk/teaser_math.py` | [TEASERS.md](TEASERS.md) | `docs/data/teasers.json` |
| GRADER | `desk/grader.py`, `desk/espn.py` | [GRADER.md](GRADER.md) | `data/ledger/ledger.json` |
| PUBLISHER | `desk/run.py`, `docs/` | [PUBLISHER.md](PUBLISHER.md) | GitHub Pages site |
| BUDGET | `desk/toa.py` | [BUDGET.md](BUDGET.md) | `data/credits.jsonl` |

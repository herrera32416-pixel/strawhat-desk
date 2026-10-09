# Strawhat Desk team roster

Each role is one deterministic module. `desk/run.py` runs them in order in GitHub Actions at 9:00am CT. None of them is a chat bot. They never place bets, touch Robinhood, or message anyone.

| Role | Module | SOP | Output |
|---|---|---|---|
| LINES | `desk/lines.py`, `desk/market.py` | [LINES.md](LINES.md) | `data/raw/odds/*.json.gz` |
| KEYS | `desk/keys.py` | [KEYS.md](KEYS.md) | outcome pmfs and fair centers (in memory) |
| SHOPPER (Board) | `desk/board.py` | [SHOPPER.md](SHOPPER.md) | `docs/data/board.json` |
| PROPS | `desk/props.py`, `desk/props_run.py` | [PROPS.md](PROPS.md) | `data/raw/props/*.json`, `docs/data/props.json` |
| ~~TEASERS~~ (retired 2026-10-08) | removed; `desk/teaser_math.py` kept only for grading old tickets | [TEASERS.md](TEASERS.md) | none |
| GRADER | `desk/grader.py`, `desk/espn.py` | [GRADER.md](GRADER.md) | `data/ledger/ledger.json` |
| PUBLISHER | `desk/run.py`, `docs/` | [PUBLISHER.md](PUBLISHER.md) | GitHub Pages site |
| BUDGET | `desk/toa.py` | [BUDGET.md](BUDGET.md) | `data/credits.jsonl` |
| MATCHUP (info only) | `desk/matchup_data.py`, `desk/matchup.py`, `desk/matchup_cfb.py` | [MATCHUP.md](MATCHUP.md) | `data/matchup/*`, `docs/data/matchups.json` |
| SIM (info only) | `desk/sim.py`, `desk/sim_run.py` | [SIM.md](SIM.md) | `docs/data/sim.json`, `data/sim_backtest.json` |
| RECHECK | `desk/recheck_plan.py`, `desk/recheck.py` | [RECHECK.md](RECHECK.md) | `docs/data/recheck.json`, `data/recheck_done.json` |
| NBA (info only) | `desk/nba_data.py`, `desk/nba_match.py`, `desk/nba_sim.py`, `desk/nba_run.py` | [NBA.md](NBA.md) | `data/nba/*`, `docs/data/nba.json` |
| NHL (info only) | `desk/nhl_data.py`, `desk/nhl_match.py`, `desk/nhl_sim.py`, `desk/nhl_run.py` | [NHL.md](NHL.md) | `data/nhl/*`, `docs/data/nhl.json` |

NBA/NHL run in their own workflow (`.github/workflows/pro.yml`, `desk/pro_run.py`, shared helpers `desk/pro_ratings.py` + `desk/pro_lines.py`), same concurrency group as the daily desk, so the two never overlap.

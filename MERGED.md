# One desk (merged Oct 9 2026)
Strawhat Desk is now the single betting desk (its look, its tabs). desk-v1's pipeline lives in `v1/`:
- `.github/workflows/v1-board.yml` (9:15am CT + backups, once-per-day guard): ESPN grading, DailyFaceoff goalies, the ONE
  Odds API pipeline (free tier, only when a game is within ~36h; ESPN fills gaps) and the ONE PAPER grader/scorecard
  (`v1/data/paper_ledger.json`). Publishes `docs/data/v1/{today,paper,paper_ledger}.json`.
- `.github/workflows/v1-goalies.yml`: NHL goalie checks before puck drop.
- `daily.yml` / `pro.yml` keep Props, Matchups, Sim, NBA, NHL sim and the pre-kick recheck, with NO Odds API key (ESPN only).
  `desk/run.py` no longer logs new rows to `data/ledger/ledger.json` (history, incl. retired teasers).
Rules: paper only, straight bets only, CT start-time sort, ML/spread/total each with model % (blank stays blank).
desk-v1 repo: workflows disabled, Pages shows a banner pointing here.

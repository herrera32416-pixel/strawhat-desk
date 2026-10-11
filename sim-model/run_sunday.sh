#!/usr/bin/env bash
# One command to refresh NFL paper picks on fresh lines:  bash /workspace/sim-model/run_sunday.sh [nflverse_week] [out_name]
# Uses the newest desk Odds API file already committed to strawhat-desk (spends no credits), fresh ESPN QB injuries,
# and a fresh Open-Meteo kickoff forecast. Sim numbers come from out/nfl_v2_preds.parquet (rebuild weekly, see README).
set -euo pipefail
cd "$(dirname "$0")"
curl -sfL -o data/nfl/games.csv https://github.com/nflverse/nfldata/raw/master/data/games.csv
WEEK=${1:-$(python3 -c "import pandas as pd;g=pd.read_csv('data/nfl/games.csv');u=g[(g.season==2026)&g.result.isna()];print(int(u.week.min()))")}
OUT=${2:-out/picks/nfl_2026_w$((WEEK+1)).json}   # file label = Luis's week numbering (nflverse week + 1)
if [ "${REBUILD:-1}" = 1 ]; then   # refresh pbp + ratings + sim for the upcoming week (walk-forward safe: only finished games feed ratings)
  curl -sfL -o data/nfl/pbp_2026.parquet https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet
  python3 src/nfl_build.py >/dev/null
  (export LEAGUE=nfl TAG=_v2 DECAY=0.95 PK=1.0 CARRY=0.8 ALPHA=0.5 UPCOMING_WEEK=$WEEK PYTHONPATH=src; python3 src/build_features.py && python3 src/sim_eval.py >/dev/null && python3 src/calibrate.py out/nfl_sim_preds_v2.parquet out/nfl_v2_preds.parquet >/dev/null)
fi
git -C /workspace/strawhat-desk fetch -q origin
F=$(git -C /workspace/strawhat-desk ls-tree --name-only origin/main data/raw/odds/ | grep -E 'odds/nfl_[0-9]{8}_[0-9]{4}\.json\.gz$' | sort | tail -1)
git -C /workspace/strawhat-desk show "origin/main:$F" > "data/odds/$(basename "$F")"
echo "lines: $F"
INJ=data/espn_nfl_injuries_$(date +%Y%m%d_%H%M).json
curl -sf https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries -o "$INJ"
PYTHONPATH=src python3 src/nfl_slate_picks.py "data/odds/$(basename "$F")" "$WEEK" "$OUT" "$INJ"
python3 src/picks_md.py "$OUT"
PYTHONPATH=src python3 src/paper_track.py log "$OUT"

#!/usr/bin/env bash
# No cron daemon on the box: a light loop instead. Sundays 08:30 CT refresh picks + log paper; grade every 6h (idempotent).
# Start: nohup bash /workspace/sim-model/scheduler.sh >/workspace/sim-model/out/paper/scheduler.log 2>&1 &
cd "$(dirname "$0")"
last_sun=""
while true; do
  d=$(date +%u); hm=$(date +%H%M); today=$(date +%F)
  if [ "$d" = 7 ] && [ "$hm" -ge 0830 ] && [ "$hm" -lt 1200 ] && [ "$last_sun" != "$today" ]; then bash run_sunday.sh && last_sun=$today; fi
  [ $(( $(date +%s) / 60 % 360 )) -lt 15 ] && bash grade_paper.sh
  sleep 900
done

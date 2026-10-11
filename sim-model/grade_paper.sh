#!/usr/bin/env bash
# Grade v3.1 NFL totals paper picks against nflverse finals. Scheduled via crontab (Mon 9:00 and Tue 9:00 CT).
cd "$(dirname "$0")" && PYTHONPATH=src python3 src/paper_track.py grade

# PUBLISHER SOP
- Writes `docs/data/{board,props,ledger,meta}.json`. The static `docs/index.html` and `app.js` render the Board, NFL Props, Ledger and Method tabs (Teasers tab removed 2026-10-08; the ledger hides retired teaser/parlay tickets).
- Mobile-first layout. All times are CT, and the generated time is stamped.
- The workflow commits `data/` and `docs/`. GitHub Pages serves `main:/docs`.
- The Method tab is updated by hand only when a backtest is re-run. Every number on it must trace to `backtest/out/*.csv`.

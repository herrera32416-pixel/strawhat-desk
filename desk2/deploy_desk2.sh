#!/bin/bash
# Rebuild + deploy Grand Line Picks desk2 (docs/desk2/index.html + assets). Usual rule: commit those files, manual stash, pull --rebase, pop,
# credits.jsonl conflict -> union of unique lines. Soft-fails.
# Branding assets live in desk2/assets and docs/desk2/assets; build.py embeds the Grand Line Picks header/favicon/og tags so daily rebuilds keep branding.
cd /workspace/strawhat-desk || exit 0
python3 desk2/build.py || { echo "desk2 build failed"; exit 0; }
cp desk2/index.html docs/desk2/index.html
mkdir -p docs/desk2/assets
# Keep published assets in sync with source assets (never drop logo/favicon)
cp -a desk2/assets/. docs/desk2/assets/ 2>/dev/null || true
git add docs/desk2/index.html docs/desk2/assets
# Also track source assets + build.py so branding survives clones
git add desk2/assets desk2/build.py 2>/dev/null || true
git diff --cached --quiet && { echo "desk2: no changes $(date)"; exit 0; }
git commit -qm "desk2 auto rebuild $(date '+%F %H:%M') CT" -- docs/desk2/index.html docs/desk2/assets desk2/assets desk2/build.py 2>/dev/null \
  || git commit -qm "desk2 auto rebuild $(date '+%F %H:%M') CT"
st=0; git stash -u -q && st=1
git pull --rebase -q || { git rebase --abort 2>/dev/null; echo "desk2: pull failed"; }
if [ $st = 1 ]; then
  if ! git stash pop -q 2>/dev/null; then
    if git diff --name-only --diff-filter=U | grep -q '^data/credits.jsonl$'; then
      (git show :2:data/credits.jsonl; git show :3:data/credits.jsonl) | awk '!seen[$0]++' > /tmp/_cr && cp /tmp/_cr data/credits.jsonl
    fi
    if [ -z "$(git diff --name-only --diff-filter=U | grep -v '^data/credits.jsonl$')" ]; then git reset -q; git stash drop -q; else echo "desk2: stash pop conflict, stash kept"; git reset -q; fi
  fi
fi
git push -q && echo "desk2: pushed $(git log -1 --format=%h) $(date)" || echo "desk2: push failed"

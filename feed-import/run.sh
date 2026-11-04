#!/bin/sh
# Full pipeline. Compares against the live state (https://brockman.news/brockman.json), fetched fresh every run.
# Delete results.jsonl, bodies/, feedcheck.tsv and validate-runs.jsonl for a fresh validation run;
# validate.py otherwise resumes.
set -eu
cd "$(dirname "$0")"
curl -sSf -o /tmp/brockman-state.json https://brockman.news/brockman.json
# optional, needs a Media Cloud token (~/.config/mediacloud/token): news outlets -> sources/mediacloud.txt
[ -f sources/mediacloud.txt ] || { [ -f ~/.config/mediacloud/token ] && ./py mediacloud.py; } || true
./py harvest.py                       # -> candidates.json, harvest-stats.json
./py validate.py 2>&1 | tee -a validate.log   # -> results.jsonl, bodies/
# Rate-limited candidates (HTTP 429: DreamHost throttles one client hitting many of its customers, Vercel
# challenges) are not re-fetched here; finalize.py lists them in retry-429.txt for a second batch, e.g.
#   ./py validate.py --refetch-status 429 --concurrency 2 --pace 2
# (--refetch-error timeout,connect,dns --per-ip 1 --pace 1 likewise re-tries throttled timeouts.)
# brockman's own feed parser (Haskell `feed` library), see feedcheck.hs
nix shell --impure --expr 'with (builtins.getFlake "nixpkgs").legacyPackages.${builtins.currentSystem}; haskellPackages.ghcWithPackages (p: with p; [ feed text bytestring ])' \
  -c ghc -O1 -rtsopts -outputdir /tmp/feedcheck-build -o feedcheck feedcheck.hs
./py finalize.py                      # -> new-bots.json, report.md, accepted.jsonl
./py spotcheck.py                     # appends the re-fetch spot-check to report.md

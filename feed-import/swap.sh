#!/usr/bin/env bash
# usage: ./swap.sh news-active/changes.json
# applies the news cleanup from select_active.py on brockman.news: removes, re-points (nick kept) and adds news bots.
# Unlike import.sh it changes existing bots, so it refuses to run if any bot it touches differs from what
# select_active.py saw (removed/changed bots must still have the old feed; added nicks must be free).
# Afterwards start watchdog.sh on the server like after an import (the backup has the same name pattern).
set -euo pipefail
changes=${1:?changes.json}
host=root@brockman.news

jq -e '(.remove | type == "object") and (.change | all(.[]; has("from") and has("to"))) and (.add | all(.[]; has("feed")))' \
  "$changes" >/dev/null
scp -q "$changes" "$host:/root/news-changes.json"
ssh "$host" bash -s <<'EOF'
set -euo pipefail
state=/var/lib/brockman/brockman.json
jq() { nix run nixpkgs#jq -- "$@"; }
c=/root/news-changes.json
# changed bots must still carry the feed select_active.py saw; added nicks must still be free
missing=$(jq -r --slurpfile c "$c" '.bots as $b | [$c[0].remove | keys[] | select($b[.] == null)] | length' "$state")
stale=$(jq -r --slurpfile c "$c" '.bots as $b | [$c[0].change | to_entries[] | select($b[.key].feed != .value.from)] | length' "$state")
clash=$(jq -r --slurpfile c "$c" '.bots as $b | [$c[0].add | keys[] | select($b[.] != null)] | length' "$state")
echo "missing removes: $missing, stale changes: $stale, nick clashes: $clash"
if [ "$stale" != 0 ] || [ "$clash" != 0 ]; then echo "state moved on since select_active.py ran; aborting"; exit 1; fi
cp -a "$state" "/var/lib/brockman/brockman_before-import_$(date +%s).json"
before=$(jq '.bots | length' "$state")
systemctl stop brockman
jq --slurpfile c "$c" '
  .bots |= (reduce ($c[0].remove | keys[]) as $n (.; del(.[$n]))
            | reduce ($c[0].change | to_entries[]) as $e (.; .[$e.key].feed = $e.value.to)
            | $c[0].add + .)' "$state" > "$state.tmp"
chown brockman:brockman "$state.tmp"; chmod 664 "$state.tmp"
mv "$state.tmp" "$state"
systemctl start brockman
echo "bots: $before -> $(jq '.bots | length' "$state")"
EOF

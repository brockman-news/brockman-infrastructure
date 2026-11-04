#!/usr/bin/env bash
# usage: ./import.sh new-bots.json
# merges new bots into brockman's state on brockman.news; existing bots always win
set -euo pipefail
new=${1:?new-bots.json}
host=root@brockman.news
state=/var/lib/brockman/brockman.json

jq -e 'type == "object" and all(.[]; has("feed"))' "$new" >/dev/null
scp -q "$new" "$host:/root/new-bots.json"
ssh "$host" bash -s <<'EOF'
set -euo pipefail
state=/var/lib/brockman/brockman.json
jq() { nix run nixpkgs#jq -- "$@"; }
cp -a "$state" "/var/lib/brockman/brockman_before-import_$(date +%s).json"
before=$(jq '.bots | length' "$state")
systemctl stop brockman
jq --slurpfile new /root/new-bots.json '.bots = ($new[0] + .bots)' "$state" > "$state.tmp"
chown brockman:brockman "$state.tmp"; chmod 664 "$state.tmp"
mv "$state.tmp" "$state"
systemctl start brockman
echo "bots: $before -> $(jq '.bots | length' "$state")"
EOF

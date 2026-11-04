#!/usr/bin/env bash
# runs ON brockman.news after an import (see import.sh): for 30 minutes, if available memory drops below 2 GB,
# stop brockman, restore the newest brockman_before-import_*.json and start it again.
# start detached (systemd-run's PATH lacks coreutils): systemd-run --unit=brockman-import-watchdog --collect -E PATH=/run/current-system/sw/bin bash /root/watchdog.sh
set -euo pipefail
cd /var/lib/brockman
for _ in $(seq 180); do
  avail=$(awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo)
  mem=$(( $(systemctl show brockman -p MemoryCurrent --value) / 1048576 ))
  echo "$(date +%T) avail=${avail}M brockman=${mem}M"
  if [ "$avail" -lt 2048 ]; then
    backup=$(ls -t brockman_before-import_*.json | head -1)
    echo "low memory: restoring $backup"
    systemctl stop brockman
    cp -a brockman.json "brockman_rolled-back_$(date +%s).json"
    cp -a "$backup" brockman.json
    systemctl start brockman
    exit 1
  fi
  sleep 10
done
echo "no problem in 30 minutes"

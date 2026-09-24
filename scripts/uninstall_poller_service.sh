#!/usr/bin/env bash
# Stop and remove the GTFS-RT poller LaunchAgent installed by
# scripts/install_poller_service.sh. The poller process itself stops;
# already-collected data in Postgres is untouched.
set -euo pipefail

LABEL="com.brisbane-transit.gtfs-realtime-poller"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST_DEST" ]; then
    echo "Not installed (no $PLIST_DEST)"
    exit 0
fi

launchctl unload "$PLIST_DEST" 2>/dev/null || true
rm -f "$PLIST_DEST"

echo "Uninstalled $LABEL"

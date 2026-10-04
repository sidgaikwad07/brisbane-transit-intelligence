#!/usr/bin/env bash
# Remove the scheduled jobs installed by scripts/install_automation.sh.
# The pollers and already-collected data are untouched.
set -euo pipefail

for job in health-check weekly-refresh; do
    LABEL="com.brisbane-transit.$job"
    PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
    if [ -f "$PLIST_DEST" ]; then
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        rm -f "$PLIST_DEST"
        echo "Uninstalled $LABEL"
    else
        echo "Not installed: $LABEL"
    fi
done

#!/usr/bin/env bash
# Install the BCC traffic poller as a macOS LaunchAgent — same reasoning as
# scripts/install_poller_service.sh, mirrored for ingestion.bcc_traffic.
#
# Idempotent: re-running this after a code change reinstalls cleanly.
# Uninstall with scripts/uninstall_traffic_poller_service.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
LABEL="com.brisbane-transit.traffic-poller"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$REPO_ROOT/logs"

if [ ! -x "$PYTHON" ]; then
    echo "No venv python at $PYTHON — create it first:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

mkdir -p "$LOG_DIR"

launchctl unload "$PLIST_DEST" 2>/dev/null || true

sed \
    -e "s#{{REPO_ROOT}}#$REPO_ROOT#g" \
    -e "s#{{PYTHON}}#$PYTHON#g" \
    -e "s#{{LABEL}}#$LABEL#g" \
    "$REPO_ROOT/scripts/poller_service/com.brisbane-transit.traffic-poller.plist.template" > "$PLIST_DEST"

launchctl load -w "$PLIST_DEST"

echo "Installed and started: $LABEL"
echo "Plist:  $PLIST_DEST"
echo "Logs:   $LOG_DIR/traffic_poller.log"
echo ""
echo "Check it's running:  launchctl list | grep brisbane-transit"
echo "Uninstall:            scripts/uninstall_traffic_poller_service.sh"

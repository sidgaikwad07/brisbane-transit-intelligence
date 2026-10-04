#!/usr/bin/env bash
# Install the two scheduled jobs as macOS LaunchAgents:
#   - health check every 15 minutes (scripts/health_check.py): notifies
#     when live data stops arriving
#   - weekly refresh, Mondays 06:00 (scripts/weekly_refresh.py): reloads
#     static data, regenerates every finding, opens a GitHub PR for review
#
# The two pollers have their own installers (install_poller_service.sh,
# install_traffic_poller_service.sh) — they run continuously, these on a
# schedule. Idempotent; uninstall with scripts/uninstall_automation.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs"

if [ ! -x "$PYTHON" ]; then
    echo "No venv python at $PYTHON — create it first:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi
for tool in git gh; do
    if ! command -v "$tool" >/dev/null; then
        echo "$tool not found on PATH — the weekly refresh needs it to open PRs" >&2
        exit 1
    fi
done
if ! gh auth status >/dev/null 2>&1; then
    echo "gh is not logged in — run: gh auth login" >&2
    exit 1
fi

# The weekly job runs without your shell profile, so give it the directories
# git and gh actually live in.
JOB_PATH="$REPO_ROOT/.venv/bin:$(dirname "$(command -v gh)"):$(dirname "$(command -v git)"):/usr/bin:/bin"

mkdir -p "$LOG_DIR"

for job in health-check weekly-refresh; do
    LABEL="com.brisbane-transit.$job"
    PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    sed \
        -e "s#{{REPO_ROOT}}#$REPO_ROOT#g" \
        -e "s#{{PYTHON}}#$PYTHON#g" \
        -e "s#{{LABEL}}#$LABEL#g" \
        -e "s#{{PATH}}#$JOB_PATH#g" \
        "$REPO_ROOT/scripts/poller_service/$LABEL.plist.template" > "$PLIST_DEST"
    launchctl load -w "$PLIST_DEST"
    echo "Installed: $LABEL"
done

echo ""
echo "Health check: every 15 min — log: logs/health_check.log"
echo "Weekly refresh: Mondays 06:00 — log: logs/weekly_refresh.log"
echo "Run the refresh now:  launchctl kickstart gui/$(id -u)/com.brisbane-transit.weekly-refresh"
echo "Uninstall:            scripts/uninstall_automation.sh"

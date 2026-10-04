"""Check that live data is still arriving, and raise a macOS notification
when it isn't.

Why this exists: on 2026-10-03 the BCC traffic poller was locked out by the
portal's daily rate limit and lost ~16 hours of data that can never be
backfilled (the feed keeps no history). The process was "running" the whole
time — launchd's KeepAlive only catches crashes, not a poller that's alive
but failing every poll. The only reliable signal is whether new rows are
landing in the database, so that's what this checks.

Alerts only on a change (ok -> stale, or recovery), with a reminder every
REMIND_AFTER while a problem persists — so a laptop left asleep overnight
produces one notification, not one every 15 minutes. State lives in
logs/health_state.json; every run appends one line to logs/health_check.log.

Runs every 15 minutes as a LaunchAgent (scripts/install_automation.sh).

Usage:
    python scripts/health_check.py            # check, notify on change
    python scripts/health_check.py --print    # just print current status
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text

from ingestion.config import DATABASE_URL

STATE_PATH = REPO_ROOT / "logs" / "health_state.json"
LOG_PATH = REPO_ROOT / "logs" / "health_check.log"
TRAFFIC_LOG_PATH = REPO_ROOT / "logs" / "traffic_poller.log"
REMIND_AFTER = timedelta(hours=6)


@dataclass(frozen=True)
class Source:
    name: str
    table: str
    time_column: str
    max_age: timedelta


# Thresholds sit well above each poller's normal cadence (GTFS-RT every 30s,
# traffic every 2 min, but the traffic feed itself publishes in irregular
# batches several minutes apart), so a single slow poll doesn't alert.
SOURCES = [
    Source("Transit trip updates", "raw.trip_updates", "polled_at", timedelta(minutes=15)),
    Source("Vehicle positions", "raw.vehicle_positions", "polled_at", timedelta(minutes=15)),
    Source("Traffic", "raw.intersection_traffic", "fetched_at", timedelta(minutes=30)),
]


def latest_timestamps(engine) -> dict[str, datetime | None]:
    with engine.connect() as conn:
        return {
            s.name: conn.execute(text(f"SELECT max({s.time_column}) FROM {s.table}")).scalar() for s in SOURCES
        }


def find_problems(latest: dict[str, datetime | None], now: datetime) -> dict[str, str]:
    """{source name: human-readable problem} for every stale source."""
    problems = {}
    for s in SOURCES:
        last = latest.get(s.name)
        if last is None:
            problems[s.name] = "no data at all"
        elif now - last > s.max_age:
            problems[s.name] = f"no new data for {_age(now - last)}"
    return problems


def traffic_rate_limit_hint() -> str | None:
    """The traffic poller logs a WARNING when the portal's daily quota is
    exhausted — worth saying so, since the fix is different (wait for the
    10am reset) from a crashed poller."""
    try:
        with open(TRAFFIC_LOG_PATH, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4000))
            tail = f.read().decode(errors="replace")
    except OSError:
        return None
    # The poller logs the WARNING, then that poll's summary line, then sleeps.
    recent = "\n".join(tail.splitlines()[-3:])
    return "BCC API daily limit reached" if "daily call limit reached" in recent else None


def decide_notifications(
    previous: dict, problems: dict[str, str], now: datetime
) -> tuple[list[str], dict]:
    """Messages to send now, and the state to persist. Notify when a source
    goes stale, every REMIND_AFTER while it stays stale, and once when it
    recovers."""
    messages, state = [], {}
    for name in {*previous, *problems}:
        prev = previous.get(name, {})
        if name in problems:
            last_alert = prev.get("last_alert")
            due = last_alert is None or now - datetime.fromisoformat(last_alert) >= REMIND_AFTER
            if due:
                messages.append(f"{name}: {problems[name]}")
            state[name] = {"status": "stale", "last_alert": now.isoformat() if due else last_alert}
        elif prev.get("status") == "stale":
            messages.append(f"{name}: recovered")
    return messages, state


def notify(message: str) -> None:
    script = f"display notification {json.dumps(message)} with title \"Brisbane transit data\""
    subprocess.run(["osascript", "-e", script], check=False)


def _age(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes / 60:.1f} h"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true", help="Print status only; don't notify or save state")
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc)
    try:
        latest = latest_timestamps(create_engine(DATABASE_URL))
        problems = find_problems(latest, now)
    except Exception as e:  # DB down (Docker stopped, laptop just woke) is itself the problem
        latest = {}
        problems = {"Database": f"unreachable ({type(e).__name__}) — is Docker running?"}

    if "Traffic" in problems and (hint := traffic_rate_limit_hint()):
        problems["Traffic"] += f" ({hint}; resumes 10am Brisbane time)"

    status = "; ".join(f"{k}: {v}" for k, v in problems.items()) or "all sources fresh"
    if args.print:
        for s in SOURCES:
            last = latest.get(s.name)
            print(f"{s.name:<22} last data {_age(now - last) + ' ago' if last else 'never'}")
        print(f"\nStatus: {status}")
        return 1 if problems else 0

    try:
        previous = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        previous = {}
    messages, state = decide_notifications(previous, problems, now)
    for message in messages:
        notify(message)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))
    with open(LOG_PATH, "a") as f:
        f.write(f"{now:%Y-%m-%d %H:%M:%S}Z {status}" + (f" [notified: {len(messages)}]" if messages else "") + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

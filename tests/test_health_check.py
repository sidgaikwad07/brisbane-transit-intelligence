import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from health_check import REMIND_AFTER, decide_notifications, find_problems

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def test_find_problems_flags_only_stale_sources():
    latest = {
        "Transit trip updates": NOW - timedelta(minutes=1),
        "Vehicle positions": NOW - timedelta(minutes=20),  # threshold 15 min
        "Traffic": None,
    }
    problems = find_problems(latest, NOW)
    assert set(problems) == {"Vehicle positions", "Traffic"}
    assert problems["Traffic"] == "no data in the last 24 h"


def test_new_problem_notifies_once_then_waits_for_reminder():
    problems = {"Traffic": "no new data for 45 min"}
    messages, state = decide_notifications({}, problems, NOW)
    assert messages == ["Traffic: no new data for 45 min"]

    # 15 minutes later, still stale: no repeat notification
    messages, state = decide_notifications(state, problems, NOW + timedelta(minutes=15))
    assert messages == []

    # After REMIND_AFTER: reminder
    messages, _ = decide_notifications(state, problems, NOW + REMIND_AFTER)
    assert messages == ["Traffic: no new data for 45 min"]


def test_recovery_notifies_and_clears_state():
    _, state = decide_notifications({}, {"Traffic": "stale"}, NOW)
    messages, state = decide_notifications(state, {}, NOW + timedelta(minutes=15))
    assert messages == ["Traffic: recovered"]
    assert state == {}

    messages, _ = decide_notifications(state, {}, NOW + timedelta(minutes=30))
    assert messages == []

"""Poll Brisbane City Council's SCATS intersection traffic feed and append
every new reading to Postgres.

Unlike the GTFS static feed, this dataset has no historical archive: the API
only ever exposes a rolling ~5-minute window of the most recent signal
readings across ~20,000 records (verified 2026-09-25). So, same as GTFS-RT,
there is nothing to backfill — the only way to build a time series is to
poll continuously starting now and let our own table become the history.

Each poll fetches only records newer than the last one we've already stored
(`where=recorded>'<last_seen>'`) in a single call to the dataset's bulk
export endpoint.

Why one call matters: the portal allows anonymous users 5,000 API calls per
day, reset at 00:00 UTC (10am Brisbane). The original version paged the
records endpoint 100 at a time — ~150 calls per poll, every 2 minutes — and
was locked out with HTTP 429 for most of every day (found 2026-10-04: only
2-14 hours of data per day since collection began). One export call per
poll is 720 calls/day. If the quota is exhausted anyway, the poller sleeps
until the reset time the API reports instead of retrying every 2 minutes.

Usage:
    python -m ingestion.bcc_traffic                 # poll forever, Ctrl+C to stop
    python -m ingestion.bcc_traffic --once            # single poll, for testing
    python -m ingestion.bcc_traffic --interval 90      # poll every 90s (default 120s)
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ingestion.config import BCC_TRAFFIC_EXPORT_URL, DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 120
REQUEST_TIMEOUT_SEC = 60  # an export returns up to ~20K records in one response
RATE_LIMIT_RESET_MARGIN_SEC = 60

_FIELDS = [
    "dbid",
    "recorded",
    "ct",
    "ss",
    "tsc",
    "lane",
    "ds1",
    "mf1",
    "rf1",
    "ds2",
    "mf2",
    "rf2",
    "ds3",
    "mf3",
    "rf3",
    "ds4",
    "mf4",
    "rf4",
]


class RateLimited(Exception):
    """The portal's daily anonymous-call quota is exhausted."""

    def __init__(self, reset_at: datetime):
        super().__init__(f"BCC API daily call limit reached; resets at {reset_at.isoformat()}")
        self.reset_at = reset_at


def _rate_limit_reset(resp: requests.Response) -> datetime:
    """When a 429'd quota resets: the error body's `reset_time` if present,
    else the next 00:00 UTC (the documented daily reset)."""
    try:
        return datetime.fromisoformat(resp.json()["reset_time"].replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        now = datetime.now(tz=timezone.utc)
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_new_records(since: datetime) -> list[dict]:
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S%z")
    since_str = since_str[:-2] + ":" + since_str[-2:]  # +1000 -> +10:00
    params = {
        "where": f"recorded>'{since_str}'",
        "select": ",".join(_FIELDS),
        "order_by": "recorded asc",
    }
    resp = requests.get(BCC_TRAFFIC_EXPORT_URL, params=params, timeout=REQUEST_TIMEOUT_SEC)
    if resp.status_code == 429:
        raise RateLimited(_rate_limit_reset(resp))
    resp.raise_for_status()
    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) < 500:
        log.warning("BCC API calls remaining today: %s", remaining)
    return resp.json()


def parse_records(records: list[dict], fetched_at: datetime) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    rows = []
    for r in records:
        rows.append(
            {
                "fetched_at": fetched_at,
                "dbid": r.get("dbid"),
                "recorded_at": r.get("recorded"),
                "tsc": r.get("tsc"),
                "ss": r.get("ss"),
                "lane": r.get("lane"),
                "cycle_time_sec": int(r["ct"]) if r.get("ct") not in (None, "") else None,
                **{
                    f"{metric}{lane}": (
                        float(r[f"{metric}{lane}"]) if r.get(f"{metric}{lane}") not in (None, "") else None
                    )
                    for metric in ("ds", "mf", "rf")
                    for lane in (1, 2, 3, 4)
                },
            }
        )
    df = pd.DataFrame(rows)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    return df


def write_rows(engine: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    df.to_sql(
        "intersection_traffic",
        engine,
        schema="raw",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=2000,
    )
    return len(df)


def latest_recorded_at(engine: Engine) -> datetime | None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(recorded_at) FROM raw.intersection_traffic")).scalar()
    return result


def poll_once(engine: Engine, since: datetime) -> tuple[int, datetime]:
    fetched_at = datetime.now(tz=timezone.utc)
    records = fetch_new_records(since)
    df = parse_records(records, fetched_at)
    n = write_rows(engine, df)
    new_since = df["recorded_at"].max().to_pydatetime() if not df.empty else since
    return n, new_since


def _handle_sigterm(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Poll a single time and exit (for testing)")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    # The feed's own "recorded" clock lags wall-clock by several minutes and
    # advances in irregular batches (observed: sits still for minutes, then
    # jumps), not every second — so a short lookback on first run can miss
    # the entire current window. 30 minutes is comfortably wider than any
    # lag/batch gap seen in testing.
    since = latest_recorded_at(engine) or (datetime.now(tz=timezone.utc) - timedelta(minutes=30))
    log.info("Starting BCC traffic poller (interval=%ss, since=%s)", args.interval, since)

    n_polls = 0
    total_rows = 0
    try:
        while True:
            start = time.monotonic()
            wait = None
            try:
                n, since = poll_once(engine, since)
                total_rows += n
            except RateLimited as e:
                # Polling again before the reset only returns more 429s.
                wait = (e.reset_at - datetime.now(tz=timezone.utc)).total_seconds() + RATE_LIMIT_RESET_MARGIN_SEC
                log.warning("%s; sleeping %.0f min", e, wait / 60)
                n = -1
            except Exception:
                log.exception("Traffic poll failed")
                n = -1
            n_polls += 1
            log.info("Poll #%d: intersection_traffic=%d (watermark=%s)", n_polls, n, since)

            if args.once:
                break

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, wait if wait is not None else args.interval - elapsed))
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Stopped after %d polls. Total rows written: %d", n_polls, total_rows)


if __name__ == "__main__":
    main()

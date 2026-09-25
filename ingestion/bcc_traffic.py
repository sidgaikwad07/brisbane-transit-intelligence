"""Poll Brisbane City Council's SCATS intersection traffic feed and append
every new reading to Postgres.

Unlike the GTFS static feed, this dataset has no historical archive: the API
only ever exposes a rolling ~5-minute window of the most recent signal
readings across ~20,000 records (verified 2026-09-25). So, same as GTFS-RT,
there is nothing to backfill — the only way to build a time series is to
poll continuously starting now and let our own table become the history.

Each poll fetches only records newer than the last one we've already stored
(`where=recorded>'<last_seen>'`, paginated 100 at a time — the API's max page
size), so polls after the first are cheap regardless of how large the
rolling window is.

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

from ingestion.config import BCC_TRAFFIC_API_URL, DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 120
REQUEST_TIMEOUT_SEC = 20
PAGE_SIZE = 100
# The API rejects offset + limit > 10,000 (no cursor pagination available),
# so a single `where` filter can only page through 10,000 records before we
# have to re-issue the query with `since` advanced to what we've seen so far.
MAX_OFFSET = 9900
MAX_CHUNKS_PER_POLL = 5  # 5 x 10,000 — a full-rolling-window safety cap

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


def fetch_page(since: datetime, offset: int) -> list[dict]:
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S%z")
    since_str = since_str[:-2] + ":" + since_str[-2:]  # +1000 -> +10:00
    params = {
        "limit": PAGE_SIZE,
        "offset": offset,
        "order_by": "recorded asc",
        "where": f"recorded>'{since_str}'",
        "select": ",".join(_FIELDS),
    }
    resp = requests.get(BCC_TRAFFIC_API_URL, params=params, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_new_records(since: datetime) -> list[dict]:
    records: list[dict] = []
    for _ in range(MAX_CHUNKS_PER_POLL):
        offset = 0
        chunk: list[dict] = []
        caught_up = False
        while offset <= MAX_OFFSET:
            page = fetch_page(since, offset)
            if not page:
                caught_up = True
                break
            chunk.extend(page)
            offset += PAGE_SIZE
            if len(page) < PAGE_SIZE:
                caught_up = True
                break
        records.extend(chunk)
        if caught_up or not chunk:
            break
        # Hit the offset cap with more records still pending — advance the
        # filter past what we've already collected and keep going.
        since = max(datetime.fromisoformat(r["recorded"]) for r in chunk)
    return records


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
            try:
                n, since = poll_once(engine, since)
                total_rows += n
            except Exception:
                log.exception("Traffic poll failed")
                n = -1
            n_polls += 1
            log.info("Poll #%d: intersection_traffic=%d (watermark=%s)", n_polls, n, since)

            if args.once:
                break

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Stopped after %d polls. Total rows written: %d", n_polls, total_rows)


if __name__ == "__main__":
    main()

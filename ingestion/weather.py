"""Backfill and refresh daily Brisbane weather via Open-Meteo (free, no auth).

Unlike traffic, weather has real, immediately-available history: the archive
endpoint serves daily observations back to 1940, so we don't need to poll
forward from today — we can backfill the entire window our other data
already covers in one run. The forecast endpoint adds the last ~92 days
through today (the archive endpoint typically lags a day or two behind
real time), so combining both gets us right up to "today" on a fresh run.

Idempotent: upserts by date, so re-running (e.g. daily via cron/LaunchAgent,
or manually) just extends coverage without duplicating rows.

Usage:
    python -m ingestion.weather                        # backfill from 2026-01-01 to today
    python -m ingestion.weather --start 2026-09-01      # custom start date
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ingestion.config import (
    BRISBANE_LAT,
    BRISBANE_LON,
    DATABASE_URL,
    WEATHER_ARCHIVE_API_URL,
    WEATHER_FORECAST_API_URL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 30
DEFAULT_START = date(2026, 1, 1)

_DAILY_VARS = "precipitation_sum,temperature_2m_min,temperature_2m_max,wind_speed_10m_max"


def _parse_daily_response(daily: dict) -> pd.DataFrame:
    if not daily.get("time"):
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "date": daily["time"],
            "rainfall_mm": daily["precipitation_sum"],
            "temp_min_c": daily["temperature_2m_min"],
            "temp_max_c": daily["temperature_2m_max"],
            "wind_kph": daily["wind_speed_10m_max"],
        }
    )


def _fetch_daily(base_url: str, start: date, end: date) -> pd.DataFrame:
    if start > end:
        return pd.DataFrame()
    params = {
        "latitude": BRISBANE_LAT,
        "longitude": BRISBANE_LON,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": _DAILY_VARS,
        "timezone": "Australia/Brisbane",
    }
    resp = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return _parse_daily_response(resp.json().get("daily", {}))


def fetch_weather(start: date, end: date) -> pd.DataFrame:
    """Archive endpoint for everything but the last few days (it lags real
    time), forecast endpoint (which also carries recent history) for the
    tail end. Falls back cleanly if either returns nothing for its slice.
    """
    archive_end = min(end, date.today() - timedelta(days=3))
    archive_df = _fetch_daily(WEATHER_ARCHIVE_API_URL, start, archive_end)

    recent_start = max(start, archive_end + timedelta(days=1))
    recent_df = _fetch_daily(WEATHER_FORECAST_API_URL, recent_start, end)

    df = pd.concat([archive_df, recent_df], ignore_index=True)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.drop_duplicates(subset="date").sort_values("date")


def upsert_weather(engine: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    with engine.begin() as conn:
        for row in df.itertuples(index=False):
            conn.execute(
                text(
                    """
                    INSERT INTO raw.weather_daily (date, rainfall_mm, temp_min_c, temp_max_c, wind_kph)
                    VALUES (:date, :rainfall_mm, :temp_min_c, :temp_max_c, :wind_kph)
                    ON CONFLICT (date) DO UPDATE SET
                        rainfall_mm = EXCLUDED.rainfall_mm,
                        temp_min_c = EXCLUDED.temp_min_c,
                        temp_max_c = EXCLUDED.temp_max_c,
                        wind_kph = EXCLUDED.wind_kph
                    """
                ),
                {
                    "date": row.date,
                    "rainfall_mm": row.rainfall_mm,
                    "temp_min_c": row.temp_min_c,
                    "temp_max_c": row.temp_max_c,
                    "wind_kph": row.wind_kph,
                },
            )
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD (default: 2026-01-01)")
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else DEFAULT_START
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()

    engine = create_engine(DATABASE_URL)
    log.info("Fetching Brisbane daily weather %s to %s", start, end)
    df = fetch_weather(start, end)
    n = upsert_weather(engine, df)
    log.info("Upserted %d daily weather rows (%s to %s)", n, start, end)


if __name__ == "__main__":
    main()

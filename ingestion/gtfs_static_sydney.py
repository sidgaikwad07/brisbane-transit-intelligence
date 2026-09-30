"""Load Sydney's static GTFS feed (Transport for NSW) into raw_syd, for the
cross-city comparison — see docs/city_comparison.md once it exists, and
ROADMAP.md for what's blocked pending a GTFS-RT API key.

Freely downloadable, no API key (unlike TfNSW's real-time feeds, which do
require one this project doesn't have). Skips `shapes` — Sydney's is ~1GB
uncompressed for route-line geometry this comparison doesn't need; the
numeric comparison (stops, routes, scheduled trips, frequency) only needs
agency/routes/stops/calendar/calendar_dates/trips/stop_times.

Run scripts/setup_city_schema.py raw_syd first.

Usage:
    python -m ingestion.gtfs_static_sydney
"""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL, RAW_DATA_DIR, SYDNEY_GTFS_STATIC_URL
from ingestion.gtfs_static import download_and_extract, load_table, log, populate_stop_geometry

SCHEMA = "raw_syd"
EXTRACT_DIR = Path(RAW_DATA_DIR) / "gtfs_static_sydney"


def main() -> None:
    start = time.time()
    extract_dir = download_and_extract(feed_url=SYDNEY_GTFS_STATIC_URL, extract_dir=EXTRACT_DIR)
    engine = create_engine(DATABASE_URL)

    for table in ["agency", "routes", "stops", "calendar", "calendar_dates", "trips"]:
        load_table(engine, extract_dir, table, schema=SCHEMA)
    load_table(engine, extract_dir, "stop_times", chunksize=200_000, schema=SCHEMA)

    populate_stop_geometry(engine, schema=SCHEMA)
    log.info("Sydney GTFS static load complete in %.1fs", time.time() - start)


if __name__ == "__main__":
    main()

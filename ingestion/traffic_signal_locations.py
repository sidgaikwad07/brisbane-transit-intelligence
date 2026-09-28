"""One-time load of BCC's traffic signal controller (tsc) site locations.

This is the missing link for a spatial join: raw.intersection_traffic (the
rolling congestion feed) identifies each reading by `tsc` but carries no
lat/lon of its own. This dataset is the lookup table — static reference
data (signal locations don't move), so unlike bcc_traffic.py this is a
single pull, not a continuous poller. Safe to re-run; upserts by tsc.

Usage:
    python -m ingestion.traffic_signal_locations
"""

from __future__ import annotations

import logging

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ingestion.config import BCC_SIGNAL_LOCATIONS_API_URL, DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 20
PAGE_SIZE = 100


def fetch_all() -> list[dict]:
    records: list[dict] = []
    offset = 0
    while True:
        resp = requests.get(
            BCC_SIGNAL_LOCATIONS_API_URL,
            params={"limit": PAGE_SIZE, "offset": offset},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        page = resp.json().get("results", [])
        if not page:
            break
        records.extend(page)
        offset += PAGE_SIZE
        if len(page) < PAGE_SIZE:
            break
    return records


def parse_records(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        point = r.get("geo_point_2d") or {}
        rows.append(
            {
                "tsc": r.get("tsc"),
                "subsystem": r.get("subsystem"),
                "areanum": r.get("areanum"),
                "lat": point.get("lat"),
                "lon": point.get("lon"),
            }
        )
    df = pd.DataFrame(rows)
    return df.dropna(subset=["tsc", "lat", "lon"])


def upsert(engine: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    with engine.begin() as conn:
        for row in df.itertuples(index=False):
            conn.execute(
                text(
                    """
                    INSERT INTO raw.traffic_signal_locations (tsc, subsystem, areanum, lat, lon, geom)
                    VALUES (:tsc, :subsystem, :areanum, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                    ON CONFLICT (tsc) DO UPDATE SET
                        subsystem = EXCLUDED.subsystem,
                        areanum = EXCLUDED.areanum,
                        lat = EXCLUDED.lat,
                        lon = EXCLUDED.lon,
                        geom = EXCLUDED.geom
                    """
                ),
                {
                    "tsc": row.tsc,
                    "subsystem": row.subsystem,
                    "areanum": row.areanum,
                    "lat": row.lat,
                    "lon": row.lon,
                },
            )
    return len(df)


def main() -> None:
    engine = create_engine(DATABASE_URL)
    records = fetch_all()
    log.info("Fetched %d signal locations", len(records))
    df = parse_records(records)
    n = upsert(engine, df)
    log.info("Upserted %d signal locations into raw.traffic_signal_locations", n)


if __name__ == "__main__":
    main()

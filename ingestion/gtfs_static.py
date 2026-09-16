"""Download the SEQ GTFS static feed and load it into Postgres.

Usage:
    python -m ingestion.gtfs_static
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from ingestion.config import DATABASE_URL, GTFS_STATIC_URL, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

EXTRACT_DIR = Path(RAW_DATA_DIR) / "gtfs_static"

# Each GTFS file maps to a raw.<table> with these exact column names kept.
# stop_times and shapes are large, so they're loaded in chunks.
TABLE_COLUMNS: dict[str, list[str]] = {
    "agency": ["agency_id", "agency_name", "agency_url", "agency_timezone", "agency_lang", "agency_phone"],
    "routes": ["route_id", "agency_id", "route_short_name", "route_long_name", "route_desc", "route_type", "route_url", "route_color", "route_text_color"],
    "stops": ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "zone_id", "stop_url", "location_type", "parent_station", "wheelchair_boarding", "platform_code"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
    "calendar_dates": ["service_id", "date", "exception_type"],
    "trips": ["route_id", "service_id", "trip_id", "trip_headsign", "trip_short_name", "direction_id", "block_id", "shape_id", "wheelchair_accessible"],
    "stop_times": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "stop_headsign", "pickup_type", "drop_off_type", "shape_dist_traveled"],
    "shapes": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"],
}

DATE_COLS = {"calendar": ["start_date", "end_date"], "calendar_dates": ["date"]}
BOOL_COLS = {"calendar": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}


def download_and_extract() -> Path:
    log.info("Downloading GTFS static feed from %s", GTFS_STATIC_URL)
    resp = requests.get(GTFS_STATIC_URL, timeout=60)
    resp.raise_for_status()
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(EXTRACT_DIR)
    log.info("Extracted GTFS feed to %s", EXTRACT_DIR)
    return EXTRACT_DIR


def _coerce(df: pd.DataFrame, table: str) -> pd.DataFrame:
    for col in DATE_COLS.get(table, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce").dt.date
    for col in BOOL_COLS.get(table, []):
        if col in df.columns:
            df[col] = df[col].astype("Int64") == 1
    if table == "agency":
        # Single-agency GTFS feeds are allowed to omit agency_id per spec,
        # but our schema uses it as a primary key — Translink's feed omits it.
        if "agency_id" not in df.columns:
            df["agency_id"] = "translink"
        df["agency_id"] = df["agency_id"].fillna("translink")
    if table == "routes" and "agency_id" in df.columns:
        df["agency_id"] = df["agency_id"].fillna("translink")
    return df


def load_table(engine, extract_dir: Path, table: str, chunksize: int | None = None) -> int:
    path = extract_dir / f"{table}.txt"
    if not path.exists():
        log.warning("%s.txt not present in feed, skipping", table)
        return 0

    columns = TABLE_COLUMNS[table]
    total_rows = 0
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE raw.{table} RESTART IDENTITY CASCADE"))

    reader = pd.read_csv(path, dtype=str, chunksize=chunksize) if chunksize else [pd.read_csv(path, dtype=str)]
    for chunk in reader:
        chunk = chunk[[c for c in columns if c in chunk.columns]]
        chunk = _coerce(chunk, table)
        chunk.to_sql(table, engine, schema="raw", if_exists="append", index=False, method="multi", chunksize=5000)
        total_rows += len(chunk)

    log.info("Loaded %s rows into raw.%s", total_rows, table)
    return total_rows


def populate_stop_geometry(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE raw.stops SET geom = ST_SetSRID(ST_MakePoint(stop_lon, stop_lat), 4326) "
                "WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL"
            )
        )
    log.info("Populated stop geometry")


def main() -> None:
    start = time.time()
    extract_dir = download_and_extract()
    engine = create_engine(DATABASE_URL)

    for table in ["agency", "routes", "stops", "calendar", "calendar_dates", "trips"]:
        load_table(engine, extract_dir, table)

    load_table(engine, extract_dir, "stop_times", chunksize=200_000)
    load_table(engine, extract_dir, "shapes", chunksize=200_000)

    populate_stop_geometry(engine)

    log.info("GTFS static load complete in %.1fs", time.time() - start)


if __name__ == "__main__":
    main()

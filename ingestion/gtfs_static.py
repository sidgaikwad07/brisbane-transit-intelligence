"""Download a GTFS static feed and load it into Postgres.

Brisbane-specific by default (SEQ feed -> raw schema); every function takes
an explicit feed_url/schema/extract_dir so ingestion/gtfs_static_sydney.py
and ingestion/gtfs_static_melbourne.py can reuse this same loader against
their own feed and their own schema (raw_syd / raw_mel — see
scripts/setup_city_schema.py) without duplicating the parsing logic.

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
# Primary-key column per table, where one exists as a single column — used
# to de-duplicate when appending a second/third sub-feed on top of an
# already-loaded one (see gtfs_static_melbourne.py, whose per-mode
# sub-feeds turned out to share some stop_ids across modes at real physical
# interchanges — not every ID collision there is a bug to namespace away).
PK_COLUMNS = {"agency": "agency_id", "routes": "route_id", "stops": "stop_id", "trips": "trip_id"}


def download_and_extract(feed_url: str = GTFS_STATIC_URL, extract_dir: Path = EXTRACT_DIR) -> Path:
    log.info("Downloading GTFS static feed from %s", feed_url)
    resp = requests.get(feed_url, timeout=120)
    resp.raise_for_status()
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(extract_dir)
    log.info("Extracted GTFS feed to %s", extract_dir)
    return extract_dir


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


def load_table(
    engine, extract_dir: Path, table: str, chunksize: int | None = None, schema: str = "raw", truncate: bool = True
) -> int:
    path = extract_dir / f"{table}.txt"
    if not path.exists():
        log.warning("%s.txt not present in feed, skipping", table)
        return 0

    columns = TABLE_COLUMNS[table]
    total_rows = 0
    if truncate:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY CASCADE"))

    pk_col = PK_COLUMNS.get(table)
    existing_pks: set[str] | None = None
    if not truncate and pk_col:
        with engine.connect() as conn:
            existing_pks = {row[0] for row in conn.execute(text(f"SELECT {pk_col} FROM {schema}.{table}"))}

    reader = pd.read_csv(path, dtype=str, chunksize=chunksize) if chunksize else [pd.read_csv(path, dtype=str)]
    for chunk in reader:
        chunk = chunk[[c for c in columns if c in chunk.columns]]
        chunk = _coerce(chunk, table)
        if existing_pks is not None and pk_col in chunk.columns:
            before = len(chunk)
            chunk = chunk[~chunk[pk_col].isin(existing_pks)]
            skipped = before - len(chunk)
            if skipped:
                log.info("Skipped %d %s rows already present (shared %s across sub-feeds)", skipped, table, pk_col)
            existing_pks.update(chunk[pk_col])
        chunk.to_sql(table, engine, schema=schema, if_exists="append", index=False, method="multi", chunksize=5000)
        total_rows += len(chunk)

    log.info("Loaded %s rows into %s.%s", total_rows, schema, table)
    return total_rows


def populate_stop_geometry(engine, schema: str = "raw") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {schema}.stops SET geom = ST_SetSRID(ST_MakePoint(stop_lon, stop_lat), 4326) "
                "WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL"
            )
        )
    log.info("Populated stop geometry for %s.stops", schema)


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

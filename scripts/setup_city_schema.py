"""Create a Postgres schema for a comparison city's static GTFS data,
cloning table structure from the existing `raw` (Brisbane) schema via
`LIKE ... INCLUDING ALL` rather than duplicating DDL — stays in sync
automatically if raw's own table definitions change.

Only the static-GTFS tables are cloned (agency, routes, stops, calendar,
calendar_dates, trips, stop_times, shapes) — Sydney/Melbourne's
GTFS-Realtime feeds require a free API key this project doesn't have yet
(see ROADMAP.md), so there's nothing real-time to store for them until
that's supplied.

Usage:
    python scripts/setup_city_schema.py raw_syd
    python scripts/setup_city_schema.py raw_mel
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from ingestion.config import DATABASE_URL

STATIC_TABLES = ["agency", "routes", "stops", "calendar", "calendar_dates", "trips", "stop_times", "shapes"]


def setup_schema(schema: str) -> None:
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        for table in STATIC_TABLES:
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {schema}.{table} (LIKE raw.{table} INCLUDING ALL)"))
    print(f"Schema {schema} ready with tables: {', '.join(STATIC_TABLES)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/setup_city_schema.py <schema_name>", file=sys.stderr)
        sys.exit(1)
    setup_schema(sys.argv[1])

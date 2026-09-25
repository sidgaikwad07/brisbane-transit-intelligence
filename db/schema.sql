-- Brisbane Transit Intelligence — raw layer schema
-- Mirrors the GTFS static spec (https://gtfs.org/schedule/reference/) plus
-- tables for polled GTFS-Realtime data (populated starting Week 2).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS raw;

-- ── GTFS static ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw.agency (
    agency_id       TEXT PRIMARY KEY,
    agency_name     TEXT NOT NULL,
    agency_url      TEXT,
    agency_timezone TEXT,
    agency_lang     TEXT,
    agency_phone    TEXT
);

CREATE TABLE IF NOT EXISTS raw.routes (
    route_id         TEXT PRIMARY KEY,
    agency_id        TEXT,
    route_short_name TEXT,
    route_long_name  TEXT,
    route_desc       TEXT,
    route_type       INTEGER,
    route_url        TEXT,
    route_color      TEXT,
    route_text_color TEXT
);

CREATE TABLE IF NOT EXISTS raw.stops (
    stop_id            TEXT PRIMARY KEY,
    stop_code          TEXT,
    stop_name          TEXT,
    stop_desc          TEXT,
    stop_lat           DOUBLE PRECISION,
    stop_lon           DOUBLE PRECISION,
    zone_id            TEXT,
    stop_url           TEXT,
    location_type      INTEGER,
    parent_station     TEXT,
    wheelchair_boarding INTEGER,
    platform_code      TEXT,
    geom               GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_stops_geom ON raw.stops USING GIST (geom);

CREATE TABLE IF NOT EXISTS raw.calendar (
    service_id TEXT PRIMARY KEY,
    monday     BOOLEAN,
    tuesday    BOOLEAN,
    wednesday  BOOLEAN,
    thursday   BOOLEAN,
    friday     BOOLEAN,
    saturday   BOOLEAN,
    sunday     BOOLEAN,
    start_date DATE,
    end_date   DATE
);

CREATE TABLE IF NOT EXISTS raw.calendar_dates (
    service_id     TEXT,
    date           DATE,
    exception_type INTEGER
);

CREATE TABLE IF NOT EXISTS raw.trips (
    route_id              TEXT,
    service_id             TEXT,
    trip_id                 TEXT PRIMARY KEY,
    trip_headsign           TEXT,
    trip_short_name         TEXT,
    direction_id            INTEGER,
    block_id                TEXT,
    shape_id                TEXT,
    wheelchair_accessible   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trips_route ON raw.trips (route_id);
CREATE INDEX IF NOT EXISTS idx_trips_service ON raw.trips (service_id);

CREATE TABLE IF NOT EXISTS raw.stop_times (
    trip_id             TEXT,
    arrival_time        TEXT,   -- GTFS allows >24:00:00, so kept as text, not TIME
    departure_time      TEXT,
    stop_id              TEXT,
    stop_sequence        INTEGER,
    stop_headsign         TEXT,
    pickup_type            INTEGER,
    drop_off_type          INTEGER,
    shape_dist_traveled    DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON raw.stop_times (trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON raw.stop_times (stop_id);

CREATE TABLE IF NOT EXISTS raw.shapes (
    shape_id             TEXT,
    shape_pt_lat          DOUBLE PRECISION,
    shape_pt_lon          DOUBLE PRECISION,
    shape_pt_sequence     INTEGER,
    shape_dist_traveled   DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_shapes_id ON raw.shapes (shape_id);

-- ── GTFS-Realtime (polled) ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw.vehicle_positions (
    id               BIGSERIAL PRIMARY KEY,
    polled_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    vehicle_id       TEXT,
    trip_id          TEXT,
    route_id         TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    bearing          DOUBLE PRECISION,
    speed            DOUBLE PRECISION,
    current_stop_id  TEXT,
    vehicle_timestamp TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_vp_trip ON raw.vehicle_positions (trip_id, polled_at);
CREATE INDEX IF NOT EXISTS idx_vp_route ON raw.vehicle_positions (route_id, polled_at);

CREATE TABLE IF NOT EXISTS raw.trip_updates (
    id                  BIGSERIAL PRIMARY KEY,
    polled_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    trip_id             TEXT,
    route_id            TEXT,
    stop_id             TEXT,
    stop_sequence       INTEGER,
    arrival_delay_sec   INTEGER,
    departure_delay_sec INTEGER,
    scheduled_arrival   TIMESTAMPTZ,
    predicted_arrival   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tu_trip ON raw.trip_updates (trip_id, polled_at);
CREATE INDEX IF NOT EXISTS idx_tu_route ON raw.trip_updates (route_id, polled_at);

CREATE TABLE IF NOT EXISTS raw.service_alerts (
    id           BIGSERIAL PRIMARY KEY,
    polled_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_id     TEXT,
    route_id     TEXT,
    stop_id      TEXT,
    cause        TEXT,
    effect       TEXT,
    header_text  TEXT,
    description  TEXT
);

-- ── External data (Week 3) ──────────────────────────────────────────────

-- BCC/SCATS intersection traffic signal snapshots. The API is a rolling
-- ~5-minute window (no historical backfill), so this table is only ever
-- populated by continuous polling, same as raw.gtfs_rt_trip_updates.
-- ds/mf/rf are repeated per approach lane (1-4): degree of saturation (%),
-- measured vehicle flow, and SCATS-reconstituted (estimated) flow.
CREATE TABLE IF NOT EXISTS raw.intersection_traffic (
    id             BIGSERIAL PRIMARY KEY,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    dbid           TEXT,
    recorded_at    TIMESTAMPTZ,
    tsc            TEXT,       -- traffic signal controller site id (the intersection)
    ss             TEXT,       -- subsystem/region grouping
    lane           TEXT,       -- approach/link id, e.g. "SA-411"
    cycle_time_sec INTEGER,
    ds1 DOUBLE PRECISION, mf1 DOUBLE PRECISION, rf1 DOUBLE PRECISION,
    ds2 DOUBLE PRECISION, mf2 DOUBLE PRECISION, rf2 DOUBLE PRECISION,
    ds3 DOUBLE PRECISION, mf3 DOUBLE PRECISION, rf3 DOUBLE PRECISION,
    ds4 DOUBLE PRECISION, mf4 DOUBLE PRECISION, rf4 DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_intersection_traffic_recorded_at
    ON raw.intersection_traffic (recorded_at);
CREATE INDEX IF NOT EXISTS idx_intersection_traffic_tsc
    ON raw.intersection_traffic (tsc);

CREATE TABLE IF NOT EXISTS raw.weather_daily (
    date         DATE PRIMARY KEY,
    rainfall_mm  DOUBLE PRECISION,
    temp_min_c   DOUBLE PRECISION,
    temp_max_c   DOUBLE PRECISION,
    wind_kph     DOUBLE PRECISION
);

-- Queensland Government open data: monthly aggregated smart-card (go card/
-- EMV) + paper-ticket origin-destination trip counts. One row per (operator,
-- month, route, direction, time_grouping, ticket_type, origin_stop,
-- destination_stop) with the trip count in `quantity` — already aggregated
-- by TransLink, not individual taps. https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards
CREATE TABLE IF NOT EXISTS raw.od_trips (
    id               BIGSERIAL PRIMARY KEY,
    operator         TEXT,
    month            DATE,
    route            TEXT,
    direction        TEXT,
    time_grouping    TEXT,
    ticket_type      TEXT,
    origin_stop      TEXT,
    destination_stop TEXT,
    quantity         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_od_trips_month ON raw.od_trips (month);
CREATE INDEX IF NOT EXISTS idx_od_trips_route ON raw.od_trips (route);
CREATE INDEX IF NOT EXISTS idx_od_trips_origin ON raw.od_trips (origin_stop);
CREATE INDEX IF NOT EXISTS idx_od_trips_dest ON raw.od_trips (destination_stop);

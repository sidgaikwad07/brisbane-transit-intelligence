# Brisbane Transit Intelligence

A data engineering + ML project that turns Brisbane's public transport open data
(GTFS static + GTFS-Realtime, Council traffic sensors, weather) into a working
pipeline that measures network reliability, predicts delays, and surfaces where
the network is under strain.

Built as a portfolio project — the emphasis is on a real, reproducible pipeline
over a large feature set: local Postgres/PostGIS, scheduled ingestion, dbt
transformations, a trained delay-prediction model, and a dashboard, all runnable
with `docker compose up`.

## Why this project

Brisbane's transit agency (Translink) and Brisbane City Council publish open,
unauthenticated data feeds — a static GTFS schedule, a live GTFS-Realtime feed
(vehicle positions + trip updates + service alerts), and live traffic sensor
data at signalised intersections. This project ingests all three, models them
together, and asks a concrete question:

> **Where and when does Brisbane's bus network become unreliable, and how much
> of that is explained by road congestion vs. schedule design?**

## Status

This is under active development. See [`ROADMAP.md`](ROADMAP.md) for the
build plan and current progress.

## Architecture

```text
                    ┌─────────────────────┐
                    │  Translink GTFS      │  static schedule (zip, daily)
                    │  (SEQ_GTFS.zip)      │
                    └──────────┬───────────┘
                               │
                    ┌─────────────────────┐
                    │  Translink GTFS-RT   │  vehicle positions, trip updates,
                    │  (protobuf, polled)  │  service alerts (polled every ~20s)
                    └──────────┬───────────┘
                               │
                    ┌─────────────────────┐
                    │  BCC Traffic API     │  intersection volume/occupancy
                    │  (Opendatasoft REST) │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  ingestion/*.py      │  Python, scheduled via cron/
                    │                      │  APScheduler
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  PostgreSQL+PostGIS  │  raw tables (docker compose)
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  dbt models          │  staging → marts
                    │  (dbt-core, local)   │  (delay, on-time %, headway)
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐        ┌─────────────────┐
        │ Delay prediction │        │ Streamlit        │
        │ model (XGBoost)  │        │ dashboard         │
        └─────────────────┘        └─────────────────┘
```

## Data sources (all public, no auth required)

| Source | Format | Update frequency | Link |
|---|---|---|---|
| SEQ GTFS static | ZIP of CSVs | Periodic (versioned) | `https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip` |
| GTFS-RT Trip Updates | Protobuf | ~20-30s | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/TripUpdates` |
| GTFS-RT Vehicle Positions | Protobuf | ~20-30s | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions` |
| GTFS-RT Service Alerts | Protobuf | On change | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/alerts` |
| BCC Intersection traffic volume | JSON (Opendatasoft) | Near real-time | `https://data.brisbane.qld.gov.au/explore/dataset/traffic-data-at-intersection/` |

## Getting started

```bash
cp .env.example .env
docker compose up -d          # starts Postgres+PostGIS
pip install -r requirements.txt
python -m ingestion.gtfs_static           # loads the static schedule
python -m ingestion.gtfs_realtime_poller  # polls live feeds (Ctrl+C to stop)
```

## Project layout

```text
ingestion/     Python scripts pulling GTFS static, GTFS-RT, and traffic data
db/            Raw Postgres schema (DDL)
dbt/           dbt-core project: staging + mart models
models/        ML: delay prediction, feature engineering
dashboard/     Streamlit app
tests/         Unit + data-quality tests
docs/          Architecture notes, findings write-ups
```

## License

Code: MIT. Data: subject to Translink and Brisbane City Council's open data
licenses (CC BY 4.0).

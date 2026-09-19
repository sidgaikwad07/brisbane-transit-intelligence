# dbt project — Week 2

Staging models (`models/staging/`) type-cast and lightly filter `raw.*`
(the GTFS static tables, plus the append-only realtime polls from
`ingestion/gtfs_realtime_poller.py`). Mart models (`models/marts/`) compute:

- `mart_stop_delay` — one row per (trip, stop) actually visited: the last
  prediction polled for that stop before the vehicle presumably passed it
- `mart_on_time_performance` — on-time/late/early % by route, our own
  measurement from polled data (not Translink's official stat)
- `mart_bunching_events` / `mart_bunching_by_route` — pairs of vehicles on
  the same route within 400m of each other in the same poll

## Running it

```bash
cd dbt
export $(grep -v '^#' ../.env | xargs)   # loads POSTGRES_* into the shell
DBT_PROFILES_DIR=. dbt run
```

`profiles.yml` reads connection details from the same `POSTGRES_*` env vars
as the rest of the project (`.env`), with `localhost`/`5433`/`transit`/
`transit` as fallback defaults — no separate dbt credentials to manage.

Needs `raw.trip_updates` / `raw.vehicle_positions` populated first — run
`python -m ingestion.gtfs_realtime_poller` (Ctrl+C to stop) for a while
before `dbt run`, then re-run `dbt run` any time to refresh the marts
against whatever's accumulated since.

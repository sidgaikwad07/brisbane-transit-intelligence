# dbt project (Week 2)

The staging models (`models/staging/`) type-cast and lightly filter the `raw.*` tables: the GTFS
static tables plus the append-only real-time polls from `ingestion/gtfs_realtime_poller.py`.
The mart models (`models/marts/`) compute:

- `mart_stop_delay`: one row per (trip, stop) actually visited, using the last prediction
  polled for that stop before the vehicle most likely passed it
- `mart_on_time_performance`: on-time, late and early percentages by route. This is my own
  measurement from the polled data, not Translink's official figure
- `mart_bunching_events` / `mart_bunching_by_route`: pairs of vehicles on the same route
  within 400m of each other in the same poll

## Running it

```bash
cd dbt
export $(grep -v '^#' ../.env | xargs)   # loads POSTGRES_* into the shell
DBT_PROFILES_DIR=. dbt run
```

`profiles.yml` reads its connection details from the same `POSTGRES_*` variables in `.env` as
the rest of the project, falling back to `localhost`/`5433`/`transit`/`transit`, so there are
no separate dbt credentials to manage.

`raw.trip_updates` and `raw.vehicle_positions` need data in them first. Run
`python -m ingestion.gtfs_realtime_poller` for a while (Ctrl+C to stop), then `dbt run`. After
that, re-run `dbt run` whenever you want the marts to include everything collected since.

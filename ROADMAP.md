# Roadmap

Scoped for a ~4 week build. Each week produces something runnable and demoable,
not just code — the goal is a working artifact at every checkpoint.

## Week 1 — Network foundation
- [x] Repo scaffold, Docker Compose (Postgres + PostGIS)
- [x] GTFS static ingestion (`ingestion/gtfs_static.py`) — download, parse, load
- [x] Raw schema: `agency, routes, stops, trips, stop_times, calendar, calendar_dates, shapes`
- [x] Network summary — route counts, stop coverage, weekday frequency by route/stop
- [x] **Demo artifact:** [`docs/week1_findings.md`](docs/week1_findings.md) + stop-frequency map — DONE

## Week 2 — Live operations
- [x] GTFS-Realtime poller (`ingestion/gtfs_realtime_poller.py`) — Trip Updates + Vehicle Positions + Service Alerts, protobuf decode, append to Postgres
- [x] dbt project scaffolded (`dbt/`) — staging models for routes/trips/trip_updates/vehicle_positions
- [x] Delay calculation (`mart_stop_delay`, `mart_on_time_performance` — scheduled vs. last-polled predicted arrival)
- [x] Bunching detection (`mart_bunching_events`, `mart_bunching_by_route` — vehicles on the same route within 400m in the same poll)
- [x] **Demo artifact:** [`docs/week2_findings.md`](docs/week2_findings.md) — on-time performance by route + bunching, from a ~26h real collection window (285K stop visits) — DONE

## Demand intelligence (added — not in the original 4-week plan)
- [x] Queensland Government open-data discovery: monthly aggregated go card/EMV/paper-ticket
  origin-destination trip counts exist and are public (CC BY 4.0) — this was assumed unavailable
  in the original scoping (see "out of scope" below, now outdated on this point)
- [x] `ingestion/od_trips.py` — loads N most recent months from data.qld.gov.au
- [x] dbt marts: `mart_od_demand_by_route`, `mart_od_demand_by_time`, `mart_od_top_pairs`
- [x] Real ridership joined against GTFS scheduled trips → riders-per-scheduled-trip by route
- [x] **Demo artifact:** [`docs/demand_intelligence_findings.md`](docs/demand_intelligence_findings.md) — DONE
- [x] First capacity-gap synthesis: [`docs/priority_routes_findings.md`](docs/priority_routes_findings.md)
  (`notebooks/priority_routes.py`) — crosses real demand against measured reliability citywide;
  surfaced SMBI ferry (100th percentile demand, 2nd percentile reliability) as the single
  highest-priority route in the network, and independently confirmed the Manly/Lota/Cleveland
  case study's routes 220/227 in the citywide top 15
- [ ] Longer-term: route planning via RAPTOR (+ live-delay layering), scenario comparison —
  scoped as a separate, larger initiative once this foundation is proven; not committed to yet

## Week 3 — Explaining delay
- [x] BCC intersection traffic ingestion (`ingestion/bcc_traffic.py`) — the API is a rolling
  ~5-minute window with no historical backfill (verified), so it's a continuous poller like
  GTFS-RT, not a one-time pull; installed as a LaunchAgent (`scripts/install_traffic_poller_service.sh`)
- [x] Weather ingestion (`ingestion/weather.py`, Open-Meteo archive + forecast endpoints) — unlike
  traffic, has real history, so this backfills the whole delay-collection window in one run
- [ ] Join traffic volume to nearby delayed trips (spatial join via PostGIS)
- [ ] Feature engineering: route, time-of-day, day-of-week, congestion, weather
- [ ] Train XGBoost delay-prediction model, evaluate (MAE, and P(delay > 5 min))
- **Demo artifact:** model card — features, performance, top delay drivers per route

## Week 4 — Dashboard + polish
- [x] Streamlit dashboard (`dashboard/app.py`, pulled forward) — network health, live delay view,
  worst routes/bunching, demand-vs-reliability, traffic & weather. Model predictions tab pending
  the delay-prediction model (still not built — see Week 3 above)
- [ ] README pass, architecture diagram finalized
- [ ] Screen-recorded demo (GIF/video) for LinkedIn
- [ ] Write-up: what the data showed, one or two concrete, specific findings about Brisbane's network

## Explicitly out of scope (for this version)
Airflow, dbt Cloud, cloud data warehouse, live public hosting, demand
*forecasting* (predicting future demand — distinct from the real historical
ridership now in scope via the OD dataset above), accessibility index,
scenario simulator, and anything requiring non-public data (fleet size,
vehicle capacity, per-service operating cost, driver rostering — needed for
real optimization/simulation, not available as open data). These are
natural follow-ups if the project gets traction, not requirements for v1.

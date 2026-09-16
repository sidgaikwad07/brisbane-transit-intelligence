# Roadmap

Scoped for a ~4 week build. Each week produces something runnable and demoable,
not just code — the goal is a working artifact at every checkpoint.

## Week 1 — Network foundation
- [x] Repo scaffold, Docker Compose (Postgres + PostGIS)
- [ ] GTFS static ingestion (`ingestion/gtfs_static.py`) — download, parse, load
- [ ] Raw schema: `agency, routes, stops, trips, stop_times, calendar, calendar_dates, shapes`
- [ ] Notebook: network summary — route counts, stop coverage by suburb, frequency by route
- **Demo artifact:** a map of stop density / service frequency across Brisbane suburbs

## Week 2 — Live operations
- [ ] GTFS-Realtime poller (`ingestion/gtfs_realtime_poller.py`) — Trip Updates + Vehicle Positions, protobuf decode, append to Postgres
- [ ] dbt staging models for realtime tables
- [ ] Delay + headway calculation (scheduled vs actual)
- [ ] Detect bunching (two vehicles on the same route within N minutes of each other)
- **Demo artifact:** on-time performance by route, computed from real polled data (not the official Translink stat — your own measurement)

## Week 3 — Explaining delay
- [ ] BCC intersection traffic ingestion
- [ ] Join traffic volume to nearby delayed trips (spatial join via PostGIS)
- [ ] Weather ingestion (BOM or Open-Meteo, simple daily pull)
- [ ] Feature engineering: route, time-of-day, day-of-week, congestion, weather
- [ ] Train XGBoost delay-prediction model, evaluate (MAE, and P(delay > 5 min))
- **Demo artifact:** model card — features, performance, top delay drivers per route

## Week 4 — Dashboard + polish
- [ ] Streamlit dashboard: network health, live-ish delay view, worst routes/stops, model predictions
- [ ] README pass, architecture diagram finalized
- [ ] Screen-recorded demo (GIF/video) for LinkedIn
- [ ] Write-up: what the data showed, one or two concrete, specific findings about Brisbane's network

## Explicitly out of scope (for this version)
Airflow, dbt Cloud, cloud data warehouse, live public hosting, demand
forecasting, accessibility index, scenario simulator. These are natural
follow-ups if the project gets traction, not requirements for v1.

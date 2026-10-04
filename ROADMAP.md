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
- [ ] **Known gap, found 2026-09-27:** the OD dataset identifies heavy rail and the Gold Coast light
  rail by literal route codes ("Rail", "GCLR"), not a GTFS route_short_name. Every existing
  route-level join (`scheduled_weekday_trips_by_route` in `demand_intelligence.py`, used by
  `priority_routes.py` and downstream by `hero_dashboard.py`/`transit_infographic.py`) silently
  drops both — meaning "top priority route" rankings and "busiest routes" charts have a blind spot
  for two entire modes (~36% of all real ridership). Worked around locally in the dashboard's
  Ridership trends tab (explicit reclassification); not yet fixed at the source
  (`stg_od_trips`/`mart_od_demand_by_route`), which would require re-deriving those marts and
  re-checking every finding that depends on them.

## Week 3 — Explaining delay
- [x] BCC intersection traffic ingestion (`ingestion/bcc_traffic.py`) — the API is a rolling
  ~5-minute window with no historical backfill (verified), so it's a continuous poller like
  GTFS-RT, not a one-time pull; installed as a LaunchAgent (`scripts/install_traffic_poller_service.sh`)
- [x] Weather ingestion (`ingestion/weather.py`, Open-Meteo archive + forecast endpoints) — unlike
  traffic, has real history, so this backfills the whole delay-collection window in one run
- [x] Signal-location reference data (`ingestion/traffic_signal_locations.py`) — BCC's rolling
  traffic feed carries no lat/lon of its own (only a signal-controller id), discovered while
  scoping this step; this one-time pull of BCC's separate "Traffic Management — Signal locations"
  dataset (1,020 sites) is what makes a spatial join possible at all
- [x] Join traffic volume to nearby delayed trips (`models/build_features.py`) — PostGIS
  `ST_DWithin` (400m) from each stop to nearby signals, congestion averaged into 30-minute time
  buckets (the feed updates in irregular batches, not continuously); joined against daily weather
  and an hourly count of active system-wide disruption alerts
- [x] Feature engineering: mode, route, hour, day-of-week, local traffic saturation, weather,
  disruption-alert count — all in `models/build_features.py`
- [x] Train XGBoost delay-prediction model, evaluate (`models/train_delay_model.py`) — MAE
  (regression) and accuracy/precision/recall/F1/ROC-AUC (classifying >5min late), each against a
  naive baseline. **Time-split result is a real negative finding, not a bug:** the model currently
  loses to its own baseline, because the ~3.5-day collection window contains one clear reliability
  regime shift (a strike-caused disruption on 25-26 Sep, much better on 27-28 Sep) that a few days
  of data can't teach a model to generalize across — confirmed via a diagnostic random-split run,
  where the same features clearly beat baseline. More days of data (spanning multiple
  disruption/no-disruption cycles) is the actual fix, not a modeling trick.
- [x] **Demo artifact:** [`docs/delay_model_card.md`](docs/delay_model_card.md) — features,
  time-split vs. random-split performance, feature importance chart, honest caveats

## Week 4 — Dashboard + polish
- [x] Streamlit dashboard (`dashboard/app.py`, pulled forward) — network health, live delay view,
  worst routes/bunching, demand-vs-reliability, traffic & weather. Model predictions tab pending
  the delay-prediction model (still not built — see Week 3 above)
- [x] **Automation (added 2026-10-04):** `scripts/health_check.py` (every 15 min — macOS
  notification when any live table stops receiving rows or the DB is down) and
  `scripts/weekly_refresh.py` (Mondays 06:00 — reload all static data, regenerate everything in a
  separate worktree, open a PR for review); both installed via `scripts/install_automation.sh`.
  `refresh_all.py` now also covers the weekend-gap, city-comparison and delay-model scripts.
  **Found while building it:** the BCC traffic poller had been hitting the portal's 5,000
  calls/day anonymous limit (~150 paged calls per poll) and was locked out for most of every
  day — only 2-14 hours of traffic data per day since collection began, mostly missing the
  morning peak. Fixed with a single bulk-export call per poll (~720/day) and sleeping until the
  quota resets if it's ever hit. The Week 3 delay model was trained on that patchy data, so its
  traffic-feature results need re-checking once a full-day window exists.
- [ ] README pass, architecture diagram finalized
- [ ] Screen-recorded demo (GIF/video) for LinkedIn
- [ ] Write-up: what the data showed, one or two concrete, specific findings about Brisbane's network

## City comparison (added 2026-09-29) — Brisbane vs. Sydney vs. Melbourne
User asked for a cross-city comparison so Brisbane's findings could be benchmarked against peers
and turned into recommendations. Explicitly scoped as the "full live pipeline" option (not a
quick published-stats comparison) — a multi-phase effort, tracked here.

- [x] **Phase 1 — static network comparison.** Both cities' static GTFS are freely downloadable,
  no API key: `ingestion/gtfs_static_sydney.py` (Transport for NSW, a single flat feed, ~1.4GB
  uncompressed) and `ingestion/gtfs_static_melbourne.py` (Transport Victoria — structurally a zip
  of separate per-mode sub-feeds; scoped to metro train/tram/bus, excluding V/Line
  regional/interstate rail, coach, and SkyBus). Loaded into their own schemas (`raw_syd`,
  `raw_mel`, cloned from `raw`'s table structure via `scripts/setup_city_schema.py`) so Brisbane's
  own tables/marts/dashboard are completely untouched. `notebooks/city_comparison.py` computes
  network scale (stops, routes, scheduled weekday trips, mode mix) from each city's own schedule,
  using the same representative-weekday methodology as every other Brisbane finding — see
  `docs/city_comparison.md`. Real headline numbers (weekday, general-public service only —
  school buses and regional/interstate excluded, see the doc's caveats): Brisbane 13,094 stops /
  494 routes / 20,853 trips; Sydney 170,908 stops / 1,288 routes / 44,860 trips; Melbourne 27,057
  stops / 655 routes / 31,737 trips. Two real data-quality findings surfaced building this, both
  documented rather than silently patched: Sydney's "Greater Sydney" feed is actually
  **statewide** (689 agencies, 45% of stops outside a generous Sydney-metro bounding box) and its
  original route count was 88% dedicated school-bus service (route_type 712) that had to be
  identified and excluded to make the comparison meaningful at all.
- [x] **Phase 1b — like-for-like service quality (added 2026-10-01).** All three feeds clipped to
  their ABS Greater Capital City boundaries and weighed against where people live (ABS 2025
  population grid, `ingestion/abs_reference.py`), via `notebooks/city_service_quality.py` — see
  `docs/city_service_quality.md`. Headline: 70% of Greater Brisbane residents live within 400m of a
  stop, close to Melbourne's 73%, but only 22% near a stop with 15-minute-or-better all-day service
  (Melbourne 32%, Sydney 41%); Brisbane last at every frequency threshold tested. Also found and
  fixed a Phase 1 bug: Sydney's representative weekday had no Sydney Trains service, because Sydney
  Trains publishes only ~1 month ahead (`service_calendar.complete_schedule_end`).
- [ ] **Phase 2 — live reliability/headway comparison, BLOCKED on API keys.** Sydney
  (opendata.transport.nsw.gov.au) and Melbourne (opendata.transport.vic.gov.au) both require a
  free, self-registered API key for their GTFS-Realtime feeds — registration this project can't
  complete on its own (needs a real person's sign-up). **Action needed: register for both and add
  the keys to `.env`** (`TFNSW_API_KEY`, `PTV_API_KEY` — not yet added to `ingestion/config.py`,
  add alongside the keys). Once supplied, Phase 2 is: pollers for both cities' GTFS-RT Trip
  Updates (mirroring `ingestion/gtfs_realtime_poller.py`), a multi-week collection window (Brisbane
  itself needed ~10 days before its own OTP numbers were trustworthy — expect similarly for these),
  then a real on-time-performance / headway comparison across all three cities.
- [x] **Phase 3 — turn the comparison into recommendations (static part done 2026-10-02).**
  `docs/recommendations.md` section C (#12-16): frequent-service coverage target benchmarked to
  Melbourne/Sydney, three named growth corridors, evening standard, weekend approach, routine
  peer benchmarking. A live-reliability comparison would be added here if Phase 2 ever runs.

## Explicitly out of scope (for this version)
Airflow, dbt Cloud, cloud data warehouse, live public hosting, demand
*forecasting* (predicting future demand — distinct from the real historical
ridership now in scope via the OD dataset above), accessibility index,
scenario simulator, and anything requiring non-public data (fleet size,
vehicle capacity, per-service operating cost, driver rostering — needed for
real optimization/simulation, not available as open data). These are
natural follow-ups if the project gets traction, not requirements for v1.

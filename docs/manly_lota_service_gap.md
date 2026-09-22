# Case study: the Manly / Lota / Cleveland service gap

Raised as a specific question: a resident of the Manly/Lota/Cleveland corridor (bayside, ~13-26km east/southeast of the Brisbane CBD, on the Cleveland rail line) has two complaints — the bus route feels too long, and it's not frequent enough (sometimes over an hour between buses). This turns both into measurable claims: one from the scheduled GTFS timetable (headway, route geometry), and — new since the first version of this case study — one from **real ridership data**, not just the schedule.

## Method

Headway (average minutes between departures, estimated as each time-of-day window's length divided by how many scheduled departures fall in it — see note below on why not a raw gap average) at the corridor's **inbound, city-bound** rail platform (Manly station, platform 1 — Lota station matches closely, same line) and its busiest inbound bus stop (Manly Rd at Silky Oaks, routes toward the City/Fortitude Valley), split into five time-of-day windows, on three representative dates chosen the same way as the main network summary (`ingestion/service_calendar.py` — the date, among all dates of that weekday type in the feed, whose total scheduled-trip count is closest to the median):

- Weekday: **Thursday, 17 September 2026**
- Saturday: **Saturday, 17 October 2026**
- Sunday: **Sunday, 18 October 2026**

## Rail: Cleveland Line at Manly station (inbound)

| Time of day | Weekday | Saturday | Sunday |
|---|---|---|---|
| AM peak | every 14 min | every 30 min | every 30 min |
| Midday | every 30 min | every 30 min | every 30 min |
| PM peak | every 15 min | every 30 min | every 30 min |
| Evening | every 21 min | every 30 min | every 30 min |
| Night/early | every 69 min | every 60 min | every 160 min |

![Cleveland Line headway at Manly station, weekday vs Saturday vs Sunday](images/manly_lota_headway.png)

Weekday peak service is genuinely good — a train roughly every 15 minutes at AM and PM peak. But there is **no weekend peak at all**: Saturday runs a flat 30-minute service all day, including the hours when someone would be travelling to a Saturday shift or an early appointment. Sunday is a little better in the morning but still 30 minutes for most of the day.

## Bus: Manly Rd corridor (inbound toward the City)

| Time of day | Weekday | Saturday | Sunday |
|---|---|---|---|
| AM peak | every 13 min | every 45 min | every 90 min |
| Midday | every 21 min | every 20 min | every 30 min |
| PM peak | every 21 min | every 19 min | every 30 min |
| Evening | every 105 min | every 210 min | — |
| Night/early | every 240 min | every 480 min | — |

The bus corridor is the more dramatic gap: a bus roughly every 13-21 minutes across the weekday collapses to **every 90 minutes on Sunday mornings**, and to **almost nothing after about 7pm** — every 105 minutes on a weekday evening, once every 4-8 hours overnight, and no scheduled evening or night service at all on Sunday.

## Is the weekend/evening gap specific to Manly/Lota, or citywide?

Checked against every other Brisbane bus stop with comparable weekday importance (≥30 weekday trips — i.e. stops that matter enough to run frequent weekday service), the Manly Rd corridor's Sunday-morning service sits at the **51st percentile** — almost exactly the citywide median for stops like it.

That's a real finding worth taking to Council or Translink on its own: **the weekend/evening gap isn't a Manly/Lota-specific shortfall, it's a citywide pattern** — Brisbane's middle and outer suburbs broadly get a weekday-only frequent-service model. Manly/Lota is a clear, well-documented example of it, not an outlier. But it's not the whole story — see below.

## Real ridership: is demand actually elevated here?

Until now this case study relied entirely on the *schedule* — it could show how often a bus is timetabled, but not whether enough people are trying to use it to justify more. Queensland Government's origin-destination trip data (real go card/EMV touch-on+touch-off counts, see `docs/demand_intelligence_findings.md`) answers that directly: **riders per scheduled trip**, benchmarked against every other route citywide.

| Route | Avg weekday riders | Scheduled trips | Riders/trip | Percentile |
|---|---|---|---|---|
| 227 (Wynnum - City) | 1,397 | 36 | 38.8 | 95th |
| 220 (Wynnum - City Express) | 1,083 | 31 | 34.9 | 93rd |
| 251 (Ormiston - Brisbane City) | 206 | 8 | 25.7 | 76th |
| 221 (Wynnum - City Rocket) | 164 | 7 | 23.5 | 71st |
| 275 (Thornlands - Brisbane City via Finucane Rd) | 173 | 8 | 21.7 | 66th |
| 224 (Wynnum Loop Anti-Clockwise) | 178 | 12 | 14.8 | 50th |
| 223 (Wynnum Loop Clockwise) | 160 | 12 | 13.4 | 47th |
| 274 (Victoria Pt Jetty - Cleveland via Thornlands) | 222 | 25 | 8.9 | 29th |
| 254 (Capalaba - Wellington Point) | 303 | 40 | 7.6 | 22nd |
| 240 (Capalaba - Wynnum) | 151 | 23 | 6.6 | 17th |
| 255 (Cleveland - Birkdale) | 124 | 26 | 4.8 | 10th |

**This is the strongest evidence in this case study.** The two main routes serving Manly — **227** and **220** — sit at the 95th and 93rd percentile of demand pressure citywide, roughly **2.5x the network median** riders per scheduled trip. Unlike the weekend-headway finding above, this genuinely isn't a citywide-typical pattern — these two routes are carrying meaningfully more demand per trip than most of Brisbane's network, which is real, specific evidence that **frequency on these two routes specifically hasn't kept pace with how much they're actually used**.

## Is the route actually too long?

Route circuity (actual path length ÷ straight-line distance between the route's endpoints — 1.0 would be a perfectly straight line) checks whether "the bus route feels too long" reflects something unusual about this corridor, or how Brisbane buses are generally drawn:

| Route | Path length | Circuity (path ÷ straight-line) |
|---|---|---|
| 274 (Victoria Pt Jetty - Cleveland via Thornlands) | 19 km | 2.27x |
| 255 (Cleveland - Birkdale) | 14 km | 2.24x |
| 220 (Wynnum - City Express) | 29 km | 2.04x |
| 227 (Wynnum - City) | 22 km | 1.75x |
| 221 (Wynnum - City Rocket) | 27 km | 1.75x |
| 273 (Cleveland - Brisbane City via Redland Bay Rd) | 38 km | 1.62x |
| 240 (Capalaba - Wynnum) | 14 km | 1.59x |
| 254 (Capalaba - Wellington Point) | 9 km | 1.57x |
| 251 (Ormiston - Brisbane City) | 36 km | 1.57x |
| 275 (Thornlands - Brisbane City via Finucane Rd) | 37 km | 1.43x |

Citywide median circuity across 408 sampled bus routes is **1.79x** — Brisbane's bus network is generally quite circuitous (suburban coverage-oriented routing, not a corridor-specific issue). Routes 220 and 227 (the two busiest, above) sit close to or right at that citywide median, not in the unusually-long tail. The Cleveland-area routes (255, 274) run somewhat higher than typical, but not to an extreme degree. **The "route is too long" complaint is real in absolute terms (a 20-30km path for what could be a much shorter direct line) but isn't a Manly/Lota/Cleveland-specific design failure** — it's a symptom of how Brisbane's whole bus network prioritises coverage over directness, same conclusion shape as the weekend-headway finding above.

## What this actually recommends

Two different conclusions for two different complaints, and they point to different fixes:
- **Frequency on routes 220/227 specifically**: genuinely under-provisioned relative to demonstrated demand (top-5th-percentile ridership pressure, not a citywide-typical pattern) — a defensible, targeted case for adding weekday peak capacity on these two routes specifically, not a network-wide ask.
- **Weekend/evening frequency and route directness**: both are real, but both are citywide patterns, not something uniquely wrong with this corridor — the useful policy conversation is Brisbane's weekend-frequency and route-design standards in general, with Manly/Lota/Cleveland as a clear illustrative example, not a corridor that needs a one-off fix.

## Caveats

- This measures the **published timetable**, not actual on-the-ground reliability — GTFS static says nothing about delays, cancellations or overcrowding.
- The headway analysis targets one named rail platform and one named bus stop, not an official suburb boundary. The ridership and circuity sections use a wider, geographic (lat/lon bounding box) definition of the corridor's bus routes, deliberately not a text search — a plain "cleveland" name match pulls in unrelated Gold Coast routes that happen to share the word somewhere in a stop name.
- One representative date per day-type, not every date in the feed — chosen to avoid a one-off public/school holiday skewing the picture, but a single day-type calendar shift (e.g. a service change mid-quarter) wouldn't be caught.
- Headway is window-length ÷ departure count, not a mean of consecutive gaps: this stop has several routes overlapping, and two of them scheduled a few minutes apart (then a long gap to the next pair) makes a raw gap-average wildly dependent on which bucket happens to catch the short gap — it can misleadingly read as high-frequency in a bucket with only one or two trips. The window/count estimate is immune to that, at the cost of smoothing over any unevenness within a window.
- **Riders/trip divides real monthly ridership by one representative weekday's scheduled trips** — same caveat as `docs/demand_intelligence_findings.md`: treat it as a directional demand-pressure signal, not an exact per-trip load figure. It also compares the May-Jul 2026 OD window against the Sept 2026 schedule snapshot; a route renumbered in between would produce a misleading ratio (not the case for 220/227, which are long-standing route numbers, but worth naming as a general limitation).
- **Circuity uses one representative shape per route** (its most common physical path), not every branch/variant a route number might run — a route with several genuinely different path variants could have its complexity understated.

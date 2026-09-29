# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-09-29 13:07 UTC** (247h 59m, 4,070 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **68.9%** of stop visits on time
- **14.9%** more than 5 minutes late
- **16.2%** more than 1 minute early
- 1,236,371 stop visits measured

### Weekday vs weekend

A blended figure across the whole collection window hides a real difference — **weekday and weekend service run at different reliability**, and earlier versions of this report were built from weekend-only data without saying so. Split here by the scheduled service's actual calendar day, not by when we happened to be polling:

| | On time | Late | Early | Stop visits |
|---|---|---|---|---|
| Weekday | 66.8% | 12.8% | 20.4% | 507,133 |
| Weekend | 70.4% | 16.3% | 13.3% | 729,238 |

![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)

These numbers are close (weekday and weekend within a few points of each other) — that's real, not a bug, and it's worth understanding *why* before concluding weekend service is nearly as good as weekday: on-time performance only measures the trips that run, not how many exist. See `docs/weekend_frequency_gap.md` for the actual weekend gap this number can't show — a real fraction of routes have zero weekend service at all, affecting ~7-10% of weekday ridership.

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F50 | Ferry | 13.7% | 1.2% | 85.1% | 322 | 173 |
| 50 | Bus | 20.1% | 0.4% | 79.5% | 283 | 36 |
| 643 | Bus | 27.5% | 12.8% | 59.7% | 149 | 6 |
| 116 | Bus | 29.2% | 68.1% | 2.7% | 408 | 7 |
| 416 | Bus | 32.2% | 0.7% | 67.1% | 143 | 9 |
| 182 | Bus | 33.1% | 34.3% | 32.6% | 1,390 | 33 |
| 40 | Bus | 33.1% | 0.0% | 66.9% | 353 | 42 |
| 446 | Bus | 34.2% | 9.2% | 56.7% | 120 | 7 |
| N199 | Bus | 35.5% | 0.0% | 64.5% | 186 | 7 |
| 357 | Bus | 37.7% | 27.6% | 34.7% | 783 | 29 |
| N226 | Bus | 37.7% | 55.5% | 6.8% | 382 | 5 |
| 432 | Bus | 38.0% | 18.8% | 43.2% | 752 | 33 |
| 336 | Bus | 38.2% | 48.9% | 12.9% | 319 | 7 |
| 201 | Bus | 38.2% | 8.9% | 52.9% | 429 | 27 |
| 431 | Bus | 39.4% | 9.9% | 50.7% | 292 | 11 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| SHBR | Rail | 100.0% | 0.0% | 0.0% | 105 | 13 |
| DBCA | Rail | 100.0% | 0.0% | 0.0% | 34 | 7 |
| BRSH | Rail | 100.0% | 0.0% | 0.0% | 98 | 12 |
| L1 | Tram/Light Rail | 99.5% | 0.4% | 0.1% | 21,373 | 792 |
| BRRP | Rail | 99.3% | 0.5% | 0.2% | 427 | 16 |
| BRCL | Rail | 98.9% | 0.0% | 1.1% | 91 | 7 |
| IPBR | Rail | 98.8% | 0.0% | 1.2% | 252 | 12 |
| BRRP | Rail | 98.5% | 0.0% | 1.5% | 200 | 9 |
| SHBR | Rail | 98.3% | 0.0% | 1.7% | 174 | 20 |
| DBBR | Rail | 98.2% | 0.0% | 1.8% | 163 | 14 |
| 669 | Bus | 97.7% | 0.0% | 2.3% | 88 | 5 |
| SPRP | Rail | 97.6% | 0.0% | 2.4% | 245 | 7 |
| SHBR | Rail | 97.5% | 1.9% | 0.5% | 364 | 35 |
| BRDB | Rail | 97.3% | 0.0% | 2.7% | 75 | 8 |
| SHBR | Rail | 97.2% | 0.0% | 2.8% | 422 | 33 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| 199 | 8,828 | 2,446 | 20:01 | 13:05 |
| M1 | 7,013 | 2,805 | 05:07 | 13:05 |
| 60 | 6,672 | 2,128 | 20:01 | 13:02 |
| 700 | 6,509 | 2,590 | 05:07 | 13:01 |
| SHBR | 6,198 | 620 | 22:37 | 13:21 |
| 705 | 5,111 | 2,442 | 05:09 | 12:53 |
| 61 | 4,269 | 2,174 | 20:01 | 13:04 |
| M2 | 4,256 | 1,977 | 05:07 | 13:04 |
| 340 | 4,145 | 2,147 | 20:27 | 13:05 |
| 196 | 4,095 | 2,166 | 20:18 | 13:03 |
| BDBR | 3,819 | 428 | 02:29 | 13:21 |
| 333 | 3,406 | 1,941 | 20:25 | 13:04 |
| 385 | 3,388 | 1,788 | 20:34 | 13:05 |
| 555 | 3,286 | 1,510 | 05:09 | 12:58 |
| 100 | 3,203 | 1,737 | 20:25 | 12:40 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.
- The route-level Worst/Best tables and the bunching table below are **blended across weekday and weekend** (splitting them further would thin out the per-route trip counts below the reliability threshold for most routes). Only the citywide/mode figures above are split by day type.

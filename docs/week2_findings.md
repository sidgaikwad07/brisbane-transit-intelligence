# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-10-08 11:40 UTC** (462h 32m, 6,635 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **68.5%** of stop visits on time
- **14.2%** more than 5 minutes late
- **17.3%** more than 1 minute early
- 1,596,933 stop visits measured

### Weekday vs weekend

A blended figure across the whole collection window hides a real difference — **weekday and weekend service run at different reliability**, and earlier versions of this report were built from weekend-only data without saying so. Split here by the scheduled service's actual calendar day, not by when we happened to be polling:

| | On time | Late | Early | Stop visits |
|---|---|---|---|---|
| Weekday | 65.9% | 13.7% | 20.4% | 770,468 |
| Weekend | 70.9% | 14.7% | 14.5% | 826,465 |

![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)

These numbers are close (weekday and weekend within a few points of each other) — that's real, not a bug, and it's worth understanding *why* before concluding weekend service is nearly as good as weekday: on-time performance only measures the trips that run, not how many exist. See `docs/weekend_frequency_gap.md` for the actual weekend gap this number can't show — a real fraction of routes have zero weekend service at all, affecting ~7-10% of weekday ridership.

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F23 | Ferry | 9.4% | 0.0% | 90.6% | 456 | 290 |
| F24 | Ferry | 14.3% | 0.0% | 85.7% | 483 | 292 |
| F50 | Ferry | 14.4% | 1.6% | 84.0% | 369 | 191 |
| 50 | Bus | 20.6% | 1.7% | 77.7% | 462 | 58 |
| F22 | Ferry | 22.2% | 0.0% | 77.8% | 126 | 86 |
| 546 | Bus | 25.0% | 25.6% | 49.4% | 176 | 29 |
| N199 | Bus | 25.9% | 0.0% | 74.1% | 301 | 12 |
| F21 | Ferry | 26.9% | 0.0% | 73.1% | 480 | 307 |
| N154 | Bus | 27.0% | 54.7% | 18.3% | 382 | 9 |
| N339 | Bus | 29.6% | 70.0% | 0.4% | 277 | 7 |
| F11 | Ferry | 32.6% | 14.0% | 53.5% | 43 | 11 |
| SMBI | Ferry | 32.6% | 1.5% | 65.9% | 745 | 132 |
| 142 | Bus | 33.1% | 9.8% | 57.1% | 133 | 27 |
| 446 | Bus | 35.1% | 8.6% | 56.2% | 185 | 10 |
| 40 | Bus | 35.5% | 5.4% | 59.0% | 608 | 69 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| L1 | Tram/Light Rail | 99.4% | 0.5% | 0.1% | 25,045 | 900 |
| BRSP | Rail | 97.8% | 0.0% | 2.2% | 90 | 5 |
| BRCA | Rail | 96.3% | 0.0% | 3.7% | 187 | 17 |
| DBCA | Rail | 94.9% | 0.0% | 5.1% | 99 | 20 |
| 746 | Bus | 94.6% | 2.7% | 2.7% | 149 | 13 |
| BRRP | Rail | 94.1% | 1.6% | 4.2% | 1,577 | 65 |
| SPNA | Rail | 93.8% | 0.0% | 6.2% | 484 | 13 |
| BRIP | Rail | 92.9% | 2.1% | 5.1% | 966 | 40 |
| SPBR | Rail | 92.8% | 7.2% | 0.0% | 153 | 13 |
| SPCA | Rail | 92.0% | 1.8% | 6.2% | 2,647 | 91 |
| 644 | Bus | 91.8% | 2.1% | 6.2% | 764 | 53 |
| 672 | Bus | 91.7% | 0.3% | 7.9% | 1,233 | 61 |
| CABR | Rail | 91.4% | 4.5% | 4.1% | 269 | 23 |
| DBBR | Rail | 91.4% | 0.0% | 8.6% | 968 | 82 |
| SHBR | Rail | 91.4% | 0.9% | 7.7% | 3,443 | 301 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| 199 | 13,006 | 3,989 | 20:01 | 12:49 |
| M1 | 10,791 | 4,554 | 05:07 | 11:32 |
| 700 | 9,970 | 4,070 | 05:07 | 12:52 |
| 60 | 9,918 | 3,507 | 20:01 | 12:53 |
| 705 | 7,628 | 3,703 | 05:09 | 12:48 |
| M2 | 6,635 | 3,330 | 05:07 | 11:36 |
| 61 | 6,614 | 3,581 | 20:01 | 12:53 |
| 385 | 6,500 | 3,118 | 20:34 | 12:49 |
| 340 | 6,457 | 3,432 | 20:27 | 12:49 |
| 196 | 6,289 | 3,516 | 20:18 | 12:52 |
| SHBR | 6,270 | 625 | 22:37 | 01:04 |
| 333 | 5,533 | 3,181 | 20:25 | 12:51 |
| SHCL | 5,437 | 588 | 21:50 | 12:31 |
| 444 | 5,205 | 3,105 | 20:01 | 12:53 |
| 100 | 4,768 | 2,780 | 20:25 | 12:48 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.
- The route-level Worst/Best tables and the bunching table below are **blended across weekday and weekend** (splitting them further would thin out the per-route trip counts below the reliability threshold for most routes). Only the citywide/mode figures above are split by day type.

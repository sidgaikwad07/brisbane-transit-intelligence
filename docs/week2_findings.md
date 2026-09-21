# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-09-21 21:57 UTC** (64h 49m, 1,292 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **69.6%** of stop visits on time
- **14.4%** more than 5 minutes late
- **15.9%** more than 1 minute early
- 585,592 stop visits measured

### Weekday vs weekend

A blended figure across the whole collection window hides a real difference — **weekday and weekend service run at different reliability**, and earlier versions of this report were built from weekend-only data without saying so. Split here by the scheduled service's actual calendar day, not by when we happened to be polling:

| | On time | Late | Early | Stop visits |
|---|---|---|---|---|
| Weekday | 68.6% | 12.0% | 19.4% | 257,847 |
| Weekend | 70.5% | 16.3% | 13.2% | 327,745 |

![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F50 | Ferry | 16.3% | 0.5% | 83.2% | 202 | 116 |
| 50 | Bus | 24.6% | 6.6% | 68.9% | 122 | 15 |
| 116 | Bus | 29.2% | 68.1% | 2.7% | 408 | 7 |
| 40 | Bus | 30.7% | 19.9% | 49.4% | 166 | 18 |
| 70 | Bus | 32.1% | 0.0% | 67.9% | 81 | 6 |
| 182 | Bus | 33.1% | 34.3% | 32.6% | 1,390 | 33 |
| 471 | Bus | 33.3% | 18.6% | 48.0% | 204 | 10 |
| 581 | Bus | 35.2% | 34.4% | 30.3% | 122 | 14 |
| N199 | Bus | 35.5% | 0.0% | 64.5% | 186 | 7 |
| 414 | Bus | 36.2% | 7.2% | 56.5% | 138 | 7 |
| CLBR | Rail | 36.8% | 0.0% | 63.2% | 144 | 6 |
| 275 | Bus | 37.3% | 34.7% | 28.0% | 300 | 8 |
| N226 | Bus | 37.7% | 55.5% | 6.8% | 382 | 5 |
| 142 | Bus | 38.3% | 19.1% | 42.6% | 47 | 10 |
| SMBI | Ferry | 39.5% | 1.1% | 59.3% | 435 | 81 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| SHBR | Rail | 100.0% | 0.0% | 0.0% | 105 | 13 |
| BRSH | Rail | 100.0% | 0.0% | 0.0% | 98 | 12 |
| L1 | Tram/Light Rail | 99.1% | 0.8% | 0.2% | 10,912 | 435 |
| SHBR | Rail | 97.5% | 1.9% | 0.5% | 364 | 35 |
| RPBR | Rail | 97.2% | 0.0% | 2.8% | 287 | 13 |
| 686 | Bus | 96.7% | 0.0% | 3.3% | 305 | 13 |
| 689 | Bus | 95.0% | 0.3% | 4.7% | 319 | 15 |
| BRFG | Rail | 94.9% | 0.0% | 5.1% | 236 | 15 |
| DBBR | Rail | 94.9% | 0.0% | 5.1% | 176 | 13 |
| SPRP | Rail | 94.6% | 2.4% | 3.0% | 539 | 16 |
| 266 | Bus | 94.6% | 1.8% | 3.6% | 167 | 5 |
| CASP | Rail | 94.4% | 0.0% | 5.6% | 215 | 8 |
| SPRP | Rail | 94.2% | 1.0% | 4.8% | 776 | 23 |
| SHBR | Rail | 93.7% | 0.0% | 6.3% | 441 | 35 |
| CAIP | Rail | 93.7% | 0.0% | 6.3% | 335 | 11 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| SHBR | 6,198 | 620 | 22:37 | 13:21 |
| BDBR | 3,819 | 428 | 02:29 | 13:21 |
| 700 | 2,573 | 931 | 05:07 | 21:56 |
| M1 | 2,516 | 986 | 05:07 | 21:56 |
| 705 | 1,916 | 838 | 05:09 | 21:56 |
| M2 | 1,624 | 730 | 05:07 | 21:56 |
| 199 | 1,479 | 401 | 20:01 | 21:56 |
| 60 | 1,385 | 361 | 20:01 | 21:56 |
| 701 | 1,171 | 640 | 05:07 | 21:56 |
| DBBR | 1,156 | 424 | 02:33 | 13:21 |
| 704 | 1,154 | 574 | 05:07 | 21:56 |
| 555 | 1,072 | 519 | 05:09 | 21:55 |
| 765 | 972 | 546 | 05:07 | 21:56 |
| 196 | 934 | 567 | 05:08 | 13:10 |
| 199 | 927 | 521 | 05:07 | 13:17 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.
- The route-level Worst/Best tables and the bunching table below are **blended across weekday and weekend** (splitting them further would thin out the per-route trip counts below the reliability threshold for most routes). Only the citywide/mode figures above are split by day type.

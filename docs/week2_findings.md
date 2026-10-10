# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-10-10 00:41 UTC** (499h 33m, 6,912 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **68.2%** of stop visits on time
- **14.4%** more than 5 minutes late
- **17.4%** more than 1 minute early
- 1,874,488 stop visits measured

### Weekday vs weekend

A blended figure across the whole collection window hides a real difference — **weekday and weekend service run at different reliability**, and earlier versions of this report were built from weekend-only data without saying so. Split here by the scheduled service's actual calendar day, not by when we happened to be polling:

| | On time | Late | Early | Stop visits |
|---|---|---|---|---|
| Weekday | 66.0% | 13.6% | 20.4% | 966,310 |
| Weekend | 70.6% | 15.3% | 14.2% | 908,178 |

![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)

These numbers are close (weekday and weekend within a few points of each other) — that's real, not a bug, and it's worth understanding *why* before concluding weekend service is nearly as good as weekday: on-time performance only measures the trips that run, not how many exist. See `docs/weekend_frequency_gap.md` for the actual weekend gap this number can't show — a real fraction of routes have zero weekend service at all, affecting ~7-10% of weekday ridership.

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F23 | Ferry | 10.4% | 0.2% | 89.5% | 541 | 343 |
| F50 | Ferry | 10.8% | 1.6% | 87.5% | 369 | 191 |
| F24 | Ferry | 15.6% | 1.8% | 82.7% | 565 | 347 |
| F22 | Ferry | 19.5% | 0.0% | 80.5% | 251 | 168 |
| 50 | Bus | 22.1% | 1.4% | 76.5% | 557 | 70 |
| N199 | Bus | 25.9% | 0.0% | 74.1% | 301 | 12 |
| F21 | Ferry | 26.7% | 0.0% | 73.3% | 559 | 356 |
| N154 | Bus | 27.0% | 54.7% | 18.3% | 382 | 9 |
| SMBI | Ferry | 29.5% | 1.5% | 69.0% | 745 | 132 |
| N339 | Bus | 29.6% | 70.0% | 0.4% | 277 | 7 |
| 546 | Bus | 29.8% | 8.1% | 62.1% | 235 | 38 |
| 142 | Bus | 30.1% | 8.0% | 62.0% | 163 | 33 |
| 416 | Bus | 33.7% | 0.0% | 66.3% | 282 | 15 |
| 40 | Bus | 35.3% | 3.9% | 60.7% | 685 | 78 |
| F11 | Ferry | 35.3% | 12.7% | 52.0% | 102 | 24 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| L1 | Tram/Light Rail | 99.6% | 0.3% | 0.1% | 25,756 | 920 |
| 669 | Bus | 98.0% | 0.0% | 2.0% | 200 | 12 |
| BRCA | Rail | 96.9% | 0.0% | 3.1% | 229 | 20 |
| BRRP | Rail | 94.9% | 1.4% | 3.7% | 1,852 | 79 |
| SPBR | Rail | 94.6% | 5.4% | 0.0% | 205 | 17 |
| BRSP | Rail | 94.5% | 0.0% | 5.5% | 109 | 6 |
| RPIP | Rail | 94.3% | 0.0% | 5.7% | 105 | 6 |
| BRIP | Rail | 93.6% | 1.7% | 4.7% | 1,207 | 51 |
| SPNA | Rail | 93.1% | 1.3% | 5.5% | 667 | 18 |
| CABR | Rail | 92.8% | 3.8% | 3.4% | 319 | 27 |
| DBBR | Rail | 92.5% | 0.0% | 7.5% | 1,248 | 109 |
| SHBR | Rail | 92.3% | 0.8% | 6.9% | 4,163 | 361 |
| 640 | Bus | 92.0% | 1.7% | 6.3% | 3,392 | 90 |
| SPCA | Rail | 91.8% | 2.0% | 6.2% | 2,931 | 103 |
| 670 | Bus | 91.5% | 2.8% | 5.7% | 1,451 | 75 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| 199 | 16,084 | 4,982 | 05:07 | 00:38 |
| 60 | 12,449 | 4,415 | 05:09 | 00:38 |
| M1 | 11,650 | 4,785 | 05:07 | 00:38 |
| 700 | 10,929 | 4,518 | 05:07 | 00:38 |
| 385 | 8,651 | 4,095 | 05:07 | 00:38 |
| 705 | 8,406 | 4,100 | 05:09 | 00:37 |
| 196 | 8,187 | 4,552 | 05:08 | 00:38 |
| 61 | 8,074 | 4,475 | 05:07 | 00:38 |
| 340 | 8,006 | 4,346 | 05:07 | 00:38 |
| M2 | 7,194 | 3,511 | 05:07 | 00:38 |
| 333 | 7,081 | 4,067 | 05:09 | 00:38 |
| 444 | 6,867 | 4,082 | 05:08 | 00:38 |
| SHBR | 6,818 | 890 | 22:37 | 01:04 |
| 130 | 6,142 | 3,564 | 05:12 | 00:33 |
| SPRP | 5,940 | 1,536 | 05:17 | 12:21 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.
- The route-level Worst/Best tables and the bunching table below are **blended across weekday and weekend** (splitting them further would thin out the per-route trip counts below the reliability threshold for most routes). Only the citywide/mode figures above are split by day type.

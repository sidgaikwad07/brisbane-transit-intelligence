# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-09-24 08:24 UTC** (123h 16m, 2,029 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **69.2%** of stop visits on time
- **14.8%** more than 5 minutes late
- **16.0%** more than 1 minute early
- 626,012 stop visits measured

### Weekday vs weekend

A blended figure across the whole collection window hides a real difference — **weekday and weekend service run at different reliability**, and earlier versions of this report were built from weekend-only data without saying so. Split here by the scheduled service's actual calendar day, not by when we happened to be polling:

| | On time | Late | Early | Stop visits |
|---|---|---|---|---|
| Weekday | 67.8% | 13.1% | 19.2% | 298,267 |
| Weekend | 70.5% | 16.3% | 13.2% | 327,745 |

![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F50 | Ferry | 19.0% | 0.5% | 80.6% | 211 | 118 |
| 529 | Bus | 20.3% | 61.0% | 18.6% | 59 | 6 |
| 50 | Bus | 23.3% | 8.7% | 68.0% | 150 | 18 |
| 263 | Bus | 24.8% | 74.4% | 0.9% | 117 | 5 |
| 116 | Bus | 29.2% | 68.1% | 2.7% | 408 | 7 |
| 471 | Bus | 32.8% | 16.6% | 50.6% | 253 | 12 |
| 182 | Bus | 33.1% | 34.3% | 32.6% | 1,390 | 33 |
| 416 | Bus | 35.2% | 1.9% | 62.9% | 105 | 6 |
| N199 | Bus | 35.5% | 0.0% | 64.5% | 186 | 7 |
| 40 | Bus | 36.5% | 6.6% | 56.9% | 181 | 19 |
| N226 | Bus | 37.7% | 55.5% | 6.8% | 382 | 5 |
| 142 | Bus | 37.9% | 12.1% | 50.0% | 58 | 12 |
| 161 | Bus | 38.3% | 14.0% | 47.6% | 1,119 | 26 |
| CLBR | Rail | 38.4% | 0.0% | 61.6% | 336 | 14 |
| 202 | Bus | 39.4% | 8.8% | 51.9% | 457 | 14 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| BRSH | Rail | 100.0% | 0.0% | 0.0% | 98 | 12 |
| SHBR | Rail | 100.0% | 0.0% | 0.0% | 105 | 13 |
| SPRP | Rail | 99.5% | 0.0% | 0.5% | 208 | 9 |
| L1 | Tram/Light Rail | 99.4% | 0.4% | 0.2% | 11,422 | 448 |
| RPSP | Rail | 99.0% | 0.0% | 1.0% | 194 | 7 |
| BRRP | Rail | 99.0% | 0.0% | 1.0% | 196 | 9 |
| BRSH | Rail | 98.5% | 0.0% | 1.5% | 133 | 12 |
| SPRP | Rail | 98.3% | 0.0% | 1.7% | 175 | 5 |
| RPBR | Rail | 98.0% | 0.0% | 2.0% | 299 | 13 |
| SHBR | Rail | 97.5% | 1.9% | 0.5% | 364 | 35 |
| IPRW | Rail | 97.1% | 0.0% | 2.9% | 34 | 6 |
| SPCA | Rail | 97.0% | 0.0% | 3.0% | 169 | 8 |
| BRIP | Rail | 96.6% | 0.0% | 3.4% | 326 | 12 |
| DBBR | Rail | 96.3% | 0.0% | 3.7% | 163 | 14 |
| CASP | Rail | 96.2% | 0.0% | 3.8% | 158 | 7 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| SHBR | 6,198 | 620 | 22:37 | 13:21 |
| M1 | 3,905 | 1,419 | 05:07 | 08:22 |
| BDBR | 3,819 | 428 | 02:29 | 13:21 |
| 199 | 3,732 | 891 | 20:01 | 08:22 |
| 60 | 3,263 | 802 | 20:01 | 08:22 |
| 700 | 3,025 | 1,251 | 05:07 | 08:22 |
| 705 | 2,832 | 1,252 | 05:09 | 08:22 |
| M2 | 2,600 | 1,037 | 05:07 | 08:22 |
| 61 | 1,725 | 862 | 20:01 | 08:20 |
| 555 | 1,560 | 754 | 05:09 | 08:21 |
| 701 | 1,522 | 872 | 05:07 | 08:22 |
| 100 | 1,522 | 692 | 20:25 | 08:22 |
| 196 | 1,492 | 801 | 20:18 | 08:22 |
| 333 | 1,490 | 811 | 20:25 | 08:21 |
| 340 | 1,423 | 762 | 20:27 | 08:22 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.
- The route-level Worst/Best tables and the bunching table below are **blended across weekday and weekend** (splitting them further would thin out the per-route trip counts below the reliability threshold for most routes). Only the citywide/mode figures above are split by day type.

# Week 2 findings — on-time performance & bunching

Collection window: **2026-09-19 05:07 – 2026-09-20 07:19 UTC** (26h 11m, 578 polls) — our own measurement from polled GTFS-Realtime data, not Translink's official on-time stat.

"On time" here means arriving no more than 1 minute early and no more than 5 minutes late — a common industry convention. Early running counts against a route because it strands passengers who timed their arrival to the published schedule, not just late running.

## Citywide

- **70.4%** of stop visits on time
- **16.6%** more than 5 minutes late
- **13.0%** more than 1 minute early
- 284,963 stop visits measured

![On-time performance by mode](images/week2_on_time_by_mode.png)

## Worst on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| F50 | Ferry | 15.7% | 1.0% | 83.3% | 102 | 61 |
| 767 | Bus | 23.9% | 75.1% | 1.0% | 393 | 14 |
| 116 | Bus | 29.2% | 68.1% | 2.7% | 408 | 7 |
| 768 | Bus | 29.7% | 66.6% | 3.6% | 878 | 28 |
| 182 | Bus | 34.6% | 34.9% | 30.4% | 1,262 | 31 |
| N199 | Bus | 35.5% | 0.0% | 64.5% | 186 | 7 |
| 758 | Bus | 36.6% | 60.6% | 2.8% | 142 | 10 |
| 629 | Bus | 37.5% | 59.5% | 3.0% | 536 | 18 |
| N226 | Bus | 37.7% | 55.5% | 6.8% | 382 | 5 |
| SMBI | Ferry | 40.4% | 1.3% | 58.3% | 235 | 44 |
| 19 | Bus | 45.2% | 15.3% | 39.5% | 803 | 70 |
| 197 | Bus | 46.1% | 13.6% | 40.3% | 154 | 9 |
| 212 | Bus | 48.6% | 46.1% | 5.3% | 697 | 19 |
| 175 | Bus | 48.8% | 48.8% | 2.4% | 2,768 | 76 |
| 322 | Bus | 48.9% | 40.2% | 10.8% | 1,042 | 19 |

## Best on-time performance (routes with ≥30 stop visits across ≥5 distinct trips)

| Route | Mode | On time | Late | Early | Stop visits | Trips |
|---|---|---|---|---|---|---|
| BRBR | Rail | 100.0% | 0.0% | 0.0% | 30 | 5 |
| BRSH | Rail | 100.0% | 0.0% | 0.0% | 98 | 12 |
| SHBR | Rail | 100.0% | 0.0% | 0.0% | 105 | 13 |
| L1 | Tram/Light Rail | 99.8% | 0.1% | 0.0% | 5,295 | 218 |
| 240 | Bus | 96.6% | 0.0% | 3.4% | 176 | 6 |
| 763 | Bus | 96.5% | 1.7% | 1.7% | 345 | 30 |
| SHBR | Rail | 96.2% | 3.0% | 0.8% | 237 | 23 |
| 689 | Bus | 95.6% | 0.0% | 4.4% | 275 | 13 |
| BRFG | Rail | 94.9% | 0.0% | 5.1% | 236 | 15 |
| 676 | Bus | 94.9% | 0.0% | 5.1% | 433 | 24 |
| SPRP | Rail | 94.6% | 2.4% | 3.0% | 539 | 16 |
| DBBR | Rail | 94.1% | 0.0% | 5.9% | 152 | 11 |
| 654 | Bus | 94.1% | 0.0% | 5.9% | 322 | 11 |
| CAIP | Rail | 93.7% | 0.0% | 6.3% | 335 | 11 |
| 578 | Bus | 93.3% | 5.8% | 1.0% | 208 | 7 |

## Bunching (two vehicles on the same route within 400m, same poll)

| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |
|---|---|---|---|---|
| SHBR | 3,929 | 397 | 22:37 | 07:19 |
| 700 | 1,911 | 525 | 05:07 | 07:18 |
| BDBR | 1,499 | 205 | 02:29 | 07:19 |
| 704 | 951 | 398 | 05:07 | 07:19 |
| 701 | 880 | 421 | 05:07 | 07:19 |
| M1 | 806 | 467 | 05:07 | 07:18 |
| 705 | 774 | 401 | 05:09 | 07:19 |
| 199 | 764 | 389 | 05:07 | 07:19 |
| 555 | 761 | 336 | 05:09 | 07:19 |
| 196 | 718 | 421 | 05:08 | 07:18 |
| 765 | 704 | 342 | 05:07 | 07:19 |
| 60 | 660 | 400 | 05:09 | 07:19 |
| 61 | 653 | 385 | 05:07 | 07:19 |
| TX7 | 560 | 395 | 05:07 | 07:17 |
| 340 | 558 | 372 | 05:07 | 07:19 |

## Method & caveats

- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; we take the last one polled before the vehicle presumably passed as the closest proxy to what happened, without cross-referencing vehicle positions stop-by-stop.
- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position check — two vehicles happening to be near each other at a shared terminus or layover point can register as "bunched" without actually being back-to-back on route. Treat the ranking as directional, not exact.
- Route rankings only include routes with ≥30 stop visits **across ≥5 distinct trips**. Stop visits alone aren't enough: a low-frequency route can rack up dozens of stop visits from a single catastrophically delayed trip cascading down its stop sequence, making one bad run look like a systemically unreliable route. Requiring several independent trips guards against that.
- A short collection window skews toward whatever was running when it was collected (e.g. all-peak, or all-overnight) — check the collection window above before treating a route's number as representative of its typical performance.

# Priority routes — where demand and unreliability overlap

Every other finding in this repo looks at demand or reliability separately. This combines them: real ridership (Queensland Government OD data, May 2026, June 2026, July 2026) against measured on-time performance (our own polled GTFS-RT data — see `docs/week2_findings.md`). A route that's both heavily used *and* unreliable affects far more riders per late arrival than a quiet route running just as badly — that's the actual case for where to act first, not raw ridership or raw unreliability alone.

`priority_score = demand_percentile × (100 − on_time_percentile)` — both factors matter multiplicatively; a route only extreme on one axis doesn't rank highly for that alone. Scheduled trips on **Thursday, 29 October 2026** (representative weekday, same method as Week 1).

![Where should Translink act first?](images/priority_routes.png)

**"Rail (network)" and "Tram/Light Rail (network)" are network-wide aggregates, not single routes.** The OD dataset reports heavy rail and the Gold Coast Light Rail as one system-wide bucket each ("Rail", "GCLR") rather than per individual line the way bus routes get their own number — so unlike every bus/ferry row below, these two represent an entire network's average, not one corridor. Included so both modes are visible at all (a plain per-route join drops them completely — neither OD code matches a GTFS route_short_name), marked with a star on the chart, not ranked as if directly comparable to a single route.

## Top priority routes

| Route | Mode | Avg weekday riders | Riders/trip (percentile) | On-time % (percentile) |
|---|---|---|---|---|
| SMBI (Southern Moreton Bay Island) | Ferry | 5,208 | 85 (99th) | 30% (2nd) |
| F11 (Apollo Road / Riverside) | Ferry | 1,007 | 53 (99th) | 35% (3rd) |
| 443 (Moggil - City Rocket) | Bus | 639 | 40 (95th) | 41% (3rd) |
| F1 (Northshore Hamilton / UQ St Lucia) | Ferry | 14,216 | 115 (100th) | 49% (8th) |
| 546 (Park Ridge - City via Greenbank & Griffith Uni) | Bus | 684 | 34 (91st) | 30% (2nd) |
| 551 (Brisbane City - Crestmead) | Bus | 464 | 46 (98th) | 50% (10th) |
| 561 (Brisbane City - Crestmead) | Bus | 453 | 45 (97th) | 52% (13th) |
| 141 (Browns Plains - City Rocket) | Bus | 548 | 32 (88th) | 42% (4th) |
| 581 (Brisbane City - Slacks Creek) | Bus | 642 | 34 (91st) | 47% (8th) |
| 573 (Brisbane City - Loganholme via Daisy Hill) | Bus | 1,106 | 44 (97th) | 53% (14th) |
| 431 (Kenmore South - City Rocket) | Bus | 189 | 32 (87th) | 43% (5th) |
| 357 (Brendale - City Express) | Bus | 541 | 32 (88th) | 46% (7th) |
| 577 (Brisbane City - Springwood via Rochedale South) | Bus | 445 | 37 (94th) | 53% (13th) |
| 426 (Kenmore - City Rocket via Chapel Hill) | Bus | 216 | 31 (86th) | 46% (6th) |
| 186 (Wishart - City Rocket) | Bus | 567 | 30 (82nd) | 40% (3rd) |

**SMBI (Southern Moreton Bay Island)** tops the list: 5,208 riders/weekday — 99th percentile demand — running on-time only 30% of the time (2nd percentile reliability, near the bottom citywide). This is a heavily-used service that's unreliable most of the time it runs, which is a materially bigger problem than either a quiet-but-unreliable route or a busy-but-punctual one.

## Caveats

- Same caveats as the underlying data: ridership is a monthly average against one representative weekday's schedule (`docs/demand_intelligence_findings.md`), and on-time performance reflects the collection window logged in `docs/week2_findings.md` (growing over time as the poller keeps running) — re-run this after a longer collection window for a more stable reliability figure.
- Percentile-based scoring is relative, not absolute: if the *whole* network were reliable, a route at the bottom percentile could still have decent raw on-time performance, and vice versa. Check the raw numbers in the table, not just the rank.
- This ranks routes, not root causes — a route's poor on-time performance could stem from anything (road congestion, dwell time, schedule padding, driver availability); this analysis doesn't diagnose which, only where to look.

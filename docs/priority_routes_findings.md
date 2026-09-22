# Priority routes — where demand and unreliability overlap

Every other finding in this repo looks at demand or reliability separately. This combines them: real ridership (Queensland Government OD data, May 2026, June 2026, July 2026) against measured on-time performance (our own polled GTFS-RT data — see `docs/week2_findings.md`). A route that's both heavily used *and* unreliable affects far more riders per late arrival than a quiet route running just as badly — that's the actual case for where to act first, not raw ridership or raw unreliability alone.

`priority_score = demand_percentile × (100 − on_time_percentile)` — both factors matter multiplicatively; a route only extreme on one axis doesn't rank highly for that alone. Scheduled trips on **Thursday, 17 September 2026** (representative weekday, same method as Week 1).

![Where should Translink act first?](images/priority_routes.png)

## Top priority routes

| Route | Mode | Avg weekday riders | Riders/trip (percentile) | On-time % (percentile) |
|---|---|---|---|---|
| SMBI (Southern Moreton Bay Island) | Ferry | 5,208 | 85 (100th) | 38% (2nd) |
| 443 (Moggil - City Rocket) | Bus | 639 | 40 (96th) | 41% (3rd) |
| 212 (Carindale - City/Valley via Seven Hills) | Bus | 1,121 | 34 (92nd) | 41% (3rd) |
| 214 (Cannon Hill - City Express) | Bus | 534 | 36 (93rd) | 51% (9th) |
| 141 (Browns Plains - City Rocket) | Bus | 548 | 32 (89th) | 48% (5th) |
| 220 (Wynnum - City Express) | Bus | 1,083 | 35 (93rd) | 53% (11th) |
| 118 (Forest Lake - City) | Bus | 465 | 39 (95th) | 55% (13th) |
| 357 (Brendale - City Express) | Bus | 541 | 32 (88th) | 49% (7th) |
| 431 (Kenmore South - City Rocket) | Bus | 189 | 32 (87th) | 49% (6th) |
| 426 (Kenmore - City Rocket via Chapel Hill) | Bus | 216 | 31 (86th) | 46% (5th) |
| 192 (Yeronga - City via UQ Lakes and Highgate Hill) | Bus | 1,950 | 35 (93rd) | 56% (14th) |
| 235 (Balmoral - City/Valley via Thynne Road) | Bus | 1,736 | 32 (89th) | 53% (11th) |
| 227 (Wynnum - City) | Bus | 1,397 | 39 (95th) | 58% (18th) |
| 175 (Garden City - City via Logan Rd) | Bus | 4,301 | 30 (85th) | 51% (8th) |
| 210 (Cannon Hill - City/Valley) | Bus | 1,540 | 30 (84th) | 50% (7th) |

**SMBI (Southern Moreton Bay Island)** tops the list: 5,208 riders/weekday — 100th percentile demand — running on-time only 38% of the time (2nd percentile reliability, near the bottom citywide). This is a heavily-used service that's unreliable most of the time it runs, which is a materially bigger problem than either a quiet-but-unreliable route or a busy-but-punctual one.

Two routes from the Manly/Lota/Cleveland case study (`docs/manly_lota_service_gap.md`) — 220 and 227 — appear in this citywide top list too, independently confirming that case study's finding: they're not just locally notable, they're among the routes Brisbane's whole network most needs to fix.

## Caveats

- Same caveats as the underlying data: ridership is a monthly average against one representative weekday's schedule (`docs/demand_intelligence_findings.md`), and on-time performance reflects the collection window logged in `docs/week2_findings.md` (growing over time as the poller keeps running) — re-run this after a longer collection window for a more stable reliability figure.
- Percentile-based scoring is relative, not absolute: if the *whole* network were reliable, a route at the bottom percentile could still have decent raw on-time performance, and vice versa. Check the raw numbers in the table, not just the rank.
- This ranks routes, not root causes — a route's poor on-time performance could stem from anything (road congestion, dwell time, schedule padding, driver availability); this analysis doesn't diagnose which, only where to look.

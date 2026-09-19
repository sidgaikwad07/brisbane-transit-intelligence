# Week 1 findings — Brisbane transit network overview

Figures reflect scheduled service on **Thursday, 17 September 2026**, picked as a typical weekday (see `ingestion/service_calendar.py`): the date, among all Tuesday/Wednesday/Thursday dates in the feed, whose total scheduled-trip count is closest to the median — not just any date with `calendar.monday = true`, which double-counts wherever the feed republishes a service under overlapping calendar windows (school terms, mid-feed corrections).

- 12,768 stops with at least one scheduled trip that day
- 494 routes running that day
- 20,853 total scheduled trips

## Weekday trips by mode

| Mode | Weekday trips |
|---|---|
| Bus | 18,926 |
| Ferry | 844 |
| Rail | 810 |
| Tram/Light Rail | 273 |

## Busiest stops (by weekday scheduled trips)

| Stop | Weekday trips | Routes served |
|---|---|---|
| Cultural Centre station, platform 1 | 1,932 | 29 |
| Cultural Centre station, platform 2 | 1,437 | 22 |
| South Bank busway station, platform 4 | 1,437 | 22 |
| Mater Hill station, platform 2 | 1,437 | 22 |
| Mater Hill station, platform 1 | 1,436 | 22 |
| South Bank busway station, platform 5 | 1,436 | 22 |
| Roma Street busway, platform 2 | 1,305 | 30 |
| Roma Street busway, platform 1 | 1,159 | 31 |
| Griffith University station, platform 1 | 1,136 | 40 |
| Griffith University station, platform 2 | 1,081 | 40 |
| Buranda busway, platform 4 | 1,070 | 47 |
| Buranda busway, platform 3 | 1,007 | 47 |
| Woolloongabba station, platform 2 | 941 | 20 |
| Woolloongabba station, platform 1 | 940 | 20 |
| Upper Mt Gravatt station, platform 1 | 798 | 32 |

## Biggest interchanges (by distinct routes served)

| Stop | Routes served | Weekday trips |
|---|---|---|
| Buranda busway, platform 4 | 47 | 1,070 |
| Buranda busway, platform 3 | 47 | 1,007 |
| Griffith University station, platform 2 | 40 | 1,081 |
| Griffith University station, platform 1 | 40 | 1,136 |
| Upper Mt Gravatt station, platform 2 | 32 | 762 |
| Upper Mt Gravatt station, platform 1 | 32 | 798 |
| Roma Street busway, platform 1 | 31 | 1,159 |
| Roma Street busway, platform 2 | 30 | 1,305 |
| Cultural Centre station, platform 1 | 29 | 1,932 |
| Adelaide Street Stop 28 near Hutton Lane | 26 | 653 |
| Eight Mile Plains station, platform 1 | 25 | 566 |
| Eight Mile Plains station, platform 2 | 24 | 363 |
| South Bank busway station, platform 5 | 22 | 1,436 |
| South Bank busway station, platform 4 | 22 | 1,437 |
| Mater Hill station, platform 2 | 22 | 1,437 |

## Highest-frequency routes

| Route | Mode | Weekday trips |
|---|---|---|
| M2 | Bus | 366 |
| M1 | Bus | 364 |
| L1 | Tram/Light Rail | 273 |
| 60 | Bus | 262 |
| 199 | Bus | 235 |
| 412 | Bus | 232 |
| 700 | Bus | 231 |
| 130 | Bus | 186 |
| 150 | Bus | 185 |
| 345 | Bus | 182 |
| 333 | Bus | 178 |
| 61 | Bus | 169 |
| 222 | Bus | 166 |
| 100 | Bus | 165 |
| 196 | Bus | 162 |

![Brisbane transit network map — weekday route shapes by mode, zoomed to Greater Brisbane, with the busiest interchanges numbered and a full-SEQ inset for regional context](images/network_map.png)

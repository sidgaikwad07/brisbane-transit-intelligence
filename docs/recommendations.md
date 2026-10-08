# Recommendations for Translink / Queensland Government

Every recommendation below is traced back to a specific, sourced finding elsewhere in this
repo — nothing here is a generic "improve public transport" statement. Where a finding is a
short real-data collection window (days, not years), that's stated explicitly rather than
glossed over; treat these as a first-pass, evidence-backed agenda for further investigation,
not a finished business case.

## A. Service and network recommendations

### 1. Fix the weekend *coverage* gap before the weekend *frequency* gap

**Finding:** [`docs/weekend_frequency_gap.md`](weekend_frequency_gap.md) — 149 routes carrying
3.4M weekday riders have **zero Saturday service**; 181 routes carrying 4.4M weekday riders
have **zero Sunday service**. Among routes that *do* survive onto the weekend timetable,
headway is only marginally worse than weekday (7.8min vs 7.7min average wait) — the problem
isn't that weekend buses run less often, it's that whole routes don't exist on weekends at all.

**Recommendation:** Prioritize a "does this route run at all on Saturday/Sunday" audit over a
"how often does it run" audit. A route that already exists on weekends and just runs a bit less
often is a frequency problem (traditionally what gets funded); a route that vanishes entirely is
a coverage problem affecting riders who may have no weekend alternative. These need different
fixes and are currently invisible to each other in a single on-time-performance metric.

### 2. Ferry reliability is the network's biggest single problem, not a footnote

**Finding:** [`docs/priority_routes_findings.md`](priority_routes_findings.md) —
**SMBI (Southern Moreton Bay Islands ferry)** is the single highest-priority route citywide:
100th-percentile real demand (5,208 riders/weekday), running on-time only 41% of the time
(4th-percentile reliability). Network-wide, ferry on-time performance is **21% on weekdays and
37% at weekends** ([`docs/week2_findings.md`](week2_findings.md)), far worse than bus (64-69%),
rail (84-86%) or tram (99-100%).

**Recommendation:** Ferry reliability warrants its own dedicated investigation, independent of
bus/rail initiatives — it's a small fleet (so likely tractable root-causes: vessel availability,
tidal/weather sensitivity, terminal turnaround) affecting a captive ridership with limited
alternative routes to the mainland.

### 3. A specific, named list of bus routes is both high-demand and unreliable

**Finding:** [`docs/priority_routes_findings.md`](priority_routes_findings.md) lists the
network's top 15 routes by `demand percentile × unreliability percentile` — headed by SMBI, then
a cluster of bus routes (443, 212, 357, 431, 546, 141, 426, 220, 332, 598, 186, 118, 206, 210)
running at **38-58% on-time while sitting in the top fifth of the network for demand pressure**. Two of these (220, 227 in earlier
runs) independently corroborate the Manly/Lota/Cleveland case study below — the same routes
surface from two unrelated analysis angles.

**Recommendation:** This is a ready-made, ranked, demand-weighted worklist — not a hypothesis
that needs more research to be actionable. Route 220 alone affects 1,083 riders/weekday at only
53% on-time.

### 4. Rail and tram are already reliable — don't spend reliability budget there

**Finding:** [`docs/week2_findings.md`](week2_findings.md) — rail runs on-time 84-86% of the
time, tram/light rail 99-100%, both essentially flat between weekday and weekend. Bus (64-69%)
and ferry (21-37%) are where the network's reliability problem actually lives.

**Recommendation:** If reliability-improvement funding is mode-agnostic, the data says direct it
at bus operations and ferry, not rail infrastructure — rail is already performing well by any
reasonable standard.

### 5. The Manly/Lota/Cleveland corridor: two distinct, separately-fixable problems

**Finding:** [`docs/manly_lota_service_gap.md`](manly_lota_service_gap.md) — (a) routes
220/227 are demonstrably under-provisioned for their demand (top-5th-percentile ridership
pressure) — a targeted, corridor-specific case for added peak capacity; (b) the Cleveland rail
line drops to a **flat 30-minute headway on weekends and evenings**, worst at night/early
(160min average wait Sunday overnight vs 69min weekday) — but this is a **citywide pattern**,
not unique to this corridor, so the actual policy conversation is Brisbane's weekend/evening
frequency standard in general, with this corridor as one clear illustration.

**Recommendation:** Don't treat this as "fix Manly/Lota" — treat (a) as a targeted route-capacity
fix and (b) as a prompt to review the citywide off-peak frequency standard, since the same
pattern likely recurs on every rail line's weekend timetable (see #1 and #6).

### 6. Bunching is a real, measurable, and geographically concentrated problem

**Finding:** [`docs/density_findings.md`](density_findings.md) — 196,004 recorded bunching
snapshots (two vehicles on the same route within 400m, same poll) in the collection window,
concentrated far more tightly around the CBD/inner-city core than either scheduled service or
real ridership are — i.e., bunching isn't simply "where the busiest routes are," it clusters
somewhere more specific.

**Recommendation:** Investigate whether inner-city bunching hotspots correlate with specific
intersections, dwell-heavy stops, or signal-priority gaps — the geographic concentration (visible
in the heatmap, not just the aggregate count) suggests a location-specific cause worth a targeted
site visit, not just "add more buses."

### 7. Congestion/weather-based delay prediction needs a longer baseline before it's trustworthy

**Finding:** [`docs/delay_model_card.md`](delay_model_card.md) — an XGBoost delay-prediction
model trained on ~3.5 days of real traffic+weather+delay data currently **loses to a naive
baseline** on a fair (time-based) evaluation, because that short window contains one clear
reliability regime shift (a strike-caused disruption) that a few days of data can't teach a model
to generalize across. A diagnostic test confirms the underlying features (route, hour,
congestion, disruption-alert count) do carry real signal.

**Recommendation:** Not "the model doesn't work" — rather, "don't stand up a congestion-based
delay-prediction tool on a data window this short." Revisit once traffic/weather collection spans
multiple weeks including both disrupted and normal-operation periods.

## B. Process-automation recommendations — reducing manual reporting effort

The infrastructure in this repo (open-data polling → structured storage → live dashboard) is a
working prototype for something Translink/DTMR could operate internally. Each item below names
a manual process it could plausibly replace or reduce, based on what this project had to build
from scratch as an outsider using only public data.

### 8. Live on-time-performance measurement, not a periodic manual compilation

This project computes on-time performance directly from Translink's own public GTFS-Realtime
feed, continuously, with no manual data entry (`ingestion/gtfs_realtime_poller.py` →
`marts.mart_on_time_performance`). An internal equivalent — likely already partially existing
given TMR publishes some official punctuality stats — could run continuously rather than as a
periodic reporting exercise, and could be sliced by route/mode/time-of-day/day-of-week on demand
instead of waiting for the next scheduled report.

### 9. A single live view of active service disruptions, aggregated across the whole network

**Finding:** while investigating a single train-line timetable page, this project discovered its
own GTFS-RT Service Alerts polling (running unmodified since Week 2) already had **62 distinct
active disruptions** captured system-wide at once — including a strike-caused alert affecting 644
routes — with no manual per-page checking required. This is now surfaced as a single expandable
panel in the live dashboard (`dashboard/app.py`).

**Recommendation:** If staff currently check disruption status by visiting individual timetable
pages, a single aggregated live view (which this project's own dashboard demonstrates is
achievable from the *public* feed alone, in a few hours of engineering) would remove that
per-page manual step entirely.

### 10. Real ridership vs. scheduled service, cross-checked automatically instead of by hand

**Finding:** [`docs/priority_routes_findings.md`](priority_routes_findings.md) and
[`docs/demand_intelligence_findings.md`](demand_intelligence_findings.md) automatically join
Queensland Government's own published OD ridership data against the GTFS schedule to compute
riders-per-scheduled-trip and a ranked "where demand and unreliability overlap" worklist — a
join that, as built here, silently drops heavy rail and light rail because the OD dataset codes
them differently than GTFS does (documented and worked around in this repo, see
`priority_routes.py`'s `mode_aggregate_rows()`). If this cross-check is currently done manually
or not done at all, both the automation and the specific rail/tram data-matching issue are worth
fixing centrally, once, rather than every analyst re-discovering it independently.

### 11. A living map of where supply, demand, and reliability problems actually are

**Finding:** [`docs/density_findings.md`](density_findings.md)'s three-panel heatmap (scheduled
service density, real ridership density, bunching density) makes visually obvious where the
network's supply and demand track each other and where they don't — something that would take
considerably longer to establish from tabular reports alone.

**Recommendation:** A standing version of this (not a one-off chart) would let planning staff
visually spot emerging mismatches between where service is scheduled and where people actually
travel, without waiting for a dedicated study.

## C. Benchmarking against Sydney and Melbourne

Sections A and B look at Brisbane on its own. This section asks how Brisbane compares with its
two closest peers, measured the same way for all three: each city clipped to its ABS Greater
Capital City boundary, with the share of residents within 400m (about a 5-minute walk) of a stop
calculated from each city's own published timetable and the ABS 2025 population grid. Source for
everything below: [`docs/city_service_quality.md`](city_service_quality.md).

![Coverage by measure](images/city_service_coverage.png)

### 12. Make frequency, not coverage, the network's headline goal

**Finding:** Brisbane's *reach* is comparable to its peers: **70%** of residents live near a stop
with weekday service (Melbourne 73%). Its *frequency* is not: only **22%** live near a stop with
service every 15 minutes or better from 7am to 7pm, against **32%** in Melbourne and **41%** in
Sydney. Brisbane is last at every frequency threshold tested (every 30, 20, 15 and 10 minutes),
so this doesn't depend on where "frequent" is drawn.

**Recommendation:** Adopt "share of residents within walking distance of all-day frequent
service" as a published network target, benchmarked to peer cities. Matching Melbourne's share
today means bringing about **282,000 more Greater Brisbane residents** within 400m of frequent
service. The comparison also shows what that target costs. Brisbane runs **0.15** scheduled stop
departures per resident per weekday, against 0.19 in Melbourne (+28%) and 0.26 in Sydney (+70%).
Reshuffling routes alone (fewer, more frequent ones) can raise frequent coverage, but only by
cutting reach somewhere else. Closing most of the gap without that trade-off needs more service
hours, not just a redesign.

### 13. Plan frequent service into growth corridors as they are built, not after

**Finding:** Half of Brisbane's population growth since 2021 (**135K of 266K** new residents in
growing areas) landed in areas where under 5% of residents have frequent service nearby, slightly
more than those areas' 43% share of the existing population. Overall, 32% of Greater Brisbane
residents (904K) live in sizeable areas (10,000+ residents) with essentially no frequent service,
against 25% in Melbourne and 10% in Sydney. The largest are concentrated in three corridors:

| Corridor | Areas (ABS SA2) | Residents without frequent service |
|---|---|---|
| Ipswich / Springfield | Ripley, Redbank Plains, Springfield Lakes | ~79K |
| Moreton Bay north | Murrumba Downs - Griffin, Caboolture - South, Narangba, Kallangur, Burpengary | ~113K |
| Logan south | Boronia Heights - Park Ridge, Jimboomba - Glenlogan | ~50K |

Ripley alone grew by over 10,000 people between 2021 and 2025 and has **no** stop with frequent
service anywhere in it.

**Recommendation:** Treat these three corridors as the first places to apply #12's target. For
estates still being built, make frequent service part of the development timeline rather than a
retrofit once travel habits have formed around the car. The ranked list of 15 areas in
`docs/city_service_quality.md` (regenerated by `notebooks/city_service_quality.py`) is a
starting worklist that updates as ABS population estimates and timetables change.

### 14. Raise the evening frequency standard (strengthens #5)

**Finding:** Only **19%** of Brisbane residents live near a stop with service at least every 30
minutes from 8pm to midnight. That's under half of Sydney's **40%**, and below Melbourne's 29%.
This is the same pattern #5 found on the Cleveland line, now measured citywide and against peers.

**Recommendation:** #5 proposed reviewing Brisbane's off-peak frequency standard. The peer
comparison gives that review a concrete benchmark: a 30-minute-or-better evening service within
walking distance of at least as many residents as Melbourne (29%), as a first step towards
Sydney's level.

### 15. On weekends, protect the frequent corridors and restore missing routes (strengthens #1)

**Finding:** Brisbane's Sunday timetable runs only **43%** of its weekday departures, the lowest
of the three (Sydney 58%, Melbourne 65%). Yet its *frequent* coverage falls by only 35% from
weekday to Sunday, about the same as Sydney (36%). Melbourne's falls 59%, so on Sundays Melbourne
ends up slightly *behind* Brisbane (13% vs 14% of residents near frequent service). Brisbane's
weekend cuts fall mostly on routes outside its frequent corridors, which matches #1's finding
that whole routes disappear at weekends while surviving routes keep close to their weekday
frequency.

**Recommendation:** Keep the current approach of protecting frequent corridors on weekends.
Melbourne shows the alternative (keeping more routes running, each less often) doesn't produce
better frequent coverage. Weekend funding should go to #1's coverage gap, the routes that don't
run at all, rather than thinning out the frequent corridors to spread service further.

### 16. Benchmark against peer cities routinely, from public data

**Finding:** Every number in this section comes from public, freely downloadable data: three
static GTFS feeds and ABS boundary and population files. The whole comparison reruns in about 30
seconds. Building it surfaced data issues that would silently distort any one-off comparison.
Sydney's feed is statewide, not metro-only. 88% of its routes are school-only buses. Sydney
Trains publishes its timetable only about a month ahead of the rest of the NSW feed, so a
naively chosen "typical" day contains no Sydney trains at all (see
[`docs/city_comparison.md`](city_comparison.md)).

**Recommendation:** Run peer-city benchmarking as a standing, automated report (each time a
city publishes a new timetable) rather than as an occasional consultancy exercise. The data
issues above are exactly what a one-off study is likely to miss.

## Caveats that apply to this whole document

- Everything above is built from **public open data only** — Translink's GTFS static/real-time
  feeds, Queensland Government's OD ridership dataset, Brisbane City Council's traffic data,
  Open-Meteo weather, Transport for NSW's and Transport Victoria's static GTFS feeds, and ABS
  boundaries and population estimates — collected over a real but short window (days to a few months depending on
  the dataset; see each linked finding for its exact window). None of this used internal
  Translink operational data, fleet/rostering data, or cost data, all of which a real
  investigation would have access to and this project deliberately doesn't.
- Recommendations 1-7 and 12-15 are findings-driven and falsifiable — re-running the underlying scripts
  against a longer collection window is the natural next step to confirm each one holds up, not
  just accepting them as stated here.
- Recommendations 8-11 describe what became *possible* by building this project as an outside
  party with only public data and a few weeks of part-time effort — they're offered as evidence
  of what's achievable, not a claim about what Translink's internal tooling already does or
  doesn't do (unknown from outside). The same applies to #16.
- **Section C compares *scheduled* service, not delivered service.** It shows what each city's
  timetable promises, not what actually ran on the street. Comparing delivered reliability across
  the three cities needs Sydney's and Melbourne's real-time feeds, which require API keys this
  project doesn't have (City comparison Phase 2 in `ROADMAP.md`). Its 400m catchments are
  straight-line distance, not along streets, which if anything flatters outer suburbs, so #13's
  gaps are more likely understated than overstated.

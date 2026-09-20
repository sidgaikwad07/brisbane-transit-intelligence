-- On-time performance by route, measured from our own polled data rather
-- than Translink's official stat. "On time" follows the common industry
-- convention (e.g. used by many US/AU transit agencies): between 1 minute
-- early and 5 minutes late, inclusive. Early running is penalised more
-- harshly than late running because a too-early vehicle strands waiting
-- passengers, same as a late one.
--
-- n_trips (distinct trip_id) matters alongside n_stop_visits: a route with
-- few actual runs in the window can have dozens of stop visits that all
-- come from one catastrophically delayed trip cascading down its stop
-- sequence, making a single bad run look like a systemically unreliable
-- route. Filter/interpret rankings by n_trips, not just n_stop_visits.
with stop_delay as (
    select * from {{ ref('mart_stop_delay') }}
),
routes as (
    select * from {{ ref('stg_routes') }}
)
select
    r.route_id,
    r.route_short_name,
    r.route_long_name,
    r.mode,
    count(*) as n_stop_visits,
    count(distinct sd.trip_id) as n_trips,
    round(avg(sd.arrival_delay_sec)) as avg_arrival_delay_sec,
    round(
        percentile_cont(0.5) within group (order by sd.arrival_delay_sec)
    ) as median_arrival_delay_sec,
    round(
        100.0 * sum(case when sd.arrival_delay_sec between -60 and 300 then 1 else 0 end)
        / count(*),
        1
    ) as on_time_pct,
    round(
        100.0 * sum(case when sd.arrival_delay_sec > 300 then 1 else 0 end)
        / count(*),
        1
    ) as late_pct,
    round(
        100.0 * sum(case when sd.arrival_delay_sec < -60 then 1 else 0 end)
        / count(*),
        1
    ) as early_pct
from stop_delay sd
join routes r on r.route_id = sd.route_id
group by r.route_id, r.route_short_name, r.route_long_name, r.mode
order by n_stop_visits desc

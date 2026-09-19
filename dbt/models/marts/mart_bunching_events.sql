-- Bunching heuristic: two distinct vehicles on the same route, whose
-- positions in the *same poll* (same polled_at — every vehicle_positions
-- row from one poll cycle shares an identical timestamp, set once per poll
-- by the poller) sit within 400m of each other. 400m is a deliberately
-- tight threshold — two buses that close together on the same route are
-- effectively running as one, doubling the wait for the gap behind them.
-- Flat-earth distance approximation (fine at this scale, ~10m error over a
-- few km) rather than a full haversine, since PostGIS isn't wired up here yet.
with vp as (
    select * from {{ ref('stg_vehicle_positions') }}
),
paired as (
    select
        a.route_id,
        a.polled_at,
        a.vehicle_id as vehicle_a,
        b.vehicle_id as vehicle_b,
        a.trip_id as trip_a,
        b.trip_id as trip_b,
        a.latitude as lat_a,
        a.longitude as lon_a,
        sqrt(
            power((a.latitude - b.latitude) * 111320, 2)
            + power((a.longitude - b.longitude) * 111320 * cos(radians(a.latitude)), 2)
        ) as distance_m
    from vp a
    join vp b
        on a.route_id = b.route_id
        and a.polled_at = b.polled_at
        and a.vehicle_id < b.vehicle_id
        and a.trip_id is distinct from b.trip_id
)
select *
from paired
where distance_m < 400
order by polled_at desc

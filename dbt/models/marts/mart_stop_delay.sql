-- One row per (trip, stop) actually visited: the *last* prediction we
-- polled for that stop before the vehicle presumably passed it. GTFS-RT
-- trip updates are predictions, not confirmed arrival events, so this is a
-- deliberate simplification — predictions sharpen as a vehicle approaches a
-- stop, so the last one polled is the closest proxy to what actually
-- happened without cross-referencing vehicle positions stop-by-stop.
with ranked as (
    select
        *,
        row_number() over (
            partition by trip_id, stop_id, stop_sequence
            order by polled_at desc
        ) as rn
    from {{ ref('stg_trip_updates') }}
    where arrival_delay_sec is not null
)
select
    trip_id,
    route_id,
    stop_id,
    stop_sequence,
    arrival_delay_sec,
    departure_delay_sec,
    scheduled_arrival,
    predicted_arrival,
    polled_at as last_polled_at
from ranked
where rn = 1

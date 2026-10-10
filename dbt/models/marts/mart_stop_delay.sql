-- One row per (trip, stop) actually visited: the *last* prediction we
-- polled for that stop before the vehicle presumably passed it. GTFS-RT
-- trip updates are predictions, not confirmed arrival events, so this is a
-- deliberate simplification — predictions sharpen as a vehicle approaches a
-- stop, so the last one polled is the closest proxy to what actually
-- happened without cross-referencing vehicle positions stop-by-stop.
--
-- Built as "latest poll per (trip, stop)" then a join back, not a
-- row_number() over the whole table: ranking ~110M rows spilled ~9GB of sort
-- to disk and ran the database volume out of space. The aggregate only holds
-- one entry per (trip, stop) (~2M) and each lookup uses idx_tu_trip. Same result
-- except where one poll reported a stop twice; ties now go to the later row.
{{ config(pre_hook="set work_mem = '256MB'") }}

with last_poll as (
    select trip_id, stop_id, stop_sequence, max(polled_at) as last_polled_at
    from {{ ref('stg_trip_updates') }}
    where arrival_delay_sec is not null
    group by trip_id, stop_id, stop_sequence
)
select
    tu.trip_id,
    tu.route_id,
    tu.stop_id,
    tu.stop_sequence,
    tu.arrival_delay_sec,
    tu.departure_delay_sec,
    tu.scheduled_arrival,
    tu.predicted_arrival,
    tu.polled_at as last_polled_at
from last_poll lp
-- lateral + limit 1: one index lookup per (trip, stop). A plain join let the
-- planner sort the whole table for a merge join, spilling just as badly.
cross join lateral (
    select *
    from {{ ref('stg_trip_updates') }} t
    where t.trip_id = lp.trip_id
        and t.polled_at = lp.last_polled_at
        and t.stop_id is not distinct from lp.stop_id
        and t.stop_sequence is not distinct from lp.stop_sequence
        and t.arrival_delay_sec is not null
    order by t.id desc
    limit 1
) tu

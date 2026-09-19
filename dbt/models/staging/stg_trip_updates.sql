select
    id,
    polled_at,
    trip_id,
    route_id,
    stop_id,
    stop_sequence,
    arrival_delay_sec,
    departure_delay_sec,
    scheduled_arrival,
    predicted_arrival
from {{ source('raw', 'trip_updates') }}
where trip_id is not null

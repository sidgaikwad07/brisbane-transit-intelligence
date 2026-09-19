select
    id,
    polled_at,
    vehicle_id,
    trip_id,
    route_id,
    latitude,
    longitude,
    bearing,
    speed,
    current_stop_id,
    vehicle_timestamp
from {{ source('raw', 'vehicle_positions') }}
where vehicle_id is not null
  and latitude is not null
  and longitude is not null

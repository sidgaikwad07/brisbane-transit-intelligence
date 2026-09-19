select
    trip_id,
    route_id,
    service_id,
    direction_id,
    shape_id,
    trip_headsign
from {{ source('raw', 'trips') }}

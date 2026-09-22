select
    stop_id,
    stop_name,
    stop_lat,
    stop_lon
from {{ source('raw', 'stops') }}

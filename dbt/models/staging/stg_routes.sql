select
    route_id,
    route_short_name,
    route_long_name,
    route_type,
    case route_type
        when 0 then 'Tram/Light Rail'
        when 2 then 'Rail'
        when 3 then 'Bus'
        when 4 then 'Ferry'
        else 'Other'
    end as mode
from {{ source('raw', 'routes') }}

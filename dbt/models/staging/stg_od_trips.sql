select
    operator,
    month,
    route,
    direction,
    time_grouping,
    (time_grouping = 'Weekend') as is_weekend,
    ticket_type,
    nullif(origin_stop, '') as origin_stop,
    nullif(destination_stop, '') as destination_stop,
    quantity
from {{ source('raw', 'od_trips') }}
where quantity is not null

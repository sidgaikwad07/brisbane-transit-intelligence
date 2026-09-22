select
    time_grouping,
    is_weekend,
    sum(quantity) as total_trips,
    count(distinct month) as n_months
from {{ ref('stg_od_trips') }}
group by time_grouping, is_weekend
order by total_trips desc

select
    od.route,
    r.route_long_name,
    r.mode,
    sum(od.quantity) as total_trips,
    sum(case when od.is_weekend then od.quantity else 0 end) as weekend_trips,
    sum(case when not od.is_weekend then od.quantity else 0 end) as weekday_trips,
    count(distinct od.month) as n_months
from {{ ref('stg_od_trips') }} od
left join {{ ref('stg_routes_by_short_name') }} r on r.route_short_name = od.route
group by od.route, r.route_long_name, r.mode
order by total_trips desc

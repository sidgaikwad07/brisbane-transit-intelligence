-- The OD dataset reports heavy rail and the Gold Coast light rail as one
-- network-wide bucket each ("Rail", "GCLR") rather than per line, so neither
-- matches a GTFS route_short_name. They're classified explicitly here, and
-- flagged, so they keep their mode instead of falling out as unmapped.
-- Joins to per-route schedules still won't match them (correctly: they're a
-- whole network, not a route); see priority_routes.mode_aggregate_rows().
select
    od.route,
    case
        when od.route = 'Rail' then 'All rail lines combined'
        when od.route = 'GCLR' then 'Gold Coast light rail (all stops)'
        else r.route_long_name
    end as route_long_name,
    case
        when od.route = 'Rail' then 'Rail'
        when od.route = 'GCLR' then 'Tram/Light Rail'
        else r.mode
    end as mode,
    (od.route in ('Rail', 'GCLR')) as is_network_aggregate,
    sum(od.quantity) as total_trips,
    sum(case when od.is_weekend then od.quantity else 0 end) as weekend_trips,
    sum(case when not od.is_weekend then od.quantity else 0 end) as weekday_trips,
    count(distinct od.month) as n_months
from {{ ref('stg_od_trips') }} od
left join {{ ref('stg_routes_by_short_name') }} r on r.route_short_name = od.route
group by 1, 2, 3, 4
order by total_trips desc

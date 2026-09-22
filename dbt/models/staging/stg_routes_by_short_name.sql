-- The OD trips dataset identifies routes by their short display code (e.g.
-- "60", "F50") only, not by GTFS route_id — and route_short_name isn't
-- unique in the static feed (the same route number republished across
-- timetable-version-specific route_id rows). One representative row per
-- short name, for display/mode lookup when joining to OD demand.
select distinct on (route_short_name)
    route_short_name,
    route_long_name,
    mode
from {{ ref('stg_routes') }}
where route_short_name is not null
order by route_short_name, route_long_name

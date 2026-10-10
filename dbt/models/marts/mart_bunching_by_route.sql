-- One row per route number, not per timetable version (see
-- macros/route_short_name.sql).
select
    min(be.route_id) as route_id,
    r.route_short_name,
    r.route_long_name,
    count(*) as bunching_observations,
    count(distinct be.polled_at) as distinct_polls_bunched,
    min(be.polled_at) as first_seen,
    max(be.polled_at) as last_seen
from {{ ref('mart_bunching_events') }} be
join {{ ref('stg_routes_by_short_name') }} r on r.route_short_name = {{ route_short_name('be.route_id') }}
group by r.route_short_name, r.route_long_name
order by bunching_observations desc

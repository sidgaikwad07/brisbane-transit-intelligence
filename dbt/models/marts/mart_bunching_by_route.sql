select
    be.route_id,
    r.route_short_name,
    r.route_long_name,
    count(*) as bunching_observations,
    count(distinct be.polled_at) as distinct_polls_bunched,
    min(be.polled_at) as first_seen,
    max(be.polled_at) as last_seen
from {{ ref('mart_bunching_events') }} be
join {{ ref('stg_routes') }} r on r.route_id = be.route_id
group by be.route_id, r.route_short_name, r.route_long_name
order by bunching_observations desc

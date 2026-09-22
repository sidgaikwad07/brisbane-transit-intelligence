-- Busiest origin-destination stop pairs, all routes/operators combined.
-- Excludes same-stop pairs (origin = destination, ~3.5% of all trips) —
-- these cluster heavily at major interchange stations and most likely
-- represent loop/re-entry journeys (fare-capping behaviour, a short trip
-- and return within one tap-off/tap-on window) rather than point-to-point
-- travel, so they'd dominate this ranking without answering "where are
-- people actually going."
--
-- Not every OD stop id resolves against the current static feed (some are
-- from stops renumbered/retired since the OD data's earliest coverage) —
-- left join keeps the pair with a null name rather than dropping it.
with pairs as (
    select
        origin_stop,
        destination_stop,
        sum(quantity) as total_trips,
        count(distinct month) as n_months
    from {{ ref('stg_od_trips') }}
    where origin_stop is not null and destination_stop is not null and origin_stop != destination_stop
    group by origin_stop, destination_stop
)
select
    p.origin_stop,
    o.stop_name as origin_stop_name,
    p.destination_stop,
    d.stop_name as destination_stop_name,
    p.total_trips,
    p.n_months
from pairs p
left join {{ ref('stg_stops') }} o on o.stop_id = p.origin_stop
left join {{ ref('stg_stops') }} d on d.stop_id = p.destination_stop
order by p.total_trips desc
limit 500

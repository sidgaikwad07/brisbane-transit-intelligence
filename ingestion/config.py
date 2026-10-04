import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://transit:transit@localhost:5432/brisbane_transit"
)

# Translink open data — public, no auth required.
# https://translink.com.au/about-translink/open-data/gtfs-rt
# https://www.data.qld.gov.au/dataset/general-transit-feed-specification-gtfs-translink
GTFS_STATIC_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"
GTFS_RT_TRIP_UPDATES_URL = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/TripUpdates"
GTFS_RT_VEHICLE_POSITIONS_URL = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions"
GTFS_RT_ALERTS_URL = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/alerts"

# Brisbane City Council open data (Opendatasoft platform)
# https://data.brisbane.qld.gov.au/explore/dataset/traffic-data-at-intersection/
# Bulk export of the dataset: every matching record in ONE request.
# Anonymous users get 5,000 API calls/day (resets 00:00 UTC); paging the
# records endpoint 100 at a time cost ~150 calls per poll and exhausted the
# quota within hours every day. One export call per poll = 720 calls/day.
BCC_TRAFFIC_EXPORT_URL = (
    "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
    "traffic-data-at-intersection/exports/json"
)

# Static reference data — traffic signal controller (tsc) site locations.
# raw.intersection_traffic has no lat/lon of its own; this is what makes a
# spatial join to it possible. Signals don't move, so this is pulled once,
# not polled.
BCC_SIGNAL_LOCATIONS_API_URL = (
    "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
    "traffic-management-signal-locations/records"
)

# Queensland Government open data (CKAN) — monthly aggregated go card/EMV/
# paper-ticket origin-destination trip counts, Jan 2022 onwards.
# https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards
OD_TRIPS_CKAN_PACKAGE_URL = (
    "https://www.data.qld.gov.au/api/3/action/package_show"
    "?id=translink-origin-destination-trips-2022-onwards"
)

# Open-Meteo (free, no auth). Archive endpoint has daily history back to
# 1940; forecast endpoint carries the last ~3 months + upcoming forecast —
# used to catch today, which the archive endpoint lags a day or two behind.
WEATHER_ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"
BRISBANE_LAT = -27.4698
BRISBANE_LON = 153.0251

RAW_DATA_DIR = "data/raw"

# ── Multi-city comparison (added 2026-09-29) ──────────────────────────────
# Sydney and Melbourne's static GTFS is freely downloadable, no API key.
# Their GTFS-Realtime feeds DO require a free self-registered API key
# (Transport for NSW / Transport Victoria open data portals) that this
# project can't obtain on its own — live reliability/headway comparison is
# blocked on that until a key is supplied. See ROADMAP.md.
SYDNEY_GTFS_STATIC_URL = (
    "https://opendata.transport.nsw.gov.au/data/dataset/d1f68d4f-b778-44df-9823-cf2fa922e47f/"
    "resource/67974f14-01bf-47b7-bfa5-c7f2f8a950ca/download/full_greater_sydney_gtfs_static_0.zip"
)
MELBOURNE_GTFS_STATIC_URL = (
    "https://opendata.transport.vic.gov.au/dataset/3f4e292e-7f8a-4ffe-831f-1953be0fe448/"
    "resource/fb152201-859f-4882-9206-b768060b50ad/download/gtfs.zip"
)

# ── ABS reference geography + population (added 2026-10-01) ──────────────
# Used to put all three cities on the same footing: clip each feed to its
# official Greater Capital City boundary (GCCSA), weigh service against
# where people actually live (Australian Population Grid, 1km cells,
# ERP at 30 June 2025), and name the gaps (SA2 boundaries). All CC BY 4.0.
ABS_ASGS_BASE_URL = (
    "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/"
    "jul2021-jun2026/access-and-downloads/digital-boundary-files"
)
ABS_GCCSA_URL = f"{ABS_ASGS_BASE_URL}/GCCSA_2021_AUST_SHP_GDA2020.zip"
ABS_SA2_URL = f"{ABS_ASGS_BASE_URL}/SA2_2021_AUST_SHP_GDA2020.zip"
ABS_POPULATION_GRID_URL = (
    "https://www.abs.gov.au/statistics/people/population/regional-population/2024-25/GEOTIFF.zip"
)

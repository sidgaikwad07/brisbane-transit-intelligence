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
BCC_TRAFFIC_API_URL = (
    "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
    "traffic-data-at-intersection/records"
)

# Queensland Government open data (CKAN) — monthly aggregated go card/EMV/
# paper-ticket origin-destination trip counts, Jan 2022 onwards.
# https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards
OD_TRIPS_CKAN_PACKAGE_URL = (
    "https://www.data.qld.gov.au/api/3/action/package_show"
    "?id=translink-origin-destination-trips-2022-onwards"
)

RAW_DATA_DIR = "data/raw"

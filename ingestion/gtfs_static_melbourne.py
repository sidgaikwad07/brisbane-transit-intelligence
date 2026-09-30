"""Load Melbourne's static GTFS feed (Transport Victoria) into raw_mel, for
the cross-city comparison — see docs/city_comparison.md once it exists,
and ROADMAP.md for what's blocked pending a GTFS-RT API key.

Freely downloadable, no API key. Structurally different from Brisbane/
Sydney: Melbourne's feed is a *zip of zips*, one nested google_transit.zip
per mode/operator, numbered folders identified by inspecting each one's
routes.txt route_type (not documented anywhere obvious, so recorded here):

    1  = V/Line regional trains       (route_type 2)
    2  = Metro trains                 (route_type 400 — extended GTFS code)
    3  = Trams                        (route_type 0)
    4  = Metropolitan buses           (route_type 3)
    5  = V/Line regional coach        (route_type 204)
    6  = Regional town bus            (route_type 701)
    10 = Interstate rail (Overland)   (route_type 102)
    11 = SkyBus (airport shuttle)     (route_type 3)

Scoped to metro Melbourne only (2, 3, 4) — matching what "PTV Melbourne"
conventionally means and keeping the comparison fair against Brisbane's
SEQ / Sydney's Greater Sydney (both bounded to their metro region, not
interstate) — folders 1/5/6/10 (regional/interstate V/Line, Overland) and
11 (SkyBus, a private premium airport service, not part of the core
network) are deliberately excluded. Revisit this scope if the comparison
later wants regional Victoria too.

Skips `shapes` for the same reason as gtfs_static_sydney.py: route-line
geometry isn't needed for the numeric comparison and is a large fraction
of the download.

Run scripts/setup_city_schema.py raw_mel first.

Usage:
    python -m ingestion.gtfs_static_melbourne
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL, MELBOURNE_GTFS_STATIC_URL, RAW_DATA_DIR
from ingestion.gtfs_static import load_table, log, populate_stop_geometry

SCHEMA = "raw_mel"
EXTRACT_DIR = Path(RAW_DATA_DIR) / "gtfs_static_melbourne"
METRO_FOLDERS = {"2": "Metro trains", "3": "Trams", "4": "Metro buses"}
REQUEST_TIMEOUT_SEC = 180


def _namespace_ids(extract_dir: Path, folder: str) -> None:
    """agency_id and calendar's service_id are short, generic, reused codes
    across Melbourne's per-mode sub-feeds ("1", "T2", ...) — confirmed by
    inspection, unlike route_id/trip_id/stop_id which are already uniquely
    namespaced (or, for stop_id, a genuinely shared statewide numbering
    scheme where collision is real, not a bug). Prefixed here, in place, so
    appending each sub-feed after the first doesn't hit a primary-key
    collision or silently overwrite one mode's calendar with another's.
    """
    prefix = f"mel{folder}_"
    for fname, cols in [
        ("agency.txt", ["agency_id"]),
        ("routes.txt", ["agency_id"]),
        ("calendar.txt", ["service_id"]),
        ("calendar_dates.txt", ["service_id"]),
        ("trips.txt", ["service_id"]),
    ]:
        path = extract_dir / fname
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str)
        for col in cols:
            if col in df.columns:
                df[col] = prefix + df[col]
        df.to_csv(path, index=False)


def download_and_extract_metro_folders() -> dict[str, Path]:
    log.info("Downloading Melbourne GTFS (all modes, ~275MB) from %s", MELBOURNE_GTFS_STATIC_URL)
    resp = requests.get(MELBOURNE_GTFS_STATIC_URL, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    outer = zipfile.ZipFile(io.BytesIO(resp.content))

    extracted: dict[str, Path] = {}
    for folder, label in METRO_FOLDERS.items():
        nested_bytes = outer.read(f"{folder}/google_transit.zip")
        target = EXTRACT_DIR / folder
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
            nested.extractall(target)
        _namespace_ids(target, folder)
        extracted[folder] = target
        log.info("Extracted folder %s (%s) to %s", folder, label, target)
    return extracted


def main() -> None:
    start = time.time()
    extracted = download_and_extract_metro_folders()
    engine = create_engine(DATABASE_URL)

    tables = ["agency", "routes", "stops", "calendar", "calendar_dates", "trips"]
    for i, (folder, extract_dir) in enumerate(extracted.items()):
        truncate = i == 0  # only the first sub-feed truncates; the rest append
        for table in tables:
            load_table(engine, extract_dir, table, schema=SCHEMA, truncate=truncate)
        load_table(engine, extract_dir, "stop_times", chunksize=200_000, schema=SCHEMA, truncate=truncate)

    populate_stop_geometry(engine, schema=SCHEMA)
    log.info("Melbourne GTFS static load complete in %.1fs", time.time() - start)


if __name__ == "__main__":
    main()

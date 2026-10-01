"""One-time download of ABS reference data for the cross-city service
comparison (notebooks/city_service_quality.py):

- GCCSA boundaries — Greater Sydney / Melbourne / Brisbane as the ABS
  defines them, so each city's GTFS feed is clipped to the same kind of
  boundary instead of whatever scope its publisher happened to choose
  (Sydney's feed is statewide, Brisbane's covers all of SEQ).
- SA2 boundaries — to name the places where coverage gaps fall.
- Australian Population Grid 2025 — 1km cells, ERP at 30 June 2025 — so
  coverage can be measured as "share of residents", not "share of stops".

Files only, no database tables: these are read directly by geopandas /
rasterio. Safe to re-run; skips files already on disk.

Usage:
    python -m ingestion.abs_reference
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import requests

from ingestion.config import ABS_GCCSA_URL, ABS_POPULATION_GRID_URL, ABS_SA2_URL, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ABS_DIR = Path(RAW_DATA_DIR) / "abs"
DOWNLOADS = {
    "gccsa": ABS_GCCSA_URL,
    "sa2": ABS_SA2_URL,
    "population_grid": ABS_POPULATION_GRID_URL,
}


def download_and_extract(name: str, url: str) -> Path:
    out_dir = ABS_DIR / name
    if out_dir.exists() and any(out_dir.iterdir()):
        log.info("%s already present at %s, skipping", name, out_dir)
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = ABS_DIR / f"{name}.zip"
    log.info("Downloading %s from %s", name, url)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
    zip_path.unlink()
    log.info("Extracted %s to %s", name, out_dir)
    return out_dir


def main() -> None:
    for name, url in DOWNLOADS.items():
        download_and_extract(name, url)


if __name__ == "__main__":
    main()

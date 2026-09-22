"""Download Queensland Government's monthly aggregated TransLink
origin-destination trip data and load it into Postgres.

Source: https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards
Already aggregated by TransLink (one row per operator/month/route/direction/
time-of-day-band/ticket-type/origin-stop/destination-stop, with a trip
`quantity` count) — not individual smart-card taps. See the dataset's own
"Open Data - Readme.pdf" for the exact field definitions.

Usage:
    python -m ingestion.od_trips              # loads the 3 most recent months
    python -m ingestion.od_trips --months 6    # loads the 6 most recent months
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import zipfile
from datetime import date

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from ingestion.config import DATABASE_URL, OD_TRIPS_CKAN_PACKAGE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 120

CSV_TO_DB_COLUMNS = {
    "OPERATOR": "operator",
    "MONTH": "month",
    "ROUTE": "route",
    "DIRECTION": "direction",
    "TIME_GROUPING": "time_grouping",
    "TICKET_TYPE": "ticket_type",
    "ORIGIN_STOP": "origin_stop",
    "DESTINATION_STOP": "destination_stop",
    "QUANTITY": "quantity",
}

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_RESOURCE_NAME_RE = re.compile(r"^(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\s*-\s*Translink", re.IGNORECASE)


def list_monthly_resources(n: int) -> list[dict]:
    """The `n` most recent monthly ZIP resources, newest first."""
    resp = requests.get(OD_TRIPS_CKAN_PACKAGE_URL, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]

    dated = []
    for r in resources:
        if (r.get("format") or "").upper() != "ZIP":
            continue
        m = _RESOURCE_NAME_RE.match(r.get("name", ""))
        if not m:
            continue
        month_num = _MONTH_NAMES.get(m.group("month").lower())
        if month_num is None:
            continue
        dated.append((date(int(m.group("year")), month_num, 1), r))

    dated.sort(key=lambda t: t[0], reverse=True)
    return [{"month": d, "url": r["url"], "name": r["name"]} for d, r in dated[:n]]


def download_month_df(resource: dict) -> pd.DataFrame:
    log.info("Downloading %s", resource["name"])
    resp = requests.get(resource["url"], timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, dtype=str)
    df = df.rename(columns=CSV_TO_DB_COLUMNS)[list(CSV_TO_DB_COLUMNS.values())]
    df["month"] = resource["month"]
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    return df


def load_month(engine, resource: dict) -> int:
    df = download_month_df(resource)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw.od_trips WHERE month = :m"), {"m": resource["month"]})
    df.to_sql("od_trips", engine, schema="raw", if_exists="append", index=False, method="multi", chunksize=5000)
    log.info("Loaded %s rows for %s", len(df), resource["month"])
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=3, help="Number of most recent months to load")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    resources = list_monthly_resources(args.months)
    log.info("Found %d monthly resources to load: %s", len(resources), [r["name"] for r in resources])

    total = 0
    for resource in resources:
        total += load_month(engine, resource)
    log.info("Done — %d total OD trip rows loaded across %d months", total, len(resources))


if __name__ == "__main__":
    main()

"""Week 1 deliverable: summarize the Brisbane transit network from the loaded
GTFS static data, and produce a weekday stop-frequency map.

"Weekday" is approximated as any service_id active on Monday
(raw.calendar.monday = true). This ignores calendar_dates exceptions
(public holidays, one-off changes) — a fine simplification for a network
overview, but not for anything measuring a specific date's actual service.

Usage:
    python notebooks/network_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

IMAGE_PATH = REPO_ROOT / "docs" / "images" / "stop_frequency_map.png"
FINDINGS_PATH = REPO_ROOT / "docs" / "week1_findings.md"

WEEKDAY_STOP_TRIPS_SQL = """
    SELECT
        s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        count(DISTINCT st.trip_id) AS weekday_trips,
        count(DISTINCT t.route_id) AS n_routes
    FROM raw.stop_times st
    JOIN raw.trips t ON t.trip_id = st.trip_id
    JOIN raw.calendar c ON c.service_id = t.service_id
    JOIN raw.stops s ON s.stop_id = st.stop_id
    WHERE c.monday = true
    GROUP BY s.stop_id, s.stop_name, s.stop_lat, s.stop_lon
"""

WEEKDAY_ROUTE_TRIPS_SQL = """
    SELECT
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        r.route_type,
        count(DISTINCT t.trip_id) AS weekday_trips
    FROM raw.trips t
    JOIN raw.routes r ON r.route_id = t.route_id
    JOIN raw.calendar c ON c.service_id = t.service_id
    WHERE c.monday = true
    GROUP BY r.route_id, r.route_short_name, r.route_long_name, r.route_type
    ORDER BY weekday_trips DESC
"""

MODE_NAMES = {0: "Tram/Light Rail", 2: "Rail", 3: "Bus", 4: "Ferry"}


def fetch_data(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    stops = pd.read_sql(WEEKDAY_STOP_TRIPS_SQL, engine)
    routes = pd.read_sql(WEEKDAY_ROUTE_TRIPS_SQL, engine)
    return stops, routes


def plot_stop_frequency_map(stops: pd.DataFrame) -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)

    # Log scale for size/color: a handful of major interchanges see orders of
    # magnitude more trips than a typical suburban stop, so a linear scale
    # would just show a few bright dots and nothing else.
    sizes = 3 + (stops["weekday_trips"].clip(lower=1)).apply(lambda x: x**0.5) * 0.6
    scatter = ax.scatter(
        stops["stop_lon"],
        stops["stop_lat"],
        c=stops["weekday_trips"],
        s=sizes,
        cmap="viridis",
        norm=plt.matplotlib.colors.LogNorm(vmin=1, vmax=stops["weekday_trips"].max()),
        alpha=0.7,
        linewidths=0,
    )
    ax.set_title("Brisbane (SEQ) Transit Stops — Weekday Scheduled Trips per Stop")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.7)
    cbar.set_label("Weekday scheduled trips (log scale)")
    fig.tight_layout()
    fig.savefig(IMAGE_PATH)
    plt.close(fig)


def write_findings(stops: pd.DataFrame, routes: pd.DataFrame) -> None:
    top_stops = stops.sort_values("weekday_trips", ascending=False).head(15)
    top_hubs = stops.sort_values("n_routes", ascending=False).head(15)
    top_routes = routes.head(15).copy()
    top_routes["mode"] = top_routes["route_type"].map(MODE_NAMES)

    mode_summary = (
        routes.assign(mode=routes["route_type"].map(MODE_NAMES))
        .groupby("mode")["weekday_trips"]
        .sum()
        .sort_values(ascending=False)
    )

    lines = ["# Week 1 findings — Brisbane transit network overview", ""]
    lines.append(f"- {stops.shape[0]:,} stops with at least one weekday-scheduled trip")
    lines.append(f"- {routes.shape[0]:,} routes running weekday service")
    lines.append(f"- {int(routes['weekday_trips'].sum()):,} total weekday scheduled trips")
    lines.append("")
    lines.append("## Weekday trips by mode")
    lines.append("")
    lines.append("| Mode | Weekday trips |")
    lines.append("|---|---|")
    for mode, n in mode_summary.items():
        lines.append(f"| {mode} | {int(n):,} |")
    lines.append("")
    lines.append("## Busiest stops (by weekday scheduled trips)")
    lines.append("")
    lines.append("| Stop | Weekday trips | Routes served |")
    lines.append("|---|---|---|")
    for _, row in top_stops.iterrows():
        lines.append(f"| {row['stop_name']} | {int(row['weekday_trips']):,} | {int(row['n_routes'])} |")
    lines.append("")
    lines.append("## Biggest interchanges (by distinct routes served)")
    lines.append("")
    lines.append("| Stop | Routes served | Weekday trips |")
    lines.append("|---|---|---|")
    for _, row in top_hubs.iterrows():
        lines.append(f"| {row['stop_name']} | {int(row['n_routes'])} | {int(row['weekday_trips']):,} |")
    lines.append("")
    lines.append("## Highest-frequency routes")
    lines.append("")
    lines.append("| Route | Mode | Weekday trips |")
    lines.append("|---|---|---|")
    for _, row in top_routes.iterrows():
        name = row["route_short_name"] or row["route_long_name"]
        lines.append(f"| {name} | {row['mode']} | {int(row['weekday_trips']):,} |")
    lines.append("")
    lines.append("![Stop frequency map](images/stop_frequency_map.png)")
    lines.append("")

    FINDINGS_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)
    stops, routes = fetch_data(engine)
    print(f"Fetched {len(stops):,} stops and {len(routes):,} routes with weekday service")

    plot_stop_frequency_map(stops)
    print(f"Saved map to {IMAGE_PATH}")

    write_findings(stops, routes)
    print(f"Saved findings to {FINDINGS_PATH}")


if __name__ == "__main__":
    main()

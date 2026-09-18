"""Week 1 deliverable: summarize the Brisbane transit network from the loaded
GTFS static data, and produce a route-shape network map.

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
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

IMAGE_PATH = REPO_ROOT / "docs" / "images" / "network_map.png"
FINDINGS_PATH = REPO_ROOT / "docs" / "week1_findings.md"

SHAPES_SQL = """
    SELECT shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence
    FROM raw.shapes
    ORDER BY shape_id, shape_pt_sequence
"""

SHAPE_MODE_SQL = """
    SELECT DISTINCT t.shape_id, r.route_type
    FROM raw.trips t
    JOIN raw.routes r ON r.route_id = t.route_id
    WHERE t.shape_id IS NOT NULL
"""

MODE_COLORS = {
    "Bus": "#4C72B0",
    "Rail": "#C44E52",
    "Ferry": "#55A868",
    "Tram/Light Rail": "#8172B2",
}

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


def fetch_shapes(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    shapes = pd.read_sql(SHAPES_SQL, engine)
    shape_modes = pd.read_sql(SHAPE_MODE_SQL, engine)
    # A shape_id is occasionally reused across route types in messy real-world
    # feeds; keep the first mode seen per shape rather than dropping/erroring.
    shape_modes = shape_modes.drop_duplicates(subset="shape_id", keep="first")
    return shapes, shape_modes


def plot_network_map(stops: pd.DataFrame, shapes: pd.DataFrame, shape_modes: pd.DataFrame) -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 14), dpi=170)

    mode_by_shape = shape_modes.set_index("shape_id")["route_type"].map(MODE_NAMES)

    # Build one polyline per shape_id (a shape is GTFS's literal road/rail/
    # ferry path a trip follows), grouped so each mode gets its own
    # LineCollection — far faster to render than thousands of ax.plot calls.
    segments_by_mode: dict[str, list] = {mode: [] for mode in MODE_COLORS}
    for shape_id, group in shapes.groupby("shape_id", sort=False):
        mode = mode_by_shape.get(shape_id, "Bus")
        if mode not in segments_by_mode:
            continue
        segments_by_mode[mode].append(group[["shape_pt_lon", "shape_pt_lat"]].to_numpy())

    # Draw rail/ferry/tram first (thicker, more saturated) then bus underneath
    # in a muted tone, so the frequent, dense bus network reads as texture
    # rather than drowning out the rapid-transit spine.
    draw_order = ["Bus", "Ferry", "Tram/Light Rail", "Rail"]
    style = {
        "Bus": {"linewidths": 0.35, "alpha": 0.35},
        "Ferry": {"linewidths": 1.1, "alpha": 0.85},
        "Tram/Light Rail": {"linewidths": 1.4, "alpha": 0.9},
        "Rail": {"linewidths": 1.2, "alpha": 0.9},
    }
    for mode in draw_order:
        segs = segments_by_mode.get(mode, [])
        if not segs:
            continue
        lc = LineCollection(segs, colors=MODE_COLORS[mode], **style[mode])
        ax.add_collection(lc)

    # Stops as a light, small-scale backdrop so hub density is still visible
    # without competing with the route lines for attention.
    ax.scatter(
        stops["stop_lon"],
        stops["stop_lat"],
        s=2,
        c="#333333",
        alpha=0.12,
        linewidths=0,
        zorder=1,
    )

    ax.set_title("Brisbane (SEQ) Transit Network — Scheduled Route Shapes by Mode")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    ax.autoscale()

    legend_handles = [
        Line2D([0], [0], color=color, lw=2.5, label=mode) for mode, color in MODE_COLORS.items()
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=True, fontsize=9)

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
    lines.append("![Network map — route shapes by mode](images/network_map.png)")
    lines.append("")

    FINDINGS_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)
    stops, routes = fetch_data(engine)
    print(f"Fetched {len(stops):,} stops and {len(routes):,} routes with weekday service")

    shapes, shape_modes = fetch_shapes(engine)
    print(f"Fetched {shapes['shape_id'].nunique():,} route shapes ({len(shapes):,} points)")

    plot_network_map(stops, shapes, shape_modes)
    print(f"Saved map to {IMAGE_PATH}")

    write_findings(stops, routes)
    print(f"Saved findings to {FINDINGS_PATH}")


if __name__ == "__main__":
    main()

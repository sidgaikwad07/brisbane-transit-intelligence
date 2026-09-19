"""Week 1 deliverable: summarize the Brisbane transit network from the loaded
GTFS static data, and produce a route-shape network map.

"Weekday" is resolved to one concrete representative date (see
ingestion.service_calendar), not a bare `calendar.monday = true` flag. The
naive flag ignores calendar's own start/end date range, so it double- and
triple-counts trips wherever the feed republishes the same service pattern
under several overlapping service_ids (school-term calendar rows, or a
mid-feed timetable correction) — on some corridors that overstated weekday
trips by 5-6x. Resolving one real date fixes it.

The network map deliberately zooms to Greater Brisbane rather than the full
SEQ extent. SEQ's TransLink feed actually covers three separate urban bus
networks strung along one coastline — Brisbane, the Sunshine Coast and the
Gold Coast — so a simple lat/lon percentile trim doesn't isolate Brisbane at
all (the other two cities have plenty of their own high-frequency stops).
Instead we DBSCAN-cluster weekday stops in projected km-space and take the
largest contiguous cluster as the Brisbane metro core, then pad it — this
reliably separates Brisbane from the ~60-90km gaps to the other two cities.
The full extent is kept as a small inset for regional context.

Usage:
    python notebooks/network_summary.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from sklearn.cluster import DBSCAN
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from ingestion.service_calendar import active_service_ids, representative_dates

IMAGE_PATH = REPO_ROOT / "docs" / "images" / "network_map.png"
FINDINGS_PATH = REPO_ROOT / "docs" / "week1_findings.md"

KM_PER_LAT_DEG = 111.32

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
    JOIN raw.stops s ON s.stop_id = st.stop_id
    WHERE t.service_id = ANY(%(service_ids)s)
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
    WHERE t.service_id = ANY(%(service_ids)s)
    GROUP BY r.route_id, r.route_short_name, r.route_long_name, r.route_type
    ORDER BY weekday_trips DESC
"""

TRIPS_PER_SERVICE_SQL = "SELECT service_id, count(*) AS n FROM raw.trips GROUP BY service_id"

MODE_NAMES = {0: "Tram/Light Rail", 2: "Rail", 3: "Bus", 4: "Ferry"}

# Draw order (back to front) and per-mode line style. Rapid-transit modes get
# a white "halo" underneath so they read clearly against the dense bus web.
DRAW_ORDER = ["Bus", "Ferry", "Tram/Light Rail", "Rail"]
LINE_STYLE = {
    "Bus": {"linewidth": 0.4, "alpha": 0.5, "halo": False},
    "Ferry": {"linewidth": 1.5, "alpha": 0.95, "halo": True},
    "Tram/Light Rail": {"linewidth": 1.8, "alpha": 0.95, "halo": True},
    "Rail": {"linewidth": 1.8, "alpha": 0.95, "halo": True},
}

N_HUBS = 8


def pick_weekday_date(engine) -> tuple[object, set[str]]:
    """A single representative weekday date and its active service_ids —
    see ingestion.service_calendar for why this replaces a bare
    `calendar.monday = true` filter.
    """
    calendar = pd.read_sql("SELECT * FROM raw.calendar", engine)
    calendar_dates = pd.read_sql("SELECT * FROM raw.calendar_dates", engine)
    trips_per_service = pd.read_sql(TRIPS_PER_SERVICE_SQL, engine).set_index("service_id")["n"]
    weekday_date = representative_dates(calendar, calendar_dates, trips_per_service)["weekday"]
    service_ids = active_service_ids(calendar, calendar_dates, weekday_date)
    return weekday_date, service_ids


def fetch_data(engine, service_ids: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    params = {"service_ids": list(service_ids)}
    stops = pd.read_sql(WEEKDAY_STOP_TRIPS_SQL, engine, params=params)
    routes = pd.read_sql(WEEKDAY_ROUTE_TRIPS_SQL, engine, params=params)
    return stops, routes


def fetch_shapes(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    shapes = pd.read_sql(SHAPES_SQL, engine)
    shape_modes = pd.read_sql(SHAPE_MODE_SQL, engine)
    # A shape_id is occasionally reused across route types in messy real-world
    # feeds; keep the first mode seen per shape rather than dropping/erroring.
    shape_modes = shape_modes.drop_duplicates(subset="shape_id", keep="first")
    return shapes, shape_modes


def _segments_by_mode(shapes: pd.DataFrame, shape_modes: pd.DataFrame) -> dict[str, list]:
    mode_by_shape = shape_modes.set_index("shape_id")["route_type"].map(MODE_NAMES)
    segments_by_mode: dict[str, list] = {mode: [] for mode in MODE_COLORS}
    for shape_id, group in shapes.groupby("shape_id", sort=False):
        mode = mode_by_shape.get(shape_id, "Bus")
        if mode not in segments_by_mode:
            continue
        segments_by_mode[mode].append(group[["shape_pt_lon", "shape_pt_lat"]].to_numpy())
    return segments_by_mode


def compute_metro_bbox(stops: pd.DataFrame, pad_km: float = 15.0) -> tuple[float, float, float, float]:
    """Greater Brisbane bounding box: the largest contiguous DBSCAN cluster
    of weekday-serving stops (in projected km-space), padded outward.

    SEQ's bus network is really three separate cities' worth of dense local
    service (Brisbane, Sunshine Coast, Gold Coast) strung along one coast, so
    trimming by lat/lon percentile doesn't isolate Brisbane — the other two
    have plenty of their own high-frequency stops. Density-based clustering
    does: at a ~1km neighbourhood radius, Brisbane's suburbs form one
    contiguous mass while the ~60-90km highway gaps to the other two cities
    keep them as separate clusters.
    """
    mean_lat = stops["stop_lat"].mean()
    km_per_lon_deg = KM_PER_LAT_DEG * np.cos(np.radians(mean_lat))
    xy = np.column_stack(
        [stops["stop_lon"] * km_per_lon_deg, stops["stop_lat"] * KM_PER_LAT_DEG]
    )
    labels = DBSCAN(eps=1.0, min_samples=10).fit_predict(xy)
    sizes = pd.Series(labels).value_counts()
    sizes = sizes[sizes.index != -1]
    core = stops[labels == sizes.idxmax()]

    pad_lon = pad_km / km_per_lon_deg
    pad_lat = pad_km / KM_PER_LAT_DEG
    return (
        core["stop_lon"].min() - pad_lon,
        core["stop_lon"].max() + pad_lon,
        core["stop_lat"].min() - pad_lat,
        core["stop_lat"].max() + pad_lat,
    )


def _draw_network(ax, segments_by_mode: dict[str, list], *, halo: bool) -> None:
    for mode in DRAW_ORDER:
        segs = segments_by_mode.get(mode, [])
        if not segs:
            continue
        style = LINE_STYLE[mode]
        if halo and style["halo"]:
            ax.add_collection(
                LineCollection(segs, colors="white", linewidths=style["linewidth"] + 1.4, alpha=0.9, zorder=2)
            )
        ax.add_collection(
            LineCollection(
                segs,
                colors=MODE_COLORS[mode],
                linewidths=style["linewidth"],
                alpha=style["alpha"],
                zorder=3,
            )
        )


def _add_scale_bar(ax, bbox: tuple[float, float, float, float], km: float = 10) -> None:
    lon_min, lon_max, lat_min, lat_max = bbox
    mean_lat = (lat_min + lat_max) / 2
    deg_per_km = 1 / (KM_PER_LAT_DEG * np.cos(np.radians(mean_lat)))
    bar_len = km * deg_per_km
    x0 = lon_min + (lon_max - lon_min) * 0.05
    y0 = lat_min + (lat_max - lat_min) * 0.035
    ax.plot([x0, x0 + bar_len], [y0, y0], color="black", lw=2.2, solid_capstyle="butt", zorder=5)
    ax.text(x0 + bar_len / 2, y0 + (lat_max - lat_min) * 0.014, f"{km} km", ha="center", fontsize=8, zorder=5)

    ax_x = x0 + bar_len * 1.9
    ay0 = y0
    ay1 = y0 + (lat_max - lat_min) * 0.045
    ax.annotate(
        "N",
        xy=(ax_x, ay1),
        xytext=(ax_x, ay0),
        ha="center",
        fontsize=9,
        fontweight="bold",
        arrowprops={"arrowstyle": "-|>", "color": "black", "lw": 1.5},
        zorder=5,
    )


def _pick_hubs(stops: pd.DataFrame, bbox: tuple[float, float, float, float], n: int) -> pd.DataFrame:
    lon_min, lon_max, lat_min, lat_max = bbox
    in_view = stops[stops["stop_lon"].between(lon_min, lon_max) & stops["stop_lat"].between(lat_min, lat_max)]
    # Collapse duplicate platforms of the same interchange (e.g. "Buranda
    # busway, platform 4" and "platform 3") to one labelled point, keyed by
    # the name stripped of its platform suffix.
    in_view = in_view.copy()
    in_view["hub_name"] = in_view["stop_name"].str.replace(
        r",?\s*(platform \d+|stop \d+[a-z]?)$", "", regex=True, case=False
    )
    grouped = (
        in_view.sort_values("n_routes", ascending=False)
        .groupby("hub_name", as_index=False)
        .first()
    )
    return grouped.sort_values("n_routes", ascending=False).head(n).reset_index(drop=True)


def _add_hub_markers(ax, hubs: pd.DataFrame) -> None:
    for i, row in hubs.iterrows():
        ax.scatter(
            row["stop_lon"], row["stop_lat"], s=130, c="white", edgecolors="black", linewidths=1.1, zorder=8
        )
        ax.annotate(
            str(i + 1),
            xy=(row["stop_lon"], row["stop_lat"]),
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            zorder=9,
        )


def _add_info_panel(ax, hubs: pd.DataFrame) -> None:
    lines = ["Busiest interchanges (by routes served)", ""]
    for i, row in hubs.iterrows():
        lines.append(f"{i + 1}.  {row['hub_name']} — {int(row['n_routes'])} routes")
    ax.text(
        0.015,
        0.985,
        "\n".join(lines),
        transform=ax.transAxes,
        fontsize=8.3,
        va="top",
        ha="left",
        zorder=10,
        bbox={"boxstyle": "round,pad=0.5", "fc": "white", "ec": "#999999", "lw": 0.7, "alpha": 0.94},
        family="monospace",
    )


def _add_mode_legend(ax) -> None:
    legend_handles = [Line2D([0], [0], color=color, lw=3, label=mode) for mode, color in MODE_COLORS.items()]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        frameon=True,
        fontsize=9.5,
        title="Mode",
        title_fontsize=9.5,
        borderpad=0.7,
    )


def _add_inset(fig, main_ax_pos, main_bbox: tuple[float, float, float, float], segments_by_mode: dict[str, list]) -> None:
    w, h = 0.24, 0.20
    x0 = main_ax_pos.x1 - w - 0.012
    y0 = main_ax_pos.y1 - h - 0.012
    inset = fig.add_axes([x0, y0, w, h])
    inset.set_facecolor("#f7f7f7")
    for mode in DRAW_ORDER:
        segs = segments_by_mode.get(mode, [])
        if not segs:
            continue
        inset.add_collection(LineCollection(segs, colors=MODE_COLORS[mode], linewidths=0.5, alpha=0.85))
    inset.autoscale()
    lon_min, lon_max, lat_min, lat_max = main_bbox
    inset.add_patch(
        Rectangle(
            (lon_min, lat_min),
            lon_max - lon_min,
            lat_max - lat_min,
            fill=False,
            edgecolor="black",
            linewidth=1.1,
            zorder=5,
        )
    )
    ymin, ymax = inset.get_ylim()
    xmin, xmax = inset.get_xlim()
    inset.text(
        xmin + (xmax - xmin) * 0.06,
        ymin + (ymax - ymin) * 0.05,
        "Full SEQ network\n(~230km,\nGympie North–Gold Coast)",
        fontsize=6.3,
        va="bottom",
        color="#444444",
    )
    inset.set_aspect(1 / np.cos(np.radians((lat_min + lat_max) / 2)))
    inset.set_xticks([])
    inset.set_yticks([])
    for spine in inset.spines.values():
        spine.set_edgecolor("#999999")
        spine.set_linewidth(0.8)


def plot_network_map(
    stops: pd.DataFrame,
    shapes: pd.DataFrame,
    shape_modes: pd.DataFrame,
    routes: pd.DataFrame,
    weekday_date,
) -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

    segments_by_mode = _segments_by_mode(shapes, shape_modes)
    bbox = compute_metro_bbox(stops)
    lon_min, lon_max, lat_min, lat_max = bbox
    mean_lat = (lat_min + lat_max) / 2

    fig = plt.figure(figsize=(12.5, 14), dpi=200)
    fig.patch.set_facecolor("white")
    # Generous box leaving room above/below for title and caption; the real
    # plotted rectangle (pos, below) will be smaller once equal-aspect shrinks
    # it to fit the data's true width:height ratio.
    ax = fig.add_axes([0.04, 0.045, 0.92, 0.86])

    _draw_network(ax, segments_by_mode, halo=True)

    in_view = stops[stops["stop_lon"].between(lon_min, lon_max) & stops["stop_lat"].between(lat_min, lat_max)]
    ax.scatter(in_view["stop_lon"], in_view["stop_lat"], s=2.5, c="#333333", alpha=0.15, linewidths=0, zorder=1)

    hubs = _pick_hubs(stops, bbox, N_HUBS)
    _add_hub_markers(ax, hubs)

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(1 / np.cos(np.radians(mean_lat)), adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    _add_scale_bar(ax, bbox)
    _add_mode_legend(ax)
    _add_info_panel(ax, hubs)

    # Equal-aspect shrinks `ax` to fit inside the rect we gave it — force a
    # layout pass and read back where it actually landed before placing
    # anything relative to it, instead of guessing.
    fig.canvas.draw()
    pos = ax.get_position()

    total_trips = int(routes["weekday_trips"].sum())
    fig.text(
        pos.x0,
        pos.y1 + 0.05,
        "Brisbane Public Transport Network",
        fontsize=19,
        fontweight="bold",
        ha="left",
        va="bottom",
    )
    fig.text(
        pos.x0,
        pos.y1 + 0.017,
        f"{weekday_date:%a %d %b %Y} (typical weekday)  —  {stops.shape[0]:,} stops · "
        f"{routes.shape[0]:,} routes · {total_trips:,} trips",
        fontsize=11,
        color="#333333",
        ha="left",
        va="bottom",
    )

    _add_inset(fig, pos, bbox, segments_by_mode)

    fig.text(
        pos.x0,
        pos.y0 - 0.018,
        f"Source: Translink GTFS static feed · generated "
        f"{datetime.now(tz=timezone.utc):%Y-%m-%d}",
        fontsize=8,
        color="#888888",
        ha="left",
        va="top",
    )

    fig.savefig(IMAGE_PATH, facecolor="white")
    plt.close(fig)


def write_findings(stops: pd.DataFrame, routes: pd.DataFrame, weekday_date) -> None:
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
    lines.append(
        f"Figures reflect scheduled service on **{weekday_date:%A, %d %B %Y}**, picked as a "
        "typical weekday (see `ingestion/service_calendar.py`): the date, among all "
        "Tuesday/Wednesday/Thursday dates in the feed, whose total scheduled-trip count is "
        "closest to the median — not just any date with `calendar.monday = true`, which "
        "double-counts wherever the feed republishes a service under overlapping calendar "
        "windows (school terms, mid-feed corrections)."
    )
    lines.append("")
    lines.append(f"- {stops.shape[0]:,} stops with at least one scheduled trip that day")
    lines.append(f"- {routes.shape[0]:,} routes running that day")
    lines.append(f"- {int(routes['weekday_trips'].sum()):,} total scheduled trips")
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
    lines.append(
        "![Brisbane transit network map — weekday route shapes by mode, zoomed to Greater "
        "Brisbane, with the busiest interchanges numbered and a full-SEQ inset for regional "
        "context](images/network_map.png)"
    )
    lines.append("")

    FINDINGS_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)

    weekday_date, service_ids = pick_weekday_date(engine)
    print(f"Representative weekday: {weekday_date:%A, %d %b %Y} ({len(service_ids)} active service_ids)")

    stops, routes = fetch_data(engine, service_ids)
    print(f"Fetched {len(stops):,} stops and {len(routes):,} routes with service that day")

    shapes, shape_modes = fetch_shapes(engine)
    print(f"Fetched {shapes['shape_id'].nunique():,} route shapes ({len(shapes):,} points)")

    plot_network_map(stops, shapes, shape_modes, routes, weekday_date)
    print(f"Saved map to {IMAGE_PATH}")

    write_findings(stops, routes, weekday_date)
    print(f"Saved findings to {FINDINGS_PATH}")


if __name__ == "__main__":
    main()

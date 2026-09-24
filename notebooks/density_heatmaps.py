"""Three spatial density heatmaps for Greater Brisbane, side by side: where
the network *provides* service, where people *actually* board (real
ridership), and where vehicles *bunch* — the supply/demand/reliability
triptych every other finding in this repo has been building toward.

Reuses the Greater Brisbane bbox, route-shape context lines, and scale bar
from notebooks/network_summary.py for visual consistency with the main
network map, and the representative-weekday resolution from
ingestion.service_calendar (same method as every other script here).

Usage:
    python notebooks/density_heatmaps.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from network_summary import (
    _add_scale_bar,
    _draw_network,
    _segments_by_mode,
    compute_metro_bbox,
    fetch_data,
    fetch_shapes,
    pick_weekday_date,
)
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

OUT_PATH = REPO_ROOT / "docs" / "images" / "density_heatmaps.png"
REPORT_PATH = REPO_ROOT / "docs" / "density_findings.md"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"

# Sequential ramps: blue for supply (dataviz skill's default sequential hue,
# light->dark per references/palette.md), orange for demand (skill's rule:
# "when two sequential contexts appear at once, the second takes the next
# categorical slot's hue"), and a status-style red-orange for bunching
# (a reliability *problem* density, closer to a status/warning signal than
# a neutral magnitude).
BLUE_RAMP = LinearSegmentedColormap.from_list(
    "blue_seq", ["#f5f9fe", "#cde2fb", "#6da7ec", "#2a78d6", "#184f95"]
)
ORANGE_RAMP = LinearSegmentedColormap.from_list(
    "orange_seq", ["#fef3ec", "#fbd2b8", "#f19257", "#eb6834", "#9c3c15"]
)
RED_RAMP = LinearSegmentedColormap.from_list(
    "red_seq", ["#fdeeee", "#f6c3c2", "#e77c7a", "#d03b3b", "#7e1f1f"]
)

GRIDSIZE = 55


def fetch_supply(engine) -> tuple[pd.DataFrame, object]:
    weekday_date, service_ids = pick_weekday_date(engine)
    stops, _routes = fetch_data(engine, service_ids)
    return stops, weekday_date


def fetch_demand(engine) -> pd.DataFrame:
    df = pd.read_sql(
        """
        WITH activity AS (
            SELECT origin_stop AS stop_id, quantity FROM raw.od_trips WHERE origin_stop IS NOT NULL
            UNION ALL
            SELECT destination_stop AS stop_id, quantity FROM raw.od_trips WHERE destination_stop IS NOT NULL
        )
        SELECT a.stop_id, s.stop_lat, s.stop_lon, sum(a.quantity) AS trips
        FROM activity a
        JOIN raw.stops s ON s.stop_id = a.stop_id
        GROUP BY a.stop_id, s.stop_lat, s.stop_lon
        """,
        engine,
    )
    return df


def fetch_bunching(engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT lat_a AS lat, lon_a AS lon FROM marts.mart_bunching_events", engine
    )


def _panel(fig, gs_cell, bbox, segments_by_mode, mean_lat, *, x, y, weights, cmap, title, cbar_label, log_scale):
    ax = fig.add_subplot(gs_cell)
    lon_min, lon_max, lat_min, lat_max = bbox

    _draw_network(ax, segments_by_mode, halo=False)
    for coll in ax.collections:
        coll.set_color("#c7c6c0")
        coll.set_alpha(0.5)
        coll.set_linewidth(0.3)
        coll.set_zorder(1)

    hb = ax.hexbin(
        x, y, C=weights, reduce_C_function=np.sum, gridsize=GRIDSIZE,
        extent=(lon_min, lon_max, lat_min, lat_max), cmap=cmap,
        bins="log" if log_scale else None, mincnt=1, linewidths=0.1, edgecolors="#ffffff20", zorder=3,
    )

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(1 / np.cos(np.radians(mean_lat)))
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=12.5, fontweight="bold", color=INK_PRIMARY, loc="left", pad=8)

    cbar = fig.colorbar(hb, ax=ax, orientation="horizontal", fraction=0.035, pad=0.02, aspect=28)
    cbar.set_label(cbar_label, fontsize=8, color=INK_SECONDARY)
    cbar.ax.tick_params(labelsize=7, colors=INK_MUTED)
    cbar.outline.set_visible(False)

    return ax


def build_heatmaps(stops: pd.DataFrame, demand: pd.DataFrame, bunching: pd.DataFrame, shapes, shape_modes) -> tuple:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bbox = compute_metro_bbox(stops)
    lon_min, lon_max, lat_min, lat_max = bbox
    mean_lat = (lat_min + lat_max) / 2
    segments_by_mode = _segments_by_mode(shapes, shape_modes)

    fig = plt.figure(figsize=(19, 10.5), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(nrows=1, ncols=3, wspace=0.08, left=0.02, right=0.98, top=0.86, bottom=0.06)

    fig.text(0.02, 0.965, "Brisbane transit, three ways", fontsize=22, fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(
        0.02, 0.925,
        "Where the network runs, where people actually go, and where vehicles bunch together — "
        "same geography, three very different pictures",
        fontsize=11.5, color=INK_SECONDARY, va="top",
    )

    _panel(
        fig, gs[0, 0], bbox, segments_by_mode, mean_lat,
        x=stops["stop_lon"], y=stops["stop_lat"], weights=stops["weekday_trips"], cmap=BLUE_RAMP,
        title="Where the network provides service", cbar_label="Scheduled weekday trips (log)", log_scale=True,
    )
    _panel(
        fig, gs[0, 1], bbox, segments_by_mode, mean_lat,
        x=demand["stop_lon"], y=demand["stop_lat"], weights=demand["trips"], cmap=ORANGE_RAMP,
        title="Where people actually board", cbar_label="Real rider trips, 3mo (log)", log_scale=True,
    )
    ax3 = _panel(
        fig, gs[0, 2], bbox, segments_by_mode, mean_lat,
        x=bunching["lon"], y=bunching["lat"], weights=np.ones(len(bunching)), cmap=RED_RAMP,
        title="Where vehicles bunch together", cbar_label="Bunching snapshots (log)", log_scale=True,
    )
    _add_scale_bar(ax3, bbox, km=10)

    fig.text(
        0.02, 0.015,
        "Sources: Translink GTFS static + GTFS-Realtime, Queensland Government open data (CC BY 4.0) · "
        "github.com/sidgaikwad07/brisbane-transit-intelligence",
        fontsize=8, color=INK_MUTED, va="bottom",
    )

    fig.savefig(OUT_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)
    return bbox, mean_lat


def write_report(stops, demand, bunching, weekday_date, bbox) -> None:
    supply_top = stops.sort_values("weekday_trips", ascending=False).head(5)
    demand_top = demand.merge(stops[["stop_id", "stop_name"]], on="stop_id", how="left").sort_values(
        "trips", ascending=False
    ).head(5)

    lines = [
        "# Density findings — supply, demand, and bunching hotspots",
        "",
        (
            "Three spatial views of the same Greater Brisbane geography, generated by "
            "`notebooks/density_heatmaps.py`: scheduled service density (from GTFS static, "
            f"representative weekday {weekday_date:%A, %d %B %Y}), real ridership density (Queensland "
            "Government OD data), and bunching-event density (our own polled GTFS-RT data). Each is "
            "a hexbin heatmap — hexagons sized by geography, colored by summed activity, log-scaled "
            "since transit activity concentrates extremely unevenly (a handful of CBD/busway hexagons "
            "vs. thousands of quiet suburban ones)."
        ),
        "",
        "![Brisbane transit, three ways](images/density_heatmaps.png)",
        "",
        "## Where the network provides service (top 5 by scheduled weekday trips)",
        "",
        "| Stop | Weekday trips |",
        "|---|---|",
    ]
    for _, row in supply_top.iterrows():
        lines.append(f"| {row['stop_name']} | {int(row['weekday_trips']):,} |")

    lines += [
        "",
        "## Where people actually board (top 5 by real ridership)",
        "",
        "| Stop | Rider trips (3mo) |",
        "|---|---|",
    ]
    for _, row in demand_top.iterrows():
        name = row["stop_id"] if pd.isna(row["stop_name"]) else row["stop_name"]
        lines.append(f"| {name} | {int(row['trips']):,} |")

    lines += [
        "",
        f"## Bunching: {len(bunching):,} recorded snapshots",
        "",
        (
            "The bunching map is the most concentrated of the three — it's dominated by whichever "
            "corridors happened to be polled during a bunching event in the collection window "
            "logged in `docs/week2_findings.md`, so treat it as \"where we've caught bunching so "
            "far,\" not an exhaustive map of every bunching-prone corridor (same caveat as "
            "`mart_bunching_events` throughout this repo)."
        ),
        "",
        "## Method & caveats",
        "",
        (
            "- **Hexbin density, not a smoothed KDE** — bin size (`gridsize=55` across the mapped "
            "extent) is a real methodological choice; a finer grid shows more local structure but "
            "gets noisier, a coarser grid smooths real hotspots away."
        ),
        (
            "- **Log color scale on all three panels** — without it, the CBD/busway core would "
            "saturate the top color band and every suburban hexagon would look identically empty. "
            "Log scaling is honest about the magnitude of concentration, but means a 2-step color "
            "difference is a much bigger gap in absolute terms than it looks."
        ),
        (
            "- **Demand density counts a stop once per trip it's an endpoint of** (origin or "
            "destination), not a true footfall/interchange count — a stop that's purely a "
            "pass-through (never an origin or destination) wouldn't register here even if every "
            "route physically passes through it."
        ),
        "- Route-shape context lines are the same Greater Brisbane extent as `docs/images/network_map.png`, for orientation — not part of the density calculation itself.",
        (
            "- A handful of ridership stop_ids show up as their raw id, not a name — same "
            "renumbering-since-2022 caveat as `docs/demand_intelligence_findings.md`. The trip "
            "counts are real; only the display name is missing."
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)

    stops, weekday_date = fetch_supply(engine)
    print(f"Supply: {len(stops):,} stops, weekday {weekday_date}")

    demand = fetch_demand(engine)
    print(f"Demand: {len(demand):,} stops with ridership, {demand['trips'].sum():,.0f} total trip-endpoints")

    bunching = fetch_bunching(engine)
    print(f"Bunching: {len(bunching):,} events")

    shapes, shape_modes = fetch_shapes(engine)

    bbox, _ = build_heatmaps(stops, demand, bunching, shapes, shape_modes)
    print(f"Saved heatmaps to {OUT_PATH} (bbox={bbox})")

    write_report(stops, demand, bunching, weekday_date, bbox)
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()

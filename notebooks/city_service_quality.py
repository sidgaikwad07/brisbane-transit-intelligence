"""Brisbane vs. Sydney vs. Melbourne — like-for-like service quality.

Phase 1 (notebooks/city_comparison.py) compared network *size* using each
feed as published, which isn't like-for-like: Sydney's feed is statewide,
Brisbane's covers all of SEQ, and raw counts say nothing about whether the
service is any good. This answers the question a resident actually cares
about — "is there a bus/train/tram near me, and does it come often?" — the
same way for all three cities:

1. Clip every feed to its ABS Greater Capital City boundary (GCCSA).
2. Count scheduled departures per stop per hour on a representative weekday,
   Saturday and Sunday (ingestion/service_calendar.py, same method as every
   other finding in this repo).
3. Weigh stops against where people live (ABS Australian Population Grid
   2025, 1km cells): share of residents within 400m (~5 min walk) of
   - any stop with service that day,
   - a *frequent* stop: >=4 departures in every hour 07:00-18:59
     ("turn up and go" — a 15-minute or better combined headway all day),
   - an *evening* stop: >=2 departures in every hour 20:00-23:59.
4. Name the biggest gaps: SA2s with the most residents outside walking
   distance of frequent service.

Static schedule only — this is what each network *promises*, not what it
delivers on the street (see ROADMAP.md, City comparison Phase 2).

Usage:
    python -m ingestion.abs_reference   # once, downloads ABS files
    python notebooks/city_service_quality.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
import shapely
from scipy.spatial import cKDTree
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from ingestion.service_calendar import active_service_ids
from notebooks.city_comparison import CITY_COLORS, GRIDLINE, INK_MUTED, INK_PRIMARY, INK_SECONDARY, feed_calendar

ABS_DIR = REPO_ROOT / "data" / "raw" / "abs"
GCCSA_PATH = ABS_DIR / "gccsa" / "GCCSA_2021_AUST_GDA2020.shp"
SA2_PATH = ABS_DIR / "sa2" / "SA2_2021_AUST_GDA2020.shp"
POP_GRID_PATH = ABS_DIR / "population_grid" / "apgr25_1_0_0.tif"
# ABS Regional population 2024-25, Table 1: ERP by SA2, 2001-2025.
SA2_ERP_PATH = ABS_DIR / "erp" / "32180DS0003_2001-25.xlsx"
GROWTH_FROM, GROWTH_TO = 2021, 2025  # since the last Census
RESULTS_PATH = REPO_ROOT / "data" / "exports" / "city_service_quality.csv"
GAPS_PATH = REPO_ROOT / "data" / "exports" / "city_frequent_service_gaps.csv"
REPORT_PATH = REPO_ROOT / "docs" / "city_service_quality.md"
COVERAGE_CHART_PATH = REPO_ROOT / "docs" / "images" / "city_service_coverage.png"
SENSITIVITY_CHART_PATH = REPO_ROOT / "docs" / "images" / "city_frequency_sensitivity.png"
GAP_MAP_PATH = REPO_ROOT / "docs" / "images" / "brisbane_frequent_service_gaps.png"
SURFACE = "#fcfcfb"

# Australian Albers — equal-area metres, and the population grid's own CRS.
METRIC_CRS = "EPSG:3577"
WALK_RADIUS_M = 400

CITIES = {
    "Brisbane": {"schema": "raw", "gccsa": "3GBRI"},
    "Sydney": {"schema": "raw_syd", "gccsa": "1GSYD"},
    "Melbourne": {"schema": "raw_mel", "gccsa": "2GMEL"},
}
# ABS Regional population 2024-25 (released 31 Mar 2026), ERP at 30 June
# 2025 by GCCSA — used to sanity-check the grid total, not in any metric.
ABS_ERP_2025 = {"Brisbane": 2_833_524, "Sydney": 5_638_830, "Melbourne": 5_435_590}

SCHOOL_BUS_ROUTE_TYPE = 712  # Sydney's dedicated school-only routes, see city_comparison.py
DAYTIME_HOURS = range(7, 19)  # 07:00-18:59
EVENING_HOURS = range(20, 24)  # 20:00-23:59
FREQUENT_MIN_PER_HOUR = 4
EVENING_MIN_PER_HOUR = 2
# Robustness check: does the ranking depend on where "frequent" is drawn?
# 2/h = 30-minute, 3/h = 20-minute, 6/h = 10-minute combined headway.
SENSITIVITY_MIN_PER_HOUR = (2, 3, 4, 6)


def stop_hourly_departures(engine, schema: str, service_ids: set[str]) -> pd.DataFrame:
    """Departures per (stop, route, hour) on one service day.

    A trip's final stop is never a departure, but feeds flag that
    inconsistently (Brisbane marks it pickup_type=1, Melbourne mostly
    doesn't), so it's dropped explicitly by stop_sequence for all three,
    as well as any other no-pickup stop. Hours past midnight stay as
    published (25 = 1am the next morning, same service day).
    """
    return pd.read_sql(
        f"""
        WITH active AS (
            SELECT t.trip_id, t.route_id
            FROM {schema}.trips t
            JOIN {schema}.routes r ON r.route_id = t.route_id
            WHERE t.service_id = ANY(%(service_ids)s)
              AND r.route_type <> {SCHOOL_BUS_ROUTE_TYPE}
        ),
        st AS (
            SELECT st.stop_id, a.route_id, st.departure_time, st.stop_sequence, st.pickup_type,
                   max(st.stop_sequence) OVER (PARTITION BY st.trip_id) AS last_seq
            FROM {schema}.stop_times st
            JOIN active a ON a.trip_id = st.trip_id
        )
        SELECT stop_id, route_id, split_part(trim(departure_time), ':', 1)::int AS hour, count(*) AS n
        FROM st
        WHERE stop_sequence < last_seq AND coalesce(pickup_type, 0) <> 1
        GROUP BY 1, 2, 3
        """,
        engine,
        params={"service_ids": list(service_ids)},
    )


def stops_in_boundary(engine, schema: str, boundary) -> gpd.GeoDataFrame:
    """Every stop in the feed that falls inside `boundary`. Filtering to
    stops with service on a given day happens later, per day."""
    stops = pd.read_sql(f"SELECT stop_id, stop_lat, stop_lon FROM {schema}.stops", engine)
    gdf = gpd.GeoDataFrame(
        stops, geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]), crs="EPSG:4326"
    ).to_crs(METRIC_CRS)
    shapely.prepare(boundary)  # GCCSA coastlines are detailed; unprepared this is minutes per city
    return gdf[shapely.contains(boundary, gdf.geometry.values)]


def population_cells(boundary) -> gpd.GeoDataFrame:
    """1km population-grid cells whose centre falls inside `boundary`."""
    with rasterio.open(POP_GRID_PATH) as src:
        data, transform = rasterio.mask.mask(src, [boundary], crop=True, nodata=src.nodata)
        nodata = src.nodata
    pop = data[0]
    rows, cols = np.where((pop != nodata) & (pop > 0))
    xs, ys = rasterio.transform.xy(transform, rows, cols, offset="ul")
    xs, ys = np.asarray(xs), np.asarray(ys)
    res = transform.a
    cells = shapely.box(xs, ys - res, xs + res, ys)
    return gpd.GeoDataFrame({"pop": pop[rows, cols].astype(float)}, geometry=cells, crs=METRIC_CRS)


SAMPLES_PER_SIDE = 10  # 10x10 sample points per 1km cell = 100m spacing


def covered_population(cells: gpd.GeoDataFrame, stops: gpd.GeoDataFrame) -> pd.Series:
    """Residents per cell within WALK_RADIUS_M of any stop in `stops`,
    assuming people are spread evenly within each 1km cell.

    The covered fraction of each cell is estimated from a regular grid of
    sample points (nearest-stop lookup) rather than by unioning thousands
    of 400m circles, which is exact but far too slow at Sydney's scale.
    """
    if stops.empty:
        return pd.Series(0.0, index=cells.index)
    bounds = cells.geometry.bounds
    side = bounds["maxx"].iloc[0] - bounds["minx"].iloc[0]
    offsets = (np.arange(SAMPLES_PER_SIDE) + 0.5) * side / SAMPLES_PER_SIDE
    dx, dy = np.meshgrid(offsets, offsets)
    xs = bounds["minx"].to_numpy()[:, None] + dx.ravel()[None, :]
    ys = bounds["miny"].to_numpy()[:, None] + dy.ravel()[None, :]

    tree = cKDTree(np.column_stack([stops.geometry.x, stops.geometry.y]))
    dist, _ = tree.query(np.column_stack([xs.ravel(), ys.ravel()]), distance_upper_bound=WALK_RADIUS_M)
    frac = (dist <= WALK_RADIUS_M).reshape(xs.shape).mean(axis=1)
    return pd.Series(frac * cells["pop"].to_numpy(), index=cells.index)


def qualifying_stops(hourly: pd.DataFrame, hours: range, min_per_hour: int) -> set[str]:
    per_hour = hourly[hourly["hour"].isin(hours)].groupby(["stop_id", "hour"])["n"].sum().unstack(fill_value=0)
    per_hour = per_hour.reindex(columns=list(hours), fill_value=0)
    return set(per_hour.index[(per_hour >= min_per_hour).all(axis=1)])


def city_service_quality(engine, city: str, cfg: dict, gccsa: gpd.GeoDataFrame, sa2: gpd.GeoDataFrame):
    schema = cfg["schema"]
    boundary = gccsa.loc[gccsa["GCC_CODE21"] == cfg["gccsa"], "geometry"].iloc[0]

    cells = population_cells(boundary)
    cell_sa2 = gpd.sjoin(
        gpd.GeoDataFrame(geometry=cells.centroid, crs=METRIC_CRS),
        sa2[["SA2_CODE21", "SA2_NAME21", "geometry"]],
        how="left",
        predicate="within",
    ).groupby(level=0).first()
    cells["sa2_code"] = cell_sa2["SA2_CODE21"]
    cells["sa2"] = cell_sa2["SA2_NAME21"]
    total_pop = cells["pop"].sum()
    print(f"  grid population in GCCSA: {total_pop:,.0f} (ABS ERP: {ABS_ERP_2025[city]:,})")

    calendar, calendar_dates, dates = feed_calendar(engine, schema)

    row = {"city": city, "population": total_pop, "area_km2": boundary.area / 1e6}
    city_stops = stops_in_boundary(engine, schema, boundary)
    weekday_frequent = None
    for day, date in dates.items():
        print(f"  {day} ({date})...")
        hourly = stop_hourly_departures(engine, schema, active_service_ids(calendar, calendar_dates, date))
        hourly = hourly[hourly["stop_id"].isin(set(city_stops["stop_id"]))]
        stops = city_stops[city_stops["stop_id"].isin(set(hourly["stop_id"]))]

        frequent = stops[stops["stop_id"].isin(qualifying_stops(hourly, DAYTIME_HOURS, FREQUENT_MIN_PER_HOUR))]
        row[f"{day}_date"] = date
        row[f"{day}_departures"] = int(hourly["n"].sum())
        row[f"{day}_frequent_stops"] = len(frequent)
        row[f"{day}_pct_near_frequent"] = covered_population(cells, frequent).sum() / total_pop
        if day == "weekday":
            evening = stops[stops["stop_id"].isin(qualifying_stops(hourly, EVENING_HOURS, EVENING_MIN_PER_HOUR))]
            row["weekday_stops"] = len(stops)
            row["weekday_routes"] = hourly["route_id"].nunique()
            row["weekday_pct_near_any"] = covered_population(cells, stops).sum() / total_pop
            row["weekday_pct_near_evening"] = covered_population(cells, evening).sum() / total_pop
            weekday_frequent = frequent
            for k in SENSITIVITY_MIN_PER_HOUR:
                qualifying = stops[stops["stop_id"].isin(qualifying_stops(hourly, DAYTIME_HOURS, k))]
                row[f"weekday_pct_near_{k}_per_hour"] = covered_population(cells, qualifying).sum() / total_pop

    row["departures_per_resident"] = row["weekday_departures"] / total_pop
    row["sunday_vs_weekday"] = row["sunday_departures"] / row["weekday_departures"]

    # Where are the residents who *don't* have frequent service nearby?
    cells["near_frequent"] = covered_population(cells, weekday_frequent)
    gaps = (
        cells.groupby(["sa2_code", "sa2"])
        .agg(population=("pop", "sum"), near_frequent=("near_frequent", "sum"))
        .assign(without_frequent=lambda d: d["population"] - d["near_frequent"])
        .assign(pct_near_frequent=lambda d: d["near_frequent"] / d["population"])
        .sort_values("without_frequent", ascending=False)
        .reset_index()
        .assign(city=city)
    )
    return row, gaps, cells, weekday_frequent


def sa2_population_growth() -> pd.DataFrame:
    """ERP by SA2 in GROWTH_FROM and GROWTH_TO, from the ABS 2001-2025
    series (header rows 0-5; years run across columns from 2001)."""
    raw = pd.read_excel(SA2_ERP_PATH, sheet_name="Table 1", header=None, skiprows=6)
    first_year_col = 10
    growth = pd.DataFrame(
        {
            "sa2_code": pd.to_numeric(raw[8], errors="coerce").astype("Int64").astype(str),
            f"erp_{GROWTH_FROM}": raw[first_year_col + GROWTH_FROM - 2001],
            f"erp_{GROWTH_TO}": raw[first_year_col + GROWTH_TO - 2001],
        }
    ).dropna()
    growth["growth"] = growth[f"erp_{GROWTH_TO}"] - growth[f"erp_{GROWTH_FROM}"]
    return growth


def new_residents_near_frequent(gaps: pd.DataFrame) -> float:
    """Share of residents added GROWTH_FROM-GROWTH_TO who live within
    walking distance of frequent service — each SA2's growth weighted by
    that SA2's coverage today, counting only SA2s that grew."""
    grew = gaps[gaps["growth"] > 0]
    return (grew["growth"] * grew["pct_near_frequent"]).sum() / grew["growth"].sum()


def style_axis(ax) -> None:
    ax.set_facecolor(SURFACE)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRIDLINE)
    ax.tick_params(colors=INK_MUTED, labelsize=8, length=0)
    ax.set_axisbelow(True)


def plot_coverage(results: pd.DataFrame) -> None:
    """One small panel per measure, one bar per city — each city named on
    its own bar, so identity never rests on colour alone."""
    panels = [
        ("weekday_pct_near_any", "Any stop\nweekday, any frequency"),
        ("weekday_pct_near_frequent", "Frequent stop, weekday\nevery 15 min+, 7am-7pm"),
        ("weekday_pct_near_evening", "Evening stop, weekday\nevery 30 min+, 8pm-midnight"),
        ("saturday_pct_near_frequent", "Frequent stop, Saturday\nevery 15 min+, 7am-7pm"),
        ("sunday_pct_near_frequent", "Frequent stop, Sunday\nevery 15 min+, 7am-7pm"),
    ]
    cities = list(results.index)
    fig, axes = plt.subplots(1, len(panels), figsize=(15, 4.2), dpi=200, sharex=True, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(top=0.7, bottom=0.1, left=0.075, right=0.99, wspace=0.18)
    for ax, (col, title) in zip(axes, panels):
        vals = results[col] * 100
        y = np.arange(len(cities))[::-1]
        ax.barh(y, vals, height=0.5, color=[CITY_COLORS[c] for c in cities], zorder=3)
        for yi, v in zip(y, vals):
            ax.text(v + 2, yi, f"{v:.0f}%", fontsize=9, fontweight="bold", color=INK_PRIMARY, va="center")
        ax.set_title(title, fontsize=9.5, fontweight="bold", color=INK_PRIMARY, loc="left")
        ax.set_xlim(0, 100)
        ax.set_yticks(y)
        ax.set_yticklabels(cities, fontsize=9.5, color=INK_PRIMARY)
        ax.grid(axis="x", color=GRIDLINE, linewidth=1, zorder=0)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xticklabels(["0", "25", "50", "75", "100%"])
        style_axis(ax)
    fig.text(0.01, 0.96, "Share of residents within a 5-minute walk (400m) of...", fontsize=15,
             fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(
        0.01, 0.875,
        "Each city clipped to its ABS Greater Capital City boundary; residents from the ABS 2025 population grid; "
        "service from each city's own published GTFS timetable",
        fontsize=9.5, color=INK_SECONDARY, va="top",
    )
    COVERAGE_CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(COVERAGE_CHART_PATH, facecolor=SURFACE)
    plt.close(fig)


def plot_sensitivity(results: pd.DataFrame) -> None:
    headways = [60 // k for k in SENSITIVITY_MIN_PER_HOUR]  # minutes between departures
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(top=0.8, bottom=0.13, left=0.06, right=0.97)
    for city, row in results.iterrows():
        vals = [row[f"weekday_pct_near_{k}_per_hour"] * 100 for k in SENSITIVITY_MIN_PER_HOUR]
        ax.plot(headways, vals, color=CITY_COLORS[city], linewidth=2, solid_capstyle="round", zorder=3)
        ax.scatter(headways, vals, s=40, color=CITY_COLORS[city], edgecolor=SURFACE, linewidth=2, zorder=4)
        # The x axis runs 30 -> 10 min (inverted), so a label at x > 30 with
        # ha="right" sits to the left of the first point, clear of it.
        ax.text(headways[0] + 1.2, vals[0], f"{city} {vals[0]:.0f}%", fontsize=9, color=INK_PRIMARY,
                va="center", ha="right")
    ax.set_xticks(headways)
    ax.set_xticklabels([f"{h} min" for h in headways])
    ax.set_xlim(40, 8)
    ax.set_ylim(0, 75)
    ax.set_yticks([0, 25, 50, 75])
    ax.set_yticklabels(["0", "25", "50", "75%"])
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_xlabel("Service at least this often, every hour 7am-7pm (weekday)", fontsize=9, color=INK_SECONDARY)
    style_axis(ax)
    fig.text(0.02, 0.96, 'Brisbane trails at every definition of "frequent"', fontsize=14,
             fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(0.02, 0.9, "Share of residents within 400m of a stop served at least this often",
             fontsize=9.5, color=INK_SECONDARY, va="top")
    fig.savefig(SENSITIVITY_CHART_PATH, facecolor=SURFACE)
    plt.close(fig)


def plot_brisbane_gaps(cells: gpd.GeoDataFrame, frequent: gpd.GeoDataFrame, gaps: pd.DataFrame) -> None:
    """Residents per 1km cell who are NOT within walking distance of
    frequent service, plus the frequent stops themselves."""
    cells = cells.assign(without=cells["pop"] - cells["near_frequent"])
    fig, ax = plt.subplots(figsize=(9, 10), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(top=0.9, bottom=0.03, left=0.02, right=0.98)
    shown = cells[cells["pop"] >= 50]
    shown.plot(ax=ax, column="without", cmap="Blues", vmin=0, vmax=shown["without"].quantile(0.98),
               linewidth=0, legend=True,
               legend_kwds={"shrink": 0.4, "label": "Residents per km² without frequent service nearby"})
    frequent.plot(ax=ax, color="#eb6834", markersize=1.2, zorder=3)
    top = gaps.head(8)
    for _, g in top.iterrows():
        c = cells[cells["sa2_code"] == g["sa2_code"]].geometry.union_all().centroid
        ax.annotate(g["sa2"], (c.x, c.y), xytext=(6, 6), textcoords="offset points", fontsize=7.5,
                    color=INK_PRIMARY, fontweight="bold",
                    bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": "none", "alpha": 0.8})
    xmin, ymin, xmax, ymax = cells[cells["pop"] >= 500].total_bounds  # frame the urban area
    pad = 2000
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_axis_off()
    fig.text(0.02, 0.975, "Greater Brisbane: where residents lack frequent service", fontsize=15,
             fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(
        0.02, 0.945,
        "Blue = residents more than 400m from a stop with service every 15 min, 7am-7pm weekdays. "
        "Orange dots = those frequent stops.\nLabelled: the 8 areas (ABS SA2) with the most residents "
        "outside walking distance of frequent service.",
        fontsize=8.5, color=INK_SECONDARY, va="top",
    )
    fig.savefig(GAP_MAP_PATH, facecolor=SURFACE)
    plt.close(fig)


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def write_report(r: pd.DataFrame, gaps: pd.DataFrame) -> None:
    bne, syd, mel = r.loc["Brisbane"], r.loc["Sydney"], r.loc["Melbourne"]
    # Residents Brisbane would need to add near frequent service to match
    # Melbourne's share — a scale for the gap, not a target.
    to_match_mel = (mel["weekday_pct_near_frequent"] - bne["weekday_pct_near_frequent"]) * bne["population"]
    big_gaps = gaps[(gaps["population"] >= 10_000) & (gaps["pct_near_frequent"] < 0.05)]
    big_gap_pop = big_gaps.groupby("city")["population"].sum()
    big_gap_n = big_gaps.groupby("city").size()
    sunday_drop = 1 - r["sunday_pct_near_frequent"] / r["weekday_pct_near_frequent"]
    frequent_of_any = r["weekday_pct_near_frequent"] / r["weekday_pct_near_any"]
    # How Brisbane's growth splits between areas with almost no frequent
    # service and everywhere else, vs how its existing population splits.
    bne_gaps = gaps[gaps["city"] == "Brisbane"]
    unserved = bne_gaps["pct_near_frequent"] < 0.05
    grew = bne_gaps["growth"] > 0
    unserved_growth = bne_gaps.loc[unserved & grew, "growth"].sum()
    unserved_growth_share = unserved_growth / bne_gaps.loc[grew, "growth"].sum()
    unserved_pop_share = bne_gaps.loc[unserved, "population"].sum() / bne_gaps["population"].sum()

    lines = [
        "# Brisbane vs. Sydney vs. Melbourne — service quality where people live",
        "",
        "Phase 1 (`docs/city_comparison.md`) compared how *big* each network is. This compares how "
        "*useful* it is to the people who live there: what share of residents can walk to a stop "
        "(400m, about 5 minutes) that has frequent service. All three cities are measured the same way, "
        "inside the same kind of boundary, from their own published timetables "
        "(`notebooks/city_service_quality.py`).",
        "",
        "![Coverage by measure](images/city_service_coverage.png)",
        "",
        "## Key insights",
        "",
        f"1. **Brisbane's problem is frequency, not reach.** {pct(bne['weekday_pct_near_any'])} of Greater "
        f"Brisbane residents live within 400m of a stop with weekday service — close to Melbourne "
        f"({pct(mel['weekday_pct_near_any'])}). But only **{pct(bne['weekday_pct_near_frequent'])}** live near "
        f"a stop with service every 15 minutes or better all day, against {pct(mel['weekday_pct_near_frequent'])} "
        f"in Melbourne and {pct(syd['weekday_pct_near_frequent'])} in Sydney. Of the residents who have a stop "
        f"nearby, about {frequent_of_any['Brisbane'] * 100:.0f} in 100 have a *frequent* one in Brisbane, "
        f"vs. {frequent_of_any['Melbourne'] * 100:.0f} in Melbourne and {frequent_of_any['Sydney'] * 100:.0f} in "
        f"Sydney. Brisbane spreads its service thinly across many low-frequency routes.",
        f"2. **The gap is about {to_match_mel / 1000:,.0f}K people.** That's how many more Greater Brisbane "
        f"residents would need frequent service within walking distance for Brisbane to match Melbourne's "
        f"share, at today's population.",
        f"3. **Brisbane runs less service per resident.** {bne['departures_per_resident']:.2f} scheduled stop "
        f"departures per resident per weekday, vs {mel['departures_per_resident']:.2f} in Melbourne "
        f"(+{(mel['departures_per_resident'] / bne['departures_per_resident'] - 1) * 100:.0f}%) and "
        f"{syd['departures_per_resident']:.2f} in Sydney "
        f"(+{(syd['departures_per_resident'] / bne['departures_per_resident'] - 1) * 100:.0f}%). Thin "
        f"frequency (insight 1) follows directly from that.",
        f"4. **Evenings are weak.** Only {pct(bne['weekday_pct_near_evening'])} of Brisbane residents "
        f"live near a stop with service at least every 30 minutes from 8pm to midnight, about half of "
        f"Sydney's {pct(syd['weekday_pct_near_evening'])} (Melbourne {pct(mel['weekday_pct_near_evening'])}). "
        f"Most Brisbane residents can't rely on a bus or train home after a late shift without a long walk "
        "or wait.",
        f"5. **Large areas have essentially no frequent service.** "
        f"{big_gap_n.get('Brisbane', 0)} Greater Brisbane areas (ABS SA2s) with 10,000+ residents each have "
        f"under 5% of residents near frequent service — **{big_gap_pop.get('Brisbane', 0) / 1e3:,.0f}K people, "
        f"{big_gap_pop.get('Brisbane', 0) / bne['population'] * 100:.0f}% of the city** "
        f"(Melbourne {big_gap_pop.get('Melbourne', 0) / mel['population'] * 100:.0f}%, Sydney "
        f"{big_gap_pop.get('Sydney', 0) / syd['population'] * 100:.0f}%). The largest are outer suburbs: "
        "see the map and table below.",
        f"6. **Weekends: Brisbane holds up comparatively well, Melbourne doesn't.** Brisbane's frequent "
        f"coverage falls {pct(sunday_drop['Brisbane'])} from weekday to Sunday, about the same as Sydney "
        f"({pct(sunday_drop['Sydney'])}). Melbourne's falls {pct(sunday_drop['Melbourne'])} — its Sunday "
        f"frequent coverage ({pct(mel['sunday_pct_near_frequent'])}) ends up *below* Brisbane's "
        f"({pct(bne['sunday_pct_near_frequent'])}), even though Melbourne runs the most Sunday service relative "
        f"to its weekday ({pct(mel['sunday_vs_weekday'])} of weekday departures, vs Brisbane "
        f"{pct(bne['sunday_vs_weekday'])}). Brisbane cuts more Sunday service overall, but the cuts fall "
        "mostly outside its frequent corridors; Melbourne keeps more service running but at frequencies "
        "below the 15-minute line.",
        f"7. **Half of Brisbane's growth is landing where there's no frequent service.** "
        f"{unserved_growth / 1e3:,.0f}K of the {bne['growth_2021_2025'] / 1e3:,.0f}K people added to growing "
        f"Brisbane areas since 2021 ({pct(unserved_growth_share)}) live in areas where under 5% of residents "
        f"have frequent service nearby, somewhat more than those areas' share of the existing population "
        f"({pct(unserved_pop_share)}). The skew is modest, though: well-served inner areas grew in line "
        f"with their population too, so on average new residents are about as well served as existing ones "
        f"({pct(bne['new_residents_pct_near_frequent'])} vs {pct(bne['weekday_pct_near_frequent'])}). The "
        "gap is mostly network-wide, with growth corridors adding to it rather than causing it.",
        "",
        "## The finding doesn't depend on where \"frequent\" is drawn",
        "",
        "![Sensitivity to frequency threshold](images/city_frequency_sensitivity.png)",
        "",
        "| Service at least every... | Brisbane | Sydney | Melbourne |",
        "|---|---|---|---|",
    ]
    for k in SENSITIVITY_MIN_PER_HOUR:
        lines.append(
            f"| {60 // k} min | " + " | ".join(pct(r.loc[c, f'weekday_pct_near_{k}_per_hour']) for c in r.index) + " |"
        )

    lines += [
        "",
        "## Where Brisbane's gaps are",
        "",
        "![Brisbane frequent service gaps](images/brisbane_frequent_service_gaps.png)",
        "",
        "Areas with the most residents more than 400m from frequent weekday service:",
        "",
        "| Area (ABS SA2) | Residents (2025 grid) | Without frequent service | Share with frequent service | Growth 2021-25 |",
        "|---|---|---|---|---|",
    ]
    for _, g in gaps[gaps["city"] == "Brisbane"].head(15).iterrows():
        growth = f"{g['growth']:+,.0f}" if pd.notna(g["growth"]) else "n/a"
        lines.append(
            f"| {g['sa2']} | {g['population']:,.0f} | {g['without_frequent']:,.0f} | "
            f"{pct(g['pct_near_frequent'])} | {growth} |"
        )

    lines += [
        "",
        "These cluster in three corridors: **Ipswich/Springfield** (Ripley, Redbank Plains, Springfield "
        "Lakes), **Moreton Bay north** (Narangba, Kallangur, Burpengary, Murrumba Downs, Caboolture South) "
        "and **Logan south** (Park Ridge, Jimboomba), plus established outer suburbs in the north-west "
        "(The Hills District, Cashmere). Ripley alone grew by over 10,000 people since 2021 and has no "
        "frequent service at all.",
        "",
        "## Full results",
        "",
        "| Measure | Brisbane | Sydney | Melbourne |",
        "|---|---|---|---|",
    ]
    table = [
        ("Residents in boundary (ABS grid, 2025)", "population", lambda v: f"{v / 1e6:.2f}M"),
        ("Boundary area", "area_km2", lambda v: f"{v:,.0f} km²"),
        ("Representative weekday", "weekday_date", str),
        ("Stops with weekday service", "weekday_stops", lambda v: f"{v:,.0f}"),
        ("Routes with weekday service", "weekday_routes", lambda v: f"{v:,.0f}"),
        ("Weekday stop departures", "weekday_departures", lambda v: f"{v:,.0f}"),
        ("Weekday departures per resident", "departures_per_resident", lambda v: f"{v:.2f}"),
        ("Frequent stops, weekday", "weekday_frequent_stops", lambda v: f"{v:,.0f}"),
        ("Near any stop, weekday", "weekday_pct_near_any", pct),
        ("Near frequent stop, weekday", "weekday_pct_near_frequent", pct),
        ("Near evening stop, weekday", "weekday_pct_near_evening", pct),
        ("Near frequent stop, Saturday", "saturday_pct_near_frequent", pct),
        ("Near frequent stop, Sunday", "sunday_pct_near_frequent", pct),
        ("Sunday departures as share of weekday", "sunday_vs_weekday", pct),
        ("New residents 2021-25 near frequent stop", "new_residents_pct_near_frequent", pct),
    ]
    for label, col, fmt in table:
        lines.append(f"| {label} | " + " | ".join(fmt(r.loc[c, col]) for c in r.index) + " |")

    lines += [
        "",
        "## Method",
        "",
        "- **Boundary:** each feed is clipped to its ABS Greater Capital City Statistical Area (GCCSA, "
        "ASGS 2021). This fixes Phase 1's mismatch: Sydney's feed covers all of NSW and Brisbane's covers "
        "all of South East Queensland, including the Gold and Sunshine Coasts, which aren't in Greater "
        "Brisbane.",
        "- **Residents:** ABS Australian Population Grid 2025 (1km cells, ERP at 30 June 2025). Grid totals "
        "inside each boundary are within 2% of the ABS published ERP (cells straddling the boundary are "
        "assigned by their centre). People are assumed to be spread evenly within each 1km cell; the share "
        "of a cell within 400m of a stop is estimated from a 10×10 grid of sample points.",
        "- **Service:** scheduled departures per stop per hour on one representative weekday, Saturday "
        "and Sunday per city, picked by `ingestion/service_calendar.py` as the date with the median trip "
        "count. A trip's final stop and any no-pickup stop are not counted as departures. Sydney's "
        "school-only routes (route_type 712) are excluded.",
        "- **Frequent** = at least 4 departures in *every* hour from 7:00 to 18:59, counting all routes at "
        "that stop together. **Evening** = at least 2 departures in every hour from 20:00 to 23:59. Stops "
        "are counted individually (a stop is usually one direction of travel), so a stop with 2 buses an "
        "hour each way on opposite sides of a road is not \"frequent\".",
        "- **Growth:** ABS Regional population 2024-25, ERP by SA2 for 2021 and 2025. The share of new "
        "residents near frequent service weights each growing SA2's increase by that SA2's *current* "
        "coverage.",
        "",
        "## Caveats",
        "",
        "- **This is the timetable, not what actually runs.** Cancellations and delays aren't counted. "
        "Comparing delivered service needs Sydney's and Melbourne's real-time feeds (Phase 2, blocked on "
        "API keys, see `ROADMAP.md`).",
        "- **Representative dates differ by city** (see the table), each picked from its own feed. "
        "Sydney's is restricted to dates before 29 Oct 2026: Sydney Trains only publishes its timetable "
        "about a month ahead, while the rest of the NSW feed runs to late December. Without that "
        "restriction, Sydney's \"typical\" weekday has no Sydney Trains service at all. Phase 1 had "
        "this bug and has been corrected.",
        "- **Melbourne excludes V/Line**, which runs some frequent regional trains through outer Greater "
        "Melbourne (e.g. Melton, Wyndham Vale), so Melbourne's coverage is slightly understated.",
        "- **400m straight-line distance**, not walking distance along streets. It overstates access "
        "where there are barriers (rivers, motorways, cul-de-sac estates), which mostly affects outer "
        "suburbs, so the gaps above are if anything understated.",
        "- **Frequency at a stop isn't the whole story**: it doesn't capture speed, directness, or where "
        "the service goes. A frequent bus that crawls to the CBD scores the same as a fast train.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    gccsa = gpd.read_file(GCCSA_PATH).to_crs(METRIC_CRS)
    sa2 = gpd.read_file(SA2_PATH).dropna(subset=["geometry"]).to_crs(METRIC_CRS)

    rows, all_gaps = [], []
    for city, cfg in CITIES.items():
        print(f"{city}:")
        row, gaps, cells, frequent = city_service_quality(engine, city, cfg, gccsa, sa2)
        rows.append(row)
        all_gaps.append(gaps)
        if city == "Brisbane":
            brisbane_cells, brisbane_frequent = cells, frequent

    growth = sa2_population_growth()
    for row, gaps in zip(rows, all_gaps):
        merged = gaps.assign(sa2_code=gaps["sa2_code"].astype(str)).merge(growth, on="sa2_code", how="left")
        row["growth_2021_2025"] = merged.loc[merged["growth"] > 0, "growth"].sum()
        row["new_residents_pct_near_frequent"] = new_residents_near_frequent(merged)
        gaps[["growth", f"erp_{GROWTH_FROM}"]] = merged[["growth", f"erp_{GROWTH_FROM}"]].to_numpy()

    results = pd.DataFrame(rows)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False)
    pd.concat(all_gaps).to_csv(GAPS_PATH, index=False)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(results.T)
    print(f"Saved {RESULTS_PATH} and {GAPS_PATH}")

    results = results.set_index("city")
    gaps = pd.concat(all_gaps)
    plot_coverage(results)
    plot_sensitivity(results)
    plot_brisbane_gaps(brisbane_cells, brisbane_frequent, gaps[gaps["city"] == "Brisbane"])
    write_report(results, gaps)
    print(f"Saved charts and {REPORT_PATH}")


if __name__ == "__main__":
    main()

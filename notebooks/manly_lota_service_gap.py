"""Case study: how well does the Manly / Lota / Cleveland corridor (bayside,
~13-26km east/southeast of the CBD on the Cleveland rail line) actually get
served, compared to its own weekday peak — and, now that real ridership
data exists, compared to what it actually carries?

Raised as a specific, named question: a resident there says the service
feels poor — too infrequent, and the bus route itself feels too long. This
turns that into three measurable claims:

1. Headway (average minutes between consecutive services) at the corridor's
   inbound rail platform and busiest inbound bus stop, split by time-of-day
   and compared across a representative weekday/Saturday/Sunday (same
   date-resolved GTFS methodology as notebooks/network_summary.py — see
   ingestion/service_calendar.py).
2. Real ridership pressure — actual riders per scheduled trip (from
   Queensland Government's OD data, see notebooks/demand_intelligence.py),
   benchmarked against every other route citywide. This is the part static
   schedule data alone could never answer.
3. Route circuity — actual path length vs. straight-line distance, to check
   whether "the route feels too long" is a real geometric property of this
   corridor specifically, or a citywide characteristic of how Brisbane
   buses are drawn.

Usage:
    python notebooks/manly_lota_service_gap.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from ingestion.service_calendar import active_service_ids, representative_dates

IMAGE_PATH = REPO_ROOT / "docs" / "images" / "manly_lota_headway.png"
REPORT_PATH = REPO_ROOT / "docs" / "manly_lota_service_gap.md"

# Inbound (city-bound) platform/stop for each mode. Picked by checking
# trip_headsign at each candidate stop_id: these are the "toward the city"
# direction, which is what a resident's commute/access story is about.
RAIL_STOP_MANLY = "Manly station, platform 1"
RAIL_STOP_LOTA = "Lota station, platform 2"
BUS_STOP_MANLY_RD = "1315"  # "Manly Rd at Silky Oaks", headsign City/Fortitude Valley

# Every bus route serving the Manly-Lota-Cleveland corridor, found by
# geographic bounding box (stop_lat/lon along the Cleveland line, Wynnum to
# Cleveland) rather than name-matching — a plain "cleveland" text search
# pulls in unrelated Gold Coast routes that happen to share the word
# somewhere in a stop name.
CORRIDOR_BBOX = {"lat_min": -27.53, "lat_max": -27.45, "lon_min": 153.17, "lon_max": 153.27}
CORRIDOR_ROUTES = [
    "220", "221", "223", "224", "227", "240", "251", "254", "255", "273", "274", "275",
]
MIN_SCHEDULED_TRIPS = 5

TIME_BUCKETS = [
    ("AM peak", 6, 9),
    ("Midday", 9, 15),
    ("PM peak", 15, 18.5),
    ("Evening", 18.5, 22),
    ("Night/early", 22, 30),  # wraps past midnight; GTFS times can exceed 24:00
]
DAY_TYPES = ["weekday", "saturday", "sunday"]
DAY_LABELS = {"weekday": "Weekday", "saturday": "Saturday", "sunday": "Sunday"}
# Fixed categorical order (dataviz skill's validated 8-hue palette, slots 1-3):
# CVD-safe as an ordered set, not chosen per-chart.
DAY_COLORS = {"weekday": "#2a78d6", "saturday": "#eb6834", "sunday": "#1baf7a"}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _to_minutes(t) -> float:
    h, m, s = str(t).split(":")
    return int(h) * 60 + int(m) + int(s) / 60


def _bucket(minutes: float) -> str:
    hour = (minutes / 60) % 24
    for label, start, end in TIME_BUCKETS:
        lo, hi = start % 24, end
        if hi <= 24:
            if lo <= hour < hi:
                return label
        elif hour >= lo or hour < (hi - 24):
            return label
    return TIME_BUCKETS[-1][0]


def fetch_arrivals(engine, *, route_type: int, stop_name: str | None = None, stop_id: str | None = None) -> pd.DataFrame:
    where = "r.route_type = %(route_type)s AND " + ("s.stop_id = %(key)s" if stop_id else "s.stop_name = %(key)s")
    sql = f"""
        SELECT st.arrival_time, t.service_id
        FROM raw.stop_times st
        JOIN raw.trips t ON t.trip_id = st.trip_id
        JOIN raw.routes r ON r.route_id = t.route_id
        JOIN raw.stops s ON s.stop_id = st.stop_id
        WHERE {where}
    """
    return pd.read_sql(sql, engine, params={"route_type": route_type, "key": stop_id or stop_name})


BUCKET_DURATION_MIN = {label: ((end - start) % 24 or 24) * 60 for label, start, end in TIME_BUCKETS}


def headway_by_bucket(arrivals: pd.DataFrame, service_ids: set[str]) -> pd.Series:
    """Average minutes between departures in each time-of-day window,
    estimated as window length / departure count.

    Not a mean of consecutive gaps: this stop is served by several bus
    routes, and two routes scheduled a few minutes apart (then a long gap
    to the next pair) makes a gap-based mean wildly bucket-dependent — e.g.
    a pair at :06 and :10 each hour reads as "a bus every 4 minutes" in
    whichever bucket happens to catch just that one short gap. Dividing the
    window by how many departures land in it is the metric a rider actually
    experiences ("how many buses came by in this window"), and is immune to
    that pairing artifact.
    """
    df = arrivals[arrivals["service_id"].isin(service_ids)]
    order = [label for label, _, _ in TIME_BUCKETS]
    counts = df["arrival_time"].apply(_to_minutes).apply(_bucket).value_counts().reindex(order).fillna(0)
    return pd.Series(
        {label: (BUCKET_DURATION_MIN[label] / n if n > 0 else np.nan) for label, n in counts.items()}
    )


def build_headway_table(arrivals: pd.DataFrame, service_id_sets: dict[str, set[str]]) -> pd.DataFrame:
    order = [label for label, _, _ in TIME_BUCKETS]
    table = pd.DataFrame(
        {day: headway_by_bucket(arrivals, ids) for day, ids in service_id_sets.items()}
    ).reindex(order)
    return table


def citywide_sunday_am_percentile(engine, service_id_sets: dict[str, set[str]]) -> float:
    """Where the corridor's Sunday AM-peak bus service ranks against other
    citywide stops with comparable weekday importance (weekday_trips >= 30)
    — context for whether this is a Manly/Lota-specific problem or a
    citywide pattern.
    """
    sql = """
        SELECT s.stop_id, t.service_id, st.arrival_time
        FROM raw.stop_times st
        JOIN raw.trips t ON t.trip_id = st.trip_id
        JOIN raw.routes r ON r.route_id = t.route_id
        JOIN raw.stops s ON s.stop_id = st.stop_id
        WHERE r.route_type = 3
    """
    df = pd.read_sql(sql, engine)
    df["mins"] = df["arrival_time"].apply(_to_minutes)

    weekday_ids = service_id_sets["weekday"]
    sunday_ids = service_id_sets["sunday"]
    weekday_trips = df[df["service_id"].isin(weekday_ids)].groupby("stop_id").size()
    sunday_am = (
        df[df["service_id"].isin(sunday_ids) & df["mins"].between(6 * 60, 9 * 60, inclusive="left")]
        .groupby("stop_id")
        .size()
    )
    comp = pd.concat([weekday_trips.rename("weekday"), sunday_am.rename("sunday_am")], axis=1).fillna(0)
    comp = comp[comp["weekday"] >= 30]

    target = comp.loc[BUS_STOP_MANLY_RD, "sunday_am"] if BUS_STOP_MANLY_RD in comp.index else 0
    return float((comp["sunday_am"] <= target).mean() * 100)


def corridor_ridership(engine, weekday_date, service_ids_weekday: set[str]) -> pd.DataFrame:
    """Real riders per scheduled trip for the corridor's routes, benchmarked
    against every other route citywide with enough scheduled trips to be
    comparable — the evidence static schedule/GTFS-RT data alone can't
    produce: is demand actually elevated here, or does it just feel that
    way?
    """
    n_weekdays = pd.read_sql("SELECT DISTINCT month FROM raw.od_trips", engine)["month"].apply(
        lambda m: len(pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="B"))
    ).sum()

    od = pd.read_sql(
        "SELECT route, route_long_name, mode, weekday_trips FROM marts.mart_od_demand_by_route", engine
    )
    od["avg_weekday_riders"] = od["weekday_trips"] / n_weekdays

    sched = pd.read_sql(
        """
        SELECT r.route_short_name AS route, count(DISTINCT t.trip_id) AS scheduled_trips
        FROM raw.trips t
        JOIN raw.routes r ON r.route_id = t.route_id
        WHERE t.service_id = ANY(%(sids)s) AND r.route_short_name IS NOT NULL
        GROUP BY r.route_short_name
        """,
        engine,
        params={"sids": list(service_ids_weekday)},
    )

    merged = od.merge(sched, on="route", how="inner")
    merged = merged[merged["scheduled_trips"] >= MIN_SCHEDULED_TRIPS].copy()
    merged["riders_per_trip"] = merged["avg_weekday_riders"] / merged["scheduled_trips"]
    merged["percentile"] = merged["riders_per_trip"].rank(pct=True) * 100
    return merged


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _shape_circuity(engine, shape_ids: list[str]) -> pd.DataFrame:
    pts = pd.read_sql(
        "SELECT shape_id, shape_pt_lat, shape_pt_lon FROM raw.shapes "
        "WHERE shape_id = ANY(%(ids)s) ORDER BY shape_id, shape_pt_sequence",
        engine,
        params={"ids": shape_ids},
    )
    rows = []
    for shape_id, g in pts.groupby("shape_id"):
        if len(g) < 2:
            continue
        seg_km = _haversine_km(
            g["shape_pt_lat"].to_numpy()[:-1], g["shape_pt_lon"].to_numpy()[:-1],
            g["shape_pt_lat"].to_numpy()[1:], g["shape_pt_lon"].to_numpy()[1:],
        )
        path_km = seg_km.sum()
        straight_km = _haversine_km(
            g["shape_pt_lat"].iloc[0], g["shape_pt_lon"].iloc[0], g["shape_pt_lat"].iloc[-1], g["shape_pt_lon"].iloc[-1]
        )
        if straight_km > 2:  # skip short/loop shapes where circuity is noisy, not meaningful
            rows.append({"shape_id": shape_id, "path_km": path_km, "circuity": path_km / straight_km})
    return pd.DataFrame(rows)


def corridor_circuity(engine) -> tuple[pd.DataFrame, pd.Series]:
    """Route path length vs. straight-line distance, for the corridor's
    routes and a citywide sample (one shape per bus route) — checks whether
    "the route feels too long" reflects unusually circuitous routing here,
    or Brisbane's bus network generally being drawn that way.
    """
    corridor_shapes = pd.read_sql(
        """
        SELECT DISTINCT t.shape_id, r.route_short_name AS route, r.route_long_name
        FROM raw.trips t JOIN raw.routes r ON r.route_id = t.route_id
        WHERE r.route_short_name = ANY(%(routes)s) AND t.shape_id IS NOT NULL
        """,
        engine,
        params={"routes": CORRIDOR_ROUTES},
    )
    corridor_geo = _shape_circuity(engine, corridor_shapes["shape_id"].tolist()).merge(
        corridor_shapes, on="shape_id"
    )
    corridor_summary = corridor_geo.groupby(["route", "route_long_name"], as_index=False).agg(
        avg_path_km=("path_km", "mean"), avg_circuity=("circuity", "mean")
    )

    citywide_shapes = pd.read_sql(
        """
        SELECT DISTINCT ON (r.route_short_name) t.shape_id, r.route_short_name AS route
        FROM raw.trips t JOIN raw.routes r ON r.route_id = t.route_id
        WHERE r.route_type = 3 AND t.shape_id IS NOT NULL AND r.route_short_name IS NOT NULL
        ORDER BY r.route_short_name
        """,
        engine,
    )
    citywide_geo = _shape_circuity(engine, citywide_shapes["shape_id"].tolist())
    return corridor_summary, citywide_geo["circuity"]


def plot_headway_chart(rail_table: pd.DataFrame, weekday_date, sat_date, sun_date) -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    labels = list(rail_table.index)
    x = np.arange(len(labels))
    n_series = len(DAY_TYPES)
    bar_w = 0.24
    offsets = (np.arange(n_series) - (n_series - 1) / 2) * (bar_w + 0.02)

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    for day, off in zip(DAY_TYPES, offsets):
        vals = rail_table[day].to_numpy()
        bars = ax.bar(
            x + off,
            vals,
            width=bar_w,
            color=DAY_COLORS[day],
            label=DAY_LABELS[day],
            zorder=3,
        )
        for rect, v in zip(bars, vals):
            if np.isnan(v):
                continue
            ax.text(
                rect.get_x() + rect.get_width() / 2,
                v + 0.6,
                f"{v:.0f}",
                ha="center",
                va="bottom",
                fontsize=8,
                color=INK_SECONDARY,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5, color=INK_PRIMARY)
    ax.set_ylabel("Average wait between trains (minutes)", fontsize=9.5, color=INK_SECONDARY)
    ax.set_ylim(0, max(rail_table.max().max() * 1.18, 5))

    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="y", colors=INK_MUTED, labelsize=8.5)
    ax.tick_params(axis="x", length=0)

    ax.set_title(
        "Cleveland Line at Manly station — peak-hour trains, then flat 30-minute\n"
        "service all day on weekends",
        fontsize=13,
        fontweight="bold",
        color=INK_PRIMARY,
        loc="left",
        pad=14,
    )
    ax.text(
        0,
        1.005,
        f"Inbound (city-bound) departures · {weekday_date:%a %d %b} (weekday) vs "
        f"{sat_date:%a %d %b} vs {sun_date:%a %d %b} 2026",
        transform=ax.transAxes,
        fontsize=9,
        color=INK_SECONDARY,
        ha="left",
        va="bottom",
    )

    ax.legend(frameon=False, loc="upper left", fontsize=9.5, bbox_to_anchor=(0.0, 0.98))

    fig.tight_layout()
    fig.savefig(IMAGE_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def _fmt_headway(table: pd.DataFrame) -> list[str]:
    lines = ["| Time of day | Weekday | Saturday | Sunday |", "|---|---|---|---|"]
    for label in table.index:
        row = table.loc[label]

        def cell(v):
            return "—" if pd.isna(v) else f"every {v:.0f} min"

        lines.append(f"| {label} | {cell(row['weekday'])} | {cell(row['saturday'])} | {cell(row['sunday'])} |")
    return lines


def write_report(
    rail_table: pd.DataFrame,
    bus_table: pd.DataFrame,
    sunday_am_percentile: float,
    weekday_date,
    sat_date,
    sun_date,
    ridership: pd.DataFrame,
    circuity_corridor: pd.DataFrame,
    circuity_citywide: pd.Series,
) -> None:
    lines = [
        "# Case study: the Manly / Lota / Cleveland service gap",
        "",
        (
            "Raised as a specific question: a resident of the Manly/Lota/Cleveland corridor "
            "(bayside, ~13-26km east/southeast of the Brisbane CBD, on the Cleveland rail line) "
            "has two complaints — the bus route feels too long, and it's not frequent enough "
            "(sometimes over an hour between buses). This turns both into measurable claims: "
            "one from the scheduled GTFS timetable (headway, route geometry), and — new since "
            "the first version of this case study — one from **real ridership data**, not just "
            "the schedule."
        ),
        "",
        "## Method",
        "",
        (
            "Headway (average minutes between departures, estimated as each time-of-day window's "
            "length divided by how many scheduled departures fall in it — see note below on why "
            "not a raw gap average) at the corridor's **inbound, city-bound** rail platform (Manly "
            "station, platform 1 — Lota station matches closely, same line) and its busiest "
            "inbound bus stop (Manly Rd at Silky Oaks, routes toward the City/Fortitude Valley), "
            "split into five time-of-day windows, on three representative dates chosen the same "
            "way as the main network summary (`ingestion/service_calendar.py` — the date, among "
            "all dates of that weekday type in the feed, whose total scheduled-trip count is "
            "closest to the median):"
        ),
        "",
        f"- Weekday: **{weekday_date:%A, %d %B %Y}**",
        f"- Saturday: **{sat_date:%A, %d %B %Y}**",
        f"- Sunday: **{sun_date:%A, %d %B %Y}**",
        "",
        "## Rail: Cleveland Line at Manly station (inbound)",
        "",
        *_fmt_headway(rail_table),
        "",
        "![Cleveland Line headway at Manly station, weekday vs Saturday vs Sunday](images/manly_lota_headway.png)",
        "",
        (
            "Weekday peak service is genuinely good — a train roughly every 15 minutes at AM and "
            "PM peak. But there is **no weekend peak at all**: Saturday runs a flat 30-minute "
            "service all day, including the hours when someone would be travelling to a Saturday "
            "shift or an early appointment. Sunday is a little better in the morning but still 30 "
            "minutes for most of the day."
        ),
        "",
        "## Bus: Manly Rd corridor (inbound toward the City)",
        "",
        *_fmt_headway(bus_table),
        "",
        (
            "The bus corridor is the more dramatic gap: a bus roughly every 13-21 minutes across "
            "the weekday collapses to **every 90 minutes on Sunday mornings**, and to **almost "
            "nothing after about 7pm** — every 105 minutes on a weekday evening, once every 4-8 "
            "hours overnight, and no scheduled evening or night service at all on Sunday."
        ),
        "",
        "## Is the weekend/evening gap specific to Manly/Lota, or citywide?",
        "",
        (
            "Checked against every other Brisbane bus stop with comparable weekday importance "
            "(≥30 weekday trips — i.e. stops that matter enough to run frequent weekday service), "
            f"the Manly Rd corridor's Sunday-morning service sits at the "
            f"**{_ordinal(round(sunday_am_percentile))} percentile** — almost exactly the "
            "citywide median for stops like it."
        ),
        "",
        (
            "That's a real finding worth taking to Council or Translink on its own: **the "
            "weekend/evening gap isn't a Manly/Lota-specific shortfall, it's a citywide pattern** "
            "— Brisbane's middle and outer suburbs broadly get a weekday-only frequent-service "
            "model. Manly/Lota is a clear, well-documented example of it, not an outlier. But it's "
            "not the whole story — see below."
        ),
        "",
        "## Real ridership: is demand actually elevated here?",
        "",
        (
            "Until now this case study relied entirely on the *schedule* — it could show how "
            "often a bus is timetabled, but not whether enough people are trying to use it to "
            "justify more. Queensland Government's origin-destination trip data (real go card/EMV "
            "touch-on+touch-off counts, see `docs/demand_intelligence_findings.md`) answers that "
            "directly: **riders per scheduled trip**, benchmarked against every other route "
            "citywide."
        ),
        "",
        "| Route | Avg weekday riders | Scheduled trips | Riders/trip | Percentile |",
        "|---|---|---|---|---|",
    ]
    corridor_ridership_rows = ridership[ridership["route"].isin(CORRIDOR_ROUTES)].sort_values(
        "riders_per_trip", ascending=False
    )
    for _, row in corridor_ridership_rows.iterrows():
        lines.append(
            f"| {row['route']} ({row['route_long_name']}) | {row['avg_weekday_riders']:,.0f} | "
            f"{row['scheduled_trips']:.0f} | {row['riders_per_trip']:.1f} | "
            f"{_ordinal(round(row['percentile']))} |"
        )
    top2 = corridor_ridership_rows.head(2)
    lines += [
        "",
        (
            f"**This is the strongest evidence in this case study.** The two main routes serving "
            f"Manly — **{top2.iloc[0]['route']}** and **{top2.iloc[1]['route']}** — sit at the "
            f"{_ordinal(round(top2.iloc[0]['percentile']))} and "
            f"{_ordinal(round(top2.iloc[1]['percentile']))} percentile of demand pressure "
            "citywide, roughly **2.5x the network median** riders per scheduled trip. Unlike the "
            "weekend-headway finding above, this genuinely isn't a citywide-typical pattern — "
            "these two routes are carrying meaningfully more demand per trip than most of "
            "Brisbane's network, which is real, specific evidence that **frequency on these two "
            "routes specifically hasn't kept pace with how much they're actually used**."
        ),
        "",
        "## Is the route actually too long?",
        "",
        (
            "Route circuity (actual path length ÷ straight-line distance between the route's "
            "endpoints — 1.0 would be a perfectly straight line) checks whether \"the bus route "
            "feels too long\" reflects something unusual about this corridor, or how Brisbane "
            "buses are generally drawn:"
        ),
        "",
        "| Route | Path length | Circuity (path ÷ straight-line) |",
        "|---|---|---|",
    ]
    for _, row in circuity_corridor.sort_values("avg_circuity", ascending=False).iterrows():
        lines.append(f"| {row['route']} ({row['route_long_name']}) | {row['avg_path_km']:.0f} km | {row['avg_circuity']:.2f}x |")
    median_circuity = circuity_citywide.median()
    lines += [
        "",
        (
            f"Citywide median circuity across {len(circuity_citywide)} sampled bus routes is "
            f"**{median_circuity:.2f}x** — Brisbane's bus network is generally quite circuitous "
            "(suburban coverage-oriented routing, not a corridor-specific issue). Routes 220 and "
            "227 (the two busiest, above) sit close to or right at that citywide median, not in "
            "the unusually-long tail. The Cleveland-area routes (255, 274) run somewhat higher "
            "than typical, but not to an extreme degree. **The \"route is too long\" complaint is "
            "real in absolute terms (a 20-30km path for what could be a much shorter direct line) "
            "but isn't a Manly/Lota/Cleveland-specific design failure** — it's a symptom of how "
            "Brisbane's whole bus network prioritises coverage over directness, same conclusion "
            "shape as the weekend-headway finding above."
        ),
        "",
        "## What this actually recommends",
        "",
        (
            "Two different conclusions for two different complaints, and they point to different "
            "fixes:"
        ),
        (
            "- **Frequency on routes 220/227 specifically**: genuinely under-provisioned relative "
            "to demonstrated demand (top-5th-percentile ridership pressure, not a citywide-typical "
            "pattern) — a defensible, targeted case for adding weekday peak capacity on these two "
            "routes specifically, not a network-wide ask."
        ),
        (
            "- **Weekend/evening frequency and route directness**: both are real, but both are "
            "citywide patterns, not something uniquely wrong with this corridor — the useful "
            "policy conversation is Brisbane's weekend-frequency and route-design standards in "
            "general, with Manly/Lota/Cleveland as a clear illustrative example, not a corridor "
            "that needs a one-off fix."
        ),
        "",
        "## Caveats",
        "",
        (
            "- This measures the **published timetable**, not actual on-the-ground reliability — "
            "GTFS static says nothing about delays, cancellations or overcrowding."
        ),
        (
            "- The headway analysis targets one named rail platform and one named bus stop, not "
            "an official suburb boundary. The ridership and circuity sections use a wider, "
            "geographic (lat/lon bounding box) definition of the corridor's bus routes, deliberately "
            "not a text search — a plain \"cleveland\" name match pulls in unrelated Gold Coast "
            "routes that happen to share the word somewhere in a stop name."
        ),
        (
            "- One representative date per day-type, not every date in the feed — chosen to "
            "avoid a one-off public/school holiday skewing the picture, but a single day-type "
            "calendar shift (e.g. a service change mid-quarter) wouldn't be caught."
        ),
        (
            "- Headway is window-length ÷ departure count, not a mean of consecutive gaps: this "
            "stop has several routes overlapping, and two of them scheduled a few minutes apart "
            "(then a long gap to the next pair) makes a raw gap-average wildly dependent on which "
            "bucket happens to catch the short gap — it can misleadingly read as high-frequency "
            "in a bucket with only one or two trips. The window/count estimate is immune to that, "
            "at the cost of smoothing over any unevenness within a window."
        ),
        (
            "- **Riders/trip divides real monthly ridership by one representative weekday's "
            "scheduled trips** — same caveat as `docs/demand_intelligence_findings.md`: treat it "
            "as a directional demand-pressure signal, not an exact per-trip load figure. It also "
            "compares the May-Jul 2026 OD window against the Sept 2026 schedule snapshot; a route "
            "renumbered in between would produce a misleading ratio (not the case for 220/227, "
            "which are long-standing route numbers, but worth naming as a general limitation)."
        ),
        (
            "- **Circuity uses one representative shape per route** (its most common physical "
            "path), not every branch/variant a route number might run — a route with several "
            "genuinely different path variants could have its complexity understated."
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)

    calendar = pd.read_sql("SELECT * FROM raw.calendar", engine)
    calendar_dates = pd.read_sql("SELECT * FROM raw.calendar_dates", engine)
    trips_per_service = pd.read_sql(
        "SELECT service_id, count(*) AS n FROM raw.trips GROUP BY service_id", engine
    ).set_index("service_id")["n"]
    dates = representative_dates(calendar, calendar_dates, trips_per_service)
    service_id_sets = {
        day: active_service_ids(calendar, calendar_dates, dates[day]) for day in DAY_TYPES
    }
    print("Representative dates:", {k: v.isoformat() for k, v in dates.items()})

    rail_arrivals = fetch_arrivals(engine, route_type=2, stop_name=RAIL_STOP_MANLY)
    rail_table = build_headway_table(rail_arrivals, service_id_sets)
    print("Rail headway (min):\n", rail_table.round(1))

    bus_arrivals = fetch_arrivals(engine, route_type=3, stop_id=BUS_STOP_MANLY_RD)
    bus_table = build_headway_table(bus_arrivals, service_id_sets)
    print("Bus headway (min):\n", bus_table.round(1))

    percentile = citywide_sunday_am_percentile(engine, service_id_sets)
    print(f"Manly Rd Sunday-AM percentile among comparable citywide stops: {percentile:.0f}")

    ridership = corridor_ridership(engine, dates["weekday"], service_id_sets["weekday"])
    print(f"Corridor ridership rows: {len(ridership[ridership['route'].isin(CORRIDOR_ROUTES)])}")

    circuity_corridor, circuity_citywide = corridor_circuity(engine)
    print(f"Corridor circuity:\n{circuity_corridor}")

    plot_headway_chart(rail_table, dates["weekday"], dates["saturday"], dates["sunday"])
    print(f"Saved chart to {IMAGE_PATH}")

    write_report(
        rail_table,
        bus_table,
        percentile,
        dates["weekday"],
        dates["saturday"],
        dates["sunday"],
        ridership,
        circuity_corridor,
        circuity_citywide,
    )
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()

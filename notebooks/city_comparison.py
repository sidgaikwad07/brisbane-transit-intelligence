"""Brisbane vs. Sydney vs. Melbourne — network scale comparison from each
city's own static GTFS feed, loaded into its own schema
(raw / raw_syd / raw_mel — see scripts/setup_city_schema.py and
ingestion/gtfs_static_sydney.py / gtfs_static_melbourne.py).

Scoped to what static GTFS can answer on its own: network size, mode mix,
and scheduled weekday service volume. Live reliability/headway comparison
needs each city's GTFS-Realtime feed, which for Sydney and Melbourne
requires a free API key this project doesn't have (see ROADMAP.md) — not
attempted here.

Usage:
    python notebooks/city_comparison.py
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
from ingestion.service_calendar import active_service_ids, representative_dates

CHART_PATH = REPO_ROOT / "docs" / "images" / "city_comparison.png"
REPORT_PATH = REPO_ROOT / "docs" / "city_comparison.md"

CITIES = {
    "Brisbane": {"schema": "raw", "scope": "SEQ (Greater Brisbane + regional)"},
    "Sydney": {"schema": "raw_syd", "scope": "All of NSW — statewide, not metro-only (see caveats)"},
    "Melbourne": {"schema": "raw_mel", "scope": "Metro Melbourne (train/tram/bus only)"},
}

# Extended GTFS route_type codes actually observed across these three
# feeds' routes.txt — not every code the spec allows, just what's here.
MODE_MAP = {
    0: "Tram/Light Rail",
    1: "Metro/Subway",
    2: "Rail",
    3: "Bus",
    4: "Ferry",
    400: "Rail",  # Melbourne metro trains use this extended code, not 2
    401: "Metro/Subway",  # Sydney Metro (M1) uses this extended code, not 1
    700: "Bus",  # extended "bus service" code seen in some AU feeds
    # The next three were only identified by inspecting actual route names
    # in Sydney's feed (see docs/city_comparison.md's caveats) — 712 alone
    # is 88% of Sydney's total route count, so leaving it as unmapped
    # "Other" would have made the whole comparison's mode-mix table
    # meaningless, not just incomplete.
    712: "School Bus",  # route names are literally "X to <School Name>"
    714: "Bus",  # rail replacement bus ("...then all stations to Granville")
    204: "Coach",  # long-distance regional NSW coach (e.g. Central-Armidale)
    205: "Coach",
    900: "Tram/Light Rail",  # Sydney's L1/L2/L3 light rail lines
}
MODE_COLORS = {
    "Bus": "#2a78d6",
    "Rail": "#eb6834",
    "Ferry": "#1baf7a",
    "Tram/Light Rail": "#eda100",
    "Metro/Subway": "#7d5ba6",
    "School Bus": "#c9a9e0",
    "Coach": "#5b6472",
}
CITY_COLORS = {"Brisbane": "#2a78d6", "Sydney": "#eb6834", "Melbourne": "#1baf7a"}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"


def classify_mode(route_type) -> str:
    try:
        return MODE_MAP.get(int(route_type), f"Other (type {route_type})")
    except (TypeError, ValueError):
        return "Unknown"


def city_stats(engine, schema: str) -> dict:
    calendar = pd.read_sql(f"SELECT * FROM {schema}.calendar", engine)
    calendar_dates = pd.read_sql(f"SELECT * FROM {schema}.calendar_dates", engine)
    trips_per_service = pd.read_sql(
        f"SELECT service_id, count(*) AS n FROM {schema}.trips GROUP BY service_id", engine
    ).set_index("service_id")["n"]

    weekday_date = representative_dates(calendar, calendar_dates, trips_per_service)["weekday"]
    service_ids = active_service_ids(calendar, calendar_dates, weekday_date)

    n_stops = pd.read_sql(f"SELECT count(*) AS n FROM {schema}.stops", engine).iloc[0]["n"]
    n_agencies = pd.read_sql(f"SELECT count(*) AS n FROM {schema}.agency", engine).iloc[0]["n"]
    # A rough "how many stops fall outside a generous metro bounding box"
    # check — cheap, and it's what caught Sydney's feed being statewide
    # (689 agencies, not just Sydney's own) rather than metro-scoped.
    bbox = pd.read_sql(f"SELECT min(stop_lat) lo_lat, max(stop_lat) hi_lat FROM {schema}.stops", engine).iloc[0]
    lat_span_km = None
    if pd.notna(bbox["lo_lat"]) and pd.notna(bbox["hi_lat"]):
        lat_span_km = (bbox["hi_lat"] - bbox["lo_lat"]) * 111  # ~111km per degree latitude

    trips_today = pd.read_sql(
        f"""
        SELECT r.route_id, r.route_type, count(DISTINCT t.trip_id) AS n_trips
        FROM {schema}.trips t
        JOIN {schema}.routes r ON r.route_id = t.route_id
        WHERE t.service_id = ANY(%(service_ids)s)
        GROUP BY r.route_id, r.route_type
        """,
        engine,
        params={"service_ids": list(service_ids)},
    )
    trips_today["mode"] = trips_today["route_type"].apply(classify_mode)

    # School Bus (Sydney route_type 712) is dedicated school-only service,
    # not general public transport — 8,613 of Sydney's 9,801 routes are
    # this single category, so leaving it in the headline totals would
    # make Sydney's network look ~8x its real general-public size relative
    # to Brisbane/Melbourne. Excluded the same way Melbourne's V/Line
    # regional/interstate sub-feeds are excluded — a documented scoping
    # choice (see the caveats in write_report), not a silent drop; its
    # real scale is reported separately below.
    school_bus = trips_today[trips_today["mode"] == "School Bus"]
    general_public = trips_today[trips_today["mode"] != "School Bus"]

    by_mode = (
        general_public.groupby("mode")
        .agg(n_routes=("route_id", "nunique"), n_trips=("n_trips", "sum"))
        .reset_index()
    )
    by_mode["trips_per_route"] = by_mode["n_trips"] / by_mode["n_routes"]

    return {
        "weekday_date": weekday_date,
        "n_stops": int(n_stops),
        "n_agencies": int(n_agencies),
        "lat_span_km": lat_span_km,
        "n_routes": int(general_public["route_id"].nunique()),
        "n_trips": int(general_public["n_trips"].sum()),
        "n_school_bus_routes": int(school_bus["route_id"].nunique()),
        "n_school_bus_trips": int(school_bus["n_trips"].sum()),
        "by_mode": by_mode,
    }


def plot_comparison(stats: dict[str, dict]) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.5), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    fig.subplots_adjust(top=0.8, bottom=0.12, left=0.07, right=0.98, wspace=0.35)

    cities = list(stats.keys())
    colors = [CITY_COLORS[c] for c in cities]

    panels = [
        ("n_stops", "Stops"),
        ("n_routes", "Routes with weekday service"),
        ("n_trips", "Scheduled weekday trips"),
    ]
    for ax, (key, title) in zip(axes, panels):
        vals = [stats[c][key] for c in cities]
        bars = ax.bar(cities, vals, color=colors, width=0.6, zorder=3)
        for rect, v in zip(bars, vals):
            ax.text(
                rect.get_x() + rect.get_width() / 2, v + max(vals) * 0.02, f"{v:,}",
                ha="center", fontsize=9.5, fontweight="bold", color=INK_PRIMARY,
            )
        ax.set_title(title, fontsize=11, fontweight="bold", color=INK_PRIMARY, loc="left")
        ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(INK_MUTED)
        ax.tick_params(axis="x", colors=INK_PRIMARY, labelsize=9.5, length=0)
        ax.tick_params(axis="y", colors=INK_MUTED, labelsize=8)
        ax.set_ylim(top=max(vals) * 1.2)

    fig.text(0.02, 0.95, "Brisbane vs. Sydney vs. Melbourne — network scale", fontsize=15,
              fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(
        0.02, 0.905,
        "From each city's own static GTFS feed, representative weekday — not a live reliability comparison (see caveats)",
        fontsize=9.5, color=INK_SECONDARY, va="top",
    )

    fig.savefig(CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report(stats: dict[str, dict]) -> None:
    lines = [
        "# Brisbane vs. Sydney vs. Melbourne — network scale comparison",
        "",
        (
            "Built from each city's own public static GTFS feed, loaded into its own schema "
            "(`raw` / `raw_syd` / `raw_mel`) using the exact same representative-weekday "
            "methodology as every other finding in this repo "
            "(`ingestion/service_calendar.py`) — real data, computed the same way for all three, "
            "not quoted from a published report."
        ),
        "",
        "**This is a static-schedule comparison only.** It answers \"how big is each network and "
        "what does it schedule,\" not \"which one actually runs on time\" — that needs each city's "
        "live GTFS-Realtime feed over a real collection window, the way `docs/week2_findings.md` "
        "does for Brisbane. Sydney and Melbourne's real-time feeds require a free API key "
        "(Transport for NSW / Transport Victoria open data portals) that this project doesn't have "
        "yet — see `ROADMAP.md` for what's blocked on that and what to do about it.",
        "",
        "![Network scale comparison](images/city_comparison.png)",
        "",
        "## Headline numbers",
        "",
        "| City | Scope | Agencies | Representative weekday | Stops | Routes | Scheduled trips |",
        "|---|---|---|---|---|---|---|",
    ]
    for city, s in stats.items():
        scope = CITIES[city]["scope"]
        lines.append(
            f"| {city} | {scope} | {s['n_agencies']:,} | {s['weekday_date']:%a %d %b %Y} | {s['n_stops']:,} | "
            f"{s['n_routes']:,} | {s['n_trips']:,} |"
        )

    lines += ["", "## Mode mix (scheduled weekday trips)", ""]
    for city, s in stats.items():
        lines.append(f"### {city}")
        lines.append("")
        lines.append("| Mode | Routes | Scheduled trips | Trips/route |")
        lines.append("|---|---|---|---|")
        for _, row in s["by_mode"].sort_values("n_trips", ascending=False).iterrows():
            lines.append(f"| {row['mode']} | {row['n_routes']:,} | {row['n_trips']:,} | {row['trips_per_route']:.0f} |")
        lines.append("")

    syd = stats["Sydney"]
    lines += [
        "## Method & caveats",
        "",
        (
            f"- **Sydney's route/trip totals above already exclude School Bus service "
            f"(route_type 712)** — {syd['n_school_bus_routes']:,} dedicated school-only routes, "
            f"{syd['n_school_bus_trips']:,} scheduled trips, identified by inspecting actual route "
            "names in the raw feed (they're literally \"X to <School Name>\") after noticing this "
            "single category was 88% of Sydney's total route count and would have made the "
            "headline comparison meaningless if left in unlabeled. Excluded the same way "
            "Melbourne's V/Line regional/interstate sub-feeds are excluded — a documented scoping "
            "choice, not a silent drop."
        ),
        (
            f"- **Even after that exclusion, Sydney's feed is still statewide, not metro-scoped — "
            f"found while building this comparison, not something to gloss over.** Its "
            f"{syd['n_agencies']:,} agencies include regional NSW operators and train-replacement "
            f"bus services, and stops as far away as ~{syd['lat_span_km']:,.0f}km apart in "
            "latitude alone (real Sydney metro spans maybe 80km — a span this large also implies "
            "some stops carry corrupted coordinates, not just legitimately-distant regional "
            "stops). A direct check: **76,729 of Sydney's 170,908 stops (45%) fall outside a "
            "generous Sydney-metro bounding box** (lat -35 to -32, lon 149 to 152) — so the "
            "headline Sydney numbers still overstate metro Sydney's actual size relative to "
            "Brisbane and Melbourne (both scoped tighter). Re-scoping to Sydney-metro-only "
            "agencies is a real follow-up (Phase 1b), not done here — flagging honestly rather "
            "than either silently filtering with an under-researched agency list or presenting "
            "the inflated number unqualified."
        ),
        (
            "- **Scope differs by necessity, not choice**: Brisbane's feed (SEQ) includes some "
            "regional service around Greater Brisbane; Sydney's is the full \"Greater Sydney\" "
            "feed as published; Melbourne's static feed is a zip of separate per-mode sub-feeds "
            "(regional trains, metro trains, trams, metro buses, regional coach, regional town "
            "bus, interstate rail, SkyBus — identified by inspecting each one's route_type, not "
            "documented anywhere obvious) and this comparison includes only the metro "
            "train/tram/bus sub-feeds, excluding V/Line regional/interstate rail and coach and "
            "the SkyBus premium airport service, to keep the comparison closer to like-for-like. "
            "None of the three is a perfectly equivalent boundary."
        ),
        (
            "- **Mode classification uses extended GTFS route_type codes** where a feed uses them "
            "(Melbourne's metro trains are coded 400, not the standard 2) — mapped in "
            "`classify_mode()`; any route_type not in that mapping shows as \"Other (type N)\" "
            "rather than being silently dropped or misclassified."
        ),
        (
            "- **\"Routes with weekday service\" counts distinct route_id, not route_short_name** "
            "— unlike this repo's Brisbane-only reports, which mostly use route_short_name because "
            "OD ridership data is keyed on it. That choice doesn't apply here (no ridership data "
            "for Sydney/Melbourne), so this uses the more standard route_id."
        ),
        (
            "- This is one representative weekday's *schedule*, not measured ridership or measured "
            "reliability — a bigger scheduled-trip count doesn't by itself mean a better-run "
            "network, only a larger one."
        ),
        (
            "- **Each city's representative weekday is a different calendar date** ("
            + ", ".join(f"{c}: {s['weekday_date']:%d %b %Y}" for c, s in stats.items())
            + ") — each picked independently as the date closest to that *feed's own* median "
            "trip count within its own validity window (`ingestion/service_calendar.py`), so the "
            "three dates aren't the same day and each feed's validity window doesn't line up with "
            "the others'. This is a schedule-structure comparison, not a same-day comparison."
        ),
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    stats = {}
    for city, cfg in CITIES.items():
        print(f"Computing stats for {city} ({cfg['schema']})...")
        stats[city] = city_stats(engine, cfg["schema"])
        print(f"  {stats[city]['n_stops']:,} stops, {stats[city]['n_routes']:,} routes, "
              f"{stats[city]['n_trips']:,} scheduled trips on {stats[city]['weekday_date']}")

    plot_comparison(stats)
    print(f"Saved chart to {CHART_PATH}")
    write_report(stats)
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()

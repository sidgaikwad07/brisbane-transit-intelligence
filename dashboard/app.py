"""Live Streamlit dashboard for Brisbane Transit Intelligence.

Pulls straight from Postgres — the same dbt marts and raw tables every other
report in this repo is built from — so what you see here is never more than
a few minutes stale, bounded by the poller intervals (GTFS-RT ~60s, traffic
~120s) and the cache TTLs below.

Run it:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "notebooks"))

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from priority_routes import build_priority_table

st.set_page_config(page_title="Brisbane Transit Intelligence", page_icon="🚌", layout="wide")

MODE_COLORS = {"Bus": "#3ea6ff", "Rail": "#ff8a3d", "Ferry": "#2ee6a6", "Tram/Light Rail": "#f5c84c"}
STATUS_COLORS = {"Early": "#3ea6ff", "On-time": "#2ee6a6", "Late": "#ff5c5c", "Unknown": "#5b6472"}
CAUSE_COLORS = {
    "STRIKE": "#ff5c5c",
    "MAINTENANCE": "#f5c84c",
    "CONSTRUCTION": "#f5c84c",
    "HOLIDAY": "#3ea6ff",
    "DEMONSTRATION": "#ff8a3d",
    "OTHER_CAUSE": "#5b6472",
}
BRISBANE_CENTER = {"lat": -27.4698, "lon": 153.0251}
CACHE_TTL_FAST = 60  # live-ish tables (delays, traffic, vehicle positions)
CACHE_TTL_SLOW = 600  # heavier joins (priority routes, demand)

# ── Look & feel ─────────────────────────────────────────────────────────
# Streamlit's default metric/tab/header styling reads as a bare data table.
# This reskins the native components (cards, glow accents, tighter tab
# chrome) rather than replacing them with custom HTML widgets, so behavior
# (hover, responsiveness, dark/light toggle) stays intact.
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.6rem; max-width: 1400px; }

    [data-testid="stMetric"] {
        background: linear-gradient(160deg, rgba(62,166,255,0.10), rgba(255,255,255,0.02));
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 1rem 1rem 0.8rem 1rem;
    }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; opacity: 0.75; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; }

    .hero-banner {
        background: linear-gradient(120deg, rgba(62,166,255,0.16), rgba(46,230,166,0.08));
        border: 1px solid rgba(62,166,255,0.25);
        border-radius: 16px;
        padding: 1.1rem 1.4rem;
        margin-bottom: 1.1rem;
    }
    .hero-banner .kicker { font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.7; }
    .hero-banner .headline { font-size: 1.35rem; font-weight: 700; margin-top: 0.15rem; line-height: 1.4; }

    .insight-box {
        border-left: 4px solid #3ea6ff;
        background: rgba(62,166,255,0.08);
        padding: 0.7rem 1rem;
        border-radius: 0 10px 10px 0;
        margin: 0.4rem 0 1.1rem 0;
        font-size: 0.92rem;
    }
    .insight-box.warn { border-left-color: #ff5c5c; background: rgba(255,92,92,0.08); }
    .insight-box.good { border-left-color: #2ee6a6; background: rgba(46,230,166,0.08); }

    .alert-row {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.55rem 0.8rem;
        border-radius: 8px;
        background: rgba(255,255,255,0.03);
        margin-bottom: 0.35rem;
        font-size: 0.88rem;
    }
    .alert-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    .alert-cause {
        font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em;
        opacity: 0.65; margin-left: auto; padding-left: 1rem; white-space: nowrap;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.03);
        border-radius: 10px 10px 0 0;
        padding: 0.5rem 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def insight(text: str, kind: str = "") -> None:
    css_class = f"insight-box {kind}".strip()
    st.markdown(f'<div class="{css_class}">💡 {text}</div>', unsafe_allow_html=True)


def style_fig(fig: go.Figure, height: int = 380, showlegend: bool | None = None) -> go.Figure:
    """Apply one consistent look to every chart: transparent background so
    it blends into the dashboard theme instead of sitting in a mismatched
    white box, a readable dark-mode font, and recessive gridlines.
    """
    layout_kwargs = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color="#c9d1d9", size=12.5),
        height=height,
        margin=dict(t=45, b=10, l=10, r=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#161b22", font_size=12),
    )
    if showlegend is not None:
        layout_kwargs["showlegend"] = showlegend
    fig.update_layout(**layout_kwargs)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.07)", zerolinecolor="rgba(255,255,255,0.15)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.07)", zerolinecolor="rgba(255,255,255,0.15)")
    return fig


def classify_delay(delay_sec) -> str:
    if pd.isna(delay_sec):
        return "Unknown"
    if delay_sec < -60:
        return "Early"
    if delay_sec <= 300:
        return "On-time"
    return "Late"


@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)


engine = get_engine()


# ── Data loaders ────────────────────────────────────────────────────────


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_collection_window() -> dict:
    df = pd.read_sql("SELECT MIN(polled_at) AS start, MAX(polled_at) AS end FROM raw.trip_updates", engine)
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_citywide_otp() -> dict:
    df = pd.read_sql(
        """
        SELECT
            ROUND(100.0 * SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) / COUNT(*), 1)
                AS on_time_pct,
            COUNT(*) AS n_stop_visits,
            COUNT(DISTINCT trip_id) AS n_trips
        FROM marts.mart_stop_delay
        """,
        engine,
    )
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_bunching_summary() -> dict:
    df = pd.read_sql(
        "SELECT COUNT(*) AS n_events, COUNT(DISTINCT route_id) AS n_routes FROM marts.mart_bunching_events", engine
    )
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_active_alerts() -> pd.DataFrame:
    """Every distinct alert live in the most recent Service Alerts poll —
    this table has been silently accumulating since Week 2 (GTFS-RT alerts
    poll) but nothing in the analysis has read it until now.
    """
    return pd.read_sql(
        """
        WITH latest_poll AS (SELECT MAX(polled_at) AS t FROM raw.service_alerts)
        SELECT sa.header_text, sa.cause, sa.effect, COUNT(DISTINCT sa.route_id) AS n_routes
        FROM raw.service_alerts sa
        CROSS JOIN latest_poll
        WHERE sa.polled_at = latest_poll.t AND sa.header_text IS NOT NULL
        GROUP BY sa.header_text, sa.cause, sa.effect
        ORDER BY n_routes DESC
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_worst_routes(min_trips: int = 5) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT route_short_name AS route, route_long_name, mode, on_time_pct, late_pct, early_pct,
               avg_arrival_delay_sec, n_trips, n_stop_visits
        FROM marts.mart_on_time_performance
        WHERE n_trips >= {min_trips}
        ORDER BY on_time_pct ASC
        LIMIT 15
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_bunching_by_route() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT route_short_name AS route, route_long_name, bunching_observations, last_seen "
        "FROM marts.mart_bunching_by_route ORDER BY bunching_observations DESC LIMIT 15",
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_delay_status_breakdown() -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT
            SUM(CASE WHEN arrival_delay_sec < -60 THEN 1 ELSE 0 END) AS "Early",
            SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) AS "On-time",
            SUM(CASE WHEN arrival_delay_sec > 300 THEN 1 ELSE 0 END) AS "Late"
        FROM marts.mart_stop_delay
        """,
        engine,
    )
    return df.iloc[0].rename_axis("status").reset_index(name="n_stop_visits")


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_mode_share() -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT mode, SUM(n_trips) AS n_trips, SUM(n_stop_visits) AS n_stop_visits, COUNT(*) AS n_routes
        FROM marts.mart_on_time_performance
        GROUP BY mode
        ORDER BY n_trips DESC
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_otp_by_hour() -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT
            EXTRACT(HOUR FROM last_polled_at AT TIME ZONE 'Australia/Brisbane')::int AS hour,
            ROUND(100.0 * SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) / COUNT(*), 1)
                AS on_time_pct,
            COUNT(*) AS n_stop_visits
        FROM marts.mart_stop_delay
        GROUP BY 1
        ORDER BY 1
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_snapshot() -> dict:
    df = pd.read_sql(
        """
        WITH latest AS (SELECT MAX(recorded_at) AS t FROM raw.intersection_traffic)
        SELECT
            recorded_at,
            AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_peak_saturation,
            COUNT(DISTINCT tsc) AS n_intersections,
            COUNT(*) AS n_readings
        FROM raw.intersection_traffic, latest
        WHERE recorded_at = latest.t
        GROUP BY recorded_at
        """,
        engine,
    )
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_trend(hours: int = 6) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT
            date_trunc('minute', recorded_at) AS recorded_at,
            AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_peak_saturation
        FROM raw.intersection_traffic
        WHERE recorded_at > NOW() - INTERVAL '{hours} hours'
        GROUP BY 1
        ORDER BY 1
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_saturation_distribution() -> pd.DataFrame:
    return pd.read_sql(
        """
        WITH latest AS (SELECT MAX(recorded_at) AS t FROM raw.intersection_traffic)
        SELECT GREATEST(ds1, ds2, ds3, ds4) AS peak_saturation
        FROM raw.intersection_traffic, latest
        WHERE recorded_at = latest.t AND GREATEST(ds1, ds2, ds3, ds4) IS NOT NULL
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_weather_recent(days: int = 7) -> pd.DataFrame:
    return pd.read_sql(
        f"SELECT * FROM raw.weather_daily WHERE date > CURRENT_DATE - INTERVAL '{days} days' ORDER BY date",
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_priority_routes() -> pd.DataFrame:
    df, weekday_date, months = build_priority_table(engine)
    return df.head(15)


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_live_delays(minutes: int = 15) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT tu.route_id, r.route_short_name AS route, r.mode,
               tu.arrival_delay_sec, tu.trip_id, tu.stop_id, tu.polled_at
        FROM raw.trip_updates tu
        JOIN staging.stg_routes r ON r.route_id = tu.route_id
        WHERE tu.polled_at > NOW() - INTERVAL '{minutes} minutes' AND tu.arrival_delay_sec IS NOT NULL
        ORDER BY tu.arrival_delay_sec DESC
        LIMIT 5000
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_live_vehicle_map() -> pd.DataFrame:
    """Every vehicle from the most recent poll, matched to its most recently
    known delay (within 10 minutes) so it can be colored by status.
    """
    return pd.read_sql(
        """
        WITH latest_vp AS (SELECT MAX(polled_at) AS t FROM raw.vehicle_positions),
        vp AS (
            SELECT vehicle_id, trip_id, route_id, latitude, longitude, speed, current_stop_id
            FROM raw.vehicle_positions, latest_vp
            WHERE polled_at = latest_vp.t
        ),
        latest_delay AS (
            SELECT DISTINCT ON (trip_id) trip_id, arrival_delay_sec
            FROM raw.trip_updates
            WHERE polled_at > NOW() - INTERVAL '10 minutes' AND arrival_delay_sec IS NOT NULL
            ORDER BY trip_id, polled_at DESC
        )
        SELECT vp.vehicle_id, vp.trip_id, r.route_short_name AS route, r.mode,
               vp.latitude, vp.longitude, vp.speed, ld.arrival_delay_sec
        FROM vp
        JOIN staging.stg_routes r ON r.route_id = vp.route_id
        LEFT JOIN latest_delay ld ON ld.trip_id = vp.trip_id
        WHERE vp.latitude IS NOT NULL AND vp.longitude IS NOT NULL
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_stop_delay_geo(min_visits: int = 8) -> pd.DataFrame:
    """Average delay per stop, geolocated — the live counterpart to
    docs/density_findings.md's static bunching heatmap.
    """
    return pd.read_sql(
        f"""
        SELECT s.stop_id, s.stop_name, s.stop_lat, s.stop_lon,
               AVG(sd.arrival_delay_sec) AS avg_delay_sec, COUNT(*) AS n_visits
        FROM marts.mart_stop_delay sd
        JOIN raw.stops s ON s.stop_id = sd.stop_id
        WHERE s.stop_lat IS NOT NULL AND s.stop_lon IS NOT NULL
        GROUP BY s.stop_id, s.stop_name, s.stop_lat, s.stop_lon
        HAVING COUNT(*) >= {min_visits}
        ORDER BY n_visits DESC
        LIMIT 6000
        """,
        engine,
    )


# ── Sidebar ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🚌 Control panel")
    all_modes = list(MODE_COLORS.keys())
    selected_modes = st.multiselect("Filter by mode", options=all_modes, default=all_modes)
    st.divider()
    st.caption("**Pollers**")
    st.caption("🟢 GTFS-Realtime — every ~60s")
    st.caption("🟢 BCC traffic — every ~120s")
    st.caption(f"Viewed: {datetime.now(tz=timezone.utc):%H:%M:%S} UTC")
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if not selected_modes:
    selected_modes = all_modes

# ── Header ──────────────────────────────────────────────────────────────

st.title("🚌 Brisbane Transit Intelligence")
st.caption(
    "Live from Postgres — GTFS-Realtime, BCC intersection traffic, and daily weather, all polled "
    "continuously. Not a static export."
)

window = load_collection_window()
otp = load_citywide_otp()
bunching = load_bunching_summary()
traffic = load_traffic_snapshot()
otp_hour = load_otp_by_hour()

# Auto-generated headline: the single most actionable live fact, computed
# fresh every load rather than a fixed caption — this is meant to change as
# the data does.
headline = "Collecting data…"
if not otp_hour.empty:
    worst_row = otp_hour.loc[otp_hour["on_time_pct"].idxmin()]
    citywide = otp.get("on_time_pct", 0)
    gap = citywide - worst_row["on_time_pct"]
    headline = (
        f"Reliability is worst around {int(worst_row['hour']):02d}:00 Brisbane time "
        f"({worst_row['on_time_pct']:.0f}% on-time, {gap:.0f} pts below the {citywide:.0f}% citywide average) "
        f"— {int(worst_row['n_stop_visits']):,} stop visits observed in that hour."
    )

st.markdown(
    f"""
    <div class="hero-banner">
        <div class="kicker">Live headline</div>
        <div class="headline">📍 {headline}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if window.get("end") is not None:
    age = pd.Timestamp.now(tz="UTC") - window["end"]
    st.caption(
        f"Delay data collected {window['start']:%Y-%m-%d %H:%M} → {window['end']:%Y-%m-%d %H:%M} UTC "
        f"(last poll {age.total_seconds() / 60:.1f} min ago)"
    )

# ── KPI row ─────────────────────────────────────────────────────────────

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Citywide on-time %", f"{otp.get('on_time_pct', 0):.1f}%")
k2.metric("Trips tracked", f"{int(otp.get('n_trips', 0)):,}")
k3.metric(
    "Bunching events", f"{int(bunching.get('n_events', 0)):,}", help="Vehicles <400m apart, same route, same poll"
)
k4.metric(
    "Peak intersection saturation",
    f"{traffic.get('avg_peak_saturation', 0):.0f}%" if traffic else "—",
    help="Avg of each intersection's busiest lane, most recent poll",
)
k5.metric("Intersections tracked", f"{int(traffic.get('n_intersections', 0)):,}" if traffic else "—")

alerts = load_active_alerts()
with st.expander(f"🚨 {len(alerts)} active service alerts right now", expanded=len(alerts) > 0):
    if alerts.empty:
        st.success("No active service alerts.")
    else:
        top_alerts = alerts.head(20)
        rows_html = ""
        for _, row in top_alerts.iterrows():
            dot_color = CAUSE_COLORS.get(row["cause"], "#5b6472")
            routes_note = f"{int(row['n_routes'])} routes" if row["n_routes"] > 0 else "stop-level"
            rows_html += (
                '<div class="alert-row">'
                f'<span class="alert-dot" style="background:{dot_color}"></span>'
                f"<span>{row['header_text']}</span>"
                f'<span class="alert-cause">{row["cause"].replace("_", " ").title()} · {routes_note}</span>'
                "</div>"
            )
        st.markdown(rows_html, unsafe_allow_html=True)
        if len(alerts) > 20:
            st.caption(f"+{len(alerts) - 20} more, filtered to the 20 affecting the most routes.")
        st.caption(
            "From raw.service_alerts (GTFS-RT), most recent poll — the same feed that shows on "
            "Translink's own journey planner, polled continuously rather than read one page at a time."
        )

c1, c2 = st.columns([1, 2])
with c1:
    st.subheader("Delay status, citywide")
    status = load_delay_status_breakdown()
    fig = px.pie(
        status,
        names="status",
        values="n_stop_visits",
        hole=0.55,
        color="status",
        color_discrete_map=STATUS_COLORS,
        category_orders={"status": ["Early", "On-time", "Late"]},
    )
    fig.update_traces(textinfo="percent+label", sort=False, marker=dict(line=dict(color="#0d1117", width=2)))
    total_visits = int(status["n_stop_visits"].sum())
    style_fig(fig, height=320, showlegend=False)
    fig.update_layout(
        annotations=[dict(text=f"{total_visits:,}<br>stop visits", x=0.5, y=0.5, font_size=14, showarrow=False)]
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption('"On-time" = 1 min early to 5 min late, the common industry convention.')

with c2:
    st.subheader("Trips tracked by mode")
    mode_share = load_mode_share()
    fig = px.bar(
        mode_share,
        x="mode",
        y="n_trips",
        color="mode",
        color_discrete_map=MODE_COLORS,
        text="n_trips",
        labels={"mode": "", "n_trips": "Trips tracked"},
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    style_fig(fig, height=320, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    top_mode = mode_share.iloc[0]
    mode_share_pct = 100 * top_mode["n_trips"] / mode_share["n_trips"].sum()
    insight(
        f"<b>{top_mode['mode']}</b> carries {mode_share_pct:.0f}% of all tracked trips ({int(top_mode['n_trips']):,} "
        f"of {int(mode_share['n_trips'].sum()):,}) — any reliability fix here has the widest reach."
    )

st.divider()

tab_map, tab_live, tab_reliability, tab_priority, tab_traffic = st.tabs(
    ["🗺️ Live map", "🔴 Live delays", "📊 Worst routes & bunching", "🎯 Demand vs reliability", "🚦 Traffic & weather"]
)

# ── Live map ────────────────────────────────────────────────────────────

with tab_map:
    map_mode = st.radio(
        "View",
        ["🚍 Vehicles right now", "🔥 Delay hotspots (all stops)"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if map_mode == "🚍 Vehicles right now":
        vp = load_live_vehicle_map()
        vp = vp[vp["mode"].isin(selected_modes)]
        if vp.empty:
            st.info("No vehicle positions in the most recent poll for the selected modes.")
        else:
            vp = vp.copy()
            vp["status"] = vp["arrival_delay_sec"].apply(classify_delay)
            fig = px.scatter_mapbox(
                vp,
                lat="latitude",
                lon="longitude",
                color="status",
                color_discrete_map=STATUS_COLORS,
                category_orders={"status": ["Early", "On-time", "Late", "Unknown"]},
                hover_name="route",
                hover_data={"mode": True, "speed": ":.0f", "arrival_delay_sec": True, "latitude": False, "longitude": False},
                zoom=9.6,
                center=BRISBANE_CENTER,
                mapbox_style="carto-darkmatter",
            )
            fig.update_traces(marker=dict(size=9, opacity=0.85))
            style_fig(fig, height=560)
            fig.update_layout(legend=dict(orientation="h", y=0.02, x=0.01, bgcolor="rgba(13,17,23,0.6)"))
            st.plotly_chart(fig, use_container_width=True)

            n_late = int((vp["status"] == "Late").sum())
            pct_late = 100 * n_late / len(vp)
            insight(
                f"<b>{n_late} of {len(vp)} vehicles</b> on screen ({pct_late:.0f}%) are running more than 5 minutes "
                "late right now. Hover any dot for its route and live delay.",
                kind="warn" if pct_late > 20 else "",
            )
    else:
        hot = load_stop_delay_geo()
        if hot.empty:
            st.info("Not enough stop-level data yet.")
        else:
            fig = px.scatter_mapbox(
                hot,
                lat="stop_lat",
                lon="stop_lon",
                color="avg_delay_sec",
                color_continuous_scale=["#3ea6ff", "#5b6472", "#ff5c5c"],
                range_color=[-120, 300],
                size="n_visits",
                size_max=11,
                hover_name="stop_name",
                hover_data={"avg_delay_sec": ":.0f", "n_visits": True, "stop_lat": False, "stop_lon": False},
                zoom=9.6,
                center=BRISBANE_CENTER,
                mapbox_style="carto-darkmatter",
            )
            fig.update_traces(marker=dict(opacity=0.75))
            style_fig(fig, height=560)
            fig.update_coloraxes(colorbar=dict(title="Avg delay (s)", bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True)

            worst_stop = hot.loc[hot["avg_delay_sec"].idxmax()]
            insight(
                f"<b>{worst_stop['stop_name']}</b> runs latest on average across the network "
                f"({worst_stop['avg_delay_sec']:.0f}s over {int(worst_stop['n_visits'])} visits). Blue = early, "
                "grey = on-time, red = late — bubble size is how many visits back the estimate.",
            )
        st.caption(
            "Every stop with ≥8 tracked visits, colored by its own average arrival delay. Intersection-level "
            "congestion isn't mapped yet — the BCC feed doesn't carry lat/lon, only a signal-controller ID."
        )

# ── Live delays ─────────────────────────────────────────────────────────

with tab_live:
    live = load_live_delays()
    live = live[live["mode"].isin(selected_modes)]
    if live.empty:
        st.info("No delay data in the last 15 minutes for the selected modes.")
    else:
        as_of = live["polled_at"].max()
        st.caption(
            f"Rolling 15-minute window, most recent poll {as_of:%Y-%m-%d %H:%M:%S} UTC "
            f"— {len(live):,} arrival predictions"
        )

        c1, c2 = st.columns([2, 1])
        with c1:
            fig = px.histogram(
                live,
                x="arrival_delay_sec",
                nbins=60,
                color="mode",
                color_discrete_map=MODE_COLORS,
                labels={"arrival_delay_sec": "Arrival delay (seconds)"},
                title="Arrival delay distribution, last 15 minutes",
            )
            fig.add_vline(x=-60, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            fig.add_vline(x=300, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            style_fig(fig, height=400)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            latest_per_trip = live.sort_values("polled_at").groupby("trip_id", as_index=False).last()
            worst_now = (
                latest_per_trip[latest_per_trip["arrival_delay_sec"] > 300]
                .groupby("route", as_index=False)["arrival_delay_sec"]
                .agg(n_late_now="count", avg_delay_sec="mean")
                .sort_values("n_late_now", ascending=False)
                .head(10)
            )
            st.markdown("**Routes running late right now** (>5 min)")
            if worst_now.empty:
                st.success("No route currently running more than 5 minutes late.")
            else:
                st.dataframe(worst_now.round(0), hide_index=True, use_container_width=True)

        st.subheader("Reliability by time of day")
        if not otp_hour.empty:
            avg_otp = otp.get("on_time_pct", 0)
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=otp_hour["hour"],
                    y=otp_hour["on_time_pct"],
                    mode="lines+markers",
                    line=dict(color="#3ea6ff", width=2.5, shape="spline"),
                    marker=dict(size=6),
                    fill="tozeroy",
                    fillcolor="rgba(62,166,255,0.10)",
                    name="On-time %",
                )
            )
            fig.add_hline(
                y=avg_otp,
                line_dash="dot",
                line_color="rgba(255,255,255,0.4)",
                annotation_text=f"citywide avg {avg_otp:.0f}%",
                annotation_position="top left",
            )
            style_fig(fig, height=320, showlegend=False)
            fig.update_layout(
                xaxis=dict(title="Hour of day (Brisbane time)", dtick=2, range=[-0.5, 23.5]),
                yaxis=dict(title="On-time %", range=[0, 100]),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "On-time % of all tracked stop visits, binned by hour of day and aggregated across the "
                "whole collection window — shows the diurnal pattern rather than a single day's noise."
            )

# ── Worst routes & bunching ─────────────────────────────────────────────

with tab_reliability:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Least reliable routes")
        worst = load_worst_routes()
        worst = worst[worst["mode"].isin(selected_modes)].sort_values("on_time_pct", ascending=False)
        if worst.empty:
            st.info("No routes match the selected modes.")
        else:
            long_names = dict(zip(worst["route"], worst["route_long_name"]))
            melted = worst.melt(
                id_vars=["route"], value_vars=["early_pct", "on_time_pct", "late_pct"], var_name="status", value_name="pct"
            )
            melted["status"] = melted["status"].map({"early_pct": "Early", "on_time_pct": "On-time", "late_pct": "Late"})
            melted["route_long_name"] = melted["route"].map(long_names)
            fig = px.bar(
                melted,
                x="pct",
                y="route",
                color="status",
                orientation="h",
                color_discrete_map=STATUS_COLORS,
                category_orders={"status": ["Early", "On-time", "Late"], "route": worst["route"].tolist()},
                labels={"pct": "Share of stop visits (%)", "route": "Route"},
                hover_data=["route_long_name"],
            )
            style_fig(fig, height=500)
            fig.update_layout(barmode="stack", legend_title=None)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Filtered to routes with ≥5 tracked trips, to avoid one bad run skewing a thin sample.")
            bottom = worst.iloc[-1]
            insight(
                f"<b>Route {bottom['route']}</b> ({bottom['route_long_name']}) is the least reliable route tracked: "
                f"on-time only {bottom['on_time_pct']:.0f}% of {int(bottom['n_trips'])} trips, "
                f"{bottom['late_pct']:.0f}% running more than 5 minutes late.",
                kind="warn",
            )

    with c2:
        st.subheader("Most bunched routes")
        bunch = load_bunching_by_route()
        if bunch.empty:
            st.info("No bunching detected in the current window.")
        else:
            fig = px.bar(
                bunch.sort_values("bunching_observations"),
                x="bunching_observations",
                y="route",
                orientation="h",
                labels={"bunching_observations": "Bunching observations", "route": "Route"},
                hover_data=["route_long_name"],
            )
            fig.update_traces(marker_color="#ff8a3d")
            style_fig(fig, height=500, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            top_bunch = bunch.iloc[0]
            insight(
                f"<b>Route {top_bunch['route']}</b> ({top_bunch['route_long_name']}) has bunched "
                f"{int(top_bunch['bunching_observations']):,} times — vehicles running so close together they're "
                "effectively one service, doubling the wait for whoever's behind them."
            )
        st.caption("Two vehicles on the same route within 400m in the same poll.")

# ── Demand vs reliability ───────────────────────────────────────────────

with tab_priority:
    st.subheader("Where real demand and poor reliability overlap")
    st.caption(
        "Crosses Queensland Government origin-destination ridership against measured on-time "
        "performance — the routes here affect the most riders per late arrival, citywide."
    )
    priority = load_priority_routes()
    priority_f = priority[priority["mode"].isin(selected_modes)]

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.scatter(
            priority_f,
            x="demand_pctile",
            y="otp_pctile",
            size="avg_weekday_riders",
            color="mode",
            color_discrete_map=MODE_COLORS,
            hover_name="route",
            hover_data={"route_long_name": True, "avg_weekday_riders": ":.0f", "on_time_pct": ":.1f"},
            labels={"demand_pctile": "Demand percentile", "otp_pctile": "On-time percentile"},
        )
        fig.add_vrect(x0=70, x1=100, y0=0, y1=30, fillcolor="rgba(255,92,92,0.08)", line_width=0)
        style_fig(fig, height=450)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Shaded corner: high demand, low reliability — the routes that need attention most.")
    with c2:
        top10 = priority_f.sort_values("priority_score", ascending=False).head(10).iloc[::-1]
        fig = px.bar(
            top10,
            x="priority_score",
            y="route",
            orientation="h",
            color="mode",
            color_discrete_map=MODE_COLORS,
            labels={"priority_score": "Priority score", "route": "Route"},
            hover_data=["route_long_name"],
        )
        style_fig(fig, height=450, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("demand_pctile × (100 − otp_pctile) — highest first.")

    if not priority_f.empty:
        top = priority_f.sort_values("priority_score", ascending=False).iloc[0]
        insight(
            f"<b>Route {top['route']}</b> ({top['route_long_name']}) tops the priority list: "
            f"{top['avg_weekday_riders']:.0f} riders/weekday at the {top['demand_pctile']:.0f}th percentile of "
            f"demand, but only {top['on_time_pct']:.0f}% on-time ({top['otp_pctile']:.0f}th percentile of "
            "reliability, citywide)."
        )

    st.dataframe(
        priority_f[["route", "route_long_name", "mode", "avg_weekday_riders", "on_time_pct", "priority_score"]].round(1),
        hide_index=True,
        use_container_width=True,
    )

# ── Traffic & weather ────────────────────────────────────────────────────

with tab_traffic:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Intersection congestion trend")
        trend = load_traffic_trend()
        if trend.empty:
            st.info("Traffic poller has just started — trend will fill in over the next few polls.")
        else:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=trend["recorded_at"],
                    y=trend["avg_peak_saturation"],
                    mode="lines",
                    line=dict(color="#3ea6ff", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(62,166,255,0.08)",
                )
            )
            style_fig(fig, height=300, showlegend=False)
            fig.update_layout(yaxis_title="Avg peak-lane saturation (%)", xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Degree of saturation on each intersection's busiest approach lane, averaged citywide. "
            "The BCC feed is a rolling ~5-minute window with no history, so this trend only covers "
            "time since the poller started."
        )

        st.subheader("Congestion right now, all intersections")
        sat_dist = load_traffic_saturation_distribution()
        if sat_dist.empty:
            st.info("No traffic readings yet.")
        else:
            fig = px.histogram(
                sat_dist, x="peak_saturation", nbins=40, labels={"peak_saturation": "Peak-lane saturation (%)"}
            )
            fig.update_traces(marker_color="#3ea6ff")
            style_fig(fig, height=280, showlegend=False)
            fig.update_layout(yaxis_title="Lanes")
            st.plotly_chart(fig, use_container_width=True)
            pct_congested = 100 * (sat_dist["peak_saturation"] > 80).mean()
            insight(f"{pct_congested:.0f}% of tracked lanes are currently above 80% saturation (near/at capacity).")
        st.caption(f"{len(sat_dist):,} lane readings from the most recent traffic poll.")

    with c2:
        st.subheader("Recent weather")
        weather = load_weather_recent()
        if weather.empty:
            st.info("No weather data yet — run `python -m ingestion.weather`.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=weather["date"], y=weather["rainfall_mm"], name="Rainfall (mm)", marker_color="#3ea6ff"))
            fig.add_trace(
                go.Scatter(
                    x=weather["date"], y=weather["temp_max_c"], name="Max temp (°C)", yaxis="y2", line_color="#ff8a3d"
                )
            )
            style_fig(fig, height=300)
            fig.update_layout(
                yaxis=dict(title="Rainfall (mm)"),
                yaxis2=dict(title="Max temp (°C)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.15),
            )
            st.plotly_chart(fig, use_container_width=True)
            rainiest = weather.loc[weather["rainfall_mm"].idxmax()]
            if rainiest["rainfall_mm"] > 0:
                insight(
                    f"Wettest day in this window: <b>{rainiest['date']}</b> with {rainiest['rainfall_mm']:.1f}mm — "
                    "worth checking against that day's on-time performance once the delay-prediction model is built."
                )
        st.caption(
            "Daily Brisbane observations from Open-Meteo. Feeds the delay-prediction model once "
            "it's built (next step)."
        )

st.divider()
st.caption(
    "Brisbane Transit Intelligence — all data public (Translink GTFS/GTFS-RT, Brisbane City Council "
    "open data, Queensland Government open data, Open-Meteo). Not affiliated with Translink or BCC."
)

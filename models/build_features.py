"""Build the training table for the delay-prediction model: one row per
tracked (trip, stop) arrival, joined against nearby traffic congestion and
that day's weather.

Two joins, deliberately different shapes:
  - Spatial (traffic): raw.intersection_traffic has no lat/lon of its own —
    only a signal-controller id (tsc). raw.traffic_signal_locations (a
    one-time pull, see ingestion/traffic_signal_locations.py) is the lookup
    that makes a PostGIS ST_DWithin join possible: every stop's nearby
    signals (400m), then that signal's congestion in the same 30-minute
    bucket as the scheduled arrival. Time-bucketed rather than nearest-poll,
    because the traffic feed updates in irregular batches (confirmed while
    building ingestion/bcc_traffic.py) — matching to the nearest single poll
    would be noisier than averaging within a half-hour window.
  - Temporal (weather): a plain date join, since weather is daily-grain.

Scoped to the traffic-data collection window only (from TRAFFIC_START) —
BCC's feed has no history before the poller started, so this is the only
period where a delay observation can have a real traffic reading.

Usage:
    python models/build_features.py                # writes data/exports/delay_features.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

OUT_PATH = REPO_ROOT / "data" / "exports" / "delay_features.csv"

# The earliest date raw.intersection_traffic actually has data from —
# confirmed via `SELECT min(recorded_at) FROM raw.intersection_traffic`.
# Not derived automatically so this stays stable across reruns even as the
# traffic table grows forward.
TRAFFIC_START = "2026-09-25"
SIGNAL_RADIUS_M = 400
TIME_BUCKET_MIN = 30

FEATURE_QUERY = f"""
WITH disruption_alerts AS (
    -- System-wide count of active REDUCED_SERVICE/SIGNIFICANT_DELAYS alerts
    -- per hour — route/hour/day-of-week alone can't tell the model "there's
    -- a strike on right now," and delay behaves very differently when one
    -- is (see docs/delay_model_card.md for how much this mattered).
    SELECT
        date_trunc('hour', polled_at) AS hour_bucket,
        COUNT(DISTINCT alert_id) FILTER (WHERE effect IN ('REDUCED_SERVICE', 'SIGNIFICANT_DELAYS')) AS n_disruption_alerts
    FROM raw.service_alerts
    GROUP BY hour_bucket
),
nearby_signals AS (
    SELECT s.stop_id, t.tsc
    FROM raw.stops s
    JOIN raw.traffic_signal_locations t
      ON ST_DWithin(s.geom::geography, t.geom::geography, {SIGNAL_RADIUS_M})
),
traffic_bucketed AS (
    SELECT
        tsc,
        date_trunc('hour', recorded_at AT TIME ZONE 'Australia/Brisbane')
            + floor(date_part('minute', recorded_at AT TIME ZONE 'Australia/Brisbane') / {TIME_BUCKET_MIN})
              * interval '{TIME_BUCKET_MIN} min' AS time_bucket,
        AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_saturation
    FROM raw.intersection_traffic
    GROUP BY tsc, time_bucket
),
stop_traffic_bucketed AS (
    SELECT ns.stop_id, tb.time_bucket, AVG(tb.avg_saturation) AS local_saturation, COUNT(*) AS n_signals
    FROM nearby_signals ns
    JOIN traffic_bucketed tb ON tb.tsc = ns.tsc
    GROUP BY ns.stop_id, tb.time_bucket
)
SELECT
    sd.trip_id,
    sd.route_id,
    r.mode,
    sd.stop_id,
    sd.arrival_delay_sec,
    sd.scheduled_arrival,
    EXTRACT(HOUR FROM sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane')::int AS hour,
    EXTRACT(ISODOW FROM sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane')::int AS day_of_week,
    (EXTRACT(ISODOW FROM sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane') >= 6) AS is_weekend,
    stt.local_saturation,
    stt.n_signals,
    w.rainfall_mm,
    w.temp_max_c,
    w.wind_kph,
    COALESCE(da.n_disruption_alerts, 0) AS n_disruption_alerts
FROM marts.mart_stop_delay sd
JOIN staging.stg_routes r ON r.route_id = sd.route_id
LEFT JOIN stop_traffic_bucketed stt
    ON stt.stop_id = sd.stop_id
   AND stt.time_bucket = date_trunc('hour', sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane')
       + floor(date_part('minute', sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane') / {TIME_BUCKET_MIN})
         * interval '{TIME_BUCKET_MIN} min'
LEFT JOIN raw.weather_daily w ON w.date = date(sd.scheduled_arrival AT TIME ZONE 'Australia/Brisbane')
LEFT JOIN disruption_alerts da ON da.hour_bucket = date_trunc('hour', sd.scheduled_arrival)
WHERE sd.scheduled_arrival >= '{TRAFFIC_START}' AND sd.scheduled_arrival IS NOT NULL
"""


def build_features(engine) -> pd.DataFrame:
    df = pd.read_sql(FEATURE_QUERY, engine)
    df["is_late"] = df["arrival_delay_sec"] > 300
    df["has_nearby_signal"] = df["local_saturation"].notna()
    return df


def main() -> None:
    engine = create_engine(DATABASE_URL)
    df = build_features(engine)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    n = len(df)
    n_signal = int(df["has_nearby_signal"].sum())
    print(f"Built {n:,} feature rows ({df['scheduled_arrival'].min()} to {df['scheduled_arrival'].max()})")
    print(f"  {n_signal:,} ({100 * n_signal / n:.0f}%) have a traffic signal within {SIGNAL_RADIUS_M}m")
    print(f"  {int(df['is_late'].sum()):,} ({100 * df['is_late'].mean():.1f}%) are >5min late")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()

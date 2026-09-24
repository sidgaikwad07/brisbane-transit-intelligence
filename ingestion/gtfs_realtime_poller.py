"""Poll Translink's GTFS-Realtime feeds (Trip Updates, Vehicle Positions,
Service Alerts) and append every poll to Postgres.

This is deliberately append-only, not upsert-on-trip: every poll writes a
fresh snapshot row per entity, timestamped by `polled_at`. That's what makes
Week 2's "measure our own on-time performance and headway" possible later —
comparing GTFS static's scheduled time against the *sequence* of predicted
times a trip_update carried over its lifetime, not just its last value.

Usage:
    python -m ingestion.gtfs_realtime_poller                  # poll forever, Ctrl+C to stop
    python -m ingestion.gtfs_realtime_poller --once            # single poll, for testing
    python -m ingestion.gtfs_realtime_poller --interval 30     # poll every 30s (default 60s)
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ingestion.config import (
    DATABASE_URL,
    GTFS_RT_ALERTS_URL,
    GTFS_RT_TRIP_UPDATES_URL,
    GTFS_RT_VEHICLE_POSITIONS_URL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 60
REQUEST_TIMEOUT_SEC = 20


def fetch_feed(url: str) -> gtfs_realtime_pb2.FeedMessage:
    resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def _epoch_to_dt(epoch: int) -> datetime | None:
    return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None


def _event_delay(event) -> int | None:
    return event.delay if event.HasField("delay") else None


def _event_time(event) -> int | None:
    return event.time if event.HasField("time") else None


def parse_trip_updates(feed: gtfs_realtime_pb2.FeedMessage, polled_at: datetime) -> pd.DataFrame:
    rows = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        route_id = tu.trip.route_id or None
        for stu in tu.stop_time_update:
            arrival_delay = _event_delay(stu.arrival) if stu.HasField("arrival") else None
            arrival_time = _event_time(stu.arrival) if stu.HasField("arrival") else None
            departure_delay = _event_delay(stu.departure) if stu.HasField("departure") else None
            rows.append(
                {
                    "polled_at": polled_at,
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "stop_id": stu.stop_id or None,
                    "stop_sequence": stu.stop_sequence or None,
                    "arrival_delay_sec": arrival_delay,
                    "departure_delay_sec": departure_delay,
                    "scheduled_arrival": (
                        _epoch_to_dt(arrival_time - arrival_delay)
                        if arrival_time is not None and arrival_delay is not None
                        else None
                    ),
                    "predicted_arrival": _epoch_to_dt(arrival_time) if arrival_time is not None else None,
                }
            )
    return pd.DataFrame(rows)


def parse_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage, polled_at: datetime) -> pd.DataFrame:
    rows = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        rows.append(
            {
                "polled_at": polled_at,
                "vehicle_id": v.vehicle.id or None,
                "trip_id": v.trip.trip_id or None,
                "route_id": v.trip.route_id or None,
                "latitude": v.position.latitude if v.HasField("position") else None,
                "longitude": v.position.longitude if v.HasField("position") else None,
                "bearing": (
                    v.position.bearing if v.HasField("position") and v.position.HasField("bearing") else None
                ),
                "speed": v.position.speed if v.HasField("position") and v.position.HasField("speed") else None,
                "current_stop_id": v.stop_id or None,
                "vehicle_timestamp": _epoch_to_dt(v.timestamp) if v.timestamp else None,
            }
        )
    return pd.DataFrame(rows)


_CAUSE_NAMES = gtfs_realtime_pb2.Alert.Cause.DESCRIPTOR.values_by_number
_EFFECT_NAMES = gtfs_realtime_pb2.Alert.Effect.DESCRIPTOR.values_by_number


def parse_service_alerts(feed: gtfs_realtime_pb2.FeedMessage, polled_at: datetime) -> pd.DataFrame:
    """One row per (alert, informed route or stop) — an alert with several
    informed_entity values (a whole line, several stops) is flattened rather
    than dropped down to a single route_id/stop_id.
    """
    rows = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        header = alert.header_text.translation[0].text if alert.header_text.translation else None
        description = alert.description_text.translation[0].text if alert.description_text.translation else None
        cause = _CAUSE_NAMES.get(alert.cause).name if alert.cause in _CAUSE_NAMES else None
        effect = _EFFECT_NAMES.get(alert.effect).name if alert.effect in _EFFECT_NAMES else None

        informed = [(ie.route_id or None, ie.stop_id or None) for ie in alert.informed_entity]
        if not informed:
            informed = [(None, None)]
        for route_id, stop_id in informed:
            rows.append(
                {
                    "polled_at": polled_at,
                    "alert_id": entity.id,
                    "route_id": route_id,
                    "stop_id": stop_id,
                    "cause": cause,
                    "effect": effect,
                    "header_text": header,
                    "description": description,
                }
            )
    return pd.DataFrame(rows)


def write_rows(engine: Engine, table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    df.to_sql(table, engine, schema="raw", if_exists="append", index=False, method="multi", chunksize=2000)
    return len(df)


def poll_once(engine: Engine) -> dict[str, int]:
    polled_at = datetime.now(tz=timezone.utc)
    counts = {}

    try:
        tu_feed = fetch_feed(GTFS_RT_TRIP_UPDATES_URL)
        counts["trip_updates"] = write_rows(engine, "trip_updates", parse_trip_updates(tu_feed, polled_at))
    except Exception:
        log.exception("Trip Updates poll failed")
        counts["trip_updates"] = -1

    try:
        vp_feed = fetch_feed(GTFS_RT_VEHICLE_POSITIONS_URL)
        counts["vehicle_positions"] = write_rows(
            engine, "vehicle_positions", parse_vehicle_positions(vp_feed, polled_at)
        )
    except Exception:
        log.exception("Vehicle Positions poll failed")
        counts["vehicle_positions"] = -1

    try:
        alerts_feed = fetch_feed(GTFS_RT_ALERTS_URL)
        counts["service_alerts"] = write_rows(engine, "service_alerts", parse_service_alerts(alerts_feed, polled_at))
    except Exception:
        log.exception("Service Alerts poll failed")
        counts["service_alerts"] = -1

    return counts


def _handle_sigterm(signum, frame) -> None:
    # Only SIGINT (Ctrl+C) is a KeyboardInterrupt by default. Running as a
    # launchd service means stop/restart cycles send SIGTERM instead — raise
    # the same exception so it takes the identical clean-shutdown path
    # (log the summary, exit 0) rather than being killed mid-request.
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Poll a single time and exit (for testing)")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    log.info("Starting GTFS-RT poller (interval=%ss)", args.interval)

    n_polls = 0
    totals = {"trip_updates": 0, "vehicle_positions": 0, "service_alerts": 0}
    try:
        while True:
            start = time.monotonic()
            counts = poll_once(engine)
            n_polls += 1
            for k, v in counts.items():
                if v >= 0:
                    totals[k] += v
            log.info(
                "Poll #%d: trip_updates=%d vehicle_positions=%d service_alerts=%d",
                n_polls,
                counts["trip_updates"],
                counts["vehicle_positions"],
                counts["service_alerts"],
            )

            if args.once:
                break

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        pass
    finally:
        log.info(
            "Stopped after %d polls. Totals: trip_updates=%d vehicle_positions=%d service_alerts=%d",
            n_polls,
            totals["trip_updates"],
            totals["vehicle_positions"],
            totals["service_alerts"],
        )


if __name__ == "__main__":
    main()

from datetime import datetime, timezone

from google.transit import gtfs_realtime_pb2

from ingestion.gtfs_realtime_poller import parse_alert_periods

POLLED_AT = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)


def _feed(*alerts):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    for alert_id, periods in alerts:
        entity = feed.entity.add(id=alert_id)
        entity.alert.header_text.translation.add(text="Weekend track closure")
        for start, end in periods:
            period = entity.alert.active_period.add()
            if start:
                period.start = start
            if end:
                period.end = end
    return feed


def test_one_row_per_period():
    feed = _feed(("track", [(1760040000, 1760184000), (1760644800, 1760788800)]), ("lift", [(1760040000, 0)]))
    df = parse_alert_periods(feed, POLLED_AT)
    assert df["alert_id"].tolist() == ["track", "track", "lift"]
    assert df.loc[0, "period_start"] == datetime.fromtimestamp(1760040000, tz=timezone.utc)


def test_open_ended_period_is_null():
    df = parse_alert_periods(_feed(("lift", [(1760040000, 0)])), POLLED_AT)
    assert df.loc[0, "period_end"] is None


def test_alert_without_periods_writes_nothing():
    df = parse_alert_periods(_feed(("always", [])), POLLED_AT)
    assert df.empty
    assert list(df.columns) == ["polled_at", "alert_id", "period_start", "period_end"]

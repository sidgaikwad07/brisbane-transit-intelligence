import datetime as dt

import pandas as pd

from ingestion.service_calendar import active_service_ids, complete_schedule_end, pick_representative_date


def _calendar_row(service_id, start, end, days="1111100"):
    dows = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    row = {"service_id": service_id, "start_date": start, "end_date": end}
    row.update({d: flag == "1" for d, flag in zip(dows, days)})
    return row


def test_active_service_ids_respects_date_range():
    calendar = pd.DataFrame(
        [
            _calendar_row("term1", dt.date(2026, 1, 1), dt.date(2026, 3, 31)),
            _calendar_row("term2", dt.date(2026, 4, 1), dt.date(2026, 6, 30)),
        ]
    )
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])

    assert active_service_ids(calendar, calendar_dates, dt.date(2026, 2, 2)) == {"term1"}
    assert active_service_ids(calendar, calendar_dates, dt.date(2026, 4, 2)) == {"term2"}


def test_active_service_ids_applies_exceptions():
    calendar = pd.DataFrame([_calendar_row("weekday", dt.date(2026, 1, 1), dt.date(2026, 12, 31))])
    calendar_dates = pd.DataFrame(
        [
            {"service_id": "weekday", "date": dt.date(2026, 1, 26), "exception_type": 2},  # removed
            {"service_id": "public_holiday_extra", "date": dt.date(2026, 1, 26), "exception_type": 1},  # added
        ]
    )

    active = active_service_ids(calendar, calendar_dates, dt.date(2026, 1, 26))
    assert active == {"public_holiday_extra"}


def test_active_service_ids_overlapping_windows_not_double_counted_by_caller():
    # Two calendar rows for the "same" weekday pattern with overlapping
    # windows — the real-world shape this module exists to handle. Both are
    # legitimately active on an overlap date; it's the caller's job (using
    # one representative date) not to sum both a Monday-flagged filter AND
    # a date-unaware one.
    calendar = pd.DataFrame(
        [
            _calendar_row("base", dt.date(2026, 9, 17), dt.date(2026, 11, 16)),
            _calendar_row("term_override", dt.date(2026, 9, 21), dt.date(2026, 10, 2)),
        ]
    )
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])

    assert active_service_ids(calendar, calendar_dates, dt.date(2026, 9, 22)) == {"base", "term_override"}
    assert active_service_ids(calendar, calendar_dates, dt.date(2026, 10, 20)) == {"base"}


def test_pick_representative_date_matches_median_not_outlier():
    # Every Tuesday runs "steady" (20 trips) except one that gets an extra
    # service added (40 trips) — the representative pick should land on a
    # "steady" Tuesday, not the outlier.
    calendar = pd.DataFrame(
        [
            _calendar_row("steady", dt.date(2026, 9, 1), dt.date(2026, 9, 30)),
        ]
    )
    calendar_dates = pd.DataFrame(
        [{"service_id": "extra", "date": dt.date(2026, 9, 8), "exception_type": 1}]
    )
    trips_per_service = pd.Series({"steady": 20, "extra": 20})

    picked = pick_representative_date(calendar, calendar_dates, trips_per_service, ("Tuesday",))
    assert picked != dt.date(2026, 9, 8)
    assert picked.strftime("%A") == "Tuesday"


def test_complete_schedule_end_stops_where_one_mode_runs_out():
    # Sydney's real shape: buses published to December, trains only to
    # October; a rail-replacement bus (714) that stops early is ignored.
    calendar = pd.DataFrame(
        [
            _calendar_row("bus", dt.date(2026, 10, 1), dt.date(2026, 12, 31), "1111111"),
            _calendar_row("rail", dt.date(2026, 10, 1), dt.date(2026, 10, 28), "1111111"),
            _calendar_row("trackwork", dt.date(2026, 10, 1), dt.date(2026, 10, 4), "1111111"),
        ]
    )
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])
    trips = pd.DataFrame(
        [
            {"service_id": "bus", "route_type": 700, "n": 1000},
            {"service_id": "rail", "route_type": 2, "n": 300},
            {"service_id": "trackwork", "route_type": 714, "n": 50},
        ]
    )

    assert complete_schedule_end(calendar, calendar_dates, trips) == dt.date(2026, 10, 28)


def test_complete_schedule_end_catches_a_partial_drop():
    # Melbourne's real shape: one bus operator's timetable stops at the end of
    # October, so bus trips fall ~20% (not to zero) from November.
    calendar = pd.DataFrame(
        [
            _calendar_row("bus_a", dt.date(2026, 10, 1), dt.date(2026, 12, 31), "1111111"),
            _calendar_row("bus_b", dt.date(2026, 10, 1), dt.date(2026, 10, 31), "1111111"),
            _calendar_row("tram", dt.date(2026, 10, 1), dt.date(2026, 12, 31), "1111111"),
        ]
    )
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])
    trips = pd.DataFrame(
        [
            {"service_id": "bus_a", "route_type": 3, "n": 800},
            {"service_id": "bus_b", "route_type": 3, "n": 200},
            {"service_id": "tram", "route_type": 0, "n": 300},
        ]
    )

    assert complete_schedule_end(calendar, calendar_dates, trips) == dt.date(2026, 10, 31)


def test_complete_schedule_end_judges_sundays_against_sundays():
    # Sunday service at ~40% of weekday is normal, not a truncated timetable.
    calendar = pd.DataFrame(
        [
            _calendar_row("weekday", dt.date(2026, 10, 1), dt.date(2026, 12, 31), "1111110"),
            _calendar_row("sunday", dt.date(2026, 10, 1), dt.date(2026, 12, 31), "0000001"),
        ]
    )
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])
    trips = pd.DataFrame(
        [
            {"service_id": "weekday", "route_type": 3, "n": 1000},
            {"service_id": "sunday", "route_type": 3, "n": 400},
        ]
    )

    assert complete_schedule_end(calendar, calendar_dates, trips) == dt.date(2026, 12, 31)


def test_pick_representative_date_respects_end():
    calendar = pd.DataFrame([_calendar_row("weekday", dt.date(2026, 10, 1), dt.date(2026, 12, 31))])
    calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])
    trips_per_service = pd.Series({"weekday": 10})

    picked = pick_representative_date(
        calendar, calendar_dates, trips_per_service, ("Tuesday",), end=dt.date(2026, 10, 28)
    )
    assert picked <= dt.date(2026, 10, 28)

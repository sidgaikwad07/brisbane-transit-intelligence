import datetime as dt

import pandas as pd

from ingestion.service_calendar import active_service_ids, pick_representative_date


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

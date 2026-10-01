"""Resolve GTFS `calendar` + `calendar_dates` into the service_ids that
actually run on one concrete date, and pick representative dates for
"typical weekday" / "typical Saturday" / "typical Sunday" summaries.

Why this exists: a naive `calendar.monday = true` filter with no date
restriction counts every service_id whose weekly pattern includes Monday,
regardless of which date range it's valid for. Real-world feeds — this one
included — routinely republish the same physical service under several
service_ids with staggered, overlapping validity windows (e.g. one calendar
row per school term, or a mid-feed timetable correction that duplicates an
existing pattern under a new id for part of its range). Translink's SEQ
feed does this heavily: of 77 calendar rows flagged `monday = true`, only
~28 are actually valid on any single real Tuesday — so the naive filter
overstates trip counts several-fold on some corridors.

Resolving service_ids for one concrete date, per GTFS's own semantics
(calendar date range + weekday flag, adjusted by calendar_dates
exceptions), avoids that. `pick_representative_date` then picks a single
date to summarize a whole feed by, chosen to be "typical" (its total
scheduled-trip count sits at the median across all candidate dates) rather
than arbitrary — so results don't depend on what "today" happens to be, and
aren't skewed by a one-off public holiday or school-holiday date landing in
the sample.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

DOW_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def active_service_ids(
    calendar: pd.DataFrame, calendar_dates: pd.DataFrame, target_date: dt.date
) -> set[str]:
    """Service ids actually operating on `target_date`: calendar rows whose
    [start_date, end_date] covers it and whose day-of-week flag is set,
    minus calendar_dates removals (exception_type=2), plus additions
    (exception_type=1).
    """
    dow_col = DOW_COLUMNS[target_date.weekday()]
    base = calendar.loc[
        (calendar["start_date"] <= target_date)
        & (calendar["end_date"] >= target_date)
        & (calendar[dow_col]),
        "service_id",
    ]
    day_exceptions = calendar_dates[calendar_dates["date"] == target_date]
    removed = day_exceptions.loc[day_exceptions["exception_type"] == 2, "service_id"]
    added = day_exceptions.loc[day_exceptions["exception_type"] == 1, "service_id"]
    return (set(base) - set(removed)) | set(added)


def trip_counts_by_date(
    calendar: pd.DataFrame,
    calendar_dates: pd.DataFrame,
    trips_per_service: pd.Series,
    dates: list[dt.date],
) -> pd.Series:
    """Total scheduled-trip count for each candidate date: the sum of
    `trips_per_service` over that date's active service_ids.
    """
    counts = {
        d: trips_per_service.reindex(list(active_service_ids(calendar, calendar_dates, d))).fillna(0).sum()
        for d in dates
    }
    return pd.Series(counts)


# Extended GTFS route_types that are temporary or seasonal by definition,
# so their timetable ending early isn't a sign of an incomplete feed.
NON_REGULAR_ROUTE_TYPES = (
    712,  # school bus — stops for school holidays
    714,  # rail replacement bus — runs only around planned trackwork
)


def complete_schedule_end(
    calendar: pd.DataFrame, calendar_dates: pd.DataFrame, trips_per_service_type: pd.DataFrame
) -> dt.date:
    """Last date on which every regular mode in the feed still has its full
    timetable published.

    Why this exists: a feed's calendar can span months while one operator
    only publishes a few weeks ahead. Transport for NSW's feed runs to late
    December, but Sydney Trains' timetable stops at the end of October —
    after that only ~170 of ~3,200 daily rail trips remain. Picking a
    "typical" date from the whole span then silently drops an entire mode.

    `trips_per_service_type` has columns service_id, route_type, n. A mode's
    timetable counts as complete on a date while its daily trip count is at
    least half its peak. Temporary/seasonal modes (NON_REGULAR_ROUTE_TYPES)
    are ignored. Rules based on the counts alone can't tell them apart:
    Sydney Trains, complete for one month of three, looks just as
    "temporary" as a weekend of rail-replacement buses.
    """
    dates = pd.date_range(calendar["start_date"].min(), calendar["end_date"].max()).date
    daily = pd.DataFrame(
        {
            d: trips_per_service_type[
                trips_per_service_type["service_id"].isin(active_service_ids(calendar, calendar_dates, d))
            ]
            .groupby("route_type")["n"]
            .sum()
            for d in dates
        }
    ).T.fillna(0)
    peak = daily.max()
    regular = [rt for rt in daily.columns if rt not in NON_REGULAR_ROUTE_TYPES]
    return min(daily.index[daily[rt] >= 0.5 * peak[rt]].max() for rt in regular)


def pick_representative_date(
    calendar: pd.DataFrame,
    calendar_dates: pd.DataFrame,
    trips_per_service: pd.Series,
    weekday_names: tuple[str, ...],
    end: dt.date | None = None,
) -> dt.date:
    """The date, among all `weekday_names` dates spanned by `calendar` (up
    to `end`, if given), whose total scheduled-trip count is closest to the
    median across all of them. A single "typical" date — robust to a
    one-off public-holiday or school-holiday calendar artifact landing in
    the sample, and independent of what "today" is.
    """
    start = calendar["start_date"].min()
    end = min(end, calendar["end_date"].max()) if end else calendar["end_date"].max()
    candidates = [d for d in pd.date_range(start, end).date if d.strftime("%A") in weekday_names]
    counts = trip_counts_by_date(calendar, calendar_dates, trips_per_service, candidates)
    return counts.sub(counts.median()).abs().idxmin()


def representative_dates(
    calendar: pd.DataFrame,
    calendar_dates: pd.DataFrame,
    trips_per_service: pd.Series,
    end: dt.date | None = None,
) -> dict[str, dt.date]:
    """Typical weekday / Saturday / Sunday dates for this feed. Weekday is
    matched over Tuesday-Thursday only, since Monday and Friday are more
    likely to sit next to a long-weekend public holiday. Pass `end` (see
    `complete_schedule_end`) for multi-operator feeds whose operators
    publish different distances ahead.
    """
    return {
        "weekday": pick_representative_date(
            calendar, calendar_dates, trips_per_service, ("Tuesday", "Wednesday", "Thursday"), end
        ),
        "saturday": pick_representative_date(calendar, calendar_dates, trips_per_service, ("Saturday",), end),
        "sunday": pick_representative_date(calendar, calendar_dates, trips_per_service, ("Sunday",), end),
    }

from datetime import datetime, timezone

from ingestion.bcc_traffic import parse_records


def _record(**overrides):
    base = {
        "dbid": "5034223115",
        "recorded": "2026-09-25T11:38:00+00:00",
        "ct": "70",
        "ss": "499",
        "tsc": "499",
        "lane": "SA-7",
        "ds1": "41",
        "mf1": "3",
        "rf1": "3",
        "ds2": None,
        "mf2": None,
        "rf2": None,
        "ds3": None,
        "mf3": None,
        "rf3": None,
        "ds4": None,
        "mf4": None,
        "rf4": None,
    }
    base.update(overrides)
    return base


def test_parse_records_maps_fields_and_types():
    df = parse_records([_record()], fetched_at=datetime.now(tz=timezone.utc))
    row = df.iloc[0]
    assert row["dbid"] == "5034223115"
    assert row["tsc"] == "499"
    assert row["lane"] == "SA-7"
    assert row["cycle_time_sec"] == 70
    assert row["ds1"] == 41.0
    assert row["mf1"] == 3.0
    assert row["rf1"] == 3.0
    assert row["ds2"] is None or pd_isna(row["ds2"])


def pd_isna(v):
    import pandas as pd

    return pd.isna(v)


def test_parse_records_handles_empty_strings_as_null():
    df = parse_records([_record(ct="", ds1="")], fetched_at=datetime.now(tz=timezone.utc))
    row = df.iloc[0]
    assert row["cycle_time_sec"] is None
    assert pd_isna(row["ds1"])


def test_parse_records_empty_input_returns_empty_df():
    df = parse_records([], fetched_at=datetime.now(tz=timezone.utc))
    assert df.empty


def test_parse_records_parses_recorded_at_as_utc_timestamp():
    df = parse_records([_record()], fetched_at=datetime.now(tz=timezone.utc))
    assert str(df.iloc[0]["recorded_at"].tzinfo) == "UTC"

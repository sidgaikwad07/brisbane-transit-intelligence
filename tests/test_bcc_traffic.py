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


class _FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_fetch_new_records_is_one_export_call(monkeypatch):
    import ingestion.bcc_traffic as bcc

    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return _FakeResponse(200, [_record(), _record(dbid="2")], {"X-RateLimit-Remaining": "4000"})

    monkeypatch.setattr(bcc.requests, "get", fake_get)
    records = bcc.fetch_new_records(datetime(2026, 10, 5, tzinfo=timezone.utc))

    assert len(records) == 2
    assert len(calls) == 1
    assert calls[0][0].endswith("/exports/json")
    assert calls[0][1]["where"] == "recorded>'2026-10-05T00:00:00+00:00'"


def test_fetch_new_records_raises_rate_limited_with_reset_time(monkeypatch):
    import pytest

    import ingestion.bcc_traffic as bcc

    body = {"errorcode": 10005, "reset_time": "2026-10-05T00:00:00Z", "call_limit": 5000}
    monkeypatch.setattr(bcc.requests, "get", lambda url, params, timeout: _FakeResponse(429, body))

    with pytest.raises(bcc.RateLimited) as exc:
        bcc.fetch_new_records(datetime(2026, 10, 4, tzinfo=timezone.utc))
    assert exc.value.reset_at == datetime(2026, 10, 5, tzinfo=timezone.utc)


def test_rate_limit_reset_falls_back_to_next_utc_midnight():
    import ingestion.bcc_traffic as bcc

    reset = bcc._rate_limit_reset(_FakeResponse(429, "not json"))
    assert (reset.hour, reset.minute, reset.tzinfo) == (0, 0, timezone.utc)
    assert reset > datetime.now(tz=timezone.utc)

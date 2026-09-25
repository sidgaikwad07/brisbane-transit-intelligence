from ingestion.weather import _parse_daily_response


def test_parse_daily_response_maps_fields():
    daily = {
        "time": ["2026-09-18", "2026-09-19"],
        "precipitation_sum": [0.0, 1.6],
        "temperature_2m_min": [11.5, 10.4],
        "temperature_2m_max": [23.7, 29.7],
        "wind_speed_10m_max": [12.6, 10.4],
    }
    df = _parse_daily_response(daily)
    assert list(df.columns) == ["date", "rainfall_mm", "temp_min_c", "temp_max_c", "wind_kph"]
    assert len(df) == 2
    assert df.iloc[1]["rainfall_mm"] == 1.6


def test_parse_daily_response_empty_when_no_time():
    assert _parse_daily_response({}).empty
    assert _parse_daily_response({"time": []}).empty

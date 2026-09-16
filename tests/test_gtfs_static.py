from ingestion.gtfs_static import TABLE_COLUMNS


def test_all_core_gtfs_tables_defined():
    expected = {"agency", "routes", "stops", "calendar", "calendar_dates", "trips", "stop_times", "shapes"}
    assert expected.issubset(TABLE_COLUMNS.keys())


def test_stops_has_lat_lon():
    assert "stop_lat" in TABLE_COLUMNS["stops"]
    assert "stop_lon" in TABLE_COLUMNS["stops"]


def test_stop_times_ordered_by_sequence_column_present():
    assert "stop_sequence" in TABLE_COLUMNS["stop_times"]

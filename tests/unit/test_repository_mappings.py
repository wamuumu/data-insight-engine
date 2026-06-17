from __future__ import annotations

from datetime import datetime, timezone

from db.repositories.history_log import HistoryLogRepository
from db.repositories.special_event import SpecialEventRepository
from ingestion.parsers.base import HistoryLogRecord, SpecialEventRecord


def test_history_log_row_conversion_builds_timezone_aware_timestamp():
    record = HistoryLogRecord(
        source_file="device_B12345678.xlsx",
        data={
            "event_date": "17/06/2026",
            "event_time": "12:34:56.123",
            "firmware_version": 7,
            "event_id": 1,
            "value": 9,
        },
    )

    row = HistoryLogRepository()._history_log_to_row(record, device_id=42, source_file_id=99)

    assert row == {
        "device_id": 42,
        "firmware_version": 7,
        "event_ts": datetime(2026, 6, 17, 12, 34, 56, 123000, tzinfo=timezone.utc),
        "event_id": 1,
        "value": 9,
        "source_file_id": 99,
    }


def test_special_event_row_conversion_maps_flags_and_time():
    record = SpecialEventRecord(
        source_file="device_B12345678.parquet",
        data={
            "acc_x": 1.1,
            "acc_y": 2.2,
            "acc_z": 3.3,
            "gyro_x": 4.4,
            "gyro_y": 5.5,
            "gyro_z": 6.6,
            "hdop": 7.7,
            "lat": 8.8,
            "lon": 9.9,
            "speed": 10.1,
            "gps_fix": 1,
            "hour": 12,
            "min": 34,
            "sec": 56,
            "cent": 99,
            "alarms": 3,
            "algo_ignited": 0,
            "algo_enabled": 1,
        },
    )

    row = SpecialEventRepository()._special_event_to_row(record, device_id=17, source_file_id=21)

    assert row["device_id"] == 17
    assert row["gps_fix"] is True
    assert row["algo_ignited"] is False
    assert row["algo_enabled"] is True
    assert row["time"].hour == 12
    assert row["time"].minute == 34
    assert row["time"].second == 56
    assert row["time"].microsecond == 990000
    assert row["source_file_id"] == 21
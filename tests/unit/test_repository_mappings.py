"""
Unit tests for repository row-conversion helpers.

These tests exercise the pure Python logic that transforms domain records into
database row dicts.  No database connection is needed.

Covers:
  HistoryLogRepository._history_log_to_row
    - timezone-aware timestamp construction
    - with and without milliseconds in the time string
    - all scalar fields passed through correctly

  SpecialEventRepository._special_event_to_row
    - boolean coercion for gps_fix, algo_ignited, algo_enabled
    - time construction from hour/min/sec/cent components
    - centisecond clamping edge cases via construct_time
    - all scalar fields passed through correctly
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from db.repositories.history_log import HistoryLogRepository
from db.repositories.special_event import SpecialEventRepository
from ingestion.parsers.base import HistoryLogRecord, SpecialEventRecord


# ── helpers ───────────────────────────────────────────────────────────────────


def _history_record(**overrides) -> HistoryLogRecord:
    defaults = {
        "event_date": "17/06/2026",
        "event_time": "12:34:56.123",
        "firmware_version": 7,
        "event_id": 1,
        "value": 9,
    }
    return HistoryLogRecord(source_file="device.xlsx", data={**defaults, **overrides})


def _special_record(**overrides) -> SpecialEventRecord:
    defaults = {
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
        "cent": 50,
        "alarms": 3,
        "algo_ignited": 0,
        "algo_enabled": 1,
    }
    return SpecialEventRecord(
        source_file="device.parquet", data={**defaults, **overrides}
    )


# ── HistoryLogRepository._history_log_to_row ─────────────────────────────────


class TestHistoryLogToRow:
    repo = HistoryLogRepository()

    def test_basic_row_structure(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=42, source_file_id=99
        )
        assert set(row.keys()) == {
            "device_id",
            "firmware_version",
            "event_ts",
            "event_id",
            "value",
            "source_file_id",
        }

    def test_device_id_propagated(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=7, source_file_id=None
        )
        assert row["device_id"] == 7

    def test_source_file_id_propagated(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=1, source_file_id=55
        )
        assert row["source_file_id"] == 55

    def test_source_file_id_none_allowed(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=1, source_file_id=None
        )
        assert row["source_file_id"] is None

    def test_timestamp_is_utc_aware(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=1, source_file_id=None
        )
        assert row["event_ts"].tzinfo == timezone.utc

    def test_timestamp_with_milliseconds(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(), device_id=1, source_file_id=None
        )
        expected = datetime(2026, 6, 17, 12, 34, 56, 123_000, tzinfo=timezone.utc)
        assert row["event_ts"] == expected

    def test_timestamp_without_milliseconds(self) -> None:
        rec = _history_record(event_time="08:00:00")
        row = self.repo._history_log_to_row(rec, device_id=1, source_file_id=None)
        expected = datetime(2026, 6, 17, 8, 0, 0, tzinfo=timezone.utc)
        assert row["event_ts"] == expected

    def test_firmware_version_passed_through(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(firmware_version=999), device_id=1, source_file_id=None
        )
        assert row["firmware_version"] == 999

    def test_event_id_passed_through(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(event_id=2), device_id=1, source_file_id=None
        )
        assert row["event_id"] == 2

    def test_value_passed_through(self) -> None:
        row = self.repo._history_log_to_row(
            _history_record(value=12345), device_id=1, source_file_id=None
        )
        assert row["value"] == 12345


# ── SpecialEventRepository._special_event_to_row ─────────────────────────────


class TestSpecialEventToRow:
    repo = SpecialEventRepository()

    def test_basic_row_structure(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(), device_id=1, source_file_id=None
        )
        expected_keys = {
            "device_id",
            "acc_x",
            "acc_y",
            "acc_z",
            "gyro_x",
            "gyro_y",
            "gyro_z",
            "hdop",
            "lat",
            "lon",
            "speed",
            "gps_fix",
            "time",
            "alarms",
            "algo_ignited",
            "algo_enabled",
            "source_file_id",
        }
        assert set(row.keys()) == expected_keys

    def test_device_id_propagated(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(), device_id=17, source_file_id=None
        )
        assert row["device_id"] == 17

    def test_source_file_id_propagated(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(), device_id=1, source_file_id=21
        )
        assert row["source_file_id"] == 21

    # boolean coercion ────────────────────────────────────────────────────────

    @pytest.mark.parametrize("truthy", [1, True, 99, "yes"])
    def test_gps_fix_truthy_coerced_to_true(self, truthy) -> None:
        row = self.repo._special_event_to_row(
            _special_record(gps_fix=truthy), device_id=1, source_file_id=None
        )
        assert row["gps_fix"] is True

    @pytest.mark.parametrize("falsy", [0, False])
    def test_gps_fix_falsy_coerced_to_false(self, falsy) -> None:
        row = self.repo._special_event_to_row(
            _special_record(gps_fix=falsy), device_id=1, source_file_id=None
        )
        assert row["gps_fix"] is False

    def test_algo_ignited_false_when_zero(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(algo_ignited=0), device_id=1, source_file_id=None
        )
        assert row["algo_ignited"] is False

    def test_algo_enabled_true_when_one(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(algo_enabled=1), device_id=1, source_file_id=None
        )
        assert row["algo_enabled"] is True

    # time construction ───────────────────────────────────────────────────────

    def test_time_hour_minute_second_correct(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(hour=23, min=59, sec=58, cent=10),
            device_id=1,
            source_file_id=None,
        )
        t = row["time"]
        assert t.hour == 23
        assert t.minute == 59
        assert t.second == 58

    def test_time_centisecond_converted_to_microseconds(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(cent=50), device_id=1, source_file_id=None
        )
        assert row["time"].microsecond == 500_000

    def test_time_centisecond_clamped_above_99(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(cent=200), device_id=1, source_file_id=None
        )
        assert row["time"].microsecond == 990_000

    def test_time_centisecond_clamped_below_0(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(cent=-1), device_id=1, source_file_id=None
        )
        assert row["time"].microsecond == 0

    # scalar fields ───────────────────────────────────────────────────────────

    def test_acc_x_passed_through(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(acc_x=99.9), device_id=1, source_file_id=None
        )
        assert row["acc_x"] == pytest.approx(99.9)

    def test_lat_lon_passed_through(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(lat=45.5, lon=11.0), device_id=1, source_file_id=None
        )
        assert row["lat"] == pytest.approx(45.5)
        assert row["lon"] == pytest.approx(11.0)

    def test_alarms_passed_through(self) -> None:
        row = self.repo._special_event_to_row(
            _special_record(alarms=255), device_id=1, source_file_id=None
        )
        assert row["alarms"] == 255

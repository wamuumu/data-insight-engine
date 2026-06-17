from __future__ import annotations

from pathlib import Path

from common.constants import SWITCH_OFF_EVENT_ID, SWITCH_ON_EVENT_ID, UNDEFINED_FIRMWARE_VERSION
from ingestion.crawler.base import BaseFile
from ingestion.parsers.xlsx import XLSXParser


def test_build_firmware_index_skips_missing_columns(tmp_path):
    path = tmp_path / "device_B12345678.xlsx"
    path.write_bytes(b"placeholder")
    file = BaseFile(path)

    parser = XLSXParser()
    assert parser._build_firmware_index(file, ["Event ID"], [(1,), (2,)]) == []


def test_build_firmware_segments_and_lookup_handle_transitions(tmp_path):
    path = tmp_path / "device_B12345678.xlsx"
    path.write_bytes(b"placeholder")
    file = BaseFile(path)

    parser = XLSXParser()
    header = ["Event ID", "Value"]
    rows = [
        (SWITCH_ON_EVENT_ID, 100),
        (10, 0),
        (SWITCH_ON_EVENT_ID, 200),
        (SWITCH_OFF_EVENT_ID, 300),
        (SWITCH_OFF_EVENT_ID, 400),
        (SWITCH_ON_EVENT_ID, 500),
    ]

    switch_events = parser._build_firmware_index(file, header, rows)
    assert switch_events == [
        (0, SWITCH_ON_EVENT_ID, 100),
        (2, SWITCH_ON_EVENT_ID, 200),
        (3, SWITCH_OFF_EVENT_ID, 300),
        (4, SWITCH_OFF_EVENT_ID, 400),
        (5, SWITCH_ON_EVENT_ID, 500),
    ]

    segments = parser._build_firmware_segments(file, switch_events, total_rows=6)
    assert segments == [
        (0, 1, 100),
        (2, 3, 200),
        (4, 4, 400),
        (5, 5, 500),
    ]

    lookup = parser._make_firmware_lookup(segments)
    assert [lookup(index) for index in range(6)] == [100, 100, 200, 200, 400, 500]


def test_make_firmware_lookup_returns_sentinel_outside_segments():
    parser = XLSXParser()
    lookup = parser._make_firmware_lookup([(2, 4, 77)])

    assert lookup(0) == UNDEFINED_FIRMWARE_VERSION
    assert lookup(3) == 77
    assert lookup(5) == UNDEFINED_FIRMWARE_VERSION
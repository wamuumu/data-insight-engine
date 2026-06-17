from __future__ import annotations

from pathlib import Path

import openpyxl

from common.constants import SWITCH_OFF_EVENT_ID, SWITCH_ON_EVENT_ID, UNDEFINED_FIRMWARE_VERSION
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import HistoryLogRecord
from ingestion.parsers.xlsx import XLSXParser


def _create_xlsx(path: Path):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "history"
    worksheet.append(["Event ID", "Value", "Date", "Time"])
    worksheet.append([SWITCH_ON_EVENT_ID, 101, "17/06/2026", "08:00:00.000"])
    worksheet.append([10, 5, "17/06/2026", "08:01:00.000"])
    worksheet.append([SWITCH_OFF_EVENT_ID, 202, "17/06/2026", "08:02:00.000"])
    worksheet.append([11, 6, "17/06/2026", "08:03:00.000"])
    workbook.save(path)


def test_can_handle_xlsx_files(tmp_path):
    parser = XLSXParser()
    path = tmp_path / "device_B12345678.xlsx"
    path.write_bytes(b"placeholder")

    assert parser.can_handle(BaseFile(path))


def test_parse_yields_history_records_with_firmware_lookup(tmp_path):
    path = tmp_path / "device_B12345678.xlsx"
    _create_xlsx(path)

    parser = XLSXParser()
    records = list(parser.parse(BaseFile(path)))

    assert len(records) == 4
    assert all(isinstance(record, HistoryLogRecord) for record in records)
    assert [record.data["firmware_version"] for record in records] == [101, 101, 101, 202]
    assert records[0].data["event_id"] == SWITCH_ON_EVENT_ID
    assert records[0].data["event_date"] == "17/06/2026"
    assert records[0].data["event_time"] == "08:00:00.000"


def test_parse_uses_undefined_firmware_when_no_switch_events(tmp_path):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["Event ID", "Value", "Date", "Time"])
    worksheet.append([99, 101, "17/06/2026", "08:00:00.000"])
    path = tmp_path / "device_B12345678.xlsx"
    workbook.save(path)

    parser = XLSXParser()
    records = list(parser.parse(BaseFile(path)))

    assert len(records) == 1
    assert records[0].data["firmware_version"] == UNDEFINED_FIRMWARE_VERSION
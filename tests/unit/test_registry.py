from __future__ import annotations

from pathlib import Path

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.crawler.base import BaseFile
from ingestion.parsers.parquet import ParquetParser
from ingestion.parsers.xlsx import XLSXParser
from ingestion.registry import get_parser


def _write_xlsx(path: Path):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["Event ID", "Value", "Date", "Time"])
    worksheet.append([1, 100, "17/06/2026", "08:00:00.000"])
    workbook.save(path)


def _write_parquet(path: Path):
    table = pa.table({"ACC_X": [1.0], "lat": [45.1]})
    pq.write_table(table, path)


def test_get_parser_selects_xlsx_parser(tmp_path):
    path = tmp_path / "device_B12345678.xlsx"
    _write_xlsx(path)

    parser = get_parser(BaseFile(path))

    assert isinstance(parser, XLSXParser)


def test_get_parser_selects_parquet_parser(tmp_path):
    path = tmp_path / "device_B12345678.parquet"
    _write_parquet(path)

    parser = get_parser(BaseFile(path))

    assert isinstance(parser, ParquetParser)


def test_get_parser_returns_none_for_unsupported_extension(tmp_path):
    path = tmp_path / "device_B12345678.txt"
    path.write_text("ignored")

    assert get_parser(BaseFile(path)) is None
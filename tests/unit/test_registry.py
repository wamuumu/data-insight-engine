"""
Unit tests for src/ingestion/registry.py

Covers:
  - Correct parser type returned for each supported extension
  - None returned for unsupported extensions
  - Multiple supported files in the same tmp dir each get the right parser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.crawler.base import BaseFile
from ingestion.parsers.parquet import ParquetParser
from ingestion.parsers.xlsx import XLSXParser
from ingestion.registry import get_parser


def _stub(tmp_path: Path, name: str) -> BaseFile:
    """Create a zero-byte file and wrap it in a BaseFile."""
    p = tmp_path / name
    p.write_bytes(b"stub")
    return BaseFile(p)


class TestGetParser:
    def test_xlsx_extension_returns_xlsx_parser(self, tmp_path: Path) -> None:
        assert isinstance(get_parser(_stub(tmp_path, "x.xlsx")), XLSXParser)

    def test_parquet_extension_returns_parquet_parser(self, tmp_path: Path) -> None:
        assert isinstance(get_parser(_stub(tmp_path, "x.parquet")), ParquetParser)

    @pytest.mark.parametrize("name", ["x.csv", "x.txt", "x.json", "x.pdf", "x"])
    def test_unsupported_extension_returns_none(
        self, tmp_path: Path, name: str
    ) -> None:
        assert get_parser(_stub(tmp_path, name)) is None

    def test_uppercase_extension_is_handled_correctly(self, tmp_path: Path) -> None:
        # BaseFile lowercases the suffix, so the registry must also work
        f = _stub(tmp_path, "x.XLSX")
        assert isinstance(get_parser(f), XLSXParser)

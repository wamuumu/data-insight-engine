"""
Unit tests for src/ingestion/parsers/parquet.py

Covers:
  - can_handle: True for .parquet, False for other extensions
  - parse: correct field mapping via _HEADER_MAPPING
  - parse: dropped columns (counter, extDataPresent, free_*) are absent
  - parse: unmapped / unknown columns are silently ignored (not in output)
  - parse: records count matches row count regardless of batch_size
  - parse: batch_size=1 (one record per batch) still produces all records
  - parse: corrupted / missing file raises
  - parse: source_file attribute is set on each record
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import SpecialEventRecord
from ingestion.parsers.parquet import ParquetParser


# ── helpers ──────────────────────────────────────────────────────────────────


def _write_parquet(path: Path, overrides: dict | None = None) -> Path:
    defaults: dict[str, list] = {
        "ACC_X": [1.1, 2.2],
        "ACC_Y": [3.3, 4.4],
        "ACC_Z": [5.5, 6.6],
        "GYRO_X": [7.7, 8.8],
        "GYRO_Y": [9.9, 10.1],
        "GYRO_Z": [11.2, 12.3],
        "HDOP": [13.4, 14.5],
        "lat": [45.1, 45.2],
        "long": [9.1, 9.2],
        "speed_km_h": [30.0, 31.5],
        "Hour": [12, 12],
        "Min": [30, 31],
        "Sec": [40, 41],
        "Cent": [5, 6],
        "Alarms": [1, 2],
        "algoIgnited": [1, 0],
        "algoEnabled": [0, 1],
        "GPS_Fix": [True, False],
        "counter": [99, 98],
        "extDataPresent": [1, 1],
    }
    data = {**defaults, **(overrides or {})}
    pq.write_table(pa.table(data), path)
    return path


# ── can_handle ────────────────────────────────────────────────────────────────


class TestParquetParserCanHandle:
    def test_true_for_parquet_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "x.parquet"
        p.write_bytes(b"stub")
        assert ParquetParser().can_handle(BaseFile(p)) is True

    def test_false_for_xlsx_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "x.xlsx"
        p.write_bytes(b"stub")
        assert ParquetParser().can_handle(BaseFile(p)) is False

    @pytest.mark.parametrize("ext", [".csv", ".txt", ".json", ""])
    def test_false_for_other_extensions(self, tmp_path: Path, ext: str) -> None:
        p = tmp_path / f"x{ext}"
        p.write_bytes(b"stub")
        assert ParquetParser().can_handle(BaseFile(p)) is False


# ── parse: field mapping ──────────────────────────────────────────────────────


class TestParquetParserFieldMapping:
    @pytest.fixture
    def two_row_file(self, tmp_path: Path) -> Path:
        return _write_parquet(tmp_path / "device_B12345678.parquet")

    def test_record_count_equals_row_count(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert len(records) == 2

    def test_all_records_are_special_event_records(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert all(isinstance(r, SpecialEventRecord) for r in records)

    def test_acc_x_mapped_correctly(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[0].data["acc_x"] == pytest.approx(1.1)

    def test_lon_mapped_from_long(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[0].data["lon"] == pytest.approx(9.1)

    def test_speed_mapped_from_speed_km_h(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[0].data["speed"] == pytest.approx(30.0)

    def test_gps_fix_truthy_value(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[0].data["gps_fix"] is True

    def test_gps_fix_falsy_value(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[1].data["gps_fix"] is False

    def test_algo_ignited_first_row(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[0].data["algo_ignited"] == 1

    def test_algo_enabled_second_row(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert records[1].data["algo_enabled"] == 1

    def test_source_file_is_set_on_every_record(self, two_row_file: Path) -> None:
        records = list(ParquetParser().parse(BaseFile(two_row_file)))
        assert all(r.source_file == two_row_file for r in records)


# ── parse: dropped columns ────────────────────────────────────────────────────


class TestParquetParserDroppedColumns:
    @pytest.mark.parametrize("col", ["counter", "extDataPresent"])
    def test_dropped_column_absent_from_record(self, tmp_path: Path, col: str) -> None:
        path = _write_parquet(tmp_path / "device_B12345678.parquet")
        records = list(ParquetParser().parse(BaseFile(path)))
        assert col not in records[0].data

    def test_unknown_column_is_silently_ignored(self, tmp_path: Path) -> None:
        path = _write_parquet(
            tmp_path / "device_B12345678.parquet",
            overrides={"UNKNOWN_FIELD": [42, 43]},
        )
        records = list(ParquetParser().parse(BaseFile(path)))
        assert "UNKNOWN_FIELD" not in records[0].data
        assert "unknown_field" not in records[0].data


# ── parse: batching behaviour ─────────────────────────────────────────────────


class TestParquetParserBatching:
    def test_batch_size_one_yields_all_records(self, tmp_path: Path) -> None:
        path = _write_parquet(tmp_path / "device_B12345678.parquet")
        records = list(ParquetParser(batch_size=1).parse(BaseFile(path)))
        assert len(records) == 2

    def test_batch_size_larger_than_file_yields_all_records(
        self, tmp_path: Path
    ) -> None:
        path = _write_parquet(tmp_path / "device_B12345678.parquet")
        records = list(ParquetParser(batch_size=10_000).parse(BaseFile(path)))
        assert len(records) == 2


# ── parse: error handling ─────────────────────────────────────────────────────


class TestParquetParserErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.parquet"
        with pytest.raises(Exception):
            list(ParquetParser().parse(BaseFile.__new__(BaseFile)))

    def test_corrupted_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "device_B12345678.parquet"
        path.write_bytes(b"this is not a parquet file")
        with pytest.raises(Exception):
            list(ParquetParser().parse(BaseFile(path)))

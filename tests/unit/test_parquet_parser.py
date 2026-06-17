from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.crawler.base import BaseFile
from ingestion.parsers.parquet import ParquetParser


def _write_parquet(path: Path) -> None:
	table = pa.table(
		{
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
	)
	pq.write_table(table, path)


def test_can_handle_parquet_files(tmp_path):
	file_path = tmp_path / "device_B1234ABCD_events.parquet"
	file_path.write_bytes(b"placeholder")

	parser = ParquetParser()

	assert parser.can_handle(BaseFile(file_path)) is True


def test_parse_maps_known_fields_and_drops_extras(tmp_path):
	file_path = tmp_path / "device_B1234ABCD_events.parquet"
	_write_parquet(file_path)

	parser = ParquetParser(batch_size=1)
	records = list(parser.parse(BaseFile(file_path)))

	assert len(records) == 2
	first = records[0].data
	assert first["acc_x"] == 1.1
	assert first["lon"] == 9.1
	assert first["speed"] == 30.0
	assert first["gps_fix"] is True
	assert first["algo_ignited"] is True
	assert first["algo_enabled"] is False
	assert "counter" not in first

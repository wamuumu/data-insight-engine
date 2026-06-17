from __future__ import annotations

from datetime import datetime, timezone

from common.utils import combine_date_time, compute_sha256, construct_time, extract_serial_number


def test_extract_serial_number_matches_expected_pattern(tmp_path):
	path = tmp_path / "device_B1234ABCD.xlsx"
	path.write_bytes(b"payload")

	assert extract_serial_number(path) == "B1234ABCD"


def test_extract_serial_number_rejects_lowercase_hex(tmp_path):
	path = tmp_path / "device_B1234abcd.xlsx"
	path.write_bytes(b"payload")

	assert extract_serial_number(path) is None


def test_compute_sha256_returns_expected_digest(tmp_path):
	path = tmp_path / "payload.bin"
	path.write_bytes(b"abc")

	digest = compute_sha256(path)

	assert digest is not None
	assert digest.hex() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_combine_date_time_uses_timezone_aware_datetime():
	result = combine_date_time("17/06/2026", "12:34:56.123")

	assert result == datetime(2026, 6, 17, 12, 34, 56, 123000, tzinfo=timezone.utc)


def test_construct_time_clamps_centiseconds():
	result = construct_time(1, 2, 3, 123)

	assert result.hour == 1
	assert result.minute == 2
	assert result.second == 3
	assert result.microsecond == 990000
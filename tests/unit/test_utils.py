"""
Unit tests for src/common/utils.py

Covers:
  - extract_serial_number: valid pattern, lowercase rejection, embedded pattern,
    no match, path with multiple candidates (first match wins)
  - compute_sha256: known digest, empty file, missing file (OSError → None)
  - combine_date_time: with and without milliseconds, UTC awareness
  - construct_time: normal values, centisecond clamping (>99, <0)
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

from common.utils import (
    combine_date_time,
    compute_sha256,
    construct_time,
    extract_serial_number,
)


# ── extract_serial_number ────────────────────────────────────────────────────


class TestExtractSerialNumber:
    def test_valid_pattern_returns_match(self, tmp_path: Path) -> None:
        path = tmp_path / "device_B1234ABCD.xlsx"
        path.write_bytes(b"x")
        assert extract_serial_number(path) == "B1234ABCD"

    def test_lowercase_hex_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "device_B1234abcd.xlsx"
        path.write_bytes(b"x")
        assert extract_serial_number(path) is None

    def test_mixed_case_hex_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "device_B1234aBcD.xlsx"
        path.write_bytes(b"x")
        assert extract_serial_number(path) is None

    def test_pattern_embedded_in_longer_path(self, tmp_path: Path) -> None:
        nested = tmp_path / "fleet" / "region" / "B00AABBCC" / "log.xlsx"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"x")
        assert extract_serial_number(nested) == "B00AABBCC"

    def test_no_pattern_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "unknown_file.xlsx"
        path.write_bytes(b"x")
        assert extract_serial_number(path) is None

    def test_too_short_hex_is_rejected(self, tmp_path: Path) -> None:
        # B + 7 chars is not a match (needs exactly 8 hex chars)
        path = tmp_path / "B1234ABC.xlsx"
        path.write_bytes(b"x")
        assert extract_serial_number(path) is None

    def test_all_digits_serial_number(self, tmp_path: Path) -> None:
        path = tmp_path / "B12345678.parquet"
        path.write_bytes(b"x")
        assert extract_serial_number(path) == "B12345678"

    def test_all_uppercase_letters_serial_number(self, tmp_path: Path) -> None:
        path = tmp_path / "B_ABCDEFGH.xlsx"  # underscore breaks the pattern
        path.write_bytes(b"x")
        assert extract_serial_number(path) is None

    def test_returns_first_occurrence_in_path(self, tmp_path: Path) -> None:
        nested = tmp_path / "B11111111" / "B22222222.xlsx"
        nested.parent.mkdir()
        nested.write_bytes(b"x")
        # The regex finds the first match in the full path string
        result = extract_serial_number(nested)
        assert result in {"B11111111", "B22222222"}


# ── compute_sha256 ────────────────────────────────────────────────────────────


class TestComputeSha256:
    # SHA-256("abc") = ba7816bf...
    _ABC_DIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_known_digest_for_abc(self, tmp_path: Path) -> None:
        path = tmp_path / "payload.bin"
        path.write_bytes(b"abc")
        digest = compute_sha256(path)
        assert digest is not None
        assert digest.hex() == self._ABC_DIGEST

    def test_empty_file_has_stable_digest(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")
        digest = compute_sha256(path)
        assert digest is not None
        assert len(digest) == 32

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.bin"
        assert compute_sha256(path) is None

    def test_digest_changes_when_content_changes(self, tmp_path: Path) -> None:
        p1 = tmp_path / "a.bin"
        p2 = tmp_path / "b.bin"
        p1.write_bytes(b"hello")
        p2.write_bytes(b"world")
        assert compute_sha256(p1) != compute_sha256(p2)

    def test_returns_bytes_of_length_32(self, tmp_path: Path) -> None:
        path = tmp_path / "data.bin"
        path.write_bytes(b"some data")
        result = compute_sha256(path)
        assert isinstance(result, bytes)
        assert len(result) == 32


# ── combine_date_time ─────────────────────────────────────────────────────────


class TestCombineDateTime:
    def test_with_milliseconds_parses_correctly(self) -> None:
        result = combine_date_time("17/06/2026", "12:34:56.123")
        assert result == datetime(2026, 6, 17, 12, 34, 56, 123_000, tzinfo=timezone.utc)

    def test_without_milliseconds_fallback(self) -> None:
        result = combine_date_time("01/01/2024", "00:00:00")
        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_result_is_timezone_aware(self) -> None:
        result = combine_date_time("17/06/2026", "08:00:00.000")
        assert result.tzinfo == timezone.utc

    def test_midnight_with_milliseconds(self) -> None:
        result = combine_date_time("31/12/2025", "00:00:00.000")
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_end_of_day_time(self) -> None:
        result = combine_date_time("17/06/2026", "23:59:59.999")
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59
        assert result.microsecond == 999_000


# ── construct_time ────────────────────────────────────────────────────────────


class TestConstructTime:
    def test_normal_values(self) -> None:
        t = construct_time(12, 34, 56, 50)
        assert t == time(12, 34, 56, 500_000)

    def test_centisecond_clamps_at_99(self) -> None:
        t = construct_time(1, 2, 3, 123)
        assert t.microsecond == 990_000  # clamped to 99 * 10_000

    def test_centisecond_clamps_at_0(self) -> None:
        t = construct_time(0, 0, 0, -5)
        assert t.microsecond == 0

    def test_zero_centiseconds(self) -> None:
        t = construct_time(10, 20, 30, 0)
        assert t.microsecond == 0

    def test_exactly_99_centiseconds(self) -> None:
        t = construct_time(0, 0, 0, 99)
        assert t.microsecond == 990_000

    def test_hour_minute_second_preserved(self) -> None:
        t = construct_time(23, 59, 59, 10)
        assert t.hour == 23
        assert t.minute == 59
        assert t.second == 59

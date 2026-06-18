"""
Unit tests for src/db/models/file_tracker.py

Covers the derived properties that live on the model (no database required):
  - FileTracker.file_name  — extracts the basename from file_path
  - FileTracker.file_type  — extracts the extension without the leading dot, lower-cased
  - FileStatus enum values
"""

from __future__ import annotations

from db.models.file_tracker import FileStatus, FileTracker


def _tracker(file_path: str) -> FileTracker:
    """Build a FileTracker with just enough state to test the properties."""
    return FileTracker(
        file_path=file_path,
        checksum_sha256=b"\x00" * 32,  # required field
        status=FileStatus.PENDING,
    )


class TestFileTrackerProperties:
    def test_file_name_for_xlsx(self) -> None:
        ft = _tracker("/some/nested/path/device_B12345678.xlsx")
        assert ft.file_name == "device_B12345678.xlsx"

    def test_file_name_for_parquet(self) -> None:
        ft = _tracker("/data/device_B12345678.parquet")
        assert ft.file_name == "device_B12345678.parquet"

    def test_file_type_xlsx(self) -> None:
        ft = _tracker("/data/device_B12345678.XLSX")  # uppercase ext
        assert ft.file_type == "xlsx"

    def test_file_type_parquet(self) -> None:
        ft = _tracker("/data/events.parquet")
        assert ft.file_type == "parquet"

    def test_file_type_is_lowercase(self) -> None:
        ft = _tracker("/data/EVENTS.PARQUET")
        assert ft.file_type == ft.file_type.lower()

    def test_file_name_bare_filename(self) -> None:
        ft = _tracker("device.xlsx")
        assert ft.file_name == "device.xlsx"


class TestFileStatus:
    def test_all_statuses_are_strings(self) -> None:
        for status in FileStatus:
            assert isinstance(status, str)

    def test_status_values(self) -> None:
        assert FileStatus.PENDING == "pending"
        assert FileStatus.PROCESSING == "processing"
        assert FileStatus.DONE == "done"
        assert FileStatus.FAILED == "failed"

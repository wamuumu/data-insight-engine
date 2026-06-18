"""
Unit tests for src/ingestion/crawler/drive.py

Covers:
  - Discovering files with supported extensions (.xlsx, .parquet)
  - Skipping files with unsupported extensions
  - Recursing into nested sub-directories
  - Raising FileNotFoundError for a missing root
  - Raising NotADirectoryError when root points to a file
  - Yielding BaseFile objects with correct metadata
  - Empty directory produces no results
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.crawler.base import BaseFile
from ingestion.crawler.drive import DriveCrawler


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestDriveCrawlerDiscovery:
    def test_discovers_xlsx_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "device_B12345678.xlsx")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 1
        assert files[0].suffix == ".xlsx"

    def test_discovers_parquet_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "device_B12345678.parquet")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 1
        assert files[0].suffix == ".parquet"

    def test_discovers_both_extensions(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.xlsx")
        _touch(tmp_path / "b.parquet")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 2

    def test_skips_unsupported_extensions(self, tmp_path: Path) -> None:
        _touch(tmp_path / "notes.txt")
        _touch(tmp_path / "data.csv")
        _touch(tmp_path / "report.pdf")
        assert list(DriveCrawler(tmp_path).crawl()) == []

    def test_mixed_extensions_only_yields_supported(self, tmp_path: Path) -> None:
        _touch(tmp_path / "keep.xlsx")
        _touch(tmp_path / "keep.parquet")
        _touch(tmp_path / "skip.csv")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 2

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        _touch(tmp_path / "level1" / "level2" / "deep.xlsx")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 1
        assert files[0].path.name == "deep.xlsx"

    def test_empty_directory_yields_nothing(self, tmp_path: Path) -> None:
        assert list(DriveCrawler(tmp_path).crawl()) == []

    def test_extension_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        # File extensions are lowercased in BaseFile.__init__
        _touch(tmp_path / "DATA.XLSX")
        _touch(tmp_path / "EVENTS.PARQUET")
        files = list(DriveCrawler(tmp_path).crawl())
        assert len(files) == 2


class TestDriveCrawlerBaseFileMetadata:
    def test_yielded_objects_are_basefile_instances(self, tmp_path: Path) -> None:
        _touch(tmp_path / "device.xlsx")
        files = list(DriveCrawler(tmp_path).crawl())
        assert all(isinstance(f, BaseFile) for f in files)

    def test_basefile_has_correct_path(self, tmp_path: Path) -> None:
        target = _touch(tmp_path / "device.xlsx")
        files = list(DriveCrawler(tmp_path).crawl())
        assert files[0].path == target

    def test_basefile_size_matches_real_size(self, tmp_path: Path) -> None:
        payload = b"hello world"
        target = _touch(tmp_path / "device.xlsx", content=payload)
        files = list(DriveCrawler(tmp_path).crawl())
        assert files[0].size == len(payload)


class TestDriveCrawlerErrors:
    def test_missing_root_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            DriveCrawler(tmp_path / "nonexistent")

    def test_file_as_root_raises_not_a_directory(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "file.txt")
        with pytest.raises(NotADirectoryError):
            DriveCrawler(f)
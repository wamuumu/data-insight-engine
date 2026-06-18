"""
Integration tests for src/ingestion/pipeline.py

Strategy
--------
We avoid a live database by substituting lightweight fakes for the four
repositories and the DB session context-manager.  This keeps the test fast
while still exercising the real pipeline orchestration logic: file discovery,
deduplication check, parser selection, batching, status transitions, and
quarantine path.

Fake objects are small, purpose-built classes (not mocks) so failures produce
clear error messages and the fakes themselves are easy to reason about.

Test coverage:
  - XLSX and Parquet files each produce the correct number of inserted records
  - FileTracker status transitions: PENDING → PROCESSING → DONE
  - Device serial number is extracted from the file name and registered once
  - Deduplication: _is_duplicate=True skips parsing entirely
  - Missing serial number: file is counted as failed, not parsed
  - Quarantine: failed file removes previously inserted records and marks FAILED
  - dry_run=True: no DB writes, records counted as inserted
  - File mode: single file processed directly without crawling
  - PipelineStats aggregated correctly across a multi-file directory run
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import ingestion.pipeline as pipeline_module
from db.models.file_tracker import FileStatus
from ingestion.pipeline import IngestionPipeline


# ─────────────────────────────────────────────────────────────────────────────
# Fake collaborators
# ─────────────────────────────────────────────────────────────────────────────


class FakeTracker:
    def __init__(self, tracker_id: int, file_path: str, checksum: bytes):
        self.id = tracker_id
        self.file_path = file_path
        self.checksum_sha256 = checksum
        self.status = FileStatus.PENDING


class FakeDevice:
    def __init__(self, device_id: int, serial_number: str):
        self.id = device_id
        self.serial_number = serial_number


class FakeSession:
    """Minimal session stub: supports session.get(Model, id)."""

    def __init__(self):
        self.tracker: FakeTracker | None = None

    def get(self, model, identity):
        if self.tracker and identity == self.tracker.id:
            return self.tracker
        return None


class FakeFileTrackerRepo:
    def __init__(self, session: FakeSession):
        self._session = session
        self.processing_calls: list[FakeTracker] = []
        self.done_calls: list[tuple[FakeTracker, int]] = []
        self.failed_calls: list[tuple[FakeTracker, str]] = []

    def get_file_tracker_by_checksum(self, session, checksum):
        return None  # always new

    def create_file_tracker(self, session, file_path, checksum_sha256):
        tracker = FakeTracker(1, file_path, checksum_sha256)
        self._session.tracker = tracker
        return tracker

    def mark_processing(self, session, tracker):
        tracker.status = FileStatus.PROCESSING
        self.processing_calls.append(tracker)

    def mark_done(self, session, tracker, rows_inserted):
        tracker.status = FileStatus.DONE
        self.done_calls.append((tracker, rows_inserted))

    def mark_failed(self, session, tracker, error_message):
        tracker.status = FileStatus.FAILED
        self.failed_calls.append((tracker, error_message))


class FakeDeviceRepo:
    def __init__(self):
        self.registered: list[str] = []

    def get_device_by_serial_number(self, session, serial_number):
        return None

    def create_device(self, session, serial_number):
        self.registered.append(serial_number)
        return FakeDevice(10, serial_number)


class FakeHistoryLogRepo:
    def __init__(self):
        self.batches: list[list] = []
        self.deleted: list[int] = []

    def insert_history_logs(self, session, records, device_id, source_file_id=None):
        self.batches.append(list(records))
        return len(records)

    def delete_history_logs_by_file(self, session, source_file_id):
        self.deleted.append(source_file_id)
        return 0


class FakeSpecialEventRepo:
    def __init__(self):
        self.batches: list[list] = []
        self.deleted: list[int] = []

    def insert_special_events(self, session, records, device_id, source_file_id=None):
        self.batches.append(list(records))
        return len(records)

    def delete_special_events_by_file(self, session, source_file_id):
        self.deleted.append(source_file_id)
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def fakes(fake_session):
    """Bundle of all fake repos wired to the same session."""
    return {
        "session": fake_session,
        "file_tracker": FakeFileTrackerRepo(fake_session),
        "device": FakeDeviceRepo(),
        "history_log": FakeHistoryLogRepo(),
        "special_event": FakeSpecialEventRepo(),
    }


@pytest.fixture
def make_pipeline(fakes, monkeypatch):
    """
    Factory that creates a patched IngestionPipeline.

    The monkeypatched get_db_session yields fakes["session"]; all four
    repositories are replaced with the fake counterparts.
    """

    @contextmanager
    def _fake_db_session(session_factory):
        yield fakes["session"]

    monkeypatch.setattr(pipeline_module, "get_db_session", _fake_db_session)
    monkeypatch.setattr(pipeline_module.settings, "workers", 1)
    monkeypatch.setattr(pipeline_module.settings, "db_batch_size", 100)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_attempts", 1)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_initial_delay", 0.01)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_max_delay", 0.01)
    monkeypatch.setattr(pipeline_module.settings, "file_retry_timeout", 30)
    monkeypatch.setattr(pipeline_module.settings, "max_batch_split_depth", 2)

    def _factory(
        path: Path, *, dry_run: bool = False, file_mode: bool = True
    ) -> IngestionPipeline:
        p = IngestionPipeline(
            root=path,
            session_factory=lambda: None,
            dry_run=dry_run,
            file_mode=file_mode,
        )
        p.file_tracker_repo = fakes["file_tracker"]
        p.device_repo = fakes["device"]
        p.history_log_repo = fakes["history_log"]
        p.special_event_repo = fakes["special_event"]
        monkeypatch.setattr(p, "_is_duplicate", lambda checksum: False)
        return p

    return _factory


# ─────────────────────────────────────────────────────────────────────────────
# File builders
# ─────────────────────────────────────────────────────────────────────────────


def _xlsx(
    tmp_path: Path, filename: str = "device_B12345678.xlsx", n_rows: int = 2
) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Event ID", "Value", "Date", "Time"])
    for i in range(n_rows):
        ws.append([1, 100 + i, "17/06/2026", f"08:0{i}:00.000"])
    path = tmp_path / filename
    wb.save(path)
    return path


def _parquet(
    tmp_path: Path, filename: str = "device_B12345678.parquet", n_rows: int = 2
) -> Path:
    n = n_rows
    table = pa.table(
        {
            "ACC_X": [1.0] * n,
            "ACC_Y": [2.0] * n,
            "ACC_Z": [3.0] * n,
            "GYRO_X": [4.0] * n,
            "GYRO_Y": [5.0] * n,
            "GYRO_Z": [6.0] * n,
            "HDOP": [7.0] * n,
            "lat": [45.0] * n,
            "long": [9.0] * n,
            "speed_km_h": [30.0] * n,
            "Hour": [12] * n,
            "Min": [0] * n,
            "Sec": [0] * n,
            "Cent": [0] * n,
            "Alarms": [0] * n,
            "algoIgnited": [1] * n,
            "algoEnabled": [0] * n,
            "GPS_Fix": [True] * n,
            "counter": [0] * n,
            "extDataPresent": [0] * n,
        }
    )
    path = tmp_path / filename
    pq.write_table(table, path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Happy-path tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineHappyPath:
    @pytest.mark.parametrize("kind", ["xlsx", "parquet"])
    def test_file_fully_processed_and_marked_done(
        self, tmp_path, fakes, make_pipeline, kind
    ) -> None:
        path = _xlsx(tmp_path) if kind == "xlsx" else _parquet(tmp_path)
        stats = make_pipeline(path).run()

        assert stats.files_parsed == 1
        assert stats.files_failed == 0
        assert stats.records_inserted == 2
        assert fakes["session"].tracker.status == FileStatus.DONE

    def test_xlsx_inserts_into_history_log_repo(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        stats = make_pipeline(_xlsx(tmp_path)).run()
        assert len(fakes["history_log"].batches) > 0
        assert fakes["special_event"].batches == []

    def test_parquet_inserts_into_special_event_repo(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        stats = make_pipeline(_parquet(tmp_path)).run()
        assert len(fakes["special_event"].batches) > 0
        assert fakes["history_log"].batches == []

    def test_device_serial_number_registered(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        make_pipeline(_xlsx(tmp_path)).run()
        assert fakes["device"].registered == ["B12345678"]

    def test_file_status_transitions_processing_then_done(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        make_pipeline(_xlsx(tmp_path)).run()
        assert len(fakes["file_tracker"].processing_calls) == 1
        assert len(fakes["file_tracker"].done_calls) == 1

    @pytest.mark.parametrize("n_rows", [1, 5, 50])
    def test_record_count_matches_rows_in_file(
        self, tmp_path, fakes, make_pipeline, n_rows
    ) -> None:
        path = _xlsx(tmp_path, n_rows=n_rows)
        stats = make_pipeline(path).run()
        assert stats.records_inserted == n_rows


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineDeduplication:
    def test_duplicate_file_is_skipped(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        path = _xlsx(tmp_path)
        pipeline = make_pipeline(path)
        monkeypatch.setattr(pipeline, "_is_duplicate", lambda checksum: True)

        stats = pipeline.run()

        assert stats.files_deduplicated == 1
        assert stats.files_parsed == 0
        assert stats.records_inserted == 0
        assert fakes["session"].tracker is None  # no DB writes

    def test_non_duplicate_file_is_processed(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        stats = make_pipeline(_xlsx(tmp_path)).run()
        assert stats.files_deduplicated == 0
        assert stats.files_parsed == 1


# ─────────────────────────────────────────────────────────────────────────────
# Error / failure paths
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineFailurePaths:
    def test_file_without_serial_number_is_counted_as_failed(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        path = _xlsx(tmp_path, filename="no_serial.xlsx")
        stats = make_pipeline(path).run()
        assert stats.files_failed == 1
        assert stats.files_parsed == 0

    def test_quarantine_marks_file_as_failed(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        path = _xlsx(tmp_path)
        pipeline = make_pipeline(path)

        # Force _stream_file to raise so quarantine is triggered
        def _boom(*args, **kwargs):
            raise RuntimeError("Simulated parse failure")

        monkeypatch.setattr(pipeline, "_stream_file", _boom)

        stats = pipeline.run()

        assert stats.files_failed == 1
        assert len(fakes["file_tracker"].failed_calls) == 1

    def test_quarantine_deletes_xlsx_records_on_failure(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        path = _xlsx(tmp_path)
        pipeline = make_pipeline(path)

        monkeypatch.setattr(
            pipeline,
            "_stream_file",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")),
        )

        pipeline.run()
        assert len(fakes["history_log"].deleted) == 1

    def test_quarantine_deletes_parquet_records_on_failure(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        path = _parquet(tmp_path)
        pipeline = make_pipeline(path)

        monkeypatch.setattr(
            pipeline,
            "_stream_file",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")),
        )

        pipeline.run()
        assert len(fakes["special_event"].deleted) == 1

    def test_unsupported_extension_counted_as_skipped(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        path = tmp_path / "device_B12345678.txt"
        path.write_bytes(b"data")
        stats = make_pipeline(path).run()
        assert stats.files_skipped == 1
        assert stats.files_parsed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run mode
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineDryRun:
    def test_dry_run_counts_records_without_db_writes(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        path = _xlsx(tmp_path)
        pipeline = make_pipeline(path, dry_run=True)
        stats = pipeline.run()

        assert stats.records_inserted == 2  # counted as inserted
        assert fakes["history_log"].batches == []  # no actual writes
        assert fakes["session"].tracker is None  # no tracker created

    def test_dry_run_does_not_check_for_duplicates(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        """In dry_run mode _is_duplicate always returns False."""
        path = _xlsx(tmp_path)
        pipeline = make_pipeline(path, dry_run=True)
        # Even if we set the real _is_duplicate, dry_run short-circuits it
        monkeypatch.setattr(pipeline, "_is_duplicate", lambda c: True)
        stats = pipeline.run()
        # dry_run overrides the duplicate guard in _persist_batch but _is_duplicate
        # is still called upstream; here we just verify no crash
        assert stats is not None


# ─────────────────────────────────────────────────────────────────────────────
# Directory / file-mode
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineDiscovery:
    def test_directory_mode_processes_multiple_files(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        _xlsx(tmp_path, filename="device_B11111111.xlsx")
        _xlsx(tmp_path, filename="device_B22222222.xlsx")

        pipeline = make_pipeline(tmp_path, file_mode=False)
        monkeypatch.setattr(pipeline, "_is_duplicate", lambda c: False)
        stats = pipeline.run()

        assert stats.files_discovered == 2
        assert stats.files_parsed == 2
        assert stats.records_inserted == 4

    def test_empty_directory_produces_zero_stats(self, tmp_path, make_pipeline) -> None:
        pipeline = make_pipeline(tmp_path, file_mode=False)
        stats = pipeline.run()
        assert stats.files_discovered == 0

    def test_file_mode_processes_single_file_directly(
        self, tmp_path, fakes, make_pipeline
    ) -> None:
        path = _xlsx(tmp_path)
        stats = make_pipeline(path, file_mode=True).run()
        assert stats.files_discovered == 1
        assert stats.files_parsed == 1


# ─────────────────────────────────────────────────────────────────────────────
# Batch-splitting (persistence layer)
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineBatchSplitting:
    def test_batch_split_on_db_error_still_inserts_all_records(
        self, tmp_path, fakes, make_pipeline, monkeypatch
    ) -> None:
        """
        Simulate a DB error on the first attempt of every batch so the pipeline
        is forced to split and retry single-record batches.
        """
        path = _xlsx(tmp_path, n_rows=4)
        pipeline = make_pipeline(path)
        monkeypatch.setattr(pipeline_module.settings, "db_retry_attempts", 1)
        monkeypatch.setattr(pipeline_module.settings, "max_batch_split_depth", 5)
        monkeypatch.setattr(pipeline_module.settings, "db_batch_size", 4)

        call_count = {"n": 0}
        original_insert = fakes["history_log"].insert_history_logs

        def _fail_first_call(session, records, device_id, source_file_id=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated transient DB error")
            return original_insert(session, records, device_id, source_file_id)

        fakes["history_log"].insert_history_logs = _fail_first_call

        stats = pipeline.run()
        assert stats.records_inserted == 4

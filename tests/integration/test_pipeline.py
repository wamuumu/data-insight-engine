from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from db.models.file_tracker import FileStatus
import ingestion.pipeline as pipeline_module
from ingestion.pipeline import IngestionPipeline


class _FakeTracker:
    def __init__(self, tracker_id: int, file_path: str, checksum_sha256: bytes):
        self.id = tracker_id
        self.file_path = file_path
        self.checksum_sha256 = checksum_sha256
        self.status = FileStatus.PENDING


class _FakeDevice:
    def __init__(self, device_id: int, serial_number: str):
        self.id = device_id
        self.serial_number = serial_number


class _FakeSession:
    def __init__(self):
        self.tracker: _FakeTracker | None = None

    def get(self, model, identity):
        if self.tracker is not None and identity == self.tracker.id:
            return self.tracker
        return None


class _FakeFileTrackerRepo:
    def __init__(self, session: _FakeSession):
        self.session = session

    def get_file_tracker_by_checksum(self, session, checksum):
        return None

    def create_file_tracker(self, session, file_path, checksum_sha256):
        self.session.tracker = _FakeTracker(1, file_path, checksum_sha256)
        return self.session.tracker

    def mark_processing(self, session, tracker):
        tracker.status = FileStatus.PROCESSING

    def mark_done(self, session, tracker, rows_inserted):
        tracker.status = FileStatus.DONE

    def mark_failed(self, session, tracker, error_message):
        tracker.status = FileStatus.FAILED


class _FakeDeviceRepo:
    def __init__(self):
        self.created_serial_numbers: list[str] = []

    def get_device_by_serial_number(self, session, serial_number):
        return None

    def create_device(self, session, serial_number):
        self.created_serial_numbers.append(serial_number)
        return _FakeDevice(10, serial_number)


class _FakeHistoryLogRepo:
    def __init__(self):
        self.batches: list[list] = []

    def insert_history_logs(self, session, records, device_id, source_file_id=None):
        self.batches.append(list(records))
        return len(records)

    def delete_history_logs_by_file(self, session, source_file_id):
        return 0


class _FakeSpecialEventRepo:
    def __init__(self):
        self.batches: list[list] = []

    def insert_special_events(self, session, records, device_id, source_file_id=None):
        self.batches.append(list(records))
        return len(records)

    def delete_special_events_by_file(self, session, source_file_id):
        return 0


def _create_xlsx(path: Path):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "history"
    worksheet.append(["Event ID", "Value", "Date", "Time"])
    worksheet.append([1, 101, "17/06/2026", "08:00:00.000"])
    worksheet.append([2, 202, "17/06/2026", "08:01:00.000"])
    workbook.save(path)


def _create_parquet(path: Path):
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


@pytest.mark.parametrize("kind", ["xlsx", "parquet"])
def test_pipeline_processes_supported_file_types_without_live_database(tmp_path, monkeypatch, kind):
    if kind == "xlsx":
        path = tmp_path / "device_B12345678.xlsx"
        _create_xlsx(path)
    else:
        path = tmp_path / "device_B12345678.parquet"
        _create_parquet(path)

    fake_session = _FakeSession()

    @contextmanager
    def fake_get_db_session(session_factory):
        yield fake_session

    monkeypatch.setattr(pipeline_module, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(pipeline_module.settings, "workers", 1)
    monkeypatch.setattr(pipeline_module.settings, "db_batch_size", 1)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_attempts", 1)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_initial_delay", 0.01)
    monkeypatch.setattr(pipeline_module.settings, "db_retry_max_delay", 0.01)
    monkeypatch.setattr(pipeline_module.settings, "file_retry_timeout", 30)
    monkeypatch.setattr(pipeline_module.settings, "max_batch_split_depth", 2)

    pipeline = IngestionPipeline(root=path, session_factory=lambda: None, dry_run=False, file_mode=True)
    pipeline.file_tracker_repo = _FakeFileTrackerRepo(fake_session)
    pipeline.device_repo = _FakeDeviceRepo()
    pipeline.history_log_repo = _FakeHistoryLogRepo()
    pipeline.special_event_repo = _FakeSpecialEventRepo()
    monkeypatch.setattr(pipeline, "_is_duplicate", lambda checksum: False)

    stats = pipeline.run()

    assert stats.files_discovered == 1
    assert stats.files_parsed == 1
    assert stats.files_failed == 0
    assert stats.records_inserted == 2
    assert fake_session.tracker is not None
    assert fake_session.tracker.status == FileStatus.DONE
    assert pipeline.device_repo.created_serial_numbers == ["B12345678"]

    if kind == "xlsx":
        assert len(pipeline.history_log_repo.batches) == 2
        assert pipeline.special_event_repo.batches == []
    else:
        assert len(pipeline.special_event_repo.batches) == 2
        assert pipeline.history_log_repo.batches == []
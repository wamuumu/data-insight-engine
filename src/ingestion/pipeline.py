from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import itertools
from pathlib import Path
import structlog
from time import monotonic, sleep
import threading

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from common.logging import get_logger
from common.utils import compute_sha256, extract_serial_number, extract_date
from config import load_settings
from db.models.file_tracker import FileTracker, FileStatus
from db.repositories.device import DeviceRepository
from db.repositories.file_tracker import FileTrackerRepository
from db.repositories.history_log import HistoryLogRepository
from db.repositories.special_event import SpecialEventRepository
from db.session import get_db_session
from ingestion.crawler.base import BaseFile, FileType
from ingestion.crawler.drive import DriveCrawler
from ingestion.parsers.base import BaseParser, HistoryLogRecord, SpecialEventRecord
from ingestion.registry import get_parser
from monitoring.metrics import (
    file_processing_duration,
    files_processed,
    pipeline_active,
    pipeline_last_run,
    records_ingested,
)
from monitoring.metrics import MetricStatus

settings = load_settings()

logger = get_logger(__name__)

_worker_local = threading.local()
_worker_counter = itertools.count(1)


@dataclass
class PipelineStats:
    """
    Tracks statistics about the ingestion pipeline execution.
    """

    files_discovered: int = 0           # Total number of files discovered by the crawler in the specified root directory
    files_parsed: int = 0               # Total number of files successfully parsed and processed
    files_skipped: int = 0              # No parser found
    files_deduplicated: int = 0         # Alredy processed, skipped based on identity
    files_failed: int = 0               # Files that failed to process due to errors
    records_produced: int = 0           # Total number of records produced by parsers
    records_inserted: int = 0           # Total number of records successfully inserted into the database

    def merge(self, other: PipelineStats):
        """
        Merge another PipelineStats object into this one by summing their respective counts.
        """
        self.files_discovered += other.files_discovered
        self.files_parsed += other.files_parsed
        self.files_skipped += other.files_skipped
        self.files_deduplicated += other.files_deduplicated
        self.files_failed += other.files_failed
        self.records_produced += other.records_produced
        self.records_inserted += other.records_inserted

    def to_dict(self, suffix: str = "") -> dict:
        """
        Convert the PipelineStats to a dictionary for logging or metrics purposes.
        """
        return {
            f"{suffix}_files_discovered": self.files_discovered,
            f"{suffix}_files_parsed": self.files_parsed,
            f"{suffix}_files_skipped": self.files_skipped,
            f"{suffix}_files_deduplicated": self.files_deduplicated,
            f"{suffix}_files_failed": self.files_failed,
            f"{suffix}_records_produced": self.records_produced,
            f"{suffix}_records_inserted": self.records_inserted,
        }


class IngestionPipeline:
    """
    Orchestrates the crawling and parsing of files for ingestion.
    """

    def __init__(
        self,
        root: Path,
        session_factory: sessionmaker,
        dry_run: bool = False,
        file_mode: bool = False,
    ):
        self.root = root
        self.session_factory = session_factory
        self.dry_run = dry_run
        self.file_mode = file_mode
        self.crawler = (
            DriveCrawler(root) if not file_mode else None
        )  # Crawler is not needed in file mode
        self.device_repo = DeviceRepository()
        self.file_tracker_repo = FileTrackerRepository()
        self.history_log_repo = HistoryLogRepository()
        self.special_event_repo = SpecialEventRepository()

    def run(self) -> PipelineStats:
        pipeline_active.set(1)

        try:
            files = self._discover_files()
            if not files:
                logger.info("No files discovered for processing.", root=str(self.root))
                return PipelineStats()  # Return empty stats if no files are found

            stats = PipelineStats()
            if settings.workers <= 1 or len(files) == 1:
                # Single-thread multi-file or single-file
                logger.debug(
                    "Running in single-threaded mode.",
                    workers=settings.workers,
                    files=len(files),
                )
                for file in files:
                    stats.merge(self._process_one(file))
            else:
                # Multi-thread multi-file
                with ThreadPoolExecutor(max_workers=settings.workers) as executor:
                    futures = [
                        executor.submit(self._process_one, file) for file in files
                    ]
                    for future in as_completed(futures):
                        local_stats = future.result()
                        if local_stats:
                            logger.debug(
                                "File processing completed in thread.",
                                **local_stats.to_dict(suffix="thread"),
                            )
                            stats.merge(local_stats)
                        else:
                            logger.warning(
                                "File processing returned no stats in thread."
                            )

            logger.info("Pipeline run completed", **stats.to_dict(suffix="total"))

            return stats
        finally:
            pipeline_active.set(0)
            pipeline_last_run.set_to_current_time()

    def _discover_files(self) -> list[BaseFile]:
        """
        Discover files in the root directory using the crawler.
        """
        if self.file_mode:
            logger.debug(
                "File mode enabled. Skipping file discovery.", root=str(self.root)
            )
            return [BaseFile(self.root)]  # Return the single file as a list
        else:
            logger.debug(
                "File mode disabled. Starting file discovery.", root=str(self.root)
            )
            return list(self.crawler.crawl())

    def _process_one(self, file: BaseFile) -> PipelineStats:
        """
        Process a single file: determine the parser, check for duplicates, parse and persist records.
        """
        structlog.contextvars.clear_contextvars()
        if not hasattr(_worker_local, "worker_id"):
            _worker_local.worker_id = next(_worker_counter)
        structlog.contextvars.bind_contextvars(worker_id=_worker_local.worker_id)

        stats = PipelineStats(files_discovered=1)

        parser = get_parser(file)
        if not parser:
            logger.info("No parser found for file, skipping", file_path=str(file.path))
            stats.files_skipped += 1
            return stats

        sn = extract_serial_number(file.path)
        if sn is None:
            logger.error(
                "Could not extract serial number from file path, skipping",
                file_path=str(file.path),
            )
            stats.files_failed += 1
            return stats
        
        date = extract_date(file.path)
        if date is None:
            logger.warning(
                "Could not extract date from file path, proceeding without date context",
                file_path=str(file.path),
            )

        checksum = compute_sha256(file.path)
        if checksum is None:
            logger.error(
                "Could not compute checksum for file, skipping",
                file_path=str(file.path),
            )
            stats.files_failed += 1
            return stats

        if self._is_duplicate(checksum):
            logger.info("Duplicate file found, skipping", file_path=str(file.path))
            stats.files_deduplicated += 1
            files_processed.labels(
                status=MetricStatus.DEDUPLICATED, file_type=file.file_type
            ).inc()
            return stats

        device_id: int = -1
        file_tracker_id: int = -1
        prev_file_tracker_id: int | None = None

        if not self.dry_run:
            with get_db_session(self.session_factory) as session:
                # Upsert device record
                device = self.device_repo.get_device_by_serial_number(session, sn)
                if device is None:
                    device = self.device_repo.create_device(session, sn)
                    logger.debug(
                        "Created new device record",
                        serial_number=sn,
                        device_id=device.id,
                    )
                else:
                    logger.debug(
                        "Found existing device record",
                        serial_number=sn,
                        device_id=device.id,
                    )

                if file.file_type == FileType.HISTORY_LOG:
                    last_log = self.history_log_repo.get_latest_log_by_device(
                        session, device.id
                    )
                    prev_file_tracker_id = last_log.source_file_id if last_log else None
                    logger.debug(
                        "Retrieved latest history log for device",
                        device_id=device.id,
                        last_log_id=last_log.id if last_log else None,
                        prev_file_tracker_id=prev_file_tracker_id,
                    )

                file_tracker = self.file_tracker_repo.get_file_tracker_by_checksum(
                    session, checksum
                )
                if file_tracker is None:
                    file_tracker = self.file_tracker_repo.create_file_tracker(
                        session, str(file.path), checksum, date
                    )
                    logger.debug(
                        "Created new file tracker record",
                        file_path=str(file.path),
                        tracker_id=file_tracker.id,
                    )
                else:
                    logger.debug(
                        "Found existing file tracker record",
                        file_path=str(file.path),
                        tracker_id=file_tracker.id,
                        status=file_tracker.status,
                    )

                self.file_tracker_repo.mark_processing(session, file_tracker)

                device_id = device.id
                file_tracker_id = file_tracker.id

        with file_processing_duration.labels(file_type=file.file_type).time():
            try:
                inserted, produced, is_complete = self._stream_file(
                    file, parser, device_id, file_tracker_id, prev_file_tracker_id
                )
                stats.files_parsed += 1
                stats.records_produced += produced
                stats.records_inserted += inserted

                if is_complete:
                    files_processed.labels(
                        status=MetricStatus.SUCCESS, file_type=file.file_type
                    ).inc()

                    if not self.dry_run:
                        with get_db_session(self.session_factory) as session:
                            ft = session.get(FileTracker, file_tracker_id)
                            if ft is not None:
                                self.file_tracker_repo.mark_done(
                                    session, ft, rows_inserted=inserted
                                )
                            else:
                                logger.error(
                                    "FileTracker record not found when marking as done",
                                    file_tracker_id=file_tracker_id,
                                )
                else:
                    logger.warning(
                        "File parsing completed with incomplete record insertion",
                        file_path=str(file.path),
                        produced=produced,
                        inserted=inserted,
                    )
                    stats.files_failed += 1
                    files_processed.labels(
                        status=MetricStatus.INCOMPLETE, file_type=file.file_type
                    ).inc()
                    self._quarantine_file(
                        file_tracker_id,
                        file.file_type,
                        f"Incomplete record insertion: produced={produced}, inserted={inserted}",
                    )

            except Exception as e:
                stats.files_failed += 1
                files_processed.labels(
                    status=MetricStatus.FAILURE, file_type=file.file_type
                ).inc()
                self._quarantine_file(file_tracker_id, file.file_type, str(e))

        structlog.contextvars.clear_contextvars()
        return stats

    def _quarantine_file(self, file_tracker_id: int, file_type: FileType, reason: str):
        """
        Mark the file as failed and provide the reason for quarantine.
        """
        if self.dry_run:
            logger.debug(
                "Dry run enabled - skipping quarantine.",
                reason=reason,
            )
            return

        logger.warning(
            "Quarantining file due to processing failure",
            file_tracker_id=file_tracker_id,
            reason=reason,
        )

        try:
            with get_db_session(self.session_factory) as session:
                if file_type == FileType.HISTORY_LOG:
                    rows = self.history_log_repo.delete_history_logs_by_file(
                        session, file_tracker_id
                    )
                    logger.info(
                        "Deleted history log records associated with quarantined file",
                        file_tracker_id=file_tracker_id,
                        deleted_rows=rows,
                    )
                elif file_type == FileType.SPECIAL_EVENT:
                    rows = self.special_event_repo.delete_special_events_by_file(
                        session, file_tracker_id
                    )
                    logger.info(
                        "Deleted special event records associated with quarantined file",
                        file_tracker_id=file_tracker_id,
                        deleted_rows=rows,
                    )
                else:
                    logger.warning(
                        "Unknown file type for quarantine, skipping deletion of records",
                        file_tracker_id=file_tracker_id,
                        file_type=file_type,
                    )

                ft = session.get(FileTracker, file_tracker_id)
                if ft is not None:
                    self.file_tracker_repo.mark_failed(session, ft, reason)
                else:
                    logger.error(
                        "FileTracker record not found for quarantine",
                        file_tracker_id=file_tracker_id,
                    )

        except Exception as e:
            logger.error(
                "Failed to mark file as failed in quarantine",
                file_tracker_id=file_tracker_id,
                error=str(e),
            )

    def _is_duplicate(self, checksum: bytes) -> bool:
        """
        Check the checksum against FileTracker for deduplication check.
        """
        if self.dry_run:
            return False  # Don't skip any files in dry run mode

        try:
            with get_db_session(self.session_factory) as session:
                row = session.execute(
                    select(FileTracker.id).where(
                        FileTracker.checksum_sha256 == checksum,
                        FileTracker.status == FileStatus.DONE,
                    )
                ).first()
                return row is not None
        except Exception as e:
            logger.error("Error checking for duplicate file in database", error=str(e))
            return False

    def _stream_file(
        self,
        file: BaseFile,
        parser: BaseParser,
        device_id: int,
        source_file_id: int,
        prev_source_file_id: int | None = None,
    ) -> tuple[int, int, bool]:
        """
        Parse a file in source order and persist records atomically in batches.
        """
        total_inserted = 0
        total_produced = 0
        batch: list[HistoryLogRecord] | list[SpecialEventRecord] = []
        deadline = monotonic() + settings.file_retry_timeout

        parsed = parser.parse(file)

        if isinstance(parsed, SpecialEventRecord):
            total_produced += 1
            batch = [parsed]

            total_inserted += self._persist_batch(
                batch, device_id, source_file_id, deadline
            )

        else:
            hl_records = parsed.records
            # for log in hl_records:
            #     logger.debug(
            #         "Cleaned record",
            #         dt=str(log.data["datetime"]),
            #         event_id=log.data["event_id"],
            #         value=log.data["value"],
            #         tssc=log.data["tssc"],
            #         rollover=log.data["rollover"],
            #         fv=log.data["firmware_version"],
            #     )
            rollover_index = parsed.rollover_index
            rollover_detected = parsed.rollover_index is not None

            if not hl_records:
                logger.warning("No records produced by parser.", file_path=str(file.path))
                return (0, 0, False)

            current_file_id = prev_source_file_id or source_file_id

            for idx, record in enumerate(hl_records):
                is_rollover_boundary = (
                    rollover_detected
                    and idx == rollover_index
                    and prev_source_file_id is not None
                )

                if is_rollover_boundary:
                    if batch:
                        logger.debug(
                            "Splitting batch due to rollover detection",
                            rollover_index=idx,
                            batch_size=len(batch),
                            source_file_id=prev_source_file_id,
                        )
                        total_inserted += self._persist_batch(
                            batch, device_id, current_file_id, deadline
                        )
                        batch.clear()

                    current_file_id = source_file_id

                total_produced += 1
                batch.append(record)

                if len(batch) >= settings.db_batch_size:
                    total_inserted += self._persist_batch(
                        batch, device_id, current_file_id, deadline
                    )
                    batch.clear()

            if batch:
                total_inserted += self._persist_batch(
                    batch, device_id, current_file_id, deadline
                )

        return (total_inserted, total_produced, total_inserted == total_produced)

    def _persist_batch(
        self,
        batch: list[HistoryLogRecord] | list[SpecialEventRecord],
        device_id: int,
        source_file_id: int,
        deadline: float,
    ) -> int:
        """
        Persist a batch of records to the database. If insertion fails, retry the batch for a fixed number of attempts.
        """
        if not batch:
            return 0

        if self.dry_run:
            logger.debug("Dry run enabled - skipping DB insert.", skipped=len(batch))
            return len(batch)

        for attempt in range(settings.db_retry_attempts):
            if monotonic() > deadline:
                logger.error("Batch insertion deadline exceeded, aborting batch.")
                return 0

            try:
                with get_db_session(self.session_factory) as session:
                    inserted = self._insert_batch_in_transaction(
                        session, batch, device_id, source_file_id
                    )
                    logger.debug(
                        "Batch inserted successfully.",
                        batch_size=len(batch),
                        inserted=inserted,
                    )
                    return inserted
            except Exception as e:
                delay = min(
                    settings.db_retry_max_delay,
                    settings.db_retry_initial_delay
                    * (2**attempt),  # Exponential backoff
                )

                logger.warning(
                    "Batch insertion failed, will retry after delay.",
                    attempt=attempt,
                    delay=delay,
                    error=str(e),
                )

                if monotonic() + delay < deadline:
                    sleep(delay)
                else:
                    logger.error(
                        "Cannot retry batch insertion due to deadline constraints, aborting batch."
                    )
                    return 0

        logger.error("All retry attempts failed for batch insertion, aborting batch.")
        return 0

    def _insert_batch_in_transaction(
        self,
        session,
        batch: list[HistoryLogRecord] | list[SpecialEventRecord],
        device_id: int,
        source_file_id: int,
    ) -> int:
        """
        Insert a batch of records into the database within a transaction.
        """
        if not batch:
            return 0

        if isinstance(batch[0], HistoryLogRecord):
            inserted = self.history_log_repo.upsert_history_logs(
                session, batch, device_id, source_file_id
            )
            records_ingested.labels(table="history_log").inc(inserted)
            logger.debug(
                "Inserted history log batch.",
                batch_size=len(batch),
                inserted=inserted,
                device_id=device_id,
                source_file_id=source_file_id,
            )
            return inserted

        elif isinstance(batch[0], SpecialEventRecord):
            inserted = self.special_event_repo.insert_special_events(
                session, batch, device_id, source_file_id
            )
            records_ingested.labels(table="special_event").inc(inserted)
            logger.debug(
                "Inserted special event batch.",
                batch_size=len(batch),
                inserted=inserted,
                device_id=device_id,
                source_file_id=source_file_id,
            )
            return inserted

        else:
            logger.warning("Unknown batch type")
            return 0

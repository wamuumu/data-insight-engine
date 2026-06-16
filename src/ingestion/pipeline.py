from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from common.logging import get_logger
from common.utils import compute_sha256, extract_serial_number
from config import load_settings
from db.models.device import Device
from db.models.file_tracker import FileTracker, FileStatus
from db.repositories.device import DeviceRepository
from db.repositories.file_tracker import FileTrackerRepository
from db.repositories.history_log import HistoryLogRepository
from db.repositories.special_event import SpecialEventRepository
from db.session import get_db_session
from ingestion.crawler.base import BaseFile
from ingestion.crawler.drive import DriveCrawler
from ingestion.parsers.base import BaseParser, HistoryLogRecord, SpecialEventRecord
from ingestion.registry import get_parser
from monitoring.metrics import (
    file_processing_duration,
    files_processed,
    pipeline_active,
    pipeline_last_run,
    records_ingested
)
from monitoring.metrics import MetricStatus

settings = load_settings()

logger = get_logger(__name__)


@dataclass
class PipelineStats:
    """
    Tracks statistics about the ingestion pipeline execution.
    """
    files_discovered: int = 0                           # Total number of files discovered by the crawler in the specified root directory
    files_parsed: int = 0                               # Total number of files successfully parsed and processed
    files_skipped: int = 0                              # No parser found
    files_deduplicated: int = 0                         # Alredy processed, skipped based on identity
    files_failed: int = 0                               # Files that failed to process due to errors
    records_produced: int = 0                           # Total number of records produced by parsers
    records_inserted: int = 0                           # Total number of records successfully inserted into the database

class IngestionPipeline:
    """
    Orchestrates the crawling and parsing of files for ingestion.
    """
    def __init__(self, root: Path, session_factory: sessionmaker, dry_run: bool = False, file_mode: bool = False):
        self.root = root
        self.session_factory = session_factory
        self.dry_run = dry_run
        self.file_mode = file_mode
        self.crawler = DriveCrawler(root) if not file_mode else None  # Crawler is not needed in file mode
        self.device_repo = DeviceRepository()
        self.file_tracker_repo = FileTrackerRepository()
        self.history_log_repo = HistoryLogRepository()
        self.special_event_repo = SpecialEventRepository()

    def run(self) -> PipelineStats:
        stats = PipelineStats()
        pipeline_active.set(1)
            
        try:
            if self.file_mode:
                # Single file mode (e.g. when root is a file path instead of directory)
                logger.info("File mode enabled. Processing single file.", file_path=str(self.root))
                stats.files_discovered = 1  # Assume one file is being processed in this mode
                self._process_one(BaseFile(self.root), stats)
            else:
                # Normal mode with crawling
                logger.info("File mode disabled. Starting crawl.", root=str(self.root))
                for file in self.crawler.crawl():
                    stats.files_discovered += 1
                    self._process_one(file, stats)
        finally:
            pipeline_active.set(0)
            pipeline_last_run.set_to_current_time()

        logger.info(
            "Pipeline run completed",
            files_discovered=stats.files_discovered,
            files_parsed=stats.files_parsed,
            files_skipped=stats.files_skipped,
            files_deduplicated=stats.files_deduplicated,
            files_failed=stats.files_failed,
            records_produced=stats.records_produced,
            records_inserted=stats.records_inserted
        )

        return stats
    
    def _process_one(self, file: BaseFile, stats: PipelineStats):
        """
        Process a single file: determine the parser, check for duplicates, parse and persist records.
        """
        file_type = file.suffix.lstrip(".").lower()
        
        parser = get_parser(file)
        if not parser:
            logger.info("No parser found for file, skipping", file_path=str(file.path))
            stats.files_skipped += 1
            return

        sn = extract_serial_number(file.path)
        if sn is None:
            logger.error("Could not extract serial number from file path, skipping", file_path=str(file.path))
            stats.files_failed += 1
            return
        
        checksum = compute_sha256(file.path)
        if checksum is None:
            logger.error("Could not compute checksum for file, skipping", file_path=str(file.path))
            stats.files_failed += 1
            return
        
        if self._is_duplicate(checksum):
            logger.info("Duplicate file found, skipping", file_path=str(file.path))
            stats.files_deduplicated += 1
            files_processed.labels(status=MetricStatus.DEDUPLICATED, file_type=file_type).inc()
            return

        device: Device | None = None
        device_id: int | None = None
        file_tracker: FileTracker | None = None
        file_tracker_id: int | None = None

        if not self.dry_run:

            with get_db_session(self.session_factory) as session:
                file_tracker = self.file_tracker_repo.get_file_tracker_by_checksum(session, checksum)
                if file_tracker is None:
                    file_tracker = self.file_tracker_repo.create_file_tracker(session, str(file.path), checksum)
                    logger.info("Created new file tracker record", file_path=str(file.path), tracker_id=file_tracker.id)
                else:
                    logger.info("Found existing file tracker record", file_path=str(file.path), tracker_id=file_tracker.id, status=file_tracker.status)

                    if file_tracker.status == FileStatus.PROCESSING:
                        logger.warning("Found stuck processing tracker, resetting", file_path=str(file.path), tracker_id=file_tracker.id)
                    elif file_tracker.status == FileStatus.FAILED:
                        logger.warning("Found previously failed tracker, retrying", file_path=str(file.path), tracker_id=file_tracker.id)
                
                self.file_tracker_repo.mark_processing(session, file_tracker)

                # Upsert device record
                device = self.device_repo.get_device_by_serial_number(session, sn)
                if device is None:
                    device = self.device_repo.create_device(session, sn)
                    logger.info("Created new device record", serial_number=sn, device_id=device.id)
                else:
                    logger.info("Found existing device record", serial_number=sn, device_id=device.id)

                device_id = device.id
                file_tracker_id = file_tracker.id

        with file_processing_duration.labels(file_type=file_type).time():
            try:
                inserted, produced, is_complete = self._stream_file(file, parser, device_id, file_tracker_id)
                stats.files_parsed += 1
                stats.records_produced += produced
                stats.records_inserted += inserted

                if is_complete:
                    files_processed.labels(status=MetricStatus.SUCCESS, file_type=file_type).inc()

                    if not self.dry_run and file_tracker_id is not None:
                        with get_db_session(self.session_factory) as session:
                            ft = session.get(FileTracker, file_tracker_id)
                            self.file_tracker_repo.mark_done(session, ft, rows_inserted=inserted)
                else:
                    logger.warning("File parsing completed with incomplete record insertion", file_path=str(file.path), produced=produced, inserted=inserted)
                    files_processed.labels(status=MetricStatus.INCOMPLETE, file_type=file_type).inc()
            
            except Exception as e:
                stats.files_failed += 1
                files_processed.labels(status=MetricStatus.FAILURE, file_type=file_type).inc()

                if not self.dry_run and file_tracker_id is not None:
                    with get_db_session(self.session_factory) as session:
                        ft = session.get(FileTracker, file_tracker_id)
                        self.file_tracker_repo.mark_failed(session, ft, error_message=str(e))
        
        # If excpetion is encountered before, retry mechanism can be implemented 

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
                        FileTracker.status == FileStatus.DONE
                    )
                ).first()
                return row is not None
        except Exception:
            return False
    
    def _stream_file(self, file: BaseFile, parser: BaseParser, device_id: int, source_file_id: int | None) -> tuple[int, int, bool]:
        """
        Stream the file through the parser and flush records in batches. Returns (inserted_count, produced_count).
        """
        total_inserted = 0
        total_produced = 0
        history_log_buffer: list[HistoryLogRecord] = []
        special_event_buffer: list[SpecialEventRecord] = []

        for record in parser.parse(file):
            total_produced += 1

            if isinstance(record, HistoryLogRecord):
                history_log_buffer.append(record)
                if len(history_log_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_history_logs(history_log_buffer, device_id, source_file_id)
                    history_log_buffer.clear()
            elif isinstance(record, SpecialEventRecord):
                special_event_buffer.append(record)
                if len(special_event_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_special_events(special_event_buffer, device_id, source_file_id)
                    special_event_buffer.clear()
            else:
                logger.warning("Unknown record type produced by parser, skipping", record=record.__dict__)

        # Flush any remaining records in buffers
        if history_log_buffer:
            total_inserted += self._flush_history_logs(history_log_buffer, device_id, source_file_id)

        if special_event_buffer:
            total_inserted += self._flush_special_events(special_event_buffer, device_id, source_file_id)

        return total_inserted, total_produced, total_inserted == total_produced

    def _flush_history_logs(self, records: list[HistoryLogRecord], device_id: int, source_file_id: int | None) -> int:
        """
        Flush a batch of history log records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug("Dry run enabled - skipping history log DB insert.", skipped=len(records))
            return 0

        with get_db_session(self.session_factory) as session:
            inserted = self.history_log_repo.insert_history_logs(session, records, device_id, source_file_id)
            records_ingested.labels(table="history_log").inc(inserted)
            logger.debug("Flushed history logs to the database.", inserted=inserted)
            return inserted

    def _flush_special_events(self, records: list[SpecialEventRecord], device_id: int, source_file_id: int | None) -> int:
        """
        Flush a batch of special event records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug("Dry run enabled - skipping special event DB insert.", skipped=len(records))
            return 0

        with get_db_session(self.session_factory) as session:
            inserted = self.special_event_repo.insert_special_events(session, records, device_id, source_file_id)
            records_ingested.labels(table="special_event").inc(inserted)
            logger.debug("Flushed special events to the database.", inserted=inserted)
            return inserted
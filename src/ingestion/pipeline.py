from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from common.logging import get_logger
from common.utils import compute_sha256, fast_file_identity
from config import load_settings
from db.models.file_tracker import FileTracker
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

settings = load_settings()

logger = get_logger(__name__)

@dataclass
class PipelineError:
    """
    Represents an error that occurred during the ingestion pipeline execution.
    """
    file_path: Path
    error_message: str

@dataclass
class PipelineStats:
    """
    Tracks statistics about the ingestion pipeline execution.
    """
    files_discovered: int = 0
    files_parsed: int = 0
    files_skipped: int = 0          # No parser found
    files_deduplicated: int = 0     # Alredy processed, skipped based on identity
    files_failed: int = 0       
    records_produced: int = 0
    records_inserted: int = 0
    errors: list[PipelineError] = field(default_factory=list)

class IngestionPipeline:
    """
    Orchestrates the crawling and parsing of files for ingestion.
    """
    def __init__(self, root: Path, session_factory: sessionmaker, dry_run: bool = False):
        self.root = root
        self.session_factory = session_factory
        self.dry_run = dry_run
        self.crawler = DriveCrawler(root)
        self.file_tracker_repo = FileTrackerRepository()
        self.history_log_repo = HistoryLogRepository()
        self.special_event_repo = SpecialEventRepository()

    def run(self) -> PipelineStats:
        stats = PipelineStats()
        pipeline_active.set(1)

        try:
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
            records_inserted=stats.records_inserted,
            errors=[e.__dict__ for e in stats.errors]
        )

        return stats
    
    def _process_one(self, file: BaseFile, stats: PipelineStats):
        """
        Process a single file: determine the parser, check for duplicates, parse and persist records.
        """
        parser = get_parser(file)
        if not parser:
            logger.info("No parser found for file, skipping", file_path=str(file.path))
            stats.files_skipped += 1
            return
        
        file_type = file.suffix.lstrip(".").lower()

        if self._is_fast_duplicate(file):
            logger.debug("Fast deduplication hit - skipping file", file_path=str(file.path))
            stats.files_deduplicated += 1
            files_processed.labels(status="deduplicated", file_type=file_type).inc()
            return
        
        try:
            checksum = compute_sha256(file.path)
        except OSError as e:
            logger.error("Cannot read file for checksum computation", file_path=str(file.path), error=str(e))
            stats.files_failed += 1
            return
        
        if not self.dry_run:
            with get_db_session(self.session_factory) as session:
                if self.file_tracker_repo.is_already_processed(session, checksum):
                    logger.info("Checksum match - already processed file, skipping", file_path=str(file.path))
                    stats.files_deduplicated += 1
                    files_processed.labels(status="deduplicated", file_type=file_type).inc()
                    return

        tracker: FileTracker | None = None
        tracker_id: int | None = None

        if not self.dry_run:
            with get_db_session(self.session_factory) as session:
                tracker, created = self.file_tracker_repo.create_file_tracker(
                    session=session,
                    file_path=str(file.path),
                    file_name=file.path.name,
                    file_type=file_type,
                    file_size_bytes=file.size,
                    file_mtime=file.modified_at,
                    checksum_sha256=checksum
                )

                if not created:
                    if tracker.status == "done":
                        logger.info("File already processed (via checksum), skipping", file_path=str(file.path))
                        stats.files_deduplicated += 1
                        files_processed.labels(status="deduplicated", file_type=file_type).inc()
                        return
                    elif tracker.status == "processing":
                        logger.warning("Found stuck processing tracker, resetting", file_path=str(file.path), tracker_id=tracker.id)
                        tracker.status = "pending"
                        session.flush()
                self.file_tracker_repo.mark_processing(session, tracker)
                tracker_id = tracker.id
        
        with file_processing_duration.labels(file_type=file_type).time():
            try:
                inserted, produced = self._stream_file(file, parser, tracker_id)
                stats.files_parsed += 1
                stats.records_produced += produced
                stats.records_inserted += inserted
                files_processed.labels(status="done", file_type=file_type).inc()

                if not self.dry_run and tracker_id is not None:
                    with get_db_session(self.session_factory) as session:
                        tracker = session.get(FileTracker, tracker_id)
                        self.file_tracker_repo.mark_done(session, tracker, rows_inserted=inserted)
            except Exception as e:
                logger.error("Error processing file", file_path=str(file.path), error=str(e))
                stats.files_failed += 1
                stats.errors.append(PipelineError(file_path=file.path, error_message=str(e)))
                files_processed.labels(status="failed", file_type=file_type).inc()

                if not self.dry_run and tracker_id is not None:
                    with get_db_session(self.session_factory) as session:
                        tracker = session.get(FileTracker, tracker_id)
                        self.file_tracker_repo.mark_failed(session, tracker, error_message=str(e))

    def _is_fast_duplicate(self, file: BaseFile) -> bool:
        """
        Check (path, size, mtime) against FileTracker for a fast deduplication check. 
        """
        if self.dry_run:
            return False  # Don't skip any files in dry run mode
        
        _, size, mtime = fast_file_identity(file.path)

        try:
            with get_db_session(self.session_factory) as session:
                row = session.execute(
                    select(FileTracker.id).where(
                        FileTracker.file_path == str(file.path),
                        FileTracker.file_size_bytes == size,
                        FileTracker.file_mtime == mtime,
                        FileTracker.status == "done"
                    )
                ).first()
                return row is not None
        except Exception:
            return False
    
    def _stream_file(self, file: BaseFile, parser: BaseParser, tracker_id: int | None) -> tuple[int, int]:
        """
        Stream the file through the parser and flush records in batches. Returns (inserted_count, produced_count).
        """
        total_inserted = 0
        total_produced = 0
        history_log_buffer: list[HistoryLogRecord] = []
        special_event_buffer: list[SpecialEventRecord] = []
        source_file_id = tracker_id

        for record in parser.parse(file):
            total_produced += 1

            if isinstance(record, HistoryLogRecord):
                history_log_buffer.append(record)
                if len(history_log_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_history_logs(history_log_buffer, source_file_id)
                    history_log_buffer.clear()
            elif isinstance(record, SpecialEventRecord):
                special_event_buffer.append(record)
                if len(special_event_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_special_events(special_event_buffer, source_file_id)
                    special_event_buffer.clear()
            else:
                logger.warning("Unknown record type produced by parser, skipping", record=record.__dict__)

        # Flush any remaining records in buffers
        if history_log_buffer:
            total_inserted += self._flush_history_logs(history_log_buffer, source_file_id)

        if special_event_buffer:
            total_inserted += self._flush_special_events(special_event_buffer, source_file_id)

        return total_inserted, total_produced

    def _flush_history_logs(self, records: list[HistoryLogRecord], source_file_id: int | None) -> int:
        """
        Flush a batch of history log records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug("Dry run enabled - skipping DB insert for %d history log records.", len(records))
            return 0

        with get_db_session(self.session_factory) as session:
            inserted = self.history_log_repo.upsert_history_logs(session, records, source_file_id)
            records_ingested.labels(table="history_log").inc(inserted)
            logger.debug("Flushed %d history log records to the database.", inserted)
            return inserted

    def _flush_special_events(self, records: list[SpecialEventRecord], source_file_id: int | None) -> int:
        """
        Flush a batch of special event records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug("Dry run enabled - skipping DB insert for %d special event records.", len(records))
            return 0

        with get_db_session(self.session_factory) as session:
            inserted = self.special_event_repo.upsert_special_events(session, records, source_file_id)
            records_ingested.labels(table="special_event").inc(inserted)
            logger.debug("Flushed %d special event records to the database.", inserted)
            return inserted
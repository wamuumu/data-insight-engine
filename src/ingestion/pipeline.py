import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from config import load_settings
from ingestion.crawler.base import BaseFile
from ingestion.crawler.drive import DriveCrawler
from ingestion.parsers.base import BaseParser, HistoryLogRecord, RawDataRecord
from ingestion.registry import get_parser
from db.repository import upsert_history_logs, upsert_raw_data
from db.session import get_db_session

settings = load_settings()

logger = logging.getLogger(__name__)

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
    files_skipped: int = 0
    files_failed: int = 0
    records_produced: int = 0
    records_inserted: int = 0
    errors: list[PipelineError] = field(default_factory=list)

class IngestionPipeline:
    """
    Orchestrates the crawling and parsing of files for ingestion.
    """
    def __init__(self, root: Path, sessionfactory: sessionmaker, dry_run: bool = False):
        self.root = root
        self.sessionfactory = sessionfactory
        self.dry_run = dry_run
        self.crawler = DriveCrawler(root)
    
    def run(self) -> PipelineStats:
        stats = PipelineStats()
        
        for file in self.crawler.crawl():
            stats.files_discovered += 1
            logger.debug(f"Discovered file: {file.path} (size: {file.size} bytes)")
            
            parser = get_parser(file)

            if not parser:
                logger.info(f"No parser found for file: {file.path}, skipping.")
                stats.files_skipped += 1
                continue

            try:
                inserted = self._process_file(file, parser, stats)
                stats.records_inserted += inserted
                stats.files_parsed += 1
            except Exception as e:
                logger.error(f"Error processing file: {file.path}, skipping. Error: {e}")
                stats.files_failed += 1
                stats.errors.append(PipelineError(file_path=file.path, error_message=str(e)))
                continue
            
            logger.info(f"Ingestion completed. Stats: {stats}")

        return stats
    
    def _process_file(self, file: BaseFile, parser: BaseParser, stats: PipelineStats) -> int:
        """
        Stream records from a single file and flush to DB in batches. Returns the number of records inserted.
        """
        total_inserted = 0
        history_buffer: list[HistoryLogRecord] = []
        raw_data_buffer: list[RawDataRecord] = []

        for record in parser.parse(file):
            stats.records_produced += 1
            
            if isinstance(record, HistoryLogRecord):
                history_buffer.append(record)
                if len(history_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_history_logs(history_buffer)
                    history_buffer.clear()
            elif isinstance(record, RawDataRecord):
                raw_data_buffer.append(record)
                if len(raw_data_buffer) >= settings.db_batch_size:
                    total_inserted += self._flush_raw_data(raw_data_buffer)
                    raw_data_buffer.clear()
        
        # Flush remaining records
        if history_buffer:
            total_inserted += self._flush_history_logs(history_buffer)
        if raw_data_buffer:
            total_inserted += self._flush_raw_data(raw_data_buffer)
        
        return total_inserted

    def _flush_history_logs(self, records: list[HistoryLogRecord]) -> int:
        """
        Flush a batch of history log records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug(f"Dry run enabled - skipping DB insert for {len(records)} history log records.")
            return 0

        with get_db_session(self.sessionfactory) as session:
            inserted = upsert_history_logs(session, records)
            logger.debug(f"Inserted {inserted} history log records into the database.")
            return inserted

    def _flush_raw_data(self, records: list[RawDataRecord]) -> int:
        """
        Flush a batch of raw data records to the database. Returns the number of records inserted.
        """
        if self.dry_run:
            logger.debug(f"Dry run enabled - skipping DB insert for {len(records)} raw data records.")
            return 0

        with get_db_session(self.sessionfactory) as session:
            inserted = upsert_raw_data(session, records)
            logger.debug(f"Inserted {inserted} raw data records into the database.")
            return inserted
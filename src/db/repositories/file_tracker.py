import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.repositories.base import Base
from db.models.file_tracker import FileTracker

logger = logging.getLogger(__name__)


class FileTrackerRepository(Base[FileTracker]):
    def __init__(self, session: Session):
        super().__init__(FileTracker, session)

    def is_already_processed(self, checksum: str) -> bool:
        """
        Check if a file with the given checksum has already been processed.
        """
        stmt = select(FileTracker.id).where(FileTracker.checksum_sha256 == checksum, FileTracker.status == "done")
        result = self.session.execute(stmt).first()
        return result is not None

    def create_file_tracker(
        self,
        *,
        file_path: str,
        file_name: str,
        file_type: str,
        file_size_bytes: int,
        file_mtime: float,
        checksum_sha256: str
    ) -> FileTracker:
        """
        Insert a new FileTracker record into the database with status 'pending' and return the created record.
        """
        tracker = FileTracker(
            file_path=file_path,
            file_name=file_name,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            file_mtime=file_mtime,
            checksum_sha256=checksum_sha256,
            status="pending",
        )
        self.session.add(tracker)
        self.session.flush()  # Populate tracker.id without committing
        return tracker

    def mark_processing(self, tracker: FileTracker):
        """
        Update the given FileTracker record to mark it as 'processing' and set the started_at timestamp.
        """
        tracker.status = "processing"
        tracker.started_at = datetime.now(timezone.utc)
        self.session.flush()

    def mark_done(self, tracker: FileTracker, rows_produced: int, rows_inserted: int):
        """
        Update the given FileTracker record to mark it as 'done', set the finished_at timestamp, and update row counts.
        """
        tracker.status = "done"
        tracker.finished_at = datetime.now(timezone.utc)
        tracker.rows_produced = rows_produced
        tracker.rows_inserted = rows_inserted
        self.session.flush()

    def mark_failed(self, tracker: FileTracker, error_message: str):
        """
        Update the given FileTracker record to mark it as 'failed', set the finished_at timestamp, and record the error message.
        """
        tracker.status = "failed"
        tracker.finished_at = datetime.now(timezone.utc)
        tracker.error_message = error_message[:1000] # Truncate to guard against excessively long messages
        self.session.flush()
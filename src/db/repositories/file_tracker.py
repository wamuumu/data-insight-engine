from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from db.repositories.base import BaseRepository
from db.models.file_tracker import FileTracker, FileStatus

logger = get_logger(__name__)


class FileTrackerRepository(BaseRepository[FileTracker]):
    def __init__(self):
        super().__init__(FileTracker)

    def is_already_processed(
        self, 
        session: Session, 
        checksum: bytes
    ) -> bool:
        """
        Check if a file with the given checksum has already been processed.
        """
        stmt = select(FileTracker.id).where(
            FileTracker.checksum_sha256 == checksum,
            FileTracker.status == FileStatus.DONE,
        )
        result = session.execute(stmt).first()
        return result is not None

    def get_file_tracker_by_checksum(
        self, 
        session: Session, 
        checksum: bytes
    ) -> FileTracker | None:
        """
        Retrieve a FileTracker record by its checksum.
        """
        stmt = select(FileTracker).where(FileTracker.checksum_sha256 == checksum)
        return session.execute(stmt).scalar_one_or_none()

    def create_file_tracker(
        self, 
        session: Session, 
        file_path: str, 
        checksum_sha256: bytes, 
        date: date | None = None
    ) -> FileTracker:
        """
        Insert a new FileTracker record into the database with status 'pending' and return the created record.
        """
        stmt = (
            insert(FileTracker)
            .values(
                file_path=file_path,
                date=date,
                checksum_sha256=checksum_sha256,
                status=FileStatus.PENDING,
            )
            .on_conflict_do_nothing(constraint="uq_file_tracker_checksum")
            .returning(FileTracker)
        )
        return session.execute(stmt).scalar_one_or_none()

    def mark_processing(self, session: Session, tracker_id: int) -> FileTracker:
        """
        Update the given FileTracker record to mark it as 'processing' and set the started_at timestamp.
        """
        return self._transition(
            session,
            tracker_id,
            FileStatus.PROCESSING,
            started_at=datetime.now(timezone.utc)
        )

    def mark_done(self, session: Session, tracker_id: int, rows_inserted: int) -> FileTracker:
        """
        Update the given FileTracker record to mark it as 'done', set the finished_at timestamp, and update row counts.
        """
        return self._transition(
            session,
            tracker_id,
            FileStatus.DONE,
            finished_at=datetime.now(timezone.utc),
            rows_inserted=rows_inserted
        )

    def mark_failed(self, session: Session, tracker_id: int, error_message: str) -> FileTracker:
        """
        Update the given FileTracker record to mark it as 'failed', set the finished_at timestamp, and record the error message.
        """
        return self._transition(
            session,
            tracker_id,
            FileStatus.FAILED,
            finished_at=datetime.now(timezone.utc),
            last_error=error_message
        )
    
    def _transition(
        self,
        session: Session,
        tracker_id: int,
        status: FileStatus,
        **fields,
    ) -> FileTracker:
        """
        Internal method to transition a FileTracker record to a new status and update additional fields.
        """
        tracker = session.get(FileTracker, tracker_id)
        
        if tracker is None:
            raise LookupError(f"No FileTracker found for id={tracker_id}")
        
        tracker.status = status
        for field, value in fields.items():
            setattr(tracker, field, value)
        
        logger.info(
            "File tracker status updated",
            file_path=tracker.file_path,
            status=status,
            **{k: v for k, v in fields.items() if k != "last_error"}
        )

        session.flush()
        return tracker
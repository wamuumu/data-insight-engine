from datetime import date

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

    def is_already_processed(self, session: Session, checksum: bytes) -> bool:
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
        self, session: Session, checksum: bytes
    ) -> FileTracker | None:
        """
        Retrieve a FileTracker record by its checksum.
        """
        stmt = select(FileTracker).where(FileTracker.checksum_sha256 == checksum)
        result = session.execute(stmt).scalar_one_or_none()
        return result

    def create_file_tracker(
        self, session: Session, file_path: str, checksum_sha256: bytes, date: date | None = None
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
        result = session.execute(stmt).scalar_one_or_none()

        if result is None:
            # If the record already exists, fetch it
            result = self.get_file_tracker_by_checksum(session, checksum_sha256)

        return result

    def mark_processing(self, session: Session, tracker: FileTracker):
        """
        Update the given FileTracker record to mark it as 'processing' and set the started_at timestamp.
        """
        tracker.status = FileStatus.PROCESSING
        logger.info("File processing started", file_path=tracker.file_path)
        session.flush()

    def mark_done(self, session: Session, tracker: FileTracker, rows_inserted: int):
        """
        Update the given FileTracker record to mark it as 'done', set the finished_at timestamp, and update row counts.
        """
        tracker.status = FileStatus.DONE
        logger.info(
            "File processing completed",
            file_path=tracker.file_path,
            rows_inserted=rows_inserted,
        )
        session.flush()

    def mark_failed(self, session: Session, tracker: FileTracker, error_message: str):
        """
        Update the given FileTracker record to mark it as 'failed', set the finished_at timestamp, and record the error message.
        """
        tracker.status = FileStatus.FAILED
        logger.error(
            "File processing failed",
            file_path=tracker.file_path,
            error_message=error_message,
        )
        session.flush()

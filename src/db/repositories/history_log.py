from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from db.repositories.base import BaseRepository
from db.models.history_log import HistoryLog
from ingestion.parsers.base import HistoryLogRecord

logger = get_logger(__name__)


class HistoryLogRepository(BaseRepository[HistoryLog]):
    def __init__(self):
        super().__init__(HistoryLog)

    def upsert_history_logs(
        self,
        session: Session,
        records: list[HistoryLogRecord],
        device_id: int,
        source_file_id: int,
    ) -> int:
        """
        Batch-upsert history log records into the database. Returns the number of records successfully inserted.
        """
        if not records:
            return 0

        rows = [self._history_log_to_row(r, device_id, source_file_id) for r in records]
        result = session.execute(
            insert(HistoryLog)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_history_log_row")
        )
        return result.rowcount or 0

    def delete_history_logs_by_file(self, session: Session, source_file_id: int) -> int:
        """
        Delete history log records associated with a specific source file. Returns the number of records deleted.
        """
        result = (
            session.query(HistoryLog)
            .filter(HistoryLog.source_file_id == source_file_id)
            .delete()
        )
        return result

    def _history_log_to_row(
        self, record: HistoryLogRecord, device_id: int, source_file_id: int
    ) -> dict:
        """
        Convert a HistoryLogRecord to a dictionary suitable for database insertion.
        """

        return {
            "device_id": device_id,
            "firmware_version": record.data.get("firmware_version"),
            "event_ts": record.data.get("event_datetime"),
            "event_id": record.data.get("event_id"),
            "value": record.data.get("value"),
            "source_file_id": source_file_id,
        }

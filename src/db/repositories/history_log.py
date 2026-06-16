from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from common.utils import combine_date_time
from db.repositories.base import BaseRepository
from db.models.history_log import HistoryLog
from ingestion.parsers.base import HistoryLogRecord

logger = get_logger(__name__)


class HistoryLogRepository(BaseRepository[HistoryLog]):
    def __init__(self):
        super().__init__(HistoryLog)

    def insert_history_logs(
        self,
        session: Session,
        records: list[HistoryLogRecord],
        device_id: int,
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-insert history log records into the database. Returns the number of records successfully inserted.
        """
        if not records:
            return 0
        
        rows = [self._history_log_to_row(r, device_id, source_file_id) for r in records]
        result = session.execute(insert(HistoryLog).values(rows))
        return result.rowcount

    def _history_log_to_row(self, record: HistoryLogRecord, device_id: int, source_file_id: int | None) -> dict:
        """
        Convert a HistoryLogRecord to a dictionary suitable for database insertion.
        """
        raw_date: str = record.data.get("event_date")
        raw_time: str = record.data.get("event_time")

        event_dt = combine_date_time(raw_date, raw_time)

        return {
            "device_id": device_id,
            "firmware_version": record.data.get("firmware_version"),
            "event_ts": event_dt,
            "event_id": record.data.get("event_id"),
            "value": record.data.get("value"),
            "source_file_id": source_file_id,
        }
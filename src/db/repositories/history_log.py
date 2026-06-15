from dateutil.parser import parse as dateutil_parse
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
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-upsert history log records into the database. Duplicates are allowed.
        """
        if not records:
            return 0
        
        rows = [self._history_log_to_row(r, source_file_id) for r in records]

        stmt = (
            insert(HistoryLog)
            .values(rows)          
        )
        result = session.execute(stmt)
        return result.rowcount

    def _history_log_to_row(self, record: HistoryLogRecord, source_file_id: int | None) -> dict:
        """
        Convert a HistoryLogRecord to a dictionary suitable for database insertion.
        """
        raw_date: str = record.data.get("event_date")
        raw_time: str = record.data.get("event_time")

        try:
            parsed_date = dateutil_parse(raw_date, dayfirst=True).date()
        except Exception as e:
            logger.warning("Failed to parse date", date=raw_date, record=record, error=str(e))
            parsed_date = None
        
        try:
            parsed_time = dateutil_parse(raw_time).time()
        except Exception as e:
            logger.warning("Failed to parse time", time=raw_time, record=record, error=str(e))
            parsed_time = None
        
        return {
            "serial_number": record.data.get("serial_number"),
            "firmware_version": record.data.get("firmware_version"),
            "event_date": parsed_date,
            "event_time": parsed_time,
            "event_id": record.data.get("event_id"),
            "value": record.data.get("value"),
            "source_file_id": source_file_id,
        }
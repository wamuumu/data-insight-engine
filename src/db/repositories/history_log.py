import logging

from dateutil.parser import parse as dateutil_parse
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.repositories.base import Base
from db.models.history_log import HistoryLog
from ingestion.parsers.base import HistoryLogRecord

logger = logging.getLogger(__name__)


class HistoryLogRepository(Base[HistoryLog]):
    def __init__(self, session: Session):
        super().__init__(HistoryLog, session)

    def upsert_history_logs(
        self,
        records: list[HistoryLogRecord],
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-upsert history log records into the database. Duplicates are silently skipped. Returns the number of records successfully inserted.
        """
        if not records:
            return 0
        
        rows = [self._history_log_to_row(r, source_file_id) for r in records]

        stmt = (
            insert(HistoryLog)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_history_log_entry")            
        )
        result = self.session.execute(stmt)
        return result.rowcount

    def _history_log_to_row(self, record: HistoryLogRecord, source_file_id: int | None) -> dict:
        """
        Convert a HistoryLogRecord to a dictionary suitable for database insertion.
        """
        raw_date: str = record.data.get("date")
        raw_time: str = record.data.get("time")

        try:
            parsed_date = dateutil_parse(raw_date, dayfirst=True).date()
        except Exception as e:
            logger.warning(f"Failed to parse date '{raw_date}' for record {record}. Error: {e}")
            parsed_date = None
        
        try:
            parsed_time = dateutil_parse(raw_time).time()
        except Exception as e:
            logger.warning(f"Failed to parse time '{raw_time}' for record {record}. Error: {e}")
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
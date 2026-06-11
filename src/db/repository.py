import logging
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models.history import HistoryLog
from db.models.raw_data import RawData
from ingestion.parsers.base import HistoryLogRecord, RawDataRecord


def upsert_history_logs(session: Session, records: list[HistoryLogRecord]) -> int:
    """
    Upsert a batch of history log records into the database, skipping duplicates.
    Returns the number of records successfully inserted.
    """
    if not records:
        return 0
    
    rows = [_history_log_to_row(r) for r in records]

    stmt = (
        insert(HistoryLog)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_history_log_entry")
    )
    
    result = session.execute(stmt)
    return result.rowcount

def _history_log_to_row(record: HistoryLogRecord) -> dict:
    return {
        "serial_number": record.data.get("serial_number"),
        "firmware_version": record.data.get("firmware_version"),
        "date": record.data.get("date"),
        "time": record.data.get("time"),
        "event_id": record.data.get("event_id"),
        "value": record.data.get("value"),
    }

def upsert_raw_data(session: Session, records: list[RawDataRecord]) -> int:
    """
    Insert a batch of raw data records into the database.
    Returns the number of records successfully inserted.
    """
    if not records:
        return 0
    
    rows = [_raw_data_to_row(r) for r in records]

    stmt = insert(RawData).values(rows)
    result = session.execute(stmt)
    return result.rowcount

def _raw_data_to_row(record: RawDataRecord) -> dict:
    return {
        "source_file": record.source_file,
        "data": record.data,
    }
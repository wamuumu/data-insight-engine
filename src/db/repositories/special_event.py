from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from db.repositories.base import BaseRepository
from db.models.special_event import SpecialEvent
from ingestion.parsers.base import SpecialEventRecord

logger = get_logger(__name__)


class SpecialEventRepository(BaseRepository[SpecialEvent]):
    def __init__(self):
        super().__init__(SpecialEvent)

    def insert_special_events(
        self,
        session: Session,
        records: list[SpecialEventRecord],
        device_id: int,
        source_file_id: int,
    ) -> int:
        """
        Insert special event records into the database. Returns the number of records successfully inserted.
        """
        if not records:
            return 0

        rows = [self._special_event_to_row(r, device_id, source_file_id) for r in records]
        result = session.execute(
            insert(SpecialEvent)
            .values(rows)
        )
        inserted = max(result.rowcount, 0)

        return inserted

    def delete_special_events_by_file(
        self, 
        session: Session, 
        source_file_id: int
    ) -> int:
        """
        Delete special event records associated with a specific source file. Returns the number of records deleted.
        """
        result = (
            session.query(SpecialEvent)
            .filter(SpecialEvent.source_file_id == source_file_id)
            .delete()
        )
        return result

    def _special_event_to_row(
        self, 
        record: SpecialEventRecord, 
        device_id: int, 
        source_file_id: int
    ) -> dict:
        """
        Convert a SpecialEventRecord to a dictionary suitable for database insertion.
        """

        return {
            "device_id": device_id,
            "source_file_id": source_file_id,
            **record.data,
        }

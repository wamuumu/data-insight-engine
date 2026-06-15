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

    def upsert_special_events(
        self,
        session: Session,
        records: list[SpecialEventRecord],
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-upsert special event records into the database. Duplicates are checked using file_tracker. Returns the number of records successfully inserted.
        """
        if not records:
            return 0
        
        rows = [self._special_event_to_row(r, source_file_id) for r in records]
        result = session.execute(insert(SpecialEvent).values(rows))
        return result.rowcount

    def _special_event_to_row(self, record: SpecialEventRecord, source_file_id: int | None) -> dict:
        """
        Convert a SpecialEventRecord to a dictionary suitable for database insertion.
        """
        
        return {
            "serial_number": record.serial_number,
            "acc_x": record.data.get("acc_x"),
            "acc_y": record.data.get("acc_y"),
            "acc_z": record.data.get("acc_z"),
            "gyro_x": record.data.get("gyro_x"),
            "gyro_y": record.data.get("gyro_y"),
            "gyro_z": record.data.get("gyro_z"),
            "hdop": record.data.get("hdop"),
            "lat": record.data.get("lat"),
            "lon": record.data.get("lon"),
            "speed": record.data.get("speed"),
            "gps_fix": bool(record.data.get("gps_fix")),
            "time": record.data.get("time"),
            "alarms": record.data.get("alarms"),
            "algo_ignited": bool(record.data.get("algo_ignited")),
            "algo_enabled": bool(record.data.get("algo_enabled")),
            "source_file_id": source_file_id,
        }
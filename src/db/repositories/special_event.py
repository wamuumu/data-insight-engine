from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from common.utils import construct_time
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
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-insert special event records into the database. Returns the number of records successfully inserted.
        """
        if not records:
            return 0
        
        rows = [self._special_event_to_row(r, device_id, source_file_id) for r in records]
        result = session.execute(insert(SpecialEvent).values(rows))
        return result.rowcount
    
    def delete_special_events_by_file(self, session: Session, source_file_id: int) -> int:
        """
        Delete special event records associated with a specific source file. Returns the number of records deleted.
        """
        result = session.query(SpecialEvent).filter(SpecialEvent.source_file_id == source_file_id).delete()
        return result

    def _special_event_to_row(self, record: SpecialEventRecord, device_id: int, source_file_id: int | None) -> dict:
        """
        Convert a SpecialEventRecord to a dictionary suitable for database insertion.
        """
        
        _hr = record.data.get("hour")
        _mn = record.data.get("min")
        _sc = record.data.get("sec")
        _cent = record.data.get("cent")
        time = construct_time(_hr, _mn, _sc, _cent)
        
        return {
            "device_id": device_id,
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
            "time": time,
            "alarms": record.data.get("alarms"),
            "algo_ignited": bool(record.data.get("algo_ignited")),
            "algo_enabled": bool(record.data.get("algo_enabled")),
            "source_file_id": source_file_id,
        }